# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS PaSD bus module."""


from __future__ import annotations

import logging
from typing import Iterator
from unittest.mock import patch

import pytest
import tango
from ska_control_model import LoggingLevel, SimulationMode
from ska_low_pasd_driver import (
    FnccSimulator,
    FndhSimulator,
    PasdBusSimulator,
    PasdHardwareSimulator,
    SmartboxSimulator,
)

from tests.harness import PasdTangoTestHarness, PasdTangoTestHarnessContext


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
        logging.getLogger(),
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


@pytest.fixture(name="fncc_simulator")
def fncc_simulator_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> FnccSimulator:
    """
    Return an FNCC simulator.

    :param pasd_bus_simulator: a real PaSD bus simulator whose FNCC
        simulator is to be returned.

    :return: an FNCC simulator
    """
    return pasd_bus_simulator.get_fncc()


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


@pytest.fixture(name="smartbox_attached_antennas")
def smartbox_attached_antennas_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> list[list[bool]]:
    """
    Return connected status for each antenna for each smartbox.

    :param pasd_bus_simulator: a PasdBusSimulator.
    :return: connected status for each antenna for each smartbox.
    """
    return pasd_bus_simulator.get_smartbox_ports_connected()


@pytest.fixture(name="smartbox_attached_antenna_names")
def smartbox_attached_antenna_names_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> list[list[str]]:
    """
    Return names of each antenna connected to each smartbox.

    :param pasd_bus_simulator: a PasdBusSimulator.
    :return: names of each antenna connected to each smartbox.
    """
    return pasd_bus_simulator.get_antenna_names_on_smartbox()


@pytest.fixture(name="pasd_hw_simulators")
def pasd_hw_simulators_fixture(
    pasd_bus_simulator: PasdBusSimulator,
    fndh_simulator: FndhSimulator,
    smartbox_attached_ports: list[int],
    off_smartbox_id: int,
) -> dict[int, PasdHardwareSimulator]:
    """
    Return the smartbox simulators.

    :param pasd_bus_simulator: a PaSD bus simulator whose smartbox
        simulators are to be returned.
    :param fndh_simulator: the FNDH simulator against which to test.
    :param smartbox_attached_ports: a list of FNDH port numbers each
        smartbox is connected to.
    :param off_smartbox_id: id of a smartbox to be turned off.
    :return: a dictionary of FNDH and smartbox simulators
    """
    fndh_simulator.initialize()
    for port_nr in smartbox_attached_ports:
        fndh_simulator.turn_port_on(port_nr)
    fndh_simulator.turn_port_off(smartbox_attached_ports[off_smartbox_id - 1])
    return pasd_bus_simulator.get_all_devices()


@pytest.fixture(name="smartbox_simulator")
def smartbox_simulator_fixture(
    pasd_hw_simulators: dict[int, PasdHardwareSimulator],
    on_smartbox_id: int,
) -> SmartboxSimulator:
    """
    Return a smartbox simulator for testing.

    :param pasd_hw_simulators:
        the FNDH and smartbox simulator backends that the TCP server will front.
    :param on_smartbox_id: id of the smartbox being addressed.

    :return: a smartbox simulator, wrapped in a mock.
    """
    return pasd_hw_simulators[on_smartbox_id]  # type: ignore


@pytest.fixture(name="smartbox_ids_to_test", scope="session")
def smartbox_ids_to_test_fixture() -> list[int]:
    """
    Return a list of smartbox IDs to use in a test.

    :return: a list of smartbox IDs to use in a test
    """
    return [1, 2]


@pytest.fixture(scope="session")
def last_smartbox_id(smartbox_ids_to_test: list[int]) -> int:
    """
    Return the ID of the last smartbox of the list which are tested.

    :param smartbox_ids_to_test: a list of the smarbox id's used in this test.
    :return: a list of smartbox IDs to use in a test
    """
    return max(smartbox_ids_to_test)


@pytest.fixture(name="on_smartbox_id", scope="session")
def on_smartbox_id_fixture(smartbox_ids_to_test: list[int]) -> int:
    """
    Return the id of a powered smartbox to be used in testing.

    :param smartbox_ids_to_test: a list of the smarbox id's used in this test.
    :return: the id of a powered smartbox to be used in testing.
    """
    return smartbox_ids_to_test[0]


@pytest.fixture(name="on_smartbox_attached_port")
def on_smartbox_attached_port_fixture(
    on_smartbox_id: int,
    smartbox_attached_ports: list[int],
) -> int:
    """
    Return the FNDH port the powered smartbox-under-test is attached to.

    :param on_smartbox_id: id of the smartbox-under-test.
    :param smartbox_attached_ports: a list of FNDH port numbers each smartbox
        is connected to.
    :return: the FNDH port the powered smartbox-under-test is attached to.
    """
    return smartbox_attached_ports[on_smartbox_id - 1]


@pytest.fixture(name="off_smartbox_id", scope="session")
def off_smartbox_id_fixture(smartbox_ids_to_test: list[int]) -> int:
    """
    Return the id of an off smartbox to be used in testing.

    :param smartbox_ids_to_test: a list of the smarbox id's used in this test.
    :return: the id of an off smartbox to be used in testing.
    """
    return smartbox_ids_to_test[1]


@pytest.fixture(name="off_smartbox_attached_port")
def off_smartbox_attached_port_fixture(
    off_smartbox_id: int,
    smartbox_attached_ports: list[int],
) -> int:
    """
    Return the FNDH port the off smartbox-under-test is attached to.

    :param off_smartbox_id: id of the smartbox-under-test.
    :param smartbox_attached_ports: a list of FNDH port numbers each smartbox
        is connected to.
    :return: the FNDH port the powered smartbox-under-test is attached to.
    """
    return smartbox_attached_ports[off_smartbox_id - 1]


# pylint: disable=too-many-positional-arguments, too-many-arguments
@pytest.fixture(name="test_context")
def test_context_fixture(
    pasd_hw_simulators: dict[int, PasdHardwareSimulator],
    smartbox_ids_to_test: list[int],
    smartbox_attached_ports: list[int],
    smartbox_attached_antennas: list[list[bool]],
    smartbox_attached_antenna_names: list[list[str]],
    station_label: str,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Fixture that returns a proxy to the PaSD bus Tango device under test.

    Here we use 1 pasd bus, 1 fndh, 1 field station, 1 fncc and 24 smartboxes.

    :param pasd_hw_simulators: the FNDH and smartbox simulators against which to test
    :param smartbox_ids_to_test: a list of the smartbox ids used in this test.
    :param smartbox_attached_ports: a list of FNDH port numbers each smartbox
        is connected to.
    :param smartbox_attached_antennas: smartbox port numbers each antenna is
        connected to for each smartbox.
    :param smartbox_attached_antenna_names: names of each antenna connected to
        each smartbox.
    :param station_label: The label of the station under test.
    :yield: a test context in which to run the integration tests.
    """
    with patch("ska_low_mccs_pasd.pasd_utils.Database") as db:
        # pylint: disable=too-many-return-statements
        def my_func(device_name: str, property_name: str) -> list:
            match property_name:
                case "inputvoltagethresholds":
                    return [50.0, 49.0, 45.0, 40.0]
                case "powersupplyoutputvoltagethresholds":
                    return [5.0, 4.9, 4.4, 4.0]
                case "powersupplytemperaturethresholds":
                    return [85.0, 70.0, 0.0, -5.0]
                case "pcbtemperaturethresholds":
                    return [85.0, 70.0, 0.0, -5.0]
                case "femambienttemperaturethresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femcasetemperature1thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femcasetemperature2thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femheatsinktemperature1thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femheatsinktemperature2thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femcurrenttripthresholds":
                    return [496, 496, 496, 496, 496, 496, 496, 496, 496, 496, 496, 496]
            return []

        db.return_value.get_device_attribute_property = my_func
        harness = PasdTangoTestHarness(station_label=station_label)
        # Set up pasdbus
        harness.set_pasd_bus_simulator(pasd_hw_simulators)
        harness.set_pasd_bus_device(
            station_label=station_label,
            polling_rate=0.1,
            device_polling_rate=0.1,
            available_smartboxes=smartbox_ids_to_test,
            logging_level=int(LoggingLevel.FATAL),
        )
        # Set up FNDH
        harness.set_fndh_device(
            int(LoggingLevel.ERROR), ports_with_smartbox=smartbox_attached_ports
        )
        # Set up fncc
        harness.set_fncc_device(int(LoggingLevel.ERROR))

        # set up smartboxes
        for smartbox_id in smartbox_ids_to_test:
            harness.add_smartbox_device(
                smartbox_id,
                int(LoggingLevel.ERROR),
                fndh_port=smartbox_attached_ports[smartbox_id - 1],
                ports_with_antennas=[
                    idx + 1
                    for idx, attached in enumerate(
                        smartbox_attached_antennas[smartbox_id - 1]
                    )
                    if attached
                ],
                antenna_names=smartbox_attached_antenna_names[smartbox_id - 1],
            )
        # Set up field station
        harness.set_field_station_device(
            station_label=station_label,
            smartbox_numbers=smartbox_ids_to_test,
            logging_level=int(LoggingLevel.ERROR),
        )

        with harness as context:
            yield context


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    test_context: PasdTangoTestHarnessContext,
) -> tango.DeviceProxy:
    """
    Fixture that returns the pasd_bus Tango device under test.

    :param test_context: context in which the integration tests will run.

    :yield: the pasd_bus Tango device under test.
    """
    pasd_bus_device = test_context.get_pasd_bus_device()
    pasd_bus_device.simulationMode = SimulationMode.TRUE
    yield pasd_bus_device


@pytest.fixture(name="fndh_device")
def fndh_device_fixture(
    test_context: PasdTangoTestHarnessContext,
) -> tango.DeviceProxy:
    """
    Fixture that returns the FNDH Tango device under test.

    :param test_context: context in which the integration tests will run.

    :yield: the FNDH Tango device under test.
    """
    yield test_context.get_fndh_device()


@pytest.fixture(name="fncc_device")
def fncc_device_fixture(
    test_context: PasdTangoTestHarnessContext,
) -> tango.DeviceProxy:
    """
    Fixture that returns the FNCC Tango device under test.

    :param test_context: context in which the integration tests will run.

    :yield: the FNCC Tango device under test.
    """
    yield test_context.get_fncc_device()


@pytest.fixture(name="field_station_device")
def field_station_device_fixture(
    test_context: PasdTangoTestHarnessContext,
) -> tango.DeviceProxy:
    """
    Fixture that returns the field station Tango device under test.

    :param test_context: context in which the integration tests will run.

    :yield: the FNDH Tango device under test.
    """
    yield test_context.get_field_station_device()


@pytest.fixture(name="on_smartbox_device")
def on_smartbox_device_fixture(
    test_context: PasdTangoTestHarnessContext,
    on_smartbox_id: int,
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns a smartbox Tango device.

    :param test_context: context in which the integration tests will run.
    :param on_smartbox_id: number of the smartbox under test

    :return: the smartbox Tango device.
    """
    return test_context.get_smartbox_device(on_smartbox_id)


@pytest.fixture(name="off_smartbox_device")
def off_smartbox_device_fixture(
    test_context: PasdTangoTestHarnessContext,
    off_smartbox_id: int,
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns a smartbox Tango device.

    :param test_context: context in which the integration tests will run.
    :param off_smartbox_id: the smartbox of interest.

    :return: the smartbox Tango device.
    """
    return test_context.get_smartbox_device(off_smartbox_id)


@pytest.fixture(name="smartbox_proxys")
def smartbox_proxys_fixture(
    test_context: PasdTangoTestHarnessContext,
    smartbox_ids_to_test: list[int],
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns a list of smartbox Tango devices.

    :param test_context: context in which the integration tests will run.
    :param smartbox_ids_to_test: a list of the smarbox id's used in this test.
    :return: the list of smartbox Tango devices.
    """
    smartbox_devices = []
    for smartbox_id in smartbox_ids_to_test:
        smartbox_devices.append(test_context.get_smartbox_device(smartbox_id))
    return smartbox_devices
