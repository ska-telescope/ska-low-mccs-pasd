# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus component manager."""
from __future__ import annotations

import unittest.mock
from typing import Any, Optional, Union

import pytest
from _pytest.fixtures import SubRequest

from ska_low_mccs_pasd.pasd_bus import (
    PasdBusComponentManager,
    PasdBusSimulatorComponentManager,
)


class TestPasdBusComponentManager:
    """
    Tests of commands common to the PaSDBus simulator and its component manager.

    Because the PaSD bus component manager passes commands down to the
    PaSD bus simulator, many commands are common. Here we test those
    common commands.
    """

    @pytest.fixture(
        params=[
            "pasd_bus_simulator_component_manager",
            "pasd_bus_component_manager",
        ]
    )
    def pasd_bus_component_manager(
        self: TestPasdBusComponentManager,
        pasd_bus_simulator_component_manager: PasdBusSimulatorComponentManager,
        pasd_bus_component_manager: PasdBusComponentManager,
        request: SubRequest,
    ) -> Union[PasdBusSimulatorComponentManager, PasdBusComponentManager]:
        """
        Return the PaSD bus component class object under test.

        This is parametrised to return

        * a PaSD bus simulator component manager,

        * a PaSD bus component manager,

        So any test that relies on this fixture will be run twice.

        :param pasd_bus_simulator_component_manager: the PaSD bus
            simulator component manager to return
        :param pasd_bus_component_manager: the PaSD bus component
            manager to return
        :param request: A pytest object giving access to the requesting test
            context.

        :raises ValueError: if parametrized with an unrecognised option

        :return: the PaSD bus component object under test
        """
        if request.param == "pasd_bus_simulator_component_manager":
            pasd_bus_simulator_component_manager.start_communicating()
            return pasd_bus_simulator_component_manager
        if request.param == "pasd_bus_component_manager":
            pasd_bus_component_manager.start_communicating()
            return pasd_bus_component_manager
        raise ValueError("PaSD bus fixture parametrized with unrecognised option")

    @pytest.mark.parametrize(
        "property_name",
        [
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
            "fndh_ports_connected",
            "fndh_port_forcings",
            "fndh_ports_desired_power_online",
            "fndh_ports_desired_power_offline",
            "smartbox_input_voltages",
            "smartbox_power_supply_output_voltages",
            "smartbox_statuses",
            "smartbox_power_supply_temperatures",
            "smartbox_outside_temperatures",
            "smartbox_pcb_temperatures",
            "smartbox_service_leds_on",
            "smartbox_fndh_ports",
            "smartboxes_desired_power_online",
            "smartboxes_desired_power_offline",
            "antennas_online",
            "antenna_forcings",
            "antennas_tripped",
            "antennas_power_sensed",
            "antennas_desired_power_online",
            "antennas_desired_power_offline",
            "antenna_currents",
        ],
    )
    def test_read_only_property(
        self: TestPasdBusComponentManager,
        mock_pasd_bus_simulator: unittest.mock.Mock,
        pasd_bus_component_manager: Union[
            PasdBusSimulatorComponentManager, PasdBusComponentManager
        ],
        property_name: str,
    ) -> None:
        """
        Test property reads on the component manager.

        Here we test only that the reads pass through to the simulator.

        :param mock_pasd_bus_simulator: a mock PaSD bus simulator that
            is acted upon by this component manager
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test
        :param property_name: name of the property to be read
        """
        _ = getattr(pasd_bus_component_manager, property_name)

        # Yes, mocking properties in python really is this messy
        type(mock_pasd_bus_simulator).__dict__[property_name].assert_called_once_with()

    @pytest.mark.parametrize(
        ("command_name", "args", "kwargs"),
        [
            ("reload_database", [], {}),
            ("get_fndh_info", [1], {}),
            ("is_fndh_port_power_sensed", [1], {}),
            ("set_fndh_service_led_on", [True], {}),
            ("get_fndh_port_forcing", [1], {}),
            ("simulate_fndh_port_forcing", [1, True], {}),
            ("get_smartbox_info", [1], {}),
            ("turn_smartbox_on", [1], {}),
            ("turn_smartbox_off", [1], {}),
            ("is_smartbox_port_power_sensed", [1, 2], {}),
            ("set_smartbox_service_led_on", [1, True], {}),
            ("get_smartbox_ports_power_sensed", [1], {}),
            ("get_antenna_info", [1], {}),
            ("get_antenna_forcing", [1], {}),
            ("simulate_antenna_forcing", [1, True], {}),
            ("simulate_antenna_breaker_trip", [1], {}),
            ("reset_antenna_breaker", [1], {}),
            ("turn_antenna_on", [1], {}),
            ("turn_antenna_off", [1], {}),
            ("update_status", [], {}),
        ],
    )
    # pylint: disable=too-many-arguments
    def test_command(
        self: TestPasdBusComponentManager,
        mock_pasd_bus_simulator: unittest.mock.Mock,
        pasd_bus_component_manager: Union[
            PasdBusSimulatorComponentManager, PasdBusComponentManager
        ],
        command_name: str,
        args: Optional[list[Any]],
        kwargs: Optional[dict[str, Any]],
    ) -> None:
        """
        Test commands invoked on the component manager.

        Here we test only that the command invokations are passed
        through to the simulator.

        :param mock_pasd_bus_simulator: a mock PaSD bus simulator that
            is acted upon by this component manager
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test
        :param command_name: name of the command to be invoked on the
            component manager.
        :param args: positional args to the command under test
        :param kwargs: keyword args to the command under test
        """
        _ = getattr(pasd_bus_component_manager, command_name)(*args, **kwargs)
        if (
            _ is None
        ):  # if method is not defined in component manager class then command is
            # called by simulator class
            getattr(mock_pasd_bus_simulator, command_name).assert_called_once_with(
                *args, **kwargs
            )
