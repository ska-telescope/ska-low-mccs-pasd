# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus component manager."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union

import pytest

from ska_low_mccs_pasd.pasd_bus import PasdBusSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_json_api import (
    PasdBusJsonApi,
    PasdBusJsonApiClient,
)
from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import (
    FndhSimulator,
    SmartboxSimulator,
)


@pytest.fixture(name="fndh_config")
def fndh_config_fixture(pasd_config: dict[str, Any]) -> list[bool]:
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


@pytest.fixture(name="fndh_simulator")
def fndh_simulator_fixture(fndh_config: list[bool]) -> FndhSimulator:
    """
    Return an FNDH simulator instance.

    :param fndh_config: the FNDH configuration data used to configure
        the FNDH simulator instance.

    :return: a smartbox simulator.
    """
    simulator = FndhSimulator()
    simulator.configure(fndh_config)
    return simulator


@pytest.fixture(name="connected_fndh_port")
def connected_fndh_port_fixture(fndh_simulator: FndhSimulator) -> int:
    """
    Return an FNDH simulator port that has a smartbox connected to it.

    :param fndh_simulator: the FNDH simulator for which a connected port
        is sought.

    :return: an FNDH port that has a smartbox connected to it.
    """
    return fndh_simulator.are_ports_connected.index(True) + 1


@pytest.fixture(name="unconnected_fndh_port")
def unconnected_fndh_port_fixture(fndh_simulator: FndhSimulator) -> int:
    """
    Return an FNDH simulator port that doesn't have a smartbox connected to it.

    :param fndh_simulator: the FNDH simulator for which an unconnected
        port is sought.

    :return: an FNDH port that doesn't have a smartbox connected to it.
    """
    return fndh_simulator.are_ports_connected.index(False) + 1


class TestFndhSimulator:
    """Tests of the FndhSimulator."""

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
        assert not fndh_simulator.is_port_power_sensed(unconnected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, True)
        assert fndh_simulator.is_port_power_sensed(unconnected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, False)
        assert not fndh_simulator.is_port_power_sensed(unconnected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(unconnected_fndh_port, None)
        assert not fndh_simulator.is_port_power_sensed(unconnected_fndh_port)

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
        assert not fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, True)
        assert fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, None)
        assert not fndh_simulator.is_port_power_sensed(connected_fndh_port)
        fndh_simulator.turn_port_on(connected_fndh_port)
        assert fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, False)
        assert not fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.simulate_port_forcing(connected_fndh_port, None)
        assert fndh_simulator.is_port_power_sensed(connected_fndh_port)

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
        assert fndh_simulator.is_port_connected(connected_fndh_port)
        assert not fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.turn_port_on(connected_fndh_port)
        assert fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.turn_port_on(connected_fndh_port) is None
        assert fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.turn_port_off(connected_fndh_port)
        assert not fndh_simulator.is_port_power_sensed(connected_fndh_port)
        assert fndh_simulator.turn_port_off(connected_fndh_port) is None
        assert not fndh_simulator.is_port_power_sensed(connected_fndh_port)

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
        assert not fndh_simulator.is_port_connected(unconnected_fndh_port)
        assert not fndh_simulator.is_port_power_sensed(unconnected_fndh_port)
        assert not fndh_simulator.turn_port_on(unconnected_fndh_port)
        assert not fndh_simulator.is_port_power_sensed(unconnected_fndh_port)

    def test_psu48v_voltages(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test the FNDH 48V power supply voltages.

        :param fndh_simulator: the FNDH simulator under test
        """
        assert fndh_simulator.psu48v_voltages == FndhSimulator.DEFAULT_PSU48V_VOLTAGES

    def test_psu5v_voltage(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test the FNDH 5V power supply voltage.

        :param fndh_simulator: the FNDH simulator under test
        """
        assert fndh_simulator.psu5v_voltage == FndhSimulator.DEFAULT_PSU5V_VOLTAGE

    def test_psu48v_current(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test the FNDH 48V power supply current.

        :param fndh_simulator: the FNDH simulator under test
        """
        assert fndh_simulator.psu48v_current == FndhSimulator.DEFAULT_PSU48V_CURRENT

    @pytest.mark.parametrize(
        ("location", "temperature"),
        [
            ("psu48v", FndhSimulator.DEFAULT_PSU48V_TEMPERATURE),
            ("psu5v", FndhSimulator.DEFAULT_PSU5V_TEMPERATURE),
            ("pcb", FndhSimulator.DEFAULT_PCB_TEMPERATURE),
            ("outside", FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE),
        ],
    )
    def test_temperatures(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
        location: str,
        temperature: float,
    ) -> None:
        """
        Test a FNDH temperature property.

        :param fndh_simulator: the FNDH simulator under test
        :param location: location of the sensor
        :param temperature: expected temperature reading
        """
        assert getattr(fndh_simulator, f"{location}_temperature") == temperature

    def test_status(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test the FNDH status.

        :param fndh_simulator: the FNDH simulator under test
        """
        assert fndh_simulator.status == FndhSimulator.DEFAULT_STATUS

    def test_service_led_on(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test turning the FNDH service led on and off.

        :param fndh_simulator: the FNDH simulator under test
        """
        assert not fndh_simulator.service_led_on
        fndh_simulator.service_led_on = True
        assert fndh_simulator.service_led_on

    def test_get_info(
        self: TestFndhSimulator,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test the ``get_info`` method.

        :param fndh_simulator: the FNDH simulator under test
        """
        fndh_info = fndh_simulator.get_info()
        assert (
            fndh_info["modbus_register_map_revision_number"]
            == FndhSimulator.MODBUS_REGISTER_MAP_REVISION_NUMBER
        )
        assert fndh_info["pcb_revision_number"] == FndhSimulator.PCB_REVISION_NUMBER
        assert fndh_info["cpu_id"] == FndhSimulator.CPU_ID
        assert fndh_info["chip_id"] == FndhSimulator.CHIP_ID
        assert fndh_info["firmware_version"] == FndhSimulator.DEFAULT_FIRMWARE_VERSION
        assert fndh_info["uptime_integer"] == FndhSimulator.DEFAULT_UPTIME
        assert fndh_info["status"] == FndhSimulator.DEFAULT_STATUS
        assert fndh_info["led_status_pattern"] == FndhSimulator.DEFAULT_LED_PATTERN
        # Check that the read time is a valid timestamp
        _ = datetime.fromisoformat(fndh_info["read_time"])


class TestSmartboxSimulator:
    """Tests of the SmartboxSimulator."""

    @pytest.fixture(name="smartbox_under_test")
    def smartbox_under_test_fixture(self: TestSmartboxSimulator) -> int:
        """
        Return the id of the smartbox to be used in testing.

        :return: the id of the smartbox to be used in testing.
        """
        return 1

    @pytest.fixture(name="smartbox_config")
    def smartbox_config_fixture(
        self: TestSmartboxSimulator,
        pasd_config: dict[str, Any],
        smartbox_under_test: int,
    ) -> list[bool]:
        """
        Return smartbox configuration data, specifying which ports are connected.

        :param pasd_config: the overall PaSD configuration data from
            which the smartbox configuration data will be extracted.
        :param smartbox_under_test: id of the smartbox to be used in
            testing

        :return: a list of booleans indicating which ports are connected
        """
        is_port_connected = [False] * SmartboxSimulator.NUMBER_OF_PORTS
        for antenna_config in pasd_config["antennas"]:
            if antenna_config["smartbox_id"] == smartbox_under_test:
                is_port_connected[antenna_config["smartbox_port"] - 1] = True
        return list(is_port_connected)

    @pytest.fixture(name="smartbox_simulator")
    def smartbox_simulator_fixture(
        self: TestSmartboxSimulator, smartbox_config: list[bool]
    ) -> SmartboxSimulator:
        """
        Return a smartbox simulator instance.

        :param smartbox_config: the smartbox configuration data used to
            configure the smartbox simulator instance.

        :return: a smartbox simulator.
        """
        simulator = SmartboxSimulator()
        simulator.configure(smartbox_config)
        return simulator

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
        return smartbox_simulator.are_ports_connected.index(True) + 1

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
        return smartbox_simulator.are_ports_connected.index(False) + 1

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
        assert not smartbox_simulator.is_port_power_sensed(unconnected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(unconnected_smartbox_port, True)
        assert smartbox_simulator.is_port_power_sensed(unconnected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(
            unconnected_smartbox_port, False
        )
        assert not smartbox_simulator.is_port_power_sensed(unconnected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(unconnected_smartbox_port, None)
        assert not smartbox_simulator.is_port_power_sensed(unconnected_smartbox_port)

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
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, True)
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, None)
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        smartbox_simulator.turn_port_on(connected_smartbox_port)
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, False)
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.simulate_port_forcing(connected_smartbox_port, None)
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

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
        assert smartbox_simulator.is_port_connected(connected_smartbox_port)
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.turn_port_on(connected_smartbox_port)
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.turn_port_on(connected_smartbox_port) is None
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.turn_port_off(connected_smartbox_port)
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.turn_port_off(connected_smartbox_port) is None
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

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
        assert not smartbox_simulator.is_port_connected(unconnected_smartbox_port)
        assert not smartbox_simulator.is_port_power_sensed(unconnected_smartbox_port)
        assert not smartbox_simulator.turn_port_on(unconnected_smartbox_port)
        assert not smartbox_simulator.is_port_power_sensed(unconnected_smartbox_port)

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
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)
        assert smartbox_simulator.turn_port_on(connected_smartbox_port)
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

        assert smartbox_simulator.simulate_port_breaker_trip(connected_smartbox_port)
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

        assert (
            smartbox_simulator.simulate_port_breaker_trip(connected_smartbox_port)
            is None
        )
        assert not smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

        assert smartbox_simulator.reset_port_breaker(connected_smartbox_port)
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

        assert smartbox_simulator.reset_port_breaker(connected_smartbox_port) is None
        assert smartbox_simulator.is_port_power_sensed(connected_smartbox_port)

    def test_port_current_draw(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        connected_smartbox_port: int,
    ) -> None:
        """
        Test smartbox port current draw.

        :param smartbox_simulator: the smartbox simulator under test.
        :param connected_smartbox_port: a smartbox port that has an
            antenna connected to it
        """
        assert (
            smartbox_simulator.get_port_current_draw(connected_smartbox_port)
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW
        )

    def test_input_voltage(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test the input voltage.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert (
            smartbox_simulator.input_voltage == SmartboxSimulator.DEFAULT_INPUT_VOLTAGE
        )

    def test_power_supply_output_voltage(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test the smartbox power supply output voltage.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert (
            smartbox_simulator.power_supply_output_voltage
            == SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        )

    def test_status(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test the smartbox status.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert smartbox_simulator.status == SmartboxSimulator.DEFAULT_STATUS

    @pytest.mark.parametrize(
        ("location", "temperature"),
        [
            (
                "power_supply",
                SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE,
            ),
            ("outside", SmartboxSimulator.DEFAULT_OUTSIDE_TEMPERATURE),
            ("pcb", SmartboxSimulator.DEFAULT_PCB_TEMPERATURE),
        ],
    )
    def test_temperature(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
        location: str,
        temperature: float,
    ) -> None:
        """
        Test the smartbox power supply temperatures.

        :param smartbox_simulator: the smartbox simulator under test.
        :param location: name of the location of the sensor; one of
            "power_supply", "outside" or "pcb"
        :param temperature: expected temperature reading at the given
            location.
        """
        assert getattr(smartbox_simulator, f"{location}_temperature") == temperature

    def test_service_led_on(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test the FNDH service led.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        assert not smartbox_simulator.service_led_on
        smartbox_simulator.service_led_on = True
        assert smartbox_simulator.service_led_on

    def test_get_info(
        self: TestSmartboxSimulator,
        smartbox_simulator: SmartboxSimulator,
    ) -> None:
        """
        Test the ``get_info`` method.

        :param smartbox_simulator: the smartbox simulator under test.
        """
        smartbox_info = smartbox_simulator.get_info()
        assert (
            smartbox_info["modbus_register_map_revision_number"]
            == SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION_NUMBER
        )
        assert (
            smartbox_info["pcb_revision_number"]
            == SmartboxSimulator.PCB_REVISION_NUMBER
        )
        assert smartbox_info["cpu_id"] == SmartboxSimulator.CPU_ID
        assert smartbox_info["chip_id"] == SmartboxSimulator.CHIP_ID
        assert (
            smartbox_info["firmware_version"]
            == SmartboxSimulator.DEFAULT_FIRMWARE_VERSION
        )
        assert smartbox_info["uptime_integer"] == SmartboxSimulator.DEFAULT_UPTIME
        assert smartbox_info["status"] == SmartboxSimulator.DEFAULT_STATUS
        assert (
            smartbox_info["led_status_pattern"] == SmartboxSimulator.DEFAULT_LED_PATTERN
        )
        # Check that the read time is a valid timestamp
        _ = datetime.fromisoformat(smartbox_info["read_time"])


class TestPasdBusSimulator:  # pylint: disable=too-many-public-methods
    """
    Tests of commands common to the PaSDBus simulator and its component manager.

    Because the PaSD bus component manager passes commands down to the
    PaSD bus simulator, many commands are common. Here we test those
    common commands.
    """

    @pytest.fixture(name="pasd_bus_simulator_api", params=["direct", "indirect"])
    def pasd_bus_simulator_api(
        self: TestPasdBusSimulator,
        pasd_bus_simulator: PasdBusSimulator,
        request: pytest.FixtureRequest,
    ) -> Union[PasdBusSimulator, PasdBusJsonApiClient]:
        """
        Return API access to the PaSD bus simulator under test.

        This is parametrised to return both direct and indirect access.

        In the direct case, the simulator itself is returned.

        In the indirect case, an JSON API client is returned. The JSON
        API client is constructed to talk to a JSON API which talks to
        the simulator itself. Thus it appears as though we are talking
        directly to the simulator, but actually all our interactions
        are being serialised to JSON and then deserialised again.

        :param pasd_bus_simulator: the underlying simulator.
        :param request: A pytest object giving access to the requesting
            test context.

        :return: API access to the simulator under test.
        """
        if request.param == "direct":  # type: ignore[attr-defined]
            return pasd_bus_simulator
        return PasdBusJsonApiClient(PasdBusJsonApi(pasd_bus_simulator))

    def test_fndh_psu48v_voltages(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the FNDH 48V power supply voltages.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert (
            pasd_bus_simulator_api.fndh_psu48v_voltages
            == FndhSimulator.DEFAULT_PSU48V_VOLTAGES
        )

    def test_fndh_psu5v_voltage(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the FNDH 5V power supply voltage.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert (
            pasd_bus_simulator_api.fndh_psu5v_voltage
            == FndhSimulator.DEFAULT_PSU5V_VOLTAGE
        )

    def test_fndh_psu48v_current(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the FNDH 48V power supply current.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert (
            pasd_bus_simulator_api.fndh_psu48v_current
            == FndhSimulator.DEFAULT_PSU48V_CURRENT
        )

    @pytest.mark.parametrize(
        ("location", "temperature"),
        [
            ("psu48v", FndhSimulator.DEFAULT_PSU48V_TEMPERATURE),
            ("psu5v", FndhSimulator.DEFAULT_PSU5V_TEMPERATURE),
            ("pcb", FndhSimulator.DEFAULT_PCB_TEMPERATURE),
            ("outside", FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE),
        ],
    )
    def test_fndh_temperatures(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
        location: str,
        temperature: float,
    ) -> None:
        """
        Test a FNDH temperature property.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param location: location of the sensor
        :param temperature: expected temperature reading
        """
        assert (
            getattr(pasd_bus_simulator_api, f"fndh_{location}_temperature")
            == temperature
        )

    def test_fndh_status(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the FNDH status.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.fndh_status == FndhSimulator.DEFAULT_STATUS

    def test_fndh_service_led_on(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the FNDH service led.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert not pasd_bus_simulator_api.fndh_service_led_on

        pasd_bus_simulator_api.set_fndh_service_led_on(True)
        assert pasd_bus_simulator_api.fndh_service_led_on

    def test_fndh_ports_connected(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test which FNDH ports are connected.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        expected_smartbox_connected = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_config in pasd_config["smartboxes"]:
            expected_smartbox_connected[smartbox_config["fndh_port"] - 1] = True

        assert (
            pasd_bus_simulator_api.fndh_ports_connected == expected_smartbox_connected
        )

    def test_fndh_port_forcing(
        self: TestPasdBusSimulator,
        pasd_bus_simulator: PasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
        connected_fndh_port: int,
    ) -> None:
        """
        Test the FNDH locally forced power.

        :param pasd_bus_simulator: the underlying simulator.
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param connected_fndh_port: the port number for an FNDH port
            that has a smartbox connected
        """
        expected_forcings: list[Optional[bool]] = [None] * FndhSimulator.NUMBER_OF_PORTS
        assert pasd_bus_simulator_api.fndh_port_forcings == expected_forcings
        assert (
            pasd_bus_simulator_api.get_fndh_port_forcing(connected_fndh_port)
            == expected_forcings[connected_fndh_port - 1]
        )

        for forcing in [True, False, None]:
            pasd_bus_simulator.simulate_fndh_port_forcing(connected_fndh_port, forcing)
            expected_forcings[connected_fndh_port - 1] = forcing
            assert pasd_bus_simulator_api.fndh_port_forcings == expected_forcings
            assert (
                pasd_bus_simulator_api.get_fndh_port_forcing(connected_fndh_port)
                == forcing
            )

    def test_get_fndh_info(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the ``get_fndh_info`` method.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        fndh_info = pasd_bus_simulator_api.get_fndh_info()
        assert (
            fndh_info["modbus_register_map_revision_number"]
            == FndhSimulator.MODBUS_REGISTER_MAP_REVISION_NUMBER
        )
        assert fndh_info["pcb_revision_number"] == FndhSimulator.PCB_REVISION_NUMBER
        assert fndh_info["cpu_id"] == FndhSimulator.CPU_ID
        assert fndh_info["chip_id"] == FndhSimulator.CHIP_ID
        assert fndh_info["firmware_version"] == FndhSimulator.DEFAULT_FIRMWARE_VERSION
        assert fndh_info["uptime_integer"] == FndhSimulator.DEFAULT_UPTIME
        assert fndh_info["status"] == FndhSimulator.DEFAULT_STATUS
        assert fndh_info["led_status_pattern"] == FndhSimulator.DEFAULT_LED_PATTERN
        # Check that the read time is a valid timestamp
        _ = datetime.fromisoformat(fndh_info["read_time"])

    def test_smartbox_input_voltages(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox input voltages.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_input_voltages == [
            SmartboxSimulator.DEFAULT_INPUT_VOLTAGE
        ] * len(pasd_config["smartboxes"])

    def test_smartbox_power_supply_output_voltages(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox power supply output voltages.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_power_supply_output_voltages == [
            SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        ] * len(pasd_config["smartboxes"])

    def test_smartbox_statuses(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox statuses.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_statuses == [
            SmartboxSimulator.DEFAULT_STATUS
        ] * len(pasd_config["smartboxes"])

    def test_smartbox_power_supply_temperatures(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox power supply temperatures.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_power_supply_temperatures == [
            SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
        ] * len(pasd_config["smartboxes"])

    def test_smartbox_outside_temperatures(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox outside temperatures.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_outside_temperatures == [
            SmartboxSimulator.DEFAULT_OUTSIDE_TEMPERATURE
        ] * len(pasd_config["smartboxes"])

    def test_smartbox_pcb_temperatures(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox PCB temperatures.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_pcb_temperatures == [
            SmartboxSimulator.DEFAULT_PCB_TEMPERATURE
        ] * len(pasd_config["smartboxes"])

    def test_smartbox_fndh_ports(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the smartbox FNDH ports.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.smartbox_fndh_ports == [
            smartbox_config["fndh_port"]
            for smartbox_config in pasd_config["smartboxes"]
        ]

    @pytest.mark.parametrize("smartbox_id", [1])
    def test_smartbox_on_off(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
        smartbox_id: int,
    ) -> None:
        """
        Test turning an antenna on and off.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param smartbox_id: the smartbox number for the antenna to turn
            on and off
        """
        fndh_port = pasd_config["smartboxes"][smartbox_id - 1]["fndh_port"]

        expected_fndh_ports_power_sensed = [False] * FndhSimulator.NUMBER_OF_PORTS
        assert (
            pasd_bus_simulator_api.fndh_ports_power_sensed
            == expected_fndh_ports_power_sensed
        )
        assert pasd_bus_simulator_api.is_fndh_port_power_sensed(fndh_port) is False

        pasd_bus_simulator_api.turn_smartbox_on(smartbox_id)
        expected_fndh_ports_power_sensed[fndh_port - 1] = True

        assert (
            pasd_bus_simulator_api.fndh_ports_power_sensed
            == expected_fndh_ports_power_sensed
        )
        assert pasd_bus_simulator_api.is_fndh_port_power_sensed(fndh_port)

        pasd_bus_simulator_api.turn_smartbox_off(smartbox_id)
        expected_fndh_ports_power_sensed[fndh_port - 1] = False

        assert (
            pasd_bus_simulator_api.fndh_ports_power_sensed
            == expected_fndh_ports_power_sensed
        )
        assert pasd_bus_simulator_api.is_fndh_port_power_sensed(fndh_port) is False

    @pytest.mark.parametrize("smartbox_id", [1])
    def test_smartbox_service_leds_on(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
        smartbox_id: int,
    ) -> None:
        """
        Test the smartbox service LEDs.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param smartbox_id: the smartbox that we'll use to test turning
            the service LED on and off
        """
        expected_leds_on = [False] * len(pasd_config["smartboxes"])
        assert pasd_bus_simulator_api.smartbox_service_leds_on == expected_leds_on

        pasd_bus_simulator_api.set_smartbox_service_led_on(smartbox_id, True)
        expected_leds_on[smartbox_id - 1] = True
        assert pasd_bus_simulator_api.smartbox_service_leds_on == expected_leds_on

        pasd_bus_simulator_api.set_smartbox_service_led_on(smartbox_id, False)
        expected_leds_on[smartbox_id - 1] = False
        assert pasd_bus_simulator_api.smartbox_service_leds_on == expected_leds_on

    @pytest.mark.parametrize("smartbox_id", [1])
    def test_get_smartbox_info(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
        smartbox_id: int,
    ) -> None:
        """
        Test the ``get_smartbox_info`` method.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param smartbox_id: the smartbox number to use in the test
        """
        smartbox_info = pasd_bus_simulator_api.get_smartbox_info(smartbox_id)
        assert (
            smartbox_info["modbus_register_map_revision_number"]
            == SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION_NUMBER
        )
        assert (
            smartbox_info["pcb_revision_number"]
            == SmartboxSimulator.PCB_REVISION_NUMBER
        )
        assert smartbox_info["cpu_id"] == SmartboxSimulator.CPU_ID
        assert smartbox_info["chip_id"] == SmartboxSimulator.CHIP_ID
        assert (
            smartbox_info["firmware_version"]
            == SmartboxSimulator.DEFAULT_FIRMWARE_VERSION
        )
        assert smartbox_info["uptime_integer"] == SmartboxSimulator.DEFAULT_UPTIME
        assert smartbox_info["status"] == SmartboxSimulator.DEFAULT_STATUS
        assert (
            smartbox_info["led_status_pattern"] == SmartboxSimulator.DEFAULT_LED_PATTERN
        )
        # Check that the read time is a valid timestamp
        _ = datetime.fromisoformat(smartbox_info["read_time"])

    @pytest.mark.parametrize("smartbox_id", [1])
    def test_antennas_online(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
        smartbox_id: int,
    ) -> None:
        """
        Test the antennas online attribute.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param smartbox_id: id of the smartbox to turn off and on, in
            order to test correct behaviour of the antennas_online
            attribute.
        """
        expected_antennas_online = [False] * len(pasd_config["antennas"])
        assert pasd_bus_simulator_api.antennas_online == expected_antennas_online

        pasd_bus_simulator_api.turn_smartbox_on(smartbox_id)
        expected_antennas_online = [
            antenna["smartbox_id"] == smartbox_id for antenna in pasd_config["antennas"]
        ]
        assert pasd_bus_simulator_api.antennas_online == expected_antennas_online

    @pytest.mark.parametrize("antenna_id", [1])
    def test_antenna_forcings(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator: PasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
        antenna_id: int,
    ) -> None:
        """
        Test the antennas_forced attribute.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator: the underlying simulator.
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param antenna_id: id of the antenna to use to test forcing
            against
        """
        expected_antenna_forcings: list[Optional[bool]] = [None] * len(
            pasd_config["antennas"]
        )
        assert pasd_bus_simulator_api.antenna_forcings == expected_antenna_forcings
        assert pasd_bus_simulator_api.get_antenna_forcing(antenna_id) is None

        for forcing in [True, False, None]:
            pasd_bus_simulator.simulate_antenna_forcing(antenna_id, forcing)
            expected_antenna_forcings[antenna_id - 1] = forcing
            assert pasd_bus_simulator_api.antenna_forcings == expected_antenna_forcings
            assert pasd_bus_simulator_api.get_antenna_forcing(antenna_id) == forcing

    def test_antenna_currents(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the antenna currents.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.antenna_currents == [
            SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW
        ] * len(pasd_config["antennas"])

    @pytest.mark.parametrize("antenna_id", [1])
    def test_antenna_on_off(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
        antenna_id: int,
    ) -> None:
        """
        Test turning an antenna on and off.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param antenna_id: the antenna number for the antenna to
            turn on and off
        """
        smartbox_id = pasd_config["antennas"][antenna_id - 1]["smartbox_id"]
        smartbox_port = pasd_config["antennas"][antenna_id - 1]["smartbox_port"]
        fndh_port = pasd_config["smartboxes"][smartbox_id - 1]["fndh_port"]

        expected_antennas_on = [False] * len(pasd_config["antennas"])
        expected_smartbox_ports_on = [False] * SmartboxSimulator.NUMBER_OF_PORTS
        expected_smartboxes_on = [False] * len(pasd_config["smartboxes"])
        expected_fndh_ports_on = [False] * FndhSimulator.NUMBER_OF_PORTS

        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online == expected_antennas_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_on
        )
        assert (
            pasd_bus_simulator_api.get_smartbox_ports_power_sensed(smartbox_id)
            == expected_smartbox_ports_on
        )
        assert (
            pasd_bus_simulator_api.smartboxes_desired_power_online
            == expected_smartboxes_on
        )
        assert (
            pasd_bus_simulator_api.smartboxes_desired_power_offline
            == expected_smartboxes_on
        )
        assert pasd_bus_simulator_api.fndh_ports_power_sensed == expected_fndh_ports_on
        assert (
            pasd_bus_simulator_api.fndh_ports_desired_power_online
            == expected_fndh_ports_on
        )
        assert (
            pasd_bus_simulator_api.fndh_ports_desired_power_offline
            == expected_fndh_ports_on
        )

        assert pasd_bus_simulator_api.turn_antenna_on(antenna_id)

        expected_antennas_on[antenna_id - 1] = True
        expected_smartbox_ports_on[smartbox_port - 1] = True
        expected_smartboxes_on[smartbox_id - 1] = True
        expected_fndh_ports_on[fndh_port - 1] = True
        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online == expected_antennas_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_on
        )
        assert (
            pasd_bus_simulator_api.smartboxes_desired_power_online
            == expected_smartboxes_on
        )
        assert (
            pasd_bus_simulator_api.smartboxes_desired_power_offline
            == expected_smartboxes_on
        )
        assert (
            pasd_bus_simulator_api.get_smartbox_ports_power_sensed(smartbox_id)
            == expected_smartbox_ports_on
        )
        assert pasd_bus_simulator_api.fndh_ports_power_sensed == expected_fndh_ports_on
        assert (
            pasd_bus_simulator_api.fndh_ports_desired_power_online
            == expected_fndh_ports_on
        )
        assert (
            pasd_bus_simulator_api.fndh_ports_desired_power_offline
            == expected_fndh_ports_on
        )

        assert pasd_bus_simulator_api.turn_antenna_on(antenna_id) is None

        assert pasd_bus_simulator_api.turn_antenna_off(antenna_id)

        expected_antennas_on[antenna_id - 1] = False
        expected_smartbox_ports_on[smartbox_port - 1] = False
        expected_smartboxes_on[smartbox_id - 1] = False
        expected_fndh_ports_on[fndh_port - 1] = False
        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online == expected_antennas_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_on
        )
        assert (
            pasd_bus_simulator_api.get_smartbox_ports_power_sensed(smartbox_id)
            == expected_smartbox_ports_on
        )
        assert (
            pasd_bus_simulator_api.smartboxes_desired_power_online
            == expected_smartboxes_on
        )
        assert (
            pasd_bus_simulator_api.smartboxes_desired_power_offline
            == expected_smartboxes_on
        )
        assert pasd_bus_simulator_api.fndh_ports_power_sensed == expected_fndh_ports_on
        assert (
            pasd_bus_simulator_api.fndh_ports_desired_power_online
            == expected_fndh_ports_on
        )
        assert (
            pasd_bus_simulator_api.fndh_ports_desired_power_offline
            == expected_fndh_ports_on
        )

        assert pasd_bus_simulator_api.turn_antenna_off(antenna_id) is None

    @pytest.mark.parametrize("antenna_id", [1])
    def test_antenna_breaker_trip(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator: PasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
        antenna_id: int,
    ) -> None:
        """
        Test tripped antenna reporting functionality.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator: the underlying simulator.
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param antenna_id: the antenna number for which to simulate
            a breaker trip
        """
        expected_antennas_tripped = [False] * len(pasd_config["antennas"])
        expected_antennas_on = [False] * len(pasd_config["antennas"])
        expected_antennas_desired_on = [False] * len(pasd_config["antennas"])
        assert pasd_bus_simulator_api.antennas_tripped == expected_antennas_tripped
        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online
            == expected_antennas_desired_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_desired_on
        )

        pasd_bus_simulator_api.turn_antenna_on(antenna_id)
        expected_antennas_on[antenna_id - 1] = True
        expected_antennas_desired_on[antenna_id - 1] = True
        assert pasd_bus_simulator_api.antennas_tripped == expected_antennas_tripped
        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online
            == expected_antennas_desired_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_desired_on
        )

        assert pasd_bus_simulator_api.reset_antenna_breaker(antenna_id) is None

        pasd_bus_simulator.simulate_antenna_breaker_trip(antenna_id)
        expected_antennas_tripped[antenna_id - 1] = True
        expected_antennas_on[antenna_id - 1] = False
        assert pasd_bus_simulator_api.antennas_tripped == expected_antennas_tripped
        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online
            == expected_antennas_desired_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_desired_on
        )

        assert pasd_bus_simulator_api.reset_antenna_breaker(antenna_id)
        expected_antennas_tripped[antenna_id - 1] = False
        expected_antennas_on[antenna_id - 1] = True
        assert pasd_bus_simulator_api.antennas_tripped == expected_antennas_tripped
        assert pasd_bus_simulator_api.antennas_power_sensed == expected_antennas_on
        assert (
            pasd_bus_simulator_api.antennas_desired_power_online
            == expected_antennas_desired_on
        )
        assert (
            pasd_bus_simulator_api.antennas_desired_power_offline
            == expected_antennas_desired_on
        )

        assert pasd_bus_simulator_api.reset_antenna_breaker(antenna_id) is None

    @pytest.mark.parametrize("antenna_id", [1])
    def test_get_antenna_info(
        self: TestPasdBusSimulator,
        pasd_config: dict,
        pasd_bus_simulator_api: PasdBusSimulator,
        antenna_id: int,
    ) -> None:
        """
        Test the ``get_antenna_info`` method.

        :param pasd_config: the PaSD configuration
        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param antenna_id: the antenna number to use in the test
        """
        antenna_config = pasd_config["antennas"][antenna_id - 1]

        assert pasd_bus_simulator_api.get_antenna_info(antenna_id) == {
            "smartbox_id": antenna_config["smartbox_id"],
            "port_number": antenna_config["smartbox_port"],
            "tpm_number": antenna_config["tpm_id"],
            "tpm_input_number": antenna_config["tpm_input"],
        }

    @pytest.mark.parametrize("smartbox_id", [1])
    def test_update_status(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
        smartbox_id: int,
    ) -> None:
        """
        Test the ``update_status`` method.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        :param smartbox_id: number of a smartbox to use
        """
        smartbox_info = pasd_bus_simulator_api.get_smartbox_info(smartbox_id)
        fndh_info = pasd_bus_simulator_api.get_fndh_info()

        initial_smartbox_read_time = datetime.fromisoformat(smartbox_info["read_time"])
        initial_fndh_read_time = datetime.fromisoformat(fndh_info["read_time"])

        # check that the read time stays the same until we call update_status()
        smartbox_info = pasd_bus_simulator_api.get_smartbox_info(smartbox_id)
        fndh_info = pasd_bus_simulator_api.get_fndh_info()
        new_smartbox_read_time = datetime.fromisoformat(smartbox_info["read_time"])
        new_fndh_read_time = datetime.fromisoformat(fndh_info["read_time"])
        assert new_smartbox_read_time == initial_smartbox_read_time
        assert new_fndh_read_time == initial_fndh_read_time

        pasd_bus_simulator_api.update_status()

        # check that the read time has advanced now that we've called update_status()
        smartbox_info = pasd_bus_simulator_api.get_smartbox_info(smartbox_id)
        fndh_info = pasd_bus_simulator_api.get_fndh_info()
        new_smartbox_read_time = datetime.fromisoformat(smartbox_info["read_time"])
        new_fndh_read_time = datetime.fromisoformat(fndh_info["read_time"])
        assert new_smartbox_read_time > initial_smartbox_read_time
        assert new_fndh_read_time > initial_fndh_read_time

    def test_reload_database(
        self: TestPasdBusSimulator,
        pasd_bus_simulator_api: PasdBusSimulator,
    ) -> None:
        """
        Test the ``update_status`` method.

        :param pasd_bus_simulator_api: the PaSD Bus simulator under test.
        """
        assert pasd_bus_simulator_api.reload_database()
