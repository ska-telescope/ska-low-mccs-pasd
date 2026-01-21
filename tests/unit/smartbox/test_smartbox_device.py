# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsSmartBox."""

from __future__ import annotations

import gc
import json
import unittest.mock
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
import tango
from ska_control_model import AdminMode, HealthState, LoggingLevel, ResultCode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsSmartBox
from tests.harness import PasdTangoTestHarness

# TODO: Weird hang-at-garbage-collection bug
gc.disable()


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    smartbox_number: int, mock_pasdbus: unittest.mock.Mock, station_label: str
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the smartbox Tango device under test.

    :param smartbox_number: number of the smartbox under test
    :param mock_pasdbus: A mock PaSD bus device.
    :param station_label: The label of the station under test.

    :yield: a proxy to the smartbox Tango device under test.
    """

    class _PatchedMccsSmartbox(MccsSmartBox):
        """A daq class with a method to call the component state callback."""

        @tango.server.command
        def CallAttributeCallback(self, argin: str) -> None:
            """
            Patched method to call attribute callback directly.

            :param argin: json-ified dict to call attribute callback with.
            """
            self._attribute_changed_callback(
                **json.loads(argin), attr_quality=tango.AttrQuality.ATTR_VALID
            )

    with patch("ska_low_mccs_pasd.pasd_utils.Database") as db:
        # pylint: disable=too-many-return-statements
        def my_func(device_name: str, property_name: str) -> list:
            match property_name:
                case "inputvoltagethresholds":
                    return [50.0, 49.0, 45.0, 40.0]
                case "powersupplyoutputvoltagethresholds":
                    return [5.0, 4.9, 4.4, 4.0]
                case "powersupplytemperaturethresholds":
                    return [85.0, 70.0, 0.0, -5.0]
                case "pcbtemperaturethresholds":
                    return [85.0, 70.0, 0.0, -5.0]
                case "femambienttemperaturethresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femcasetemperature1thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femcasetemperature2thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femheatsinktemperature1thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femheatsinktemperature2thresholds":
                    return [60.0, 45.0, 0.0, -5.0]
                case "femcurrenttripthresholds":
                    return [496, 496, 496, 496, 496, 496, 496, 496, 496, 496, 496, 496]
            return []

        db.return_value.get_device_attribute_property = my_func
        harness = PasdTangoTestHarness(station_label=station_label)
        harness.set_mock_pasd_bus_device(mock_pasdbus)
        harness.add_smartbox_device(
            smartbox_number,
            logging_level=int(LoggingLevel.DEBUG),
            device_class=_PatchedMccsSmartbox,
        )

        with harness as context:
            yield context.get_smartbox_device(smartbox_number)


def test_device_transitions_to_power_state_of_fndh_port(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    mocked_initial_port_power_state: bool,
) -> None:
    """
    Test the smartbox transitions to the correct power upon startup.

    the FNDH port that this smartbox is attached to has a mocked value.
    Check that the smartbox gets the same value when it start communicating.

    :param smartbox_device: the smartbox device under test
    :param change_event_callbacks: a collection of change event callbacks.
    :param mocked_initial_port_power_state: the initial power state of the FNDH
        this smartbox is attached to.
    """
    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    # When the smartbox starts communicating it will start enter a unknown state until
    # Its communication with the FNDH has been established. Once this occurs the device
    # Subscribes to the power state of the port it is attached to. In this test the
    # Mock FNDH has been mocked to have the power OFF.
    smartbox_device.adminMode = AdminMode.ONLINE
    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)

    state = {True: tango.DevState.ON, False: tango.DevState.OFF}
    change_event_callbacks.assert_change_event(
        "state", state[mocked_initial_port_power_state]
    )


@pytest.mark.parametrize(
    (
        "device_command",
        "device_command_argin",
    ),
    [
        (
            "PowerOnPort",
            4,
        ),
        (
            "PowerOffPort",
            4,
        ),
        (
            "SetPortPowers",
            json.dumps(
                {
                    "smartbox_number": 2,
                    "port_powers": [False for _ in range(12)],
                    "stay_on_when_offline": True,
                }
            ),
        ),
    ],
)
def test_command_queued(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    mocked_initial_port_power_state: bool,
    device_command: str,
    device_command_argin: Any,
) -> None:
    """
    Test commands return the correct result code.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param smartbox_device: the smartbox device under test
    :param change_event_callbacks: a collection of change event callbacks.
    :param mocked_initial_port_power_state: the initial power state of the FNDH
        this smartbox is attached to.
    :param device_command: name of the device command under test.
    :param device_command_argin: argument to the device command
    """
    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    smartbox_device.adminMode = AdminMode.ONLINE
    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)

    state = {True: tango.DevState.ON, False: tango.DevState.OFF}
    change_event_callbacks.assert_change_event(
        "state", state[mocked_initial_port_power_state]
    )

    command = getattr(smartbox_device, device_command)
    if device_command_argin is None:
        command_return = command([])
    else:
        command_return = command(device_command_argin)

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command


@pytest.mark.parametrize(
    (
        "attribute",
        "max_alarm",
        "max_warning",
        "min_warning",
        "min_alarm",
    ),
    [
        (
            "InputVoltage",
            49.5,
            48.5,
            45.5,
            41,
        ),
        (
            "PowerSupplyOutputVoltage",
            4.95,
            4.8,
            4.5,
            4.1,
        ),
        (
            "PowerSupplyTemperature",
            80,
            65,
            5,
            -2,
        ),
        (
            "PcbTemperature",
            80,
            65,
            5,
            -2,
        ),
        (
            "FemAmbientTemperature",
            55,
            40,
            5,
            -2,
        ),
        (
            "FemCaseTemperature1",
            55,
            40,
            5,
            -2,
        ),
        (
            "FemCaseTemperature2",
            55,
            40,
            5,
            -2,
        ),
        (
            "FemHeatsinkTemperature1",
            55,
            40,
            5,
            -2,
        ),
        (
            "FemHeatsinkTemperature2",
            55,
            40,
            5,
            -2,
        ),
        (
            "portBreakersTripped",
            4,
            2,
            -1,
            -2,
        ),
    ],
)
# pylint: disable=too-many-arguments, too-many-positional-arguments
def test_health(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    attribute: str,
    max_alarm: float,
    max_warning: float,
    min_warning: float,
    min_alarm: float,
) -> None:
    """
    Test healthstate responds correctly to attribute changes.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param smartbox_device: the smartbox device under test
    :param change_event_callbacks: a collection of change event callbacks.
    :param attribute: the attribute to test health for.
    :param max_alarm: maximum alarm threshold for the attribute.
    :param max_warning: maximum warning threshold for the attribute.
    :param min_warning: minimum warning threshold for the attribute.
    :param min_alarm: minimum alarm threshold for the attribute.
    """
    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks["state"].assert_change_event(tango.DevState.DISABLE)

    smartbox_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.UNKNOWN)

    smartbox_device.subscribe_event(
        "powersupplyOutputVoltage",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["attribute"],
    )
    change_event_callbacks.assert_change_event("attribute", Anything)

    smartbox_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)

    # This is a bit reliant on implementation details. This is the last attribute we
    # poll for health, so we wait on a change event for this attribute as a proxy for
    # a full poll cycle completing.
    change_event_callbacks.assert_change_event("attribute", Anything)

    try:
        attribute_config = smartbox_device.get_attribute_config(attribute.lower())
        alarm_config = attribute_config.alarms
        alarm_config.max_warning = str(max_warning)
        alarm_config.max_alarm = str(max_alarm)
        alarm_config.min_warning = str(min_warning)
        alarm_config.min_alarm = str(min_alarm)
        attribute_config.alarms = alarm_config
        smartbox_device.set_attribute_config(attribute_config)
    except tango.DevFailed:
        pytest.xfail("Ran into PyTango monitor lock issue, to be fixed in 10.1.0")

    smartbox_device.CallAttributeCallback(
        json.dumps(
            {
                "attr_name": attribute.lower(),
                "attr_value": float(max_alarm * 1.5),
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.FAILED)
    assert smartbox_device.state() == tango.DevState.ALARM

    smartbox_device.CallAttributeCallback(
        json.dumps(
            {
                "attr_name": attribute.lower(),
                "attr_value": float((max_warning + min_warning) / 2),
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)
    assert smartbox_device.state() == tango.DevState.ON


@pytest.mark.parametrize(
    (
        "pasd_status",
        "health_state",
        "dev_state",
    ),
    [
        ("UNINITIALISED", HealthState.OK, tango.DevState.ON),
        ("OK", HealthState.OK, tango.DevState.ON),
        ("WARNING", HealthState.DEGRADED, tango.DevState.ALARM),
        ("ALARM", HealthState.FAILED, tango.DevState.ALARM),
        ("RECOVERY", HealthState.FAILED, tango.DevState.ALARM),
        ("POWERDOWN", HealthState.UNKNOWN, tango.DevState.ON),
        ("FAKE_STATUS", HealthState.UNKNOWN, tango.DevState.ON),
    ],
)
def test_pasd_status_health(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    pasd_status: str,
    health_state: HealthState,
    dev_state: tango.DevState,
) -> None:
    """
    Test the healthstate responds correctly to the pasdstatus.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param smartbox_device: the smartbox device under test
    :param change_event_callbacks: a collection of change event callbacks.
    :param pasd_status: the PaSD status to simulate.
    :param health_state: the expected health state.
    :param dev_state: the expected device state.
    """
    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks["state"].assert_change_event(tango.DevState.DISABLE)

    smartbox_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.UNKNOWN)

    smartbox_device.subscribe_event(
        "femHeatsinkTemperature2",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["attribute"],
    )
    change_event_callbacks.assert_change_event("attribute", Anything)

    smartbox_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)

    # This is a bit reliant on implementation details. This is the last attribute we
    # poll for health, so we wait on a change event for this attribute as a proxy for
    # a full poll cycle completing.
    change_event_callbacks.assert_change_event("attribute", Anything)

    smartbox_device.CallAttributeCallback(
        json.dumps(
            {
                "attr_name": "pasdstatus",
                "attr_value": pasd_status,
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )
    )
    # Device starts in OK, we'll only get an event if its changing.
    if health_state != HealthState.OK:
        change_event_callbacks["healthState"].assert_change_event(health_state)
    else:
        change_event_callbacks["healthState"].assert_not_called()
    assert smartbox_device.healthstate == health_state
    assert smartbox_device.state() == dev_state


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
        "attribute",
        timeout=3.0,
        assert_no_error=False,
    )
