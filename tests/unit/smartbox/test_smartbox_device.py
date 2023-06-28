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
import unittest.mock
from typing import Any, Generator

import pytest
import tango
from ska_control_model import (
    AdminMode,
    CommunicationStatus,
    LoggingLevel,
    PowerState,
    ResultCode,
)
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsSmartBox
from ska_low_mccs_pasd.smart_box import SmartBoxComponentManager

# TODO: Weird hang-at-garbage-collection bug
gc.disable()


@pytest.fixture(name="smartbox_name", scope="session")
def smartbox_name_fixture() -> str:
    """
    Return the name of the smartbox_bus Tango device.

    :return: the name of the smartbox_bus Tango device.
    """
    return "low-mccs-pasd/smartbox/00001"


@pytest.fixture(name="patched_smartbox_device_class")
def patched_smartbox_device_class_fixture(
    smartbox_component_manager: unittest.mock.Mock,
) -> type[MccsSmartBox]:
    """
    Return a SmartBox device that is patched with a mock component manager.

    :param smartbox_component_manager: the smartbox component manager with
        which to patch the device

    :return: a SmartBox device that is patched with a mock component
        manager.
    """

    class PatchedMccsSmartBox(MccsSmartBox):
        """A SmartBox bus device patched with a mock component manager."""

        def create_component_manager(
            self: PatchedMccsSmartBox,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager.

            :return: a mock component manager with overwritten callbacks.
            """
            smartbox_component_manager._component_state_callback = (
                self._component_state_callback
            )
            smartbox_component_manager._communication_state_callback = (
                self._communication_state_changed
            )
            smartbox_component_manager._smartbox_proxy._attribute_change_callback = (
                self._attribute_changed_callback
            )
            smartbox_component_manager._fndh_proxy._port_power_callback = (
                smartbox_component_manager._power_state_change
            )

            return smartbox_component_manager

    return PatchedMccsSmartBox


@pytest.fixture(name="test_context")
def test_context_fixture(  # pylint: disable=too-many-arguments
    fndh_fqdn: str,
    mock_fndh: unittest.mock.Mock,
    mock_pasdbus: unittest.mock.Mock,
    pasdbus_fqdn: str,
    smartbox_name: str,
    patched_smartbox_device_class: type[MccsSmartBox],
) -> Generator[TangoContextProtocol, None, None]:
    """
    Create a test context standing up the devices under test.

    :param fndh_fqdn: the name of the FNDH.
    :param mock_fndh: A mock FNDH device.
    :param mock_pasdbus: A mock PaSDBus device.
    :param pasdbus_fqdn: The name of the PaSDBus.
    :param smartbox_name: the name of the smartbox to stand up.
    :param patched_smartbox_device_class: the patched smartbox device to
        use.

    :yield: A tango context with devices to test.
    """
    context_manager = ThreadedTestTangoContextManager()
    # Add SmartBox and Tile mock devices.
    context_manager.add_device(
        smartbox_name,
        patched_smartbox_device_class,
        FndhPort=5,
        PasdFQDN="low-mccs/pasdbus/001",
        FndhFQDN="low-mccs/fndh/001",
        SmartBoxNumber=5,
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    context_manager.add_mock_device(fndh_fqdn, mock_fndh)
    context_manager.add_mock_device(pasdbus_fqdn, mock_pasdbus)
    with context_manager as context:
        yield context


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    test_context: TangoContextProtocol,
    smartbox_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the smartbox Tango device under test.

    :param test_context: a test context containing the Tango devices.
    :param smartbox_name: name of the smartbox_bus Tango device.

    :yield: the smartbox Tango device under test.
    """
    yield test_context.get_device(smartbox_name)


def test_device_transitions_to_power_state_of_fndh_port(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    mocked_initial_port_power_state: PowerState,
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

    state = {PowerState.ON: tango.DevState.ON, PowerState.OFF: tango.DevState.OFF}
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
    ],
)
def test_command_queued(
    smartbox_device: tango.DeviceProxy,
    smartbox_component_manager: SmartBoxComponentManager,
    device_command: str,
    device_command_argin: Any,
) -> None:
    """
    Test commands return the correct result code.

    :param smartbox_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param device_command: name of the device command under test.
    :param device_command_argin: argument to the device command
    :param smartbox_component_manager: the component manager of the
        smartbox device.
    """
    # Mock the smartbox being connected.
    smartbox_component_manager._update_communication_state(
        CommunicationStatus.ESTABLISHED
    )

    command = getattr(smartbox_device, device_command)
    if device_command_argin is None:
        command_return = command()
    else:
        command_return = command(device_command_argin)

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command


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
        timeout=10.0,
        assert_no_error=False,
    )
