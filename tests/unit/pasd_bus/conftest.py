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
from typing import Optional

import pytest
import yaml
from ska_control_model import (
    CommunicationStatus,
    PowerState,
    ResultCode,
    SimulationMode,
)
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd import MccsPasdBus
from ska_low_mccs_pasd.pasd_bus import (
    PasdBusComponentManager,
    PasdBusSimulator,
    PasdBusSimulatorComponentManager,
)


@pytest.fixture(name="max_workers")
def max_workers_fixture() -> int:
    """
    Return the number of worker threads.

    :return: number of worker threads
    """
    return 1


@pytest.fixture(name="pasd_config_path")
def pasd_config_path_fixture() -> str:
    """
    Return the path to a YAML file that specifies the PaSD configuration.

    :return: the path to a YAML file that specifies the PaSD
        configuration.
    """
    return "src/ska_low_mccs_pasd/pasd_bus/pasd_configuration.yaml"


@pytest.fixture(name="station_id")
def station_id_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 1


@pytest.fixture(name="pasd_config")
def pasd_config_fixture(pasd_config_path: str, station_id: int) -> dict:
    """
    Return the PaSD config that the pasd bus device uses.

    :param pasd_config_path: path to a YAML file that specifies the PaSD
        configuration
    :param station_id: id of the staion whose configuration will be used
        in testing.

    :return: the PaSD config that the PaSD bus object under test uses.
    """
    with open(pasd_config_path, "r", encoding="utf8") as stream:
        config = yaml.safe_load(stream)
    return config["stations"][station_id - 1]


@pytest.fixture(name="pasd_bus_simulator")
def pasd_bus_simulator_fixture(
    pasd_config_path: str,
    station_id: int,
    logger: logging.Logger,
) -> PasdBusSimulator:
    """
    Fixture that returns a PaSD bus simulator.

    :param pasd_config_path: path to a YAML file that specifies the PaSD
        configuration.
    :param station_id: the id of the station whose PaSD bus we are
        simulating.
    :param logger: a logger for the PaSD bus simulator to use.

    :return: a PaSD bus simulator
    """
    return PasdBusSimulator(pasd_config_path, station_id, logger)


@pytest.fixture(name="mock_pasd_bus_simulator")
def mock_pasd_bus_simulator_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> unittest.mock.Mock:
    """
    Return a mock PaSD bus simulator.

    The returned mock wraps a real simulator instance, so it will behave
    like a real one, but we can access it as a mock too, for example
    assert calls.

    :param pasd_bus_simulator: a real PaSD bus simulator to wrap in a
        mock.

    :return: a mock PaSD bus simulator
    """
    mock_simulator = unittest.mock.Mock(wraps=pasd_bus_simulator)

    # "wraps" doesn't handle properties -- we have to add them manually
    for property_name in [
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
    ]:
        setattr(
            type(mock_simulator),
            property_name,
            unittest.mock.PropertyMock(
                return_value=getattr(pasd_bus_simulator, property_name)
            ),
        )

    return mock_simulator


@pytest.fixture(name="pasd_bus_simulator_component_manager")
def pasd_bus_simulator_component_manager_fixture(
    mock_pasd_bus_simulator: unittest.mock.Mock,
    logger: logging.Logger,
    max_workers: int,
    callbacks: MockCallableGroup,
) -> PasdBusSimulatorComponentManager:
    """
    Return a PaSD bus simulator component manager.

    (This is a pytest fixture.)

    :param mock_pasd_bus_simulator: a mock PaSD bus simulator to be used
        by the PaSD bus simulator component manager
    :param logger: the logger to be used by this object.
    :param max_workers: number of worker threads
    :param callbacks: a group of mock callables for the component
        manager under test to use as callbacks

    :return: a PaSD bus simulator component manager.
    """
    return PasdBusSimulatorComponentManager(
        logger,
        max_workers,
        callbacks["communication_state"],
        callbacks["component_state"],
        _simulator=mock_pasd_bus_simulator,
    )


@pytest.fixture(name="pasd_bus_component_manager")
def pasd_bus_component_manager_fixture(
    pasd_bus_simulator_component_manager: PasdBusSimulatorComponentManager,
    logger: logging.Logger,
    max_workers: int,
    callbacks: MockCallableGroup,
) -> PasdBusComponentManager:
    """
    Return a PaSD bus component manager.

    :param pasd_bus_simulator_component_manager: a pre-initialised
        PaSD bus simulator component manager to be used by the PaSD bus
        component manager
    :param logger: the logger to be used by this object.
    :param max_workers: number of worker threads
    :param callbacks: a group of mock callables for the component
        manager under test to use as callbacks

    :return: a PaSD bus component manager
    """
    return PasdBusComponentManager(
        SimulationMode.TRUE,
        logger,
        max_workers,
        callbacks["communication_state"],
        callbacks["component_state"],
        _simulator_component_manager=pasd_bus_simulator_component_manager,
    )


@pytest.fixture(name="mock_component_manager")
def mock_component_manager_fixture(unique_id: str) -> unittest.mock.Mock:
    """
    Return a mock component manager.

    The mock component manager is a simple mock except for one bit of
    extra functionality: when we call start_communicating() on it, it
    makes calls to callbacks signaling that communication is established
    and the component is off.

    :param unique_id: a unique id used to check Tango layer functionality

    :return: a mock component manager
    """
    mock = unittest.mock.Mock()
    mock.is_communicating = False

    def _start_communicating(mock: unittest.mock.Mock) -> None:
        mock.is_communicating = True
        mock._communication_status_changed_callback(CommunicationStatus.NOT_ESTABLISHED)
        mock._communication_status_changed_callback(CommunicationStatus.ESTABLISHED)
        mock._component_state_changed_callback({"power_state": PowerState.OFF})

    mock.start_communicating.side_effect = lambda: _start_communicating(mock)

    mock.return_value = unique_id, ResultCode.QUEUED

    return mock


@pytest.fixture(name="patched_pasd_bus_device_class")
def patched_pasd_bus_device_class_fixture(
    mock_component_manager: unittest.mock.Mock,
) -> type[MccsPasdBus]:
    """
    Return a pasd bus device that is patched with a mock component manager.

    :param mock_component_manager: the mock component manager with
        which to patch the device

    :return: a pasd bus device that is patched with a mock component
        manager.
    """

    class PatchedMccsPasdBus(MccsPasdBus):
        """A pasd bus device patched with a mock component manager."""

        def __init__(self) -> None:
            """Initialise."""
            self._communication_status: Optional[CommunicationStatus] = None
            super().__init__()

        def create_component_manager(
            self: PatchedMccsPasdBus,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager instead of the usual one.

            :return: a mock component manager
            """
            mock_component_manager._communication_status_changed_callback = (
                self._communication_status_changed_callback
            )
            mock_component_manager._component_state_changed_callback = (
                self._component_state_changed_callback
            )
            return mock_component_manager

    return PatchedMccsPasdBus
