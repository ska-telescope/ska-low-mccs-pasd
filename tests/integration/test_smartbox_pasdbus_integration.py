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

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import SmartboxSimulator

gc.disable()  # TODO: why is this needed?


class TestSmartBoxPasdBusIntegration:
    """Test pasdbus, smartbox, fndh integration."""

    def test_smartbox_power_state(  # pylint: disable=too-many-statements
        self: TestSmartBoxPasdBusIntegration,
        smartbox_devices: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of smartbox with the pasdBus and FNDH.

        This test looks at the power state transitions.
        It tests that the devices are power change events:
        - MccsPasd pushed the power state of all ports
        - This is received by the MccsFndh
        - MccsFndh pushed the power state of each individual port
        - MccsSmartBox is subscribed to a single port and receives this

        This test also looks at powerstate retreival and recovery after a
        loss in connection.
        - Smartbox stops listening to a port.
        - the port turn off
        - when the smartbox starts listening again it gets a update on the
        powerstate.

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
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        smartbox_device = smartbox_devices[0]
        assert smartbox_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE
        assert fndh_device.adminMode == AdminMode.OFFLINE

        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.DISABLE
        )
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
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["healthState"],
        )

        change_event_callbacks.assert_change_event("healthState", HealthState.UNKNOWN)
        assert pasd_bus_device.healthState == HealthState.UNKNOWN
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        # ----------------------------------------------------------------
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
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        change_event_callbacks.assert_change_event("healthState", HealthState.OK)
        assert pasd_bus_device.healthState == HealthState.OK

        change_event_callbacks.assert_against_call("smartbox24PortsCurrentDraw")

        # Turn the Fndh On
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.OFF)
        change_event_callbacks["fndh_state"].assert_not_called()

        # The smartbox should enter UNKNOWN, then it should check with the
        # The fndh that the port this subrack is attached to
        # has power, this is simulated as off.

        # Check that we get a DevFailed for accessing non initialied attributes.
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

        # The Smartbox does not yet know the Fndh Port it is attached.
        # Therefore, the state will transition to unknown.
        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_not_called()

        # ----------------------------------------------
        # Station works out what port the smartbox is on
        # ----------------------------------------------

        # check the port power state as reported by Fndh and PasdBus
        fndh_reported_port_power = fndh_device.IsPortOn(2)
        pasdbus_reported_port_power = pasd_bus_device.fndhPortsPowerSensed[1]
        assert fndh_reported_port_power == pasdbus_reported_port_power

        # Update the smartbox Fndhport and check it is called back
        assert smartbox_device.fndhPort == 0
        smartbox_device.fndhPort = 2

        # check that the smartbox gets a callback with the correct power state.
        if fndh_reported_port_power:
            change_event_callbacks["smartbox_state"].assert_change_event(
                tango.DevState.ON
            )
        else:
            change_event_callbacks["smartbox_state"].assert_change_event(
                tango.DevState.OFF
            )

        # Check a situation:
        # 1 - SmartBox stops listening to device
        # 2 - Power state of device changes
        # 3 - SmartBox reconnects
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
            "fndhport2powerstate", PowerState.UNKNOWN
        )

        change_event_callbacks["fndhport2powerstate"].assert_not_called()
        change_event_callbacks["smartbox_state"].assert_not_called()

        fndh_device.PowerOnPort(2)

        change_event_callbacks["smartbox_state"].assert_not_called()

        change_event_callbacks.assert_change_event("fndhport2powerstate", PowerState.ON)

        # When the smartbox want to listen again it gets the most recent power state.
        # TODO: MCCS-1485: This is a hack until we add unsubscribe.
        smartbox_device.fndhPort = 2

        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["smartbox_state"].assert_not_called()

    # pylint: disable-next=too-many-arguments, too-many-statements
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
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        smartbox_device = smartbox_devices[0]
        assert smartbox_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE
        assert fndh_device.adminMode == AdminMode.OFFLINE

        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.DISABLE
        )
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
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["healthState"],
        )

        change_event_callbacks.assert_change_event("healthState", HealthState.UNKNOWN)
        assert pasd_bus_device.healthState == HealthState.UNKNOWN
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        # ----------------------------------------------------------------
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
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        change_event_callbacks.assert_change_event("healthState", HealthState.OK)
        assert pasd_bus_device.healthState == HealthState.OK

        change_event_callbacks.assert_against_call("smartbox24PortsCurrentDraw")

        # Turn the Fndh On
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.OFF)
        change_event_callbacks["fndh_state"].assert_not_called()

        # The smartbox should enter UNKNOWN, then it should check with the
        # The fndh that the port this subrack is attached to
        # has power, this is simulated as off.

        # Check that we get a DevFailed for accessing non initialied attributes.
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

        # The Smartbox does not yet know the Fndh Port it is attached.
        # Therefore, the state will transition to unknown.
        smartbox_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_not_called()

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

        # TODO: This is a bit of a hack. We want a setter method on the simulator.
        # rather than changing the class attribute.
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
        timeout=10.0,
        assert_no_error=False,
    )
