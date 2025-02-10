# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains integration tests for AdminMode propagation."""

from __future__ import annotations

import pytest
import tango
from ska_control_model import AdminMode
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
        "fncc_adminMode",
        "smartbox_adminMode",
        timeout=2.0,
        assert_no_error=False,
    )


class TestAdminModePropagation:
    """Test adminMode propagation."""

    def test_fndh_mode_propagation(
        self: TestAdminModePropagation,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test AdminMode propagation for FNDH.

        :param field_station_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        fndh_device.inheritModes = True

        assert field_station_device.adminMode == AdminMode.OFFLINE
        assert fndh_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "adminMode",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_adminMode"],
        )

        field_station_device.adminMode = AdminMode.ONLINE

        # First change events might be subscription errors so we set
        # a higher lookahead value
        change_event_callbacks.assert_change_event(
            "fndh_adminMode", AdminMode.ONLINE, lookahead=2, consume_nonmatches=True
        )
        assert fndh_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event("fndh_adminMode", AdminMode.OFFLINE)
        assert fndh_device.adminMode == AdminMode.OFFLINE

        # Turn inheritance off by setting directly
        fndh_device.adminMode = AdminMode.ENGINEERING
        change_event_callbacks.assert_change_event(
            "fndh_adminMode", AdminMode.ENGINEERING
        )

        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_adminMode"].assert_not_called()
        assert fndh_device.adminMode == AdminMode.ENGINEERING

        # Go back to inheriting
        fndh_device.inheritModes = True
        change_event_callbacks.assert_change_event("fndh_adminMode", AdminMode.ONLINE)
        assert fndh_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event("fndh_adminMode", AdminMode.OFFLINE)
        assert fndh_device.adminMode == AdminMode.OFFLINE

    def test_pasdbus_mode_propagation(
        self: TestAdminModePropagation,
        field_station_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test AdminMode propagation for pasdbus.

        :param field_station_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        pasd_bus_device.inheritModes = True

        assert field_station_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        pasd_bus_device.subscribe_event(
            "adminMode",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdbus_adminMode"],
        )

        field_station_device.adminMode = AdminMode.ONLINE

        # First change events might be subscription errors so we set
        # a higher lookahead value
        change_event_callbacks.assert_change_event(
            "pasdbus_adminMode", AdminMode.ONLINE, lookahead=2, consume_nonmatches=True
        )
        assert pasd_bus_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event(
            "pasdbus_adminMode", AdminMode.OFFLINE
        )
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        # Turn inheritance off by setting directly
        pasd_bus_device.adminMode = AdminMode.ENGINEERING
        change_event_callbacks.assert_change_event(
            "pasdbus_adminMode", AdminMode.ENGINEERING
        )

        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasdbus_adminMode"].assert_not_called()
        assert pasd_bus_device.adminMode == AdminMode.ENGINEERING

        # Go back to inheriting
        pasd_bus_device.inheritModes = True
        change_event_callbacks.assert_change_event(
            "pasdbus_adminMode", AdminMode.ONLINE
        )
        assert pasd_bus_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event(
            "pasdbus_adminMode", AdminMode.OFFLINE
        )
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

    def test_smartbox_mode_propagation(
        self: TestAdminModePropagation,
        field_station_device: tango.DeviceProxy,
        on_smartbox_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test AdminMode propagation for Smartbox.

        :param field_station_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param on_smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        on_smartbox_device.inheritModes = True

        assert field_station_device.adminMode == AdminMode.OFFLINE
        assert on_smartbox_device.adminMode == AdminMode.OFFLINE

        on_smartbox_device.subscribe_event(
            "adminMode",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox_adminMode"],
        )

        field_station_device.adminMode = AdminMode.ONLINE

        # First change events might be subscription errors so we set
        # a higher lookahead value
        change_event_callbacks.assert_change_event(
            "smartbox_adminMode", AdminMode.ONLINE, lookahead=2, consume_nonmatches=True
        )
        assert on_smartbox_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event(
            "smartbox_adminMode", AdminMode.OFFLINE
        )
        assert on_smartbox_device.adminMode == AdminMode.OFFLINE

        # Turn inheritance off by setting directly
        on_smartbox_device.adminMode = AdminMode.ENGINEERING
        change_event_callbacks.assert_change_event(
            "smartbox_adminMode", AdminMode.ENGINEERING
        )

        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox_adminMode"].assert_not_called()
        assert on_smartbox_device.adminMode == AdminMode.ENGINEERING

        # Go back to inheriting
        on_smartbox_device.inheritModes = True
        change_event_callbacks.assert_change_event(
            "smartbox_adminMode", AdminMode.ONLINE
        )
        assert on_smartbox_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event(
            "smartbox_adminMode", AdminMode.OFFLINE
        )
        assert on_smartbox_device.adminMode == AdminMode.OFFLINE

    def test_fncc_mode_propagation(
        self: TestAdminModePropagation,
        field_station_device: tango.DeviceProxy,
        fncc_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test AdminMode propagation for Smartbox.

        :param field_station_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fncc_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        fncc_device.inheritModes = True

        assert field_station_device.adminMode == AdminMode.OFFLINE
        assert fncc_device.adminMode == AdminMode.OFFLINE

        fncc_device.subscribe_event(
            "adminMode",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fncc_adminMode"],
        )

        field_station_device.adminMode = AdminMode.ONLINE

        # First change events might be subscription errors so we set
        # a higher lookahead value
        change_event_callbacks.assert_change_event(
            "fncc_adminMode", AdminMode.ONLINE, lookahead=2, consume_nonmatches=True
        )
        assert fncc_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event("fncc_adminMode", AdminMode.OFFLINE)
        assert fncc_device.adminMode == AdminMode.OFFLINE

        # Turn inheritance off by setting directly
        fncc_device.adminMode = AdminMode.ENGINEERING
        change_event_callbacks.assert_change_event(
            "fncc_adminMode", AdminMode.ENGINEERING
        )

        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fncc_adminMode"].assert_not_called()
        assert fncc_device.adminMode == AdminMode.ENGINEERING

        # Go back to inheriting
        fncc_device.inheritModes = True
        change_event_callbacks.assert_change_event("fncc_adminMode", AdminMode.ONLINE)
        assert fncc_device.adminMode == AdminMode.ONLINE

        field_station_device.adminMode = AdminMode.OFFLINE
        change_event_callbacks.assert_change_event("fncc_adminMode", AdminMode.OFFLINE)
        assert fncc_device.adminMode == AdminMode.OFFLINE
