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
from typing import Callable, Optional

from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common.component import check_communicating
from ska_ser_devices.client_server import (
    ApplicationClient,
    SentinelBytesMarshaller,
    TcpClient,
)
from ska_tango_base.executor import TaskExecutorComponentManager

from .pasd_bus_json_api import PasdBusJsonApiClient


class PasdBusComponentManager(TaskExecutorComponentManager):
    """A component manager for a PaSD bus."""

    def __init__(  # pylint: disable=too-many-arguments
        self: PasdBusComponentManager,
        host: str,
        port: int,
        timeout: float,
        logger: logging.Logger,
        max_workers: int,
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[..., None],
        pasd_device_state_changed_callback: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param host: IP address of PaSD bus
        :param port: port of the PaSD bus
        :param timeout: maximum time to wait for a response to a server
            request (in seconds).
        :param logger: a logger for this object to use
        :param max_workers: no of worker threads
        :param communication_state_changed_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed_callback: callback to be called
            when the component state changes. Note this in this case the
            "component" is the PaSD bus itself. The PaSD bus has no
            no monitoring points. All we can do is infer that it is
            powered on and not in fault, from the fact that we receive
            responses to our requests.
        :param pasd_device_state_changed_callback: callback to be called
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
        self._pasd_bus_device_state_changed_callback = (
            pasd_device_state_changed_callback
        )
        super().__init__(
            logger,
            communication_state_changed_callback,
            component_state_changed_callback,
            max_workers=max_workers,
            power=None,
            fault=None,
        )

    def start_communicating(self: PasdBusComponentManager) -> None:
        """
        Start communicating with the component.

        (This is a temporary implementation that checks for
        communication with the PaSD by querying a single attribute.
        In future this will be updated to lauch a polling loop.)
        """
        # TODO: This is a temporary implementation that only makes a
        # single request.
        if self.communication_state == CommunicationStatus.ESTABLISHED:
            return
        if self.communication_state == CommunicationStatus.DISABLED:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            # TODO: These are temporary calls, just until we have a poller.
            self._get_fndh_static_info()
            self._get_fndh_status()
            self._get_fndh_ports_status()
            for smartbox_number in range(1, 25):
                self._get_smartbox_static_info(smartbox_number)
                self._get_smartbox_status(smartbox_number)
                self._get_smartbox_ports_status(smartbox_number)

    def stop_communicating(self: PasdBusComponentManager) -> None:
        """
        Break off communicating with the component.

        (This is a temporary implementation that doesn't do anything.
        In future it will stop the polling loop.)
        """
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._update_communication_state(CommunicationStatus.DISABLED)
        self._update_component_state(power=None, fault=None)

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

    def _get_fndh_static_info(self: PasdBusComponentManager) -> None:
        """Call back with updated static information about a PaSD device."""
        self._read_from_pasd(
            0,
            "modbus_register_map_revision",
            "pcb_revision",
            "cpu_id",
            "chip_id",
            "firmware_version",
        )

    def _get_fndh_status(self: PasdBusComponentManager) -> None:
        """Call back with updated information about the status of the FNDH."""
        self._read_from_pasd(
            0,
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

    def _get_fndh_ports_status(self: PasdBusComponentManager) -> None:
        """Call back with updated information about status of the FNDH ports."""
        self._read_from_pasd(
            0,
            "ports_connected",
            "port_forcings",
            "port_breakers_tripped",
            "ports_desired_power_when_online",
            "ports_desired_power_when_offline",
            "ports_power_sensed",
        )

    def _get_smartbox_static_info(
        self: PasdBusComponentManager,
        smartbox_number: int,
    ) -> None:
        """
        Call back with updated static information about a smartbox.

        :param smartbox_number: number of the smartbox for which information is sought.
        """
        self._read_from_pasd(
            smartbox_number,
            "modbus_register_map_revision",
            "pcb_revision",
            "cpu_id",
            "chip_id",
            "firmware_version",
        )

    def _get_smartbox_status(
        self: PasdBusComponentManager,
        smartbox_number: int,
    ) -> None:
        """
        Call back with updated information about the status of a smartbox.

        :param smartbox_number: number of the smartbox for which information is sought.
        """
        self._read_from_pasd(
            smartbox_number,
            "uptime",
            "status",
            "led_pattern",
            "input_voltage",
            "power_supply_output_voltage",
            "power_supply_temperature",
            "outside_temperature",
            "pcb_temperature",
        )

    def _get_smartbox_ports_status(
        self: PasdBusComponentManager,
        smartbox_number: int,
    ) -> None:
        """
        Call back with updated information about status of a smartbox's ports.

        :param smartbox_number: number of the smartbox for which information is sought.
        """
        self._read_from_pasd(
            smartbox_number,
            "ports_connected",
            "port_forcings",
            "port_breakers_tripped",
            "ports_desired_power_when_online",
            "ports_desired_power_when_offline",
            "ports_power_sensed",
            "ports_current_draw",
        )

    def _read_from_pasd(
        self: PasdBusComponentManager,
        pasd_device_number: int,
        *attribute_names: str,
    ) -> None:
        attribute_values = self._pasd_bus_api_client.read_attributes(
            pasd_device_number,
            *attribute_names,
        )

        # TODO: Handle communication failures by wrapping the above in a
        # try block and catching exceptions, instead of assuming
        # communication will always succeed.
        self._update_communication_state(CommunicationStatus.ESTABLISHED)
        self._update_component_state(power=PowerState.ON, fault=False)

        self._pasd_bus_device_state_changed_callback(
            pasd_device_number,
            **attribute_values,
        )

    @check_communicating
    def reset_fndh_port_breaker(
        self: PasdBusComponentManager,
        port_number: int,
    ) -> Optional[bool]:
        """
        Reset an FNDH port breaker.

        :param port_number: the number of the port to reset.

        :return: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            0, "reset_port_breaker", port_number
        )
        self._get_fndh_ports_status()  # XXX: Until we poll
        return result

    @check_communicating
    def turn_fndh_port_on(
        self: PasdBusComponentManager,
        port_number: int,
        stay_on_when_offline: bool,
    ) -> Optional[bool]:
        """
        Turn on a specified FNDH port.

        :param port_number: the number of the port.
        :param stay_on_when_offline: whether the port should remain on
            if monitoring and control goes offline.

        :return: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            0, "turn_port_on", port_number, stay_on_when_offline
        )
        self._get_fndh_ports_status()  # XXX: Until we poll
        return result

    @check_communicating
    def turn_fndh_port_off(
        self: PasdBusComponentManager,
        port_number: int,
    ) -> Optional[bool]:
        """
        Turn off a specified FNDH port.

        :param port_number: the number of the port.

        :return: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            0, "turn_port_off", port_number
        )
        self._get_fndh_ports_status()  # XXX: Until we poll
        return result

    @check_communicating
    def set_fndh_led_pattern(
        self: PasdBusComponentManager,
        led_pattern: str,
    ) -> Optional[bool]:
        """
        Set the FNDH's LED pattern.

        :param led_pattern: name of the LED pattern.
            Options are "OFF" and "SERVICE".

        :returns: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            0, "set_led_pattern", led_pattern
        )
        self._get_fndh_status()  # XXX: Until we poll
        return result

    @check_communicating
    def reset_smartbox_port_breaker(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_number: int,
    ) -> Optional[bool]:
        """
        Reset a smartbox port's breaker.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_number: the number of the port to reset.

        :return: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            smartbox_id, "reset_port_breaker", port_number
        )
        self._get_smartbox_ports_status(smartbox_id)  # XXX: Until we poll
        return result

    @check_communicating
    def turn_smartbox_port_on(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_number: int,
        stay_on_when_offline: bool,
    ) -> Optional[bool]:
        """
        Turn on a specified smartbox port.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_number: the number of the port.
        :param stay_on_when_offline: whether the port should remain on
            if monitoring and control goes offline.

        :return: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            smartbox_id, "turn_port_on", port_number, stay_on_when_offline
        )
        self._get_smartbox_ports_status(smartbox_id)  # XXX: Until we poll
        return result

    @check_communicating
    def turn_smartbox_port_off(
        self: PasdBusComponentManager,
        smartbox_id: int,
        port_number: int,
    ) -> Optional[bool]:
        """
        Turn off a specified smartbox port.

        :param smartbox_id: id of the smartbox being addressed.
        :param port_number: the number of the port.

        :return: whether successful, or None if there was nothing to do.
        """
        result = self._pasd_bus_api_client.execute_command(
            smartbox_id, "turn_port_off", port_number
        )
        self._get_smartbox_ports_status(smartbox_id)  # XXX: Until we poll
        return result

    @check_communicating
    def set_smartbox_led_pattern(
        self: PasdBusComponentManager,
        smartbox_id: int,
        led_pattern: str,
    ) -> Optional[bool]:
        """
        Set a smartbox's LED pattern.

        :param smartbox_id: the smartbox to have its LED pattern set
        :param led_pattern: name of the LED pattern.
            Options are "OFF" and "SERVICE".

        :return: whether successful, or None if there was nothing to do
        """
        result = self._pasd_bus_api_client.execute_command(
            smartbox_id, "set_led_pattern", led_pattern
        )
        self._get_smartbox_status(smartbox_id)  # XXX: Until we poll
        return result
