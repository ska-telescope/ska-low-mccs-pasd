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
from typing import Dict, Iterator

import pytest
import tango

from ska_low_mccs_pasd.pasd_bus import (FndhSimulator, PasdBusSimulator,
                                        SmartboxSimulator)
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
    return PasdBusSimulator(pasd_config_path, station_label, logging.DEBUG)


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
) -> Dict[int, SmartboxSimulator]:
    """
    Return the smartbox simulators.

    :param pasd_bus_simulator: a PaSD bus simulator whose smartbox
        simulators are to be returned.
    :return: a dictionary of smartbox simulators
    """
    # TODO
    # fndh_simulator.initialize()
    # for port_nr in smartbox_attached_ports:
    #     fndh_simulator.turn_port_on(port_nr)
    return pasd_bus_simulator.get_smartboxes()


@pytest.fixture(name="smartbox_simulator")
def smartbox_simulator_fixture(
    smartbox_simulators: Dict[int, SmartboxSimulator],
    smartbox_number: int,
) -> SmartboxSimulator:
    """
    Return a smartbox simulator for testing.

    :param smartbox_simulators:
        the smartbox simulator backends that the TCP server will front.
    :param smartbox_number: id of the smartbox being addressed.

    :return: a smartbox simulator, wrapped in a mock.
    """
    return smartbox_simulators[smartbox_number]


@pytest.fixture(name="smartbox_number")
def smartbox_number_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 1


@pytest.fixture(name="test_context")
def test_context_fixture(
    fndh_simulator: FndhSimulator,
    smartbox_simulators: dict[int, SmartboxSimulator],
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Fixture that returns a proxy to the PaSD bus Tango device under test.

    :param fndh_simulator: the FNDH simulator against which to test
    :param smartbox_simulators: the smartbox simulators against which to test

    :yield: a test context in which to run the integration tests.
    """
    harness = PasdTangoTestHarness()

    harness.set_pasd_bus_simulator(fndh_simulator, smartbox_simulators)
    harness.set_pasd_bus_device()  # using all defaults
    harness.set_fndh_device()

    for smartbox_number in range(1, 25):
        harness.add_smartbox_device(smartbox_number)

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


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    test_context: PasdTangoTestHarnessContext,
    smartbox_number: int,
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns a smartbox Tango device.

    :param test_context: context in which the integration tests will run.
    :param smartbox_number: number of the smartbox under test

    :return: the smartbox Tango device.
    """
    return test_context.get_smartbox_device(smartbox_number)
