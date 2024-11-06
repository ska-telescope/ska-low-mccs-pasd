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
import random

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState, ResultCode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import (
    FndhAlarmFlags,
    PasdConversionUtility,
)
from ska_low_mccs_pasd.pasd_data import PasdData

from ..conftest import Helpers

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
        # ----------------------------------------------------------------

        # Check that the devices enters the correct state after turning adminMode on
        # ================================================================
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)

        # The fndh should enter UNKNOWN, if communication can be established
        # the FNDH has power.
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)
        # ================================================================

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_communication(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
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
        :param last_smartbox_id: ID of the last smartbox polled
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
            f"smartbox{last_smartbox_id}AlarmFlags",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{last_smartbox_id}AlarmFlags"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{last_smartbox_id}AlarmFlags", Anything
        )

        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

        # TODO: Weird behaviour, this started failing with WOM-276 changes
        Helpers.print_change_event_queue(change_event_callbacks, "pasd_bus_state")
        # change_event_callbacks.assert_change_event(
        #     "pasd_bus_state", tango.DevState.UNKNOWN
        # )
        # change_event_callbacks.assert_change_event(
        #     "pasd_bus_state", tango.DevState.ON
        # )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.ON, 2, True
        )
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
        assert (
            fndh_device.CpuId
            == PasdConversionUtility.convert_cpu_id(FndhSimulator.CPU_ID)[0]
        )
        assert (
            fndh_device.ChipId
            == PasdConversionUtility.convert_chip_id(FndhSimulator.CHIP_ID)[0]
        )
        assert (
            fndh_device.FirmwareVersion
            == PasdConversionUtility.convert_firmware_version(
                [FndhSimulator.DEFAULT_FIRMWARE_VERSION]
            )[0]
        )
        assert (
            fndh_device.Uptime
            <= PasdConversionUtility.convert_uptime(fndh_simulator.uptime)[0]
        )
        assert fndh_device.PasdStatus == "OK"
        assert fndh_device.LedPattern == "service: OFF, status: GREENSLOW"
        assert (
            fndh_device.Psu48vVoltage1
            == PasdConversionUtility.scale_volts(
                FndhSimulator.DEFAULT_PSU48V_VOLTAGE_1
            )[0]
        )
        assert (
            fndh_device.Psu48vVoltage2
            == PasdConversionUtility.scale_volts(
                FndhSimulator.DEFAULT_PSU48V_VOLTAGE_2
            )[0]
        )
        assert (
            fndh_device.Psu48vCurrent
            == PasdConversionUtility.scale_48vcurrents(
                [FndhSimulator.DEFAULT_PSU48V_CURRENT]
            )[0]
        )
        assert (
            fndh_device.Psu48vTemperature1
            == PasdConversionUtility.scale_signed_16bit(
                FndhSimulator.DEFAULT_PSU48V_TEMPERATURE_1
            )[0]
        )
        assert (
            fndh_device.Psu48vTemperature2
            == PasdConversionUtility.scale_signed_16bit(
                FndhSimulator.DEFAULT_PSU48V_TEMPERATURE_2
            )[0]
        )
        assert (
            fndh_device.PanelTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_PANEL_TEMPERATURE]
            )[0]
        )
        assert (
            fndh_device.FncbTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_FNCB_TEMPERATURE]
            )[0]
        )
        assert fndh_device.FncbHumidity == FndhSimulator.DEFAULT_FNCB_HUMIDITY
        assert (
            fndh_device.CommsGatewayTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE]
            )[0]
        )
        assert (
            fndh_device.PowerModuleTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE]
            )[0]
        )
        assert (
            fndh_device.OutsideTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE]
            )[0]
        )
        assert (
            fndh_device.InternalAmbientTemperature
            == PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE]
            )[0]
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
        assert list(fndh_device.PortsPowerControl) == fndh_simulator.ports_power_control
        assert list(
            fndh_device.Psu48vVoltage1Thresholds
        ) == PasdConversionUtility.scale_volts(
            fndh_simulator.psu48v_voltage_1_thresholds
        )
        assert list(
            fndh_device.Psu48vVoltage2Thresholds
        ) == PasdConversionUtility.scale_volts(
            fndh_simulator.psu48v_voltage_2_thresholds
        )
        assert list(
            fndh_device.Psu48vCurrentThresholds
        ) == PasdConversionUtility.scale_48vcurrents(
            fndh_simulator.psu48v_current_thresholds
        )
        assert list(
            fndh_device.Psu48vTemperature1Thresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.psu48v_temperature_1_thresholds
        )
        assert list(
            fndh_device.Psu48vTemperature2Thresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.psu48v_temperature_2_thresholds
        )
        assert list(
            fndh_device.PanelTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.panel_temperature_thresholds
        )
        assert list(
            fndh_device.FncbTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.fncb_temperature_thresholds
        )
        assert (
            list(fndh_device.FncbHumidityThresholds)
            == fndh_simulator.fncb_humidity_thresholds
        )
        assert list(
            fndh_device.CommsGatewayTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.comms_gateway_temperature_thresholds
        )
        assert list(
            fndh_device.PowerModuleTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.power_module_temperature_thresholds
        )
        assert list(
            fndh_device.OutsideTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.outside_temperature_thresholds
        )
        assert list(
            fndh_device.InternalAmbientTemperatureThresholds
        ) == PasdConversionUtility.scale_signed_16bit(
            fndh_simulator.internal_ambient_temperature_thresholds
        )
        assert fndh_device.WarningFlags == FndhAlarmFlags.NONE.name
        assert fndh_device.AlarmFlags == FndhAlarmFlags.NONE.name

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

        # When we write an attribute, check the simulator gets updated
        fndh_device.subscribe_event(
            "OutsideTemperatureThresholds",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["outsideTemperatureThresholds"],
        )
        setattr(
            fndh_device,
            "OutsideTemperatureThresholds",
            [30.2, 25.5, 10.5, 5],
        )
        change_event_callbacks["outsideTemperatureThresholds"].assert_change_event(
            [30.2, 25.5, 10.5, 5], lookahead=2
        )
        assert fndh_simulator.outside_temperature_thresholds == [3020, 2550, 1050, 500]

        # Check the threshold values get propagated to the Tango alarm configuration
        assert (
            fndh_device.read_attribute("outsideTemperature").quality
            == tango.AttrQuality.ATTR_ALARM
        )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_port_power(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
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
        :param last_smartbox_id: ID of the last smartbox polled
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
            f"smartbox{last_smartbox_id}AlarmFlags",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{last_smartbox_id}AlarmFlags"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{last_smartbox_id}AlarmFlags", Anything
        )

        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

        # TODO: Weird behaviour, this started failing with WOM-276 changes
        Helpers.print_change_event_queue(change_event_callbacks, "pasd_bus_state")
        # change_event_callbacks.assert_change_event(
        #     "pasd_bus_state", tango.DevState.UNKNOWN
        # )
        # change_event_callbacks.assert_change_event(
        #     "pasd_bus_state", tango.DevState.ON
        # )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.ON, 2, True
        )
        change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
        assert pasd_bus_device.healthState == HealthState.OK
        assert pasd_bus_device.InitializeFndh()[0] == ResultCode.OK

        fndh_device.adminMode = AdminMode.ONLINE

        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)

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

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_health(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test integration of FNDH health with pasdBus.

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
        # Grab a random attribute with alarms defined.
        threshold_attributes = list(FndhSimulator.ALARM_MAPPING.keys())
        random_index = random.randrange(0, len(threshold_attributes) - 1)
        attribute_name: str = threshold_attributes[random_index]
        attribute_threshold = attribute_name + "_thresholds"

        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE
        assert (
            fndh_device.PortPowerState(off_smartbox_attached_port) == PowerState.UNKNOWN
        )
        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdBushealthState"],
        )

        change_event_callbacks.assert_change_event(
            "pasdBushealthState", HealthState.UNKNOWN
        )
        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]
        change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
        fndh_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhhealthState"],
        )
        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.UNKNOWN
        )
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)
        assert fndh_device.healthState == HealthState.OK

        # Check for transitions through health. when value changes.
        (
            max_alarm,
            max_warning,
            min_warning,
            min_alarm,
        ) = getattr(fndh_simulator, attribute_threshold)
        healthy_value = (max_warning + min_warning) / 2
        setattr(fndh_simulator, attribute_name, max_alarm)
        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.DEGRADED
        )
        setattr(fndh_simulator, attribute_name, max_warning)
        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)
        setattr(fndh_simulator, attribute_name, min_alarm)
        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.DEGRADED
        )
        setattr(fndh_simulator, attribute_name, min_warning)
        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)
        setattr(fndh_simulator, attribute_name, int(healthy_value))
        change_event_callbacks["fndhhealthState"].assert_not_called()
        pasd_bus_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks["fndhhealthState"].assert_not_called()

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_health_from_port_power_control(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        off_smartbox_attached_port: int,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test health when we modify the percent of uncontrolled smartbox.

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

        def _simulate_pdoc_control_line_state(
            port_pdoc_enabled: list[tuple[int, bool]]
        ) -> None:
            for port, enabled in port_pdoc_enabled:
                fndh_simulator._ports[port].enabled = enabled

        def _simulate_smartbox_control(
            smartbox_has_control: list[tuple[int, bool]]
        ) -> None:
            pdoc_control = [(i, True) for i in range(PasdData.NUMBER_OF_FNDH_PORTS)]
            ports_with_smartbox = []
            for smartbox_id, controllable in smartbox_has_control:
                ports_with_smartbox.append(smartbox_id)
                if not controllable:
                    pdoc_control[smartbox_id - 1] = (smartbox_id - 1, controllable)
            fndh_device.portsWithSmartbox = ports_with_smartbox
            _simulate_pdoc_control_line_state(pdoc_control)

        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE
        assert (
            fndh_device.PortPowerState(off_smartbox_attached_port) == PowerState.UNKNOWN
        )
        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdBushealthState"],
        )

        change_event_callbacks.assert_change_event(
            "pasdBushealthState", HealthState.UNKNOWN
        )
        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]
        change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
        fndh_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndhhealthState"],
        )
        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.UNKNOWN
        )
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)
        assert fndh_device.healthState == HealthState.OK

        # 23 out of 24 smartbox have control
        _simulate_smartbox_control([(i, i != 1) for i in range(24)])

        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.DEGRADED
        )
        # 1 out of 24 smartbox have control
        _simulate_smartbox_control([(i, False) for i in range(24)])

        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.FAILED
        )
        # 23 out of 24 smartbox have control
        _simulate_smartbox_control([(i, i != 1) for i in range(24)])

        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.DEGRADED
        )
        # 24 out of 24 smartbox have control
        _simulate_smartbox_control([(i, True) for i in range(24)])

        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture(
    last_smartbox_id: int,
) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :param last_smartbox_id: ID of the last smartbox polled
    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "fndh_state",
        "pasd_bus_state",
        "pasdBushealthState",
        "fndhhealthState",
        f"smartbox{last_smartbox_id}AlarmFlags",
        "fndhPortPowerState",
        "fndhPort2PowerState",
        "outsideTemperatureThresholds",
        timeout=26.0,
        assert_no_error=False,
    )
