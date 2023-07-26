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
from typing import Generator

import pytest
import tango
from ska_control_model import AdminMode, HealthState, LoggingLevel
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import SmartboxSimulator

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
        "fndhPortBreakersTripped",
        "fndhPortsConnected",
        "fndhPortsPowerSensed",
        f"smartbox{smartbox_id}LedPattern",
        f"smartbox{smartbox_id}PortBreakersTripped",
        f"smartbox{smartbox_id}PortsConnected",
        f"smartbox{smartbox_id}PortsPowerSensed",
        "smartbox24PortsConnected",
        timeout=15.0,
        assert_no_error=False,
    )


@pytest.fixture(name="pasd_bus_name", scope="session")
def pasd_bus_name_fixture() -> str:
    """
    Return the name of the pasd_bus Tango device.

    :return: the name of the pasd_bus Tango device.
    """
    return "low-mccs/pasd_bus/001"


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    pasd_bus_name: str,
    pasd_bus_info: dict,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param pasd_bus_name: the name of the pasd_bus Tango device
    :param pasd_bus_info: information about the PaSD bus, such as its
        IP address (host and port) and an appropriate timeout to use.

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        pasd_bus_name,
        "ska_low_mccs_pasd.pasd_bus.MccsPasdBus",
        Host=pasd_bus_info["host"],
        Port=pasd_bus_info["port"],
        Timeout=pasd_bus_info["timeout"],
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    with context_manager as context:
        yield context


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the pasd_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: name of the pasd_bus Tango device.

    :yield: the pasd_bus Tango device under test.
    """
    yield tango_harness.get_device(pasd_bus_name)


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
        "smartbox24PortsConnected",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["smartbox24PortsConnected"],
    )
    change_event_callbacks.assert_change_event("smartbox24PortsConnected", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK

    change_event_callbacks.assert_against_call("smartbox24PortsConnected", lookahead=5)

    assert (
        pasd_bus_device.fndhModbusRegisterMapRevisionNumber
        == FndhSimulator.MODBUS_REGISTER_MAP_REVISION
    )
    assert pasd_bus_device.fndhPcbRevisionNumber == FndhSimulator.PCB_REVISION
    assert pasd_bus_device.fndhCpuId == FndhSimulator.CPU_ID
    assert pasd_bus_device.fndhChipId == FndhSimulator.CHIP_ID
    assert pasd_bus_device.fndhFirmwareVersion == FndhSimulator.DEFAULT_FIRMWARE_VERSION
    assert pasd_bus_device.fndhUptime == FndhSimulator.DEFAULT_UPTIME
    assert pasd_bus_device.fndhSysAddress == FndhSimulator.SYS_ADDRESS
    assert pasd_bus_device.fndhStatus == FndhSimulator.DEFAULT_STATUS
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
    assert list(pasd_bus_device.fndhPortsConnected) == fndh_simulator.ports_connected
    assert (
        list(pasd_bus_device.fndhPortBreakersTripped)
        == fndh_simulator.port_breakers_tripped
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
        == SmartboxSimulator.DEFAULT_UPTIME
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
        list(getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsConnected"))
        == smartbox_simulator.ports_connected
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


def test_turn_fndh_port_on_off(
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
        "fndhPortsConnected",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortsConnected"],
    )
    change_event_callbacks.assert_change_event("fndhPortsConnected", None)

    pasd_bus_device.subscribe_event(
        "fndhPortsPowerSensed",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortsPowerSensed"],
    )
    change_event_callbacks.assert_change_event("fndhPortsPowerSensed", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    change_event_callbacks.assert_change_event(
        "fndhPortsConnected", fndh_simulator.ports_connected
    )
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_simulator.ports_power_sensed
    )

    fndh_ports_connected = list(pasd_bus_device.fndhPortsConnected)
    connected_fndh_port = fndh_ports_connected.index(True) + 1

    fndh_ports_power_sensed = list(pasd_bus_device.fndhPortsPowerSensed)
    is_on = fndh_ports_power_sensed[connected_fndh_port - 1]

    if is_on:
        pasd_bus_device.TurnFndhPortOff(connected_fndh_port)
        fndh_ports_power_sensed[connected_fndh_port - 1] = False
        change_event_callbacks.assert_change_event(
            "fndhPortsPowerSensed", fndh_ports_power_sensed
        )

    json_argument = json.dumps(
        {"port_number": connected_fndh_port, "stay_on_when_offline": True}
    )
    pasd_bus_device.TurnFndhPortOn(json_argument)
    fndh_ports_power_sensed[connected_fndh_port - 1] = True
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_ports_power_sensed
    )

    pasd_bus_device.TurnFndhPortOff(connected_fndh_port)
    fndh_ports_power_sensed[connected_fndh_port - 1] = False
    change_event_callbacks.assert_change_event(
        "fndhPortsPowerSensed", fndh_ports_power_sensed
    )


def test_reset_fndh_port_breaker(
    pasd_bus_device: tango.DeviceProxy,
    fndh_simulator: FndhSimulator,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device can be used to reset an FNDH port's breaker.

    :param pasd_bus_device: a proxy to the PaSD bus device under test.
    :param fndh_simulator: the FNDH simulator under test
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    fndh_ports_connected = fndh_simulator.ports_connected
    connected_fndh_port = fndh_ports_connected.index(True) + 1

    fndh_simulator.simulate_port_breaker_trip(connected_fndh_port)
    fndh_port_breakers_tripped = fndh_simulator.port_breakers_tripped
    assert fndh_port_breakers_tripped[connected_fndh_port - 1]
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
        "fndhPortsConnected",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortsConnected"],
    )
    change_event_callbacks.assert_change_event("fndhPortsConnected", None)

    pasd_bus_device.subscribe_event(
        "fndhPortBreakersTripped",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["fndhPortBreakersTripped"],
    )
    change_event_callbacks.assert_change_event("fndhPortBreakersTripped", None)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    change_event_callbacks.assert_change_event(
        "fndhPortsConnected", fndh_ports_connected
    )
    change_event_callbacks.assert_change_event(
        "fndhPortBreakersTripped", fndh_port_breakers_tripped
    )

    pasd_bus_device.ResetFndhPortBreaker(connected_fndh_port)
    fndh_port_breakers_tripped[connected_fndh_port - 1] = False
    change_event_callbacks.assert_change_event(
        "fndhPortBreakersTripped", fndh_port_breakers_tripped
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


def test_turning_smartbox_port_on_off(
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
        f"smartbox{smartbox_id}PortsConnected",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}PortsConnected"],
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsConnected", None
    )

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

    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsConnected",
        smartbox_simulator.ports_connected,
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsPowerSensed",
        smartbox_simulator.ports_power_sensed,
    )

    smartbox_ports_connected = list(
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsConnected")
    )
    connected_smartbox_port = smartbox_ports_connected.index(True) + 1

    smartbox_ports_power_sensed = list(
        getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed")
    )
    is_on = smartbox_ports_power_sensed[connected_smartbox_port - 1]

    if is_on:
        json_argument = json.dumps(
            {
                "smartbox_number": smartbox_id,
                "port_number": connected_smartbox_port,
            }
        )
        pasd_bus_device.TurnSmartboxPortOff(json_argument)
        smartbox_ports_power_sensed[connected_smartbox_port - 1] = False
        change_event_callbacks.assert_change_event(
            f"smartbox{smartbox_id}PortsPowerSensed",
            smartbox_ports_power_sensed,
        )

    json_argument = json.dumps(
        {
            "smartbox_number": smartbox_id,
            "port_number": connected_smartbox_port,
            "stay_on_when_offline": True,
        }
    )
    pasd_bus_device.TurnSmartboxPortOn(json_argument)
    smartbox_ports_power_sensed[connected_smartbox_port - 1] = True
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsPowerSensed", smartbox_ports_power_sensed
    )

    json_argument = json.dumps(
        {
            "smartbox_number": smartbox_id,
            "port_number": connected_smartbox_port,
        }
    )
    pasd_bus_device.TurnSmartboxPortOff(json_argument)
    smartbox_ports_power_sensed[connected_smartbox_port - 1] = False
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsPowerSensed", smartbox_ports_power_sensed
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

    smartbox_simulator.simulate_port_breaker_trip(connected_smartbox_port)
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
        f"smartbox{smartbox_id}PortsConnected",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks[f"smartbox{smartbox_id}PortsConnected"],
    )
    change_event_callbacks.assert_change_event(
        f"smartbox{smartbox_id}PortsConnected", None
    )

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
        f"smartbox{smartbox_id}PortsConnected", smartbox_ports_connected
    )
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
