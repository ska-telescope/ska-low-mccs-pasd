# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple tests of the MCCS PaSD bus Tango device."""
from __future__ import annotations

import gc
import json
from typing import Literal

import tango
from pytest_bdd import given, parsers, scenario, then, when
from ska_control_model import AdminMode, HealthState
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

gc.disable()


@scenario(
    "features/monitor_and_control.feature",
    "Monitor PaSD",
)
def test_monitoring() -> None:
    """
    Test basic monitoring of a PaSD.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@scenario(
    "features/monitor_and_control.feature",
    "Turn on FNDH port",
)
def test_turning_on_fndh_port() -> None:
    """
    Test turning on an FNDH port.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@scenario(
    "features/monitor_and_control.feature",
    "Turn off FNDH port",
)
def test_turning_off_fndh_port() -> None:
    """
    Test turning off an FNDH port.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@scenario(
    "features/monitor_and_control.feature",
    "Turn on smartbox port",
)
def test_turning_on_smartbox_port() -> None:
    """
    Test turning on an smartbox port.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@scenario(
    "features/monitor_and_control.feature",
    "Turn off smartbox port",
)
def test_turning_off_smartbox_port() -> None:
    """
    Test turning off an smartbox port.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given("the PaSD is available")
def pasd_is_available() -> None:
    """Make sure the PaSD is available."""
    # TODO: We need a way of confirm that the PaSD is there,
    # independently of MCCS.


@given("a smartbox", target_fixture="smartbox_id")
def smartbox_id_fixture() -> int:
    """
    Return the number of the smartbox under test.

    :return: the number of the smartbox under test.
    """
    return 1


@given("MCCS-for-PaSD is in DISABLE state")
def check_mccs_is_disabled(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that MCCS-for-PaSD is in DISABLE state.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    if pasd_bus_device.state() != tango.DevState.DISABLE:
        pasd_bus_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event(
            "state",
            tango.DevState.DISABLE,
        )
    assert pasd_bus_device.state() == tango.DevState.DISABLE


@given("MCCS-for-PaSD is in ON state")
def check_mccs_is_on(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that MCCS-for-PaSD is in ON state.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    if pasd_bus_device.state() == tango.DevState.DISABLE:
        put_pasd_bus_device_online(pasd_bus_device)
        check_state_becomes_on(change_event_callbacks)
    assert pasd_bus_device.state() == tango.DevState.ON


@given("MCCS-for-PaSD has UNKNOWN health")
def check_mccs_has_unknown_health(
    pasd_bus_device: tango.DeviceProxy,
) -> None:
    """
    Check that MCCS-for-PaSD has UNKNOWN health state.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    """
    assert pasd_bus_device.healthState == HealthState.UNKNOWN


@when("MCCS-for-PaSD adminMode is set to ONLINE")
def put_pasd_bus_device_online(
    pasd_bus_device: tango.DeviceProxy,
) -> None:
    """
    Put the PaSD bus device online.

    :param pasd_bus_device: the PaSD bus Tango device under test
    """
    print("Putting PaSD bus device ONLINE...")
    pasd_bus_device.adminMode = AdminMode.ONLINE


@then("MCCS-for-PaSD reports ON state")
def check_state_becomes_on(
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the state of the PaSD bus device progresses from UNKNOWN.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    print("PaSD bus device is in UNKNOWN state.")

    change_event_callbacks.assert_change_event(
        "state",
        tango.DevState.ON,
    )
    print("PaSD bus device is in ON state.")


@then(parsers.parse("MCCS-for-PaSD reports its {monitoring_point}"))
def check_monitoring_point_is_reported(
    change_event_callbacks: MockTangoEventCallbackGroup,
    smartbox_id: int,
    monitoring_point: str,
) -> None:
    """
    Check that an event is received corresponding to the monitoring point of interest.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param smartbox_id: number of the smartbox under test.
    :param monitoring_point: reference to a monitoring point.
    """
    attribute_name_map = {
        "FNDH uptime": "fndhUptime",
        "FNDH status": "fndhStatus",
        "FNDH LED pattern": "fndhLedPattern",
        "FNDH 48v PSU voltages": "fndhPsu48vVoltages",
        "FNDH 48v PSU current": "fndhPsu48vCurrent",
        "FNDH 48v PSU temperature": "fndhPsu48vTemperature",
        "FNDH 5v PSU voltage": "fndhPsu5vVoltage",
        "FNDH 5v PSU temperature": "fndhPsu5vTemperature",
        "FNDH PCB temperature": "fndhPcbTemperature",
        "FNDH outside temperature": "fndhOutsideTemperature",
        "smartbox uptime": f"smartbox{smartbox_id}Uptime",
        "smartbox status": f"smartbox{smartbox_id}Status",
        "smartbox LED pattern": f"smartbox{smartbox_id}LedPattern",
        "smartbox input voltage": f"smartbox{smartbox_id}InputVoltage",
        "smartbox power supply output voltage": (
            f"smartbox{smartbox_id}PowerSupplyOutputVoltage"
        ),
        "smartbox power supply temperature": (
            f"smartbox{smartbox_id}PowerSupplyTemperature"
        ),
        "smartbox PCB temperature": f"smartbox{smartbox_id}PcbTemperature",
        "smartbox outside temperature": f"smartbox{smartbox_id}OutsideTemperature",
    }
    attribute_name = attribute_name_map[monitoring_point]
    change_event_callbacks[attribute_name].assert_change_event(Anything)


@then("MCCS-for-PaSD health becomes OK")
def check_health_becomes_okay(
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the health of the PaSD bus device becomes OK.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)


@given("a connected FNDH port", target_fixture="connected_fndh_port")
def find_connected_fndh_port(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> int:
    """
    Find and return a connected FNDH port.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.

    :return: the port number of the FNDH port that was checked.
        This will be a port that has a smartbox connected, so that the
        port can be turned on and power will be sensed.
    """
    try:
        fndh_connected_ports = list(pasd_bus_device.fndhPortsConnected)
    except tango.DevFailed:
        change_event_callbacks["fndhPortsConnected"].assert_change_event(Anything)
        fndh_connected_ports = list(pasd_bus_device.fndhPortsConnected)

    connected_fndh_port = fndh_connected_ports.index(True) + 1
    return connected_fndh_port


@given("the FNDH port is off")
def check_fndh_port_is_off(
    pasd_bus_device: tango.DeviceProxy,
    connected_fndh_port: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the FNDH port is off.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param connected_fndh_port: an FNDH port with a smartbox connected,
        so that it is possible to turn the port on and sense power
        delivery.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    change_event_callbacks["fndhPortsPowerSensed"].assert_change_event(Anything)
    try:
        fndh_ports_power_sensed = pasd_bus_device.fndhPortsPowerSensed
    except tango.DevFailed:
        change_event_callbacks["fndhPortsPowerSensed"].assert_change_event(Anything)
        fndh_ports_power_sensed = pasd_bus_device.fndhPortsPowerSensed
    assert not fndh_ports_power_sensed[connected_fndh_port - 1]


@given("the FNDH port is on")
def check_fndh_port_is_on(
    pasd_bus_device: tango.DeviceProxy,
    connected_fndh_port: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the FNDH port is on.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param connected_fndh_port: an FNDH port with a smartbox connected,
        so that it is possible to turn the port on and sense power
        delivery.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    fndh_ports_power_sensed = pasd_bus_device.fndhPortsPowerSensed
    is_on = fndh_ports_power_sensed[connected_fndh_port - 1]
    if not is_on:
        turn_fndh_port_on(pasd_bus_device, connected_fndh_port)
        check_fndh_port_changes_power_state(
            pasd_bus_device,
            connected_fndh_port,
            change_event_callbacks,
            "on",
        )
        fndh_ports_power_sensed = pasd_bus_device.fndhPortsPowerSensed
        is_on = fndh_ports_power_sensed[connected_fndh_port - 1]
    assert is_on


@when("I tell MCCS-for-PaSD to turn the FNDH port on")
def turn_fndh_port_on(
    pasd_bus_device: tango.DeviceProxy,
    connected_fndh_port: int,
) -> None:
    """
    Turn the FNDH port on.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param connected_fndh_port: an FNDH port with a smartbox connected,
        so that it is possible to turn the port on and sense power
        delivery.
    """
    json_argument = json.dumps(
        {"port_number": connected_fndh_port, "stay_on_when_offline": True}
    )
    pasd_bus_device.TurnFndhPortOn(json_argument)


@when("I tell MCCS-for-PaSD to turn the FNDH port off")
def turn_fndh_port_off(
    pasd_bus_device: tango.DeviceProxy,
    connected_fndh_port: int,
) -> None:
    """
    Turn the FNDH port off.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param connected_fndh_port: an FNDH port with a smartbox connected,
        so that it is possible to turn the port on and sense power
        delivery.
    """
    pasd_bus_device.TurnFndhPortOff(connected_fndh_port)


@then(parsers.parse("the FNDH port turns {state_name}"))
def check_fndh_port_changes_power_state(
    pasd_bus_device: tango.DeviceProxy,
    connected_fndh_port: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
    state_name: Literal["off", "on"],
) -> None:
    """
    Check that the FNDH port changes power state.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param connected_fndh_port: an FNDH port with a smartbox connected,
        so that it is possible to turn the port on and sense power
        delivery.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param state_name: name of the expected power state: "on" or "off".
    """
    state_map = {"on": True, "off": False}

    change_event_callbacks["fndhPortsPowerSensed"].assert_change_event(Anything)
    powered = pasd_bus_device.fndhPortsPowerSensed

    if powered[connected_fndh_port - 1] != state_map[state_name]:
        change_event_callbacks["fndhPortsPowerSensed"].assert_change_event(Anything)
        powered = pasd_bus_device.fndhPortsPowerSensed
    assert powered[connected_fndh_port - 1] == state_map[state_name]


@given("a connected smartbox port", target_fixture="connected_smartbox_port")
def find_connected_smartbox_port(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> int:
    """
    Find and return a connected smartbox port.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param smartbox_id: number of the smartbox under test.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.

    :return: the port number of the smartbox port that was checked.
        This will be a port that has an antenna connected, so that the
        port can be turned on and power will be sensed.
    """
    try:
        smartbox_connected_ports = list(
            getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsConnected")
        )
    except tango.DevFailed:
        change_event_callbacks[
            f"smartbox{smartbox_id}PortsConnected"
        ].assert_change_event(Anything)
        smartbox_connected_ports = list(
            getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsConnected")
        )

    connected_smartbox_port = smartbox_connected_ports.index(True) + 1
    return connected_smartbox_port


@given("the smartbox port is off")
def check_smartbox_port_is_off(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    connected_smartbox_port: int,
    smartbox_id: int,
) -> None:
    """
    Check that the smartbox port is off.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param connected_smartbox_port: an smartbox port with an antenna
        connected, so that it is possible to turn the port on and sense
        power delivery.
    :param smartbox_id: number of the smartbox under test.
    """
    change_event_callbacks[
        f"smartbox{smartbox_id}PortsPowerSensed"
    ].assert_change_event(Anything)

    smartbox_ports_power_sensed = getattr(
        pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed"
    )
    assert not smartbox_ports_power_sensed[connected_smartbox_port - 1]


@given("the smartbox port is on")
def check_smartbox_port_is_on(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    connected_smartbox_port: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Check that the smartbox port is on.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param smartbox_id: number of the smartbox under test.
    :param connected_smartbox_port: a smartbox port with an antenna
        connected, so that it is possible to turn the port on and sense
        power delivery.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    smartbox_ports_power_sensed = getattr(
        pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed"
    )
    is_on = smartbox_ports_power_sensed[connected_smartbox_port - 1]
    if not is_on:
        turn_smartbox_port_on(pasd_bus_device, smartbox_id, connected_smartbox_port)
        check_smartbox_port_changes_power_state(
            pasd_bus_device,
            smartbox_id,
            connected_smartbox_port,
            change_event_callbacks,
            "on",
        )
        smartbox_ports_power_sensed = getattr(
            pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed"
        )
        is_on = smartbox_ports_power_sensed[connected_smartbox_port - 1]
    assert is_on


@when("I tell MCCS-for-PaSD to turn the smartbox port on")
def turn_smartbox_port_on(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    connected_smartbox_port: int,
) -> None:
    """
    Turn on the smartbox port.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param smartbox_id: number of the smartbox under test.
    :param connected_smartbox_port: a smartbox port with an antenna
        connected, so that it is possible to turn the port on and sense
        power delivery.
    """
    json_argument = json.dumps(
        {
            "smartbox_number": smartbox_id,
            "port_number": connected_smartbox_port,
            "stay_on_when_offline": True,
        }
    )
    pasd_bus_device.TurnSmartboxPortOn(json_argument)


@when("I tell MCCS-for-PaSD to turn the smartbox port off")
def turn_smartbox_port_off(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    connected_smartbox_port: int,
) -> None:
    """
    Turn off the smartbox port.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param smartbox_id: number of the smartbox under test.
    :param connected_smartbox_port: a smartbox port with an antenna
        connected, so that it is possible to turn the port on and sense
        power delivery.
    """
    json_argument = json.dumps(
        {
            "smartbox_number": smartbox_id,
            "port_number": connected_smartbox_port,
        }
    )
    pasd_bus_device.TurnSmartboxPortOff(json_argument)


@then(parsers.parse("the smartbox port turns {state_name}"))
def check_smartbox_port_changes_power_state(
    pasd_bus_device: tango.DeviceProxy,
    smartbox_id: int,
    connected_smartbox_port: int,
    change_event_callbacks: MockTangoEventCallbackGroup,
    state_name: Literal["off", "on"],
) -> None:
    """
    Check that the specified smartbox port reports a new power state.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param smartbox_id: number of the smartbox under test.
    :param connected_smartbox_port: a smartbox port with an antenna
        connected, so that it is possible to turn the port on and sense
        power delivery.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param state_name: name of the expected power state: "on" or "off".
    """
    state_map = {"on": True, "off": False}

    change_event_callbacks[
        f"smartbox{smartbox_id}PortsPowerSensed"
    ].assert_change_event(Anything)
    powered = getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed")

    if powered[connected_smartbox_port - 1] != state_map[state_name]:
        change_event_callbacks[
            f"smartbox{smartbox_id}PortsPowerSensed"
        ].assert_change_event(Anything)
        powered = getattr(pasd_bus_device, f"smartbox{smartbox_id}PortsPowerSensed")

    assert powered[connected_smartbox_port - 1] == state_map[state_name]
