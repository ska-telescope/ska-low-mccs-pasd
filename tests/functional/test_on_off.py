# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple tests of the pasd on off."""
from __future__ import annotations

import gc
from typing import Callable

import pytest
import tango
from pytest_bdd import given, scenario, then, when
from ska_control_model import AdminMode, HealthState
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.harness import get_field_station_name, get_pasd_bus_name

gc.disable()


@scenario(
    "features/on_off.feature",
    "Initialise PaSD devices",
)
def test_inititalise() -> None:
    """
    Test basic initialise of pasd.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@scenario(
    "features/on_off.feature",
    "Turn off PaSD devices",
)
def test_turn_off_pasd() -> None:
    """
    Test power off of pasd.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@scenario(
    "features/on_off.feature",
    "Turn on PaSD devices",
)
def test_turn_on_pasd() -> None:
    """
    Test power on of pasd.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given("A pasd setup that is connected to hardware")
def check_against_hardware(hw_context: bool) -> None:
    """
    Skip the test if not in real context.

    :param hw_context: whether or not the current context is against real HW.
    """
    if not hw_context:
        pytest.skip("This test requires real context.")


@given("pasd is in DISABLE state")
def get_devices_disabled(set_device_state: Callable) -> None:
    """
    Get device in state DISABLE and adminmode OFFLINE.

    :param set_device_state: function to set device state.
    """
    print("Setting device pasd_bus not ready...")
    set_device_state(
        "MCCS-for-PaSD",
        state=tango.DevState.DISABLE,
        mode=AdminMode.OFFLINE,
    )
    print("Setting device FieldStation not ready...")
    set_device_state(
        "MccsFieldStation",
        state=tango.DevState.DISABLE,
        mode=AdminMode.OFFLINE,
    )


@given("pasd has UNKNOWN health")
def pasd_has_unknown_health(
    pasd_bus_device: tango.DeviceProxy,
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Assert pasd devices are in health state UNKNOWN.

    :param pasd_bus_device: proxy to pasd bus.
    :param field_station_device: proxy to field station.
    """
    assert pasd_bus_device.healthState == HealthState.UNKNOWN
    assert field_station_device.healthState == HealthState.UNKNOWN


@given("pasd has OK health")
def pasd_has_ok_health(
    pasd_bus_device: tango.DeviceProxy,
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Assert pasd devices are in health state ok.

    :param pasd_bus_device: proxy to pasd bus.
    :param field_station_device: proxy to field station.
    """
    assert pasd_bus_device.healthState == HealthState.OK
    assert field_station_device.healthState == HealthState.OK


@given("pasd is in ON state")
def get_devices_on(set_device_state: Callable) -> None:
    """
    Get device in state ON and adminmode ONLINE.

    :param set_device_state: function to set device state.
    """
    print("Setting device pasd_bus to on...")
    set_device_state(
        "MCCS-for-PaSD",
        state=tango.DevState.ON,
        mode=AdminMode.ONLINE,
    )
    print("Setting device FieldStation to on...")
    set_device_state(
        "MccsFieldStation",
        state=tango.DevState.ON,
        mode=AdminMode.ONLINE,
    )


@given("pasd is in OFF state")
def get_devices_off(set_device_state: Callable) -> None:
    """
    Get device in state OFF and adminmode OFFLINE.

    :param set_device_state: function to set device state.
    """
    print("Setting device pasd_bus to off...")
    set_device_state(
        "MCCS-for-PaSD",
        state=tango.DevState.OFF,
        mode=AdminMode.OFFLINE,
    )
    print("Setting device FieldStation not ready...")
    set_device_state(
        "MccsFieldStation",
        state=tango.DevState.OFF,
        mode=AdminMode.OFFLINE,
    )


@when("pasd adminMode is set to ONLINE")
def pasd_set_online(
    pasd_bus_device: tango.DeviceProxy,
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Set the pasd devices into adminmode ONLINE.

    :param pasd_bus_device: proxy to pasd bus.
    :param field_station_device: proxy to field station.
    """
    pasd_bus_device.adminmode == AdminMode.ONLINE
    field_station_device.adminmode == AdminMode.ONLINE


@when("field station is turned on")
def fieldstation_turned_on(
    pasd_bus_device: tango.DeviceProxy,
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Turn field station on.

    :param pasd_bus_device: proxy to pasd bus.
    :param field_station_device: proxy to field station.
    """
    pasd_bus_device.adminmode == AdminMode.ONLINE
    field_station_device.adminmode == AdminMode.ONLINE
    field_station_device.on()


@when("field station is turned off")
def fieldstation_turned_off(
    pasd_bus_device: tango.DeviceProxy,
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Turn field station off.

    Set the field station devices into adminmode ONLINE.

    :param pasd_bus_device: proxy to pasd bus.
    :param field_station_device: proxy to field station.
    """
    pasd_bus_device.adminmode == AdminMode.ONLINE
    field_station_device.adminmode == AdminMode.ONLINE
    field_station_device.off()


@then("pasd reports ON state")
def pasd_reports_online(
    change_event_callbacks: MockTangoEventCallbackGroup, station_label: str
) -> None:
    """
    Assert the pasd devices are ON.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param station_label: The label of the station under test.
    """
    change_event_callbacks[
        f"{get_pasd_bus_name(station_label=station_label)}/state"
    ].assert_change_event(
        tango.DevState.ON,
        lookahead=10,  # TODO: We only need 3 in lightweight testing. Why?
        consume_nonmatches=True,
    )
    print("PaSD bus device is in ON state.")
    change_event_callbacks[
        f"{get_field_station_name(station_label)}/state"
    ].assert_change_event(
        tango.DevState.ON,
        lookahead=10,  # TODO: We only need 3 in lightweight testing. Why?
        consume_nonmatches=True,
    )
    print("field station device is in ON state.")


@then("pasd reports OFF state")
def pasd_reports_offline(
    change_event_callbacks: MockTangoEventCallbackGroup, station_label: str
) -> None:
    """
    Assert the pasd devices are OFF.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param station_label: The label of the station under test.
    """
    change_event_callbacks[
        f"{get_pasd_bus_name(station_label=station_label)}/state"
    ].assert_change_event(
        tango.DevState.OFF,
        lookahead=10,  # TODO: We only need 3 in lightweight testing. Why?
        consume_nonmatches=True,
    )
    print("PaSD bus device is in ON state.")
    change_event_callbacks[
        f"{get_field_station_name(station_label)}/state"
    ].assert_change_event(
        tango.DevState.OFF,
        lookahead=10,  # TODO: We only need 3 in lightweight testing. Why?
        consume_nonmatches=True,
    )
    print("field station device is in ON state.")
