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
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional

from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_pasd_driver.pasd_bus_modbus_api import PasdBusModbusApiClient
from ska_tango_base.base import check_communicating
from ska_tango_base.poller import PollingComponentManager

from ska_low_mccs_pasd.pasd_data import PasdData

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


# pylint: disable=too-many-public-methods, too-many-instance-attributes
class PasdBusComponentManager(PollingComponentManager[PasdBusRequest, PasdBusResponse]):
    """A component manager for a PaSD bus."""

    # The warning and alarm flag attributes are the same for both FNDH and Smartboxes
    # but are non-contiguous
    WARNING_FLAGS_ATTRIBUTE: Final = "warning_flags"
    ALARM_FLAGS_ATTRIBUTE: Final = "alarm_flags"

    FEM_CURRENT_TRIP_THRESHOLDS_ATTRIBUTE: Final = "fem_current_trip_thresholds"
    INPUT_VOLTAGE_THRESHOLDS_ATTRIBUTE: Final = "input_voltage_thresholds"

    STATIC_INFO_ATTRIBUTES: Final[list[str]] = []
    FNCC_STATUS_ATTRIBUTES: Final[list[str]] = []
    for key, register in PasdData.CONTROLLERS_CONFIG["FNCC"]["registers"].items():
        if register.get("static", False):
            STATIC_INFO_ATTRIBUTES.append(key)
        else:
            FNCC_STATUS_ATTRIBUTES.append(key)

    FNDH_STATUS_ATTRIBUTES: Final[list[str]] = []
    FNDH_PORTS_STATUS_ATTRIBUTES: Final[list[str]] = []
    FNDH_THRESHOLD_ATTRIBUTES: Final[list[str]] = []
    for key, register in PasdData.CONTROLLERS_CONFIG["FNPC"]["registers"].items():
        if register["modbus_class"] == "PasdBusPortAttribute":
            FNDH_PORTS_STATUS_ATTRIBUTES.append(key)
        elif "default_thresholds" in register:
            FNDH_THRESHOLD_ATTRIBUTES.append(key)
        elif not register.get("static", False) and key not in [
            WARNING_FLAGS_ATTRIBUTE,
            ALARM_FLAGS_ATTRIBUTE,
        ]:
            FNDH_STATUS_ATTRIBUTES.append(key)

    SMARTBOX_STATUS_ATTRIBUTES: Final[list[str]] = []
    SMARTBOX_PORTS_STATUS_ATTRIBUTES: Final[list[str]] = []
    SMARTBOX_THRESHOLD_ATTRIBUTES: Final[list[str]] = []
    SMARTBOX_CURRENT_TRIP_THRESHOLD_ATTRIBUTES: Final = []
    for key, register in PasdData.CONTROLLERS_CONFIG["FNSC"]["registers"].items():
        if (
            key == "ports_current_draw"
            or register["modbus_class"] == "PasdBusPortAttribute"
        ):
            SMARTBOX_PORTS_STATUS_ATTRIBUTES.append(key)
        elif "default_thresholds" in register:
            SMARTBOX_THRESHOLD_ATTRIBUTES.append(key)
        elif "threshold" in key:
            SMARTBOX_CURRENT_TRIP_THRESHOLD_ATTRIBUTES.append(key)
        elif not register.get("static", False) and key not in [
            WARNING_FLAGS_ATTRIBUTE,
            ALARM_FLAGS_ATTRIBUTE,
        ]:
            SMARTBOX_STATUS_ATTRIBUTES.append(key)

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self: PasdBusComponentManager,
        host: str,
        port: int,
        polling_rate: float,
        device_polling_rate: float,
        poll_delay_after_failure: float,
        timeout: float,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        pasd_device_state_callback: Callable[..., None],
        available_smartboxes: list[int],
        smartbox_ids: list[int] | None,
    ) -> None:
        """
        Initialise a new instance.

        :param host: IP address of PaSD bus
        :param port: port of the PaSD bus
        :param polling_rate: minimum amount of time between communications
            on the PaSD bus
        :param device_polling_rate: minimum amount of time between communications
            with the same device.
        :param poll_delay_after_failure: time in seconds to wait before next poll
            after a comms failure
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
        :param available_smartboxes: a list of available smartbox ids to poll.
        :param smartbox_ids: optional list of smartbox IDs associated with
            each FNDH port.
        """
        self._logger = logger
        self._pasd_bus_api_client = PasdBusModbusApiClient(
            host, port, logger, timeout=timeout
        )
        self._pasd_bus_device_state_callback = pasd_device_state_callback
        self._polling_rate = polling_rate
        self._poll_delay_after_failure = poll_delay_after_failure
        self._request_provider = PasdBusRequestProvider(
            int(device_polling_rate / polling_rate),
            self._logger,
            available_smartboxes,
            smartbox_ids,
        )
        self._last_request_timestamp: float = 0
        self._connection_reset_count = 0
        self._poll_delay_event = threading.Event()

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
        self._request_provider.initialise()
        self._pasd_bus_api_client.connect()

    def polling_stopped(self: PasdBusComponentManager) -> None:
        """Define actions to be taken when polling stops."""
        self._logger.info("Stopping polling and closing connection to the server...")
        self._pasd_bus_api_client.close()
        super().polling_stopped()

    def reset_connection(self: PasdBusComponentManager) -> None:
        """Reset the connection to the device."""
        self._connection_reset_count += 1
        self._logger.info(f"Connection reset count: {self._connection_reset_count}")
        self._pasd_bus_api_client.reset_connection()

    # TODO: None return is reasonable and should be supported by ska-tango-base
    def get_request(  # type: ignore[override]
        self: PasdBusComponentManager,
    ) -> PasdBusRequest | None:
        """
        Return the action/s to be taken in the next poll.

        :raises AssertionError: if an unrecognised poll option is
            returned by the provider

        :return: attributes to be read and commands to be executed in
            the next poll.
        """
        port: int  # for the type checker
        stay_on_when_offline: bool  # for the type checker
        is_on: bool  # for the type checker

        timestamp = time.time()
        elapsed_time = (
            timestamp - self._last_request_timestamp
            if self._last_request_timestamp != 0
            else 0
        )

        # If a comms error occurred, we need to delay the next poll
        if self._poll_delay_event.is_set():
            if elapsed_time < self._poll_delay_after_failure:
                # Still in delay period, return None to skip this poll
                return None
            # Delay period has elapsed, resume polling
            self._poll_delay_event.clear()

        # If the last request took a long time (e.g. due to a timeout),
        # we need to inform the request manager to increment the
        # ticks accordingly
        if (
            self._last_request_timestamp != 0
            and (elapsed_time - self._last_request_timestamp) > self._polling_rate
        ):
            request_spec = self._request_provider.get_request(
                math.floor(elapsed_time / self._polling_rate)
            )
        else:
            request_spec = self._request_provider.get_request(1)
        self._last_request_timestamp = timestamp

        if request_spec is None:
            return None
        match request_spec:
            case (device_id, "INITIALIZE", None):
                request = PasdBusRequest(device_id, "initialize", None, [])
            case (device_id, "READ", attribute):
                request = PasdBusRequest(device_id, None, None, [attribute])
            case (device_id, "WRITE", spec):
                request = PasdBusRequest(device_id, None, *spec)
            case (device_id, "LED_PATTERN", pattern):
                request = PasdBusRequest(device_id, "set_led_pattern", None, [pattern])
            case (device_id, "SET_LOW_PASS_FILTER", arguments):
                request = PasdBusRequest(
                    device_id, "set_low_pass_filter", None, arguments
                )
            case (device_id, "BREAKER_RESET", port):
                request = PasdBusRequest(device_id, "reset_port_breaker", None, [port])
            case (device_id, "SET_PORT_POWERS", arguments):
                request = PasdBusRequest(device_id, "set_port_powers", None, arguments)
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
                    device_id, None, None, self.STATIC_INFO_ATTRIBUTES
                )
            case (device_id, "RESET_ALARMS", None):
                request = PasdBusRequest(device_id, "reset_alarms", None, [])
            case (device_id, "RESET_WARNINGS", None):
                request = PasdBusRequest(device_id, "reset_warnings", None, [])
            case (PasdData.FNDH_DEVICE_ID, "STATUS", None):
                request = PasdBusRequest(
                    PasdData.FNDH_DEVICE_ID, None, None, self.FNDH_STATUS_ATTRIBUTES
                )
            case (PasdData.FNDH_DEVICE_ID, "PORTS", None):
                request = PasdBusRequest(
                    PasdData.FNDH_DEVICE_ID,
                    None,
                    None,
                    self.FNDH_PORTS_STATUS_ATTRIBUTES,
                )
            case (PasdData.FNDH_DEVICE_ID, "THRESHOLDS", None):
                request = PasdBusRequest(
                    PasdData.FNDH_DEVICE_ID, None, None, self.FNDH_THRESHOLD_ATTRIBUTES
                )
            case (PasdData.FNDH_DEVICE_ID, "ALARM_FLAGS", None):
                request = PasdBusRequest(
                    PasdData.FNDH_DEVICE_ID, None, None, [self.ALARM_FLAGS_ATTRIBUTE]
                )
            case (PasdData.FNDH_DEVICE_ID, "WARNING_FLAGS", None):
                request = PasdBusRequest(
                    PasdData.FNDH_DEVICE_ID, None, None, [self.WARNING_FLAGS_ATTRIBUTE]
                )

            case (PasdData.FNCC_DEVICE_ID, "STATUS", None):
                request = PasdBusRequest(
                    PasdData.FNCC_DEVICE_ID, None, None, self.FNCC_STATUS_ATTRIBUTES
                )

            case (PasdData.FNCC_DEVICE_ID, "RESET_STATUS", None):
                request = PasdBusRequest(
                    PasdData.FNCC_DEVICE_ID, "reset_status", None, []
                )

            case (smartbox_id, "STATUS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, self.SMARTBOX_STATUS_ATTRIBUTES
                )
            case (smartbox_id, "PORTS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, self.SMARTBOX_PORTS_STATUS_ATTRIBUTES
                )
            case (smartbox_id, "THRESHOLDS", None):
                request = PasdBusRequest(
                    smartbox_id, None, None, self.SMARTBOX_THRESHOLD_ATTRIBUTES
                )
            case (smartbox_id, "CURRENT_TRIP_THRESHOLDS", None):
                request = PasdBusRequest(
                    smartbox_id,
                    None,
                    None,
                    self.SMARTBOX_CURRENT_TRIP_THRESHOLD_ATTRIBUTES,
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
        super().poll_succeeded(poll_response)

        if "error" in poll_response.data:
            # Set the event to delay the next poll
            command_info = (
                f" for command {poll_response.command}" if poll_response.command else ""
            )
            self._logger.error(
                f"Error response from device {poll_response.device_id}{command_info}: "
                f"{poll_response.data['error']['detail']}. Delaying next poll..."
            )
            self._poll_delay_event.set()
        else:
            # Ensure the event is cleared to allow normal polling
            self._poll_delay_event.clear()

        self._update_component_state(power=PowerState.ON, fault=False)

        if poll_response.command is None:
            self._pasd_bus_device_state_callback(
                poll_response.device_id,
                **(poll_response.data),
            )

    def poll_failed(self: PasdBusComponentManager, exception: Exception) -> None:
        """
        Respond to an exception being raised by a poll attempt.

        This is a hook called by the poller when an exception occurs.

        :param exception: the exception that was raised by a recent poll
            attempt.
        """
        self._logger.error("Poll failed:", exception, stacklevel=3)
        super().poll_failed(exception)
        self.reset_connection()
        # Set the event to delay the next poll
        self._logger.debug("Setting poll delay event")
        self._poll_delay_event.set()

    @check_communicating
    def request_startup_info(self: PasdBusComponentManager, device_id: int) -> None:
        """Read the registers normally just polled at startup.

        :param: device_id: 0 for the FNDH, 100 for the FNCC, else a smartbox id
        """
        self._request_provider.desire_read_startup_info(device_id)

    @check_communicating
    def initialize_fndh(self: PasdBusComponentManager) -> None:
        """Initialize the FNDH by writing to its status register."""
        self._request_provider.desire_initialize(PasdData.FNDH_DEVICE_ID)
        self._request_provider.desire_read_startup_info(PasdData.FNDH_DEVICE_ID)

    @check_communicating
    def initialize_smartbox(self: PasdBusComponentManager, smartbox_id: int) -> None:
        """
        Initialize a smartbox by writing to its status register.

        :param: smartbox_id: id of the smartbox being addressed
        """
        self._request_provider.desire_initialize(smartbox_id)
        self._request_provider.desire_read_startup_info(smartbox_id)

    @check_communicating
    def initialize_fem_current_trip_thresholds(
        self: PasdBusComponentManager, smartbox_id: int, fem_current_trip_threshold: int
    ) -> None:
        """
        Initialize the FEM current trip thresholds.

        :param: smartbox_id: id of the smartbox being addressed
        :param: fem_current_trip_threshold: threshold value to write
        """
        self._request_provider.desire_attribute_write(
            smartbox_id,
            self.FEM_CURRENT_TRIP_THRESHOLDS_ATTRIBUTE,
            [fem_current_trip_threshold] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
        )

    @check_communicating
    def initialize_sb_input_voltage_thresholds(
        self: PasdBusComponentManager,
        smartbox_id: int,
        input_voltage_thresholds: list[float],
    ) -> None:
        """
        Initialize the input voltage thresholds.

        :param: smartbox_id: id of the smartbox being addressed
        :param: input_voltage_thresholds: alarm hi, warn hi, warn lo, alarm lo values
        """
        if (
            input_voltage_thresholds[0]
            > input_voltage_thresholds[1]
            > input_voltage_thresholds[2]
            > input_voltage_thresholds[3]
        ):
            self._request_provider.desire_attribute_write(
                smartbox_id,
                self.INPUT_VOLTAGE_THRESHOLDS_ATTRIBUTE,
                input_voltage_thresholds,
            )
        else:
            self._logger.error(
                f"Not initializing SB{smartbox_id} input voltage thresholds as "
                "they are not in decreasing order: "
                f"{input_voltage_thresholds}"
            )

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
        self._request_provider.desire_port_powers(
            PasdData.FNDH_DEVICE_ID, port_powers, stay_on_when_offline
        )

    @check_communicating
    def set_fndh_led_pattern(
        self: PasdBusComponentManager,
        pattern: str,
    ) -> None:
        """
        Set the FNDH's LED pattern.

        :param pattern: name of the service LED pattern.
        """
        self._request_provider.desire_led_pattern(PasdData.FNDH_DEVICE_ID, pattern)

    @check_communicating
    def set_fndh_low_pass_filters(
        self: PasdBusComponentManager,
        cutoff: float,
        extra_sensors: bool = False,
    ) -> None:
        """
        Set the FNDH's sensors' low pass filter constants.

        :param cutoff: frequency of LPF to set.
        :param extra_sensors: write the constant to the extra sensors' registers after
            the LED status register.
        """
        self._request_provider.desire_set_low_pass_filter(
            PasdData.FNDH_DEVICE_ID, cutoff, extra_sensors
        )

    @check_communicating
    def reset_fndh_alarms(self: PasdBusComponentManager) -> None:
        """Reset the FNDH alarms register."""
        self._request_provider.desire_alarm_reset(PasdData.FNDH_DEVICE_ID)

    @check_communicating
    def reset_fndh_warnings(self: PasdBusComponentManager) -> None:
        """Reset the FNDH warnings register."""
        self._request_provider.desire_warning_reset(PasdData.FNDH_DEVICE_ID)

    @check_communicating
    def reset_fncc_status(self: PasdBusComponentManager) -> None:
        """Reset the FNCC status register."""
        self._request_provider.desire_status_reset(PasdData.FNCC_DEVICE_ID)

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
        self._request_provider.desire_port_breaker_reset(smartbox_id, port_number)

    @check_communicating
    def set_smartbox_port_powers(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_powers: list[bool | None],
        stay_on_when_offline: bool,
    ) -> None:
        """
        Set the smartbox's port powers.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_powers: specification of the desired power of each port.
            True means on, False means off, None means no change desired.
        :param stay_on_when_offline: whether any ports being turned on
            should remain on if MCCS loses its connection with the PaSD.
        """
        self._request_provider.desire_port_powers(
            smartbox_id, port_powers, stay_on_when_offline
        )

    @check_communicating
    def set_smartbox_led_pattern(
        self: PasdBusComponentManager,
        smartbox_id: int,
        pattern: str,
    ) -> None:
        """
        Set a smartbox's LED pattern.

        :param smartbox_id: the smartbox to have its LEDs' pattern set.
        :param pattern: name of the service LED pattern.
        """
        self._request_provider.desire_led_pattern(smartbox_id, pattern)

    @check_communicating
    def set_smartbox_low_pass_filters(
        self: PasdBusComponentManager,
        smartbox_id: int,
        cutoff: float,
        extra_sensors: bool = False,
    ) -> None:
        """
        Set the Smartbox's sensors' low pass filter constants.

        :param smartbox_id: the smartbox to have its LPF constants set.
        :param cutoff: frequency of LPF to set.
        :param extra_sensors: write the constant to the extra sensors' registers after
            the LED status register.
        """
        self._request_provider.desire_set_low_pass_filter(
            smartbox_id, cutoff, extra_sensors
        )

    @check_communicating
    def reset_smartbox_alarms(self: PasdBusComponentManager, smartbox_id: int) -> None:
        """Reset a smartbox alarms register.

        :param smartbox_id: the smartbox to have its alarms reset
        """
        self._request_provider.desire_alarm_reset(smartbox_id)

    @check_communicating
    def reset_smartbox_warnings(
        self: PasdBusComponentManager, smartbox_id: int
    ) -> None:
        """Reset a smartbox warnings register.

        :param smartbox_id: the smartbox to have its warnings reset
        """
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
        self._request_provider.desire_attribute_write(device_id, attribute_name, value)

    def update_port_power_states(
        self: PasdBusComponentManager, port_power_states: list[bool]
    ) -> None:
        """
        Update the port power states and therefore the list of smartboxes to poll.

        :param port_power_states: list of port power statuses (true=On, false=Off).
        """
        self._request_provider.update_port_power_states(port_power_states)
