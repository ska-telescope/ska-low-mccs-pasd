# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsPasdBus."""

# pylint: disable=too-many-lines
from __future__ import annotations

import gc
import json
import random

import pytest
import tango
from ska_control_model import AdminMode, HealthState, SimulationMode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FnccSimulator, FndhSimulator, SmartboxSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import (
    FndhAlarmFlags,
    PasdConversionUtility,
    SmartboxAlarmFlags,
)
from tests.harness import PasdTangoTestHarness

# TODO: Weird hang-at-garbage-collection bug
gc.disable()


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture(
    smartbox_id: int,
) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :param smartbox_id: id of the smartbox being addressed.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return MockTangoEventCallbackGroup(
        "adminMode",
        "healthState",
        "longRunningCommandResult",
        "longRunningCommandStatus",
        "state",
        "fndhStatus",
        "fndhLedPattern",
        "fndhPortsPowerSensed",
        "fndhPortsPowerControl",
        "fndhOutsideTemperatureThresholds",
        f"smartbox{smartbox_id}LedPattern",
        f"smartbox{smartbox_id}PortBreakersTripped",
        f"smartbox{smartbox_id}PortsPowerSensed",
        f"smartbox{smartbox_id}AlarmFlags",
        f"smartbox{smartbox_id}PcbTemperatureThresholds",
        timeout=30.0,
        assert_no_error=False,
    )


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    mock_pasd_hw_simulators: dict[
        int, FndhSimulator | FnccSimulator | SmartboxSimulator
    ],
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the PaSD bus Tango device under test.

    :param mock_pasd_hw_simulators:
        the FNDH and smartbox simulator backends that the TCP server will front,
        each wrapped with a mock so that we can assert calls.
    :yield: a proxy to the PaSD bus Tango device under test.
    """
    harness = PasdTangoTestHarness()
    harness.set_pasd_bus_simulator(mock_pasd_hw_simulators)
    harness.set_pasd_bus_device(polling_rate=0.1, device_polling_rate=0.1)
    with harness as context:
        pasd_bus_device = context.get_pasd_bus_device()
        pasd_bus_device.simulationMode = SimulationMode.TRUE
        yield pasd_bus_device


def test_communication(  # pylint: disable=too-many-statements
    pasd_bus_device: tango.DeviceProxy,
    fndh_simulator: FndhSimulator,
    smartbox_simulator: SmartboxSimulator,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device's communication with the PaSD bus.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param fndh_simulator: the FNDH simulator under test
    :param smartbox_simulator: the smartbox simulator under test.
    :param smartbox_id: id of the smartbox being addressed.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )

    change_event_callbacks.assert_change_event("healthState", HealthState.UNKNOWN)
    assert pasd_bus_device.healthState == HealthState.UNKNOWN

    # This is a bit of a cheat.
    # It's an implementation-dependent detail that
    # this is one of the last attributes to be read from the simulator.
    # We subscribe events on this attribute because we know that
    # once we have an updated value for this attribute,
    # we have an updated value for all of them.
    pasd_bus_device.subscribe_event(
        f"smartbox{smartbox_id}AlarmFlags",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}AlarmFlags"],
    )
    change_event_callbacks.assert_change_event(f"smartbox{smartbox_id}AlarmFlags", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK

    change_event_callbacks.assert_against_call(
        f"smartbox{smartbox_id}AlarmFlags", lookahead=5
    )

    assert (
        pasd_bus_device.fndhModbusRegisterMapRevisionNumber
        == FndhSimulator.MODBUS_REGISTER_MAP_REVISION
    )
    assert pasd_bus_device.fndhPcbRevisionNumber == FndhSimulator.PCB_REVISION
    assert (
        pasd_bus_device.fndhCpuId
        == PasdConversionUtility.convert_cpu_id(FndhSimulator.CPU_ID)[0]
    )
    assert (
        pasd_bus_device.fndhChipId
        == PasdConversionUtility.convert_chip_id(FndhSimulator.CHIP_ID)[0]
    )
    assert (
        pasd_bus_device.fndhFirmwareVersion
        == PasdConversionUtility.convert_firmware_version(
            [FndhSimulator.DEFAULT_FIRMWARE_VERSION]
        )[0]
    )
    assert (
        pasd_bus_device.fndhUptime
        <= PasdConversionUtility.convert_uptime(fndh_simulator.uptime)[0]
    )
    assert pasd_bus_device.fndhSysAddress == FndhSimulator.SYS_ADDRESS
    assert pasd_bus_device.fndhStatus == "OK"
    assert pasd_bus_device.fndhLedPattern == "service: OFF, status: GREENSLOW"
    assert list(
        pasd_bus_device.fndhPsu48vVoltages
    ) == PasdConversionUtility.scale_volts(FndhSimulator.DEFAULT_PSU48V_VOLTAGES)
    assert (
        pasd_bus_device.fndhPsu48vCurrent
        == PasdConversionUtility.scale_48vcurrents(
            [FndhSimulator.DEFAULT_PSU48V_CURRENT]
        )[0]
    )
    assert list(
        pasd_bus_device.fndhPsu48vTemperatures
    ) == PasdConversionUtility.scale_signed_16bit(
        FndhSimulator.DEFAULT_PSU48V_TEMPERATURES
    )
    assert (
        pasd_bus_device.fndhPanelTemperature
        == PasdConversionUtility.scale_signed_16bit(
            [FndhSimulator.DEFAULT_PANEL_TEMPERATURE]
        )[0]
    )
    assert (
        pasd_bus_device.fndhFncbTemperature
        == PasdConversionUtility.scale_signed_16bit(
            [FndhSimulator.DEFAULT_FNCB_TEMPERATURE]
        )[0]
    )
    assert pasd_bus_device.fndhFncbHumidity == FndhSimulator.DEFAULT_FNCB_HUMIDITY
    assert (
        pasd_bus_device.fndhCommsGatewayTemperature
        == PasdConversionUtility.scale_signed_16bit(
            [FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE]
        )[0]
    )
    assert (
        pasd_bus_device.fndhPowerModuleTemperature
        == PasdConversionUtility.scale_signed_16bit(
            [FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE]
        )[0]
    )
    assert (
        pasd_bus_device.fndhOutsideTemperature
        == PasdConversionUtility.scale_signed_16bit(
            [FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE]
        )[0]
    )
    assert (
        pasd_bus_device.fndhInternalAmbientTemperature
        == PasdConversionUtility.scale_signed_16bit(
            [FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE]
        )[0]
    )
    assert list(pasd_bus_device.fndhPortForcings) == fndh_simulator.port_forcings
    assert (
        list(pasd_bus_device.fndhPortsDesiredPowerOnline)
        == fndh_simulator.ports_desired_power_when_online
    )
    assert (
        list(pasd_bus_device.fndhPortsDesiredPowerOffline)
        == fndh_simulator.ports_desired_power_when_offline
    )
    assert (
        list(pasd_bus_device.fndhPortsPowerSensed) == fndh_simulator.ports_power_sensed
    )
    assert (
        list(pasd_bus_device.fndhPortsPowerControl)
        == fndh_simulator.ports_power_control
    )
    assert list(
        pasd_bus_device.fndhPsu48vVoltage1Thresholds
    ) == PasdConversionUtility.scale_volts(fndh_simulator.psu48v_voltage_1_thresholds)
    assert list(
        pasd_bus_device.fndhPsu48vVoltage2Thresholds
    ) == PasdConversionUtility.scale_volts(fndh_simulator.psu48v_voltage_2_thresholds)
    assert list(
        pasd_bus_device.fndhPsu48vCurrentThresholds
    ) == PasdConversionUtility.scale_48vcurrents(
        fndh_simulator.psu48v_current_thresholds
    )
    assert list(
        pasd_bus_device.fndhPsu48vTemperature1Thresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.psu48v_temperature_1_thresholds
    )
    assert list(
        pasd_bus_device.fndhPsu48vTemperature2Thresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.psu48v_temperature_2_thresholds
    )
    assert list(
        pasd_bus_device.fndhPanelTemperatureThresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.panel_temperature_thresholds
    )
    assert list(
        pasd_bus_device.fndhFncbTemperatureThresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.fncb_temperature_thresholds
    )
    assert (
        list(pasd_bus_device.fndhHumidityThresholds)
        == fndh_simulator.fncb_humidity_thresholds
    )
    assert list(
        pasd_bus_device.fndhCommsGatewayTemperatureThresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.comms_gateway_temperature_thresholds
    )
    assert list(
        pasd_bus_device.fndhPowerModuleTemperatureThresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.power_module_temperature_thresholds
    )
    assert list(
        pasd_bus_device.fndhOutsideTemperatureThresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.outside_temperature_thresholds
    )
    assert list(
        pasd_bus_device.fndhInternalAmbientTemperatureThresholds
    ) == PasdConversionUtility.scale_signed_16bit(
        fndh_simulator.internal_ambient_temperature_thresholds
    )
    assert pasd_bus_device.fndhWarningFlags == FndhAlarmFlags.NONE.name
    assert pasd_bus_device.fndhAlarmFlags == FndhAlarmFlags.NONE.name
    assert (
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}ModbusRegisterMapRevisionNumber",
        )
        == SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PcbRevisionNumber")
        == SmartboxSimulator.PCB_REVISION
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}CpuId")
        == PasdConversionUtility.convert_cpu_id(SmartboxSimulator.CPU_ID)[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}ChipId")
        == PasdConversionUtility.convert_chip_id(SmartboxSimulator.CHIP_ID)[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}FirmwareVersion")
        == PasdConversionUtility.convert_firmware_version(
            [SmartboxSimulator.DEFAULT_FIRMWARE_VERSION]
        )[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Uptime")
        <= PasdConversionUtility.convert_uptime(smartbox_simulator.uptime)[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Status")
        == SmartboxSimulator.DEFAULT_STATUS.name
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}LedPattern")
        == "service: OFF, status: YELLOWFAST"
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}InputVoltage")
        == PasdConversionUtility.scale_volts([SmartboxSimulator.DEFAULT_INPUT_VOLTAGE])[
            0
        ]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PowerSupplyOutputVoltage")
        == PasdConversionUtility.scale_volts(
            [SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE]
        )[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PowerSupplyTemperature")
        == PasdConversionUtility.scale_signed_16bit(
            [SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE]
        )[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PcbTemperature")
        == PasdConversionUtility.scale_signed_16bit(
            [SmartboxSimulator.DEFAULT_PCB_TEMPERATURE]
        )[0]
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}FemAmbientTemperature")
        == PasdConversionUtility.scale_signed_16bit(
            [SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE]
        )[0]
    )
    assert list(
        getattr(pasd_bus_device, f"smartbox{smartbox_id}FemCaseTemperatures")
    ) == PasdConversionUtility.scale_signed_16bit(
        SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES
    )
    assert list(
        getattr(pasd_bus_device, f"smartbox{smartbox_id}FemHeatsinkTemperatures")
    ) == PasdConversionUtility.scale_signed_16bit(
        SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}PortForcings"))
        == smartbox_simulator.port_forcings
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}PortBreakersTripped"))
        == smartbox_simulator.port_breakers_tripped
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}PortsDesiredPowerOnline",
            )
        )
        == smartbox_simulator.ports_desired_power_when_online
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}PortsDesiredPowerOffline",
            )
        )
        == smartbox_simulator.ports_desired_power_when_offline
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed"))
        == smartbox_simulator.ports_power_sensed
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsCurrentDraw"))
        == smartbox_simulator.ports_current_draw
    )
    assert list(
        getattr(pasd_bus_device, f"smartbox{smartbox_id}InputVoltageThresholds")
    ) == PasdConversionUtility.scale_volts(smartbox_simulator.input_voltage_thresholds)
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}PowerSupplyOutputVoltageThresholds",
        )
    ) == PasdConversionUtility.scale_volts(
        smartbox_simulator.power_supply_output_voltage_thresholds
    )
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}PowerSupplyTemperatureThresholds",
        )
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.power_supply_temperature_thresholds
    )
    assert list(
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PcbTemperatureThresholds")
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.pcb_temperature_thresholds
    )
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}FemAmbientTemperatureThresholds",
        )
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.fem_ambient_temperature_thresholds
    )
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}FemCaseTemperature1Thresholds",
        )
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.fem_case_temperature_1_thresholds
    )
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}FemCaseTemperature2Thresholds",
        )
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.fem_case_temperature_2_thresholds
    )
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}FemHeatsinkTemperature1Thresholds",
        )
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.fem_heatsink_temperature_1_thresholds
    )
    assert list(
        getattr(
            pasd_bus_device,
            f"smartbox{smartbox_id}FemHeatsinkTemperature2Thresholds",
        )
    ) == PasdConversionUtility.scale_signed_16bit(
        smartbox_simulator.fem_heatsink_temperature_2_thresholds
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}FemCurrentTripThresholds"))
        == smartbox_simulator.fem_current_trip_thresholds
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}WarningFlags")
        == SmartboxAlarmFlags.NONE.name
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}AlarmFlags")
        == SmartboxAlarmFlags.NONE.name
    )


def test_set_fndh_port_powers(
    pasd_bus_device: tango.DeviceProxy,
    fndh_simulator: FndhSimulator,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to turn FNDH ports on and off.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param fndh_simulator: the FNDH simulator under test
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        "fndhPortsPowerSensed",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortsPowerSensed"],
    )
    change_event_callbacks.assert_change_event("fndhPortsPowerSensed", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    pasd_bus_device.InitializeFndh()
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_simulator.ports_power_sensed
    )

    for i in range(1, 5):
        print(f"\nTest iteration {i}")
        fndh_ports_power_sensed = list(pasd_bus_device.fndhPortsPowerSensed)

        desired_port_powers: list[bool | None] = random.choices(
            [True, False, None], k=len(fndh_ports_power_sensed)
        )

        expected_fndh_ports_power_sensed = list(fndh_ports_power_sensed)
        for i, desired in enumerate(desired_port_powers):
            if desired is not None:
                expected_fndh_ports_power_sensed[i] = desired

        json_arg = {
            "port_powers": desired_port_powers,
            "stay_on_when_offline": False,
        }
        pasd_bus_device.SetFndhPortPowers(json.dumps(json_arg))
        change_event_callbacks.assert_change_event(
            "fndhPortsPowerSensed", expected_fndh_ports_power_sensed
        )


def test_fndh_led_pattern(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to set the FNDH LED pattern.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        "fndhLedPattern",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhLedPattern"],
    )
    change_event_callbacks.assert_change_event("fndhLedPattern", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    change_event_callbacks.assert_change_event(
        "fndhLedPattern", "service: OFF, status: GREENSLOW"
    )

    # Check for validation error
    json_argument = json.dumps({"pattern": "SERVICE"})
    with pytest.raises(tango.DevFailed) as exception:
        pasd_bus_device.SetFndhLedPattern(json_argument)
    assert "jsonschema.exceptions.ValidationError" in str(exception.value)

    # Set correct values
    json_argument = json.dumps({"pattern": "FAST"})
    pasd_bus_device.SetFndhLedPattern(json_argument)
    change_event_callbacks.assert_change_event(
        "fndhLedPattern", "service: FAST, status: GREENSLOW"
    )


def test_fndh_low_pass_filters(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to set the FNDH LED pattern.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    pasd_bus_device.simulationMode = SimulationMode.FALSE
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE
    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)
    pasd_bus_device.adminMode = AdminMode.ONLINE
    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    # Check for validation errors
    json_argument = json.dumps({"cutoff": 0.09})
    with pytest.raises(tango.DevFailed) as exception:
        pasd_bus_device.SetFndhLowPassFilters(json_argument)
    assert "jsonschema.exceptions.ValidationError" in str(exception.value)
    json_argument = json.dumps({"cutoff": 1000.1})
    with pytest.raises(tango.DevFailed) as exception:
        pasd_bus_device.SetFndhLowPassFilters(json_argument)
    assert "jsonschema.exceptions.ValidationError" in str(exception.value)

    # Set correct values
    json_argument = json.dumps({"cutoff": 10.0})
    pasd_bus_device.SetFndhLowPassFilters(json_argument)
    json_argument = json.dumps({"cutoff": 10.0, "extra_sensors": True})
    pasd_bus_device.SetFndhLowPassFilters(json_argument)


def test_fndh_port_faults(
    pasd_bus_device: tango.DeviceProxy,
    fndh_simulator: FndhSimulator,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to reset a smartbox port's breaker.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param fndh_simulator: the smartbox simulator under test.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    fndh_ports_connected = fndh_simulator.ports_connected
    connected_fndh_port = fndh_ports_connected.index(True) + 1

    # Confirm a connected port is turned on
    assert fndh_simulator.turn_port_on(connected_fndh_port) is None
    # Simulate over current condition and check
    assert fndh_simulator.simulate_port_over_current(connected_fndh_port)
    fndh_ports_power_sensed = fndh_simulator.ports_power_sensed
    assert fndh_ports_power_sensed[connected_fndh_port - 1] is False
    fndh_ports_power_control = fndh_simulator.ports_power_control
    assert fndh_ports_power_control[connected_fndh_port - 1]

    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)
    pasd_bus_device.subscribe_event(
        "fndhPortsPowerSensed",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortsPowerSensed"],
    )
    change_event_callbacks.assert_change_event("fndhPortsPowerSensed", None)
    pasd_bus_device.subscribe_event(
        "fndhPortsPowerControl",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortsPowerControl"],
    )
    change_event_callbacks.assert_change_event("fndhPortsPowerControl", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_ports_power_sensed, lookahead=2
    )
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerControl", fndh_ports_power_control, lookahead=2
    )

    # Revert over current condition and check
    assert fndh_simulator.simulate_port_over_current(connected_fndh_port, False)
    fndh_ports_power_sensed[connected_fndh_port - 1] = True
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_ports_power_sensed, lookahead=2
    )

    # Test port stuck on condition
    assert fndh_simulator.simulate_port_stuck_on(connected_fndh_port)
    assert fndh_simulator.simulate_port_forcing(False)

    fndh_ports_power_sensed = fndh_simulator.ports_power_sensed
    assert fndh_ports_power_sensed[connected_fndh_port - 1]
    fndh_ports_power_control = fndh_simulator.ports_power_control
    assert fndh_ports_power_control[connected_fndh_port - 1] is False

    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_ports_power_sensed, lookahead=2
    )
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerControl", fndh_ports_power_control, lookahead=2
    )


def test_set_smartbox_port_powers(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_simulator: SmartboxSimulator,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to turn smartbox ports on and off.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param smartbox_simulator: the smartbox simulator under test.
    :param smartbox_id: id of the smartbox being addressed.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        f"smartbox{smartbox_id}PortsPowerSensed",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}PortsPowerSensed"],
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsPowerSensed", None
    )

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    pasd_bus_device.InitializeSmartbox(smartbox_id)
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsPowerSensed",
        smartbox_simulator.ports_power_sensed,
    )

    for i in range(1, 5):
        print(f"\nTest iteration {i}")
        ports_power_sensed = list(
            getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed")
        )

        desired_port_powers: list[bool | None] = random.choices(
            [True, False, None], k=len(ports_power_sensed)
        )

        expected_ports_power_sensed = list(ports_power_sensed)
        for i, desired in enumerate(desired_port_powers):
            if desired is not None:
                expected_ports_power_sensed[i] = desired

        json_arg = {
            "smartbox_number": smartbox_id,
            "port_powers": desired_port_powers,
            "stay_on_when_offline": False,
        }
        pasd_bus_device.SetSmartboxPortPowers(json.dumps(json_arg))
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}PortsPowerSensed", expected_ports_power_sensed
        )


def test_reset_smartbox_port_breaker(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_simulator: SmartboxSimulator,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to reset a smartbox port's breaker.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param smartbox_simulator: the smartbox simulator under test.
    :param smartbox_id: id of the smartbox being addressed.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    smartbox_ports_connected = smartbox_simulator.ports_connected
    connected_smartbox_port = smartbox_ports_connected.index(True) + 1

    assert smartbox_simulator.initialize()
    assert smartbox_simulator.turn_port_on(connected_smartbox_port)
    assert smartbox_simulator.simulate_port_over_current(connected_smartbox_port)
    smartbox_port_breakers_tripped = smartbox_simulator.port_breakers_tripped
    assert smartbox_port_breakers_tripped[connected_smartbox_port - 1]
    # All of the above just to set up the simulator
    # so that one of its port breakers has tripped

    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        f"smartbox{smartbox_id}PortBreakersTripped",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}PortBreakersTripped"],
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortBreakersTripped", None
    )

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortBreakersTripped",
        smartbox_port_breakers_tripped,
    )

    json_argument = json.dumps(
        {
            "smartbox_number": smartbox_id,
            "port_number": connected_smartbox_port,
        }
    )
    print("Reset breaker command sending")
    pasd_bus_device.ResetSmartboxPortBreaker(json_argument)
    print("Reset breaker command sent")
    smartbox_port_breakers_tripped[connected_smartbox_port - 1] = False
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortBreakersTripped",
        smartbox_port_breakers_tripped,
    )


def test_smartbox_led_pattern(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to set a smartbox's LED pattern.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param smartbox_id: id of the smartbox being addressed.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        f"smartbox{smartbox_id}LedPattern",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}LedPattern"],
    )
    change_event_callbacks.assert_change_event(f"smartbox{smartbox_id}LedPattern", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}LedPattern", "service: OFF, status: YELLOWFAST"
    )

    # Check for validation error
    json_argument = json.dumps({"smartbox_number": smartbox_id, "pattern": "SERVICE"})
    with pytest.raises(tango.DevFailed) as exception:
        pasd_bus_device.SetSmartboxLedPattern(json_argument)
    assert "jsonschema.exceptions.ValidationError" in str(exception.value)

    # Set correct values
    json_argument = json.dumps({"smartbox_number": smartbox_id, "pattern": "FAST"})
    pasd_bus_device.SetSmartboxLedPattern(json_argument)
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}LedPattern", "service: FAST, status: YELLOWFAST"
    )


def test_smartbox_low_pass_filters(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to set a smartbox's LED pattern.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param smartbox_id: id of the smartbox being addressed.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    pasd_bus_device.simulationMode = SimulationMode.FALSE
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE
    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)
    pasd_bus_device.adminMode = AdminMode.ONLINE
    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    # Check for validation errors
    json_argument = json.dumps({"smartbox_number": smartbox_id, "cutoff": 0.09})
    with pytest.raises(tango.DevFailed) as exception:
        pasd_bus_device.SetSmartboxLowPassFilters(json_argument)
    assert "jsonschema.exceptions.ValidationError" in str(exception.value)
    json_argument = json.dumps({"smartbox_number": smartbox_id, "cutoff": 1000.1})
    with pytest.raises(tango.DevFailed) as exception:
        pasd_bus_device.SetSmartboxLowPassFilters(json_argument)
    assert "jsonschema.exceptions.ValidationError" in str(exception.value)

    # Set correct values
    json_argument = json.dumps({"smartbox_number": smartbox_id, "cutoff": 10.0})
    pasd_bus_device.SetSmartboxLowPassFilters(json_argument)
    json_argument = json.dumps(
        {"smartbox_number": smartbox_id, "cutoff": 10.0, "extra_sensors": True}
    )
    pasd_bus_device.SetSmartboxLowPassFilters(json_argument)


def test_set_fndh_thresholds(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to set an FNDH's alarm thresholds.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        "fndhOutsideTemperatureThresholds",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhOutsideTemperatureThresholds"],
    )
    change_event_callbacks.assert_change_event("fndhOutsideTemperatureThresholds", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    pasd_bus_device.fndhOutsideTemperatureThresholds = [80, 70, 40, 30]

    change_event_callbacks.assert_change_event(
        "fndhOutsideTemperatureThresholds", [80, 70, 40, 30]
    )


def test_set_smartbox_thresholds(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to set a smartbox's alarm thresholds.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param smartbox_id: id of the smartbox being addressed.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    pasd_bus_device.subscribe_event(
        f"smartbox{smartbox_id}PcbTemperatureThresholds",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}PcbTemperatureThresholds"],
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PcbTemperatureThresholds", None
    )

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    setattr(
        pasd_bus_device,
        f"smartbox{smartbox_id}PcbTemperatureThresholds",
        [55, 50, 20, 0],
    )

    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PcbTemperatureThresholds", [55, 50, 20, 0]
    )
