# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements polling management for a PaSD bus."""


import logging
import time
from dataclasses import dataclass
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


def fncc_read_request_iterator() -> Iterator[str]:
    """
    Return an iterator that says what attributes should be read next on the FNCC.

    It starts by reading static information attributes
    and then loops forever to read the status.

    :yields: the name of an attribute group to be read from the device.
    """
    yield "INFO"
    # Delay starting the status loop until all other info has been read
    for _ in range(6):
        yield ""
    while True:
        yield "STATUS"


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


@dataclass
class ExpeditedReadRequest:
    """
    Class to represent an expedited read request.

    Encapsulates data about a read request including a
    'not before' timestamp to allow time for the register
    in question to be updated.
    """

    device_id: int
    request_description: tuple[str, Any]
    not_before: float

    def __post_init__(self) -> None:
        """Post init method to record the request timestamp."""
        self.timestamp = time.time()


class DeviceRequestProvider:
    """
    A class that determines the next communication with a specified device.

    It keeps track of the current intent of PaSD monitoring and control,
    for example, whether a command has been requested to be executed on the device;
    and it decides what, if any, communication with it should occur in the next poll.
    """

    # pylint: disable=too-many-arguments,too-many-instance-attributes
    # pylint: disable=too-many-positional-arguments
    def __init__(
        self,
        number_of_ports: int,
        read_request_iterator_factory: Callable[[], Iterator[str]],
        attribute_read_delay: float,
        port_status_read_delay: float,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param number_of_ports: the number of ports this device has.
        :param read_request_iterator_factory: a callable that returns
            a read request iterator
        :param attribute_read_delay: time in seconds to wait after writing an
            attribute before reading it again
        :param port_status_read_delay: time in seconds to wait after setting
            port status before reading it again
        :param logger: a logger.
        """
        self._logger = logger

        self._initialize_requested: bool = False
        self._led_pattern_requested: str = ""
        self._low_pass_filter_block_1_requested: tuple[float, bool] | None = None
        self._low_pass_filter_block_2_requested: tuple[float, bool] | None = None
        self._alarm_reset_requested: bool = False
        self._warning_reset_requested: bool = False
        self._status_reset_requested: bool = False
        self._status_read_requested: bool = False
        self._port_power_changes: list[tuple[bool, bool] | None] = [
            None
        ] * number_of_ports
        self._port_breaker_resets: list[bool] = [False] * number_of_ports
        self._attribute_writes: dict[str, list[Any]] = {}

        # Store a list of attribute names for expedited reading
        # following a write command
        self._attribute_update_requests: list[str] = []
        self._ports_status_update_request: bool = False

        self._attribute_read_delay = attribute_read_delay
        self._port_status_read_delay = port_status_read_delay

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

    def desire_status_reset(self) -> None:
        """Register a request to reset the status register."""
        self._status_reset_requested = True

    def desire_status_read(self) -> None:
        """Register a request to read the status register.

        This is done whenever a comms failure has occurred to attempt to
        re-establish communications.
        """
        self._status_read_requested = True

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

    def desire_set_low_pass_filter(self, cutoff: float, extra_sensors: bool) -> None:
        """
        Register a request to set the device's low pass filter constants.

        :param cutoff: frequency of LPF to set.
        :param extra_sensors: write the constant to the extra sensors' registers after
            the LED status register.
        """
        if extra_sensors:
            self._low_pass_filter_block_2_requested = (cutoff, True)
        else:
            self._low_pass_filter_block_1_requested = (cutoff, False)

    def desire_attribute_write(self, attribute_name: str, values: list[Any]) -> None:
        """
        Register a request to write an attribute.

        :param attribute_name: the name of the attribute to set.
        :param values: the new value(s) to write.
        """
        self._attribute_writes[attribute_name] = values

    # pylint: disable=too-many-return-statements
    def get_write(self) -> tuple[str, Any]:  # noqa: C901
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

        if any(change is not None for change in self._port_power_changes):
            requested_powers = self._get_requested_port_powers()
            return "SET_PORT_POWERS", requested_powers

        if self._status_reset_requested:
            self._status_reset_requested = False
            return "RESET_STATUS", None

        if self._alarm_reset_requested:
            self._alarm_reset_requested = False
            self._attribute_update_requests.append("alarm_flags")
            return "RESET_ALARMS", None

        if self._warning_reset_requested:
            self._warning_reset_requested = False
            self._attribute_update_requests.append("warning_flags")
            return "RESET_WARNINGS", None

        return "NONE", None

    def _get_requested_port_powers(self) -> list[tuple[bool, bool] | None]:
        requested_powers = self._port_power_changes
        self._port_power_changes = [None] * len(requested_powers)
        self._ports_status_update_request = True
        return requested_powers

    def get_read(self) -> str:
        """
        Return a description of the next read to be performed on the device.

        :return: The name of the next read to be performed on the device.
        """
        return next(self._read_request_iterator)

    def get_expedited_read(self, device_id: int) -> ExpeditedReadRequest | None:
        """
        Return an ExpeditedReadRequest for future action.

        This is required for attributes which have been written to by the user,
        so we don't have to wait until their turn in the regular poll.

        :param: device_id: The id of the device requiring the request.
        :return: An ExpeditedReadRequest, encapsulating information about
            the request to make and when it should be actioned.
        """
        if self._ports_status_update_request:
            self._ports_status_update_request = False
            return ExpeditedReadRequest(
                device_id, ("PORTS", None), time.time() + self._port_status_read_delay
            )
        if self._attribute_update_requests:
            return ExpeditedReadRequest(
                device_id,
                ("READ", self._attribute_update_requests.pop(0)),
                time.time() + self._attribute_read_delay,
            )
        return None

    def get_expedited_writes(self, device_id: int) -> list[ExpeditedReadRequest] | None:
        """
        Get any expedited writes for the device.

        By default there are no expedited writes.

        :param device_id: The id of the device requiring the request.

        :returns: a list of expedited requests.
        """
        return None


# pylint: disable=too-many-positional-arguments, too-many-arguments
class FndhRequestProvider(DeviceRequestProvider):
    """
    A class to handle staggered powering of Fndh ports.

    A request for powering N ports becomes N requests for powering 1 port.
    """

    def __init__(
        self,
        number_of_ports: int,
        read_request_iterator_factory: Callable[[], Iterator[str]],
        attribute_read_delay: float,
        port_status_read_delay: float,
        port_power_delay: float,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param number_of_ports: the number of ports this device has.
        :param read_request_iterator_factory: a callable that returns
            a read request iterator
        :param attribute_read_delay: time in seconds to wait after writing an
            attribute before reading it again
        :param port_status_read_delay: time in seconds to wait after setting
            port status before reading it again
        :param port_power_delay: 5ime in seconds to wait between setting
            each FNDH port power.
        :param logger: a logger.
        """
        self._port_power_delay = port_power_delay
        super().__init__(
            number_of_ports,
            read_request_iterator_factory,
            attribute_read_delay,
            port_status_read_delay,
            logger,
        )

    def _get_requested_port_powers(self) -> list[tuple[bool, bool] | None]:
        """
        Get requested FNDH port powers.

        The initial request is simply recorded to be fulfilled through expedited
        requests later.

        :returns: no ports to change immediately.
        """
        return [None] * len(self._port_power_changes)

    def get_expedited_writes(self, device_id: int) -> list[ExpeditedReadRequest] | None:
        """
        Get any expedited writes for the FNDH.

        A command to set port powers will be converted into N requests to write,
        interleaved with N requests to read.

        :param device_id: The id of the device requiring the request.

        :returns: a list of expedited requests.
        """
        expedited_requests = []
        offset = 0
        for requested_port, port_power in enumerate(self._port_power_changes):
            if port_power is not None:
                requested_powers: list[tuple[bool, bool] | None] = [None] * len(
                    self._port_power_changes
                )
                requested_powers[requested_port] = port_power
                self._port_power_changes[requested_port] = None
                port_power_time = time.time() + offset * self._port_power_delay
                port_read_time = port_power_time + self._port_status_read_delay
                expedited_requests.append(
                    ExpeditedReadRequest(
                        device_id,
                        ("SET_PORT_POWERS", requested_powers),
                        port_power_time,
                    )
                )
                expedited_requests.append(
                    ExpeditedReadRequest(
                        device_id,
                        ("PORTS", None),
                        port_read_time,
                    )
                )
                offset += 1
        if expedited_requests:
            return expedited_requests
        return super().get_expedited_writes(device_id)


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

    # pylint: disable=too-many-instance-attributes, too-many-arguments
    # pylint: disable=too-many-positional-arguments
    def __init__(
        self,
        min_ticks: int,
        logger: logging.Logger,
        attribute_read_delay: float,
        port_status_read_delay: float,
        port_power_delay: float,
        available_smartboxes: list[int],
        smartbox_ids: Optional[list[int]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param min_ticks: minimum number of ticks between communications
            with any given device
        :param logger: a logger.
        :param attribute_read_delay: time in seconds to wait after writing an
            attribute before reading it again
        :param port_status_read_delay: time in seconds to wait after setting
            port status before reading it again
        :param port_power_delay: 5ime in seconds to wait between setting
            each FNDH port power.
        :param available_smartboxes: list of available smartbox ids to poll
        :param smartbox_ids: optional list of smartbox IDs associated with
            each FNDH port
        """
        if port_status_read_delay >= port_power_delay:
            logger.warning(
                f"Port status read delay ({port_status_read_delay}) >= Port Power Delay"
                f" ({port_power_delay}), setting port status read delay to "
                f"{port_power_delay - 1}"
            )
            port_status_read_delay = port_power_delay - 1
        self._min_ticks = min_ticks
        self._logger = logger
        self._attribute_read_delay = attribute_read_delay
        self._port_status_read_delay = port_status_read_delay
        self._port_power_delay = port_power_delay

        # Create a dict mapping FNDH ports to smartbox Modbus IDs
        # if smartboxIDs is provided, otherwise just use available_smartboxes
        self._smartboxIDs = {}
        if smartbox_ids:
            for fndh_port, smartbox_id in enumerate(smartbox_ids, start=1):
                if smartbox_id != 0:
                    self._smartboxIDs[fndh_port] = smartbox_id
            self._available_smartboxes = list(self._smartboxIDs.values())
        else:
            self._available_smartboxes = available_smartboxes

        self._expedited_reads: list[ExpeditedReadRequest] = []
        self.initialise()

    def initialise(self) -> None:
        """Initialise the PasdBusRequestProvider.

        This may be called when the device is taken offline to reset
        all the request providers.
        """
        # Instantiate ticks dict in the order the devices will be polled:
        # First FNDH, then FNCC, then all available Smartboxes
        # (Smartboxes are added manually once they are powered on)
        self._ticks = {
            PasdData.FNDH_DEVICE_ID: self._min_ticks,
            PasdData.FNCC_DEVICE_ID: self._min_ticks,
        }

        if not self._smartboxIDs:
            # We don't know the port mapping so we poll all available
            # smartboxes immediately
            self._ticks.update(
                {
                    device_number: self._min_ticks
                    for device_number in self._available_smartboxes
                }
            )

        fndh_request_provider = FndhRequestProvider(
            PasdData.NUMBER_OF_FNDH_PORTS,
            fndh_read_request_iterator,
            self._attribute_read_delay,
            self._port_status_read_delay,
            self._port_power_delay,
            logger=self._logger,
        )
        fncc_request_provider = DeviceRequestProvider(
            0,
            fncc_read_request_iterator,
            attribute_read_delay=self._attribute_read_delay,
            port_status_read_delay=self._port_status_read_delay,
            logger=self._logger,
        )
        self._device_request_providers: dict[int, DeviceRequestProvider] = {
            smartbox_id: DeviceRequestProvider(
                PasdData.NUMBER_OF_SMARTBOX_PORTS,
                smartbox_read_request_iterator,
                self._attribute_read_delay,
                self._port_status_read_delay,
                self._logger,
            )
            for smartbox_id in self._available_smartboxes
        }
        self._device_request_providers[PasdData.FNDH_DEVICE_ID] = fndh_request_provider
        self._device_request_providers[PasdData.FNCC_DEVICE_ID] = fncc_request_provider

    def update_port_power_states(self, port_power_states: list[bool]) -> None:
        """
        Use the new power states to update the smartbox polling list.

        :param port_power_states: list of FNDH port power states.
        """
        if not self._smartboxIDs:
            # We don't have the port mapping so we cannot update the polling list
            return

        for fndh_port, power_state in enumerate(port_power_states, start=1):
            smartbox_id = self._smartboxIDs.get(fndh_port)
            if smartbox_id is None:
                # No associated smartbox on this port
                continue
            if power_state and smartbox_id not in self._ticks:
                self._logger.info(f"Starting to poll smartbox {smartbox_id}")
                self._ticks.update({smartbox_id: self._min_ticks})
            elif not power_state and smartbox_id in self._ticks:
                self._logger.info(f"Stopping polling smartbox {smartbox_id}")
                self._ticks.pop(smartbox_id, None)

    def desire_read_startup_info(self, device_id: int) -> None:
        """
        Register a request to read the information usually just read at startup.

        :param device_id: the device number.
        """
        self._device_request_providers[device_id].desire_read_startup_info()

    def desire_initialize(self, device_id: int) -> None:
        """
        Register a request to initialize a device.

        :param device_id: the device number.
        """
        self._device_request_providers[device_id].desire_initialize()

    def desire_attribute_write(
        self, device_id: int, name: str, values: list[Any]
    ) -> None:
        """
        Register a request to write an attribute.

        :param device_id: the device number.
        :param name: the name of the attribute to write.
        :param values: the new value(s) to write.
        """
        self._device_request_providers[device_id].desire_attribute_write(name, values)

    def desire_alarm_reset(self, device_id: int) -> None:
        """
        Register a request to reset an alarm.

        :param device_id: the device number.
        """
        self._device_request_providers[device_id].desire_alarm_reset()

    def desire_warning_reset(self, device_id: int) -> None:
        """
        Register a request to reset a warning.

        :param device_id: the device number.
        """
        self._device_request_providers[device_id].desire_warning_reset()

    def desire_status_reset(self, device_id: int) -> None:
        """
        Register a request to reset the status register.

        :param device_id: the device number.
        """
        self._device_request_providers[device_id].desire_status_reset()

    def desire_status_read(self, device_id: int) -> None:
        """
        Register a request to read the status register.

        :param device_id: the device number.
        """
        self._device_request_providers[device_id].desire_status_read()

    def desire_port_powers(
        self,
        device_id: int,
        port_powers: Sequence[bool | None],
        stay_on_when_offline: bool,
    ) -> None:
        """
        Register a request to turn some of device's ports on.

        :param device_id: the device number.
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
        :param port_number: the number of the port whose breaker is to
            be reset.
        """
        self._device_request_providers[device_id].desire_port_breaker_reset(port_number)

    def desire_led_pattern(self, device_id: int, pattern: str) -> None:
        """
        Register a request to set a device's LED pattern.

        :param device_id: the device number.
        :param pattern: name of the service LED pattern.
        """
        self._device_request_providers[device_id].desire_led_pattern(pattern)

    def desire_set_low_pass_filter(
        self, device_id: int, cutoff: float, extra_sensors: bool
    ) -> None:
        """
        Register a request to set a device's low pass filter constants.

        :param device_id: the device number.
        :param cutoff: frequency of LPF to set.
        :param extra_sensors: write the constant to the extra sensors' registers after
            the LED status register.
        """
        self._device_request_providers[device_id].desire_set_low_pass_filter(
            cutoff, extra_sensors
        )

    # pylint: disable=too-many-branches
    def get_request(  # noqa: C901
        self, tick_increment: int
    ) -> tuple[int, str, Any] | None:
        """
        Get a description of the next communication with the PaSD bus.

        :param tick_increment: the number of ticks to increment by.
            This is usually 1, but can be higher if more than the usual
            polling period has elapsed since the last request.
        :return: a tuple consisting of the name of the communication
            and any arguments or extra information.
        """
        for device_id, tick in self._ticks.items():
            self._ticks[device_id] = tick + tick_increment

        # Check if there is an FNDH SYS_STATUS request to re-establish comms.
        # This should always take priority over everything else.
        if self._device_request_providers[
            PasdData.FNDH_DEVICE_ID
        ]._status_read_requested:
            if self._ticks[PasdData.FNDH_DEVICE_ID] < self._min_ticks:
                # This shouldn't ever happen as we delay the poll in
                # this scenario. Keep returning until enough time has
                # passed.
                return None
            self._device_request_providers[
                PasdData.FNDH_DEVICE_ID
            ]._status_read_requested = False
            # By deleting this before zeroing it,
            # we ensure the new zeroed value is added to the end of the dict,
            # and hence the dict is maintained in descending order of ticks,
            # which is what lets us break out of the following loops
            # as soon as we encounter a tick less than the minimum.
            del self._ticks[PasdData.FNDH_DEVICE_ID]
            self._ticks[PasdData.FNDH_DEVICE_ID] = 0
            return PasdData.FNDH_DEVICE_ID, *("READ", "status")

        # Check if any expedited attribute reads need to be added to the list
        # for future polls. These are actioned after a delay, so we maintain
        # a list rather than executing them immediately, so as not to hold
        # up other requests.
        for device_id, _ in self._ticks.items():
            expedited_read_request = self._device_request_providers[
                device_id
            ].get_expedited_read(device_id)
            if expedited_read_request is not None:
                self._expedited_reads.append(expedited_read_request)
            expedited_write_requests = self._device_request_providers[
                device_id
            ].get_expedited_writes(device_id)
            if expedited_write_requests is not None:
                self._expedited_reads.extend(expedited_write_requests)

        # Now see if any expedited reads are ready to be executed.
        # This takes priority over writes so that we can update the polling
        # list if the port power states have changed.
        for expedited_read in self._expedited_reads:
            if expedited_read.not_before < time.time():
                self._expedited_reads.remove(expedited_read)
                return expedited_read.device_id, *expedited_read.request_description

        # Next we check for any write requests.
        for device_id, tick in self._ticks.items():
            if tick < self._min_ticks:
                break
            write_request = self._device_request_providers[device_id].get_write()
            if write_request != ("NONE", None):
                del self._ticks[device_id]
                self._ticks[device_id] = 0
                return device_id, *write_request

        # No outstanding reads/writes remaining, so cycle through the polling list.
        fncc_skip = False
        for device_id, tick in self._ticks.items():
            if tick < self._min_ticks:
                break
            read_request = self._device_request_providers[device_id].get_read()
            if read_request == "":
                fncc_skip = True
                continue
            del self._ticks[device_id]  # see comment above
            self._ticks[device_id] = 0
            if fncc_skip:
                del self._ticks[PasdData.FNCC_DEVICE_ID]
                self._ticks[PasdData.FNCC_DEVICE_ID] = 0
            return device_id, read_request, None

        return None
