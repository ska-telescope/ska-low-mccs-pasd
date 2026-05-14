# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Functional test for aborting a FieldStation ON command mid-flight."""
from __future__ import annotations

import gc
import json
import time
from typing import Callable

import pytest
import tango
from pytest_bdd import given, scenario, then, when
from ska_control_model import AdminMode, ResultCode, SimulationMode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.conftest import MAX_NUMBER_OF_SMARTBOXES_PER_STATION
from tests.harness import (
    get_field_station_name,
    get_fndh_name,
    get_pasd_bus_name,
    get_smartbox_name,
)

gc.disable()


class _LrcAbortCompleted:
    """Matches lrcFinished values whose last JSON entry signals Abort completed OK."""

    def __eq__(self, other: object) -> bool:
        if not other:
            return False
        try:
            info = json.loads(other[-1])  # type: ignore[index]
            return info.get("result", [None, None])[1] == "Abort completed OK"
        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class _LrcUidResult:
    """Matches lrcFinished values whose last JSON entry has a given uid and result."""

    def __init__(self, uid: str, result_code: ResultCode) -> None:
        self._uid = uid
        self._result_code = result_code

    def __eq__(self, other: object) -> bool:
        if not other:
            return False
        try:
            info = json.loads(other[-1])  # type: ignore[index]
            return info.get("uid") == self._uid and info.get("result", [None])[
                0
            ] == int(self._result_code)
        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


@pytest.fixture(name="smartbox_ids")
def smartbox_ids_fixture() -> list[int]:
    """
    Return the 12 smartbox IDs matching the ci-1 minikube deployment.

    :return: smartbox IDs 1-12.
    """
    return list(range(1, 13))


@pytest.fixture(name="device_subscriptions")
def device_subscriptions_fixture(
    smartbox_id: int, station_label: str
) -> dict[str, list[str]]:
    """
    Return device subscriptions, adding lrcFinished for FieldStation, FNDH and PasdBus.

    :param smartbox_id: ID of the primary smartbox under test.
    :param station_label: label of the station under test.
    :return: mapping of device name to subscribed attribute names.
    """
    device_subscriptions: dict[str, list[str]] = {
        get_pasd_bus_name(station_label=station_label): [
            "state",
            "healthState",
            "adminMode",
            "lrcFinished",
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
        get_fndh_name(station_label=station_label): [
            "state",
            "healthState",
            "adminMode",
            "lrcFinished",
        ],
        get_field_station_name(station_label=station_label): [
            "state",
            "healthState",
            "adminMode",
            "lrcFinished",
        ],
    }
    for i in range(1, MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        device_subscriptions[get_smartbox_name(i, station_label=station_label)] = [
            "state",
            "healthState",
            "adminMode",
        ]
    return device_subscriptions


@scenario(
    "features/field_station_abort.feature",
    "FieldStation ON command is aborted mid-flight",
)
def test_field_station_abort_during_on() -> None:
    """Test that a FieldStation ON command can be aborted mid-flight."""


@given("all PaSD devices are ready and initialised")
def all_pasd_devices_ready(
    set_device_state: Callable,
    pasd_bus_device: tango.DeviceProxy,
    smartboxes_under_test: list[tango.DeviceProxy],
) -> None:
    """
    Bring all PaSD devices into a ready, communicating state.

    FNDH is left in STANDBY (ports unpowered) and smartboxes in OFF so that
    the subsequent FieldStation ON command has to power everything up from
    scratch, without going through an unnecessary ON→OFF cycle.

    :param set_device_state: fixture to set a device's state and admin mode.
    :param pasd_bus_device: proxy to MccsPasdBus.
    :param smartboxes_under_test: proxies to the 12 MccsSmartBox devices.
    """
    set_device_state(
        "MCCS-for-PaSD",
        state=tango.DevState.ON,
        mode=AdminMode.ONLINE,
        simulation_mode=SimulationMode.TRUE,
    )
    pasd_bus_device.initializefndh()
    for i in range(1, len(smartboxes_under_test) + 1):
        pasd_bus_device.initializesmartbox(i)
    set_device_state(
        "MccsFndh",
        state=tango.DevState.STANDBY,
        mode=AdminMode.ONLINE,
        simulation_mode=SimulationMode.TRUE,
    )
    for smartbox in smartboxes_under_test:
        set_device_state(
            device_proxy=smartbox,
            device_ref="",
            state=tango.DevState.OFF,
            mode=AdminMode.ONLINE,
            simulation_mode=SimulationMode.TRUE,
        )


@given("the FieldStation is in the OFF state")
def field_station_is_off(set_device_state: Callable) -> None:
    """
    Put the FieldStation into the OFF state with ONLINE admin mode.

    :param set_device_state: fixture to set a device's state and admin mode.
    """
    set_device_state(
        "MccsFieldStation",
        state=tango.DevState.OFF,
        mode=AdminMode.ONLINE,
        simulation_mode=SimulationMode.TRUE,
    )


@when("I start turning the FieldStation ON")
def start_field_station_on(
    field_station_device: tango.DeviceProxy,
    clipboard: dict,
) -> None:
    """
    Issue the ON command to the FieldStation and store the command ID.

    :param field_station_device: proxy to MccsFieldStation.
    :param clipboard: shared dict for passing data between steps.
    """
    [result_code], [on_command_id] = field_station_device.On()
    assert result_code == ResultCode.QUEUED
    clipboard["on_command_id"] = on_command_id


@when("smartboxes 1 to 6 reach STANDBY")
def smartboxes_reach_standby(
    change_event_callbacks: MockTangoEventCallbackGroup,
    station_label: str,
) -> None:
    """
    Wait for smartboxes 1 to 6 to each reach STANDBY state.

    The FieldStation ON command turns on FNDH ports first (causing
    smartboxes to power up and reach STANDBY), then iterates through
    smartbox blocks. Waiting for smartboxes 1-6 proves the FNDH phase
    is complete and we are in the smartbox iteration phase.

    :param change_event_callbacks: Tango change event callbacks.
    :param station_label: label of the station under test.
    """
    for sb_id in range(1, 7):
        sb_name = get_smartbox_name(sb_id, station_label=station_label)
        change_event_callbacks[f"{sb_name}/state"].assert_change_event(
            tango.DevState.STANDBY,
            lookahead=10,
            consume_nonmatches=True,
        )


@when("I abort the FieldStation")
def abort_field_station(
    field_station_device: tango.DeviceProxy,
    clipboard: dict,
) -> None:
    """
    Abort the FieldStation and store the abort command ID.

    :param field_station_device: proxy to MccsFieldStation.
    :param clipboard: shared dict for passing data between steps.
    """
    [[result_code], [abort_command_id]] = field_station_device.Abort()
    assert ResultCode(result_code) == ResultCode.STARTED
    clipboard["abort_command_id"] = abort_command_id


@then("the FieldStation does not reach the ON state")
def field_station_does_not_reach_on(
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Assert the FieldStation never transitions to ON after the abort.

    Polls the device state for up to 30 seconds. Fails immediately if
    ON is reached; returns early once the state has been stable and
    non-ON for 3 consecutive seconds.

    :param field_station_device: proxy to MccsFieldStation.
    """
    deadline = time.time() + 30
    last_state = None
    same_state_since = time.time()
    while time.time() < deadline:
        state = field_station_device.state()
        assert (
            state != tango.DevState.ON
        ), "FieldStation reached ON state despite Abort() being called"
        if state != last_state:
            last_state = state
            same_state_since = time.time()
        elif time.time() - same_state_since > 3:
            return
        time.sleep(0.5)
    assert field_station_device.state() != tango.DevState.ON


@then("the On commands were aborted and Abort commands completed OK")
def on_commands_aborted_abort_commands_completed(
    change_event_callbacks: MockTangoEventCallbackGroup,
    clipboard: dict,
    station_label: str,
) -> None:
    """
    Assert that the On commands were aborted and the Abort commands completed OK.

    Uses lookahead with consume_nonmatches=False so that earlier events
    (e.g. from setup commands) are not consumed and each search finds its
    target independently.

    :param change_event_callbacks: Tango change event callbacks.
    :param clipboard: shared dict carrying on_command_id and abort_command_id.
    :param station_label: label of the station under test.
    """
    fs_name = get_field_station_name(station_label=station_label)
    fndh_name = get_fndh_name(station_label=station_label)
    pasd_bus_name = get_pasd_bus_name(station_label=station_label)

    change_event_callbacks[f"{fs_name}/lrcFinished"].assert_change_event(
        _LrcUidResult(clipboard["on_command_id"], ResultCode.ABORTED),
        lookahead=10,
    )
    change_event_callbacks[f"{fs_name}/lrcFinished"].assert_change_event(
        _LrcUidResult(clipboard["abort_command_id"], ResultCode.OK),
        lookahead=10,
    )
    change_event_callbacks[f"{fndh_name}/lrcFinished"].assert_change_event(
        _LrcAbortCompleted(),
        lookahead=10,
    )
    change_event_callbacks[f"{pasd_bus_name}/lrcFinished"].assert_change_event(
        _LrcAbortCompleted(),
        lookahead=10,
    )
