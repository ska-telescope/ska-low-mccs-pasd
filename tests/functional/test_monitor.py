# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple tests of the MCCS PaSD bus Tango device."""
from __future__ import annotations

import gc

import tango
from pytest_bdd import given, scenario, then, when
from ska_control_model import AdminMode, HealthState
from ska_tango_testing.context import TangoContextProtocol
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

gc.disable()


@scenario(
    "features/monitor.feature",
    "Monitor PaSD",
)
def test_monitor() -> None:
    """
    Test basic monitoring of a PaSD.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given("a PaSD bus Tango device", target_fixture="pasd_bus_device")
def pasd_bus_device_given(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
) -> tango.DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsPasdBus.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: the name of the PaSD bus device under test.

    :return: A proxy to an instance of MccsPasdBus.
    """
    return tango_harness.get_device(pasd_bus_name)


@given("the PaSD bus Tango device is offline")
def check_pasd_bus_device_is_offline(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the PaSD bus device is offline.

    :param pasd_bus_device: the PaSD bus Tango device under test
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    admin_mode = pasd_bus_device.adminMode
    print(f"PaSD bus device is in admin_mode {admin_mode.name}")

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["pasd_bus_state"],
    )
    pasd_bus_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["pasd_bus_health"],
    )

    if admin_mode != AdminMode.OFFLINE:
        change_event_callbacks.assert_change_event("pasd_bus_state", Anything)
        change_event_callbacks.assert_change_event("pasd_bus_health", Anything)
        pasd_bus_device.adminMode = AdminMode.OFFLINE

    change_event_callbacks.assert_change_event("pasd_bus_state", tango.DevState.DISABLE)
    change_event_callbacks.assert_change_event("pasd_bus_health", HealthState.UNKNOWN)


@when("I put the PaSD bus Tango device online")
def put_pasd_bus_device_online(
    pasd_bus_device: tango.DeviceProxy,
) -> None:
    """
    Put the PaSD bus device online.

    :param pasd_bus_device: the PaSD bus Tango device under test
    """
    print("Putting PaSD bus device ONLINE...")
    pasd_bus_device.adminMode = AdminMode.ONLINE


@then("the PaSD bus Tango device reports the state of the PaSD system")
def check_state_is_updated(
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the state of the PaSD bus device progresses from UNKNOWN.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    change_event_callbacks.assert_change_event("pasd_bus_state", tango.DevState.UNKNOWN)
    print("PaSD bus device is in UNKNOWN state.")

    change_event_callbacks.assert_change_event(
        "pasd_bus_state",
        tango.DevState.ON,
    )
    print("PaSD bus device is in ON state.")


@then("the PaSD bus Tango device reports the health of the PaSD system")
def check_health_is_updated(
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the health of the PaSD bus device progresses from UNKNOWN.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    change_event_callbacks.assert_change_event("pasd_bus_health", HealthState.OK)
    print("PaSD bus device is in OK health.")
