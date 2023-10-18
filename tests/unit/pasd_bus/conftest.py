# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS PaSD bus module."""


from __future__ import annotations

import functools
import logging
import unittest.mock

import pytest
import yaml

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusSimulator,
    SmartboxSimulator,
)


@pytest.fixture(name="station_label")
def station_label_fixture() -> str:
    """
    Return the name of the station whose configuration will be used in testing.

    :return: the name of the station whose configuration will be used in
        testing.
    """
    return "ci-1"


@pytest.fixture(name="pasd_config")
def pasd_config_fixture(pasd_config_path: str) -> dict:
    """
    Return the PaSD config that the pasd bus device uses.

    :param pasd_config_path: path to the PaSD configuration file

    :return: the PaSD config that the PaSD bus object under test uses.
    """
    with open(pasd_config_path, "r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


@pytest.fixture(name="pasd_bus_simulator")
def pasd_bus_simulator_fixture(
    pasd_config_path: str, station_label: str
) -> PasdBusSimulator:
    """
    Fixture that returns a PaSD bus simulator.

    :param pasd_config_path: path to the PaSD configuration file
    :param station_label: the name of the station whose PaSD bus we are
        simulating.

    :return: a PaSD bus simulator
    """
    return PasdBusSimulator(
        pasd_config_path,
        station_label,
        logging.DEBUG,
        smartboxes_depend_on_attached_ports=True,
    )


@pytest.fixture(name="fndh_simulator")
def fndh_simulator_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> FndhSimulator:
    """
    Return an FNDH simulator.

    :param pasd_bus_simulator: a real PaSD bus simulator whose FNDH
        simulator is to be returned.

    :return: an FNDH simulator
    """
    return pasd_bus_simulator.get_fndh()


@pytest.fixture(name="mock_fndh_simulator")
def mock_fndh_simulator_fixture(
    fndh_simulator: PasdBusSimulator,
) -> unittest.mock.Mock:
    """
    Return a mock FNDH simulator.

    The returned mock wraps a real simulator instance, so it will behave
    like a real one, but we can access it as a mock too, for example
    assert calls.

    :param fndh_simulator: an FNDH simulator to be wrapped in a mock.

    :return: a mock FNDH simulator
    """
    mock_simulator = unittest.mock.Mock(wraps=fndh_simulator)

    # "wraps" doesn't handle properties -- we have to add them manually
    for property_name in [
        "port_forcings",
        "ports_desired_power_when_online",
        "ports_desired_power_when_offline",
        "ports_power_sensed",
        "led_pattern",
        "sys_address",
        "psu48v_voltages",
        "psu48v_current",
        "psu48v_temperatures",
        "panel_temperature",
        "fncb_temperature",
        "fncb_humidity",
        "comms_gateway_temperature",
        "power_module_temperature",
        "outside_temperature",
        "internal_ambient_temperature",
        "psu48v_voltage_1_thresholds",
        "psu48v_voltage_2_thresholds",
        "psu48v_current_thresholds",
        "psu48v_temperature_1_thresholds",
        "psu48v_temperature_2_thresholds",
        "panel_temperature_thresholds",
        "fncb_temperature_thresholds",
        "fncb_humidity_thresholds",
        "comms_gateway_temperature_thresholds",
        "power_module_temperature_thresholds",
        "outside_temperature_thresholds",
        "internal_ambient_temperature_thresholds",
        "warning_flags",
        "alarm_flags",
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
        "uptime",
        "status",
    ]:

        def side_effect(sim, prop, val=None):
            if val:
                setattr(sim, prop, val)
            else:
                return getattr(sim, prop)

        side_effect_partial = functools.partial(
            side_effect, fndh_simulator, property_name
        )
        setattr(
            type(mock_simulator),
            property_name,
            unittest.mock.PropertyMock(side_effect=side_effect_partial),
        )

    return mock_simulator


@pytest.fixture(name="smartbox_attached_ports")
def smartbox_attached_ports_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> list[int]:
    """
    Return a list of FNDH port numbers each smartbox is connected to.

    :param pasd_bus_simulator: a PasdBusSimulator.
    :return: a list of FNDH port numbers each smartbox is connected to.
    """
    return pasd_bus_simulator.get_smartbox_attached_ports()


@pytest.fixture(name="smartbox_simulators")
def smartbox_simulators_fixture(
    pasd_bus_simulator: PasdBusSimulator,
    fndh_simulator: FndhSimulator,
    smartbox_attached_ports: list[int],
) -> dict[int, SmartboxSimulator]:
    """
    Return the smartbox simulators.

    :param pasd_bus_simulator: a PaSD bus simulator whose smartbox
        simulators are to be returned.
    :param fndh_simulator: FNDH simulator the smartboxes are connected to.
    :param smartbox_attached_ports: a list of FNDH port numbers each smartbox
            is connected to.
    :return: a dictionary of smartbox simulators
    """
    fndh_simulator.initialize()
    for port_nr in smartbox_attached_ports:
        fndh_simulator.turn_port_on(port_nr)
    return pasd_bus_simulator.get_smartboxes()


@pytest.fixture(name="mock_smartbox_simulators")
def mock_smartbox_simulators_fixture(
    smartbox_simulators: dict[int, SmartboxSimulator],
) -> dict[int, unittest.mock.Mock]:
    """
    Return the mock smartbox simulators.

    Each mock wraps a real simulator instance,
    so it will behave like a real one,
    but we can access it as a mock too, for example assert calls.

    :param smartbox_simulators:
        the smartbox simulator backends that the TCP server will front.

    :return: a sequence of mock smartbox simulators
    """
    mock_simulators: dict[int, unittest.mock.Mock] = {}

    for smartbox_id, smartbox_simulator in smartbox_simulators.items():
        mock_simulator = unittest.mock.Mock(wraps=smartbox_simulator)

        # "wraps" doesn't handle properties -- we have to add them manually
        property_name: str
        for property_name in [
            "modbus_register_map_revision",
            "pcb_revision",
            "cpu_id",
            "chip_id",
            "firmware_version",
            "uptime",
            "sys_address",
            "input_voltage",
            "power_supply_output_voltage",
            "power_supply_temperature",
            "pcb_temperature",
            "fem_ambient_temperature",
            "status",
            "led_pattern",
            "fem_case_temperatures",
            "fem_heatsink_temperatures",
            "input_voltage_thresholds",
            "power_supply_output_voltage_thresholds",
            "power_supply_temperature_thresholds",
            "pcb_temperature_thresholds",
            "fem_ambient_temperature_thresholds",
            "fem_case_temperature_1_thresholds",
            "fem_case_temperature_2_thresholds",
            "fem_heatsink_temperature_1_thresholds",
            "fem_heatsink_temperature_2_thresholds",
            "warning_flags",
            "alarm_flags",
            "fem1_current_trip_threshold",
            "fem2_current_trip_threshold",
            "fem3_current_trip_threshold",
            "fem4_current_trip_threshold",
            "fem5_current_trip_threshold",
            "fem6_current_trip_threshold",
            "fem7_current_trip_threshold",
            "fem8_current_trip_threshold",
            "fem9_current_trip_threshold",
            "fem10_current_trip_threshold",
            "fem11_current_trip_threshold",
            "fem12_current_trip_threshold",
            "ports_connected",
            "port_forcings",
            "port_breakers_tripped",
            "ports_desired_power_when_online",
            "ports_desired_power_when_offline",
            "ports_power_sensed",
            "ports_current_draw",
        ]:

            def side_effect(sim, prop, val=None):
                if val:
                    setattr(sim, prop, val)
                else:
                    return getattr(sim, prop)

            side_effect_partial = functools.partial(
                side_effect, smartbox_simulator, property_name
            )
            setattr(
                type(mock_simulator),
                property_name,
                unittest.mock.PropertyMock(side_effect=side_effect_partial),
            )

        mock_simulators[smartbox_id] = mock_simulator

    return mock_simulators


@pytest.fixture(name="smartbox_id")
def smartbox_id_fixture() -> int:
    """
    Return the id of the smartbox to be used in testing.

    :return: the id of the smartbox to be used in testing.
    """
    return 1


@pytest.fixture(name="smartbox_simulator")
def smartbox_simulator_fixture(
    smartbox_simulators: dict[int, SmartboxSimulator],
    smartbox_id: int,
) -> SmartboxSimulator:
    """
    Return a smartbox simulator for testing.

    :param smartbox_simulators:
        the smartbox simulator backends that the TCP server will front.
    :param smartbox_id: id of the smartbox being addressed.

    :return: a smartbox simulator, wrapped in a mock.
    """
    return smartbox_simulators[smartbox_id]


@pytest.fixture(name="mock_smartbox_simulator")
def mock_smartbox_simulator(
    mock_smartbox_simulators: list[unittest.mock.Mock],
    smartbox_id: int,
) -> unittest.mock.Mock:
    """
    Return a mock smartbox simulator.

    That is, a smartbox simulator, wrapped in a mock so that we can
    assert on calls to it.

    :param mock_smartbox_simulators:
        the smartbox simulator backends that the TCP server will front,
        each wrapped with a mock so that we can assert calls.
    :param smartbox_id: id of the smartbox being addressed.

    :return: a smartbox simulator, wrapped in a mock.
    """
    return mock_smartbox_simulators[smartbox_id - 1]
