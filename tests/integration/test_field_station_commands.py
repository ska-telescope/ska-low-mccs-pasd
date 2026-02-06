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
import random
import time

import pytest
import tango
from ska_control_model import AdminMode, PowerState, ResultCode
from ska_low_pasd_driver import FndhSimulator
from ska_low_pasd_driver.pasd_bus_conversions import PasdConversionUtility
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

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
        "field_station_configuration_change",
        "fndh_state",
        "pasd_bus_state",
        "antenna_power_states",
        "field_station_outside_temperature",
        "fndh_outside_temperature",
        "smartbox1_state",
        "smartbox2_state",
        "fndh_ports_power_sensed",
        timeout=20.0,
    )


@pytest.fixture(name="antenna_to_turn_on")
def antenna_to_turn_on_fixture() -> str:
    """
    Return the logical antenna.

    :return: the logical antenna to use in test.
    """
    return "sb01-04"


class TestFieldStationIntegration:
    """Test pasdbus and fndh integration."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_off_command(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        off_smartbox_attached_port: int,
        smartbox_attached_ports: list[int],
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test Off command turns off only the FNDH ports with attached smartboxes.

        :param field_station_device: proxy to the field station device
        :param fndh_device: proxy to the FNDH device
        :param fndh_simulator: the backend fndh simulator
        :param off_smartbox_attached_port: the FNDH port connected to the off smartbox.
        :param smartbox_attached_ports: list of ports with attached smartboxes
        :param change_event_callbacks: group of Tango change event
            callbacks with asynchrony support
        """
        fndh_device.PortsWithSmartbox = smartbox_attached_ports
        field_station_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_state"],
        )
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.DISABLE
        )

        field_station_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.UNKNOWN, lookahead=2
        )
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.STANDBY, lookahead=2
        )

        # All FNDH ports with attached smartboxes should now be turned on
        expected_port_status = [
            i in smartbox_attached_ports
            for i in range(1, PasdData.NUMBER_OF_FNDH_PORTS + 1)
        ]
        expected_port_status[off_smartbox_attached_port - 1] = False
        assert all(
            a == b for a, b in zip(fndh_device.portsPowerSensed, expected_port_status)
        )

        # Manually turn on an additional random port
        # which is not connected to this FNDH
        unattached_ports: set[int] = set(range(PasdData.NUMBER_OF_FNDH_PORTS)) - set(
            smartbox_attached_ports
        )
        random_port: int = random.choice(list(unattached_ports))
        expected_port_status[random_port - 1] = True

        fndh_simulator.simulate_port_stuck_on(random_port)

        fndh_device.subscribe_event(
            "portsPowerSensed",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_ports_power_sensed"],
        )

        # Turn Field Station Off and verify only attached smartbox ports
        # are turned off
        expected_port_status = [False] * PasdData.NUMBER_OF_FNDH_PORTS
        expected_port_status[random_port - 1] = True
        assert field_station_device.Off()[0] == ResultCode.QUEUED
        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.OFF, lookahead=2
        )
        # These events will now be staggered as each FNDH port is powered individually.
        # We could do a complicated loop of assertions, however that is done in unit
        # testing, lets just assert we end up in the right state.
        change_event_callbacks["fndh_ports_power_sensed"].assert_change_event(
            expected_port_status, lookahead=6 + 28
        )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    # pylint: disable=too-many-locals
    def test_turn_on_off_antenna(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        smartbox_proxys: list[tango.DeviceProxy],
        antenna_to_turn_on: str,
        fndh_simulator: FndhSimulator,
    ) -> None:
        """
        Test Antenna can be powered on.

        :param field_station_device: provide to the field station device
        :param pasd_bus_device: proxy to the pasd_device
        :param fndh_device: proxy to the FNDH device
        :param change_event_callbacks: group of Tango change event
            callbacks with asynchrony support
        :param smartbox_proxys: a dict of device proxies to the stations
            smartboxes.
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
        for i in range(1, len(smartbox_proxys) + 1):
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
            tango.DevState.STANDBY, lookahead=2
        )
        for i in range(len(smartbox_proxys)):
            change_event_callbacks["antenna_power_states"].assert_change_event(Anything)

        # Jank using the knowledge that sb01-03 is on port 3 of smartbox 1
        # (see add_smartbox_device in PasdTangoTestHarness)
        chosen_smartbox_port = int(antenna_to_turn_on.split("-")[1])
        chosen_smartbox_id = int(antenna_to_turn_on.split("-")[0][2:])
        # Check initial state.
        assert not smartbox_proxys[chosen_smartbox_id - 1].portspowersensed[
            chosen_smartbox_port - 1
        ]

        antenna_power_states = json.loads(field_station_device.antennapowerstates)
        assert antenna_power_states[antenna_to_turn_on] != PowerState.ON

        # Turn on Antenna
        field_station_device.PowerOnAntenna(antenna_to_turn_on)

        # Check power changed.
        change_event_callbacks["antenna_power_states"].assert_change_event(Anything)
        assert smartbox_proxys[chosen_smartbox_id - 1].portspowersensed[
            chosen_smartbox_port - 1
        ]

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
            scaled_outside_temperature, lookahead=2
        )
        change_event_callbacks["field_station_outside_temperature"].assert_change_event(
            scaled_outside_temperature, lookahead=2
        )

    def test_configure(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test that configuring the field station configures subservient devices.

        :param field_station_device: provide to the field station device
        :param fndh_device: proxy to the FNDH device
        :param pasd_bus_device: proxy to the pasd bus device.
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
        pasd_bus_device.adminMode = AdminMode.ONLINE
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
        field_station_device.subscribe_event(
            "longRunningCommandStatus",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_command_status"],
        )
        change_event_callbacks["field_station_command_status"].assert_change_event(
            Anything
        )
        response = field_station_device.Configure(json.dumps(config))
        [result_code_array, [command_id]] = response
        assert result_code_array[0] == ResultCode.QUEUED

        # lookahead of 4. It seems most of the time a lookahead of 3 is sufficient.
        # However, it seems that STAGING is sometimes called (but not always).
        change_event_callbacks["field_station_command_status"].assert_change_event(
            (command_id, "COMPLETED"), lookahead=4
        )
        assert fndh_device.overCurrentThreshold == over_current_threshold
        assert fndh_device.overVoltageThreshold == over_voltage_threshold
        assert fndh_device.humidityThreshold == humidity_threshold


# pylint: disable=inconsistent-return-statements
def poll_until_command_completed(
    device: tango.DeviceProxy, command_id: str, no_of_iters: int = 5
) -> None:
    """
    Poll until command has completed.

    This function recursively calls itself up to `no_of_iters` times.

    :param device: the TANGO device
    :param command_id: the command_id to check
    :param no_of_iters: number of times to iterate
    """
    command_status = device.CheckLongRunningCommandStatus(command_id)
    if command_status == "COMPLETED":
        return

    if no_of_iters == 1:
        pytest.fail("Command Failed to complete in time")

    time.sleep(0.1)
    return poll_until_command_completed(device, command_id, no_of_iters - 1)
