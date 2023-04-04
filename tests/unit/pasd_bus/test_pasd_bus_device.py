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
import unittest.mock
from typing import Any, Generator

import pytest
import tango
from ska_control_model import HealthState, LoggingLevel, ResultCode
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsPasdBus

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


@pytest.fixture(name="mock_component_manager")
def mock_component_manager_fixture() -> unittest.mock.Mock:
    """
    Return a mock to be used as a component manager for the PaSD bus device.

    :return: a mock to be used as a component manager for the
        pasd bus device.
    """
    return unittest.mock.Mock()


@pytest.fixture(name="patched_pasd_bus_device_class")
def patched_pasd_bus_device_class_fixture(
    mock_component_manager: unittest.mock.Mock,
) -> type[MccsPasdBus]:
    """
    Return a PaSD bus device that is patched with a mock component manager.

    :param mock_component_manager: the mock component manager with
        which to patch the device

    :return: a PaSD bus device that is patched with a mock component
        manager.
    """

    class PatchedMccsPasdBus(MccsPasdBus):
        """A PaSD bus device patched with a mock component manager."""

        def create_component_manager(
            self: PatchedMccsPasdBus,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager instead of the usual one.

            :return: a mock component manager
            """
            mock_component_manager._component_state_changed_callback = (
                self._component_state_changed_callback
            )

            return mock_component_manager

    return PatchedMccsPasdBus


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    pasd_bus_name: str,
    patched_pasd_bus_device_class: type[MccsPasdBus],
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param pasd_bus_name: the name of the pasd_bus Tango device
    :param patched_pasd_bus_device_class: a subclass of MccsPasdBus that
        has been patched with extra commands that mock system under
        control behaviours.

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        pasd_bus_name,
        patched_pasd_bus_device_class,
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


def test_healthState(
    pasd_bus_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test for healthState.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: a mock component manager that has
        been patched into the device under test
    :param change_event_callbacks: group of Tango change event
        callback with asynchrony support
    """
    pasd_bus_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )

    change_event_callbacks.assert_change_event("healthState", HealthState.UNKNOWN)
    assert pasd_bus_device.healthState == HealthState.UNKNOWN

    mock_component_manager._component_state_changed_callback(health=HealthState.OK)
    change_event_callbacks.assert_change_event("healthState", HealthState.OK)
    assert pasd_bus_device.healthState == HealthState.OK


@pytest.mark.parametrize(
    ("device_attribute", "component_manager_property", "example_value"),
    [
        ("antennasOnline", "antennas_online", [True, False]),
        ("antennasForced", "antenna_forcings", [False, False]),
        ("antennasTripped", "antennas_tripped", [False, True]),
        ("antennasPowerSensed", "antennas_power_sensed", [True, True]),
        (
            "antennasDesiredPowerOnline",
            "antennas_desired_on_online",
            [True, True],
        ),
        (
            "antennasDesiredPowerOffline",
            "antennas_desired_on_offline",
            [True, True],
        ),
        ("antennaCurrents", "antenna_currents", [0.0, 0.0]),
        ("smartboxInputVoltages", "smartbox_input_voltages", [0.0, 0.0]),
        (
            "smartboxPowerSupplyOutputVoltages",
            "smartbox_power_supply_output_voltages",
            [0.0, 0.0],
        ),
        ("smartboxStatuses", "smartbox_statuses", ["OK", "OK"]),
        (
            "smartboxPowerSupplyTemperatures",
            "smartbox_power_supply_temperatures",
            [40.0, 40.1],
        ),
        (
            "smartboxOutsideTemperatures",
            "smartbox_outside_temperatures",
            [40.0, 40.1],
        ),
        (
            "smartboxPcbTemperatures",
            "smartbox_pcb_temperatures",
            [40.0, 40.1],
        ),
        (
            "smartboxServiceLedsOn",
            "smartbox_service_leds_on",
            [False, True],
        ),
        ("smartboxFndhPorts", "smartbox_fndh_ports", [12, 4, 1]),
        (
            "smartboxDesiredPowerOnline",
            "smartbox_desired_power_online",
            [True, True],
        ),
        (
            "smartboxDesiredPowerOffline",
            "smartbox_desired_power_offline",
            [True, True],
        ),
        ("fndhPsu48vVoltages", "fndh_psu48v_voltages", [48.0, 48.0]),
        ("fndhPsu5vVoltage", "fndh_psu5v_voltage", 5.0),
        ("fndhPsu48vCurrent", "fndh_psu48v_current", 20.0),
        ("fndhPsu48vTemperature", "fndh_psu48v_temperature", 39.0),
        ("fndhPsu5vTemperature", "fndh_psu5v_temperature", 38.0),
        ("fndhPcbTemperature", "fndh_pcb_temperature", 37.0),
        ("fndhOutsideTemperature", "fndh_pcb_temperature", 36.0),
        ("fndhStatus", "fndh_status", "OK"),
        (
            "fndhPortsConnected",
            "fndh_ports_connected",
            [False, True],
        ),
        (
            "fndhPortsForced",
            "fndh_port_forcings",
            [False, True],
        ),
        (
            "fndhPortsDesiredPowerOnline",
            "fndh_ports_desired_power_online",
            [False, True],
        ),
        (
            "fndhPortsDesiredPowerOffline",
            "fndh_ports_desired_power_offline",
            [False, True],
        ),
    ],
)
def test_readonly_attribute(
    pasd_bus_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_attribute: str,
    component_manager_property: str,
    example_value: Any,
) -> None:
    """
    Test that device attributes reads result in component manager property reads.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched pasd bus device.
    :param device_attribute: name of the device attribute under test.
    :param component_manager_property: name of the component manager
        property that is expected to be called when the device
        attribute is called.
    :param example_value: any value of the correct type for the
        device attribute.
    """
    property_mock = unittest.mock.PropertyMock(return_value=example_value)
    setattr(
        type(mock_component_manager),
        component_manager_property,
        property_mock,
    )
    property_mock.assert_not_called()

    _ = getattr(pasd_bus_device, device_attribute)
    property_mock.assert_called_once_with()


@pytest.mark.parametrize(
    (
        "device_command",
        "component_manager_method",
        "device_command_argin",
        "component_manager_method_return",
    ),
    [
        (
            "ReloadDatabase",
            "reload_database",
            None,
            [True, True],
        ),
        (
            "GetFndhInfo",
            "get_fndh_info",
            1,
            [True, True],
        ),
        (
            "TurnFndhServiceLedOn",
            "turn_fndh_service_led_on",
            1,
            [True, True],
        ),
        (
            "TurnFndhServiceLedOff",
            "turn_fndh_service_led_off",
            1,
            [True, True],
        ),
        (
            "GetSmartboxInfo",
            "get_smartbox_info",
            1,
            [True, True],
        ),
        (
            "TurnSmartboxOn",
            "turn_smartbox_on",
            1,
            [True, True],
        ),
        (
            "TurnSmartboxOff",
            "turn_smartbox_off",
            1,
            [True, True],
        ),
        (
            "TurnSmartboxServiceLedOn",
            "turn_smartbox_service_led_on",
            1,
            [True, True],
        ),
        (
            "TurnSmartboxServiceLedOff",
            "turn_smartbox_service_led_off",
            1,
            [True, True],
        ),
        (
            "GetAntennaInfo",
            "get_antenna_info",
            1,
            [True, True],
        ),
        (
            "ResetAntennaBreaker",
            "reset_antenna_breaker",
            1,
            [True, True],
        ),
        (
            "TurnAntennaOn",
            "turn_antenna_on",
            1,
            [True, True],
        ),
        (
            "TurnAntennaOff",
            "turn_antenna_off",
            1,
            [True, True],
        ),
    ],
)
def test_command(  # pylint: disable=too-many-arguments
    pasd_bus_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
) -> None:
    """
    Test that device attribute writes result in component manager property writes.

    :param pasd_bus_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched pasd bus device.
    :param device_command: name of the device command under test.
    :param component_manager_method: name of the component manager
        method that is expected to be called when the device
        command is called.
    :param device_command_argin: argument to the device command
    :param component_manager_method_return: return value of the
        component manager method
    """
    method_mock = unittest.mock.Mock(return_value=component_manager_method_return)
    setattr(mock_component_manager, component_manager_method, method_mock)
    method_mock.assert_not_called()

    command = getattr(pasd_bus_device, device_command)
    if device_command_argin is None:
        command_return = command()
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command
