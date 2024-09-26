# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Integration tests of MccsFieldStation with subservient devices."""

from __future__ import annotations

import copy
import gc
import json
import re
import time
import unittest.mock
from typing import Any

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
        "field_station_configuration_change",
        "fndh_state",
        "pasd_bus_state",
        "antenna_power_states",
        "field_station_outside_temperature",
        "fndh_outside_temperature",
        "smartbox1_state",
        "smartbox2_state",
        timeout=20.0,
    )


@pytest.fixture(name="invalid_simulated_configuration", scope="module")
def invalid_simulated_configuration_fixture() -> dict[Any, Any]:
    """
    Return a invalid configuration.

    This is invalid because all 256 antenna must be specified.
    And the masked key is required.
    This configuration only specifies 230.

    :return: a configuration for representing the antenna port mapping information.
    """
    number_of_antenna = 230
    antennas = {}
    smartboxes = {}
    for i in range(1, number_of_antenna + 1):
        antennas[i] = {"smartbox": i % 13 + 1, "smartbox_port": i % 11}
    for i in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        smartboxes[i] = {"fndh_port": str(i), "modbus_id": i}

    configuration = {"antennas": antennas, "pasd": {"smartboxes": smartboxes}}
    return configuration


@pytest.fixture(name="simulated_configuration_alternative", scope="session")
def simulated_configuration_alternative_fixture(
    simulated_configuration: dict[Any, Any],
) -> dict[Any, Any]:
    """
    Return an alternate configuration for the fieldstation.

    :param simulated_configuration: the default simulated configuration.

    :return: an alternate configuration for fieldstation
    """
    alternate_config = copy.deepcopy(simulated_configuration)
    antenna1 = alternate_config["antennas"]["sb01-01"]
    antenna2 = alternate_config["antennas"]["sb01-02"]

    alternate_config["antennas"]["sb01-01"] = antenna2
    alternate_config["antennas"]["sb01-02"] = antenna1

    return alternate_config


@pytest.fixture(name="antenna_to_turn_on")
def antenna_to_turn_on_fixture() -> str:
    """
    Return the logical antenna.

    :return: the logical antenna to use in test.
    """
    return "sb01-04"


def antenna_mapping_from_reference_data(
    reference_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Return the antenna mapping expected from a reference configuration.

    :param reference_data: the backend reference data.

    :return: the antenna_mapping that adheres to
        'schemas.MccsFieldStation_UpdateAntennaMapping.json'
    """
    antenna_mapping: dict = {}
    for antenna_name, values in reference_data["antennas"].items():
        antenna_mapping[antenna_name] = [values["smartbox"], values["smartbox_port"]]

    return {"antennaMapping": antenna_mapping}


class TestFieldStationIntegration:
    """Test pasdbus and fndh integration."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    # pylint: disable=too-many-locals, too-many-statements
    def test_turn_on_off_antenna(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        smartbox_proxys: list[tango.DeviceProxy],
        off_smartbox_id: int,
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
        field_station_device.subscribe_event(
            "smartboxMapping",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_configuration_change"],
        )
        change_event_callbacks[
            "field_station_configuration_change"
        ].assert_change_event(Anything)
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
            tango.DevState.STANDBY
        )
        for i in range(len(smartbox_proxys)):
            change_event_callbacks["antenna_power_states"].assert_change_event(Anything)

        # Use mapping to work out what smartbox port will change.
        antenna_mapping = json.loads(field_station_device.antennamapping)

        chosen_smartbox_port = 0
        chosen_smartbox_id: int
        for antenna_id, (smartbox_id_str, smartbox_port) in antenna_mapping[
            "antennaMapping"
        ].items():
            if antenna_id == antenna_to_turn_on:
                chosen_smartbox_port = smartbox_port
                chosen_smartbox_id = int(re.findall(r"\d+", smartbox_id_str)[0]) - 1
        # Check initial state.
        assert not smartbox_proxys[chosen_smartbox_id].portspowersensed[
            chosen_smartbox_port - 1
        ]

        antenna_power_states = json.loads(field_station_device.antennapowerstates)
        assert antenna_power_states[antenna_to_turn_on] != PowerState.ON

        # Turn on Antenna
        field_station_device.PowerOnAntenna(antenna_to_turn_on)

        # Check power changed.
        change_event_callbacks["antenna_power_states"].assert_change_event(Anything)
        assert smartbox_proxys[chosen_smartbox_id].portspowersensed[
            chosen_smartbox_port - 1
        ]
        antenna_power_states = json.loads(field_station_device.antennapowerstates)

        # off_smartbox_id is off in the simulator.
        # Check that antennas attached to it are OFF.
        for antenna_id, config in antenna_mapping["antennaMapping"].items():
            chosen_smartbox_id = config[0]
            # If the smartbox is off all antenna attached to it are OFF.
            if chosen_smartbox_id == off_smartbox_id:
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
            (command_id, "COMPLETED"), lookahead=3
        )

        assert fndh_device.overCurrentThreshold == over_current_threshold
        assert fndh_device.overVoltageThreshold == over_voltage_threshold
        assert fndh_device.humidityThreshold == humidity_threshold

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_configuration_change(
        self: TestFieldStationIntegration,
        field_station_device: tango.DeviceProxy,
        simulated_configuration: dict[Any, Any],
        configuration_manager: unittest.mock.Mock,
        invalid_simulated_configuration: dict[Any, Any],
        simulated_configuration_alternative: dict[Any, Any],
    ) -> None:
        """
        Test loading a new configuration.

        :param field_station_device: provide to the field station device
        :param simulated_configuration: a fixture containing the
            simulated configuration.
        :param configuration_manager: the configuration manager to manager configuration
            for field station.
        :param invalid_simulated_configuration: a fixture containing a
            invalid simulated configuration.
        :param simulated_configuration_alternative: a fixture containing a
            alternative simulated configuration.
        """
        antenna_mapping = antenna_mapping_from_reference_data(simulated_configuration)

        # Check initial configuration loaded.
        assert field_station_device.antennamapping == json.dumps(antenna_mapping)

        # Loading a invalid backend configuration.
        configuration_manager.read_data = unittest.mock.Mock(
            return_value=invalid_simulated_configuration
        )
        [return_code], [command_id] = field_station_device.LoadConfiguration()
        poll_until_command_completed(field_station_device, command_id, 3)

        assert field_station_device.antennamapping == json.dumps(antenna_mapping)
        invalid_antenna_mapping = antenna_mapping_from_reference_data(
            invalid_simulated_configuration
        )
        assert field_station_device.antennamapping != json.dumps(
            invalid_antenna_mapping
        )

        # Loading a different backend configuration.
        configuration_manager.read_data = unittest.mock.Mock(
            return_value=simulated_configuration_alternative
        )

        [return_code], [command_id] = field_station_device.LoadConfiguration()
        poll_until_command_completed(field_station_device, command_id, 3)

        alternative_antenna_mapping = antenna_mapping_from_reference_data(
            simulated_configuration_alternative
        )
        assert field_station_device.antennamapping != json.dumps(antenna_mapping)
        assert field_station_device.antennamapping == json.dumps(
            alternative_antenna_mapping
        )


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
