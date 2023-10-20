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
from typing import Any, Callable, Final, Optional

from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_tango_base.base import check_communicating
from ska_tango_base.poller import PollingComponentManager

from .pasd_bus_modbus_api import PasdBusModbusApiClient

NUMBER_OF_FNDH_PORTS: Final = 28
NUMBER_OF_SMARTBOXES: Final = 24
NUMBER_OF_SMARTBOX_PORTS: Final = 12

from .pasd_bus_poll_management import PasdBusRequestProvider


@dataclass
class PasdBusRequest:
    """
    Class representing an action to be performed by a poll.

    it comprises a device ID number, a command name or attribute to write, and a list of
    command arguments or values

    If the command name and attribute_to_write are both None, then the arguments
    are interpreted as a list of attribute values to read.
    """

    device_id: int
    command: str | None
    attribute_to_write: str | None
    arguments: list[Any]


@dataclass
class PasdBusResponse:
    """
    Class representing the result of a poll.

    It comprises the device ID number, a command name, and a dictionary
    of returned data.

    If the command name is None, then the request was an attribute read
    request, and the data are the attribute values. Otherwise, the data
    is the result of executing the command
    """

    device_id: int
    command: str | None
    data: dict[str, Any]


# pylint: disable=too-many-public-methods
class PasdBusComponentManager(PollingComponentManager[PasdBusRequest, PasdBusResponse]):
    """A component manager for a PaSD bus."""

    STATIC_INFO_ATTRIBUTES: Final = (
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
    )

    FNDH_STATUS_ATTRIBUTES: Final = (
        "uptime",
        "sys_address",
        "psu48v_voltages",
        "psu48v_current",
        "psu48v_temperatures",
        "panel_temperature",
        "fncb_temperature",
        "fncb_humidity",
        "status",
        "led_pattern",
        "comms_gateway_temperature",
        "power_module_temperature",
        "outside_temperature",
        "internal_ambient_temperature",
    )

    FNDH_PORTS_STATUS_ATTRIBUTES: Final = (
        "port_forcings",  # Register STATE[9:8] - TO
        "ports_desired_power_when_online",  # Register STATE[13:12] - DSON
        "ports_desired_power_when_offline",  # Register STATE[11:10] - DSOFF
        "ports_power_sensed",  # Register STATE[7] - PWRSENSE
        # "ports_power_contol", # Register STATE[6] - POWER
    )

    FNDH_THRESHOLD_ATTRIBUTES: Final = (
        "psu48v_voltage_1_thresholds",
        "psu48v_voltage_2_thresholds",
        "psu48v_current_thresholds",
        "psu48v_temperature_1_thresholds",
        "psu48v_temperature_2_thresholds",
        "panel_temperature_thresholds",
        "fncb_temperature_thresholds",
        "fncb_humidity_thresholds",
        "comms_gateway_temperature_thresholds",
        "power_module_temperature_thresholds",
        "outside_temperature_thresholds",
        "internal_ambient_temperature_thresholds",
    )

    SMARTBOX_STATUS_ATTRIBUTES: Final = (
        "uptime",
        "sys_address",
        "input_voltage",
        "power_supply_output_voltage",
        "power_supply_temperature",
        "pcb_temperature",
        "fem_ambient_temperature",
        "status",
        "led_pattern",
        "fem_case_temperatures",
        "fem_heatsink_temperatures",
    )

    SMARTBOX_PORTS_STATUS_ATTRIBUTES: Final = (
        "port_forcings",  # Register STATE[9:8] - TO
        "port_breakers_tripped",  # Register STATE[7] - BREAKER
        "ports_desired_power_when_online",  # Register STATE[13:12] - DSON
        "ports_desired_power_when_offline",  # Register STATE[11:10] - DSOFF
        "ports_power_sensed",  # Register STATE[6] - POWER
        "ports_current_draw",  # Register CURRENT
    )

    SMARTBOX_THRESHOLD_ATTRIBUTES: Final = (
        "input_voltage_thresholds",
        "power_supply_output_voltage_thresholds",
        "power_supply_temperature_thresholds",
        "pcb_temperature_thresholds",
        "fem_ambient_temperature_thresholds",
        "fem_case_temperature_1_thresholds",
        "fem_case_temperature_2_thresholds",
        "fem_heatsink_temperature_1_thresholds",
        "fem_heatsink_temperature_2_thresholds",
    )

    SMARTBOX_CURRENT_TRIP_THRESHOLD_ATTRIBUTES: Final = (
        "fem1_current_trip_threshold",
        "fem2_current_trip_threshold",
        "fem3_current_trip_threshold",
        "fem4_current_trip_threshold",
        "fem5_current_trip_threshold",
        "fem6_current_trip_threshold",
        "fem7_current_trip_threshold",
        "fem8_current_trip_threshold",
        "fem9_current_trip_threshold",
        "fem10_current_trip_threshold",
        "fem11_current_trip_threshold",
        "fem12_current_trip_threshold",
    )

    # The warning and alarm flag attributes are the same for both FNDH and Smartboxes
    # but are non-contiguous
    WARNING_FLAGS_ATTRIBUTE: Final = "warning_flags"
    ALARM_FLAGS_ATTRIBUTE: Final = "alarm_flags"

    def __init__(  # pylint: disable=too-many-arguments
        self: PasdBusComponentManager,
        host: str,
        port: int,
        polling_rate: float,
        device_polling_rate: float,
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
        :param polling_rate: minimum amount of time between communications
            on the PaSD bus
        :param device_polling_rate: minimum amount of time between communications
            with the same device.
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
        self._logger = logger
        # self._logger.debug(
        #     f"Creating TCP client for ({host}, {port}) with timeout {timeout}..."
        # )
        # tcp_client = TcpClient((host, port), timeout, logger=logger)

        # self._logger.debug(r"Creating marshaller with sentinel '\n'...")
        # marshaller = SentinelBytesMarshaller(b"\n", logger=logger)
        # application_client = ApplicationClient[bytes, bytes](
        #     tcp_client, marshaller.marshall, marshaller.unmarshall
        # )
        # self._pasd_bus_api_client = PasdBusJsonApiClient(application_client)

        self._pasd_bus_api_client = PasdBusModbusApiClient(host, port, logger)
        self._pasd_bus_device_state_callback = pasd_device_state_callback

        self._min_ticks = int(device_polling_rate / polling_rate)
        self._request_provider: PasdBusRequestProvider | None = None

        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
            polling_rate,
            # fndh_status=None,
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
        self._logger.info("Connecting to server and commencing to poll...")

        self._request_provider = PasdBusRequestProvider(self._min_ticks, self._logger)
        self._pasd_bus_api_client.connect()

    def polling_stopped(self: PasdBusComponentManager) -> None:
        """Define actions to be taken when polling stops."""
        self._logger.info("Stopping polling and closing connection to the server...")
        self._pasd_bus_api_client.close()
        self._request_provider = None
        super().polling_stopped()

    # TODO: None return is reasonable and should be supported by ska-tango-base
    def get_request(  # type: ignore[override]
        self: PasdBusComponentManager,
    ) -> PasdBusRequest | None:
        """
        Return the action/s to be taken in the next poll.

        :raises AssertionError: if an unrecognosed poll option is
            returned by the provider

        :return: attributes to be read and commands to be executed in
            the next poll.
        """
        assert self._request_provider is not None

        port: int  # for the type checker
        stay_on_when_offline: bool  # for the type checker
        is_on: bool  # for the type checker

        request_spec = self._request_provider.get_request()
        if request_spec is None:
            return None
        match request_spec:
            case (device_id, "INITIALIZE", None):
                request = PasdBusRequest(device_id, "initialize", None, [])
            case (device_id, "WRITE", spec):
                request = PasdBusRequest(device_id, None, *spec)
            case (device_id, "LED_PATTERN", pattern):
                request = PasdBusRequest(device_id, "set_led_pattern", None, [pattern])
            case (device_id, "BREAKER_RESET", port):
                request = PasdBusRequest(device_id, "reset_port_breaker", None, [port])
            case (device_id, "PORT_POWER", (port, is_on, stay_on_when_offline)):
                if is_on:
                    request = PasdBusRequest(
                        device_id,
                        "turn_port_on",
                        None,
                        [port, stay_on_when_offline],
                    )
                else:
                    request = PasdBusRequest(device_id, "turn_port_off", None, [port])
            case (device_id, "INFO", None):
                request = PasdBusRequest(
                    device_id, None, None, list(self.STATIC_INFO_ATTRIBUTES)
                )
            case (0, "STATUS", None):
                request = PasdBusRequest(
                    0, None, None, list(self.FNDH_STATUS_ATTRIBUTES)
                )
            case (0, "PORTS", None):
                request = PasdBusRequest(
                    0, None, None, list(self.FNDH_PORTS_STATUS_ATTRIBUTES)
                )
            case (0, "THRESHOLDS", None):
                request = PasdBusRequest(
                    0, None, None, list(self.FNDH_THRESHOLD_ATTRIBUTES)
                )
            case (0, "ALARM_FLAGS", None):
                request = PasdBusRequest(0, None, None, [self.ALARM_FLAGS_ATTRIBUTE])
            case (0, "WARNING_FLAGS", None):
                request = PasdBusRequest(0, None, None, [self.WARNING_FLAGS_ATTRIBUTE])

            case (smartbox_id, "STATUS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, list(self.SMARTBOX_STATUS_ATTRIBUTES)
                )
            case (smartbox_id, "PORTS", None):
                request = PasdBusRequest(
                    smartbox_id,
                    None,
                    None,
                    list(self.SMARTBOX_PORTS_STATUS_ATTRIBUTES),
                )
            case (smartbox_id, "THRESHOLDS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, list(self.SMARTBOX_THRESHOLD_ATTRIBUTES)
                )
            case (smartbox_id, "CURRENT_TRIP_THRESHOLDS", None):
                request = PasdBusRequest(
                    smartbox_id,
                    None,
                    None,
                    list(self.SMARTBOX_CURRENT_TRIP_THRESHOLD_ATTRIBUTES),
                )
            case (smartbox_id, "ALARM_FLAGS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, [self.ALARM_FLAGS_ATTRIBUTE]
                )
            case (smartbox_id, "WARNING_FLAGS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, [self.WARNING_FLAGS_ATTRIBUTE]
                )
            case _:
                message = f"Unrecognised poll request {repr(request_spec)}"
                self._logger.error(message)
                raise AssertionError(message)

        return request

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
        if poll_request.command is not None:
            response_data = self._pasd_bus_api_client.execute_command(
                poll_request.device_id,
                poll_request.command,
                *poll_request.arguments,
            )
        elif poll_request.attribute_to_write is not None:
            if isinstance(poll_request.arguments, int):
                response_data = self._pasd_bus_api_client.write_attribute(
                    poll_request.device_id,
                    poll_request.attribute_to_write,
                    poll_request.arguments,
                )
            else:
                response_data = self._pasd_bus_api_client.write_attribute(
                    poll_request.device_id,
                    poll_request.attribute_to_write,
                    *poll_request.arguments,
                )
        else:
            response_data = self._pasd_bus_api_client.read_attributes(
                poll_request.device_id, *poll_request.arguments
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
        self.logger.info("Handling results of successful poll.")
        super().poll_succeeded(poll_response)

        self._update_component_state(power=PowerState.ON, fault=False)
        if poll_response.command is None:
            self._pasd_bus_device_state_callback(
                poll_response.device_id,
                **(poll_response.data),
            )

    @check_communicating
    def initialize_fndh(self: PasdBusComponentManager) -> None:
        """Initialize the FNDH by writing to its status register."""
        assert self._request_provider is not None
        self._request_provider.desire_initialize(0)

    @check_communicating
    def initialize_smartbox(self: PasdBusComponentManager, smartbox_id: int) -> None:
        """
        Initialize a smartbox by writing to its status register.

        :param: smartbox_id: id of the smartbox being addressed
        """
        assert self._request_provider is not None
        self._request_provider.desire_initialize(smartbox_id)

    @check_communicating
    def reset_fndh_port_breaker(
        self: PasdBusComponentManager,
        port_number: int,
    ) -> None:
        """
        Reset an FNDH port breaker.

        :param port_number: the number of the port to reset.
        """
        assert self._request_provider is not None
        self._request_provider.desire_port_breaker_reset(0, port_number)

    @check_communicating
    def set_fndh_port_powers(
        self: PasdBusComponentManager,
        port_powers: list[bool | None],
        stay_on_when_offline: bool,
    ) -> None:
        """
        Set the FNDH port powers.

        :param port_powers: specification of the desired power of each port.
            True means on, False means off, None means no change desired.
        :param stay_on_when_offline: whether any ports being turned on
            should remain on if MCCS loses its connection with the PaSD.
        """
        assert self._request_provider is not None
        self._request_provider.desire_port_powers(0, port_powers, stay_on_when_offline)

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
        assert self._request_provider is not None
        self._request_provider.desire_led_pattern(0, led_pattern)

    @check_communicating
    def reset_fndh_alarms(self: PasdBusComponentManager) -> None:
        """Reset the FNDH alarms register."""
        assert self._request_provider is not None
        self._request_provider.desire_alarm_reset(0)

    @check_communicating
    def reset_fndh_warnings(self: PasdBusComponentManager) -> None:
        """Reset the FNDH warnings register."""
        assert self._request_provider is not None
        self._request_provider.desire_warning_reset(0)

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
        assert self._request_provider is not None
        self._request_provider.desire_port_breaker_reset(smartbox_id, port_number)

    @check_communicating
    def set_smartbox_port_powers(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_powers: list[bool | None],
        stay_on_when_offline: bool,
    ) -> None:
        """
        Set the FNDH port powers.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_powers: specification of the desired power of each port.
            True means on, False means off, None means no change desired.
        :param stay_on_when_offline: whether any ports being turned on
            should remain on if MCCS loses its connection with the PaSD.
        """
        assert self._request_provider is not None
        self._request_provider.desire_port_powers(
            smartbox_id, port_powers, stay_on_when_offline
        )

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
        assert self._request_provider is not None
        self._request_provider.desire_led_pattern(smartbox_id, led_pattern)

    @check_communicating
    def reset_smartbox_alarms(self: PasdBusComponentManager, smartbox_id: int) -> None:
        """Reset a smartbox alarms register.

        :param smartbox_id: the smartbox to have its alarms reset
        """
        assert self._request_provider is not None
        self._request_provider.desire_alarm_reset(smartbox_id)

    @check_communicating
    def reset_smartbox_warnings(
        self: PasdBusComponentManager, smartbox_id: int
    ) -> None:
        """Reset a smartbox warnings register.

        :param smartbox_id: the smartbox to have its warnings reset
        """
        assert self._request_provider is not None
        self._request_provider.desire_warning_reset(smartbox_id)

    @check_communicating
    def write_attribute(
        self: PasdBusComponentManager,
        device_id: int,
        attribute_name: str,
        value: Any,
    ) -> None:
        """
        Write a new value to an attribute.

        :param device_id: the smartbox or FNDH id
        :param attribute_name: the name of the attribute to write
        :param value: the new value to write
        """
        assert self._request_provider is not None
        self._request_provider.desire_attribute_write(device_id, attribute_name, value)
