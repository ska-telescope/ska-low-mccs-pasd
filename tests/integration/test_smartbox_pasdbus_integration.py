# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsSmartBox."""

# pylint: disable=too-many-lines
from __future__ import annotations

import gc
import json
import time

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState, ResultCode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator, SmartboxSimulator

gc.disable()  # TODO: why is this needed?


def turn_pasd_devices_online(
    smartbox_device: tango.DeviceProxy,
    pasd_bus_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
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
    """
    # This is a bit of a cheat.
    # It's an implementation-dependent detail that
    # this is one of the last attributes to be read from the simulator.
    # We subscribe events on this attribute because we know that
    # once we have an updated value for this attribute,
    # we have an updated value for all of them.
    pasd_bus_device.subscribe_event(
        "smartbox24AlarmFlags",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["smartbox24AlarmFlags"],
    )
    change_event_callbacks.assert_change_event("smartbox24AlarmFlags", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.UNKNOWN)
    # TODO: Do we want to enter On state here?
    change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["pasd_bus_state"].assert_not_called()
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK

    # ---------------------
    # FNDH adminMode online
    # ---------------------
    fndh_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["fndh_state"].assert_not_called()

    # -------------------------
    # SmartBox adminMode Online
    # -------------------------

    # The Smartbox will estabish a connection and transition to OFF.
    smartbox_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.UNKNOWN)
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

    pasd_bus_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )

    change_event_callbacks.assert_change_event("healthState", HealthState.UNKNOWN)
    assert pasd_bus_device.healthState == HealthState.UNKNOWN
    change_event_callbacks["pasd_bus_state"].assert_not_called()


class TestSmartBoxPasdBusIntegration:
    """Test pasdbus, smartbox, fndh integration."""

    def test_power_interplay(  # pylint: disable=too-many-arguments, too-many-statements
        self: TestSmartBoxPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        smartbox_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        smartbox_number: int,
    ) -> None:
        """
        Test power interplay between TANGO devices.

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
        :param smartbox_number: the smartbox number
        """
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)
        change_event_callbacks["fndh_state"].assert_not_called()

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
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # SETUP
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        assert pasd_bus_device.InitializeFndh()[0] == ResultCode.OK
        assert pasd_bus_device.InitializeSmartbox(smartbox_number)[0] == ResultCode.OK

        # ---------------------
        # FNDH adminMode online
        # ---------------------
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["fndh_state"].assert_not_called()

        # -------------------------
        # SmartBox adminMode Online
        # -------------------------

        # The Smartbox will estabish a connection and transition to OFF.
        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        change_event_callbacks["smartbox_state"].assert_not_called()

        # Subscribe
        fndh_device.subscribe_event(
            f"Port{smartbox_number}PowerState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"fndhport{smartbox_number}powerstate"],
        )
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.OFF)
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_not_called()

        fndh_device.PowerOnPort(smartbox_number)
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.ON)
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_not_called()
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        assert pasd_bus_device.fndhPortsPowerSensed[smartbox_number - 1]
        change_event_callbacks["smartbox_state"].assert_not_called()

        fndh_device.PowerOffPort(smartbox_number)
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.OFF)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        assert not pasd_bus_device.fndhPortsPowerSensed[smartbox_number - 1]
        change_event_callbacks["smartbox_state"].assert_not_called()
        json_argument = json.dumps(
            {"port_number": smartbox_number, "stay_on_when_offline": True}
        )
        pasd_bus_device.TurnFndhPortOn(json_argument)
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.ON)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        assert pasd_bus_device.fndhPortsPowerSensed[smartbox_number - 1]

        pasd_bus_device.TurnFndhPortOff(smartbox_number)
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.OFF)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        assert not pasd_bus_device.fndhPortsPowerSensed[smartbox_number - 1]

        smartbox_device.On()
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.ON)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        assert pasd_bus_device.fndhPortsPowerSensed[smartbox_number - 1]

        smartbox_device.Off()
        change_event_callbacks[
            f"fndhport{smartbox_number}powerstate"
        ].assert_change_event(PowerState.OFF)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        assert not pasd_bus_device.fndhPortsPowerSensed[smartbox_number - 1]

    def test_component_state_callbacks(
        self: TestSmartBoxPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        smartbox_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the component state callbacks.

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
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)
        change_event_callbacks["fndh_state"].assert_not_called()

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
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # Smartbox start communicating without the MccsPaSDBus
        # communicating with PaSD system.
        smartbox_device.adminMode = 0
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # MccsPaSD started communicating, the smartbox should not
        # change state since it requires
        # both the MCCSPaSD and MccsFNDH to determine its state.
        pasd_bus_device.adminMode = 0
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # When we start communicating on the MccsFNDH,
        # it should transition to ON (always on).
        # The smartbox should transition to OFF/ON dependent on
        # the power state of the port the smartbox is attached to.
        fndh_device.adminMode = 0
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        change_event_callbacks["fndh_state"].assert_not_called()
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        change_event_callbacks["smartbox_state"].assert_not_called()

        pasd_bus_device.adminMode = 1
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        # TODO: Update the FNDH to subscribe to state changes on the MccsPaSDBus.
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["fndh_state"].assert_not_called()
        change_event_callbacks["smartbox_state"].assert_not_called()

        pasd_bus_device.adminMode = 0
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)

        fndh_device.adminMode = 1
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["fndh_state"].assert_not_called()
        change_event_callbacks["smartbox_state"].assert_not_called()

        fndh_device.adminMode = 0
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)

    @pytest.mark.xfail(
        reason=(
            "Cannot unsubscribe from proxy so event received,"
            "even though communication is not established"
        )
    )
    def test_power_state_transitions(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of smartbox, pasdBus and FNDH.

        This test looks at the simple power state transitions.

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
        # ==========
        # PaSD SETUP
        # ==========
        this_smartbox_port = 2

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
        )
        fndh_port_power_state = fndh_device.PortPowerState(this_smartbox_port)
        is_pasd_port_on = pasd_bus_device.fndhPortsPowerSensed[this_smartbox_port - 1]
        if not is_pasd_port_on:
            pasd_reports_fndh_port_power_state = PowerState.OFF
        elif is_pasd_port_on:
            pasd_reports_fndh_port_power_state = PowerState.ON
        else:
            pasd_reports_fndh_port_power_state = PowerState.UNKNOWN

        assert fndh_port_power_state == pasd_reports_fndh_port_power_state

        # assert fndh_port_power_state == is_pasd_port_on

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
            "Port2PowerState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhport2powerstate"],
        )
        change_event_callbacks.assert_change_event(
            "fndhport2powerstate", PowerState.OFF
        )

        # 2 - Power state of device changes
        fndh_device.PowerOnPort(this_smartbox_port)
        # The smartbox should not be called since adminMode == OFFLINE
        change_event_callbacks["smartbox_state"].assert_not_called()
        change_event_callbacks.assert_change_event("fndhport2powerstate", PowerState.ON)

        # 3 - SmartBox reconnects
        smartbox_device.adminMode = AdminMode.ONLINE
        time.sleep(5)  # allow time for polling and callbacks
        # change_event_callbacks["smartbox_state"].assert_change_event(
        #     tango.DevState.ON, lookahead= 4
        # )
        # change_event_callbacks["smartbox_state"].assert_not_called()
        assert smartbox_device.state() == tango.DevState.ON

    # pylint: disable=too-many-arguments
    def test_turn_on_mccs_smartbox_antenna_port_when_smartbox_under_test_is_off(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        smartbox_number: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
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

        :param smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param smartbox_number: the smartbox of interest in this test
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
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
        )

        # Check that both the PaSD and FNDH say
        # the smartbox under investigation Is OFF.
        assert fndh_device.PortPowerState(smartbox_number) == PowerState.OFF
        pasd_claimed_port_states = getattr(
            pasd_bus_device, f"smartbox{smartbox_number}portspowersensed"
        )
        smartbox_claimed_port_states = smartbox_device.PortsPowerSensed
        assert all(smartbox_claimed_port_states == pasd_claimed_port_states)

        # Check that the Port is not ON
        assert not smartbox_device.PortsPowerSensed[smartbox_port_desired_on - 1]

        # Subscribe to FNDH and Smartbox status attributes
        fndh_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhstatus"],
        )
        change_event_callbacks.assert_change_event(
            "fndhstatus", FndhSimulator.DEFAULT_STATUS
        )
        smartbox_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1status"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1status", SmartboxSimulator.DEFAULT_STATUS
        )

        # ===
        # ACT
        # ===
        # TODO: MCCS to make a decision on the requirements of this test,
        # discussions held on MR!41.
        pasd_bus_device.InitializeFndh()
        smartbox_device.PowerOnPort(smartbox_port_desired_on)
        pasd_bus_device.InitializeSmartbox(smartbox_number)

        # ======
        # ASSERT
        # ======
        # Check the FNDH and smartbox simulators' statuses.
        change_event_callbacks["fndhstatus"].assert_change_event("OK")
        assert fndh_device.PasdStatus == "OK"
        change_event_callbacks["smartbox1status"].assert_change_event("OK")
        assert smartbox_device.PasdStatus == "OK"

        # Check the MccsSmartbox device is turned on.
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()
        assert fndh_device.PortPowerState(smartbox_number) == PowerState.ON

        # Check that the Port is turned on as desired.
        assert smartbox_device.PortsPowerSensed[smartbox_port_desired_on - 1]
        # This can take some time for the callback to be called.

    # pylint: disable=too-many-arguments
    def test_turn_on_multiple_mccs_smartbox_antenna_ports(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        smartbox_number: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test we can turn on multiple smartbox antennas when smartbox-under-test is off.

        :param smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param smartbox_number: the smartbox of interest in this test
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
        # ==========
        # PaSD SETUP
        # ==========
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
        )

        # Check that both the PaSD and FNDH say
        # the smartbox under investigation Is OFF.
        assert fndh_device.PortPowerState(smartbox_number) == PowerState.OFF
        pasd_claimed_port_states = getattr(
            pasd_bus_device, f"smartbox{smartbox_number}portspowersensed"
        )
        smartbox_claimed_port_states = smartbox_device.PortsPowerSensed
        assert all(smartbox_claimed_port_states == pasd_claimed_port_states)

        # Check that the Port is not ON
        for port in smartbox_ports_desired_on:
            assert not smartbox_device.PortsPowerSensed[port - 1]

        smartbox_device.subscribe_event(
            "PortsPowerSensed",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1portpowersensed"],
        )
        change_event_callbacks["smartbox1portpowersensed"].assert_change_event(Anything)
        # ===
        # ACT
        # ===
        pasd_bus_device.InitializeFndh()
        for port in smartbox_ports_desired_on:
            smartbox_device.PowerOnPort(port)
        pasd_bus_device.InitializeSmartbox(smartbox_number)

        # ======
        # ASSERT
        # ======
        # Check the MccsSmartbox device is turned on.
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()
        assert fndh_device.PortPowerState(smartbox_number) == PowerState.ON

        change_event_callbacks["smartbox1portpowersensed"].assert_change_event(Anything)
        for port in smartbox_ports_desired_on:
            # Check that the requested ports are powered on.
            assert smartbox_device.PortsPowerSensed[port - 1]

    # pylint: disable-next=too-many-arguments,too-many-statements
    def test_smartbox_pasd_integration(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        smartbox_simulator: SmartboxSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of smartbox with the pasdBus.

        This tests basic communications:
        - Does the state transition as expected when adminMode put online
        with the MccsPasdBus
        - Can MccsSmartBox handle a changing attribute event pushed from the
        MccsPasdBus.

        :param smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param smartbox_simulator: the smartbox simulator under test.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
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
            "FemCaseTemperatures",
            "FemHeatsinkTemperatures",
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
            "Fem1CurrentTripThreshold",
            "Fem2CurrentTripThreshold",
            "Fem3CurrentTripThreshold",
            "Fem4CurrentTripThreshold",
            "Fem5CurrentTripThreshold",
            "Fem6CurrentTripThreshold",
            "Fem7CurrentTripThreshold",
            "Fem8CurrentTripThreshold",
            "Fem9CurrentTripThreshold",
            "Fem10CurrentTripThreshold",
            "Fem11CurrentTripThreshold",
            "Fem12CurrentTripThreshold",
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
        )

        # Check that the smartbox has updated its values from the smartbox simulator.
        assert (
            smartbox_device.ModbusRegisterMapRevisionNumber
            == SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION
        )
        assert smartbox_device.PcbRevisionNumber == SmartboxSimulator.PCB_REVISION
        assert smartbox_device.CpuId == SmartboxSimulator.CPU_ID
        assert smartbox_device.ChipId == SmartboxSimulator.CHIP_ID
        assert (
            smartbox_device.FirmwareVersion
            == SmartboxSimulator.DEFAULT_FIRMWARE_VERSION
        )
        assert smartbox_device.Uptime <= smartbox_simulator.uptime
        assert smartbox_device.PasdStatus == SmartboxSimulator.DEFAULT_STATUS
        assert smartbox_device.InputVoltage == SmartboxSimulator.DEFAULT_INPUT_VOLTAGE
        assert (
            smartbox_device.PowerSupplyOutputVoltage
            == SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        )
        assert (
            smartbox_device.PowerSupplyTemperature
            == SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
        )
        assert (
            smartbox_device.PcbTemperature == SmartboxSimulator.DEFAULT_PCB_TEMPERATURE
        )
        assert (
            smartbox_device.FemAmbientTemperature
            == SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE
        )
        assert (
            list(smartbox_device.FemCaseTemperatures)
            == SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES
        )
        assert (
            list(smartbox_device.FemHeatsinkTemperatures)
            == SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
        )
        assert (
            list(smartbox_device.InputVoltageThresholds)
            == smartbox_simulator.input_voltage_thresholds
        )
        assert (
            list(smartbox_device.PowerSupplyOutputVoltageThresholds)
            == smartbox_simulator.power_supply_output_voltage_thresholds
        )
        assert (
            list(smartbox_device.PowerSupplyTemperatureThresholds)
            == smartbox_simulator.power_supply_temperature_thresholds
        )
        assert (
            list(smartbox_device.PcbTemperatureThresholds)
            == smartbox_simulator.pcb_temperature_thresholds
        )
        assert (
            list(smartbox_device.FemAmbientTemperatureThresholds)
            == smartbox_simulator.fem_ambient_temperature_thresholds
        )
        assert (
            list(smartbox_device.FemCaseTemperature1Thresholds)
            == smartbox_simulator.fem_case_temperature_1_thresholds
        )
        assert (
            list(smartbox_device.FemCaseTemperature2Thresholds)
            == smartbox_simulator.fem_case_temperature_2_thresholds
        )
        assert (
            list(smartbox_device.FemHeatsinkTemperature1Thresholds)
            == smartbox_simulator.fem_heatsink_temperature_1_thresholds
        )
        assert (
            list(smartbox_device.FemHeatsinkTemperature2Thresholds)
            == smartbox_simulator.fem_heatsink_temperature_2_thresholds
        )
        assert (
            smartbox_device.Fem1CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem2CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem3CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem4CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem5CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem6CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem7CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem8CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem9CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem10CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem11CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        assert (
            smartbox_device.Fem12CurrentTripThreshold
            == SmartboxSimulator.DEFAULT_PORT_CURRENT_THRESHOLD
        )
        # TODO
        # assert smartbox_device.WarningFlags == SmartboxSimulator.DEFAULT_FLAGS
        # assert smartbox_device.AlarmFlags == SmartboxSimulator.DEFAULT_FLAGS

        # Subscribe to attribute change events
        smartbox_device.subscribe_event(
            "PasdStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1status"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1status", SmartboxSimulator.DEFAULT_STATUS
        )
        smartbox_device.subscribe_event(
            "InputVoltage",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1inputvoltage"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1inputvoltage", SmartboxSimulator.DEFAULT_INPUT_VOLTAGE
        )
        smartbox_device.subscribe_event(
            "PowerSupplyOutputVoltage",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1psuoutput"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1psuoutput", SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        )
        smartbox_device.subscribe_event(
            "PowerSupplyTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1psutemperature"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1psutemperature",
            SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE,
        )
        smartbox_device.subscribe_event(
            "PcbTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1pcbtemperature"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1pcbtemperature", SmartboxSimulator.DEFAULT_PCB_TEMPERATURE
        )
        smartbox_device.subscribe_event(
            "FemAmbientTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1femambienttemperature"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1femambienttemperature",
            SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE,
        )
        smartbox_device.subscribe_event(
            "FemCaseTemperatures",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1femcasetemperatures"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1femcasetemperatures",
            SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES,
        )
        smartbox_device.subscribe_event(
            "FemHeatsinkTemperatures",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox1femheatsinktemperatures"],
        )
        change_event_callbacks.assert_change_event(
            "smartbox1femheatsinktemperatures",
            SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES,
        )

        # When we mock a change in an attribute at the simulator level.
        # This is received and pushed onward by the MccsSmartbox device.

        # Initialize smartbox simulator status
        assert pasd_bus_device.InitializeSmartbox(1)[0] == ResultCode.OK
        change_event_callbacks.assert_change_event("smartbox1status", "OK")
        assert smartbox_device.PasdStatus == "OK"

        smartbox_simulator.input_voltage = 3000
        change_event_callbacks.assert_change_event("smartbox1inputvoltage", 3000)
        change_event_callbacks.assert_change_event("smartbox1status", "ALARM")
        assert smartbox_device.InputVoltage == 3000
        smartbox_simulator.input_voltage = 4200
        change_event_callbacks.assert_change_event("smartbox1inputvoltage", 4200)
        change_event_callbacks.assert_change_event("smartbox1status", "RECOVERY")
        assert smartbox_device.InputVoltage == 4200
        assert pasd_bus_device.InitializeSmartbox(1)[0] == ResultCode.OK
        change_event_callbacks.assert_change_event("smartbox1status", "WARNING")
        smartbox_simulator.input_voltage = 4800
        change_event_callbacks.assert_change_event("smartbox1inputvoltage", 4800)
        change_event_callbacks.assert_change_event("smartbox1status", "OK")
        assert smartbox_device.InputVoltage == 4800

        smartbox_simulator.power_supply_output_voltage = 495
        change_event_callbacks.assert_change_event("smartbox1psuoutput", 495)
        change_event_callbacks.assert_change_event("smartbox1status", "WARNING")
        assert smartbox_device.PowerSupplyOutputVoltage == 495

        smartbox_simulator.power_supply_temperature = 5000
        change_event_callbacks.assert_change_event("smartbox1psutemperature", 5000)
        assert smartbox_device.PowerSupplyTemperature == 5000

        smartbox_simulator.pcb_temperature = 5000
        change_event_callbacks.assert_change_event("smartbox1pcbtemperature", 5000)
        assert smartbox_device.PcbTemperature == 5000

        smartbox_simulator.fem_ambient_temperature = 5000
        change_event_callbacks.assert_change_event(
            "smartbox1femambienttemperature", 5000
        )
        assert smartbox_device.FemAmbientTemperature == 5000

        smartbox_simulator.fem_case_temperatures = [5000, 4900]
        change_event_callbacks.assert_change_event(
            "smartbox1femcasetemperatures", [5000, 4900]
        )
        assert (smartbox_device.FemCaseTemperatures == [5000, 4900]).all()

        smartbox_simulator.fem_heatsink_temperatures = [5100, 5000]
        change_event_callbacks.assert_change_event(
            "smartbox1femheatsinktemperatures", [5100, 5000]
        )
        assert (smartbox_device.FemHeatsinkTemperatures == [5100, 5000]).all()


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture(smartbox_number: int) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :param smartbox_number: the number of the smartbox under test

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "smartbox_state",
        "pasd_bus_state",
        "fndh_state",
        "healthState",
        "fndhstatus",
        "smartbox24AlarmFlags",
        "smartbox1portpowersensed",
        "smartbox1inputvoltage",
        "smartbox1psuoutput",
        "smartbox1psutemperature",
        "smartbox1pcbtemperature",
        "smartbox1femambienttemperature",
        "smartbox1femcasetemperatures",
        "smartbox1femheatsinktemperatures",
        "smartbox1status",
        f"fndhport{smartbox_number}powerstate",
        timeout=10.0,
        assert_no_error=False,
    )
