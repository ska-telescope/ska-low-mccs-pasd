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
import tango
from ska_control_model import LoggingLevel
from ska_ser_devices.client_server import TcpServer
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)

from ska_low_mccs_pasd import MccsFNDH, MccsPasdBus, MccsSmartBox
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
        "sys_address",
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


@pytest.fixture(name="smartbox_id")
def smartbox_id_fixture() -> int:
    """
    Return the id of the smartbox to be used in testing.

    :return: the id of the smartbox to be used in testing.
    """
    return 1


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
            "power_supply_temperature",
            "outside_temperature",
            "pcb_temperature",
            "modbus_register_map_revision",
            "pcb_revision",
            "cpu_id",
            "chip_id",
            "firmware_version",
            "uptime",
            "sys_address",
            "status",
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


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the pasd_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: name of the pasd_bus Tango device.

    :yield: the pasd_bus Tango device under test.
    """
    yield tango_harness.get_device(pasd_bus_name)


@pytest.fixture(name="smartbox_devices")
def smartbox_devices_fixture(
    tango_harness: TangoContextProtocol,
    smartbox_names: str,
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns the pasd_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param smartbox_names: the name of the smartbox_bus Tango device

    :return: the pasd_bus Tango device under test.
    """
    smartbox_proxies = []
    for smartbox_no in range(2):
        smartbox_proxies.append(tango_harness.get_device(smartbox_names[smartbox_no]))
    return smartbox_proxies


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    smartbox_devices: list[tango.DeviceProxy], smartbox_id: int
) -> list[tango.DeviceProxy]:
    """
    Fixture that returns a smartbox Tango device.

    :param smartbox_devices: a list of smartboxes.
    :param smartbox_id: the smartbox of interest.

    :return: the smartbox Tango device.
    """
    return smartbox_devices[smartbox_id]


@pytest.fixture(name="smartbox_names", scope="session")
def smartbox_names_fixture() -> list[str]:
    """
    Return the names of the smartbox Tango devices.

    :return: the names of the smartbox Tango devices.
    """
    smartboxes = []
    for i in range(1, 25):
        smartboxes.append(f"low-mccs/smartbox/{i:05}")

    return smartboxes


@pytest.fixture(name="pasd_bus_name", scope="session")
def pasd_bus_name_fixture() -> str:
    """
    Return the name of the pasd_bus Tango device.

    :return: the name of the pasd_bus Tango device.
    """
    return "low-mccs/pasdbus/001"


@pytest.fixture(name="fndh_name", scope="session")
def fndh_name_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs/fndh/001"


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    smartbox_names: list[str],
    pasd_bus_name: str,
    fndh_name: str,
    pasd_bus_info: dict,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param smartbox_names: the name of the smartbox_bus Tango device
    :param pasd_bus_name: the fqdn of the pasdbus
    :param fndh_name: the fqdn of the fndh
    :param pasd_bus_info: the information for pasd setup

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    # Add the pasdbus.
    context_manager.add_device(
        pasd_bus_name,
        MccsPasdBus,
        Host=pasd_bus_info["host"],
        Port=pasd_bus_info["port"],
        Timeout=pasd_bus_info["timeout"],
        LoggingLevelDefault=int(LoggingLevel.OFF),
    )
    # add the FNDH.
    context_manager.add_device(
        fndh_name,
        MccsFNDH,
        PasdFQDN=pasd_bus_name,
        LoggingLevelDefault=int(LoggingLevel.OFF),
    )
    # Add the 24 Smartboxes.
    for smartbox_no in range(24):
        context_manager.add_device(
            smartbox_names[smartbox_no],
            MccsSmartBox,
            PasdFQDN=pasd_bus_name,
            FndhFQDN=fndh_name,
            FndhPort=smartbox_no + 1,
            SmartBoxNumber=smartbox_no + 1,
            LoggingLevelDefault=int(LoggingLevel.OFF),
        )

    with context_manager as context:
        yield context


@pytest.fixture(name="fndh_fqdn", scope="session")
def fndh_fqdn_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs/fndh/001"


@pytest.fixture(name="fndh_device")
def fndh_device_fixture(
    tango_harness: TangoContextProtocol,
    fndh_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the fndh Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param fndh_name: name of the fndh_bus Tango device.

    :yield: the fndh Tango device under test.
    """
    yield tango_harness.get_device(fndh_name)
