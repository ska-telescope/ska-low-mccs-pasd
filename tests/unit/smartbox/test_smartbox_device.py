# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsSmartBox."""

from __future__ import annotations

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

from ska_low_mccs_pasd import MccsSmartBox


@pytest.fixture(name="mock_component_manager")
def mock_component_manager_fixture() -> unittest.mock.Mock:
    """
    Return a mock to be used as a component manager for the SmartBox bus device.

    :return: a mock to be used as a component manager for the
        smartbox bus device.
    """
    return unittest.mock.Mock()


@pytest.fixture(name="patched_smartbox_device_class")
def patched_smartbox_device_class_fixture(
    mock_component_manager: unittest.mock.Mock,
) -> type[MccsSmartBox]:
    """
    Return a SmartBox bus device that is patched with a mock component manager.

    :param mock_component_manager: the mock component manager with
        which to patch the device

    :return: a SmartBox bus device that is patched with a mock component
        manager.
    """

    class PatchedMccsSmartBox(MccsSmartBox):
        """A SmartBox bus device patched with a mock component manager."""

        def create_component_manager(
            self: PatchedMccsSmartBox,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager instead of the usual one.

            :return: a mock component manager
            """
            mock_component_manager._component_state_changed_callback = (
                self._component_state_changed_callback
            )

            return mock_component_manager

    return PatchedMccsSmartBox


@pytest.fixture(name="smartbox_name", scope="session")
def smartbox_name_fixture() -> str:
    """
    Return the name of the smartbox_bus Tango device.

    :return: the name of the smartbox_bus Tango device.
    """
    return "low-mccs-smartbox/smartbox/00001"


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    smartbox_name: str,
    patched_smartbox_device_class: type[MccsSmartBox],
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param smartbox_name: the name of the smartbox_bus Tango device
    :param patched_smartbox_device_class: a subclass of MccsSmartBox that
        has been patched with extra commands that mock system under
        control behaviours.

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        smartbox_name,
        patched_smartbox_device_class,
        FndhPort=5,
        PasdFQDNs="low-mccs-pasd/pasdbus/001",
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    with context_manager as context:
        yield context


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    tango_harness: TangoContextProtocol,
    smartbox_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the smartbox_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param smartbox_name: name of the smartbox_bus Tango device.

    :yield: the smartbox_bus Tango device under test.
    """
    yield tango_harness.get_device(smartbox_name)


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
            "turn_on_port",
            4,
            [True, True],
        ),
        (
            "PowerOffPort",
            "turn_off_port",
            4,
            [True, True],
        ),
        (
            "GetAntennaInfo",
            "get_antenna_info",
            4,
            [True, True],
        ),
    ],
)
def test_command(  # pylint: disable=too-many-arguments
    smartbox_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
) -> None:
    """
    Test that device attribute writes result in component manager property writes.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched smartbox bus device.
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

    command = getattr(smartbox_device, device_command)
    if device_command_argin is None:
        command_return = command()
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command


@pytest.mark.xfail
def test_communication(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Test the Tango device's communication with the smartbox_device.

    :param smartbox_device: a proxy to the smartbox_device device under test.
    :param change_event_callbacks: dictionary of mock change event
        callbacks with asynchrony support
    """
    assert smartbox_device.adminMode == AdminMode.OFFLINE

    smartbox_device.subscribe_event(
        "state",
        tango.EventType.CHANGE_EVENT,
        change_event_callbacks["state"],
    )
    change_event_callbacks.assert_change_event("state", tango.DevState.DISABLE)

    smartbox_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

    change_event_callbacks.assert_change_event("state", tango.DevState.UNKNOWN)
    change_event_callbacks.assert_change_event("state", tango.DevState.ON)


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
