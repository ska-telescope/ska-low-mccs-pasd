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
from typing import Any

import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, PowerState, ResultCode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.harness import PasdTangoTestHarness

# TODO: Weird hang-at-garbage-collection bug
gc.disable()


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    fndh_port: int,
    smartbox_number: int,
    mock_fndh: unittest.mock.Mock,
    mock_pasdbus: unittest.mock.Mock,
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the smartbox Tango device under test.

    :param fndh_port: the port that this smartbox is attached to
    :param smartbox_number: number of the smartbox under test
    :param mock_pasdbus: A mock PaSD bus device.
    :param mock_fndh: A mock FNDH device.

    :yield: a proxy to the smartbox Tango device under test.
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_fndh_device(mock_fndh)
    harness.set_mock_pasd_bus_device(mock_pasdbus)
    harness.add_smartbox_device(
        smartbox_number,
        fndh_port=fndh_port,
        logging_level=int(LoggingLevel.DEBUG),
    )

    with harness as context:
        yield context.get_smartbox_device(smartbox_number)


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
        (
            "PowerOnAllPorts",
            None,
        ),
        (
            "PowerOffAllPorts",
            None,
        ),
    ],
)
def test_command_queued(
    smartbox_device: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    mocked_initial_port_power_state: PowerState,
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

    state = {PowerState.ON: tango.DevState.ON, PowerState.OFF: tango.DevState.OFF}
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
