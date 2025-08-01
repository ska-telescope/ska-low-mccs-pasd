# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsSmartBox."""

# pylint: disable=too-many-lines,too-many-arguments, too-many-positional-arguments
from __future__ import annotations

import gc
import json
import random
import time

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState, ResultCode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import SmartboxSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import (
    PasdConversionUtility,
    SmartboxAlarmFlags,
    SmartboxStatusMap,
)
from ska_low_mccs_pasd.pasd_data import PasdData

from .. import harness

gc.disable()  # TODO: why is this needed?


def turn_pasd_devices_online(
    smartbox_device: tango.DeviceProxy,
    pasd_bus_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    last_smartbox_id: int,
    smartbox_on: bool = True,
) -> None:
    """
    Turn the PaSD devices adminMode online.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    :param last_smartbox_id: ID of the last smartbox polled
    :param smartbox_on: expected Tango state of smartbox device
    """
    # This is a bit of a cheat.
    # It's an implementation-dependent detail that
    # this is one of the last attributes to be read from the simulator.
    # We subscribe events on this attribute because we know that
    # once we have an updated value for this attribute,
    # we have an updated value for all of them.
    pasd_bus_device.subscribe_event(
        f"smartbox{last_smartbox_id}AlarmFlags",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{last_smartbox_id}AlarmFlags"],
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{last_smartbox_id}AlarmFlags", Anything
    )

    pasd_bus_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK

    # ---------------------
    # FNDH adminMode online
    # ---------------------
    fndh_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)

    # -------------------------
    # SmartBox adminMode Online
    # -------------------------

    # The Smartbox will estabish a connection and transition to ON if powered.
    smartbox_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.UNKNOWN)
    if smartbox_on:
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.STANDBY
        )
    else:
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
    change_event_callbacks["smartbox_state"].assert_not_called()


def setup_devices_with_subscriptions(
    smartbox_device: tango.DeviceProxy,
    pasd_bus_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Subscribe to the pasd devices state and adminMode.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert smartbox_device.adminMode == AdminMode.OFFLINE
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE
    assert fndh_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["pasd_bus_state"],
    )
    change_event_callbacks.assert_change_event("pasd_bus_state", tango.DevState.DISABLE)
    fndh_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndh_state"],
    )
    change_event_callbacks.assert_change_event("fndh_state", tango.DevState.DISABLE)
    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["smartbox_state"],
    )
    change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.DISABLE)

    smartbox_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["smartboxHealthState"],
    )
    change_event_callbacks.assert_change_event(
        "smartboxHealthState", HealthState.UNKNOWN
    )

    pasd_bus_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )

    change_event_callbacks.assert_change_event("healthState", HealthState.UNKNOWN)
    assert pasd_bus_device.healthState == HealthState.UNKNOWN


# pylint: disable=inconsistent-return-statements
def poll_until_command_completed(
    device: tango.DeviceProxy, command_id: str, no_of_iters: int = 10
) -> None:
    """
    Poll until command has completed.

    This function recursively calls itself up to `no_of_iters` times.

    :param device: the TANGO device
    :param command_id: the command_id to check
    :param no_of_iters: number of times to iterate
    """
    command_status = device.CheckLongRunningCommandStatus(command_id)
    if command_status == "COMPLETED":
        return

    if no_of_iters == 1:
        pytest.fail("Command Failed to complete in time")

    time.sleep(0.1)
    return poll_until_command_completed(device, command_id, no_of_iters - 1)


class TestSmartBoxPasdBusIntegration:
    """Test pasdbus, smartbox, fndh integration."""

    def test_power_interplay(
        self: TestSmartBoxPasdBusIntegration,
        pasd_bus_device: tango.DeviceProxy,
        off_smartbox_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        off_smartbox_attached_port: int,
    ) -> None:
        """
        Test power interplay between the smartbox and the PaSD.

        :param off_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        :param off_smartbox_attached_port: the FNDH port the unpowered
            smartbox-under-test is attached to.
        """
        smartbox_device = off_smartbox_device

        assert smartbox_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        smartbox_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox_state"],
        )
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        # SETUP
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)

        # -------------------------
        # SmartBox adminMode Online
        # -------------------------

        # The Smartbox will estabish a connection and transition to OFF.
        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)

        fndh_ports_power_sensed = pasd_bus_device.fndhPortsPowerSensed
        assert not fndh_ports_power_sensed[off_smartbox_attached_port - 1]

        desired_port_powers: list[bool | None] = [None for _ in fndh_ports_power_sensed]
        desired_port_powers[off_smartbox_attached_port - 1] = True
        json_argument = json.dumps(
            {"port_powers": desired_port_powers, "stay_on_when_offline": True}
        )

        # Turning on FNDH ports should send the Smartbox to STANDBY.
        pasd_bus_device.SetFndhPortPowers(json_argument)
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.STANDBY
        )
        assert pasd_bus_device.fndhPortsPowerSensed[off_smartbox_attached_port - 1]

        desired_port_powers[off_smartbox_attached_port - 1] = False
        json_argument = json.dumps(
            {"port_powers": desired_port_powers, "stay_on_when_offline": True}
        )
        pasd_bus_device.SetFndhPortPowers(json_argument)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        assert not pasd_bus_device.fndhPortsPowerSensed[off_smartbox_attached_port - 1]

        smartbox_device.On()
        # Check the MccsSmartbox device goes to STANDBY once the FNDH port is on.
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.STANDBY
        )
        # Check the MccsSmartbox devices goes to ON once the Smartbox port is on.
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        assert pasd_bus_device.fndhPortsPowerSensed[off_smartbox_attached_port - 1]

        smartbox_device.Off()
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        assert not pasd_bus_device.fndhPortsPowerSensed[off_smartbox_attached_port - 1]

    def test_component_state_callbacks(
        self: TestSmartBoxPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        off_smartbox_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the component state callbacks.

        :param off_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
        smartbox_device = off_smartbox_device

        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)

        smartbox_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox_state"],
        )
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        change_event_callbacks["smartbox_state"].assert_not_called()

        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        # Smartbox start communicating without the MccsPaSDBus
        # communicating with PaSD system.
        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )

        # MccsPaSD started communicating
        # The smartbox should change state since it requires
        # only the MccsPasd to determine its state.
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)

        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)

        # When we start communicating on the MccsFNDH,
        # it should transition to ON (always on).
        # The smartbox should not change state,
        # because it does not depend on FNDH device in any way.
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()

        pasd_bus_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        # TODO: Update the FNDH to subscribe to state changes on the MccsPaSDBus.
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )

        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)

        fndh_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)
        change_event_callbacks["smartbox_state"].assert_not_called()

        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()

    @pytest.mark.xfail(
        reason=(
            "Cannot unsubscribe from proxy so event received,"
            "even though communication is not established"
        )
    )
    def test_power_state_transitions(
        self: TestSmartBoxPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        off_smartbox_device: tango.DeviceProxy,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
    ) -> None:
        """
        Test the integration of smartbox, pasdBus and FNDH.

        This test looks at the simple power state transitions.

        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param off_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param off_smartbox_attached_port: the FNDH port the powered
             smartbox-under-test is attached to.
        :param change_event_callbacks: group of Tango change event
             callback with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        # ==========
        # PaSD SETUP
        # ==========
        smartbox_device = off_smartbox_device
        smartbox_attached_port = off_smartbox_attached_port

        setup_devices_with_subscriptions(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
        )
        turn_pasd_devices_online(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
            last_smartbox_id,
            smartbox_on=False,
        )
        fndh_port_power_state = fndh_device.PortPowerState(smartbox_attached_port)
        is_pasd_port_on = pasd_bus_device.fndhPortsPowerSensed[
            smartbox_attached_port - 1
        ]
        if not is_pasd_port_on:
            pasd_reports_fndh_port_power_state = PowerState.OFF
        elif is_pasd_port_on:
            pasd_reports_fndh_port_power_state = PowerState.ON
        else:
            pasd_reports_fndh_port_power_state = PowerState.UNKNOWN

        assert fndh_port_power_state == pasd_reports_fndh_port_power_state

        # --------------------------------------
        # Check a situation:
        # 1 - SmartBox stops listening to device
        # 2 - Power state of device changes
        # 3 - SmartBox reconnects
        # --------------------------------------

        # 1 - SmartBox stops listening to device
        smartbox_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        change_event_callbacks["smartbox_state"].assert_not_called()
        fndh_device.subscribe_event(
            f"Port{smartbox_attached_port}PowerState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhportpowerstate"],
        )
        change_event_callbacks.assert_change_event("fndhportpowerstate", PowerState.OFF)

        # 2 - Power state of device changes
        fndh_device.PowerOnPort(smartbox_attached_port)
        # The smartbox should not be called since adminMode == OFFLINE
        change_event_callbacks["smartbox_state"].assert_not_called()
        change_event_callbacks.assert_change_event("fndhportpowerstate", PowerState.ON)

        # 3 - SmartBox reconnects
        smartbox_device.adminMode = AdminMode.ONLINE
        time.sleep(5)  # allow time for polling and callbacks
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.ON, lookahead=4
        )
        change_event_callbacks["smartbox_state"].assert_not_called()
        assert smartbox_device.state() == tango.DevState.ON

    def test_turn_on_mccs_smartbox_antenna_port_when_smartbox_under_test_is_off(
        self: TestSmartBoxPasdBusIntegration,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        off_smartbox_device: tango.DeviceProxy,
        off_smartbox_id: int,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
    ) -> None:
        """
        Test we can turn on a smartbox antenna port when a smartbox-under-test is off.

        The MccsSmartbox is in a state determined by the "Smartbox-under-test" state.
        GIVEN the "Smartbox-under-test" is off.
        WHEN we ask the MccsSmartbox to turn on a antenna port.
        THEN the MccsSmartbox asks the MCCSFndh to turn on the "fndh-under-test" port
        that the "Smartbox-under-test" is attached to.
        AND the MccsSmartbox responds to the "Smartbox-under-test" turning on by
        transitions to the On state.
        AND the MccsSmartbox will ask the "Smartbox-under-test" to turn on the
        antenna port.
        AND the MCCSSmartbox will get a callback when the "Smartbox-under-test"
        antenna port has turned on.

        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param off_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param off_smartbox_id: the smartbox of interest in this test.
        :param off_smartbox_attached_port: the FNDH port the on
            smartbox-under-test is attached to.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        smartbox_device = off_smartbox_device
        smartbox_id = off_smartbox_id
        smartbox_attached_port = off_smartbox_attached_port
        # ==========
        # PaSD SETUP
        # ==========
        smartbox_port_desired_on = 6

        setup_devices_with_subscriptions(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
        )
        turn_pasd_devices_online(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
            last_smartbox_id,
            smartbox_on=False,
        )

        # Check that both the PaSD and FNDH say
        # the smartbox under investigation Is OFF.
        assert not pasd_bus_device.fndhPortsPowerSensed[smartbox_attached_port - 1]
        assert fndh_device.PortPowerState(smartbox_attached_port) == PowerState.OFF
        fndh_device.subscribe_event(
            f"Port{smartbox_attached_port}PowerState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhportpowerstate"],
        )
        change_event_callbacks["fndhportpowerstate"].assert_change_event(PowerState.OFF)

        # Check that the Port is not ON
        assert not smartbox_device.PortsPowerSensed[smartbox_port_desired_on - 1]

        # Subscribe to FNDH and Smartbox status attributes
        fndh_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhstatus"],
        )
        change_event_callbacks.assert_change_event("fndhstatus", "OK")
        assert fndh_device.PasdStatus == "OK"
        smartbox_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}status"],
        )

        # ===
        # ACT
        # ===
        # TODO: MCCS to make a decision on the requirements of this test,
        # discussions held on MR!41.
        [return_code], [command_id] = smartbox_device.PowerOnPort(
            smartbox_port_desired_on
        )
        assert return_code == ResultCode.QUEUED
        poll_until_command_completed(smartbox_device, command_id)

        # ======
        # ASSERT
        # ======
        # Check the FNDH and smartbox simulator's status.
        change_event_callbacks[f"smartbox{smartbox_id}status"].assert_change_event(
            "OK",
            lookahead=3,
            consume_nonmatches=True,
        )
        assert smartbox_device.PasdStatus == "OK"

        # Check the MccsSmartbox device goes to STANDBY once the FNDH port is on.
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.STANDBY
        )
        # Check the MccsSmartbox devices goes to ON once the Smartbox port is on.
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()
        change_event_callbacks["fndhportpowerstate"].assert_change_event(PowerState.ON)
        assert fndh_device.PortPowerState(smartbox_attached_port) == PowerState.ON

        # Check that the Port is turned on as desired.
        smartbox_device.subscribe_event(
            "PortsPowerSensed",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}portpowersensed"],
        )
        expected_smartbox_port_states = [False] * SmartboxSimulator.NUMBER_OF_PORTS
        expected_smartbox_port_states[smartbox_port_desired_on - 1] = True
        change_event_callbacks[
            f"smartbox{smartbox_id}portpowersensed"
        ].assert_change_event(expected_smartbox_port_states)
        assert smartbox_device.PortsPowerSensed[smartbox_port_desired_on - 1]
        # This can take some time for the callback to be called.

    # pylint: disable=too-many-locals
    def test_turn_on_multiple_mccs_smartbox_antenna_ports(
        self: TestSmartBoxPasdBusIntegration,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        off_smartbox_device: tango.DeviceProxy,
        off_smartbox_id: int,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
    ) -> None:
        """
        Test we can turn on multiple smartbox antennas when smartbox-under-test is off.

        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param off_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param off_smartbox_id: the smartbox of interest in this test
        :param off_smartbox_attached_port: the FNDH port the on
            smartbox-under-test is attached to.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        smartbox_device = off_smartbox_device
        smartbox_id = off_smartbox_id
        smartbox_attached_port = off_smartbox_attached_port
        smartbox_ports_desired_on = [6, 7, 8]

        setup_devices_with_subscriptions(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
        )
        turn_pasd_devices_online(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
            last_smartbox_id,
            smartbox_on=False,
        )

        # Check that both the PaSD and FNDH say
        # the smartbox under investigation Is OFF.
        assert not pasd_bus_device.fndhPortsPowerSensed[smartbox_attached_port - 1]
        assert fndh_device.PortPowerState(smartbox_attached_port) == PowerState.OFF
        fndh_device.subscribe_event(
            f"Port{smartbox_attached_port}PowerState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhportpowerstate"],
        )
        change_event_callbacks["fndhportpowerstate"].assert_change_event(PowerState.OFF)

        # Subscribe to FNDH status attributes
        fndh_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhstatus"],
        )
        change_event_callbacks.assert_change_event("fndhstatus", "OK")
        assert fndh_device.PasdStatus == "OK"

        # Smartbox ports' states
        smartbox_device.subscribe_event(
            "PortsPowerSensed",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}portpowersensed"],
        )
        expected_smartbox_port_states = [False] * SmartboxSimulator.NUMBER_OF_PORTS

        for port in smartbox_ports_desired_on:
            [return_code], [command_id] = smartbox_device.PowerOnPort(port)
            assert return_code == ResultCode.QUEUED
            poll_until_command_completed(smartbox_device, command_id)
            expected_smartbox_port_states[port - 1] = True
            change_event_callbacks[
                f"smartbox{smartbox_id}portpowersensed"
            ].assert_change_event(
                expected_smartbox_port_states, lookahead=4, consume_nonmatches=True
            )
            assert (
                list(smartbox_device.PortsPowerSensed) == expected_smartbox_port_states
            )

    # pylint: disable-next=too-many-statements
    def test_smartbox_pasd_integration(
        self: TestSmartBoxPasdBusIntegration,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        on_smartbox_device: tango.DeviceProxy,
        on_smartbox_id: int,
        smartbox_simulator: SmartboxSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
    ) -> None:
        """
        Test the integration of smartbox with the pasdBus.

        This tests basic communications:
        - Does the state transition as expected when adminMode put online
        with the MccsPasdBus
        - Can MccsSmartBox handle a changing attribute event pushed from the
        MccsPasdBus.
        - Can MccsSmartBox write an attribute with READ/WRITE permissions.

        :param on_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param smartbox_simulator: the smartbox simulator under test.
        :param on_smartbox_id: the smartbox of interest in this test.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        smartbox_device = on_smartbox_device
        smartbox_id = on_smartbox_id
        # ==========
        # PaSD SETUP
        # ==========
        setup_devices_with_subscriptions(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
        )

        # Check that we get a DevFailed for accessing non initialised attributes.
        for i in [
            "ModbusRegisterMapRevisionNumber",
            "PcbRevisionNumber",
            "CpuId",
            "ChipId",
            "FirmwareVersion",
            "Uptime",
            "SysAddress",
            "InputVoltage",
            "PowerSupplyOutputVoltage",
            "PowerSupplyTemperature",
            "PcbTemperature",
            "FemAmbientTemperature",
            "FemCaseTemperature1",
            "FemCaseTemperature2",
            "FemHeatsinkTemperature1",
            "FemHeatsinkTemperature2",
            "PortForcings",
            "PortBreakersTripped",
            "PortsDesiredPowerOnline",
            "PortsDesiredPowerOffline",
            "PortsPowerSensed",
            "PortsCurrentDraw",
            "InputVoltageThresholds",
            "PowerSupplyOutputVoltageThresholds",
            "PowerSupplyTemperatureThresholds",
            "PcbTemperatureThresholds",
            "FemAmbientTemperatureThresholds",
            "FemCaseTemperature1Thresholds",
            "FemCaseTemperature2Thresholds",
            "FemHeatsinkTemperature1Thresholds",
            "FemHeatsinkTemperature2Thresholds",
            "FemCurrentTripThresholds",
            "WarningFlags",
            "AlarmFlags",
        ]:
            with pytest.raises(tango.DevFailed):
                getattr(smartbox_device, i)

        turn_pasd_devices_online(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
            last_smartbox_id,
        )

        # Check that the smartbox has updated its values from the smartbox simulator.
        assert (
            smartbox_device.ModbusRegisterMapRevisionNumber
            == SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION
        )
        assert smartbox_device.PcbRevisionNumber == SmartboxSimulator.PCB_REVISION
        assert (
            smartbox_device.CpuId
            == PasdConversionUtility.convert_cpu_id(SmartboxSimulator.CPU_ID)[0]
        )
        assert (
            smartbox_device.ChipId
            == PasdConversionUtility.convert_chip_id(SmartboxSimulator.CHIP_ID)[0]
        )
        assert (
            smartbox_device.FirmwareVersion
            == PasdConversionUtility.convert_firmware_version(
                [SmartboxSimulator.DEFAULT_FIRMWARE_VERSION]
            )[0]
        )
        assert (
            smartbox_device.Uptime
            <= PasdConversionUtility.convert_uptime(smartbox_simulator.uptime)[0]
        )
        assert smartbox_device.PasdStatus == SmartboxSimulator.DEFAULT_STATUS.name
        assert smartbox_device.LedPattern == "service: OFF, status: YELLOWFAST"
        assert (
            smartbox_device.InputVoltage
            == PasdConversionUtility.scale_volts(
                [SmartboxSimulator.DEFAULT_INPUT_VOLTAGE]
            )[0]
        )
        assert (
            smartbox_device.PowerSupplyOutputVoltage
            == PasdConversionUtility.scale_volts(
                [SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE]
            )[0]
        )
        assert (
            smartbox_device.PowerSupplyTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE]
            )[0]
        )
        assert (
            smartbox_device.PcbTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_PCB_TEMPERATURE]
            )[0]
        )
        assert (
            smartbox_device.FemAmbientTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE]
            )[0]
        )
        assert (
            smartbox_device.FemCaseTemperature1
            == PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURE_1
            )[0]
        )
        assert (
            smartbox_device.FemCaseTemperature2
            == PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURE_2
            )[0]
        )
        assert (
            smartbox_device.FemHeatsinkTemperature1
            == PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURE_1
            )[0]
        )
        assert (
            smartbox_device.FemHeatsinkTemperature2
            == PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURE_2
            )[0]
        )
        assert list(
            smartbox_device.InputVoltageThresholds
        ) == PasdConversionUtility.scale_volts(
            smartbox_simulator.input_voltage_thresholds
        )
        assert list(
            smartbox_device.PowerSupplyOutputVoltageThresholds
        ) == PasdConversionUtility.scale_volts(
            smartbox_simulator.power_supply_output_voltage_thresholds
        )
        assert list(
            smartbox_device.PowerSupplyTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.power_supply_temperature_thresholds
        )
        assert list(
            smartbox_device.PcbTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.pcb_temperature_thresholds
        )
        assert list(
            smartbox_device.FemAmbientTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.fem_ambient_temperature_thresholds
        )
        assert list(
            smartbox_device.FemCaseTemperature1Thresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.fem_case_temperature_1_thresholds
        )
        assert list(
            smartbox_device.FemCaseTemperature2Thresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.fem_case_temperature_2_thresholds
        )
        assert list(
            smartbox_device.FemHeatsinkTemperature1Thresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.fem_heatsink_temperature_1_thresholds
        )
        assert list(
            smartbox_device.FemHeatsinkTemperature2Thresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            smartbox_simulator.fem_heatsink_temperature_2_thresholds
        )

        assert smartbox_device.WarningFlags == SmartboxAlarmFlags.NONE.name
        assert smartbox_device.AlarmFlags == SmartboxAlarmFlags.NONE.name

        # Subscribe to attribute change events
        smartbox_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}status"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status",
            SmartboxSimulator.DEFAULT_STATUS.name,
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "InputVoltage",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}inputvoltage"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}inputvoltage",
            PasdConversionUtility.scale_volts(
                [
                    SmartboxSimulator.DEFAULT_INPUT_VOLTAGE,
                ]
            )[0],
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "PowerSupplyOutputVoltage",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}psuoutput"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}psuoutput",
            PasdConversionUtility.scale_volts(
                [SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE]
            )[0],
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "PowerSupplyTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}psutemperature"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}psutemperature",
            PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE]
            )[0],
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "PcbTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}pcbtemperature"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}pcbtemperature",
            PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_PCB_TEMPERATURE]
            )[0],
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "FemAmbientTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}femambienttemperature"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femambienttemperature",
            PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE]
            )[0],
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "FemCaseTemperature1",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}femcasetemperature1"],
        )
        smartbox_device.subscribe_event(
            "FemCaseTemperature2",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}femcasetemperature2"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femcasetemperature1",
            PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURE_1
            )[0],
            lookahead=2,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femcasetemperature2",
            PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURE_2
            )[0],
            lookahead=2,
        )
        smartbox_device.subscribe_event(
            "FemHeatsinkTemperature1",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}femheatsinktemperature1"],
        )
        smartbox_device.subscribe_event(
            "FemHeatsinkTemperature2",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}femheatsinktemperature2"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femheatsinktemperature1",
            PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURE_1
            )[0],
            lookahead=2,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femheatsinktemperature2",
            PasdConversionUtility.scale_signed_16bit(
                SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURE_2
            )[0],
            lookahead=2,
        )

        # When we mock a change in an attribute at the simulator level.
        # This is received and pushed onward by the MccsSmartbox device.

        # Initialize smartbox simulator
        assert pasd_bus_device.InitializeSmartbox(smartbox_id)[0] == ResultCode.OK
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status", "OK", lookahead=17, consume_nonmatches=True
        )
        assert smartbox_device.PasdStatus == "OK"
        assert smartbox_device.LedPattern == "service: OFF, status: GREENSLOW"
        assert (
            list(smartbox_device.FemCurrentTripThresholds)
            == [harness.FEM_CURRENT_TRIP_THRESHOLD] * SmartboxSimulator.NUMBER_OF_PORTS
        )

        smartbox_simulator.input_voltage = 3000
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}inputvoltage",
            30.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status",
            "ALARM",
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.InputVoltage == 30.00
        smartbox_simulator.input_voltage = 4200
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}inputvoltage",
            42.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status",
            "RECOVERY",
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.InputVoltage == 42.00
        assert pasd_bus_device.InitializeSmartbox(smartbox_id)[0] == ResultCode.OK
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status",
            "WARNING",
            lookahead=13,
            consume_nonmatches=True,
        )
        smartbox_simulator.input_voltage = 4800
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}inputvoltage",
            48.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status",
            "OK",
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.InputVoltage == 48.00

        smartbox_simulator.power_supply_output_voltage = 495
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}psuoutput",
            4.95,
            lookahead=13,
            consume_nonmatches=True,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}status",
            "WARNING",
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.PowerSupplyOutputVoltage == 4.95

        smartbox_simulator.power_supply_temperature = 5000
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}psutemperature",
            50.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.PowerSupplyTemperature == 50.00

        smartbox_simulator.pcb_temperature = 5000
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}pcbtemperature",
            50.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.PcbTemperature == 50.00

        smartbox_simulator.fem_ambient_temperature = 5000
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femambienttemperature",
            50.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.FemAmbientTemperature == 50.00

        smartbox_simulator.fem_case_temperature_1 = 5000
        smartbox_simulator.fem_case_temperature_2 = 4900
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femcasetemperature1",
            50.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femcasetemperature2",
            49.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.FemCaseTemperature1 == 50.00
        assert smartbox_device.FemCaseTemperature2 == 49.00

        smartbox_simulator.fem_heatsink_temperature_1 = 5100
        smartbox_simulator.fem_heatsink_temperature_2 = 5000
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femheatsinktemperature1",
            51.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}femheatsinktemperature2",
            50.00,
            lookahead=13,
            consume_nonmatches=True,
        )
        assert smartbox_device.FemHeatsinkTemperature1 == 51.00
        assert smartbox_device.FemHeatsinkTemperature2 == 50.00

        # When we write an attribute, check the simulator gets updated
        smartbox_device.subscribe_event(
            "PcbTemperatureThresholds",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}pcbtemperaturethresholds"],
        )
        setattr(
            smartbox_device,
            "PcbTemperatureThresholds",
            [30.2, 25.5, 10.5, 5],
        )
        change_event_callbacks[
            f"smartbox{smartbox_id}pcbtemperaturethresholds"
        ].assert_change_event([30.2, 25.5, 10.5, 5], lookahead=13)
        assert smartbox_simulator.pcb_temperature_thresholds == [3020, 2550, 1050, 500]

        # Check the threshold values get propagated to the Tango alarm configuration
        assert (
            smartbox_device.read_attribute("pcbTemperature").quality
            == tango.AttrQuality.ATTR_ALARM
        )

    def test_set_port_powers(
        self: TestSmartBoxPasdBusIntegration,
        on_smartbox_device: tango.DeviceProxy,
        on_smartbox_id: int,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test `SetPortPowers` turns on the correct ports on the correct smartbox.

        :param on_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param on_smartbox_id: A fixture containing the id of a smartbox that is `ON`
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
        smartbox_id = on_smartbox_id
        smartbox_device = on_smartbox_device

        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.DISABLE
        )

        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.ON, lookahead=2
        )

        pasd_bus_device.initializesmartbox(smartbox_id)
        smartbox_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox_state"],
        )
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_change_event(Anything)
        change_event_callbacks["smartbox_state"].assert_not_called()

        json_argument = json.dumps(
            {
                "port_powers": [True] * 12,
                "stay_on_when_offline": True,
            }
        )
        smartbox_device.subscribe_event(
            "portspowersensed",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{smartbox_id}portpowersensed"],
        )
        change_event_callbacks[
            f"smartbox{smartbox_id}portpowersensed"
        ].assert_change_event(
            [False] * 12,
        )
        smartbox_device.SetPortPowers(json_argument)

        change_event_callbacks[
            f"smartbox{smartbox_id}portpowersensed"
        ].assert_change_event(
            [True] * 12,
        )

    def test_smartbox_health(
        self: TestSmartBoxPasdBusIntegration,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        on_smartbox_device: tango.DeviceProxy,
        on_smartbox_id: int,
        smartbox_simulator: SmartboxSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
    ) -> None:
        """
        Test the health of smartbox.

        :param on_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param smartbox_simulator: the smartbox simulator under test.
        :param on_smartbox_id: the smartbox of interest in this test.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        smartbox_device = on_smartbox_device

        monitoring_point = "input_voltage"
        monitoring_point_thresholds = monitoring_point + "_thresholds"
        # ==========
        # PaSD SETUP
        # ==========
        setup_devices_with_subscriptions(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
        )

        turn_pasd_devices_online(
            smartbox_device,
            pasd_bus_device,
            fndh_device,
            change_event_callbacks,
            last_smartbox_id,
        )
        pasd_bus_device.initializeSmartbox(on_smartbox_id)
        max_alarm, max_warning, min_warning, min_alarm = getattr(
            smartbox_simulator, monitoring_point_thresholds
        )
        healthy_value = (max_warning + min_warning) / 2

        # We need to subscribe to the status register since the health state
        # now also depends on this.
        on_smartbox_device.subscribe_event(
            "pasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdStatus"],
        )

        change_event_callbacks.assert_change_event(
            "smartboxHealthState",
            HealthState.OK,
        )

        # Test ALARM / FAILED state
        setattr(smartbox_simulator, monitoring_point, max_alarm + 100)
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.ALARM.name, lookahead=20, consume_nonmatches=True
        )
        change_event_callbacks.assert_change_event(
            "smartboxHealthState",
            HealthState.FAILED,
        )
        setattr(smartbox_simulator, monitoring_point, max_warning)
        # We should now be in RECOVERY state - this is still FAILED
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.RECOVERY.name, lookahead=20, consume_nonmatches=True
        )
        change_event_callbacks["smartboxHealthState"].assert_not_called()

        # Test transition to WARNING / DEGRADED
        assert pasd_bus_device.initializeSmartbox(on_smartbox_id)[0] == ResultCode.OK
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.WARNING.name, lookahead=20, consume_nonmatches=True
        )
        change_event_callbacks.assert_change_event(
            "smartboxHealthState",
            HealthState.DEGRADED,
        )

        # Test transition to OK / HEALTHY
        setattr(smartbox_simulator, monitoring_point, healthy_value)
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.OK.name, lookahead=20, consume_nonmatches=True
        )
        change_event_callbacks.assert_change_event(
            "smartboxHealthState", HealthState.OK
        )

        # Test minimum alarm and warning thresholds
        setattr(smartbox_simulator, monitoring_point, min_alarm - 100)
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.ALARM.name, lookahead=20, consume_nonmatches=True
        )
        change_event_callbacks.assert_change_event(
            "smartboxHealthState",
            HealthState.FAILED,
        )

        setattr(smartbox_simulator, monitoring_point, min_warning)
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.RECOVERY.name, lookahead=20, consume_nonmatches=True
        )
        change_event_callbacks["smartboxHealthState"].assert_not_called()

        assert pasd_bus_device.initializeSmartbox(on_smartbox_id)[0] == ResultCode.OK
        change_event_callbacks["pasdStatus"].assert_change_event(
            SmartboxStatusMap.WARNING.name, lookahead=20, consume_nonmatches=True
        )

        change_event_callbacks.assert_change_event(
            "smartboxHealthState",
            HealthState.DEGRADED,
        )

        # Test breaker trip causes FAILED health state
        smartbox_simulator.simulate_breaker_trip(
            random.randint(1, PasdData.NUMBER_OF_SMARTBOX_PORTS)
        )
        change_event_callbacks.assert_change_event(
            "smartboxHealthState",
            HealthState.FAILED,
        )


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture(
    on_smartbox_id: int,
    off_smartbox_id: int,
    last_smartbox_id: int,
) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :param on_smartbox_id: the number of the powered smartbox under test.
    :param off_smartbox_id: the number of the unpowered smartbox under test.
    :return: a dictionary of callables to be used as tango change event
        callbacks.
    :param last_smartbox_id: ID of the last smartbox polled
    """
    return MockTangoEventCallbackGroup(
        "smartbox_state",
        "pasd_bus_state",
        "fndh_state",
        "healthState",
        "smartboxHealthState",
        "fndhstatus",
        "pasdStatus",
        f"smartbox{last_smartbox_id}AlarmFlags",
        f"smartbox{on_smartbox_id}portpowersensed",
        f"smartbox{on_smartbox_id}inputvoltage",
        f"smartbox{on_smartbox_id}psuoutput",
        f"smartbox{on_smartbox_id}psutemperature",
        f"smartbox{on_smartbox_id}pcbtemperature",
        f"smartbox{on_smartbox_id}femambienttemperature",
        f"smartbox{on_smartbox_id}femcasetemperature1",
        f"smartbox{on_smartbox_id}femcasetemperature2",
        f"smartbox{on_smartbox_id}femheatsinktemperature1",
        f"smartbox{on_smartbox_id}femheatsinktemperature2",
        f"smartbox{on_smartbox_id}status",
        f"smartbox{on_smartbox_id}pcbtemperaturethresholds",
        f"smartbox{off_smartbox_id}portpowersensed",
        f"smartbox{off_smartbox_id}status",
        "fndhportpowerstate",
        timeout=30.0,
        assert_no_error=False,
    )
