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
import unittest.mock
from typing import Generator

import pytest
import tango
from ska_control_model import AdminMode, HealthState, LoggingLevel, ResultCode
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import PasdBusSimulator

# TODO: Weird hang-at-garbage-collection bug
gc.disable()


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return MockTangoEventCallbackGroup(
        "adminMode",
        "healthState",
        "longRunningCommandResult",
        "longRunningCommandStatus",
        "state",
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


def test_communication(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device's communication with the PaSD bus.

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

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)


def test_healthState(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test for healthState.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
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

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK


@pytest.mark.parametrize(
    ("device_attribute", "simulator_attribute", "test_type"),
    [
        ("antennasOnline", "antennas_online", "array"),
        ("antennasTripped", "antennas_tripped", "array"),
        ("antennasPowerSensed", "antennas_power_sensed", "array"),
        ("antennasDesiredPowerOnline", "antennas_desired_power_online", "array"),
        ("antennasDesiredPowerOffline", "antennas_desired_power_offline", "array"),
        ("antennaCurrents", "antenna_currents", "array"),
        ("smartboxInputVoltages", "smartbox_input_voltages", "array"),
        (
            "smartboxPowerSupplyOutputVoltages",
            "smartbox_power_supply_output_voltages",
            "array",
        ),
        ("smartboxStatuses", "smartbox_statuses", "list"),
        (
            "smartboxPowerSupplyTemperatures",
            "smartbox_power_supply_temperatures",
            "array",
        ),
        ("smartboxOutsideTemperatures", "smartbox_outside_temperatures", "array"),
        ("smartboxPcbTemperatures", "smartbox_pcb_temperatures", "array"),
        ("smartboxServiceLedsOn", "smartbox_service_leds_on", "array"),
        ("smartboxFndhPorts", "smartbox_fndh_ports", "array"),
        ("smartboxesDesiredPowerOnline", "smartboxes_desired_power_online", "array"),
        ("smartboxesDesiredPowerOffline", "smartboxes_desired_power_offline", "array"),
        ("fndhPsu48vVoltages", "fndh_psu48v_voltages", "array"),
        ("fndhPsu5vVoltage", "fndh_psu5v_voltage", "scalar"),
        ("fndhPsu48vCurrent", "fndh_psu48v_current", "scalar"),
        ("fndhPsu48vTemperature", "fndh_psu48v_temperature", "scalar"),
        ("fndhPsu5vTemperature", "fndh_psu5v_temperature", "scalar"),
        ("fndhPcbTemperature", "fndh_pcb_temperature", "scalar"),
        ("fndhOutsideTemperature", "fndh_pcb_temperature", "scalar"),
        ("fndhStatus", "fndh_status", "scalar"),
        ("fndhPortsConnected", "fndh_ports_connected", "array"),
        ("fndhPortsDesiredPowerOnline", "fndh_ports_desired_power_online", "array"),
        ("fndhPortsDesiredPowerOffline", "fndh_ports_desired_power_offline", "array"),
    ],
)
def test_readonly_attribute(  # pylint: disable=too-many-arguments
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: PasdBusSimulator,
    change_event_callbacks: MockTangoEventCallbackGroup,
    device_attribute: str,
    simulator_attribute: str,
    test_type: str,
) -> None:
    """
    Test that device attributes reads result in simulator reads.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    :param device_attribute: name of the device attribute under test.
    :param simulator_attribute: name of the corresponding simulator
        attribute
    :param test_type: how to test for equality; options are "array",
        "list" or "scalar"
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = getattr(pasd_bus_device, device_attribute)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    # Yes, mocking properties in python really is this messy
    type(mock_pasd_bus_simulator).__dict__[
        simulator_attribute
    ].reset_mock()  # because start_communication() reads fndh_status ATM.

    value_as_read = getattr(pasd_bus_device, device_attribute)

    type(mock_pasd_bus_simulator).__dict__[
        simulator_attribute
    ].assert_called_once_with()

    simulator_value = getattr(mock_pasd_bus_simulator, simulator_attribute)

    if test_type == "array":
        assert (value_as_read == simulator_value).all()
    elif test_type == "list":
        assert list(value_as_read) == list(simulator_value)
    else:
        assert test_type == "scalar"
        assert value_as_read == simulator_value


def test_forcings(
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test reads of the antennasForced and fndhPortsForced attributes.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.antennasForced

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.fndhPortsForced

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    antennas_forced = pasd_bus_device.antennasForced

    # Yes, mocking properties in python really is this messy
    type(mock_pasd_bus_simulator).__dict__["antenna_forcings"].assert_called_once_with()

    antenna_forcings = mock_pasd_bus_simulator.antenna_forcings

    for forced, forcing in zip(antennas_forced, antenna_forcings):
        assert forced == (forcing is not None)

    fndh_ports_forced = pasd_bus_device.fndhPortsForced

    # Yes, mocking properties in python really is this messy
    type(mock_pasd_bus_simulator).__dict__[
        "fndh_port_forcings"
    ].assert_called_once_with()

    fndh_port_forcings = mock_pasd_bus_simulator.fndh_port_forcings

    for forced, forcing in zip(fndh_ports_forced, fndh_port_forcings):
        assert forced == (forcing is not None)


def test_ReloadDatabase_command(
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test that device command invokation result in actions on the simulator.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.ReloadDatabase()

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    command_return = pasd_bus_device.ReloadDatabase()
    assert command_return[0] == ResultCode.OK

    mock_pasd_bus_simulator.reload_database.assert_called_once_with()


def test_GetFndhInfo_command(
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the GetFndhInfo command.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.GetFndhInfo()

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    returned_fndh_info = json.loads(pasd_bus_device.GetFndhInfo())

    mock_pasd_bus_simulator.get_fndh_info.assert_called_once_with()

    simulator_fndh_info = mock_pasd_bus_simulator.get_fndh_info()

    assert returned_fndh_info == simulator_fndh_info


def test_fndh_service_led(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test setting and unsetting the FNDH service LED.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnFndhServiceLedOn()

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnFndhServiceLedOff()

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    assert not pasd_bus_device.fndhServiceLedOn

    [[result_code], [message]] = pasd_bus_device.TurnFndhServiceLedOn()
    assert result_code == ResultCode.OK
    assert message == "TurnFndhServiceLedOn succeeded"

    assert pasd_bus_device.fndhServiceLedOn

    [[result_code], [message]] = pasd_bus_device.TurnFndhServiceLedOn()
    assert result_code == ResultCode.OK
    assert message == "TurnFndhServiceLedOn succeeded: nothing to do"

    assert pasd_bus_device.fndhServiceLedOn

    [[result_code], [message]] = pasd_bus_device.TurnFndhServiceLedOff()
    assert result_code == ResultCode.OK
    assert message == "TurnFndhServiceLedOff succeeded"

    assert not pasd_bus_device.fndhServiceLedOn

    [[result_code], [message]] = pasd_bus_device.TurnFndhServiceLedOff()
    assert result_code == ResultCode.OK
    assert message == "TurnFndhServiceLedOff succeeded: nothing to do"

    assert not pasd_bus_device.fndhServiceLedOn


def test_GetSmartboxInfo_command(
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the GetSmartboxInfo command.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.GetSmartboxInfo(1)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    returned_smartbox_info = json.loads(pasd_bus_device.GetSmartboxInfo(1))

    mock_pasd_bus_simulator.get_smartbox_info.assert_called_once_with(1)

    simulator_smartbox_info = mock_pasd_bus_simulator.get_smartbox_info(1)

    assert returned_smartbox_info == simulator_smartbox_info


def test_smartbox_service_led(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test setting and unsetting a smartbox service LED.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnSmartboxServiceLedOn(1)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnSmartboxServiceLedOff(1)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    assert not pasd_bus_device.smartboxServiceLedsOn[0]
    assert not pasd_bus_device.smartboxServiceLedsOn[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxServiceLedOn(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxServiceLedOn 1 succeeded"

    assert pasd_bus_device.smartboxServiceLedsOn[0]
    assert not pasd_bus_device.smartboxServiceLedsOn[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxServiceLedOn(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxServiceLedOn 1 succeeded: nothing to do"

    assert pasd_bus_device.smartboxServiceLedsOn[0]
    assert not pasd_bus_device.smartboxServiceLedsOn[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxServiceLedOn(2)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxServiceLedOn 2 succeeded"

    assert pasd_bus_device.smartboxServiceLedsOn[0]
    assert pasd_bus_device.smartboxServiceLedsOn[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxServiceLedOff(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxServiceLedOff 1 succeeded"

    assert not pasd_bus_device.smartboxServiceLedsOn[0]
    assert pasd_bus_device.smartboxServiceLedsOn[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxServiceLedOff(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxServiceLedOff 1 succeeded: nothing to do"

    assert not pasd_bus_device.smartboxServiceLedsOn[0]
    assert pasd_bus_device.smartboxServiceLedsOn[1]


def test_turn_smartbox_on_off(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test turning a smartbox off and on.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnSmartboxOn(1)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnSmartboxOff(1)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    assert not pasd_bus_device.smartboxesDesiredPowerOnline[0]
    assert not pasd_bus_device.smartboxesDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxOn(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxOn 1 succeeded"

    assert pasd_bus_device.smartboxesDesiredPowerOnline[0]
    assert not pasd_bus_device.smartboxesDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxOn(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxOn 1 succeeded: nothing to do"

    assert pasd_bus_device.smartboxesDesiredPowerOnline[0]
    assert not pasd_bus_device.smartboxesDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxOn(2)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxOn 2 succeeded"

    assert pasd_bus_device.smartboxesDesiredPowerOnline[0]
    assert pasd_bus_device.smartboxesDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxOff(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxOff 1 succeeded"

    assert not pasd_bus_device.smartboxesDesiredPowerOnline[0]
    assert pasd_bus_device.smartboxesDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnSmartboxOff(1)
    assert result_code == ResultCode.OK
    assert message == "TurnSmartboxOff 1 succeeded: nothing to do"

    assert not pasd_bus_device.smartboxesDesiredPowerOnline[0]
    assert pasd_bus_device.smartboxesDesiredPowerOnline[1]


def test_GetAntennaInfo_command(
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the GetAntennaInfo command.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.GetAntennaInfo(1)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    returned_antenna_info = json.loads(pasd_bus_device.GetAntennaInfo(1))

    mock_pasd_bus_simulator.get_antenna_info.assert_called_once_with(1)

    simulator_antenna_info = mock_pasd_bus_simulator.get_antenna_info(1)

    assert returned_antenna_info == simulator_antenna_info


def test_turn_antenna_on_off(
    pasd_bus_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test turning an antenna off and on.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnAntennaOn(1)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.TurnAntennaOff(1)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    assert not pasd_bus_device.antennasDesiredPowerOnline[0]
    assert not pasd_bus_device.antennasDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnAntennaOn(1)
    assert result_code == ResultCode.OK
    assert message == "TurnAntennaOn 1 succeeded"

    assert pasd_bus_device.antennasDesiredPowerOnline[0]
    assert not pasd_bus_device.antennasDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnAntennaOn(1)
    assert result_code == ResultCode.OK
    assert message == "TurnAntennaOn 1 succeeded: nothing to do"

    assert pasd_bus_device.antennasDesiredPowerOnline[0]
    assert not pasd_bus_device.antennasDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnAntennaOn(2)
    assert result_code == ResultCode.OK
    assert message == "TurnAntennaOn 2 succeeded"

    assert pasd_bus_device.antennasDesiredPowerOnline[0]
    assert pasd_bus_device.antennasDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnAntennaOff(1)
    assert result_code == ResultCode.OK
    assert message == "TurnAntennaOff 1 succeeded"

    assert not pasd_bus_device.antennasDesiredPowerOnline[0]
    assert pasd_bus_device.antennasDesiredPowerOnline[1]

    [[result_code], [message]] = pasd_bus_device.TurnAntennaOff(1)
    assert result_code == ResultCode.OK
    assert message == "TurnAntennaOff 1 succeeded: nothing to do"

    assert not pasd_bus_device.antennasDesiredPowerOnline[0]
    assert pasd_bus_device.antennasDesiredPowerOnline[1]


def test_ResetAntennaBreaker_command(
    pasd_bus_device: tango.DeviceProxy,
    mock_pasd_bus_simulator: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test that device command invokation result in actions on the simulator.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_pasd_bus_simulator: the PaSD bus simulator
        that is acted upon by the component manager under test,
        wrapped by a mock so that we can assert calls
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    pasd_bus_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    with pytest.raises(tango.DevFailed, match="Communication is not being attempted"):
        _ = pasd_bus_device.ResetAntennaBreaker(1)

    pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)

    [[result_code], [message]] = pasd_bus_device.ResetAntennaBreaker(1)
    assert result_code == ResultCode.OK
    assert message == "ResetAntennaBreaker 1 succeeded: nothing to do"

    mock_pasd_bus_simulator.reset_antenna_breaker.assert_called_once_with(1)

    mock_pasd_bus_simulator.simulate_antenna_breaker_trip(1)

    [[result_code], [message]] = pasd_bus_device.ResetAntennaBreaker(1)
    assert result_code == ResultCode.OK
    assert message == "ResetAntennaBreaker 1 succeeded"

    [[result_code], [message]] = pasd_bus_device.ResetAntennaBreaker(1)
    assert result_code == ResultCode.OK
    assert message == "ResetAntennaBreaker 1 succeeded: nothing to do"
