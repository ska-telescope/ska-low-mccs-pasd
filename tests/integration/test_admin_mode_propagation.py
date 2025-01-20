# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains integration tests for AdminMode propagation in the PaSD devices."""

from __future__ import annotations

import time

import pytest
import tango
from ska_control_model import AdminMode
from ska_low_mccs_common.mode_inheritance import ModeInheritor
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return MockTangoEventCallbackGroup(
        "fndh_adminMode",
        "pasdbus_adminMode",
        timeout=2.0,
        assert_no_error=False,
    )


class TestAdminModePropagation:
    """Test adminMode propagation."""

    def test_admin_mode_propagation(
        self: TestAdminModePropagation,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test AdminMode propagation.

        :param field_station_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        # Wait for the ModeInheritor initial thread to finish so that
        # the initial value of the adminMode attribute is set.
        # TODO: Move this to a fixture.
        time.sleep(ModeInheritor.INITIAL_VALUE_TIMEOUT + 1)

        assert field_station_device.adminMode == AdminMode.OFFLINE
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "adminMode",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_adminMode"],
        )

        pasd_bus_device.subscribe_event(
            "adminMode",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdbus_adminMode"],
        )

        field_station_device.adminMode = AdminMode.ONLINE

        change_event_callbacks.assert_change_event(
            "fndh_adminMode", AdminMode.ONLINE, lookahead=4, consume_nonmatches=True
        )
        change_event_callbacks.assert_change_event(
            "pasdbus_adminMode", AdminMode.ONLINE, lookahead=2, consume_nonmatches=True
        )
        assert fndh_device.adminMode == AdminMode.ONLINE
        assert pasd_bus_device.adminMode == AdminMode.ONLINE
