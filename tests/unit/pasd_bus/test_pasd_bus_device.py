# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsPasdBus."""

from __future__ import annotations

import gc
import json
import random

import pytest
import tango
from ska_control_model import AdminMode, HealthState
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import SmartboxSimulator
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
        f"smartbox{smartbox_id}LedPattern",
        f"smartbox{smartbox_id}PortBreakersTripped",
        f"smartbox{smartbox_id}PortsPowerSensed",
        f"smartbox{smartbox_id}AlarmFlags",
        timeout=20.0,
        assert_no_error=False,
    )


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    mock_fndh_simulator: FndhSimulator,
    mock_smartbox_simulators: dict[int, SmartboxSimulator],
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the PaSD bus Tango device under test.

    :param mock_fndh_simulator:
        the FNDH simulator backend that the TCP server will front,
        wrapped with a mock so that we can assert calls.
    :param mock_smartbox_simulators:
        the smartbox simulator backends that the TCP server will front,
        each wrapped with a mock so that we can assert calls.

    :yield: a proxy to the PaSD bus Tango device under test.
    """
    harness = PasdTangoTestHarness()
    harness.set_pasd_bus_simulator(mock_fndh_simulator, mock_smartbox_simulators)
    harness.set_pasd_bus_device(polling_rate=0.1, device_polling_rate=0.2)
    with harness as context:
        yield context.get_pasd_bus_device()


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
    assert pasd_bus_device.fndhCpuId == FndhSimulator.CPU_ID
    assert pasd_bus_device.fndhChipId == FndhSimulator.CHIP_ID
    assert pasd_bus_device.fndhFirmwareVersion == FndhSimulator.DEFAULT_FIRMWARE_VERSION
    assert pasd_bus_device.fndhUptime <= fndh_simulator.uptime
    assert pasd_bus_device.fndhSysAddress == FndhSimulator.SYS_ADDRESS
    assert pasd_bus_device.fndhStatus == "OK"
    assert pasd_bus_device.fndhLedPattern == FndhSimulator.DEFAULT_LED_PATTERN
    assert (
        list(pasd_bus_device.fndhPsu48vVoltages)
        == FndhSimulator.DEFAULT_PSU48V_VOLTAGES
    )
    assert pasd_bus_device.fndhPsu48vCurrent == FndhSimulator.DEFAULT_PSU48V_CURRENT
    assert (
        list(pasd_bus_device.fndhPsu48vTemperatures)
        == FndhSimulator.DEFAULT_PSU48V_TEMPERATURES
    )
    assert (
        pasd_bus_device.fndhPanelTemperature == FndhSimulator.DEFAULT_PANEL_TEMPERATURE
    )
    assert pasd_bus_device.fndhFncbTemperature == FndhSimulator.DEFAULT_FNCB_TEMPERATURE
    assert pasd_bus_device.fndhFncbHumidity == FndhSimulator.DEFAULT_FNCB_HUMIDITY
    assert (
        pasd_bus_device.fndhCommsGatewayTemperature
        == FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE
    )
    assert (
        pasd_bus_device.fndhPowerModuleTemperature
        == FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE
    )
    assert (
        pasd_bus_device.fndhOutsideTemperature
        == FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE
    )
    assert (
        pasd_bus_device.fndhInternalAmbientTemperature
        == FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE
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
        list(pasd_bus_device.fndhPsu48vVoltage1Thresholds)
        == fndh_simulator.psu48v_voltage_1_thresholds
    )
    assert (
        list(pasd_bus_device.fndhPsu48vVoltage2Thresholds)
        == fndh_simulator.psu48v_voltage_2_thresholds
    )
    assert (
        list(pasd_bus_device.fndhPsu48vCurrentThresholds)
        == fndh_simulator.psu48v_current_thresholds
    )
    assert (
        list(pasd_bus_device.fndhPsu48vTemperature1Thresholds)
        == fndh_simulator.psu48v_temperature_1_thresholds
    )
    assert (
        list(pasd_bus_device.fndhPsu48vTemperature2Thresholds)
        == fndh_simulator.psu48v_temperature_2_thresholds
    )
    assert (
        list(pasd_bus_device.fndhPanelTemperatureThresholds)
        == fndh_simulator.panel_temperature_thresholds
    )
    assert (
        list(pasd_bus_device.fndhFncbTemperatureThresholds)
        == fndh_simulator.fncb_temperature_thresholds
    )
    assert (
        list(pasd_bus_device.fndhHumidityThresholds)
        == fndh_simulator.fncb_humidity_thresholds
    )
    assert (
        list(pasd_bus_device.fndhCommsGatewayTemperatureThresholds)
        == fndh_simulator.comms_gateway_temperature_thresholds
    )
    assert (
        list(pasd_bus_device.fndhPowerModuleTemperatureThresholds)
        == fndh_simulator.power_module_temperature_thresholds
    )
    assert (
        list(pasd_bus_device.fndhOutsideTemperatureThresholds)
        == fndh_simulator.outside_temperature_thresholds
    )
    assert (
        list(pasd_bus_device.fndhInternalAmbientTemperatureThresholds)
        == fndh_simulator.internal_ambient_temperature_thresholds
    )
    assert pasd_bus_device.fndhWarningFlags == FndhSimulator.DEFAULT_FLAGS
    assert pasd_bus_device.fndhAlarmFlags == FndhSimulator.DEFAULT_FLAGS
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
        == SmartboxSimulator.CPU_ID
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}ChipId")
        == SmartboxSimulator.CHIP_ID
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}FirmwareVersion")
        == SmartboxSimulator.DEFAULT_FIRMWARE_VERSION
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Uptime")
        <= smartbox_simulator.uptime
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Status")
        == SmartboxSimulator.DEFAULT_STATUS
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}LedPattern")
        == SmartboxSimulator.DEFAULT_LED_PATTERN
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}InputVoltage")
        == SmartboxSimulator.DEFAULT_INPUT_VOLTAGE
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PowerSupplyOutputVoltage")
        == SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PowerSupplyTemperature")
        == SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PcbTemperature")
        == SmartboxSimulator.DEFAULT_PCB_TEMPERATURE
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}FemAmbientTemperature")
        == SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}FemCaseTemperatures"))
        == SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}FemHeatsinkTemperatures"))
        == SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
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
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}InputVoltageThresholds"))
        == smartbox_simulator.input_voltage_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}PowerSupplyOutputVoltageThresholds",
            )
        )
        == smartbox_simulator.power_supply_output_voltage_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}PowerSupplyTemperatureThresholds",
            )
        )
        == smartbox_simulator.power_supply_temperature_thresholds
    )
    assert (
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}PcbTemperatureThresholds"))
        == smartbox_simulator.pcb_temperature_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}FemAmbientTemperatureThresholds",
            )
        )
        == smartbox_simulator.fem_ambient_temperature_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}FemCaseTemperature1Thresholds",
            )
        )
        == smartbox_simulator.fem_case_temperature_1_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}FemCaseTemperature2Thresholds",
            )
        )
        == smartbox_simulator.fem_case_temperature_2_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}FemHeatsinkTemperature1Thresholds",
            )
        )
        == smartbox_simulator.fem_heatsink_temperature_1_thresholds
    )
    assert (
        list(
            getattr(
                pasd_bus_device,
                f"smartbox{smartbox_id}FemHeatsinkTemperature2Thresholds",
            )
        )
        == smartbox_simulator.fem_heatsink_temperature_2_thresholds
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem1CurrentTripThreshold")
        == smartbox_simulator.fem1_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem2CurrentTripThreshold")
        == smartbox_simulator.fem2_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem3CurrentTripThreshold")
        == smartbox_simulator.fem3_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem4CurrentTripThreshold")
        == smartbox_simulator.fem4_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem5CurrentTripThreshold")
        == smartbox_simulator.fem5_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem6CurrentTripThreshold")
        == smartbox_simulator.fem6_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem7CurrentTripThreshold")
        == smartbox_simulator.fem7_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem8CurrentTripThreshold")
        == smartbox_simulator.fem8_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem9CurrentTripThreshold")
        == smartbox_simulator.fem9_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem10CurrentTripThreshold")
        == smartbox_simulator.fem10_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem11CurrentTripThreshold")
        == smartbox_simulator.fem11_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}Fem12CurrentTripThreshold")
        == smartbox_simulator.fem12_current_trip_threshold
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}WarningFlags")
        == SmartboxSimulator.DEFAULT_FLAGS
    )
    assert (
        getattr(pasd_bus_device, f"smartbox{smartbox_id}AlarmFlags")
        == SmartboxSimulator.DEFAULT_FLAGS
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

    change_event_callbacks.assert_change_event("fndhLedPattern", "OFF")

    pasd_bus_device.SetFndhLedPattern("SERVICE")
    change_event_callbacks.assert_change_event("fndhLedPattern", "SERVICE")


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
    assert smartbox_simulator.simulate_port_breaker_trip(connected_smartbox_port)
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
    pasd_bus_device.ResetSmartboxPortBreaker(json_argument)
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
        f"smartbox{smartbox_id}LedPattern", "OFF"
    )

    json_argument = json.dumps({"smartbox_number": smartbox_id, "pattern": "SERVICE"})
    pasd_bus_device.SetSmartboxLedPattern(json_argument)
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}LedPattern", "SERVICE"
    )
