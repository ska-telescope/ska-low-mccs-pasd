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
import importlib.resources
import logging
import threading
import unittest.mock
from contextlib import contextmanager
from typing import Any, Callable, ContextManager, Generator, Iterator, Sequence

import pytest
import yaml
from ska_ser_devices.client_server import TcpServer
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusComponentManager,
    PasdBusSimulator,
    PasdBusSimulatorJsonServer,
)
from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import SmartboxSimulator


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

    assert config_data

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
        "ports_connected",
        "port_forcings",
        "port_breakers_tripped",
        "ports_desired_power_when_online",
        "ports_desired_power_when_offline",
        "ports_power_sensed",
        "led_pattern",
        "sys_address",
        "psu48v_voltages",
        "psu48v_current",
        "psu48v_temperatures",
        "pcb_temperature",
        "fncb_temperature",
        "humidity",
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
        "uptime",
        "status",
    ]:
        setattr(
            type(mock_simulator),
            property_name,
            unittest.mock.PropertyMock(
                side_effect=functools.partial(getattr, fndh_simulator, property_name)
            ),
        )

    return mock_simulator


@pytest.fixture(name="smartbox_simulators")
def smartbox_simulators_fixture(
    pasd_bus_simulator: PasdBusSimulator,
) -> Sequence[SmartboxSimulator]:
    """
    Return the smartbox simulators.

    :param pasd_bus_simulator: a PaSD bus simulator whose smartbox
        simulators are to be returned.

    :return: a sequence of smartbox simulators
    """
    return pasd_bus_simulator.get_smartboxes()


@pytest.fixture(name="mock_smartbox_simulators")
def mock_smartbox_simulators_fixture(
    smartbox_simulators: Sequence[SmartboxSimulator],
) -> Sequence[unittest.mock.Mock]:
    """
    Return the mock smartbox simulators.

    Each mock wraps a real simulator instance,
    so it will behave like a real one,
    but we can access it as a mock too, for example assert calls.

    :param smartbox_simulators:
        the smartbox simulator backends that the TCP server will front.

    :return: a sequence of mock smartbox simulators
    """
    mock_simulators: list[unittest.mock.Mock] = []

    for smartbox_simulator in smartbox_simulators:
        mock_simulator = unittest.mock.Mock(wraps=smartbox_simulator)

        # "wraps" doesn't handle properties -- we have to add them manually
        property_name: str
        for property_name in [
            "ports_connected",
            "port_forcings",
            "port_breakers_tripped",
            "ports_desired_power_when_online",
            "ports_desired_power_when_offline",
            "ports_power_sensed",
            "led_pattern",
            "sys_address",
            "ports_current_draw",
            "input_voltage",
            "power_supply_output_voltage",
            "status",
            "power_supply_temperature",
            "outside_temperature",
            "pcb_temperature",
            "modbus_register_map_revision",
            "pcb_revision",
            "cpu_id",
            "chip_id",
            "firmware_version",
            "uptime",
        ]:
            setattr(
                type(mock_simulator),
                property_name,
                unittest.mock.PropertyMock(
                    side_effect=functools.partial(
                        getattr, smartbox_simulator, property_name
                    )
                ),
            )

        mock_simulators.append(mock_simulator)

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
    smartbox_simulators: list[unittest.mock.Mock],
    smartbox_id: int,
) -> unittest.mock.Mock:
    """
    Return a smartbox simulator for testing.

    :param smartbox_simulators:
        the smartbox simulator backends that the TCP server will front.
    :param smartbox_id: id of the smartbox being addressed.

    :return: a smartbox simulator, wrapped in a mock.
    """
    return smartbox_simulators[smartbox_id - 1]


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


@pytest.fixture(name="pasd_bus_simulator_server_launcher")
def pasd_bus_simulator_server_launcher_fixture(
    mock_fndh_simulator: FndhSimulator,
    mock_smartbox_simulators: Sequence[SmartboxSimulator],
    logger: logging.Logger,
) -> Callable[[], ContextManager[TcpServer]]:
    """
    Return a context manager factory for a PaSD bus simulator server.

    That is, a callable that, when called,
    returns a context manager that spins up a simulator server,
    yields it for use in testing,
    and then shuts its down afterwards.

    :param mock_fndh_simulator:
        the FNDH simulator backend that the TCP server will front,
        wrapped with a mock so that we can assert calls.
    :param mock_smartbox_simulators:
        the smartbox simulator backends that the TCP server will front,
        each wrapped with a mock so that we can assert calls.
    :param logger: a python standard logger

    :return: a PaSD bus simulator server context manager factory
    """

    @contextmanager
    def launch_pasd_bus_simulator_server() -> Iterator[TcpServer]:
        simulator_server = PasdBusSimulatorJsonServer(
            mock_fndh_simulator, mock_smartbox_simulators
        )
        server = TcpServer(
            "localhost",
            0,  # let the kernel give us a port
            simulator_server,
            logger=logger,
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
    mock_callbacks: MockCallableGroup,
) -> PasdBusComponentManager:
    """
    Return a PaSD bus simulator component manager.

    (This is a pytest fixture.)

    :param pasd_bus_info: information about the PaSD bus, such as its
        IP address (host and port) and an appropriate timeout to use.
    :param logger: the logger to be used by this object.
    :param mock_callbacks: a group of mock callables for the component
        manager under test to use as callbacks

    :return: a PaSD bus simulator component manager.
    """
    component_manager = PasdBusComponentManager(
        pasd_bus_info["host"],
        pasd_bus_info["port"],
        pasd_bus_info["timeout"],
        logger,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["pasd_device_state"],
    )
    return component_manager
