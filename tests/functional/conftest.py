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
import time
from functools import lru_cache
from typing import Callable, Iterator, Optional
from unittest.mock import patch

import _pytest
import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, ResultCode, SimulationMode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.conftest import MAX_NUMBER_OF_SMARTBOXES_PER_STATION
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_field_station_name,
    get_fndh_name,
    get_pasd_bus_name,
    get_smartbox_name,
)


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


@pytest.fixture(name="is_true_context")
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


@pytest.fixture(name="pasd_address")
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


@pytest.fixture(name="station_label")
def station_label_fixture() -> str | None:
    """
    Return the name of the station under test.

    :return: the name of the station under test.
    """
    return os.environ.get("STATION_LABEL", "ci-1")


@pytest.fixture(name="pasd_timeout")
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
    return list(range(1, MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1))


@pytest.fixture(name="smartbox_id", scope="session")
def smartbox_id_under_test_fixture() -> int:
    """
    Return the number of the smartbox under test.

    :return: the number of the smartbox under test.
    """
    return 1


@pytest.fixture(name="smartboxes_under_test")
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
            if f"low-mccs/smartbox/{station_label}-sb" in device_name:
                smartbox_proxy = tango.DeviceProxy(device_name)
                smartboxes_under_test.append(smartbox_proxy)

    return smartboxes_under_test


# pylint: disable=too-many-arguments, too-many-positional-arguments
@pytest.fixture(name="functional_test_context")
def functional_test_context_fixture(
    is_true_context: bool,
    station_label: str,
    pasd_address: tuple[str, int] | None,
    pasd_config_path: str,
    pasd_timeout: float,
    smartbox_ids: list[int],
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

    :yields: a Tango context containing the devices under test
    """
    if not is_true_context:
        with patch("ska_low_mccs_pasd.pasd_utils.Database") as db:
            # pylint: disable=too-many-return-statements
            def my_func(device_name: str, property_name: str) -> list:
                match property_name:
                    case "inputvoltagethresholds":
                        return [50.0, 49.0, 45.0, 40.0]
                    case "powersupplyoutputvoltagethresholds":
                        return [5.0, 4.9, 4.4, 4.0]
                    case "powersupplytemperaturethresholds":
                        return [85.0, 70.0, 0.0, -5.0]
                    case "pcbtemperaturethresholds":
                        return [85.0, 70.0, 0.0, -5.0]
                    case "femambienttemperaturethresholds":
                        return [60.0, 45.0, 0.0, -5.0]
                    case "femcasetemperature1thresholds":
                        return [60.0, 45.0, 0.0, -5.0]
                    case "femcasetemperature2thresholds":
                        return [60.0, 45.0, 0.0, -5.0]
                    case "femheatsinktemperature1thresholds":
                        return [60.0, 45.0, 0.0, -5.0]
                    case "femheatsinktemperature2thresholds":
                        return [60.0, 45.0, 0.0, -5.0]
                    case "femcurrenttripthresholds":
                        return [
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                            496,
                        ]
                return []

            db.return_value.get_device_attribute_property = my_func

            harness = PasdTangoTestHarness(station_label)
            if pasd_address is None:
                # Defer importing from ska_low_mccs_pasd
                # until we know we need to launch a PaSD bus simulator to test against.
                # This ensures that we can use this harness
                # to run tests against a real cluster,
                # from within a pod that does not have ska_low_mccs_pasd installed.
                # pylint: disable-next=import-outside-toplevel
                from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import (
                    PasdBusSimulator,
                )

                # Initialise simulator
                pasd_bus_simulator = PasdBusSimulator(
                    pasd_config_path,
                    station_label,
                    logging.getLogger(),
                    smartboxes_depend_on_attached_ports=True,
                )
                pasd_hw_simulators = pasd_bus_simulator.get_all_devices()
                fndh_ports_with_smartboxes = (
                    pasd_bus_simulator.get_smartbox_attached_ports()
                )
                smartbox_attached_antennas = (
                    pasd_bus_simulator.get_smartbox_ports_connected()
                )
                smartbox_attached_antenna_names = (
                    pasd_bus_simulator.get_antenna_names_on_smartbox()
                )
                # Set devices for test harness
                harness.set_pasd_bus_simulator(pasd_hw_simulators)
                harness.set_pasd_bus_device(
                    timeout=pasd_timeout,
                    polling_rate=0.05,
                    device_polling_rate=0.1,
                    logging_level=int(LoggingLevel.FATAL),
                    available_smartboxes=smartbox_ids,
                )

                for smartbox_id in smartbox_ids:
                    harness.add_smartbox_device(
                        smartbox_id,
                        int(LoggingLevel.ERROR),
                        fndh_port=fndh_ports_with_smartboxes[smartbox_id - 1],
                        ports_with_antennas=[
                            idx + 1
                            for idx, attached in enumerate(
                                smartbox_attached_antennas[smartbox_id - 1]
                            )
                            if attached
                        ],
                        antenna_names=smartbox_attached_antenna_names[smartbox_id - 1],
                    )
                harness.set_fndh_device(
                    int(LoggingLevel.ERROR),
                    ports_with_smartbox=fndh_ports_with_smartboxes,
                )
                harness.set_fncc_device(int(LoggingLevel.ERROR))
                harness.set_field_station_device(smartbox_ids, int(LoggingLevel.ERROR))

            with harness as context:
                yield context
    else:
        harness = PasdTangoTestHarness(station_label)
        with harness as context:
            yield context


@pytest.fixture(name="change_event_callbacks")
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
        timeout=120.0,
        assert_no_error=False,
    )


@pytest.fixture(name="field_station_device")
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


@pytest.fixture(name="pasd_bus_device")
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


@pytest.fixture(name="fndh_device")
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


@pytest.fixture(name="fncc_device")
def fncc_device_fixture(
    functional_test_context: PasdTangoTestHarnessContext,
    subscribe_device_proxy: Callable,
) -> Iterator[tango.DeviceProxy]:
    """
    Return a DeviceProxy to an instance of MccsFNCC.

    :param functional_test_context: context in which the functional tests run.
    :param subscribe_device_proxy: cached fixture for setting up device proxy.

    :yields: A proxy to an instance of MccsFNCC.
    """
    proxy = functional_test_context.get_fncc_device()
    yield subscribe_device_proxy(proxy)


@pytest.fixture(name="device_mapping")
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
        "MccsFncc": functional_test_context.get_fncc_device(),
        "MCCS-for-PaSD": functional_test_context.get_pasd_bus_device(),
        "MccsFieldStation": functional_test_context.get_field_station_device(),
    }
    return device_dict


@pytest.fixture(name="state_mapping")
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


@pytest.fixture(name="device_subscriptions")
def device_subscriptions_fixture(smartbox_id: int) -> dict[str, list[str]]:
    """
    Return a dictionary mapping device name to list of subscriptions to make.

    :param smartbox_id: number of the smartbox under test.
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
            "fndhPsu48vVoltage1",
            "fndhPsu48vVoltage2",
            "fndhPsu48vCurrent",
            "fndhPsu48vTemperature1",
            "fndhPsu48vTemperature2",
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
            "fnccStatus",
            f"smartbox{smartbox_id}Uptime",
            f"smartbox{smartbox_id}Status",
            f"smartbox{smartbox_id}LedPattern",
            f"smartbox{smartbox_id}InputVoltage",
            f"smartbox{smartbox_id}PowerSupplyOutputVoltage",
            f"smartbox{smartbox_id}PowerSupplyTemperature",
            f"smartbox{smartbox_id}PcbTemperature",
            f"smartbox{smartbox_id}FemAmbientTemperature",
            f"smartbox{smartbox_id}FemCaseTemperature1",
            f"smartbox{smartbox_id}FemCaseTemperature2",
            f"smartbox{smartbox_id}FemHeatsinkTemperature1",
            f"smartbox{smartbox_id}FemHeatsinkTemperature2",
            f"smartbox{smartbox_id}PortsPowerSensed",
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

    for i in range(1, MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
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


@pytest.fixture(name="subscribe_device_proxy")
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
        print(f"Check device {device_name} replies to ping...")
        reply_time = 0
        max_attempts = 20
        for i in range(max_attempts):
            try:
                reply_time = proxy.ping()
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                # This is reached in stfc-ci. Not seen in minikube.
                # It will only occur on the first run of a pipeline,
                # immediatly after a deployment.
                # Why is a ping failing? is the readiness probe not working?, is there
                # loads of traffic to a device slowing a reply?
                print(f"failed to ping {repr(e)}")
                if i == max_attempts - 1:
                    raise e
                time.sleep(1)

        print(f"reply received in {reply_time} microseconds")
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


@pytest.fixture(name="set_device_state")
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
            try:
                set_tango_device_state(
                    change_event_callbacks, subscribe_device_proxy, device_proxy, state
                )
            except tango.DevFailed:
                # Try one more time, sometimes we lose communication
                time.sleep(10)
                print("Retrying set_tango_device_state")
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
    result_code = ResultCode.UNKNOWN
    command_id = ""
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
            desired_state, lookahead=6, consume_nonmatches=True
        )
    assert dev.state() == desired_state


@pytest.fixture(name="check_change_event")
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


@pytest.fixture(name="check_attribute")
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


@pytest.fixture(name="check_fastcommand")
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


def is_running_in_kubernetes() -> bool:
    """
    Check if test is running in kubernetes.

    :return: if test is running in kubernetes.
    """
    # Check for Kubernetes environment variable
    kubernetes_service_host = os.getenv("KUBERNETES_SERVICE_HOST")
    # Check for Kubernetes service account files
    service_account_path = "/var/run/secrets/kubernetes.io/serviceaccount"
    return kubernetes_service_host is not None and os.path.exists(service_account_path)
