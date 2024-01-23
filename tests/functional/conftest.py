# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains pytest-specific test harness for PaSD functional tests."""
import os
import time
import unittest.mock
from functools import lru_cache
from typing import Any, Callable, Iterator, Optional

import _pytest
import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, ResultCode, SimulationMode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_field_station_name,
    get_fndh_name,
    get_pasd_bus_name,
    get_smartbox_name,
)

NUMBER_OF_ANTENNA = 256
NUMBER_OF_SMARTBOX = 24
NUMBER_OF_SMARTBOX_PORTS = 12


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


@pytest.fixture(name="is_true_context", scope="module")
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


@pytest.fixture(name="pasd_address", scope="module")
def pasd_address_fixture() -> tuple[str, int] | None:
    """
    Return the address of the PaSD.

    If a real hardware PaSD is present, or there is a pre-existing
    simulator, then this fixture returns the PaSD address as a
    (hostname, port) tuple. If there is no pre-existing PaSD,
    then this fixture returns None, indicating that the test harness
    should stand up a PaSD simulator server itself.

    :return: the address of the PaSD,
        or None if no PaSD (genuine or simulated) is available.
    """
    address_var = "PASD_ADDRESS"
    if address_var in os.environ:
        [host, port_str] = os.environ[address_var].split(":")
        return host, int(port_str)
    return None


@pytest.fixture(name="station_label", scope="module")
def station_label_fixture() -> str | None:
    """
    Return the name of the station under test.

    :return: the name of the station under test.
    """
    return os.environ.get("STATION_LABEL", "ci-1")


@pytest.fixture(name="pasd_timeout", scope="module")
def pasd_timeout_fixture() -> Optional[float]:
    """
    Return the timeout to use when communicating with the PaSD.

    :return: the timeout to use when communicating with the PaSD.
    """
    return 5.0


@pytest.fixture(name="smartbox_ids", scope="session")
def smartbox_ids_fixture() -> list[int]:
    """
    Return a list of smartbox IDs to use in a test.

    :return: a list of smartbox IDs to use in a test
    """
    return list(range(1, 25))


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


@pytest.fixture(name="smartboxes_under_test", scope="module")
def smartboxes_under_test_fixture(
    is_true_context: bool,
    smartbox_ids: list[int],
    station_label: str,
    functional_test_context: PasdTangoTestHarnessContext,
) -> list[tango.DeviceProxy]:
    """
    Return a list of the smartboxes under test.

    :param is_true_context: whether to test against an existing Tango
        deployment
    :param smartbox_ids: a list of the smarbox id's used in this test.
    :param station_label: name of the station under test.
    :param functional_test_context: context in which the functional tests run.

    :return: a list of device proxies to use in this test.
    """
    smartboxes_under_test = []

    if not is_true_context:
        for smartbox_id in smartbox_ids:
            smartboxes_under_test.append(
                functional_test_context.get_smartbox_device(smartbox_id)
            )
    else:
        db = tango.Database()
        devices_exported = db.get_device_exported("*")
        for device_name in devices_exported:
            if f"low-mccs/smartbox/{station_label}" in device_name:
                smartbox_proxy = tango.DeviceProxy(device_name)
                smartboxes_under_test.append(smartbox_proxy)

    return smartboxes_under_test


@pytest.fixture(name="functional_test_context", scope="module")
def functional_test_context_fixture(  # pylint: disable=too-many-arguments
    is_true_context: bool,
    station_label: str,
    pasd_address: tuple[str, int] | None,
    pasd_config_path: str,
    pasd_timeout: float,
    smartbox_ids: list[int],
    configuration_manager: unittest.mock.Mock,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Yield a Tango context containing the device/s under test.

    :param is_true_context: whether to test against an existing Tango
        deployment
    :param station_label: name of the station under test.
    :param pasd_address: address of the PaSD, if already present
    :param pasd_config_path: configuration file from which to configure
        a simulator if necessary
    :param pasd_timeout: timeout to use with the PaSD
    :param smartbox_ids: a list of the smarbox id's used in this test.
    :param configuration_manager: a mock configuration manager to manage a
        configuration for the field station

    :yields: a Tango context containing the devices under test
    """
    harness = PasdTangoTestHarness(station_label)

    if not is_true_context:
        if pasd_address is None:
            # Defer importing from ska_low_mccs_pasd
            # until we know we need to launch a PaSD bus simulator to test against.
            # This ensures that we can use this harness
            # to run tests against a real cluster,
            # from within a pod that does not have ska_low_mccs_pasd installed.
            # pylint: disable-next=import-outside-toplevel
            from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import PasdBusSimulator

            # Initialise simulator
            pasd_bus_simulator = PasdBusSimulator(
                pasd_config_path,
                station_label,
                smartboxes_depend_on_attached_ports=True,
            )
            pasd_hw_simulators = pasd_bus_simulator.get_fndh_and_smartboxes()
            # Set devices for test harness
            harness.set_pasd_bus_simulator(pasd_hw_simulators)
            harness.set_configuration_server(configuration_manager)
            harness.set_pasd_bus_device(
                timeout=pasd_timeout,
                polling_rate=0.05,
                device_polling_rate=0.1,
                logging_level=int(LoggingLevel.DEBUG),
            )

            for smartbox_id in smartbox_ids:
                harness.add_smartbox_device(smartbox_id=smartbox_id)
            harness.set_fndh_device()
            harness.set_field_station_device(smartbox_numbers=smartbox_ids)

    with harness as context:
        yield context


@pytest.fixture(name="change_event_callbacks", scope="module")
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
        timeout=500.0,
        assert_no_error=False,
    )


@pytest.fixture(name="field_station_device", scope="module")
def field_station_device_fixture(
    functional_test_context: PasdTangoTestHarnessContext,
    subscribe_device_proxy: Callable,
) -> Iterator[tango.DeviceProxy]:
    """
    Return a DeviceProxy to an instance of MccsFieldStation.

    :param functional_test_context: context in which the functional tests run.
    :param subscribe_device_proxy: cached fixture for setting up device proxy.

    :yields: A proxy to an instance of MccsFieldStation.
    """
    proxy = functional_test_context.get_field_station_device()
    yield subscribe_device_proxy(proxy)


@pytest.fixture(name="pasd_bus_device", scope="module")
def pasd_bus_device_fixture(
    functional_test_context: PasdTangoTestHarnessContext,
    subscribe_device_proxy: Callable,
) -> Iterator[tango.DeviceProxy]:
    """
    Return a DeviceProxy to an instance of MccsPasdBus.

    :param functional_test_context: context in which the functional tests run.
    :param subscribe_device_proxy: cached fixture for setting up device proxy.

    :yields: A proxy to an instance of MccsPasdBus.
    """
    proxy = functional_test_context.get_pasd_bus_device()
    yield subscribe_device_proxy(proxy)


@pytest.fixture(name="fndh_device", scope="module")
def fndh_device_fixture(
    functional_test_context: PasdTangoTestHarnessContext,
    subscribe_device_proxy: Callable,
) -> Iterator[tango.DeviceProxy]:
    """
    Return a DeviceProxy to an instance of MccsFNDH.

    :param functional_test_context: context in which the functional tests run.
    :param subscribe_device_proxy: cached fixture for setting up device proxy.

    :yields: A proxy to an instance of MccsFNDH.
    """
    proxy = functional_test_context.get_fndh_device()
    yield subscribe_device_proxy(proxy)


@pytest.fixture(name="device_mapping", scope="module")
def device_mapping_fixture(
    functional_test_context: PasdTangoTestHarnessContext,
) -> dict[str, tango.DeviceProxy]:
    """
    Return a dictionary mapping Gherkin reference to device proxy.

    :param functional_test_context: context in which the functional tests run.

    :return: A dictionary mapping Gherkin reference to device proxy.
    """
    device_dict = {
        "MccsFndh": functional_test_context.get_fndh_device(),
        "MCCS-for-PaSD": functional_test_context.get_pasd_bus_device(),
        "MccsFieldStation": functional_test_context.get_field_station_device(),
    }
    return device_dict


@pytest.fixture(name="state_mapping", scope="module")
def state_mapping_fixture() -> dict[str, tango.DevState]:
    """
    Return a dictionary mapping Gherkin reference to device state.

    :return: A dictionary mapping Gherkin reference to device state.
    """
    state_mapping_dict = {
        "OFF": tango.DevState.OFF,
        "ON": tango.DevState.ON,
    }
    return state_mapping_dict


@pytest.fixture(name="device_subscriptions", scope="module")
def device_subscriptions_fixture() -> dict[str, list[str]]:
    """
    Return a dictionary mapping device name to list of subscriptions to make.

    :return: A dictionary mapping device name to list of subscriptions to make.
    """
    device_subscriptions = {
        get_pasd_bus_name(): [
            "state",
            "healthState",
            "adminMode",
            "fndhUptime",
            "fndhStatus",
            "fndhLedPattern",
            "fndhPsu48vVoltages",
            "fndhPsu48vCurrent",
            "fndhPsu48vTemperatures",
            "fndhPanelTemperature",
            "fndhFncbTemperature",
            "fndhFncbHumidity",
            "fndhCommsGatewayTemperature",
            "fndhPowerModuleTemperature",
            "fndhOutsideTemperature",
            "fndhInternalAmbientTemperature",
            "fndhPortForcings",
            "fndhPortsDesiredPowerOnline",
            "fndhPortsDesiredPowerOffline",
            "fndhPortsPowerSensed",
            "fndhPortsPowerControl",
            "smartbox1Uptime",
            "smartbox1Status",
            "smartbox1LedPattern",
            "smartbox1InputVoltage",
            "smartbox1PowerSupplyOutputVoltage",
            "smartbox1PowerSupplyTemperature",
            "smartbox1PcbTemperature",
            "smartbox1FemAmbientTemperature",
            "smartbox1FemCaseTemperatures",
            "smartbox1FemHeatsinkTemperatures",
            "smartbox1PortsPowerSensed",
            "smartbox24AlarmFlags",
        ],
        get_fndh_name(): [
            "state",
            "healthState",
            "adminMode",
        ],
        get_field_station_name(): [
            "state",
            "healthState",
            "adminMode",
        ],
    }

    for i in range(1, NUMBER_OF_SMARTBOX + 1):
        device_subscriptions.update(
            {
                get_smartbox_name(i): [
                    "state",
                    "healthState",
                    "adminMode",
                ],
            }
        )

    return device_subscriptions


@pytest.fixture(name="subscribe_device_proxy", scope="module")
def subscribe_device_proxy_fixture(
    device_subscriptions: dict[str, list[str]],
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> Callable[[tango.DeviceProxy], tango.DeviceProxy]:
    """
    Return a cached device proxy with subscriptions set up.

    :param device_subscriptions: list of subscriptions to make.
    :param change_event_callbacks: a dictionary of callables to be used as
        tango change event callbacks.

    :return: A cached device proxy with subscriptions set up.
    """

    @lru_cache
    def _subscribe_device_proxy(proxy: tango.DeviceProxy) -> tango.DeviceProxy:
        device_name = proxy.dev_name()
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

    return _subscribe_device_proxy


@pytest.fixture(name="set_device_state", scope="module")
def set_device_state_fixture(
    device_mapping: dict[str, tango.DeviceProxy],
    subscribe_device_proxy: Callable,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> Callable:
    """
    Set device state.

    :param device_mapping: A dictionary mapping short name to FQDN for devices
        under test.
    :param subscribe_device_proxy: A cached device proxy with subscriptions set up.
    :param change_event_callbacks: a dictionary of callables to be used as
        tango change event callbacks.

    :return: A function to set device state.
    """

    def _set_device_state(
        device_ref: str,
        state: tango.DevState,
        mode: AdminMode,
        simulation_mode: SimulationMode,
        device_proxy: Optional[tango.DeviceProxy] = None,
    ) -> None:
        if device_proxy is None:
            device_proxy = device_mapping[device_ref]

        subscribe_device_proxy(device_proxy)
        device_name = device_proxy.dev_name()

        admin_mode_callback = change_event_callbacks[f"{device_name}/adminMode"]
        state_callback = change_event_callbacks[f"{device_name}/state"]
        device_proxy.simulationMode = simulation_mode
        if device_proxy.adminMode != mode:
            device_proxy.adminMode = mode
            admin_mode_callback.assert_change_event(mode)
            if mode != AdminMode.OFFLINE:
                state_callback.assert_change_event(tango.DevState.UNKNOWN)
            state_callback.assert_change_event(Anything)

        if device_proxy.read_attribute("state").value != state:
            print(f"Turning {device_proxy.dev_name()} {state}")
            set_tango_device_state(
                change_event_callbacks, subscribe_device_proxy, device_proxy, state
            )

    return _set_device_state


def set_tango_device_state(
    change_event_callbacks: MockTangoEventCallbackGroup,
    subscribe_device_proxy: Callable[[tango.DeviceProxy], tango.DeviceProxy],
    dev: tango.DeviceProxy,
    desired_state: tango.DevState,
) -> None:
    """
    Turn a Tango device on or off using its On() and Off() commands.

    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support.
    :param subscribe_device_proxy: a caching Tango device factory.
    :param dev: proxy to the device.
    :param desired_state: the desired power state, either "on" or "off" or "standby"

    :raises ValueError: if input desired_state is not valid.
    """
    subscribe_device_proxy(dev)
    initial_state = dev.state()
    # Issue the command
    if desired_state != initial_state:
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
    if initial_state != desired_state:
        change_event_callbacks[f"{dev.dev_name()}/state"].assert_change_event(
            desired_state
        )
    assert dev.state() == desired_state


@pytest.fixture(name="check_change_event", scope="module")
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


@pytest.fixture(name="check_attribute", scope="module")
def check_attribute_fixture() -> Callable:
    """
    Check value of device attribute within timeout.

    :returns: A callable which checks value of device attribute.
    """

    def _check_attribute(
        device_proxy: tango.DeviceProxy, attribute_name: str, timeout: float = 60
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


@pytest.fixture(name="check_fastcommand", scope="module")
def check_fastcommand_fixture() -> Callable:
    """
    Check value of given FastCommand within timeout.

    :returns: A callable which checks value of given FastCommand.
    """

    def _check_fastcommand(  # TODO: reduce the timeout to 3
        device_proxy: tango.DeviceProxy, command: str, args: str, timeout: float = 4
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


@pytest.fixture(scope="module")
def clipboard() -> dict:
    """
    Return a dictionary to be used to store contextual information across steps.

    :return: a dictionary to be used to store contextual information across steps.
    """
    return {}
