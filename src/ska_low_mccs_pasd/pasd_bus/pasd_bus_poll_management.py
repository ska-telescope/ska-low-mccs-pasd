# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements polling management for a PaSD bus."""


import logging
from typing import Any, Callable, Iterator, Optional, Sequence

from ska_low_mccs_pasd.pasd_data import PasdData


def fndh_read_request_iterator() -> Iterator[str]:
    """
    Return an iterator that says what attributes should be read next on the FNDH.

    It starts by reading static information attributes,
    then moves on to writable attributes that are otherwise static,
    and then loops forever, alternating between status attributes and port attributes.

    :yields: the name of an attribute group to be read from the device.
    """
    yield "INFO"
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
        self._logger = logger

        self._initialize_requested: bool = False
        self._led_pattern_requested: str = ""
        self._low_pass_filter_block_1_requested: tuple[float, bool] | None = None
        self._low_pass_filter_block_2_requested: tuple[float, bool] | None = None
        self._alarm_reset_requested: bool = False
        self._warning_reset_requested: bool = False
        self._port_power_changes: list[tuple[bool, bool] | None] = [
            None
        ] * number_of_ports
        self._port_breaker_resets: list[bool] = [False] * number_of_ports
        self._attribute_writes: dict[str, list[Any]] = {}

        # Store a list of attribute names for expedited reading
        # following a write command
        self._attribute_update_requests: list[str] = []
        self._ports_status_update_request: bool = False

        self._read_request_iterator_factory = read_request_iterator_factory
        self._read_request_iterator = read_request_iterator_factory()

    def desire_read_startup_info(self) -> None:
        """Register a request to read the info usually just read on startup."""
        self._read_request_iterator = self._read_request_iterator_factory()

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

        :param pattern: name of the service LED pattern.
        """
        self._led_pattern_requested = pattern

    def desire_set_low_pass_filter(
        self, cutoff: float, extra_sensors: bool
    ) -> Optional[bool]:
        """
        Register a request to set the device's low pass filter constants.

        :param cutoff: frequency of LPF to set.
        :param extra_sensors: write the constant to the extra sensors' registers after
            the LED status register.
        :return: whether successful, or None if there was nothing to do.
        """
        if extra_sensors:
            self._low_pass_filter_block_2_requested = (cutoff, True)
        else:
            self._low_pass_filter_block_1_requested = (cutoff, False)
        return True

    def desire_attribute_write(self, attribute_name: str, values: list[Any]) -> None:
        """
        Register a request to write an attribute.

        :param attribute_name: the name of the attribute to set.
        :param values: the new value(s) to write.
        """
        self._attribute_writes[attribute_name] = values

    # pylint: disable=too-many-return-statements
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
            self._attribute_update_requests.append(attribute_name)
            return "WRITE", (attribute_name, values)

        if self._led_pattern_requested:
            pattern = self._led_pattern_requested
            self._led_pattern_requested = ""
            self._attribute_update_requests.append("led_pattern")
            return "LED_PATTERN", pattern

        if self._low_pass_filter_block_1_requested is not None:
            arguments = self._low_pass_filter_block_1_requested
            self._low_pass_filter_block_1_requested = None
            return "SET_LOW_PASS_FILTER", arguments

        if self._low_pass_filter_block_2_requested is not None:
            arguments = self._low_pass_filter_block_2_requested
            self._low_pass_filter_block_2_requested = None
            return "SET_LOW_PASS_FILTER", arguments

        for port, reset in enumerate(self._port_breaker_resets, start=1):
            if reset is True:
                self._port_breaker_resets[port - 1] = False
                return "BREAKER_RESET", port

        for port, change in enumerate(self._port_power_changes, start=1):
            if change is not None:
                requested_powers = self._port_power_changes
                self._port_power_changes = [None] * len(requested_powers)
                self._ports_status_update_request = True
                return "SET_PORT_POWERS", requested_powers

        return "NONE", None

    def get_read(self) -> str:
        """
        Return a description of the next read to be performed on the device.

        :return: The name of the next read to be performed on the device.
        """
        return next(self._read_request_iterator)

    def get_expedited_read(self) -> tuple[str, Any]:
        """
        Return a description of an expedited read request.

        This is required for attributes which have been written to by the user,
        so we don't have to wait until their turn in the regular poll.

        :return: A tuple, consisting of the name of a predefined attribute set
            (see PasdBusComponentManager), or the command READ along with the
            name of the specific attribute to be read.
        """
        if self._ports_status_update_request:
            self._ports_status_update_request = False
            return "PORTS", None
        if self._attribute_update_requests:
            return "READ", self._attribute_update_requests.pop(0)
        return "NONE", None


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
        self._min_ticks = min_ticks
        self._logger = logger

        self._ticks = {
            device_number: self._min_ticks
            for device_number in range(PasdData.NUMBER_OF_SMARTBOXES + 1)
        }

        fndh_request_provider = DeviceRequestProvider(
            PasdData.NUMBER_OF_FNDH_PORTS, fndh_read_request_iterator, logger
        )
        smartbox_request_providers = [
            DeviceRequestProvider(
                PasdData.NUMBER_OF_SMARTBOX_PORTS,
                smartbox_read_request_iterator,
                logger,
            )
            for _ in range(PasdData.NUMBER_OF_SMARTBOXES)
        ]
        self._device_request_providers = [
            fndh_request_provider
        ] + smartbox_request_providers

    def desire_read_startup_info(self, device_id: int) -> None:
        """
        Register a request to read the information usually just read at startup.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        """
        self._device_request_providers[device_id].desire_read_startup_info()

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
        :param pattern: name of the service LED pattern.
        """
        self._device_request_providers[device_id].desire_led_pattern(pattern)

    def desire_set_low_pass_filter(
        self, device_id: int, cutoff: float, extra_sensors: bool
    ) -> Optional[bool]:
        """
        Register a request to set a device's low pass filter constants.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param cutoff: frequency of LPF to set.
        :param extra_sensors: write the constant to the extra sensors' registers after
            the LED status register.
        :return: whether successful, or None if there was nothing to do.
        """
        return self._device_request_providers[device_id].desire_set_low_pass_filter(
            cutoff, extra_sensors
        )

    def get_request(self) -> tuple[int, str, Any] | None:
        """
        Get a description of the next communication with the PaSD bus.

        :return: a tuple consisting of the name of the communication
            and any arguments or extra information.
        """
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

        # Next check if any expedited attribute reads need to be done.
        for device_id, tick in self._ticks.items():
            if tick < self._min_ticks:
                break
            expedited_read_request = self._device_request_providers[
                device_id
            ].get_expedited_read()
            if expedited_read_request != ("NONE", None):
                del self._ticks[device_id]  # see comment above
                self._ticks[device_id] = 0
                return device_id, *expedited_read_request

        # No outstanding reads/writes remaining, so cycle through the polling list.
        for device_id, tick in self._ticks.items():
            if tick < self._min_ticks:
                break
            read_request = self._device_request_providers[device_id].get_read()
            del self._ticks[device_id]  # see comment above
            self._ticks[device_id] = 0
            return device_id, read_request, None

        return None
