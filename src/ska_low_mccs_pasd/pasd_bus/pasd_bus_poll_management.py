# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements polling management for a PaSD bus."""


import logging
import threading
from typing import Any, Callable, Final, Iterator, Sequence

NUMBER_OF_FNDH_PORTS: Final = 28
NUMBER_OF_SMARTBOXES: Final = 24
NUMBER_OF_SMARTBOX_PORTS: Final = 12
NUMBER_OF_FNDH_INITIAL_READS: Final = 2


def fndh_read_request_iterator() -> Iterator[str]:
    """
    Return an iterator that says what attributes should be read next on the FNDH.

    It starts by reading static information attributes,
    then moves on to writable attributes that are otherwise static,
    and then loops forever, alternating between status attributes and port attributes.

    :yields: the name of an attribute group to be read from the device.
    """
    yield "INFO"
    yield "PORTS"
    yield "THRESHOLDS"
    while True:
        yield "STATUS"
        yield "PORTS"
        yield "WARNING_FLAGS"
        yield "ALARM_FLAGS"


def smartbox_read_request_iterator() -> Iterator[str]:
    """
    Return an iterator that says what attributes should be read next on a smartbox.

    It starts by reading static information attributes,
    then moves on to writable attributes that are otherwise static,
    and then loops forever, alternating between status attributes and port attributes.

    :yields: the name of an attribute group to be read from the device.
    """
    yield "INFO"
    yield "THRESHOLDS"
    yield "CURRENT_TRIP_THRESHOLDS"
    while True:
        yield "STATUS"
        yield "PORTS"
        yield "WARNING_FLAGS"
        yield "ALARM_FLAGS"


class DeviceRequestProvider:  # pylint: disable=too-many-instance-attributes
    """
    A class that determines the next communication with a specified device.

    It keeps track of the current intent of PaSD monitoring and control,
    for example, whether a command has been requested to be executed on the device;
    and it decides what, if any, communication with it should occur in the next poll.
    """

    def __init__(
        self,
        number_of_ports: int,
        read_request_iterator_factory: Callable[[], Iterator[str]],
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param number_of_ports: the number of ports this device has.
        :param read_request_iterator_factory: a callable that returns
            a read request iterator
        :param logger: a logger.
        """
        self._lock = threading.Lock()

        self._logger = logger

        self._initialize_requested: bool = False
        self._led_pattern_requested: str = ""
        self._alarm_reset_requested: bool = False
        self._warning_reset_requested: bool = False
        self._port_power_changes: list[tuple[bool, bool] | None] = [
            None
        ] * number_of_ports
        self._port_breaker_resets: list[bool] = [False] * number_of_ports
        self._attribute_writes: dict[str, list[Any]] = {}

        self._read_request_iterator = read_request_iterator_factory()

    def desire_initialize(self) -> None:
        """Register a request to initialize the device."""
        self._initialize_requested = True

    def desire_alarm_reset(self) -> None:
        """Register a request to reset the alarm."""
        self._alarm_reset_requested = True

    def desire_warning_reset(self) -> None:
        """Register a request to reset the warning state."""
        self._warning_reset_requested = True

    def desire_port_powers(
        self,
        port_powers: Sequence[bool | None],
        stay_on_when_offline: bool,
    ) -> None:
        """
        Register a request to modify the power of some device ports.

        :param port_powers: a desired port power state for each port.
            True means the port is desired on,
            False means it is desired off,
            None means no desire to change the port.
        :param stay_on_when_offline: whether any ports being turned on
            should remain on if MCCS loses its connection with the PaSD.
        """
        with self._lock:
            for index, power in enumerate(port_powers):
                if power is None:
                    continue
                self._port_power_changes[index] = (power, stay_on_when_offline)

    def desire_port_breaker_reset(self, port_number: int) -> None:
        """
        Register a request to reset a port breaker.

        :param port_number: the number of the port whose breaker is to
            be reset.
        """
        self._port_breaker_resets[port_number - 1] = True

    def desire_led_pattern(self, pattern: str) -> None:
        """
        Register a request to set the device's LED pattern.

        :param pattern: the name of the LED pattern.
        """
        self._led_pattern_requested = pattern

    def desire_attribute_write(self, attribute_name: str, values: list[Any]) -> None:
        """
        Register a request to write an attribute.

        :param attribute_name: the name of the attribute to set.
        :param values: the new value(s) to write.
        """
        self._attribute_writes[attribute_name] = values

    def get_write(self) -> tuple[str, Any]:
        """
        Return a description of the next write / command to be performed on the device.

        :return: A tuple, comprising the name of the write / command,
            along with any additional information such as the value to be written.
        """
        if self._initialize_requested:
            self._initialize_requested = False
            return "INITIALIZE", None

        if self._attribute_writes:
            attribute_name, values = self._attribute_writes.popitem()
            return "WRITE", (attribute_name, values)

        if self._led_pattern_requested:
            pattern = self._led_pattern_requested
            self._led_pattern_requested = ""
            return "LED_PATTERN", pattern

        for port, reset in enumerate(self._port_breaker_resets, start=1):
            if reset is True:
                self._port_breaker_resets[port - 1] = False
                return "BREAKER_RESET", port

        with self._lock:
            # TODO: [WOM-149] Support updating port power for many ports at once.
            for port, change in enumerate(self._port_power_changes, start=1):
                if change is None:
                    continue
                self._port_power_changes[port - 1] = None
                return "PORT_POWER", (port, *change)

        return "NONE", None

    def get_read(self) -> str:
        """
        Return a description of the next read to be performed on the device.

        :return: The name of the next read to be performed on the device.
        """
        return next(self._read_request_iterator)


class PasdBusRequestProvider:
    """
    A class that determines the next communication with the PaSD, across all devices.

    It ensures that:

    * a certain number of ticks are guaranteed to have passed between
      communications with any single device.

    * commands get executed as promptly as possible

    * device attributes are polled as frequently as possible,
      given the above constraints
    """

    def __init__(self, min_ticks: int, logger: logging.Logger) -> None:
        """
        Initialise a new instance.

        :param min_ticks: minimum number of ticks between communications
            with any given device
        :param logger: a logger.
        """
        self._lock = threading.Lock()

        self._min_ticks = min_ticks
        self._logger = logger

        self._ticks = {
            device_number: self._min_ticks
            for device_number in range(NUMBER_OF_SMARTBOXES + 1)
        }

        fndh_request_provider = DeviceRequestProvider(
            NUMBER_OF_FNDH_PORTS, fndh_read_request_iterator, logger
        )
        smartbox_request_providers = [
            DeviceRequestProvider(
                NUMBER_OF_SMARTBOX_PORTS, smartbox_read_request_iterator, logger
            )
            for _ in range(NUMBER_OF_SMARTBOXES)
        ]
        self._device_request_providers = [
            fndh_request_provider
        ] + smartbox_request_providers

        self._fndh_initial_read_count = 0

    def desire_initialize(self, device_id: int) -> None:
        """
        Register a request to initialize a device.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        """
        self._device_request_providers[device_id].desire_initialize()

    def desire_attribute_write(
        self, device_id: int, name: str, values: list[Any]
    ) -> None:
        """
        Register a request to write an attribute.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param name: the name of the attribute to write.
        :param values: the new value(s) to write.
        """
        self._device_request_providers[device_id].desire_attribute_write(name, values)

    def desire_alarm_reset(self, device_id: int) -> None:
        """
        Register a request to reset an alarm.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        """
        self._device_request_providers[device_id].desire_alarm_reset()

    def desire_warning_reset(self, device_id: int) -> None:
        """
        Register a request to reset a warning.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        """
        self._device_request_providers[device_id].desire_warning_reset()

    def desire_port_powers(
        self,
        device_id: int,
        port_powers: Sequence[bool | None],
        stay_on_when_offline: bool,
    ) -> None:
        """
        Register a request to turn some of device's ports on.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param port_powers: a desired port power state for each port.
            True means the port is desired on,
            False means it is desired off,
            None means no desire to change the port.
        :param stay_on_when_offline: whether any ports being turned on
            should remain on if MCCS loses its connection with the PaSD.
        """
        self._device_request_providers[device_id].desire_port_powers(
            port_powers, stay_on_when_offline
        )

    def desire_port_breaker_reset(self, device_id: int, port_number: int) -> None:
        """
        Register a request to reset a port breaker.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param port_number: the number of the port whose breaker is to
            be reset.
        """
        self._device_request_providers[device_id].desire_port_breaker_reset(port_number)

    def desire_led_pattern(self, device_id: int, pattern: str) -> None:
        """
        Register a request to set a device's LED pattern.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param pattern: the name of the LED pattern.
        """
        self._device_request_providers[device_id].desire_led_pattern(pattern)

    def get_request(self) -> tuple[int, str, Any] | None:
        """
        Get a description of the next communication with the PaSD bus.

        :return: a tuple consisting of the name of the communication
            and any arguments or extra information.
        """
        if self._fndh_initial_read_count != NUMBER_OF_FNDH_INITIAL_READS:
            # First read the FNDH status to get the Modbus map revision number
            # and so we know which SmartBoxes are connected. This requires
            # two reads.
            read_request = self._device_request_providers[0].get_read()
            self._fndh_initial_read_count += 1
            return 0, read_request, None

        for device_id, tick in self._ticks.items():
            self._ticks[device_id] = tick + 1

        for device_id, tick in self._ticks.items():
            if tick < self._min_ticks:
                break
            write_request = self._device_request_providers[device_id].get_write()
            if write_request != ("NONE", None):
                # By deleting this before zeroing it,
                # we ensure the new zeroed value is added to the end of the dict,
                # and hence the dict is maintained in descending order of ticks,
                # which is what lets us break out of this loop
                # as soon as we encounter a tick less than the minimum.
                del self._ticks[device_id]
                self._ticks[device_id] = 0
                return device_id, *write_request

        for device_id, tick in self._ticks.items():
            if tick < self._min_ticks:
                break
            read_request = self._device_request_providers[device_id].get_read()
            del self._ticks[device_id]  # see comment above
            self._ticks[device_id] = 0
            return device_id, read_request, None

        return None
