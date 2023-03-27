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
from typing import Any, Callable, Optional, cast

from ska_control_model import CommunicationStatus, SimulationMode, TaskStatus
from ska_low_mccs_common.component import (
    DriverSimulatorSwitchingComponentManager,
    MccsComponentManagerProtocol,
    ObjectComponentManager,
    check_communicating,
)

from .pasd_bus_simulator import PasdBusSimulator


class PasdBusSimulatorComponentManager(ObjectComponentManager):
    """A base component manager for a PaSD bus simulator."""

    def __init__(
        self: PasdBusSimulatorComponentManager,
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
        super().__init__(
            pasd_bus_simulator,
            logger,
            max_workers,
            communication_state_changed_callback,
            component_state_changed_callback,
            None,
        )

    def __getattr__(
        self: PasdBusSimulatorComponentManager,
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
        self: PasdBusSimulatorComponentManager,
        name: str,
    ) -> Any:
        """
        Get an attribute from the component (if we are communicating with it).

        :param name: name of the attribute to get.

        :return: the attribute value
        """
        # This one-liner is only a method so that we can decorate it.
        return getattr(self._component, name)


class PasdBusComponentManager(DriverSimulatorSwitchingComponentManager):
    """A component manager that switches between PaSD bus simulator and driver."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: PasdBusComponentManager,
        initial_simulation_mode: SimulationMode,
        logger: logging.Logger,
        max_workers: int,
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[[dict[str, Any]], None],
        _simulator_component_manager: Optional[PasdBusSimulatorComponentManager] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param initial_simulation_mode: the simulation mode that the
            component should start in
        :param logger: a logger for this object to use
        :param max_workers: no of worker threads
        :param initial_simulation_mode: the simulation mode that the
            component should start in
        :param communication_state_changed_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed_callback: callback to be called when the
            component state changes
        :param _simulator_component_manager: for testing only, we can
            provide a pre-created component manager for the simulator,
            rather than letting this component manager create one.
        """
        pasd_bus_simulator = (
            _simulator_component_manager
            or PasdBusSimulatorComponentManager(
                logger,
                max_workers,
                communication_state_changed_callback,
                component_state_changed_callback,
            )
        )
        super().__init__(
            None,
            cast(MccsComponentManagerProtocol, pasd_bus_simulator),
            initial_simulation_mode,
        )

    def reload_database(
        self: PasdBusComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Submit the reload_database slow task.

        This method returns immediately after it is submitted for execution.

        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._reload_database, args=[], task_callback=task_callback
        )
        return task_status, unique_id

    def get_fndh_info(
        self: PasdBusComponentManager,
        fndh: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the get_fndh_info slow task.

        This method returns immediately after it is submitted for execution.

        :param fndh: the fndh to get info from
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._get_fndh_info, args=[fndh], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_fndh_service_led_on(
        self: PasdBusComponentManager,
        fndh: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_fndh_service_led_on slow task.

        This method returns immediately after it is submitted for execution.

        :param fndh: the fndh service led to turn on
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_fndh_service_led_on, args=[fndh], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_fndh_service_led_off(
        self: PasdBusComponentManager,
        fndh: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_fndh_service_led_off slow task.

        This method returns immediately after it is submitted for execution.

        :param fndh: the fndh service led to turn off
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_fndh_service_led_off, args=[fndh], task_callback=task_callback
        )
        return task_status, unique_id

    def get_smartbox_info(
        self: PasdBusComponentManager,
        smartbox: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the get_smartbox_info slow task.

        This method returns immediately after it is submitted for execution.

        :param smartbox: the smartbox to get info from
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._get_smartbox_info, args=[smartbox], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_smartbox_on(
        self: PasdBusComponentManager,
        smartbox: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_smartbox_off slow task.

        This method returns immediately after it is submitted for execution.

        :param smartbox: the smartbox to turn on
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_smartbox_on, args=[smartbox], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_smartbox_off(
        self: PasdBusComponentManager,
        smartbox: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_smartbox_off slow task.

        This method returns immediately after it is submitted for execution.

        :param smartbox: the smartbox to turn off
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_smartbox__off, args=[smartbox], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_smartbox_service_led_on(
        self: PasdBusComponentManager,
        smartbox: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_smartbox_service_led_on slow task.

        This method returns immediately after it is submitted for execution.

        :param smartbox: the smartbox service led to turn on
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_smartbox_service_led_on,
            args=[smartbox],
            task_callback=task_callback,
        )
        return task_status, unique_id

    def turn_smartbox_service_led_off(
        self: PasdBusComponentManager,
        smartbox: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_smartbox_service_led_off slow task.

        This method returns immediately after it is submitted for execution.

        :param smartbox: the smartbox service led to turn off
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_smartbox_service_led_off,
            args=[smartbox],
            task_callback=task_callback,
        )
        return task_status, unique_id

    def get_antenna_info(
        self: PasdBusComponentManager,
        antenna: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the get_antenna_info slow task.

        This method returns immediately after it is submitted for execution.

        :param antenna: the antenna to get info from
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._get_antenna_info, args=[antenna], task_callback=task_callback
        )
        return task_status, unique_id

    def reset_antenna_breaker(
        self: PasdBusComponentManager,
        antenna: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the reset_antenna_breaker slow task.

        This method returns immediately after it is submitted for execution.

        :param antenna: the antenna breaker to reset
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._reset_antenna_breaker, args=[antenna], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_antenna_on(
        self: PasdBusComponentManager,
        antenna: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_antenna_on slow task.

        This method returns immediately after it is submitted for execution.

        :param antenna: the antenna to turn on
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_antenna_on, args=[antenna], task_callback=task_callback
        )
        return task_status, unique_id

    def turn_antenna_off(
        self: PasdBusComponentManager,
        antenna: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the turn_antenna_off slow task.

        This method returns immediately after it is submitted for execution.

        :param antenna: the antenna to turn off
        :param task_callback: Update task state, defaults to None

        :return: A tuple containing a task status and a unique id string to
            identify the command
        """
        task_status, unique_id = self.submit_task(
            self._turn_antenna_off, args=[antenna], task_callback=task_callback
        )
        return task_status, unique_id
