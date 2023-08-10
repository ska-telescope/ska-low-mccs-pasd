# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus component manager."""
from __future__ import annotations

from typing import Any, Sequence

import pytest

from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import (
    FndhSimulator,
    SmartboxSimulator,
)


# pylint: disable=too-few-public-methods
class TestPasdBusSimulator:
    """Tests of the combined PasdBusSimulator."""

    @pytest.mark.xfail(reason="uptime currently must be a static value for tango mocks")
    def test_uptimes(
        self: TestPasdBusSimulator,
        fndh_simulator: FndhSimulator,
        smartbox_simulators: Sequence[SmartboxSimulator],
    ) -> None:
        """
        Test the uptimes of a PaSD bus simulator.

        Test that the uptime is tracked and differ between simulators according
            to the order of configuration.

        :param fndh_simulator: the FNDH simulator under test
        :param smartbox_simulators: list of smartbox simulators under test
        """
        fndh_uptime = fndh_simulator.uptime
        assert fndh_uptime > 0
        previous_smartbox_uptime = 10000
        for smartbox_simulator in smartbox_simulators:
            assert smartbox_simulator.uptime > 0
            assert fndh_uptime > smartbox_simulator.uptime
            assert smartbox_simulator.uptime < previous_smartbox_uptime
            previous_smartbox_uptime = smartbox_simulator.uptime


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
        assert fndh_simulator.initialize()
        assert fndh_simulator.status == "OK"

        expected_forcings: list[str] = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        fndh_simulator.fncb_temperature = 10000
        assert fndh_simulator.status == "ALARM"
        assert fndh_simulator.turn_port_on(unconnected_fndh_port)
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]
        assert all(fndh_simulator.simulate_port_forcing(True))
        expected_forcings = ["ON"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert all(
            result is None for result in fndh_simulator.simulate_port_forcing(True)
        )
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert all(fndh_simulator.simulate_port_forcing(False))
        expected_forcings = ["OFF"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert all(
            result is None for result in fndh_simulator.simulate_port_forcing(False)
        )
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert all(fndh_simulator.simulate_port_forcing(None))
        expected_forcings = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

        assert all(
            result is None for result in fndh_simulator.simulate_port_forcing(None)
        )
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
        assert fndh_simulator.initialize()
        assert fndh_simulator.status == "OK"

        expected_forcings: list[str] = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        fndh_simulator.fncb_temperature = 10000
        assert fndh_simulator.status == "ALARM"
        assert fndh_simulator.turn_port_on(connected_fndh_port)
        assert all(fndh_simulator.simulate_port_forcing(True))
        expected_forcings = ["ON"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert fndh_simulator.turn_port_off(connected_fndh_port)
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert all(fndh_simulator.simulate_port_forcing(None))
        expected_forcings = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        fndh_simulator.fncb_temperature = fndh_simulator.DEFAULT_FNCB_TEMPERATURE
        assert fndh_simulator.initialize()
        assert fndh_simulator.status == "OK"
        assert fndh_simulator.turn_port_on(connected_fndh_port)
        assert fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert all(fndh_simulator.simulate_port_forcing(False))
        expected_forcings = ["OFF"] * FndhSimulator.NUMBER_OF_PORTS
        assert fndh_simulator.port_forcings == expected_forcings
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert fndh_simulator.turn_port_on(connected_fndh_port) is None
        assert not fndh_simulator.ports_power_sensed[connected_fndh_port - 1]

        assert all(fndh_simulator.simulate_port_forcing(None))
        expected_forcings = ["NONE"] * FndhSimulator.NUMBER_OF_PORTS
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
        assert fndh_simulator.initialize()
        assert fndh_simulator.status == "OK"
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
        Test that we can power on an FNDH port that is unconnected.

        :param fndh_simulator: the FNDH simulator under test
        :param unconnected_fndh_port: the port number for an FNDH port
            that doesn't have a smartbox connected.
        """
        assert fndh_simulator.initialize()
        assert not fndh_simulator.ports_connected[unconnected_fndh_port - 1]
        assert not fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]
        assert fndh_simulator.turn_port_on(unconnected_fndh_port)
        assert fndh_simulator.ports_power_sensed[unconnected_fndh_port - 1]

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
            ("psu48v_voltages", [5300, 4800], "ALARM"),
            ("psu48v_voltages", [4800, 5100], "WARNING"),
            ("psu48v_voltages", [4800, 4800], "OK"),
            ("psu48v_voltages", [4400, 4800], "WARNING"),
            ("psu48v_voltages", [4800, 3900], "ALARM"),
            ("psu48v_temperatures", [10100, 6000], "ALARM"),
            ("psu48v_temperatures", [6000, 8600], "WARNING"),
            ("psu48v_temperatures", [6000, 6000], "OK"),
            ("psu48v_temperatures", [-100, 6000], "WARNING"),
            ("psu48v_temperatures", [6000, -600], "ALARM"),
            ("panel_temperature", 9000, "ALARM"),
            ("panel_temperature", 7500, "WARNING"),
            ("panel_temperature", 5000, "OK"),
            ("panel_temperature", -100, "WARNING"),
            ("panel_temperature", -600, "ALARM"),
            ("fncb_temperature", 9000, "ALARM"),
            ("fncb_temperature", 7500, "WARNING"),
            ("fncb_temperature", 5000, "OK"),
            ("fncb_temperature", -100, "WARNING"),
            ("fncb_temperature", -600, "ALARM"),
            ("fncb_humidity", 9000, "ALARM"),
            ("fncb_humidity", 7500, "WARNING"),
            ("fncb_humidity", 5000, "OK"),
            ("fncb_humidity", 500, "WARNING"),
            ("fncb_humidity", -100, "ALARM"),
            ("comms_gateway_temperature", 9000, "ALARM"),
            ("comms_gateway_temperature", 7500, "WARNING"),
            ("comms_gateway_temperature", 5000, "OK"),
            ("comms_gateway_temperature", -100, "WARNING"),
            ("comms_gateway_temperature", -600, "ALARM"),
            ("power_module_temperature", 9000, "ALARM"),
            ("power_module_temperature", 7500, "WARNING"),
            ("power_module_temperature", 5000, "OK"),
            ("power_module_temperature", -100, "WARNING"),
            ("power_module_temperature", -600, "ALARM"),
            ("outside_temperature", 9000, "ALARM"),
            ("outside_temperature", 7500, "WARNING"),
            ("outside_temperature", 5000, "OK"),
            ("outside_temperature", -100, "WARNING"),
            ("outside_temperature", -600, "ALARM"),
            ("internal_ambient_temperature", 9000, "ALARM"),
            ("internal_ambient_temperature", 7500, "WARNING"),
            ("internal_ambient_temperature", 5000, "OK"),
            ("internal_ambient_temperature", -100, "WARNING"),
            ("internal_ambient_temperature", -600, "ALARM"),
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
        assert fndh_simulator.status == FndhSimulator.DEFAULT_STATUS
        assert fndh_simulator.initialize()
        assert fndh_simulator.status == "OK"
        setattr(fndh_simulator, sensor_name, simulated_value)
        assert getattr(fndh_simulator, sensor_name) == simulated_value
        assert fndh_simulator.status == expected_status
        default_value = getattr(fndh_simulator, "DEFAULT_" + sensor_name.upper())
        setattr(fndh_simulator, sensor_name, default_value)
        if expected_status == "ALARM":
            assert fndh_simulator.status == "RECOVERY"
            setattr(fndh_simulator, sensor_name, simulated_value)
            assert fndh_simulator.status == expected_status
            assert fndh_simulator.initialize() is False
            setattr(fndh_simulator, sensor_name, default_value)
            assert fndh_simulator.status == "RECOVERY"
            assert fndh_simulator.initialize()
        assert fndh_simulator.status == "OK"


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
        assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"
        assert smartbox_simulator.turn_port_on(unconnected_smartbox_port)

        smartbox_simulator.power_supply_temperature = 10000
        assert smartbox_simulator.status == "ALARM"
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(True))
        assert smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(False))
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(None))
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
        assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"
        assert smartbox_simulator.turn_port_on(connected_smartbox_port)

        smartbox_simulator.power_supply_temperature = 10000
        assert smartbox_simulator.status == "ALARM"
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(True))
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(None))
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]

        smartbox_simulator.power_supply_temperature = (
            smartbox_simulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
        )
        assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"
        assert smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(False))
        assert not smartbox_simulator.ports_power_sensed[connected_smartbox_port - 1]
        assert all(smartbox_simulator.simulate_port_forcing(None))
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
        assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"

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
        assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"
        assert not smartbox_simulator.ports_connected[unconnected_smartbox_port - 1]
        assert not smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]
        assert smartbox_simulator.turn_port_on(unconnected_smartbox_port)
        assert smartbox_simulator.ports_power_sensed[unconnected_smartbox_port - 1]

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
        assert smartbox_simulator.initialize()

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
            SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW if port_connected else 0
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
            ("sys_address", SmartboxSimulator.DEFAULT_SYS_ADDRESS),
            ("cpu_id", SmartboxSimulator.CPU_ID),
            ("chip_id", SmartboxSimulator.CHIP_ID),
            ("firmware_version", SmartboxSimulator.DEFAULT_FIRMWARE_VERSION),
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

    def test_sys_address(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test setting the smartbox system address.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert smartbox_simulator.sys_address == smartbox_simulator.DEFAULT_SYS_ADDRESS
        assert smartbox_simulator.set_sys_address(2)
        assert smartbox_simulator.sys_address == 2
        assert smartbox_simulator.set_sys_address(2) is None
        assert smartbox_simulator.sys_address == 2
        assert smartbox_simulator.set_sys_address(100) is False
        assert smartbox_simulator.sys_address == 2
        assert smartbox_simulator.set_sys_address(0) is False
        assert smartbox_simulator.sys_address == 2

    @pytest.mark.parametrize(
        ("sensor_name", "simulated_value", "expected_status"),
        [
            ("input_voltage", 5100, "ALARM"),
            ("input_voltage", 4950, "WARNING"),
            ("input_voltage", 4800, "OK"),
            ("input_voltage", 4400, "WARNING"),
            ("input_voltage", 3900, "ALARM"),
            ("power_supply_output_voltage", 510, "ALARM"),
            ("power_supply_output_voltage", 490, "WARNING"),
            ("power_supply_output_voltage", 480, "OK"),
            ("power_supply_output_voltage", 430, "WARNING"),
            ("power_supply_output_voltage", 390, "ALARM"),
            ("power_supply_temperature", 9000, "ALARM"),
            ("power_supply_temperature", 7500, "WARNING"),
            ("power_supply_temperature", 5000, "OK"),
            ("power_supply_temperature", -100, "WARNING"),
            ("power_supply_temperature", -600, "ALARM"),
            ("pcb_temperature", 9000, "ALARM"),
            ("pcb_temperature", 7500, "WARNING"),
            ("pcb_temperature", 5000, "OK"),
            ("pcb_temperature", -100, "WARNING"),
            ("pcb_temperature", -600, "ALARM"),
            ("fem_ambient_temperature", 6100, "ALARM"),
            ("fem_ambient_temperature", 4600, "WARNING"),
            ("fem_ambient_temperature", 3000, "OK"),
            ("fem_ambient_temperature", -100, "WARNING"),
            ("fem_ambient_temperature", -600, "ALARM"),
            ("fem_case_temperatures", [6100, 3000], "ALARM"),
            ("fem_case_temperatures", [3000, 4600], "WARNING"),
            ("fem_case_temperatures", [3000, 3000], "OK"),
            ("fem_case_temperatures", [-100, 3000], "WARNING"),
            ("fem_case_temperatures", [3000, -600], "ALARM"),
            ("fem_heatsink_temperatures", [6100, 3000], "ALARM"),
            ("fem_heatsink_temperatures", [3000, 4600], "WARNING"),
            ("fem_heatsink_temperatures", [3000, 3000], "OK"),
            ("fem_heatsink_temperatures", [-100, 3000], "WARNING"),
            ("fem_heatsink_temperatures", [3000, -600], "ALARM"),
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
        assert smartbox_simulator.status == SmartboxSimulator.DEFAULT_STATUS
        assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"
        setattr(smartbox_simulator, sensor_name, simulated_value)
        assert getattr(smartbox_simulator, sensor_name) == simulated_value
        assert smartbox_simulator.status == expected_status
        default_value = getattr(smartbox_simulator, "DEFAULT_" + sensor_name.upper())
        setattr(smartbox_simulator, sensor_name, default_value)
        if expected_status == "ALARM":
            assert smartbox_simulator.status == "RECOVERY"
            setattr(smartbox_simulator, sensor_name, simulated_value)
            assert smartbox_simulator.status == expected_status
            assert smartbox_simulator.initialize() is False
            setattr(smartbox_simulator, sensor_name, default_value)
            assert smartbox_simulator.status == "RECOVERY"
            assert smartbox_simulator.initialize()
        assert smartbox_simulator.status == "OK"
