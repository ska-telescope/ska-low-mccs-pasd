# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Integration tests of MccsFieldStation with subservient devices."""

from __future__ import annotations

import gc
import json
import time

import pytest
import tango
from ska_control_model import AdminMode, ResultCode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

gc.disable()


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "field_station_state",
        "field_station_command_status",
        "fndh_state",
        timeout=15.0,
    )


class TestFieldStationIntegration:  # pylint: disable=too-few-public-methods
    """Test pasdbus and fndh integration."""

    def test_configure(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test that configuring the field station configures subservient devices.

        :param field_station_device: provide to the field station device
        :param fndh_device: proxy to the FNDH device
        :param change_event_callbacks: group of Tango change event
            callbacks with asynchrony support
        """
        # Setup and confirm initial state of FNDH
        assert fndh_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )

        # TODO: https://gitlab.com/tango-controls/pytango/-/issues/533
        # Device is in alarm state because
        # we haven't defined root attributes for its forwarded attributes,
        # because tango.test_context.MultiDeviceTestContext does not yet support this.
        # Forwarded attributes will be supported in a future pytango version.
        change_event_callbacks["fndh_state"].assert_change_event(
            tango.DevState.ALARM,  # DISABLE
        )

        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)

        assert fndh_device.overCurrentThreshold == 0.0
        assert fndh_device.overVoltageThreshold == 0.0
        assert fndh_device.humidityThreshold == 0.0

        # Setup and confirm initial state of field station
        assert field_station_device.adminMode == AdminMode.OFFLINE

        field_station_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_state"],
        )

        # The field station device will be in alarm state
        # because
        #     Forwarded attribute outsideTemperature is not correctly configured!
        #     Root attribute name = Not defined
        # but we can still test what we need to
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.ALARM
        )

        field_station_device.adminMode = AdminMode.ONLINE

        # State is stuck in ALARM so there's no way to check
        # that we have successfully established communication.
        # Let's just sleep for a few seconds.
        time.sleep(3)

        over_current_threshold = 12.3
        over_voltage_threshold = 45.6
        humidity_threshold = 78.9

        config = {
            "overCurrentThreshold": over_current_threshold,
            "overVoltageThreshold": over_voltage_threshold,
            "humidityThreshold": humidity_threshold,
        }

        response = field_station_device.Configure(json.dumps(config))
        [result_code_array, [command_id]] = response
        assert result_code_array[0] == ResultCode.QUEUED

        field_station_device.subscribe_event(
            "longRunningCommandStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_command_status"],
        )
        # Sometimes COMPLETED follows so soon after QUEUED
        # that we don't see the QUEUED event.
        # So instead of asserting QUEUED then COMPLETED,
        # We just assert COMPLETED with lookahead 2.
        change_event_callbacks["field_station_command_status"].assert_change_event(
            (command_id, "COMPLETED"), lookahead=2
        )

        assert fndh_device.overCurrentThreshold == over_current_threshold
        assert fndh_device.overVoltageThreshold == over_voltage_threshold
        assert fndh_device.humidityThreshold == humidity_threshold
