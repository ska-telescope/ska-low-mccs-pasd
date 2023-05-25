# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsSmartBox."""

from __future__ import annotations

import gc
import json
import time

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import SmartboxSimulator

gc.disable()  # TODO: why is this needed?


def test_power_interplay(
    smartbox_device: tango.DeviceProxy,
    pasd_bus_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    smartbox_id: int,
) -> None:
    """
    Test Power interplay between TANGO devices.

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
    :param smartbox_id: the smartbox number
    """
    # SETUP
    assert pasd_bus_device.state() == tango.DevState.DISABLE
    pasd_bus_device.adminMode = 0
    time.sleep(4)
    assert pasd_bus_device.state() == tango.DevState.ON

    assert fndh_device.state() == tango.DevState.DISABLE
    fndh_device.adminMode = 0
    assert fndh_device.state() == tango.DevState.ON

    assert smartbox_device.state() == tango.DevState.DISABLE
    smartbox_device.adminMode = 0
    time.sleep(2)
    assert smartbox_device.state() == tango.DevState.OFF

    # Subscribe
    fndh_device.subscribe_event(
        f"Port{smartbox_id+1}PowerState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["FndhPortPowerState"],
    )
    change_event_callbacks.assert_change_event("FndhPortPowerState", PowerState.OFF)

    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["smartbox_state"],
    )
    change_event_callbacks.assert_change_event("smartbox_state", tango.DevState.OFF)
    change_event_callbacks.assert_not_called()

    fndh_device.PowerOnPort(smartbox_id + 1)
    change_event_callbacks.assert_change_event("FndhPortPowerState", PowerState.ON)
    change_event_callbacks.assert_change_event("smartbox_state", tango.DevState.ON)
    assert pasd_bus_device.fndhPortsPowerSensed[smartbox_id] is True

    fndh_device.PowerOffPort(smartbox_id + 1)
    change_event_callbacks.assert_change_event("FndhPortPowerState", PowerState.OFF)
    change_event_callbacks.assert_change_event("smartbox_state", tango.DevState.OFF)
    assert pasd_bus_device.fndhPortsPowerSensed[smartbox_id] is False

    json_argument = json.dumps(
        {"port_number": smartbox_id + 1, "stay_on_when_offline": True}
    )
    pasd_bus_device.TurnFndhPortOn(json_argument)
    change_event_callbacks.assert_change_event("FndhPortPowerState", PowerState.ON)
    change_event_callbacks.assert_change_event("smartbox_state", tango.DevState.ON)
    assert pasd_bus_device.fndhPortsPowerSensed[smartbox_id] is True

    pasd_bus_device.TurnFndhPortOff(smartbox_id + 1)
    change_event_callbacks.assert_change_event("FndhPortPowerState", PowerState.OFF)
    change_event_callbacks.assert_change_event("smartbox_state", tango.DevState.OFF)
    assert pasd_bus_device.fndhPortsPowerSensed[smartbox_id] is False

    smartbox_device.On()
    change_event_callbacks.assert_change_event("FndhPortPowerState", PowerState.ON)
    change_event_callbacks.assert_change_event("smartbox_state", tango.DevState.ON)
    assert pasd_bus_device.fndhPortsPowerSensed[smartbox_id] is True


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
        "smartbox24PortsCurrentDraw",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["smartbox24PortsCurrentDraw"],
    )
    change_event_callbacks.assert_change_event("smartbox24PortsCurrentDraw", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.UNKNOWN)
    # TODO: Do we want to enter On state here?
    change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["pasd_bus_state"].assert_not_called()
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK

    change_event_callbacks.assert_against_call("smartbox24PortsCurrentDraw")

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

    @pytest.mark.xfail(
        reason="Cannot unsubscribe from proxy so event,"
        "though communication not established we get callback"
    )
    def test_power_state_transitions(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_devices: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of smartbox, pasdBus and FNDH.

        This test looks at the simple power state transitions.

        :param smartbox_devices: fixture that provides a
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
        smartbox_device = smartbox_devices[1]

        setup_devices_with_subscriptions(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
        )
        turn_pasd_devices_online(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
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
        # It will transition into UNKNOWN when the first proxy
        # changes to the DISABLE state and then DISABLE when the second
        # changes to DISABLE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
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
    def test_turn_on_smartbox_port_when_smartbox_off(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_devices: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        smartbox_number: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test we can turn on a smartbox port when smartbox is off.

        :param smartbox_devices: fixture that provides a
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

        smartbox_device = smartbox_devices[smartbox_number - 1]
        setup_devices_with_subscriptions(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
        )
        turn_pasd_devices_online(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
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

        # ===
        # ACT
        # ===
        smartbox_device.PowerOnPort(smartbox_port_desired_on)

        # ======
        # ASSERT
        # ======

        # Check the smartbox is turned on first
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()
        assert fndh_device.PortPowerState(smartbox_number) == PowerState.ON

        # Check that the Port is turned on.
        assert smartbox_device.PortsPowerSensed[smartbox_port_desired_on - 1]
        # Check that the port is then turned on as desired
        # This can take some time for the callback to be called.

    # pylint: disable=too-many-arguments
    def test_turn_on_multiple_smartbox_ports_when_smartbox_off(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_devices: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        smartbox_number: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test we can turn on multiple smartbox ports when smartbox is off.

        :param smartbox_devices: fixture that provides a
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

        smartbox_device = smartbox_devices[smartbox_number - 1]
        setup_devices_with_subscriptions(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
        )
        turn_pasd_devices_online(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
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

        # ===
        # ACT
        # ===
        for port in smartbox_ports_desired_on:
            smartbox_device.PowerOnPort(port)

        # ======
        # ASSERT
        # ======

        # Check the smartbox is turned on first
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()

        assert fndh_device.PortPowerState(smartbox_number) == PowerState.ON

        # manual sleep to allow time for polling and callbacks.
        time.sleep(1)
        for port in smartbox_ports_desired_on:
            # Check that the requested ports are powered on.
            assert smartbox_device.PortsPowerSensed[port - 1]

    # pylint: disable-next=too-many-arguments
    def test_smartbox_pasd_integration(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_devices: tango.DeviceProxy,
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

        :param smartbox_devices: fixture that provides a
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
        smartbox_device = smartbox_devices[0]
        setup_devices_with_subscriptions(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
        )

        # Check that we get a DevFailed for accessing non initialised attributes.
        for i in [
            "ModbusRegisterMapRevisionNumber",
            "PcbRevisionNumber",
            "CpuId",
            "ChipId",
            "FirmwareVersion",
            "Uptime",
            "InputVoltage",
            "PowerSupplyOutputVoltage",
            "PowerSupplyTemperature",
            "OutsideTemperature",
            "PcbTemperature",
        ]:
            with pytest.raises(tango.DevFailed):
                getattr(smartbox_device, i)

        turn_pasd_devices_online(
            smartbox_device, pasd_bus_device, fndh_device, change_event_callbacks
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
        assert smartbox_device.Uptime == SmartboxSimulator.DEFAULT_UPTIME
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
            smartbox_device.OutsideTemperature
            == SmartboxSimulator.DEFAULT_OUTSIDE_TEMPERATURE
        )
        assert (
            smartbox_device.PcbTemperature == SmartboxSimulator.DEFAULT_PCB_TEMPERATURE
        )

        # We are just testing one attribute here to check the functionality
        # TODO: probably worth testing every attribute.
        initial_input_voltage = smartbox_device.InputVoltage
        smartbox_device.subscribe_event(
            "InputVoltage",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["SmartboxInputVoltage"],
        )
        change_event_callbacks.assert_change_event(
            "SmartboxInputVoltage", initial_input_voltage
        )

        # When we mock a change in an attribute at the simulator level.
        # This is received and pushed onward by the MccsSmartbox device.

        smartbox_simulator.input_voltage = 10
        change_event_callbacks.assert_change_event("SmartboxInputVoltage", 10.0)

        assert smartbox_device.InputVoltage != initial_input_voltage
        assert smartbox_device.InputVoltage == 10


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "smartbox_state",
        "pasd_bus_state",
        "fndh_state",
        "healthState",
        "smartbox24PortsCurrentDraw",
        "smartbox24PortsConnected",
        "SmartboxInputVoltage",
        "fndhport2powerstate",
        "pasdBushealthState",
        "PasdPortPowerSensed",
        "FndhPortPowerState",
        timeout=10.0,
        assert_no_error=False,
    )
