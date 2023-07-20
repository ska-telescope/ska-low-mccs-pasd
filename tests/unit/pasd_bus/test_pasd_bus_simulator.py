# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus component manager."""
from __future__ import annotations

from typing import Any

import pytest

from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import (
    FndhSimulator,
    SmartboxSimulator,
)


class TestFndhSimulator:
    """Tests of the FndhSimulator."""

    @pytest.fixture(name="fndh_config")
    def fndh_config_fixture(
        self: TestFndhSimulator, pasd_config: dict[str, Any]
    ) -> list[bool]:
        """
        Return FNDH configuration data, specifying which ports are connected.

        :param pasd_config: the overall PaSD configuration data from
            which the FNDH configuration data will be extracted.

        :return: a list of booleans indicating which ports are connected
        """
        is_port_connected = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_config in pasd_config["smartboxes"]:
            is_port_connected[smartbox_config["fndh_port"] - 1] = True
        return list(is_port_connected)

    @pytest.fixture(name="connected_fndh_port")
    def connected_fndh_port_fixture(
        self: TestFndhSimulator, fndh_simulator: FndhSimulator
    ) -> int:
        """
        Return an FNDH simulator port that has a smartbox connected to it.

        :param fndh_simulator: the FNDH simulator for which a connected port
            is sought.

        :return: an FNDH port that has a smartbox connected to it.
        """
        return fndh_simulator.ports_connected.index(True) + 1

    @pytest.fixture(name="unconnected_fndh_port")
    def unconnected_fndh_port_fixture(
        self: TestFndhSimulator, fndh_simulator: FndhSimulator
    ) -> int:
        """
        Return an FNDH simulator port that doesn't have a smartbox connected to it.

        :param fndh_simulator: the FNDH simulator for which an unconnected
            port is sought.

        :return: an FNDH port that doesn't have a smartbox connected to it.
        """
        return fndh_simulator.ports_connected.index(False) + 1

    def test_forcing_unconnected_fndh_port(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        unconnected_fndh_port: int,
    ) -> None:
        """
        Test that we can force an unconnected port on.

        :param fndh_simulator: the FNDH simulator under test
        :param unconnected_fndh_port: the port number for an FNDH port
            that doesn't have a smartbox connected
        """
        expected_forcings: list[str] = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, True)
        expected_forcings[unconnected_fndh_port - 1] = "ON"
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, True) is None
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, False)
        expected_forcings[unconnected_fndh_port - 1] = "OFF"
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert (
            fndh_simulator.simulate_port_forcing(unconnected_fndh_port, False) is None
        )
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, None)
        expected_forcings[unconnected_fndh_port - 1] = "NONE"
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, None) is None
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

    def test_forcing_connected_fndh_port(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        connected_fndh_port: int,
    ) -> None:
        """
        Test that we can force a connected port on.

        :param fndh_simulator: the FNDH simulator under test
        :param connected_fndh_port: the port number for an FNDH port
            that has a smartbox connected
        """
        expected_forcings: list[str] = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, True)
        expected_forcings[connected_fndh_port - 1] = "ON"
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert not fndh_simulator.turn_port_off(connected_fndh_port)
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, None)
        expected_forcings[connected_fndh_port - 1] = "NONE"
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        fndh_simulator.turn_port_on(connected_fndh_port)
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, False)
        expected_forcings[connected_fndh_port - 1] = "OFF"
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert not fndh_simulator.turn_port_on(connected_fndh_port)
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, None)
        expected_forcings[connected_fndh_port - 1] = "NONE"
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

    def test_connected_fndh_port_power_on_off(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        connected_fndh_port: int,
    ) -> None:
        """
        Test that we can power on and off an FNDH port that has a smartbox connected.

        :param fndh_simulator: the FNDH simulator under test
        :param connected_fndh_port: the port number for an FNDH port
            that has a smartbox connected
        """
        assert fndh_simulator.ports_connected[connected_fndh_port - 1]
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]
        assert fndh_simulator.turn_port_on(connected_fndh_port)
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]
        assert fndh_simulator.turn_port_on(connected_fndh_port) is None
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]
        assert fndh_simulator.turn_port_off(connected_fndh_port)
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]
        assert fndh_simulator.turn_port_off(connected_fndh_port) is None
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

    def test_unconnected_fndh_port_power_on_off(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        unconnected_fndh_port: int,
    ) -> None:
        """
        Test that we can't power on an FNDH port that has a smartbox connected.

        :param fndh_simulator: the FNDH simulator under test
        :param unconnected_fndh_port: the port number for an FNDH port
            that doesn't have a smartbox connected.
        """
        assert not fndh_simulator.ports_connected[unconnected_fndh_port - 1]
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]
        assert not fndh_simulator.turn_port_on(unconnected_fndh_port)
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

    @pytest.mark.parametrize(
        ("attribute_name", "expected_value"),
        [
            (
                "modbus_register_map_revision",
                FndhSimulator.MODBUS_REGISTER_MAP_REVISION,
            ),
            ("pcb_revision", FndhSimulator.PCB_REVISION),
            ("sys_address", FndhSimulator.SYS_ADDRESS),
            ("cpu_id", FndhSimulator.CPU_ID),
            ("chip_id", FndhSimulator.CHIP_ID),
            ("firmware_version", FndhSimulator.DEFAULT_FIRMWARE_VERSION),
            ("uptime", FndhSimulator.DEFAULT_UPTIME),
            ("led_pattern", FndhSimulator.DEFAULT_LED_PATTERN),
        ],
    )
    def test_canned_attributes(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        attribute_name: str,
        expected_value: Any,
    ) -> None:
        """
        Test the values of canned attributes.

        :param fndh_simulator: the FNDH simulator under test
        :param attribute_name: name of the attribute to test
        :param expected_value: the expected value of the attribute
        """
        assert getattr(fndh_simulator, attribute_name) == expected_value

    def test_led_pattern(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test setting the LED pattern.

        :param fndh_simulator: the FNDH simulator under test
        """
        assert fndh_simulator.led_pattern == "OFF"
        assert fndh_simulator.set_led_pattern("SERVICE")
        assert fndh_simulator.led_pattern == "SERVICE"

    @pytest.mark.parametrize(
        ("sensor_name", "simulated_value", "expected_status"),
        [
            ("psu48v_voltage", 51.0, "ALARM"),
            ("psu48v_voltage", 50.0, "WARNING"),
            ("psu48v_voltage", 48.0, "OK"),
            ("psu48v_voltage", 46.0, "WARNING"),
            ("psu48v_voltage", 45.0, "ALARM"),
            ("psu48v_temperature", 65.0, "ALARM"),
            ("psu48v_temperature", 55.0, "WARNING"),
            ("psu48v_temperature", 25.0, "OK"),
            ("psu48v_temperature", 8.0, "WARNING"),
            ("psu48v_temperature", 4.0, "ALARM"),
            ("psu5v_voltage", 5.3, "ALARM"),
            ("psu5v_voltage", 5.2, "WARNING"),
            ("psu5v_voltage", 5.0, "OK"),
            ("psu5v_voltage", 4.8, "WARNING"),
            ("psu5v_voltage", 4.7, "ALARM"),
            ("psu5v_temperature", 65.0, "ALARM"),
            ("psu5v_temperature", 55.0, "WARNING"),
            ("psu5v_temperature", 25.0, "OK"),
            ("psu5v_temperature", 8.0, "WARNING"),
            ("psu5v_temperature", 4.0, "ALARM"),
            ("outside_temperature", 65.0, "ALARM"),
            ("outside_temperature", 55.0, "WARNING"),
            ("outside_temperature", 25.0, "OK"),
            ("outside_temperature", 8.0, "WARNING"),
            ("outside_temperature", 4.0, "ALARM"),
            ("pcb_temperature", 65.0, "ALARM"),
            ("pcb_temperature", 55.0, "WARNING"),
            ("pcb_temperature", 25.0, "OK"),
            ("pcb_temperature", 8.0, "WARNING"),
            ("pcb_temperature", 4.0, "ALARM"),
        ],
    )
    def test_sensors_and_status_transitions(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        sensor_name: str,
        simulated_value: float,
        expected_status: str,
    ) -> None:
        """
        Test the FNDH sensors and status.

        Check if status is initialized to OK, and changes if a given sensor
        value is out of bounds.

        :param fndh_simulator: the FNDH simulator under test.
        :param sensor_name: name of the sensor to test.
        :param simulated_value: value to set the sensor to.
        :param expected_status: the expected status of the sensor and FNDH.
        """
        assert fndh_simulator.status == "UNINITIALISED"
        fndh_simulator.status = "write to initialise"
        print(fndh_simulator._sensors_status)
        assert fndh_simulator.status == "OK"
        setattr(fndh_simulator, sensor_name, simulated_value)
        assert getattr(fndh_simulator, sensor_name) == simulated_value
        assert fndh_simulator.status == expected_status


class TestSmartboxSimulator:
    """Tests of the SmartboxSimulator."""

    @pytest.fixture(name="connected_smartbox_port")
    def connected_smartbox_port_fixture(
        self: TestSmartboxSimulator, smartbox_simulator: SmartboxSimulator
    ) -> int:
        """
        Return a smartbox simulator port that has an antenna connected to it.

        :param smartbox_simulator: the smartbox simulator for which a
            connected port is sought.

        :return: a smartbox port that has an antenna connected to it.
        """
        return smartbox_simulator.ports_connected.index(True) + 1

    @pytest.fixture(name="unconnected_smartbox_port")
    def unconnected_smartbox_port_fixture(
        self: TestSmartboxSimulator, smartbox_simulator: SmartboxSimulator
    ) -> int:
        """
        Return a smartbox simulator port that doesn't have an antenna connected to it.

        :param smartbox_simulator: the smartbox simulator for which an
            unconnected port is sought.

        :return: a smartbox port that doesn't have an antenna connected
            to it.
        """
        return smartbox_simulator.ports_connected.index(False) + 1

    def test_forcing_unconnected_smartbox_port(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        unconnected_smartbox_port: int,
    ) -> None:
        """
        Test that we can force an unconnected port on and off.

        :param smartbox_simulator: the smartbox simulator under test.
        :param unconnected_smartbox_port: a smartbox port that doesn't
            have an antenna connected to it
        """
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(unconnected_smartbox_port, True)
        assert smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(
            unconnected_smartbox_port, False
        )
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(unconnected_smartbox_port, None)
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]

    def test_forcing_connected_smartbox_port(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        connected_smartbox_port: int,
    ) -> None:
        """
        Test that we can force a connected port on and off.

        :param smartbox_simulator: the smartbox simulator under test.
        :param connected_smartbox_port: a smartbox port that has an
            antenna connected to it
        """
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, True)
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, None)
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        smartbox_simulator.turn_port_on(connected_smartbox_port)
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, False)
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, None)
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

    def test_connected_smartbox_port_power_on_off(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        connected_smartbox_port: int,
    ) -> None:
        """
        Test turning on a conncted smartbox port.

        :param smartbox_simulator: the smartbox simulator under test.
        :param connected_smartbox_port: a smartbox port that has an
            antenna connected to it
        """
        expected_when_online = [False] * SmartboxSimulator.NUMBER_OF_PORTS
        assert (
            smartbox_simulator.ports_desired_power_when_online == expected_when_online
        )
        expected_when_offline = [False] * SmartboxSimulator.NUMBER_OF_PORTS
        assert (
            smartbox_simulator.ports_desired_power_when_offline == expected_when_offline
        )
        assert smartbox_simulator.ports_connected[connected_smartbox_port - 1]
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.turn_port_on(connected_smartbox_port)
        expected_when_online[connected_smartbox_port - 1] = True
        expected_when_offline[connected_smartbox_port - 1] = True
        assert (
            smartbox_simulator.ports_desired_power_when_online == expected_when_online
        )
        assert (
            smartbox_simulator.ports_desired_power_when_offline == expected_when_offline
        )
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.turn_port_on(connected_smartbox_port, True) is None
        assert (
            smartbox_simulator.ports_desired_power_when_online == expected_when_online
        )
        assert (
            smartbox_simulator.ports_desired_power_when_offline == expected_when_offline
        )

        assert smartbox_simulator.turn_port_on(connected_smartbox_port, False)
        expected_when_offline[connected_smartbox_port - 1] = False
        assert (
            smartbox_simulator.ports_desired_power_when_online == expected_when_online
        )
        assert (
            smartbox_simulator.ports_desired_power_when_offline == expected_when_offline
        )
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.turn_port_off(connected_smartbox_port)
        expected_when_online[connected_smartbox_port - 1] = False
        expected_when_offline[connected_smartbox_port - 1] = False
        assert (
            smartbox_simulator.ports_desired_power_when_online == expected_when_online
        )
        assert (
            smartbox_simulator.ports_desired_power_when_offline == expected_when_offline
        )
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.turn_port_off(connected_smartbox_port) is None
        assert (
            smartbox_simulator.ports_desired_power_when_online == expected_when_online
        )
        assert (
            smartbox_simulator.ports_desired_power_when_offline == expected_when_offline
        )
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

    def test_unconnected_smartbox_port_power_on_off(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        unconnected_smartbox_port: int,
    ) -> None:
        """
        Test trying to turn on an unconnected port.

        :param smartbox_simulator: the smartbox simulator under test.
        :param unconnected_smartbox_port: a smartbox port that doesn't
            have an antenna connected to it
        """
        assert not smartbox_simulator.ports_connected[unconnected_smartbox_port - 1]
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert not smartbox_simulator.turn_port_on(unconnected_smartbox_port)
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]

    def test_port_breaker_trip(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        connected_smartbox_port: int,
    ) -> None:
        """
        Test smartbox port breaker tripping.

        :param smartbox_simulator: the smartbox simulator under test.
        :param connected_smartbox_port: a smartbox port that has an
            antenna connected to it
        """
        expected_tripped = [False] * SmartboxSimulator.NUMBER_OF_PORTS
        assert smartbox_simulator.port_breakers_tripped == expected_tripped

        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert smartbox_simulator.turn_port_on(connected_smartbox_port)
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.simulate_port_breaker_trip(connected_smartbox_port)
        expected_tripped[connected_smartbox_port - 1] = True
        assert smartbox_simulator.port_breakers_tripped == expected_tripped
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert (
            smartbox_simulator.simulate_port_breaker_trip(connected_smartbox_port)
            is None
        )
        assert smartbox_simulator.port_breakers_tripped == expected_tripped
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.reset_port_breaker(connected_smartbox_port)
        expected_tripped[connected_smartbox_port - 1] = False
        assert smartbox_simulator.port_breakers_tripped == expected_tripped
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        assert smartbox_simulator.reset_port_breaker(connected_smartbox_port) is None
        assert smartbox_simulator.port_breakers_tripped == expected_tripped
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

    def test_ports_current_draw(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test smartbox port current draw.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert smartbox_simulator.ports_current_draw == [
            SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW if port_connected else 0.0
            for port_connected in smartbox_simulator.ports_connected
        ]

    @pytest.mark.parametrize(
        ("attribute_name", "expected_value"),
        [
            (
                "modbus_register_map_revision",
                SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION,
            ),
            ("pcb_revision", SmartboxSimulator.PCB_REVISION),
            ("sys_address", SmartboxSimulator.SYS_ADDRESS),
            ("cpu_id", SmartboxSimulator.CPU_ID),
            ("chip_id", SmartboxSimulator.CHIP_ID),
            ("firmware_version", SmartboxSimulator.DEFAULT_FIRMWARE_VERSION),
            ("uptime", SmartboxSimulator.DEFAULT_UPTIME),
            ("led_pattern", SmartboxSimulator.DEFAULT_LED_PATTERN),
        ],
    )
    def test_canned_attributes(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        attribute_name: str,
        expected_value: Any,
    ) -> None:
        """
        Test the values of canned attributes.

        :param smartbox_simulator: the smartbox simulator under test.
        :param attribute_name: name of the attribute to test
        :param expected_value: the expected value of the attribute
        """
        assert getattr(smartbox_simulator, attribute_name) == expected_value

    def test_led_pattern(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test setting the smartbox LED service pattern.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert smartbox_simulator.led_pattern == "OFF"
        assert smartbox_simulator.set_led_pattern("SERVICE")
        assert smartbox_simulator.led_pattern == "SERVICE"
        assert smartbox_simulator.set_led_pattern("SERVICE") is None
        assert smartbox_simulator.led_pattern == "SERVICE"
        assert smartbox_simulator.set_led_pattern("OFF")
        assert smartbox_simulator.led_pattern == "OFF"

    @pytest.mark.parametrize(
        ("sensor_name", "simulated_value", "expected_status"),
        [
            ("input_voltage", 51.0, "ALARM"),
            ("input_voltage", 50.0, "WARNING"),
            ("input_voltage", 48.0, "OK"),
            ("input_voltage", 46.0, "WARNING"),
            ("input_voltage", 45.0, "ALARM"),
            ("power_supply_output_voltage", 5.3, "ALARM"),
            ("power_supply_output_voltage", 5.2, "WARNING"),
            ("power_supply_output_voltage", 5.0, "OK"),
            ("power_supply_output_voltage", 4.8, "WARNING"),
            ("power_supply_output_voltage", 4.7, "ALARM"),
            ("power_supply_temperature", 65.0, "ALARM"),
            ("power_supply_temperature", 55.0, "WARNING"),
            ("power_supply_temperature", 25.0, "OK"),
            ("power_supply_temperature", 8.0, "WARNING"),
            ("power_supply_temperature", 4.0, "ALARM"),
            ("outside_temperature", 65.0, "ALARM"),
            ("outside_temperature", 55.0, "WARNING"),
            ("outside_temperature", 25.0, "OK"),
            ("outside_temperature", 8.0, "WARNING"),
            ("outside_temperature", 4.0, "ALARM"),
            ("pcb_temperature", 65.0, "ALARM"),
            ("pcb_temperature", 55.0, "WARNING"),
            ("pcb_temperature", 25.0, "OK"),
            ("pcb_temperature", 8.0, "WARNING"),
            ("pcb_temperature", 4.0, "ALARM"),
        ],
    )
    def test_sensors_and_status_transitions(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        sensor_name: str,
        simulated_value: float,
        expected_status: str,
    ) -> None:
        """
        Test the smartbox sensors and status.

        Check if status is initialized to OK, and changes if a given sensor
        value is out of bounds.

        :param smartbox_simulator: the smartbox simulator under test.
        :param sensor_name: name of the sensor to test.
        :param simulated_value: value to set the sensor to.
        :param expected_status: the expected status of the sensor and smartbox.
        """
        assert smartbox_simulator.status == "UNINITIALISED"
        smartbox_simulator.status = "write to initialise"
        assert smartbox_simulator.status == "OK"
        setattr(smartbox_simulator, sensor_name, simulated_value)
        assert getattr(smartbox_simulator, sensor_name) == simulated_value
        assert smartbox_simulator.status == expected_status
