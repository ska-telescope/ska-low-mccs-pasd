# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsFNDH."""

from __future__ import annotations

import gc
import json
import unittest.mock
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, ContextManager
from unittest.mock import patch

import numpy as np
import pytest
import tango
from ska_control_model import (
    AdminMode,
    HealthState,
    LoggingLevel,
    PowerState,
    ResultCode,
)
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsFNDH
from tests.harness import PasdTangoTestHarness

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
        "attribute",
        timeout=2.0,
        assert_no_error=False,
    )


@pytest.fixture(name="mock_component_manager")
def mock_component_manager_fixture() -> unittest.mock.Mock:
    """
    Return a mock to be used as a component manager for the fndh bus device.

    :return: a mock to be used as a component manager for the
        fndh bus device.
    """
    component_manager = unittest.mock.Mock()
    component_manager.max_queued_tasks = 0
    component_manager.max_executing_tasks = 1
    return component_manager


@pytest.fixture(name="patched_fndh_device_class")
def patched_fndh_device_class_fixture(
    mock_component_manager: unittest.mock.Mock,
) -> type[MccsFNDH]:
    """
    Return a fndh bus device that is patched with a mock component manager.

    :param mock_component_manager: the mock component manager with
        which to patch the device

    :return: a fndh bus device that is patched with a mock component
        manager.
    """

    class PatchedMccsFNDH(MccsFNDH):
        """A fndh bus device patched with a mock component manager."""

        def __init__(self: PatchedMccsFNDH, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)

        def create_component_manager(
            self: PatchedMccsFNDH,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager instead of the usual one.

            :return: a mock component manager
            """
            mock_component_manager._component_state_changed_callback = (
                self._component_state_changed_callback
            )

            return mock_component_manager

    return PatchedMccsFNDH


@pytest.fixture(name="fndh_device")
def fndh_device_fixture(
    patched_fndh_device_class: type[MccsFNDH],
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the FNDH Tango device under test.

    :param patched_fndh_device_class: a patches class for use in testing

    :yield: a proxy to the FNDH Tango device under test.
    """
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
        harness = PasdTangoTestHarness()
        harness.set_fndh_device(
            logging_level=int(LoggingLevel.DEBUG),
            device_class=patched_fndh_device_class,
        )

        with harness as context:
            yield context.get_fndh_device()


@pytest.fixture(name="healthful_fndh_device")
def healthful_fndh_device_fixture(
    mock_pasdbus: unittest.mock.Mock,
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the FNDH Tango device under test.

    :param mock_pasdbus: mocked pasdbus to add to the context.

    :yield: a proxy to the FNDH Tango device under test.
    """

    class PatchedMccsFNDH(MccsFNDH):
        """A fndh bus device patched with a mock component manager."""

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
        harness = PasdTangoTestHarness()
        harness.set_fndh_device(
            logging_level=int(LoggingLevel.DEBUG),
            device_class=PatchedMccsFNDH,
        )
        harness.set_mock_pasd_bus_device(mock_pasdbus)

        with harness as context:
            yield context.get_fndh_device()


@pytest.mark.parametrize(
    (
        "device_command",
        "component_manager_method",
        "device_command_argin",
        "component_manager_method_return",
    ),
    [
        (
            "PowerOnPort",
            "power_on_port",
            4,
            [True, True],
        ),
        (
            "PowerOffPort",
            "power_off_port",
            4,
            [True, True],
        ),
        (
            "SetPortPowers",
            "set_port_powers",
            json.dumps(
                {
                    "port_powers": [False for _ in range(24)],
                    "stay_on_when_offline": True,
                }
            ),
            [True, True],
        ),
    ],
)
def test_command(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    fndh_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
) -> None:
    """
    Test tango command with mocked response from component manager.

    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched fndh bus device.
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

    command = getattr(fndh_device, device_command)
    if device_command_argin is None:
        command_return = command([])
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command


def test_is_port_on(
    fndh_device: tango.DeviceProxy,
) -> None:
    """
    Test the PortPowerState command.

    This unit test is kept very light because all it does is
    read a default value from a dictionary.

    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    """
    assert fndh_device.PortPowerState(1) == PowerState.UNKNOWN


@pytest.mark.parametrize(
    "config_in, expected_config, context",
    [
        pytest.param(
            {
                "overCurrentThreshold": 12.3,
                "overVoltageThreshold": 45.6,
                "humidityThreshold": 78.9,
            },
            {
                "overCurrentThreshold": 12.3,
                "overVoltageThreshold": 45.6,
                "humidityThreshold": 78.9,
            },
            None,
            id="valid config is entered correctly",
        ),
        pytest.param(
            {"overCurrentThreshold": 12.3, "humidityThreshold": 78.9},
            {
                "overCurrentThreshold": 12.3,
                "overVoltageThreshold": 0.0,
                "humidityThreshold": 78.9,
            },
            None,
            id="missing config data is valid",
        ),
        pytest.param(
            {
                "overCurrentThreshold_wrong_name": 12.3,
                "overVoltageThreshold": 45.6,
                "humidityThreshold": 78.9,
            },
            {
                "overCurrentThreshold": 0.0,
                "overVoltageThreshold": 45.6,
                "humidityThreshold": 78.9,
            },
            None,
            id="invalid named configs are skipped",
        ),
        pytest.param(
            {
                "overCurrentThreshold_wrong_name": "some string",
                "overVoltageThreshold": True,
                "humidityThreshold": [78.9, 12.3],
            },
            None,
            pytest.raises(
                tango.DevFailed, match="ValidationError: True is not of type 'number'"
            ),
            id="invalid types raise validation error",
        ),
        pytest.param(
            {},
            {
                "overCurrentThreshold": 0.0,
                "overVoltageThreshold": 0.0,
                "humidityThreshold": 0.0,
            },
            None,
            id="empty dict is no op",
        ),
    ],
)
def test_configure(
    fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    config_in: dict,
    expected_config: dict | None,
    context: ContextManager | None,
) -> None:
    """
    Test for Configure.

    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param change_event_callbacks: a callback that
        we can use to change events on device.
    :param config_in: configuration of the device
    :param expected_config: the expected output configuration
    :param context: context in which to invoke the Configure command.
        Useful for asserting whether the command will raise an error or
        not.
    """
    fndh_device.subscribe_event(
        "adminMode",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["adminMode"],
    )
    change_event_callbacks.assert_change_event("adminMode", AdminMode.OFFLINE)
    assert fndh_device.adminMode == AdminMode.OFFLINE

    fndh_device.adminMode = AdminMode.ONLINE
    change_event_callbacks.assert_change_event("adminMode", AdminMode.ONLINE)
    assert fndh_device.adminMode == AdminMode.ONLINE

    with context or nullcontext():
        fndh_device.Configure(json.dumps(config_in))

    if expected_config is not None:
        assert (
            fndh_device.overCurrentThreshold == expected_config["overCurrentThreshold"]
        )
        assert (
            fndh_device.overVoltageThreshold == expected_config["overVoltageThreshold"]
        )
        assert fndh_device.humidityThreshold == expected_config["humidityThreshold"]


def test_threshold_attributes(
    fndh_device: tango.DeviceProxy,
) -> None:
    """
    Test for Configure.

    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    """
    fndh_device.overCurrentThreshold = 22.0
    assert fndh_device.overCurrentThreshold == 22.0
    fndh_device.overVoltageThreshold = 6.0
    assert fndh_device.overVoltageThreshold == 6.0
    fndh_device.humidityThreshold = 60.0
    assert fndh_device.humidityThreshold == 60.0


def test_ports_with_smartbox(
    fndh_device: tango.DeviceProxy,
) -> None:
    """
    Test that we can update the port configuration.

    :param fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    """
    assert fndh_device.portsWithSmartbox.tolist() == [1, 2, 3]
    mocked_ports_bad = [i + 1 for i in range(25)]
    with pytest.raises(tango.DevFailed):
        fndh_device.portsWithSmartbox = mocked_ports_bad
    mocked_ports = [i + 1 for i in range(24)]
    fndh_device.portsWithSmartbox = np.array(mocked_ports)
    assert fndh_device.portsWithSmartbox.tolist() == mocked_ports
    # check less than a full station.
    mocked_ports = [i + 1 for i in range(4)]
    fndh_device.portsWithSmartbox = np.array(mocked_ports)
    assert fndh_device.portsWithSmartbox.tolist() == mocked_ports


@pytest.mark.parametrize(
    ("attribute", "max_alarm", "max_warning", "min_warning", "min_alarm"),
    [
        ("Psu48vVoltage1", 51, 49, 46, 41),
        ("Psu48vVoltage2", 51, 49, 46, 41),
        ("Psu48vCurrent", 17, 15, 0, -4),
        ("Psu48vTemperature1", 95, 80, 5, -2),
        ("Psu48vTemperature2", 95, 80, 5, -2),
        ("PanelTemperature", 80, 65, 5, -2),
        ("FncbTemperature", 80, 65, 5, -2),
        ("FncbHumidity", 80, 65, 15, 5),
        ("CommsGatewayTemperature", 80, 65, 5, -2),
        ("PowerModuleTemperature", 80, 65, 5, -2),
        ("OutsideTemperature", 80, 65, 5, -2),
        ("InternalAmbientTemperature", 80, 65, 5, -2),
    ],
)
# pylint: disable=too-many-arguments, too-many-positional-arguments
def test_health(
    healthful_fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    attribute: str,
    max_alarm: float,
    max_warning: float,
    min_warning: float,
    min_alarm: float,
) -> None:
    """
    Test the FNDH health model.

    :param healthful_fndh_device: the  device under test
    :param change_event_callbacks: a collection of change event callbacks.
    :param attribute: the attribute to test health for.
    :param max_alarm: maximum alarm threshold for the attribute.
    :param max_warning: maximum warning threshold for the attribute.
    :param min_warning: minimum warning threshold for the attribute.
    :param min_alarm: minimum alarm threshold for the attribute.
    """
    healthful_fndh_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks["state"].assert_change_event(tango.DevState.DISABLE)

    healthful_fndh_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.UNKNOWN)

    healthful_fndh_device.subscribe_event(
        "internalAmbientTemperature",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["attribute"],
    )
    change_event_callbacks.assert_change_event("attribute", Anything)

    healthful_fndh_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)

    # This is a bit reliant on implementation details. This is the last attribute we
    # poll for health, so we wait on a change event for this attribute as a proxy for
    # a full poll cycle completing.
    change_event_callbacks.assert_change_event("attribute", Anything)

    try:
        attribute_config = healthful_fndh_device.get_attribute_config(attribute.lower())
        alarm_config = attribute_config.alarms
        alarm_config.max_warning = str(max_warning)
        alarm_config.max_alarm = str(max_alarm)
        alarm_config.min_warning = str(min_warning)
        alarm_config.min_alarm = str(min_alarm)
        attribute_config.alarms = alarm_config
        healthful_fndh_device.set_attribute_config(attribute_config)
    except tango.DevFailed:
        pytest.xfail("Ran into PyTango monitor lock issue, to be fixed in 10.1.0")
    converter = float if attribute.lower() != "fncbhumidity" else int
    healthful_fndh_device.CallAttributeCallback(
        json.dumps(
            {
                "attr_name": attribute.lower(),
                "attr_value": converter(max_alarm * 1.5),
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.FAILED)
    assert healthful_fndh_device.state() == tango.DevState.ALARM

    healthful_fndh_device.CallAttributeCallback(
        json.dumps(
            {
                "attr_name": attribute.lower(),
                "attr_value": converter((max_warning + min_warning) / 2),
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)
    assert healthful_fndh_device.state() == tango.DevState.ON


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
        ("POWERUP", HealthState.UNKNOWN, tango.DevState.ON),
        ("FAKE_STATUS", HealthState.UNKNOWN, tango.DevState.ON),
    ],
)
def test_pasd_status_health(
    healthful_fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    pasd_status: str,
    health_state: HealthState,
    dev_state: tango.DevState,
) -> None:
    """
    Test pasdstatus converted to correct health state.

    :param healthful_fndh_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param healthful_fndh_device: the smartbox device under test
    :param change_event_callbacks: a collection of change event callbacks.
    :param pasd_status: the PaSD status to simulate.
    :param health_state: the expected health state.
    :param dev_state: the expected device state.
    """
    healthful_fndh_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks["state"].assert_change_event(tango.DevState.DISABLE)

    healthful_fndh_device.subscribe_event(
        "healthState",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["healthState"],
    )
    change_event_callbacks["healthState"].assert_change_event(HealthState.UNKNOWN)

    healthful_fndh_device.subscribe_event(
        "internalAmbientTemperature",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["attribute"],
    )
    change_event_callbacks.assert_change_event("attribute", Anything)

    healthful_fndh_device.adminMode = AdminMode.ONLINE
    change_event_callbacks["state"].assert_change_event(tango.DevState.UNKNOWN)
    change_event_callbacks["state"].assert_change_event(tango.DevState.ON)
    change_event_callbacks["healthState"].assert_change_event(HealthState.OK)

    # This is a bit reliant on implementation details. This is the last attribute we
    # poll for health, so we wait on a change event for this attribute as a proxy for
    # a full poll cycle completing.
    change_event_callbacks.assert_change_event("attribute", Anything)

    healthful_fndh_device.CallAttributeCallback(
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
    assert healthful_fndh_device.healthstate == health_state
    assert healthful_fndh_device.state() == dev_state
