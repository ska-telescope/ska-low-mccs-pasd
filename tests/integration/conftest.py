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
import unittest.mock
from typing import Any, Iterator

import pytest
import tango

from ska_low_mccs_pasd.pasd_bus import PasdBusSimulator, PasdHardwareSimulator
from ska_low_mccs_pasd.pasd_data import PasdData
from tests.harness import PasdTangoTestHarness, PasdTangoTestHarnessContext


@pytest.fixture(name="station_label")
def station_label_fixture() -> str:
    """
    Return the name of the station whose configuration will be used in testing.

    :return: the name of the station whose configuration will be used in
        testing.
    """
    return "ci-1"


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
) -> PasdHardwareSimulator:
    """
    Return an FNDH simulator.

    :param pasd_bus_simulator: a real PaSD bus simulator whose FNDH
        simulator is to be returned.

    :return: an FNDH simulator
    """
    return pasd_bus_simulator.get_fndh()


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


@pytest.fixture(name="pasd_hw_simulators")
def pasd_hw_simulators_fixture(
    pasd_bus_simulator: PasdBusSimulator,
    fndh_simulator: PasdHardwareSimulator,
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
    return pasd_bus_simulator.get_fndh_and_smartboxes()


@pytest.fixture(name="smartbox_simulator")
def smartbox_simulator_fixture(
    pasd_hw_simulators: dict[int, PasdHardwareSimulator],
    on_smartbox_id: int,
) -> PasdHardwareSimulator:
    """
    Return a smartbox simulator for testing.

    :param pasd_hw_simulators:
        the smartbox simulator backends that the TCP server will front.
    :param on_smartbox_id: id of the smartbox being addressed.

    :return: a smartbox simulator, wrapped in a mock.
    """
    return pasd_hw_simulators[on_smartbox_id]


@pytest.fixture(name="on_smartbox_id")
def on_smartbox_id_fixture() -> int:
    """
    Return the id of a powered smartbox to be used in testing.

    :return: the id of a powered smartbox to be used in testing.
    """
    return 1


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


@pytest.fixture(name="off_smartbox_id")
def off_smartbox_id_fixture() -> int:
    """
    Return the id of an off smartbox to be used in testing.

    :return: the id of an off smartbox to be used in testing.
    """
    return 2


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


@pytest.fixture(name="configuration_manager", scope="module")
def configuration_manager_fixture(
    simulated_configuration: dict[Any, Any]
) -> unittest.mock.Mock:
    """
    Return a mock configuration_manager.

    :param simulated_configuration: a fixture containing the
        simulated configuration.

    :return: a mock configuration_manager.
    """
    manager = unittest.mock.Mock()
    manager.connect = unittest.mock.Mock(return_value=True)
    manager.read_data = unittest.mock.Mock(return_value=simulated_configuration)
    return manager


@pytest.fixture(name="test_context")
def test_context_fixture(
    pasd_hw_simulators: dict[int, PasdHardwareSimulator],
    smartbox_attached_ports: list[int],
    configuration_manager: unittest.mock.Mock,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Fixture that returns a proxy to the PaSD bus Tango device under test.

    :param pasd_hw_simulators: the FNDH and smartbox simulators against which to test
    :param smartbox_attached_ports: a list of FNDH port numbers each
        smartbox is connected to.
    :param configuration_manager: the configuration manager to manage configuration
        for field station.

    :yield: a test context in which to run the integration tests.
    """
    harness = PasdTangoTestHarness()

    harness.set_pasd_bus_simulator(pasd_hw_simulators)
    harness.set_pasd_bus_device(polling_rate=0.05, device_polling_rate=0.1)
    harness.set_fndh_device()

    for smartbox_id in range(1, PasdData.NUMBER_OF_SMARTBOXES + 1):
        harness.add_smartbox_device(
            smartbox_id, smartbox_attached_ports[smartbox_id - 1]
        )
    harness.set_configuration_server(configuration_manager)
    harness.set_field_station_device()

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
    yield test_context.get_pasd_bus_device()


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
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns a list of smartbox Tango devices.

    :param test_context: context in which the integration tests will run.

    :return: the list of smartbox Tango devices.
    """
    smartbox_devices = []
    for i in range(1, PasdData.NUMBER_OF_SMARTBOXES + 1):
        smartbox_devices.append(test_context.get_smartbox_device(i))
    return smartbox_devices
