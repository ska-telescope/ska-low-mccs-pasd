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

from ska_control_model import CommunicationStatus, TaskStatus
from ska_low_mccs_common.component import check_communicating
from ska_tango_base.executor import TaskExecutorComponentManager

from .pasd_bus_json_api import PasdBusJsonApi, PasdBusJsonApiClient
from .pasd_bus_simulator import PasdBusSimulator


class PasdBusComponentManager(TaskExecutorComponentManager):
    """A component manager for a PaSD bus."""

    def __init__(
        self: PasdBusComponentManager,
        logger: logging.Logger,
        max_workers: int,
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[[dict[str, Any]], None],
        _simulator: Optional[PasdBusSimulator] = None,
        # TODO callbacks for changes to antenna power, smartbox power, etc
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param max_workers: no of worker threads
        :param communication_state_changed_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed_callback: callback to be called when the
            component state changes
        :param _simulator: for testing only, we can provide a simulator
            rather than letting the component manager create one.
        """
        pasd_bus_simulator = _simulator or PasdBusSimulator(
            "src/ska_low_mccs_pasd/pasd_bus/pasd_configuration.yaml",
            1,
            logger,
        )
        pasd_bus_api = PasdBusJsonApi(pasd_bus_simulator)
        self._pasd_bus_api_client = PasdBusJsonApiClient(pasd_bus_api)
        super().__init__(
            logger,
            communication_state_changed_callback,
            component_state_changed_callback,
            max_workers=max_workers,
        )

    def start_communicating(self: PasdBusComponentManager) -> None:
        """
        Start communicating with the component.

        (This is a temporary implementation that never fails to establish
        communication immediately, since the simulator is an object in
        memory.)
        """
        if self.communication_state == CommunicationStatus.ESTABLISHED:
            return
        if self.communication_state == CommunicationStatus.DISABLED:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            self._update_communication_state(CommunicationStatus.ESTABLISHED)

    def stop_communicating(self: PasdBusComponentManager) -> None:
        """Break off communicating with the component."""
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
            "reload_database",
            "reset",
            "get_fndh_info",
            "fndh_psu48v_voltages",
            "fndh_psu5v_voltage",
            "fndh_psu48v_current",
            "fndh_psu48v_temperature",
            "fndh_psu5v_temperature",
            "fndh_pcb_temperature",
            "fndh_outside_temperature",
            "fndh_status",
            "fndh_service_led_on",
            "set_fndh_service_led_on",
            "fndh_ports_power_sensed",
            "is_fndh_port_power_sensed",
            "fndh_ports_connected",
            "fndh_port_forcings",
            "get_fndh_port_forcing",
            "simulate_fndh_port_forcing",
            "fndh_ports_desired_power_online",
            "fndh_ports_desired_power_offline",
            "get_smartbox_info",
            "turn_smartbox_on",
            "turn_smartbox_off",
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
            "simulate_antenna_forcing",
            "simulate_antenna_breaker_trip",
            "reset_antenna_breaker",
            "antennas_tripped",
            "turn_antenna_on",
            "turn_antenna_off",
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
