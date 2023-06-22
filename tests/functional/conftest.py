# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains pytest-specific test harness for PaSD functional tests."""
import logging
import os
import threading
from contextlib import contextmanager
from typing import Callable, ContextManager, Generator, Iterator, Optional, Union, cast

import _pytest
import pytest
import tango
from ska_control_model import LoggingLevel
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
    TrueTangoContextManager,
)
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup


# TODO: https://github.com/pytest-dev/pytest-forked/issues/67
# We're stuck on pytest 6.2 until this gets fixed,
# and this version of pytest is not fully typehinted
def pytest_addoption(
    parser: _pytest.config.argparsing.Parser,  # type: ignore[name-defined]
) -> None:
    """
    Add a command line option to pytest.

    This is a pytest hook, here implemented to add the `--true-context`
    option, used to indicate that a true Tango subsystem is available,
    so there is no need for the test harness to spin up a Tango test
    context.

    :param parser: the command line options parser
    """
    parser.addoption(
        "--true-context",
        action="store_true",
        default=False,
        help=(
            "Tell pytest that you have a true Tango context and don't "
            "need to spin up a Tango test context"
        ),
    )


@pytest.fixture(name="true_context", scope="session")
def true_context_fixture(request: pytest.FixtureRequest) -> bool:
    """
    Return whether to test against an existing Tango deployment.

    If True, then Tango is already deployed, and the tests will be run
    against that deployment.

    If False, then Tango is not deployed, so the test harness will stand
    up a test context and run the tests against that.

    :param request: A pytest object giving access to the requesting test
        context.

    :return: whether to test against an existing Tango deployment
    """
    if request.config.getoption("--true-context"):
        return True
    if os.getenv("TRUE_TANGO_CONTEXT", None):
        return True
    return False


@pytest.fixture(name="pasd_address_context_manager_factory", scope="module")
def pasd_address_context_manager_factory_fixture() -> Callable[
    [], ContextManager[tuple[str | bytes | bytearray, int]]
]:
    """
    Return a PaSD address context manager factory.

    That is, return a callable that, when called, provides a context
    manager that, when entered, returns a PaSD host and port, while
    at the same time ensuring the validity of that host and port.

    This fixture obtains the PaSD address in one of two ways:

    Firstly it checks for a `PASD_ADDRESS` environment variable, of
    the form "localhost:8502". If found, it is expected that a PaSD is
    already available at this host and port, so there is nothing more
    for this fixture to do. The callable that it returns will itself
    return an empty context manager that, when entered, simply yields
    the specified host and port.

    Otherwise, the callable that this factory returns will be a context
    manager for a PaSD simulator server instance. When entered, that
    context manager will launch the PaSD simulator server, and then
    yield the host and port on which it is running.

    :return: a callable that returns a context manager that, when
        entered, yields the host and port of a PaSD server.
    """
    address_var = "PASD_ADDRESS"
    if address_var in os.environ:
        [host, port_str] = os.environ[address_var].split(":")

        @contextmanager
        def _yield_address() -> Generator[tuple[str, int], None, None]:
            yield host, int(port_str)

        return _yield_address
    else:

        @contextmanager
        def launch_simulator_server() -> Iterator[tuple[str | bytes | bytearray, int]]:
            # Imports are deferred until now,
            # so that we do not try to import from ska_low_mccs_pasd
            # until we know that we need to.
            # This allows us to run our functional tests
            # against a real cluster
            # from within a test runner pod
            # that does not have ska_low_mccs_pasd installed.
            from ska_ser_devices.client_server import TcpServer

            from ska_low_mccs_pasd.pasd_bus import (
                PasdBusSimulator,
                PasdBusSimulatorJsonServer,
            )

            simulator = PasdBusSimulator(1, logging.DEBUG)
            simulator_server = PasdBusSimulatorJsonServer(
                simulator.get_fndh(), simulator.get_smartboxes()
            )
            server = TcpServer(
                "127.0.0.1", 0, simulator_server  # let the kernel give us a port
            )
            with server:
                server_thread = threading.Thread(
                    name="Signal generator simulator thread",
                    target=server.serve_forever,
                )
                server_thread.daemon = True  # don't hang on exit
                server_thread.start()
                yield server.server_address
                server.shutdown()
                server_thread.join()

        return launch_simulator_server


@pytest.fixture(name="pasd_bus_name", scope="module")
def pasd_bus_name_fixture() -> str:
    """
    Return the name of the PaSD bus device under test.

    :return: the name of the PaSD bus device under test.
    """
    return "low-mccs/pasdbus/001"


@pytest.fixture(name="field_station_name", scope="module")
def field_station_name_fixture() -> str:
    """
    Return the name of the PaSD bus device under test.

    :return: the name of the PaSD bus device under test.
    """
    return "low-mccs/fieldstation/001"


@pytest.fixture(name="fndh_name", scope="module")
def fndh_name_fixture() -> str:
    """
    Return the name of the PaSD bus device under test.

    :return: the name of the PaSD bus device under test.
    """
    return "low-mccs/fndh/001"


@pytest.fixture(name="pasd_timeout", scope="module")
def pasd_timeout_fixture() -> Optional[float]:
    """
    Return the timeout to use when communicating with the PaSD.

    :return: the timeout to use when communicating with the PaSD.
    """
    return 5.0


@pytest.fixture(name="tango_harness", scope="module")
def tango_harness_fixture(
    true_context: bool,
    pasd_bus_name: str,
    pasd_address_context_manager_factory: Callable[[], ContextManager[tuple[str, int]]],
    pasd_timeout: Optional[float],
) -> Generator[TangoContextProtocol, None, None]:
    """
    Yield a Tango context containing the device/s under test.

    :param true_context: whether to test against an existing Tango
        deployment
    :param pasd_bus_name: name of the PaSD bus Tango device.
    :param pasd_address_context_manager_factory: a callable that returns
        a context manager that, when entered, yields the host and port
        of a PaSD bus.
    :param pasd_timeout: timeout to use when communicating with the
        PaSD, in seconds. If None, communications will block
        indefinitely.

    :yields: a Tango context containing the devices under test
    """
    tango_context_manager: Union[
        TrueTangoContextManager, ThreadedTestTangoContextManager
    ]  # for the type checker
    if true_context:
        tango_context_manager = TrueTangoContextManager()
        with tango_context_manager as context:
            yield context
    else:
        with pasd_address_context_manager_factory() as (pasd_host, pasd_port):
            tango_context_manager = ThreadedTestTangoContextManager()
            cast(ThreadedTestTangoContextManager, tango_context_manager).add_device(
                pasd_bus_name,
                "ska_low_mccs_pasd.MccsPasdBus",
                Host=pasd_host,
                Port=pasd_port,
                Timeout=pasd_timeout,
                LoggingLevelDefault=int(LoggingLevel.DEBUG),
            )
            with tango_context_manager as context:
                yield context


@pytest.fixture(name="change_event_callbacks", scope="module")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "state",
        "healthState",
        "healthState",
        "fndhUptime",
        "fndhStatus",
        "fndhLedPattern",
        "fndhPortsConnected",
        "fndhPsu48vVoltages",
        "fndhPsu48vCurrent",
        "fndhPsu48vTemperature",
        "fndhPsu5vVoltage",
        "fndhPsu5vTemperature",
        "fndhPcbTemperature",
        "fndhOutsideTemperature",
        "fndhPortsPowerSensed",
        "smartbox1Uptime",
        "smartbox1Status",
        "smartbox1LedPattern",
        "smartbox1InputVoltage",
        "smartbox1PowerSupplyOutputVoltage",
        "smartbox1PowerSupplyTemperature",
        "smartbox1PcbTemperature",
        "smartbox1OutsideTemperature",
        "smartbox1PortsConnected",
        "smartbox1PortsPowerSensed",
        "outsideTemperature",
        "smartbox24PortsCurrentDraw",
        "fieldstationoutsideTemperature",
        timeout=10.0,
        assert_no_error=False,
    )


@pytest.fixture(name="fndh_device_proxy", scope="module")
def fndh_device_proxy_fixture(
    tango_harness: TangoContextProtocol,
    fndh_name: str,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsFndh.

    :param tango_harness: a test harness for Tango devices.
    :param fndh_name: the name of the fndh device under test.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.

    :return: A proxy to an instance of MccsFndh.
    """
    proxy = tango_harness.get_device(fndh_name)

    for attribute_name in [
        "state",
        "healthState",
        "outsideTemperature",
    ]:
        print(f"Subscribing proxy to {attribute_name}...")
        proxy.subscribe_event(
            attribute_name,
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[attribute_name],
        )
        change_event_callbacks.assert_change_event(attribute_name, Anything)

    return proxy


@pytest.fixture(name="field_station_device", scope="module")
def field_station_device_fixture(
    tango_harness: TangoContextProtocol,
    field_station_name: str,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsFieldStation.

    :param tango_harness: a test harness for Tango devices.
    :param field_station_name: the name of the field station device under test.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.

    :return: A proxy to an instance of MccsFieldStation.
    """
    proxy = tango_harness.get_device(field_station_name)

    for attribute_name in [
        "state",
        "healthState",
    ]:
        print(f"Subscribing proxy to {attribute_name}...")
        proxy.subscribe_event(
            attribute_name,
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[attribute_name],
        )
        change_event_callbacks.assert_change_event(attribute_name, Anything)

    print("Subscribing proxy to outsideTemperature...")
    proxy.subscribe_event(
        "OutsideTemperature",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fieldstationoutsideTemperature"],
    )
    change_event_callbacks["fieldstationoutsideTemperature"].assert_change_event(
        Anything
    )
    return proxy


@pytest.fixture(name="pasd_bus_device", scope="module")
def pasd_bus_device_fixture(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsPasdBus.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: the name of the PaSD bus device under test.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.

    :return: A proxy to an instance of MccsPasdBus.
    """
    proxy = tango_harness.get_device(pasd_bus_name)

    for attribute_name in [
        "state",
        "healthState",
        "fndhUptime",
        "fndhStatus",
        "fndhLedPattern",
        "fndhPsu48vVoltages",
        "fndhPsu48vCurrent",
        "fndhPsu48vTemperature",
        "fndhPsu5vVoltage",
        "fndhPsu5vTemperature",
        "fndhPcbTemperature",
        "fndhOutsideTemperature",
        "fndhPortsConnected",
        "fndhPortsPowerSensed",
        "smartbox1Uptime",
        "smartbox1Status",
        "smartbox1LedPattern",
        "smartbox1InputVoltage",
        "smartbox1PowerSupplyOutputVoltage",
        "smartbox1PowerSupplyTemperature",
        "smartbox1PcbTemperature",
        "smartbox1OutsideTemperature",
        "smartbox1PortsConnected",
        "smartbox1PortsPowerSensed",
        "smartbox24PortsCurrentDraw",
    ]:
        print(f"Subscribing proxy to {attribute_name}...")
        proxy.subscribe_event(
            attribute_name,
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[attribute_name],
        )
        change_event_callbacks.assert_change_event(attribute_name, Anything)

    return proxy
