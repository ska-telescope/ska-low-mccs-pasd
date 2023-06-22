# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements a component manager for a PaSD bus."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Final, Iterator, Literal, Optional

from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_ser_devices.client_server import (
    ApplicationClient,
    SentinelBytesMarshaller,
    TcpClient,
)
from ska_tango_base.base import check_communicating
from ska_tango_base.poller import PollingComponentManager

from .pasd_bus_json_api import PasdBusJsonApiClient


@dataclass
class PasdBusRequest:
    """
    Class representing an action to be performed by a poll.

    it comprises a device ID number, a command name, and a list of
    arguments to the command.

    If the command name is None, then the arguments are interpreted as
    a list of attribute values to read.
    """

    device_id: int
    command: str | None
    arguments: list[Any]


@dataclass
class PasdBusResponse:
    """
    Class representing the result of a a poll.

    It comprises the device ID number, a command name, and a dictionary
    of returned data.

    If the command name is None, then the request was an attribute read
    request, and the data are the attribute values. Otherwise, the data
    is the result of executing the command
    """

    device_id: int
    command: str | None
    data: dict[str, Any]


def read_request_iterator() -> Iterator[tuple[int, str]]:
    """
    Return an iterator that specifies what attributes should be read on the next poll.

    It reads static info once for each device,
    and then never reads it again.
    (In order to re-read static info, a new iterator must be created.)
    It then loops forever over each device,
    reading status attributes and then port status attributes.

    :yields: a tuple specifying a device number, and a group of
        attributes to be read from that device.
    """
    for device_id in range(25):
        yield (device_id, "INFO")
    while True:
        for device_id in range(25):
            yield (device_id, "STATUS")
            yield (device_id, "PORTS")


class PasdBusRequestProvider:
    """
    A class that determines what should be done in the next poll.

    It keeps track of the current intent of PaSD monitoring and control,
    for example, whether a command has been requested to be executed;
    and it decides what should be done in the next poll.
    """

    STATIC_INFO_ATTRIBUTES: Final = (
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
    )

    FNDH_STATUS_ATTRIBUTES: Final = (
        "uptime",
        "status",
        "led_pattern",
        "psu48v_voltages",
        "psu5v_voltage",
        "psu48v_current",
        "psu48v_temperature",
        "psu5v_temperature",
        "pcb_temperature",
        "outside_temperature",
    )

    FNDH_PORTS_STATUS_ATTRIBUTES: Final = (
        "ports_connected",
        "port_forcings",
        "port_breakers_tripped",
        "ports_desired_power_when_online",
        "ports_desired_power_when_offline",
        "ports_power_sensed",
    )

    SMARTBOX_STATUS_ATTRIBUTES: Final = (
        "uptime",
        "status",
        "led_pattern",
        "input_voltage",
        "power_supply_output_voltage",
        "power_supply_temperature",
        "outside_temperature",
        "pcb_temperature",
    )

    SMARTBOX_PORTS_STATUS_ATTRIBUTES: Final = (
        "ports_connected",
        "port_forcings",
        "port_breakers_tripped",
        "ports_desired_power_when_online",
        "ports_desired_power_when_offline",
        "ports_power_sensed",
        "ports_current_draw",
    )

    def __init__(self, logger: logging.Logger) -> None:
        """
        Initialise a new instance.

        :param logger: a logger.
        """
        self._logger = logger

        self._led_pattern_writes: dict[int, str] = {}
        self._port_power_changes: dict[
            tuple[int, int], tuple[Literal[True], bool] | Literal[False]
        ] = {}
        self._port_breaker_resets: dict[tuple[int, int], bool] = {}
        self._read_request_iterator = read_request_iterator()

    def desire_info(self) -> None:
        """Register a desire to obtain static info about the PaSD devices."""
        self._read_request_iterator = read_request_iterator()

    def desire_port_on(
        self, device_id: int, port_number: int, stay_on_when_offline: bool
    ) -> None:
        """
        Register a request to turn a port on.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param port_number: the number of the port to be turned on.
        :param stay_on_when_offline: whether the port should remain on
            if MCCS loses its connection with the PaSD.
        """
        self._port_power_changes[(device_id, port_number)] = (
            True,
            stay_on_when_offline,
        )

    def desire_port_off(self, device_id: int, port_number: int) -> None:
        """
        Register a request to turn a port off.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param port_number: the number of the port to be turned off.
        """
        self._port_power_changes[(device_id, port_number)] = False

    def desire_port_breaker_reset(self, device_id: int, port_number: int) -> None:
        """
        Register a request to reset a port breaker.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param port_number: the number of the port whose breaker is to
            be reset.
        """
        self._port_breaker_resets[(device_id, port_number)] = True

    def set_led_pattern(self, device_id: int, pattern: str) -> None:
        """
        Register a request to set a device's LED pattern.

        :param device_id: the device number.
            This is 0 for the FNDH, otherwise a smartbox number.
        :param pattern: the name of the LED pattern.
        """
        self._led_pattern_writes[device_id] = pattern

    def _get_led_pattern_request(self) -> PasdBusRequest | None:
        if not self._led_pattern_writes:
            return None

        device_id, pattern = self._led_pattern_writes.popitem()
        return PasdBusRequest(device_id, "set_led_pattern", [pattern])

    def _get_port_breaker_reset_request(
        self,
    ) -> PasdBusRequest | None:
        if not self._port_breaker_resets:
            return None

        (device_id, port_number), _ = self._port_breaker_resets.popitem()
        return PasdBusRequest(device_id, "reset_port_breaker", [port_number])

    def _get_port_power_request(self) -> PasdBusRequest | None:
        if not self._port_power_changes:
            return None

        (device_id, port_number), change = self._port_power_changes.popitem()
        match change:
            case (True, stay_on_when_offline):
                return PasdBusRequest(
                    device_id,
                    "turn_port_on",
                    [port_number, stay_on_when_offline],
                )
            case False:
                return PasdBusRequest(device_id, "turn_port_off", [port_number])
            case _:
                raise AssertionError("This should be unreachable.")

    def _get_read_request(self) -> PasdBusRequest:
        read_request = next(self._read_request_iterator)

        match read_request:
            case (device_id, "INFO"):
                request = PasdBusRequest(
                    device_id, None, list(self.STATIC_INFO_ATTRIBUTES)
                )
            case (0, "STATUS"):
                request = PasdBusRequest(0, None, list(self.FNDH_STATUS_ATTRIBUTES))
            case (0, "PORTS"):
                request = PasdBusRequest(
                    0, None, list(self.FNDH_PORTS_STATUS_ATTRIBUTES)
                )
            case (smartbox_id, "STATUS"):
                request = PasdBusRequest(
                    smartbox_id, None, list(self.SMARTBOX_STATUS_ATTRIBUTES)
                )
            case (smartbox_id, "PORTS"):
                request = PasdBusRequest(
                    smartbox_id,
                    None,
                    list(self.SMARTBOX_PORTS_STATUS_ATTRIBUTES),
                )
            case _:
                message = f"Unrecognised poll request {repr(read_request)}"
                self._logger.error(message)
                raise AssertionError(message)

        return request

    def get_request(self) -> PasdBusRequest:
        """
        Return a description of what should be done on the next poll.

        :return: a description of what should be done on the next poll.
        """
        request = self._get_led_pattern_request()
        if request is not None:
            return request

        request = self._get_port_breaker_reset_request()
        if request is not None:
            return request

        request = self._get_port_power_request()
        if request is not None:
            return request

        return self._get_read_request()


class PasdBusComponentManager(PollingComponentManager[PasdBusRequest, PasdBusResponse]):
    """A component manager for a PaSD bus."""

    def __init__(  # pylint: disable=too-many-arguments
        self: PasdBusComponentManager,
        host: str,
        port: int,
        timeout: float,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        pasd_device_state_callback: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param host: IP address of PaSD bus
        :param port: port of the PaSD bus
        :param timeout: maximum time to wait for a response to a server
            request (in seconds).
        :param logger: a logger for this object to use
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_callback: callback to be called
            when the component state changes. Note this in this case the
            "component" is the PaSD bus itself. The PaSD bus has no
            no monitoring points. All we can do is infer that it is
            powered on and not in fault, from the fact that we receive
            responses to our requests.
        :param pasd_device_state_callback: callback to be called
            when one of the PaSD devices (i.e. the FNDH or one of the
            smartboxes) provides updated information about its state.
            This callable takes a single positional argument, which is
            the device number (0 for FNDH, otherwise the smartbox
            number), and keyword arguments representing the state
            changes.
        """
        tcp_client = TcpClient(host, port, timeout)
        marshaller = SentinelBytesMarshaller(b"\n")
        application_client = ApplicationClient(
            tcp_client, marshaller.marshall, marshaller.unmarshall
        )
        self._pasd_bus_api_client = PasdBusJsonApiClient(application_client)
        self._pasd_bus_device_state_callback = pasd_device_state_callback

        self._poll_request_provider = PasdBusRequestProvider(logger)

        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
            fndh_status=None,
        )

    def off(
        self: PasdBusComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn off the PaSD bus simulator.

        :param task_callback: callback to be called when the status of
            the command changes

        :raises NotImplementedError: because this is not yet implemented.
        """
        raise NotImplementedError("The PaSD cannot yet be turned off.")

    def standby(
        self: PasdBusComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Put the PaSD bus simulator into low-power standby mode.

        :param task_callback: callback to be called when the status of
            the command changes

        :raises NotImplementedError: because this is not yet implemented.
        """
        raise NotImplementedError("The PaSD cannot yet be put into standby.")

    def on(
        self: PasdBusComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn on the PaSD bus simulator.

        :param task_callback: callback to be called when the status of
            the command changes

        :raises NotImplementedError: because this is not yet implemented.
        """
        raise NotImplementedError("The PaSD cannot yet be turned on.")

    def reset(
        self: PasdBusComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Reset the PaSD bus simulator.

        :param task_callback: callback to be called when the status of
            the command changes

        :raises NotImplementedError: because this is not yet implemented.
        """
        raise NotImplementedError("The PaSD cannot yet be reset")

    def polling_started(self: PasdBusComponentManager) -> None:
        """Define actions to be taken when polling starts."""
        self._poll_request_provider.desire_info()

    def get_request(
        self: PasdBusComponentManager,
    ) -> PasdBusRequest:
        """
        Return the action/s to be taken in the next poll.

        :return: attributes to be read and commands to be executed in
            the next poll.
        """
        return self._poll_request_provider.get_request()

    def poll(
        self: PasdBusComponentManager, poll_request: PasdBusRequest
    ) -> PasdBusResponse:
        """
        Poll the PaSD hardware.

        Connect to the hardware, execute a command or read some values.

        :param poll_request: specification of the actions to be taken in
            this poll.

        :return: responses to queries in this poll
        """
        if poll_request.command is None:
            response_data = self._pasd_bus_api_client.read_attributes(
                poll_request.device_id, *poll_request.arguments
            )
        else:
            response_data = self._pasd_bus_api_client.execute_command(
                poll_request.device_id,
                poll_request.command,
                *poll_request.arguments,
            )
        return PasdBusResponse(
            poll_request.device_id, poll_request.command, response_data
        )

    def poll_succeeded(
        self: PasdBusComponentManager, poll_response: PasdBusResponse
    ) -> None:
        """
        Handle the receipt of new polling values.

        This is a hook called by the poller when values have been read
        during a poll.

        :param poll_response: response to the pool, including any values
            read.
        """
        self.logger.info("Handing results of successful poll.")
        super().poll_succeeded(poll_response)

        self._update_component_state(power=PowerState.ON, fault=False)

        if poll_response.command is None:
            self._pasd_bus_device_state_callback(
                poll_response.device_id,
                **(poll_response.data),
            )

    @check_communicating
    def reset_fndh_port_breaker(
        self: PasdBusComponentManager,
        port_number: int,
    ) -> None:
        """
        Reset an FNDH port breaker.

        :param port_number: the number of the port to reset.
        """
        self._poll_request_provider.desire_port_breaker_reset(0, port_number)

    @check_communicating
    def turn_fndh_port_on(
        self: PasdBusComponentManager,
        port_number: int,
        stay_on_when_offline: bool,
    ) -> None:
        """
        Turn on a specified FNDH port.

        :param port_number: the number of the port.
        :param stay_on_when_offline: whether the port should remain on
            if monitoring and control goes offline.
        """
        self._poll_request_provider.desire_port_on(0, port_number, stay_on_when_offline)

    @check_communicating
    def turn_fndh_port_off(
        self: PasdBusComponentManager,
        port_number: int,
    ) -> None:
        """
        Turn off a specified FNDH port.

        :param port_number: the number of the port.
        """
        self._poll_request_provider.desire_port_off(0, port_number)

    @check_communicating
    def set_fndh_led_pattern(
        self: PasdBusComponentManager,
        led_pattern: str,
    ) -> None:
        """
        Set the FNDH's LED pattern.

        :param led_pattern: name of the LED pattern.
            Options are "OFF" and "SERVICE".
        """
        self._poll_request_provider.set_led_pattern(0, led_pattern)

    @check_communicating
    def reset_smartbox_port_breaker(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_number: int,
    ) -> None:
        """
        Reset a smartbox port's breaker.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_number: the number of the port to reset.
        """
        self._poll_request_provider.desire_port_breaker_reset(smartbox_id, port_number)

    @check_communicating
    def turn_smartbox_port_on(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_number: int,
        stay_on_when_offline: bool,
    ) -> None:
        """
        Turn on a specified smartbox port.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_number: the number of the port.
        :param stay_on_when_offline: whether the port should remain on
            if monitoring and control goes offline.
        """
        self._poll_request_provider.desire_port_on(
            smartbox_id, port_number, stay_on_when_offline
        )

    @check_communicating
    def turn_smartbox_port_off(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_number: int,
    ) -> None:
        """
        Turn off a specified smartbox port.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_number: the number of the port.
        """
        self._poll_request_provider.desire_port_off(smartbox_id, port_number)

    @check_communicating
    def set_smartbox_led_pattern(
        self: PasdBusComponentManager,
        smartbox_id: int,
        led_pattern: str,
    ) -> None:
        """
        Set a smartbox's LED pattern.

        :param smartbox_id: the smartbox to have its LED pattern set
        :param led_pattern: name of the LED pattern.
            Options are "OFF" and "SERVICE".
        """
        self._poll_request_provider.set_led_pattern(smartbox_id, led_pattern)
