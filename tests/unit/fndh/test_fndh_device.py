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
from typing import Any, Generator

import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, ResultCode
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsFNDH

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
    return unittest.mock.Mock()


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


@pytest.fixture(name="fndh_name", scope="session")
def fndh_name_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs-pasd/fndh/001"


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    fndh_name: str,
    patched_fndh_device_class: type[MccsFNDH],
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param fndh_name: the name of the fndh Tango device
    :param patched_fndh_device_class: a subclass of MccsFNDH that
        has been patched with extra commands that mock system under
        control behaviours.

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        fndh_name,
        patched_fndh_device_class,
        FndhPort=5,
        PasdFQDNs="low-mccs-pasd/pasdbus/001",
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    with context_manager as context:
        yield context


@pytest.fixture(name="fndh_device")
def fndh_device_fixture(
    tango_harness: TangoContextProtocol,
    fndh_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the fndh Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param fndh_name: name of the fndh Tango device.

    :yield: the fndh Tango device under test.
    """
    yield tango_harness.get_device(fndh_name)


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
    ],
)
def test_command(  # pylint: disable=too-many-arguments
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
        command_return = command()
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command


@pytest.mark.parametrize(
    (
        "device_command",
        "component_manager_method",
        "device_command_argin",
        "component_manager_method_return",
        "device_response",
    ),
    [
        (
            "IsPortOn",
            "is_port_on",
            4,
            False,
            False,
        ),
    ],
)
def test_fast_command(  # pylint: disable=too-many-arguments
    fndh_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
    device_response: Any,
) -> None:
    """
    Test tango fast command with mocked response from component manager.

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
    :param device_response: response from the device.
    """
    method_mock = unittest.mock.Mock(return_value=component_manager_method_return)
    setattr(mock_component_manager, component_manager_method, method_mock)
    method_mock.assert_not_called()

    command = getattr(fndh_device, device_command)
    if device_command_argin is None:
        command_return = command()
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return == device_response


@pytest.mark.parametrize(
    "config_in, expected_config",
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
            id="valid config is entered correctly",
        ),
        pytest.param(
            {"overCurrentThreshold": 12.3, "humidityThreshold": 78.9},
            {
                "overCurrentThreshold": 12.3,
                "overVoltageThreshold": 0.0,
                "humidityThreshold": 78.9,
            },
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
            id="invalid named configs are skipped",
        ),
        pytest.param(
            {
                "overCurrentThreshold_wrong_name": "some string",
                "overVoltageThreshold": True,
                "humidityThreshold": [78.9, 12.3],
            },
            {
                "overCurrentThreshold": 0.0,
                "overVoltageThreshold": 0.0,
                "humidityThreshold": 0.0,
            },
            id="invalid types dont apply",
        ),
        pytest.param(
            {},
            {
                "overCurrentThreshold": 0.0,
                "overVoltageThreshold": 0.0,
                "humidityThreshold": 0.0,
            },
            id="empty dict is no op",
        ),
    ],
)
def test_configure(
    fndh_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    config_in: dict,
    expected_config: dict,
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

    fndh_device.Configure(json.dumps(config_in))

    assert fndh_device.overCurrentThreshold == expected_config["overCurrentThreshold"]
    assert fndh_device.overVoltageThreshold == expected_config["overVoltageThreshold"]
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
