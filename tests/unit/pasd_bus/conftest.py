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
import importlib
import logging
import threading
import unittest.mock
from contextlib import contextmanager
from typing import Any, Callable, ContextManager, Generator, Iterator

import pytest
import yaml
from ska_ser_devices.client_server import TcpServer
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.pasd_bus import (
    PasdBusComponentManager,
    PasdBusSimulator,
    PasdBusSimulatorJsonServer,
)


@pytest.fixture(name="max_workers")
def max_workers_fixture() -> int:
    """
    Return the number of worker threads.

    :return: number of worker threads
    """
    return 1


@pytest.fixture(name="station_id")
def station_id_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 1


@pytest.fixture(name="pasd_config")
def pasd_config_fixture(station_id: int) -> dict:
    """
    Return the PaSD config that the pasd bus device uses.

    :param station_id: id of the staion whose configuration will be used
        in testing.

    :return: the PaSD config that the PaSD bus object under test uses.
    """
    config_data = importlib.resources.read_text(
        "ska_low_mccs_pasd.pasd_bus",
        PasdBusSimulator.CONFIG_PATH,
    )

    assert config_data is not None  # for the type-checker

    config = yaml.safe_load(config_data)
    return config["stations"][station_id - 1]


@pytest.fixture(name="pasd_bus_simulator")
def pasd_bus_simulator_fixture(station_id: int) -> PasdBusSimulator:
    """
    Fixture that returns a PaSD bus simulator.

    :param station_id: the id of the station whose PaSD bus we are
        simulating.

    :return: a PaSD bus simulator
    """
    return PasdBusSimulator(station_id, logging.DEBUG)


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
                side_effect=functools.partial(
                    getattr, pasd_bus_simulator, property_name
                )
            ),
        )

    return mock_simulator


@pytest.fixture(name="pasd_bus_simulator_server_launcher")
def pasd_bus_simulator_server_launcher_fixture(
    mock_pasd_bus_simulator: PasdBusSimulator,
) -> Callable[[], ContextManager[TcpServer]]:
    """
    Return a context manager factory for a PaSD bus simulator server.

    That is, a callable that, when called,
    returns a context manager that spins up a simulator server,
    yields it for use in testing,
    and then shuts its down afterwards.

    :param mock_pasd_bus_simulator:
        the simulator backend that the TCP server will front,
        wrapped with a mock that that we can assert calls.

    :return: a PaSD bus simulator server context manager factory
    """

    @contextmanager
    def launch_pasd_bus_simulator_server() -> Iterator[TcpServer]:
        simulator_server = PasdBusSimulatorJsonServer(mock_pasd_bus_simulator)
        server = TcpServer(
            "localhost",
            0,  # let the kernel give us a port
            simulator_server,
        )

        with server:
            server_thread = threading.Thread(
                name="PaSD bus simulator thread",
                target=server.serve_forever,
            )
            server_thread.daemon = True  # don't hang on exit
            server_thread.start()
            yield server
            server.shutdown()

    return launch_pasd_bus_simulator_server


@pytest.fixture(name="pasd_bus_simulator_server")
def pasd_bus_simulator_server_fixture(
    pasd_bus_simulator_server_launcher: Callable[[], ContextManager[TcpServer]],
) -> Generator[TcpServer, None, None]:
    """
    Return a running PaSD bus simulator server for use in testing.

    :param pasd_bus_simulator_server_launcher: a callable that, when called,
        returns a context manager that spins up a simulator server,
        yields it for use in testing,
        and then shuts its down afterwards.

    :yields: a PaSD bus simulator server
    """
    with pasd_bus_simulator_server_launcher() as server:
        yield server


@pytest.fixture(name="pasd_bus_info")
def pasd_bus_info_fixture(
    pasd_bus_simulator_server: TcpServer,
) -> dict[str, Any]:
    """
    Return the host and port of the PaSD bus.

    :param pasd_bus_simulator_server:
        a TCP server front end to a PaSD bus simulator.

    :return: the host and port of the AWG.
    """
    host, port = pasd_bus_simulator_server.server_address
    return {
        "host": host,
        "port": port,
        "timeout": 3.0,
    }


@pytest.fixture(name="pasd_bus_component_manager")
def pasd_bus_component_manager_fixture(
    pasd_bus_info: dict[str, Any],
    logger: logging.Logger,
    max_workers: int,
    mock_callbacks: MockCallableGroup,
) -> PasdBusComponentManager:
    """
    Return a PaSD bus simulator component manager.

    (This is a pytest fixture.)

    :param pasd_bus_info: information about the PaSD bus, such as its
        IP address (host and port) and an appropriate timeout to use.
    :param logger: the logger to be used by this object.
    :param max_workers: number of worker threads
    :param mock_callbacks: a group of mock callables for the component
        manager under test to use as callbacks

    :return: a PaSD bus simulator component manager.
    """
    component_manager = PasdBusComponentManager(
        pasd_bus_info["host"],
        pasd_bus_info["port"],
        pasd_bus_info["timeout"],
        logger,
        max_workers,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
    )
    component_manager.start_communicating()
    return component_manager
