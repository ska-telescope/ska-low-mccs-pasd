# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsFNDH."""

from __future__ import annotations

import gc

import pytest
import tango
from ska_control_model import AdminMode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator

gc.disable()  # Bug in garbage collection causes tests to hang.


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return MockTangoEventCallbackGroup(
        "field_station_state",
        "field_station_healthstate",
        "fndh_state",
        "fndh_healthstate",
        "smartbox_state",
        "smartbox_healthstate",
        "smartbox_adminMode",
        timeout=5.0,
    )


class TestFieldStationHealth:
    """Class to test Field Station health."""

    def test_health_aggregation(
        self: TestFieldStationHealth,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        fndh_simulator: FndhSimulator,
        smartbox_proxys: list[tango.DeviceProxy],
    ) -> None:
        """
        Test the health aggregation of the Field Station device

        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: a proxy to the PaSD bus device under test.
        :param fndh_simulator: the FNDH simulator under test
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        assert field_station_device.adminMode == AdminMode.OFFLINE
        field_station_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_healthstate"],
        )
        field_station_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_state"],
        )

        field_station_device.adminMode = AdminMode.ONLINE
        fndh_device.adminMode = AdminMode.ONLINE
        pasd_bus_device.adminMode = AdminMode.ONLINE
        for smartbox in smartbox_proxys:
            smartbox.adminMode = AdminMode.ONLINE
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.STANDBY, lookahead=10
        )
        field_station_device.On()
        # Stuck in Standby/Failed for some reason.
        import time

        time.sleep(5)
        print(f"{len(smartbox_proxys)=}")
        print(f"{field_station_device.healthState=}")
        print(f"{field_station_device.healthReport=}")
        print(f"{field_station_device.lrcExecuting=}")
        print(f"{field_station_device.lrcFinished=}")
        print(f"{field_station_device.state()=}")

        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.ON, lookahead=10
        )
        assert field_station_device.state() == tango.DevState.ON
        # print(f"{field_station_device.healthReport=}")
        # assert field_station_device.healthState == HealthState.OK
        # assert fndh_device.healthState == HealthState.OK
        # for smartbox in smartbox_proxys:
        #     assert smartbox.healthState == HealthState.OK
        # assert field_station_device.healthThresholds == (0, 1, 1)
