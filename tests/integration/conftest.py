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
import threading
import unittest.mock
from contextlib import contextmanager
from typing import Any, Callable, ContextManager, Generator, Iterator, Sequence

import pytest
from ska_ser_devices.client_server import TcpServer

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusSimulator,
    PasdBusSimulatorJsonServer,
    SmartboxSimulator,
)


@pytest.fixture(name="station_id")
def station_id_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 1


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
        "psu48v_voltages",
        "psu5v_voltage",
        "psu48v_current",
        "psu48v_temperature",
        "psu5v_temperature",
        "pcb_temperature",
        "outside_temperature",
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
        "uptime",
        "status",
        "led_pattern",
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
            "led_pattern",
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


@pytest.fixture(name="pasd_bus_simulator_server_launcher")
def pasd_bus_simulator_server_launcher_fixture(
    mock_fndh_simulator: FndhSimulator,
    mock_smartbox_simulators: Sequence[SmartboxSimulator],
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


@pytest.fixture(name="smartbox_number")
def smartbox_number_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 1


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
