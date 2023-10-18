# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsFieldStation."""

from __future__ import annotations

import gc
import json
import unittest.mock
from contextlib import nullcontext
from typing import Any, ContextManager

import pytest
import tango
from ska_control_model import (
    AdminMode,
    LoggingLevel,
    PowerState,
    ResultCode,
    TaskStatus,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsFieldStation
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
        timeout=2.0,
        assert_no_error=False,
    )


@pytest.fixture(name="mock_component_manager")
def mock_component_manager_fixture() -> unittest.mock.Mock:
    """
    Return a mock to be used as a component manager for the field station bus device.

    :return: a mock to be used as a component manager for the
        field station bus device.
    """
    return unittest.mock.Mock()


@pytest.fixture(name="patched_field_station_device_class")
def patched_field_station_device_class_fixture(
    mock_component_manager: unittest.mock.Mock,
) -> type[MccsFieldStation]:
    """
    Return a field station bus device that is patched with a mock component manager.

    :param mock_component_manager: the mock component manager with
        which to patch the device

    :return: a field station bus device that is patched with a mock component
        manager.
    """

    class PatchedMccsFieldStation(MccsFieldStation):
        """A field station bus device patched with a mock component manager."""

        def __init__(self: PatchedMccsFieldStation, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)

        def create_component_manager(
            self: PatchedMccsFieldStation,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager instead of the usual one.

            :return: a mock component manager
            """
            mock_component_manager._component_state_callback = (
                self._component_state_callback
            )

            return mock_component_manager

    return PatchedMccsFieldStation


@pytest.fixture(name="field_station_device")
def field_station_device_fixture(
    patched_field_station_device_class: type[MccsFieldStation],
    mock_fndh: unittest.mock.Mock,
    mock_smartbox: unittest.mock.Mock,
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the FieldStation Tango device under test.

    :param patched_field_station_device_class: a patches class for use in testing

    :yield: a proxy to the FieldStation Tango device under test.
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_fndh_device(mock_fndh)
    for smarbox_no in range(1, 24 + 1):
        harness.set_mock_smartbox_device(mock_smartbox, smarbox_no)
    harness.set_field_station_device(
        logging_level=int(LoggingLevel.DEBUG),
        device_class=patched_field_station_device_class,
    )

    with harness as context:
        yield context.get_field_station_device()


@pytest.mark.parametrize(
    (
        "device_command",
        "component_manager_method",
        "device_command_argin",
        "component_manager_method_return",
    ),
    [
        (
            "PowerOnAntenna",
            "turn_on_antenna",
            4,
            [True, True],
        ),
        (
            "PowerOffAntenna",
            "turn_off_antenna",
            4,
            [True, True],
        ),
    ],
)
def test_command(  # pylint: disable=too-many-arguments
    field_station_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
    change_event_callbacks,
) -> None:
    """
    Test tango command with mocked response from component manager.

    :param field_station_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched field station bus device.
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

    command = getattr(field_station_device, device_command)
    field_station_device.adminmode = AdminMode.ONLINE
    if device_command_argin is None:
        command_return = command()
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command
