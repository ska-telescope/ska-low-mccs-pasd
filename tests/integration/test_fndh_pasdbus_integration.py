# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsFNDH."""

from __future__ import annotations

import gc

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState, ResultCode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator

gc.disable()  # TODO: why is this needed?


class TestfndhPasdBusIntegration:
    """Test pasdbus and fndh integration."""

    def test_fndh_pasd_integration(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of fndh with the pasdBus.

        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)
        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        # ----------------------------------------------------------------

        # Check that the devices enters the correct state after turning adminMode on
        # ================================================================
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # The fndh should enter UNKNOWN, if communication can be established
        # the FNDH has power.
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        # ================================================================

    def test_communication(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the Tango device's communication with the PaSD bus.

        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: a proxy to the PaSD bus device under test.
        :param fndh_simulator: the FNDH simulator under test
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        """
        # pylint: disable=too-many-statements
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

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
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)

        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdBushealthState"],
        )

        change_event_callbacks.assert_change_event(
            "pasdBushealthState", HealthState.UNKNOWN
        )
        assert pasd_bus_device.healthState == HealthState.UNKNOWN
        # -----------------------------------------------------------------

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

        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.UNKNOWN
        )
        change_event_callbacks.assert_change_event("pasd_bus_state", tango.DevState.ON)
        change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
        assert pasd_bus_device.healthState == HealthState.OK

        fndh_device.adminMode = AdminMode.ONLINE

        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["fndh_state"].assert_not_called()

        assert (
            fndh_device.ModbusRegisterMapRevisionNumber
            == FndhSimulator.MODBUS_REGISTER_MAP_REVISION
        )
        assert fndh_device.SysAddress == FndhSimulator.SYS_ADDRESS
        assert fndh_device.PcbRevisionNumber == FndhSimulator.PCB_REVISION
        assert fndh_device.CpuId == FndhSimulator.CPU_ID
        assert fndh_device.ChipId == FndhSimulator.CHIP_ID
        assert fndh_device.FirmwareVersion == FndhSimulator.DEFAULT_FIRMWARE_VERSION
        assert fndh_device.Uptime <= fndh_simulator.uptime
        assert fndh_device.PasdStatus == "OK"
        assert fndh_device.LedPattern == FndhSimulator.DEFAULT_LED_PATTERN
        assert list(fndh_device.Psu48vVoltages) == FndhSimulator.DEFAULT_PSU48V_VOLTAGES
        assert fndh_device.Psu48vCurrent == FndhSimulator.DEFAULT_PSU48V_CURRENT
        assert (
            list(fndh_device.Psu48vTemperatures)
            == FndhSimulator.DEFAULT_PSU48V_TEMPERATURES
        )
        assert fndh_device.PanelTemperature == FndhSimulator.DEFAULT_PANEL_TEMPERATURE
        assert fndh_device.FncbTemperature == FndhSimulator.DEFAULT_FNCB_TEMPERATURE
        assert fndh_device.FncbHumidity == FndhSimulator.DEFAULT_FNCB_HUMIDITY
        assert (
            fndh_device.CommsGatewayTemperature
            == FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE
        )
        assert (
            fndh_device.PowerModuleTemperature
            == FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE
        )
        assert (
            fndh_device.OutsideTemperature == FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE
        )
        assert (
            fndh_device.InternalAmbientTemperature
            == FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE
        )
        assert list(fndh_device.PortForcings) == fndh_simulator.port_forcings
        assert (
            list(fndh_device.PortsDesiredPowerOnline)
            == fndh_simulator.ports_desired_power_when_online
        )
        assert (
            list(fndh_device.PortsDesiredPowerOffline)
            == fndh_simulator.ports_desired_power_when_offline
        )
        assert list(fndh_device.PortsPowerSensed) == fndh_simulator.ports_power_sensed
        assert (
            list(fndh_device.Psu48vVoltage1Thresholds)
            == fndh_simulator.psu48v_voltage_1_thresholds
        )
        assert (
            list(fndh_device.Psu48vVoltage2Thresholds)
            == fndh_simulator.psu48v_voltage_2_thresholds
        )
        assert (
            list(fndh_device.Psu48vCurrentThresholds)
            == fndh_simulator.psu48v_current_thresholds
        )
        assert (
            list(fndh_device.Psu48vTemperature1Thresholds)
            == fndh_simulator.psu48v_temperature_1_thresholds
        )
        assert (
            list(fndh_device.Psu48vTemperature2Thresholds)
            == fndh_simulator.psu48v_temperature_2_thresholds
        )
        assert (
            list(fndh_device.PanelTemperatureThresholds)
            == fndh_simulator.panel_temperature_thresholds
        )
        assert (
            list(fndh_device.FncbTemperatureThresholds)
            == fndh_simulator.fncb_temperature_thresholds
        )
        assert (
            list(fndh_device.HumidityThresholds)
            == fndh_simulator.fncb_humidity_thresholds
        )
        assert (
            list(fndh_device.CommsGatewayTemperatureThresholds)
            == fndh_simulator.comms_gateway_temperature_thresholds
        )
        assert (
            list(fndh_device.PowerModuleTemperatureThresholds)
            == fndh_simulator.power_module_temperature_thresholds
        )
        assert (
            list(fndh_device.OutsideTemperatureThresholds)
            == fndh_simulator.outside_temperature_thresholds
        )
        assert (
            list(fndh_device.InternalAmbientTemperatureThresholds)
            == fndh_simulator.internal_ambient_temperature_thresholds
        )
        assert fndh_device.WarningFlags == FndhSimulator.DEFAULT_FLAGS
        assert fndh_device.AlarmFlags == FndhSimulator.DEFAULT_FLAGS

        for port in range(1, FndhSimulator.NUMBER_OF_PORTS + 1):
            is_port_on = fndh_simulator.ports_power_sensed[port - 1]
            if not is_port_on:
                assert getattr(fndh_device, f"Port{port}PowerState") == PowerState.OFF
            elif is_port_on:
                assert getattr(fndh_device, f"Port{port}PowerState") == PowerState.ON
            else:
                assert (
                    getattr(fndh_device, f"Port{port}PowerState") == PowerState.UNKNOWN
                )

    # pylint: disable=too-many-arguments
    def test_port_power(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the MccsFNDH port power state.

        - MccsFNDH.PortPowerState starts in a UNKNOWN state.
        - After MccsFNDH starts communication with the simulator it gets the
            simulated power state.
        - When we change the simulated power state, MccsFNDH is notified and updated.

        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: a proxy to the PaSD bus device under test.
        :param fndh_simulator: the FNDH simulator under test
        :param off_smartbox_attached_port: the FNDH port the off
            smartbox-under-test is attached to.
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        """
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE
        assert (
            fndh_device.PortPowerState(off_smartbox_attached_port) == PowerState.UNKNOWN
        )

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
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)

        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdBushealthState"],
        )

        change_event_callbacks.assert_change_event(
            "pasdBushealthState", HealthState.UNKNOWN
        )
        assert pasd_bus_device.healthState == HealthState.UNKNOWN

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

        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.UNKNOWN
        )
        change_event_callbacks.assert_change_event("pasd_bus_state", tango.DevState.ON)
        change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
        assert pasd_bus_device.healthState == HealthState.OK
        assert pasd_bus_device.InitializeFndh()[0] == ResultCode.OK

        fndh_device.adminMode = AdminMode.ONLINE

        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["fndh_state"].assert_not_called()

        fndh_device.subscribe_event(
            f"Port{off_smartbox_attached_port}PowerState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhPortPowerState"],
        )
        change_event_callbacks["fndhPortPowerState"].assert_change_event(PowerState.OFF)

        assert fndh_device.PortPowerState(off_smartbox_attached_port) == PowerState.OFF
        assert fndh_simulator.turn_port_on(off_smartbox_attached_port)

        change_event_callbacks["fndhPortPowerState"].assert_change_event(PowerState.ON)

        assert fndh_device.PortPowerState(off_smartbox_attached_port) == PowerState.ON


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "fndh_state",
        "pasd_bus_state",
        "pasdBushealthState",
        "smartbox24AlarmFlags",
        "fndhPortPowerState",
        timeout=20.0,
        assert_no_error=False,
    )
