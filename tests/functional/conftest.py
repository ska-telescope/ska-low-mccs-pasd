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
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import (
    Any,
    Callable,
    ContextManager,
    Generator,
    Iterator,
    Optional,
    Union,
    cast,
)

import _pytest
import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, ResultCode
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


@pytest.fixture(name="is_true_context", scope="session")
def is_true_context_fixture(request: pytest.FixtureRequest) -> bool:
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


@pytest.fixture(name="pasd_address_context_manager_factory", scope="session")
def pasd_address_context_manager_factory_fixture(
    logger: logging.Logger,
) -> Callable[[], ContextManager[tuple[str | bytes | bytearray, int]]]:
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

    :param logger: a python standard logger

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
                "127.0.0.1",
                0,
                simulator_server,  # let the kernel give us a port
                logger=logger,
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


@pytest.fixture(name="pasd_bus_name", scope="session")
def pasd_bus_name_fixture() -> str:
    """
    Return the name of the PaSD bus device under test.

    :return: the name of the PaSD bus device under test.
    """
    return "low-mccs/pasdbus/001"


@pytest.fixture(name="field_station_name", scope="session")
def field_station_name_fixture() -> str:
    """
    Return the name of the PaSD bus device under test.

    :return: the name of the PaSD bus device under test.
    """
    return "low-mccs/fieldstation/001"


@pytest.fixture(name="fndh_name", scope="session")
def fndh_name_fixture() -> str:
    """
    Return the name of the PaSD bus device under test.

    :return: the name of the PaSD bus device under test.
    """
    return "low-mccs/fndh/001"


@pytest.fixture(name="pasd_timeout", scope="session")
def pasd_timeout_fixture() -> Optional[float]:
    """
    Return the timeout to use when communicating with the PaSD.

    :return: the timeout to use when communicating with the PaSD.
    """
    return 5.0


@pytest.fixture(name="tango_harness", scope="session")
def tango_harness_fixture(
    is_true_context: bool,
    pasd_bus_name: str,
    fndh_name: str,
    pasd_address_context_manager_factory: Callable[[], ContextManager[tuple[str, int]]],
    pasd_timeout: Optional[float],
) -> Generator[TangoContextProtocol, None, None]:
    """
    Yield a Tango context containing the device/s under test.

    :param is_true_context: whether to test against an existing Tango
        deployment
    :param pasd_bus_name: name of the PaSD bus Tango device.
    :param fndh_name: the name of the FNDH Tango device.
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
    if is_true_context:
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
            cast(ThreadedTestTangoContextManager, tango_context_manager).add_device(
                fndh_name,
                "ska_low_mccs_pasd.MccsFNDH",
                PasdFQDN=pasd_bus_name,
                LoggingLevelDefault=int(LoggingLevel.DEBUG),
            )
            with tango_context_manager as context:
                yield context


@pytest.fixture(name="change_event_callbacks", scope="session")
def change_event_callbacks_fixture(
    device_subscriptions: dict[str, list]
) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :param device_subscriptions: list of subscriptions to make.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    keys = [
        f"{device_name}/{device_attribute}"
        for device_name in device_subscriptions.keys()
        for device_attribute in device_subscriptions[device_name]
    ]
    return MockTangoEventCallbackGroup(
        *keys,
        timeout=10.0,
        assert_no_error=False,
    )


@pytest.fixture(name="field_station_device", scope="session")
def field_station_device_fixture(
    field_station_name: str,
    get_device_proxy: Callable,
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsFieldStation.

    :param field_station_name: the name of the field station device under test.
    :param get_device_proxy: cached fixture for setting up device proxy.

    :return: A proxy to an instance of MccsFieldStation.
    """
    return get_device_proxy(field_station_name)


@pytest.fixture(name="pasd_bus_device", scope="session")
def pasd_bus_device_fixture(
    pasd_bus_name: str,
    get_device_proxy: Callable,
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsPasdBus.

    :param pasd_bus_name: the name of the PaSD bus device under test.
    :param get_device_proxy: cached fixture for setting up device proxy.

    :return: A proxy to an instance of MccsPasdBus.
    """
    return get_device_proxy(pasd_bus_name)


@pytest.fixture(name="fndh_device", scope="session")
def fndh_device_fixture(
    fndh_name: str, get_device_proxy: Callable
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsFNDH.

    :param fndh_name: the name of the FNDH device under test.
    :param get_device_proxy: cached fixture for setting up device proxy.

    :return: A proxy to an instance of MccsFNDH.
    """
    return get_device_proxy(fndh_name)


@pytest.fixture(name="device_mapping", scope="session")
def device_mapping_fixture(
    fndh_name: str,
    pasd_bus_name: str,
    field_station_name: str,
) -> dict[str, str]:
    """
    Return a dictionary mapping short name to FQDN for devices under test.

    :param fndh_name: the name of the FNDH device under test.
    :param pasd_bus_name: the name of the pasd bus device under test.
    :param field_station_name: the name of the field station device under test.

    :return: A dictionary mapping short name to FQDN for devices under test.
    """
    device_dict = {
        "MccsFndh": fndh_name,
        "MCCS-for-PaSD": pasd_bus_name,
        "MccsFieldStation": field_station_name,
    }
    return device_dict


@pytest.fixture(name="device_subscriptions", scope="session")
def device_subscriptions_fixture(
    fndh_name: str, pasd_bus_name: str, field_station_name: str
) -> dict[str, list[str]]:
    """
    Return a dictionary mapping device name to list of subscriptions to make.

    :param fndh_name: the name of the FNDH device under test.
    :param pasd_bus_name: the name of the pasd bus device under test.
    :param field_station_name: the name of the field station device under test.

    :return: A dictionary mapping device name to list of subscriptions to make.
    """
    device_subscriptions = {
        pasd_bus_name: [
            "state",
            "healthState",
            "adminMode",
            "fndhUptime",
            "fndhStatus",
            "fndhLedPattern",
            "fndhPsu48vVoltage",
            "fndhPsu48vCurrent",
            "fndhPsu48vTemperatures",
            "fndhPcbTemperature",
            "fndhFncbTemperature",
            "fndhHumidity",
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
        ],
        fndh_name: [
            "state",
            "healthState",
            "adminMode",
        ],
        field_station_name: [
            "state",
            "healthState",
            "adminMode",
            "OutsideTemperature",
        ],
    }
    return device_subscriptions


@pytest.fixture(name="get_device_proxy", scope="session")
def get_device_proxy_fixture(
    device_subscriptions: dict[str, list[str]],
    tango_harness: TangoContextProtocol,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> tango.DeviceProxy:
    """
    Return a cached device proxy with subscriptions set up.

    :param device_subscriptions: list of subscriptions to make.
    :param tango_harness: a Tango context containing the devices under test.
    :param change_event_callbacks: a dictionary of callables to be used as
        tango change event callbacks.

    :return: A cached device proxy with subscriptions set up.
    """

    @lru_cache
    def _get_device_proxy(device_name: str) -> tango.DeviceProxy:
        proxy = tango_harness.get_device(device_name)
        print(f"Creating proxy for {device_name}")
        for attribute_name in device_subscriptions[device_name]:
            print(f"Subscribing proxy to {device_name}/{attribute_name}...")
            proxy.subscribe_event(
                attribute_name,
                tango.EventType.CHANGE_EVENT,
                change_event_callbacks[f"{device_name}/{attribute_name}"],
            )
            change_event_callbacks[
                f"{device_name}/{attribute_name}"
            ].assert_change_event(Anything)
        return proxy

    return _get_device_proxy


@pytest.fixture(name="set_device_state", scope="session")
def set_device_state_fixture(
    device_mapping: dict[str, str],
    get_device_proxy: Callable,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> Callable:
    """
    Set device state.

    :param device_mapping: A dictionary mapping short name to FQDN for devices
        under test.
    :param get_device_proxy: A cached device proxy with subscriptions set up.
    :param change_event_callbacks: a dictionary of callables to be used as
        tango change event callbacks.

    :return: A function to set device state.
    """

    def _set_device_state(
        device: tango.DeviceProxy, state: tango.DevState, mode: AdminMode
    ) -> None:
        device_name = device_mapping[device]

        device_proxy = get_device_proxy(device_name)

        admin_mode_callback = change_event_callbacks[f"{device_name}/adminMode"]
        state_callback = change_event_callbacks[f"{device_name}/state"]
        if device_proxy.adminMode != mode:
            device_proxy.adminMode = mode
            admin_mode_callback.assert_change_event(mode)
            if mode != AdminMode.OFFLINE:
                state_callback.assert_change_event(tango.DevState.UNKNOWN)
            state_callback.assert_change_event(Anything)

        if device_proxy.read_attribute("state").value != state:
            print(f"Turning {device_proxy.dev_name()} {state}")
            set_tango_device_state(
                change_event_callbacks, get_device_proxy, device_name, state
            )
            state_callback.assert_change_event(mode)

    return _set_device_state


def set_tango_device_state(
    change_event_callbacks: MockTangoEventCallbackGroup,
    get_device_proxy: Callable[[str], tango.DeviceProxy],
    device_name: str,
    desired_state: tango.DevState,
) -> None:
    """
    Turn a Tango device on or off using its On() and Off() commands.

    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support.
    :param get_device_proxy: a caching Tango device factory.
    :param device_name: the FQDN of the device.
    :param desired_state: the desired power state, either "on" or "off" or "standby"

    :raises ValueError: if input desired_state is not valid.
    """
    dev = get_device_proxy(device_name)
    # Issue the command
    if desired_state != dev.state():
        if desired_state == tango.DevState.ON:
            [result_code], [command_id] = dev.On()
        elif desired_state == tango.DevState.OFF:
            [result_code], [command_id] = dev.Off()
        elif desired_state == tango.DevState.STANDBY:
            [result_code], [command_id] = dev.Standby()
        else:
            raise ValueError(f"State {desired_state} is not a valid state.")

    assert result_code == ResultCode.QUEUED
    print(f"Command queued on {dev.dev_name()}: {command_id}")

    change_event_callbacks[f"{dev.dev_name()}/state"].assert_change_event(desired_state)


@pytest.fixture(name="queue_command", scope="session")
def queue_command_fixture() -> Callable:
    """
    Queue command on device, check it is queued.

    :returns: A callable which queues command on device, check it is queued.
    """

    def _queue_command(
        device_proxy: tango.DeviceProxy, command: str, args: Any
    ) -> None:
        assert device_proxy.command_inout(command, args)[0] == ResultCode.QUEUED

    return _queue_command


@pytest.fixture(name="check_change_event", scope="session")
def check_change_event_fixture(
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> Callable:
    """
    Check given change event will be called.

    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support.

    :returns: A callable which checks given change event will be called.
    """

    def _check_change_event(
        device_proxy: tango.DeviceProxy, attribute_name: str
    ) -> None:
        device_name = device_proxy.dev_name()
        change_event_callbacks[f"{device_name}/{attribute_name}"].assert_change_event(
            Anything
        )

    return _check_change_event


@pytest.fixture(name="check_attribute", scope="session")
def check_attribute_fixture() -> Callable:
    """
    Check value of device attribute within timeout.

    :returns: A callable which checks value of device attribute.
    """

    def _check_attribute(
        device_proxy: tango.DeviceProxy, attribute_name: str, timeout: float = 3
    ) -> None:
        current_time = time.time()
        value = None
        while time.time() < current_time + timeout:
            try:
                value = device_proxy.read_attribute(attribute_name).value
                break
            except tango.DevFailed:
                time.sleep(0.1)
        assert value is not None, (
            f"Failed to read {device_proxy.dev_name()}/{attribute_name} "
            f"within {timeout}s."
        )
        return value

    return _check_attribute


@pytest.fixture(name="check_fastcommand", scope="session")
def check_fastcommand_fixture() -> Callable:
    """
    Check value of given FastCommand within timeout.

    :returns: A callable which checks value of given FastCommand.
    """

    def _check_fastcommand(
        device_proxy: tango.DeviceProxy, command: str, args: str, timeout: float = 3
    ) -> None:
        current_time = time.time()
        value = None
        while time.time() < current_time + timeout:
            try:
                value = device_proxy.command_inout(command, args)
                break
            except tango.DevFailed:
                time.sleep(0.1)
        assert value is not None, (
            f"Failed to receive value from {device_proxy.dev_name()}/{command}, "
            f"args = {args} within {timeout}s."
        )
        return value

    return _check_fastcommand
