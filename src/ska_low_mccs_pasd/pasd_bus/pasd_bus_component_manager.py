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
from typing import Any, Callable, Optional

from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common.component import check_communicating
from ska_ser_devices.client_server import (
    ApplicationClient,
    SentinelBytesMarshaller,
    TcpClient,
)
from ska_tango_base.executor import TaskExecutorComponentManager

from .pasd_bus_json_api import PasdBusJsonApiClient
from .pasd_bus_simulator import AntennaInfoType, FndhInfoType, SmartboxInfoType


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
        # TODO callbacks for changes to antenna power, smartbox power, etc
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
        :param component_state_changed_callback: callback to be called when the
            component state changes
        """
        tcp_client = TcpClient(host, port, timeout)
        marshaller = SentinelBytesMarshaller(b"\n")
        application_client = ApplicationClient(
            tcp_client, marshaller.marshall, marshaller.unmarshall
        )
        self._pasd_bus_api_client = PasdBusJsonApiClient(application_client)

        super().__init__(
            logger,
            communication_state_changed_callback,
            component_state_changed_callback,
            max_workers=max_workers,
            power=None,
            fault=None,
            fndh_status=None,
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
            self._update_communication_state(CommunicationStatus.ESTABLISHED)

            if self.fndh_status == "OK":
                self._update_component_state(
                    power=PowerState.ON,
                    fault=False,
                    fndh_status="OK",
                )

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

    @check_communicating
    def reload_database(self: PasdBusComponentManager) -> bool:
        """
        Tell the PaSD to reload its configuration data.

        :return: whether successful.
        """
        return self._pasd_bus_api_client.reload_database()

    @check_communicating
    def get_fndh_info(self: PasdBusComponentManager) -> FndhInfoType:
        """
        Return information about an FNDH controller.

        :return: a dictionary containing information about the FNDH
            controller.
        """
        return self._pasd_bus_api_client.get_fndh_info()

    @check_communicating
    def set_fndh_service_led_on(
        self: PasdBusComponentManager,
        led_on: bool,
    ) -> Optional[bool]:
        """
        Turn on/off the FNDH's blue service indicator LED.

        :param led_on: whether the LED should be on.

        :returns: whether successful, or None if there was nothing to do
        """
        return self._pasd_bus_api_client.set_fndh_service_led_on(led_on)

    @check_communicating
    def get_smartbox_info(
        self: PasdBusComponentManager, smartbox_number: int
    ) -> SmartboxInfoType:
        """
        Return information about a smartbox.

        :param smartbox_number: the number of the smartbox for which to
            return information

        :return: a dictionary containing information about the smartbox.
        """
        return self._pasd_bus_api_client.get_smartbox_info(smartbox_number)

    @check_communicating
    def get_antenna_info(
        self: PasdBusComponentManager, antenna_number: int
    ) -> AntennaInfoType:
        """
        Return information about a antenna.

        :param antenna_number: the number of the antenna for which to
            return information

        :return: a dictionary containing information about the antenna.
        """
        return self._pasd_bus_api_client.get_antenna_info(antenna_number)

    @check_communicating
    def turn_smartbox_on(
        self: PasdBusComponentManager,
        smartbox_id: int,
    ) -> Optional[bool]:
        """
        Turn on a smartbox.

        :param smartbox_id: the id of the smartbox to turn on.

        :return: whether successful, or None if there was nothing to do.
        """
        return self._pasd_bus_api_client.turn_smartbox_on(smartbox_id)

    @check_communicating
    def turn_smartbox_off(
        self: PasdBusComponentManager,
        smartbox_id: int,
    ) -> Optional[bool]:
        """
        Turn off a smartbox.

        :param smartbox_id: the id of the smartbox to turn off.

        :return: whether successful, or None if there was nothing to do.
        """
        return self._pasd_bus_api_client.turn_smartbox_off(smartbox_id)

    @check_communicating
    def turn_antenna_on(
        self: PasdBusComponentManager,
        antenna_id: int,
    ) -> Optional[bool]:
        """
        Turn on an antenna.

        :param antenna_id: the id of the antenna to turn on.

        :return: whether successful, or None if there was nothing to do.
        """
        return self._pasd_bus_api_client.turn_antenna_on(antenna_id)

    @check_communicating
    def turn_antenna_off(
        self: PasdBusComponentManager,
        antenna_id: int,
    ) -> Optional[bool]:
        """
        Turn off an antenna.

        :param antenna_id: the id of the antenna to turn off.

        :return: whether successful, or None if there was nothing to do.
        """
        return self._pasd_bus_api_client.turn_antenna_off(antenna_id)

    @check_communicating
    def reset_antenna_breaker(
        self: PasdBusComponentManager,
        antenna_id: int,
    ) -> Optional[bool]:
        """
        Reset an antenna's port breaker.

        :param antenna_id: the id of the antenna to turn off.

        :return: whether successful, or None if there was nothing to do.
        """
        return self._pasd_bus_api_client.reset_antenna_breaker(antenna_id)

    def __getattr__(
        self: PasdBusComponentManager,
        name: str,
        default_value: Any = None,
    ) -> Any:
        """
        Get value for an attribute not found in the usual way.

        Implemented to check against a list of attributes to pass down
        to the simulator. The intent is to avoid having to implement a
        whole lot of methods that simply call the corresponding method
        on the simulator. The only reason this is possible is because
        the simulator has much the same interface as its component
        manager.

        :param name: name of the requested attribute
        :param default_value: value to return if the attribute is not
            found

        :return: the requested attribute
        """
        if name in [
            "fndh_psu48v_voltages",
            "fndh_psu5v_voltage",
            "fndh_psu48v_current",
            "fndh_psu48v_temperature",
            "fndh_psu5v_temperature",
            "fndh_pcb_temperature",
            "fndh_outside_temperature",
            "fndh_status",
            "fndh_service_led_on",
            "fndh_ports_power_sensed",
            "is_fndh_port_power_sensed",
            "fndh_ports_connected",
            "fndh_port_forcings",
            "get_fndh_port_forcing",
            "fndh_ports_desired_power_online",
            "fndh_ports_desired_power_offline",
            "is_smartbox_port_power_sensed",
            "smartbox_input_voltages",
            "smartbox_power_supply_output_voltages",
            "smartbox_statuses",
            "smartbox_power_supply_temperatures",
            "smartbox_outside_temperatures",
            "smartbox_pcb_temperatures",
            "smartbox_service_leds_on",
            "set_smartbox_service_led_on",
            "smartbox_fndh_ports",
            "smartboxes_desired_power_online",
            "smartboxes_desired_power_offline",
            "get_smartbox_ports_power_sensed",
            "get_antenna_info",
            "antennas_online",
            "antenna_forcings",
            "get_antenna_forcing",
            "antennas_tripped",
            "antennas_power_sensed",
            "antennas_desired_power_online",
            "antennas_desired_power_offline",
            "antenna_currents",
            "update_status",
        ]:
            return self._get_from_component(name)
        return default_value

    @check_communicating
    def _get_from_component(
        self: PasdBusComponentManager,
        name: str,
    ) -> Any:
        """
        Get an attribute from the component (if we are communicating with it).

        :param name: name of the attribute to get.

        :return: the attribute value
        """
        # This one-liner is only a method so that we can decorate it.
        return getattr(self._pasd_bus_api_client, name)
