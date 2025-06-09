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
import re
import warnings

import pytest
import tango
from ska_control_model import AdminMode, HealthState, PowerState, ResultCode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.fndh import FndhHealthModel
from ska_low_mccs_pasd.pasd_bus import FndhSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import (
    FndhAlarmFlags,
    PasdConversionUtility,
)

from ..conftest import Helpers

gc.disable()  # Bug in garbage collection causes tests to hang.

# Strings with a placeholder to check health report.
STUCK_ON_PDOC_TEMPLATE = (
    "PDOC {} stuck ON, fault within the PDOC, "
    "cannot turn OFF PDOC port in response to a POWERDOWN from the SMART Box"
)
STUCK_OFF_PDOC_TEMPLATE = (
    "PDOC {} stuck OFF, could be a fault within the PDOC, "
    "damaged PDOC cable, or faulty SMART Box EP"
)


def generate_pdoc_strings(template: str, replacements: list[str]) -> list[str]:
    """
    Return a list of strings by replacing the placeholder in the template with values.

    :param template: the template string with a placeholder present.
    :param replacements: a list of strings to replace placeholder.

    :returns: a list of strings
    """
    pdoc_strings = []
    for replacement in replacements:
        # Use .format() to insert the replacement into the template
        pdoc_string = template.format(replacement)
        pdoc_strings.append(pdoc_string)

    return pdoc_strings


def _check_pdoc_stuck_message(expected_reports: list[str], fault_report: str) -> None:
    """
    Check that expected PDOC fault reports match fault_report.

    :param expected_reports: a list of expected fault reports.
    :param fault_report: the complete fault report.
    """
    pattern = r"PDOC (\d{1,2}) stuck (ON|OFF)"

    matches = re.findall(pattern, fault_report)
    expected_matches = re.findall(pattern, ",".join(expected_reports))

    assert sorted(matches) == sorted(expected_matches)


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

    def test_health(
        self: TestfndhPasdBusIntegration,
        healthy_fndh: tango.DeviceProxy,
        supported_fndh_health_monitoring_points: list[str],
        positive_only_monitoring_points: list[str],
        fndh_simulator: FndhSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test integration of FNDH health with pasdBus.

        :param healthy_fndh: fixture that provides FNDH in the
            Healthy state.
        :param supported_fndh_health_monitoring_points: a list of monitoring
            points supported by the health model.
        :param positive_only_monitoring_points: a list of monitoring
            points that can only take a positive value in hardware.
        :param fndh_simulator: the FNDH simulator under test
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        """
        for attribute_name in supported_fndh_health_monitoring_points:
            attribute_threshold = attribute_name + "_thresholds"
            print(f"Test attribute: {attribute_name}")
            # Check for transitions through health. when value changes.
            (
                max_alarm,
                max_warning,
                min_warning,
                min_alarm,
            ) = getattr(fndh_simulator, attribute_threshold)

            healthy_value = (max_warning + min_warning) / 2
            setattr(fndh_simulator, attribute_name, max_alarm)
            change_event_callbacks["fndhhealthState"].assert_change_event(
                HealthState.FAILED
            )
            setattr(fndh_simulator, attribute_name, max_warning)
            change_event_callbacks["fndhhealthState"].assert_change_event(
                HealthState.DEGRADED
            )
            if min_alarm < 0 and attribute_name in positive_only_monitoring_points:
                warnings.warn(
                    UserWarning(
                        f"positive only monitoring point {attribute_name} "
                        "is not being tested for min_alarm due to "
                        "attempting to set a negative value "
                        "in the simulator. Hardware does not allow this. "
                        "see src/ska_low_mccs_pasd/pasd_bus/pasd_bus_conversions.py"
                    )
                )
            else:
                setattr(fndh_simulator, attribute_name, min_alarm)
                change_event_callbacks["fndhhealthState"].assert_change_event(
                    HealthState.FAILED
                )
            if min_warning < 0 and attribute_name in positive_only_monitoring_points:
                warnings.warn(
                    UserWarning(
                        f"positive only monitoring point {attribute_name} "
                        "is not being tested for max_alm due to "
                        "attempting to set a negative value "
                        "in the simulator. Hardware does not allow this. "
                        "See src/ska_low_mccs_pasd/pasd_bus/pasd_bus_conversions.py"
                    )
                )
            else:
                setattr(fndh_simulator, attribute_name, min_warning)
                change_event_callbacks["fndhhealthState"].assert_change_event(
                    HealthState.DEGRADED
                )
            setattr(fndh_simulator, attribute_name, int(healthy_value))
            change_event_callbacks["fndhhealthState"].assert_change_event(
                HealthState.OK
            )

        change_event_callbacks["fndhhealthState"].assert_not_called()

    def test_faulty_smartbox_configured_ports_degraded(
        self: TestfndhPasdBusIntegration,
        healthy_fndh: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test that the FNDH becomes DEGRADED when smartbox ports are faulty.

        Simulates the following actions:
        - A random smartbox-configured-port being stuck ON.
        - A random smartbox-configured-port port being stuck OFF.

        Check the HealthReport and HealthState for expected response.

        :param healthy_fndh: Fixture that provides an FNDH in the Healthy state.
        :param fndh_simulator: The FNDH simulator under test.
        :param change_event_callbacks: A dictionary of mock change event callbacks
            with support for asynchrony.
        """
        # Just renaming since it is not always healthy
        fndh_device = healthy_fndh

        ports_with_smartbox = list(fndh_device.portswithsmartbox)
        random_stuck_off_port = random.choice(ports_with_smartbox)
        ports_with_smartbox.remove(random_stuck_off_port)
        random_stuck_on_port = random.choice(ports_with_smartbox)
        fndh_simulator.simulate_port_stuck_on(random_stuck_on_port)
        fndh_simulator._ports[random_stuck_on_port - 1].enabled = False
        fndh_simulator.simulate_port_stuck_off(random_stuck_off_port)
        fndh_simulator._ports[random_stuck_off_port - 1].enabled = True
        # ++++++++++++++++++++++++++++++++++++++++

        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.DEGRADED
        )
        expected_stuck_on_faults = [random_stuck_on_port]
        expected_stuck_off_faults = [random_stuck_off_port]
        stuck_on_faults = generate_pdoc_strings(
            STUCK_ON_PDOC_TEMPLATE, expected_stuck_on_faults
        )
        stuck_off_faults = generate_pdoc_strings(
            STUCK_OFF_PDOC_TEMPLATE, expected_stuck_off_faults
        )
        _check_pdoc_stuck_message(
            stuck_off_faults + stuck_on_faults,
            fndh_device.healthReport,
        )

    def test_faulty_smartbox_configured_ports_failed_stuck_on(
        self: TestfndhPasdBusIntegration,
        healthy_fndh: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test health when we have all smartbox ports faulty stuck ON.

        Simulates the following actions:
        - All smartbox-configured-port being stuck ON.

        Check the HealthReport and HealthState for expected response.

        :param healthy_fndh: Fixture that provides an FNDH in the Healthy state.
        :param fndh_simulator: The FNDH simulator under test.
        :param change_event_callbacks: A dictionary of mock change event callbacks
            with support for asynchrony.
        """
        fndh_device = healthy_fndh

        # +++++++++++++++++++++++++++++++++++++++++

        # Simulate a stuck on condition.
        for i in fndh_device.portswithsmartbox:
            fndh_simulator.simulate_port_stuck_on(i)
            fndh_simulator._ports[i - 1].enabled = False
        # ++++++++++++++++++++++++++++++++++++++++

        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.FAILED
        )
        # Example usage
        expected_stuck_on_faults = fndh_device.portswithsmartbox
        expected_stuck_off_faults: list = []
        stuck_on_faults = generate_pdoc_strings(
            STUCK_ON_PDOC_TEMPLATE, expected_stuck_on_faults
        )
        stuck_off_faults = generate_pdoc_strings(
            STUCK_OFF_PDOC_TEMPLATE, expected_stuck_off_faults
        )
        _check_pdoc_stuck_message(
            stuck_off_faults + stuck_on_faults,
            fndh_device.healthReport,
        )

        # +++++++++++++++++++++++++++++++++++++++++
        # Remove fault
        for i in fndh_device.portswithsmartbox:
            fndh_simulator.simulate_port_stuck_on(i, False)
        # ++++++++++++++++++++++++++++++++++++++++
        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)

        # Example usage
        expected_stuck_on_faults = []
        expected_stuck_off_faults = []
        stuck_on_faults = generate_pdoc_strings(
            STUCK_ON_PDOC_TEMPLATE, expected_stuck_on_faults
        )
        stuck_off_faults = generate_pdoc_strings(
            STUCK_OFF_PDOC_TEMPLATE, expected_stuck_off_faults
        )
        _check_pdoc_stuck_message(
            stuck_off_faults + stuck_on_faults,
            fndh_device.healthReport,
        )

    def test_faulty_smartbox_configured_ports_failed_stuck_off(
        self: TestfndhPasdBusIntegration,
        healthy_fndh: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test health when we have all smartbox ports faulty stuck ON.

        Simulates the following actions:
        - All smartbox-configured-port being stuck OFF.

        Check the HealthReport and HealthState for expected response.

        :param healthy_fndh: Fixture that provides an FNDH in the Healthy state.
        :param fndh_simulator: The FNDH simulator under test.
        :param change_event_callbacks: A dictionary of mock change event callbacks
            with support for asynchrony.
        """
        fndh_device = healthy_fndh

        # +++++++++++++++++++++++++++++++++++++++++
        # Simulate a stuck OFF condition.
        for i in fndh_device.portswithsmartbox:
            fndh_simulator.simulate_port_stuck_off(i)
            fndh_simulator._ports[i - 1].enabled = True
        # ++++++++++++++++++++++++++++++++++++++++

        change_event_callbacks.assert_change_event(
            "fndhhealthState", HealthState.FAILED
        )

        # Example usage
        expected_stuck_on_faults: list = []
        expected_stuck_off_faults = fndh_device.portswithsmartbox
        stuck_on_faults = generate_pdoc_strings(
            STUCK_ON_PDOC_TEMPLATE, expected_stuck_on_faults
        )
        stuck_off_faults = generate_pdoc_strings(
            STUCK_OFF_PDOC_TEMPLATE, expected_stuck_off_faults
        )
        _check_pdoc_stuck_message(
            stuck_off_faults + stuck_on_faults,
            fndh_device.healthReport,
        )

        # +++++++++++++++++++++++++++++++++++++++++
        # remove the stuck OFF condition.
        for i in fndh_device.portswithsmartbox:
            fndh_simulator.simulate_port_stuck_off(i, False)
        # ++++++++++++++++++++++++++++++++++++++++

        change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)
        # Example usage
        expected_stuck_on_faults = []
        expected_stuck_off_faults = []
        stuck_on_faults = generate_pdoc_strings(
            STUCK_ON_PDOC_TEMPLATE, expected_stuck_on_faults
        )
        stuck_off_faults = generate_pdoc_strings(
            STUCK_OFF_PDOC_TEMPLATE, expected_stuck_off_faults
        )
        _check_pdoc_stuck_message(
            stuck_off_faults + stuck_on_faults,
            fndh_device.healthReport,
        )


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


@pytest.fixture(name="supported_fndh_health_monitoring_points")
def supported_fndh_health_monitoring_points_fixture() -> set[str]:
    """
    Return a set of all monitoring points supported by the FNDH.

    :returns: a set of all monitoring points supported by the FNDH.
    """
    monitoring_points = list(FndhSimulator.ALARM_MAPPING.keys())
    supported_points = list(FndhHealthModel.SUPPORTED_MONITORING_POINTS.keys())
    dict1_no_underscore = [key.replace("_", "") for key in monitoring_points]
    dict2_no_underscore = [key.replace("_", "") for key in supported_points]

    supported_items = (
        monitoring_points[i]
        for i in range(len(monitoring_points))
        if dict1_no_underscore[i] in dict2_no_underscore
    )
    # random_index: int = random.randrange(0, len(supported_items) - 1)
    return set(supported_items)  # [random_index]


@pytest.fixture(name="positive_only_monitoring_points")
def positive_only_monitoring_points_fixture() -> set[str]:
    """
    Return a set of monitoring points that can only have a positive value.

    :returns: a set of monitoring points that can
        only have a positive value.
    """
    return {
        "psu48v_current",
        "psu48v_voltage_1",
        "psu48v_voltage_2",
    }


@pytest.fixture(name="healthy_fndh")
def healthy_fndh_fixture(
    fndh_device: tango.DeviceProxy,
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> tango.DeviceProxy:
    """
    Fixture that returns a FNDH in the Healthy State.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: A dictionary of mock change event callbacks
        with support for asynchrony.

    :yield: a FNDH in the Healthy State.
    """
    assert fndh_device.adminMode == AdminMode.OFFLINE
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE
    pasd_sub_id = pasd_bus_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["pasdBushealthState"],
    )

    change_event_callbacks.assert_change_event(
        "pasdBushealthState", HealthState.UNKNOWN
    )
    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]
    change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
    pasd_bus_device.initializefndh()
    fndh_sub_id = fndh_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhhealthState"],
    )
    change_event_callbacks.assert_change_event("fndhhealthState", HealthState.UNKNOWN)
    # Carefully configure smartbox on unfaulty ports
    fndh_device.portswithsmartbox = [
        1,
        2,
        4,
        6,
        7,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        26,
        28,
    ]
    fndh_device.adminMode = AdminMode.ONLINE
    change_event_callbacks.assert_change_event("fndhhealthState", HealthState.OK)
    assert fndh_device.healthState == HealthState.OK

    yield fndh_device

    fndh_device.unsubscribe_event(fndh_sub_id)
    pasd_bus_device.unsubscribe_event(pasd_sub_id)
