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
from typing import Any, Optional

import pytest

from ska_low_mccs_pasd.pasd_bus import PasdBusComponentManager


class TestPasdBusComponentManager:
    """
    Tests of commands common to the PaSDBus simulator and its component manager.

    Because the PaSD bus component manager passes commands down to the
    PaSD bus simulator, many commands are common. Here we test those
    common commands.
    """

    @pytest.mark.parametrize(
        "attribute_name",
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
        pasd_bus_component_manager: PasdBusComponentManager,
        attribute_name: str,
    ) -> None:
        """
        Test property reads on the component manager.

        We tell the component manager to read a value from the PaSD bus,
        and we also read the value directly from the simulator.
        Then we assert that these values are the same.

        :param mock_pasd_bus_simulator: the PaSD bus simulator
            that is acted upon by the component manager under test,
            wrapped by a mock so that we can assert calls
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test
        :param attribute_name: name of the attribute to be read
        """
        # Reset this because start_communicating() calls fndh_status ATM.
        # Yes, mocking properties in python really is this messy
        type(mock_pasd_bus_simulator).__dict__[attribute_name].reset_mock()

        value_as_read = getattr(pasd_bus_component_manager, attribute_name)

        type(mock_pasd_bus_simulator).__dict__[attribute_name].assert_called_once_with()

        simulator_value = getattr(mock_pasd_bus_simulator, attribute_name)
        assert value_as_read == simulator_value

        # TODO: It's a little surprising that this test passes as-is,
        # even though some of these attributes are float-valued.
        # We should break out the float-valued ones into another test,
        # and use pytest.approx() for equality checking.

    @pytest.mark.parametrize(
        ("command_name", "args", "kwargs"),
        [
            ("reload_database", [], {}),
            ("get_fndh_info", [], {}),
            ("is_fndh_port_power_sensed", [1], {}),
            ("set_fndh_service_led_on", [True], {}),
            ("get_fndh_port_forcing", [1], {}),
            ("get_smartbox_info", [1], {}),
            ("turn_smartbox_off", [1], {}),
            ("is_smartbox_port_power_sensed", [1, 2], {}),
            ("set_smartbox_service_led_on", [1, True], {}),
            ("get_smartbox_ports_power_sensed", [1], {}),
            ("get_antenna_info", [1], {}),
            ("get_antenna_forcing", [1], {}),
            ("reset_antenna_breaker", [1], {}),
            ("turn_antenna_off", [1], {}),
            ("update_status", [], {}),
        ],
    )
    # pylint: disable=too-many-arguments
    def test_command(
        self: TestPasdBusComponentManager,
        mock_pasd_bus_simulator: unittest.mock.Mock,
        pasd_bus_component_manager: PasdBusComponentManager,
        command_name: str,
        args: Optional[list[Any]],
        kwargs: Optional[dict[str, Any]],
    ) -> None:
        """
        Test commands invoked on the component manager.

        Here we test only that the command invokations are passed
        through to the simulator.

        :param mock_pasd_bus_simulator: the PaSD bus simulator
            that is acted upon by the component manager under test,
            wrapped with a mock so that we can assert calls
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test
        :param command_name: name of the command to be invoked on the
            component manager.
        :param args: positional args to the command under test
        :param kwargs: keyword args to the command under test
        """
        _ = getattr(pasd_bus_component_manager, command_name)(*args, **kwargs)

        getattr(mock_pasd_bus_simulator, command_name).assert_called_once_with(
            *args, **kwargs
        )

    def test_turn_smartbox_on_off(
        self: TestPasdBusComponentManager,
        mock_pasd_bus_simulator: unittest.mock.Mock,
        pasd_bus_component_manager: PasdBusComponentManager,
    ) -> None:
        """
        Test a smartbox on and off.

        :param mock_pasd_bus_simulator: the PaSD bus simulator
            that is acted upon by the component manager under test,
            wrapped with a mock so that we can assert calls
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test
        """
        assert pasd_bus_component_manager.turn_smartbox_on(1)
        mock_pasd_bus_simulator.turn_smartbox_on.assert_called_once_with(1, True)
        mock_pasd_bus_simulator.turn_smartbox_on.reset_mock()

        assert None is pasd_bus_component_manager.turn_smartbox_on(1)
        mock_pasd_bus_simulator.assert_not_called()

        assert pasd_bus_component_manager.turn_smartbox_off(1)
        mock_pasd_bus_simulator.turn_smartbox_off.assert_called_once_with(1)
        mock_pasd_bus_simulator.turn_smartbox_off.reset_mock()

        assert None is pasd_bus_component_manager.turn_smartbox_off(1)
        mock_pasd_bus_simulator.assert_not_called()

    def test_turn_antenna_on_off(
        self: TestPasdBusComponentManager,
        mock_pasd_bus_simulator: unittest.mock.Mock,
        pasd_bus_component_manager: PasdBusComponentManager,
    ) -> None:
        """
        Test turning on a smartbox.

        :param mock_pasd_bus_simulator: the PaSD bus simulator
            that is acted upon by the component manager under test,
            wrapped with a mock so that we can assert calls
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test
        """
        assert pasd_bus_component_manager.turn_antenna_on(1)
        mock_pasd_bus_simulator.turn_antenna_on.assert_called_once_with(1, True)
        mock_pasd_bus_simulator.turn_antenna_on.reset_mock()

        assert None is pasd_bus_component_manager.turn_antenna_on(1)
        mock_pasd_bus_simulator.assert_not_called()

        assert pasd_bus_component_manager.turn_antenna_off(1)
        mock_pasd_bus_simulator.turn_antenna_off.assert_called_once_with(1)
        mock_pasd_bus_simulator.turn_antenna_off.reset_mock()

        assert None is pasd_bus_component_manager.turn_antenna_off(1)
        mock_pasd_bus_simulator.assert_not_called()
