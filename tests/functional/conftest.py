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
from functools import lru_cache
from typing import (
    Callable,
    ContextManager,
    Generator,
    Iterator,
    Optional,
    Union,
    cast,
)
import time

import _pytest
import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, ResultCode
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
    TrueTangoContextManager,
)
from pytest_bdd import given, parsers, scenario, then, when
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


@pytest.fixture(name="pasd_address_context_manager_factory", scope="session")
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
        def launch_simulator_server() -> Iterator[
            tuple[str | bytes | bytearray, int]
        ]:
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


@pytest.fixture(name="fndh_name", scope="session")
def fqdn_name_fixture() -> str:
    """
    Return the name of the FNDH device under test.

    :return: the name of the FNDH device under test.
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
    true_context: bool,
    pasd_bus_name: str,
    pasd_address_context_manager_factory: Callable[
        [], ContextManager[tuple[str, int]]
    ],
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
            cast(
                ThreadedTestTangoContextManager, tango_context_manager
            ).add_device(
                pasd_bus_name,
                "ska_low_mccs_pasd.MccsPasdBus",
                Host=pasd_host,
                Port=pasd_port,
                Timeout=pasd_timeout,
                LoggingLevelDefault=int(LoggingLevel.DEBUG),
            )
            with tango_context_manager as context:
                yield context


@pytest.fixture(name="change_event_callbacks", scope="session")
def change_event_callbacks_fixture(device_subscriptions: dict[str,list]) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

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


@pytest.fixture(name="pasd_bus_device", scope="session")
def pasd_bus_device_fixture(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
    change_event_callbacks: MockTangoEventCallbackGroup,
    get_device_proxy: Callable
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsPasdBus.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: the name of the PaSD bus device under test.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.

    :return: A proxy to an instance of MccsPasdBus.
    """
    # proxy = tango_harness.get_device(pasd_bus_name)

    # for attribute_name in [
    #     "state",
    #     "healthState",
    #     "fndhUptime",
    #     "fndhStatus",
    #     "fndhLedPattern",
    #     "fndhPsu48vVoltages",
    #     "fndhPsu48vCurrent",
    #     "fndhPsu48vTemperature",
    #     "fndhPsu5vVoltage",
    #     "fndhPsu5vTemperature",
    #     "fndhPcbTemperature",
    #     "fndhOutsideTemperature",
    #     "fndhPortsConnected",
    #     "fndhPortsPowerSensed",
    #     "smartbox1Uptime",
    #     "smartbox1Status",
    #     "smartbox1LedPattern",
    #     "smartbox1InputVoltage",
    #     "smartbox1PowerSupplyOutputVoltage",
    #     "smartbox1PowerSupplyTemperature",
    #     "smartbox1PcbTemperature",
    #     "smartbox1OutsideTemperature",
    #     "smartbox1PortsConnected",
    #     "smartbox1PortsPowerSensed",
    # ]:
    #     print(f"Subscribing proxy to {attribute_name}...")
    #     proxy.subscribe_event(
    #         attribute_name,
    #         tango.EventType.CHANGE_EVENT,
    #         change_event_callbacks[attribute_name],
    #     )
    #     change_event_callbacks.assert_change_event(attribute_name, Anything)

    return get_device_proxy(pasd_bus_name)


@pytest.fixture(name="device_mapping", scope="session")
def device_mapping_fixture(fndh_name, pasd_bus_name,):
    device_dict = {"MccsFndh": fndh_name, "MCCS-for-PaSD": pasd_bus_name}
    return device_dict

@pytest.fixture(name="device_subscriptions", scope="session")
def device_subscriptions_fixture(fndh_name, pasd_bus_name):
    device_subscriptions = {
        pasd_bus_name: [
            "state",
            "healthState",
            "adminMode",
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
        ],
        fndh_name: [
            "state",
            "healthState",
            "adminMode",
        ]
    }
    return device_subscriptions


@pytest.fixture(name="get_device_proxy", scope="session")
def get_device_proxy_fixture(device_subscriptions: list[str], tango_harness: TangoContextProtocol, change_event_callbacks: MockTangoEventCallbackGroup) -> tango.DeviceProxy:

    @lru_cache
    def _get_device_proxy(device_name: str):    
        proxy = tango_harness.get_device(device_name)
        print(f"Creating proxy for {device_name}")
        for attribute_name in device_subscriptions[device_name]:
            print(f"Subscribing proxy to {device_name}/{attribute_name}...")
            proxy.subscribe_event(
                attribute_name,
                tango.EventType.CHANGE_EVENT,
                change_event_callbacks[f"{device_name}/{attribute_name}"],
            )
            #print(proxy.read_attribute(attribute_name).value)
            time.sleep(0.1)
            change_event_callbacks.assert_change_event(f"{device_name}/{attribute_name}", Anything,lookahead=50)
        return proxy

    return _get_device_proxy


@pytest.fixture(name="set_device_state", scope="session")
def set_device_state_fixture(
    # device: str,
    # state: tango.DevState,
    # mode: AdminMode,
    device_mapping: dict[str],
    get_device_proxy: Callable,
    change_event_callbacks,
    ) -> None:
    """
    Hello World.

    123
    """
    def _set_device_state(device, state, mode):
        device_name = device_mapping[device]

        device_proxy = get_device_proxy(device_name)

        admin_mode_callback = change_event_callbacks[f"{device_name}/adminMode"]
        if device_proxy.adminMode != mode:
            device_proxy.adminMode = mode
            admin_mode_callback.assert_change_event(mode)
        # else:
        #     admin_mode_callback.assert_not_called()
        print(device_proxy.adminMode)
        print(mode)
        time.sleep(5)
        state_callback = change_event_callbacks[f"{device_name}/state"]
        if device_proxy.read_attribute("state").value != state:
            print(f"Turning {device_proxy.dev_name()} {state}")
            set_tango_device_state(change_event_callbacks, get_device_proxy, device_name, state)
            state_callback.assert_change_event(mode)
        # else:
        #     state_callback.assert_not_called()
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
        callbacks with asynchrony support
    :param get_device: a caching Tango device factory
    :param short_name: the short name of the device
    :param desired_state: the desired power state, either "on" or "off"
    """
    dev = get_device_proxy(device_name)
    # Issue the command
    print(dev.state())
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

    # while not (
    #     result_code == "COMPLETED"
    #     or (
    #         # status to FAILED even when it succeeds in turning its TPM on
    #         dev.info().dev_class == "MccsTile"
    #         and result_code == "FAILED"
    #     )
    # ):
    #     call_details = change_event_callbacks[
    #         f"{dev.dev_name()}/longRunningCommandStatus"
    #     ].assert_against_call()
    #     print(f"LRCS on {dev.dev_name()}: {call_details['attribute_value']}")
    #     assert call_details["attribute_value"][-2] == command_id
    #     result_code = call_details["attribute_value"][-1]
    # time.sleep(5)
    change_event_callbacks[f"{dev.dev_name()}/state"].assert_change_event(desired_state,lookahead=100)


@given(parsers.parse("A {device} which is ready"))
def get_ready_device(device: str, set_device_state: Callable) -> None:
    """
    Get ready device
    """
    print(device)
    set_device_state(device=device, state=tango.DevState.ON, mode=AdminMode.ONLINE)

@given(parsers.parse("A {device} which is not ready"))
def get_not_ready_device(device: str, set_device_state: Callable) -> None:
    """
    Get ready device
    """
    print(device)
    set_device_state(device=device, state=tango.DevState.DISABLE, mode=AdminMode.OFFLINE)

