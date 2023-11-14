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
from ska_control_model import AdminMode, PowerState, ResultCode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FndhSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import PasdConversionUtility
from ska_low_mccs_pasd.pasd_data import PasdData

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
        "pasd_bus_state",
        "antenna_power_states",
        "field_station_outside_temperature",
        "fndh_outside_temperature",
        "smartbox24PortsPowerSensed",
        "smartbox1_state",
        "smartbox2_state",
        "smartbox3_state",
        "smartbox4_state",
        "smartbox5_state",
        "smartbox6_state",
        "smartbox7_state",
        "smartbox8_state",
        "smartbox9_state",
        "smartbox10_state",
        "smartbox11_state",
        "smartbox12_state",
        "smartbox13_state",
        "smartbox14_state",
        "smartbox15_state",
        "smartbox16_state",
        "smartbox17_state",
        "smartbox18_state",
        "smartbox19_state",
        "smartbox20_state",
        "smartbox21_state",
        "smartbox22_state",
        "smartbox23_state",
        "smartbox24_state",
        "smartbox24AlarmFlags",
        timeout=20.0,
    )


@pytest.fixture(name="antenna_to_turn_on")
def antenna_to_turn_on_fixture() -> int:
    """
    Return the logical antenna.

    :return: the logical antenna to use in test.
    """
    return 26


class TestFieldStationIntegration:
    """Test pasdbus and fndh integration."""

    # pylint: disable=too-many-arguments, disable=too-many-locals
    def test_turn_on_off_antenna(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        smartbox_proxys: list[tango.DeviceProxy],
        off_smartbox_id: int,
        antenna_to_turn_on: int,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test Antenna can be powered on.

        :param field_station_device: provide to the field station device
        :param pasd_bus_device: proxy to the pasd_device
        :param fndh_device: proxy to the FNDH device
        :param change_event_callbacks: group of Tango change event
            callbacks with asynchrony support
        :param smartbox_proxys: a list of device proxies to the stations
            smartboxes.
        :param off_smartbox_id: a fixture containing the id of a smartbox
            simulated to be off.
        :param antenna_to_turn_on: the antenne under test.
        :param fndh_simulator: the backend fndh simulator.
        """
        # PasdBus Online
        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)

        # Initialise the station subdevices.
        pasd_bus_device.initializefndh()
        for i in range(PasdData.NUMBER_OF_SMARTBOXES):
            pasd_bus_device.initializesmartbox(i)

        # set adminMode online for all smartbox.
        for smartbox_id, smartbox in enumerate(smartbox_proxys):
            smartbox.subscribe_event(
                "state",
                tango.EventType.CHANGE_EVENT,
                change_event_callbacks[f"smartbox{smartbox_id+1}_state"],
            )
            change_event_callbacks[
                f"smartbox{smartbox_id+1}_state"
            ].assert_change_event(Anything)

            smartbox.adminMode = AdminMode.ONLINE

            change_event_callbacks[
                f"smartbox{smartbox_id+1}_state"
            ].assert_change_event(tango.DevState.UNKNOWN)

            change_event_callbacks[
                f"smartbox{smartbox_id+1}_state"
            ].assert_change_event(Anything)

        # Set the Fndh adminMode ONLINE
        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )
        change_event_callbacks["fndh_state"].assert_change_event(Anything)
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.ON)

        # Subscribe to antennapowerstates attribute.
        field_station_device.subscribe_event(
            "antennapowerstates",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["antenna_power_states"],
        )
        change_event_callbacks["antenna_power_states"].assert_change_event(Anything)

        # Set the FieldStation adminMode ONLINE
        # This will form proxies to smartboxes.
        field_station_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_state"],
        )
        change_event_callbacks["field_station_state"].assert_change_event(Anything)
        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.ON
        )
        for i in range(PasdData.NUMBER_OF_SMARTBOXES):
            change_event_callbacks["antenna_power_states"].assert_change_event(Anything)
        change_event_callbacks["antenna_power_states"].assert_not_called()

        # Use mapping to work out what smartbox port will change.
        antenna_mapping = json.loads(field_station_device.antennamapping)
        smartbox_id, smartbox_port = antenna_mapping[str(antenna_to_turn_on)]

        # Check initial state.
        assert not smartbox_proxys[smartbox_id - 1].portspowersensed[smartbox_port - 1]

        # Turn on Antenna
        field_station_device.PowerOnAntenna(antenna_to_turn_on)

        # Check power changed.
        change_event_callbacks["antenna_power_states"].assert_change_event(Anything)
        assert smartbox_proxys[smartbox_id - 1].portspowersensed[smartbox_port - 1]
        antenna_power_states = json.loads(field_station_device.antennapowerstates)

        # off_smartbox_id is off in the simulator.
        # Check that antennas attached to it are OFF.
        for antenna_id, config in antenna_mapping.items():
            smartbox_id = config[0]
            # If the smartbox is off all antenna attached to it are OFF.
            if smartbox_id == off_smartbox_id:
                assert antenna_power_states[str(antenna_id)] == PowerState.OFF

        # Check both fndh and FieldStation agree value of outsideTemperature
        default_simulator_outside_temperature = (
            PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE]
            )[0]
        )
        fndh_device.subscribe_event(
            "outsideTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_outside_temperature"],
        )
        change_event_callbacks["fndh_outside_temperature"].assert_change_event(
            default_simulator_outside_temperature
        )
        field_station_device.subscribe_event(
            "outsideTemperature",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_outside_temperature"],
        )
        change_event_callbacks["field_station_outside_temperature"].assert_change_event(
            default_simulator_outside_temperature
        )
        assert fndh_device.outsideTemperature == default_simulator_outside_temperature
        assert (
            field_station_device.outsideTemperature
            == default_simulator_outside_temperature
        )

        # Check that when we mock a change in the register value
        # Both fndh and FieldStation get the updated value.
        mocked_outside_temperature_register: int = 2345
        scaled_outside_temperature = PasdConversionUtility.scale_signed_16bit(
            [mocked_outside_temperature_register]
        )[0]

        fndh_simulator.outside_temperature = mocked_outside_temperature_register

        change_event_callbacks["fndh_outside_temperature"].assert_change_event(
            scaled_outside_temperature
        )
        change_event_callbacks["field_station_outside_temperature"].assert_change_event(
            scaled_outside_temperature
        )

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
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)

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

        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        # State will only reach unknown as it inherits state from smartboxes which
        # aren't being acted upon.
        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # State is stuck in UNKNOWN so there's no way to check
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
