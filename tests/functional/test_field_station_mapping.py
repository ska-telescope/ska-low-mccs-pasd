# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a test of the MCCS FieldStation device antenna mapping."""
from __future__ import annotations

import gc
import json
import time
from typing import Any, Callable, Final

import jsonschema
import pytest
import tango
from pytest_bdd import given, parsers, scenarios, then, when
from ska_control_model import AdminMode, PowerState, SimulationMode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.conftest import MAX_NUMBER_OF_SMARTBOXES_PER_STATION

gc.disable()

ANTENNA_MAPPING_SCHEMA: Final = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://skao.int/UpdateAntennaMapping.json",
    "title": "MccsFieldStation UpdateAntennaMapping schema",
    "description": "Schema for MccsFieldStation's UpdateAntennaMapping command",
    "type": "object",
    "properties": {
        "antennaMapping": {
            "description": "the antennas",
            "type": "object",
            "minProperties": 0,
            "maxProperties": 256,
            "patternProperties": {
                "[a-zA-Z0-9_]+": {
                    "description": "the antennas",
                    "type": "array",
                }
            },
        }
    },
    "required": ["antennaMapping"],
}
ANTENNA_MASK_SCHEMA: Final = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://skao.int/UpdateAntennaMask.json",
    "title": "MccsFieldStation UpdateAntennaMask schema",
    "description": "Schema for MccsFieldStation's UpdateAntennaMask command",
    "type": "object",
    "properties": {
        "antennaMask": {
            "description": "the antennas",
            "type": "object",
            "minProperties": 0,
            "maxProperties": 256,
            "patternProperties": {
                "[a-zA-Z0-9_]+": {"description": "the antennas", "type": "boolean"}
            },
        }
    },
    "required": ["antennaMask"],
}
SMARTBOX_MAPPING_SCHEMA: Final = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://skao.int/UpdateSmartboxMapping.json",
    "title": "MccsFieldStation UpdateSmartboxMapping schema",
    "description": "Schema for MccsFieldStation's UpdateSmartboxMapping command",
    "type": "object",
    "properties": {
        "smartboxMapping": {
            "description": "the smartbox mappings",
            "type": "object",
            "minProperties": 0,
            "maxProperties": 24,
            "patternProperties": {
                "[a-zA-Z0-9_]+": {"description": "fqdns", "type": "integer"}
            },
        }
    },
    "required": ["smartboxMapping"],
}

scenarios("./features/field_station_mapping.feature")


@given(parsers.parse("A {device_ref} which is ready"))
def get_ready_device(device_ref: str, set_device_state: Callable) -> None:
    """
    Get device in state ON and adminmode ONLINE.

    :param device_ref: Gherkin reference to device under test.
    :param set_device_state: function to set device state.
    """
    print(f"Setting device {device_ref} ready...")
    set_device_state(
        device_ref,
        state=tango.DevState.ON,
        mode=AdminMode.ONLINE,
        simulation_mode=SimulationMode.TRUE,
    )


@given("PasdBus is initialised")
def pasd_is_initialised(pasd_bus_device: tango.DeviceProxy, smartbox_id: int) -> None:
    """
    Get PaSD devices initialised.

    :param pasd_bus_device: A `tango.DeviceProxy` to the PaSD device.
    :param smartbox_id: number of the smartbox under test.
    """
    pasd_bus_device.initializefndh()
    pasd_bus_device.initializesmartbox(smartbox_id)


@given("the smartboxes are ready")
def get_device_ready(
    set_device_state: Callable,
    smartboxes_under_test: list[tango.DeviceProxy],
) -> None:
    """
    Check that the fieldstation exists.

    :param smartboxes_under_test: a list of the smartboxes under test.
    :param set_device_state: function to set device state.
    """
    for smartbox in smartboxes_under_test:
        print(f"Setting device {smartbox.dev_name()} ready...")
        set_device_state(
            device_proxy=smartbox,
            device_ref="",
            state=tango.DevState.ON,
            mode=AdminMode.ONLINE,
            simulation_mode=SimulationMode.TRUE,
        )


@then(parsers.parse("smartbox {smartbox_id} is {desired_state}"))
@given(
    parsers.parse("smartbox {smartbox_id} is {desired_state}"),
    target_fixture="smartbox_under_test",
)
def set_smartbox_off(
    smartbox_id: str,
    set_device_state: Callable,
    smartboxes_under_test: list[tango.DeviceProxy],
    station_label: str,
    state_mapping: dict[str, tango.DevState],
    desired_state: str,
) -> None:
    """
    Check that the fieldstation exists.

    :param smartbox_id: a list of the smartboxes under test.
    :param set_device_state: function to set device state.
    :param smartboxes_under_test: a list of the smartboxes under test.
    :param station_label: name of the station under test
    :param state_mapping: mapping from the reference Gherkin state to
        a `tango.DevState`.
    :param desired_state: a Gherkin reference state.

    :return: a `tango.DeviceProxy` to the smartbox under test.
    """
    for smartbox_proxy in smartboxes_under_test:
        if (
            smartbox_proxy.dev_name()
            == f"low-mccs/smartbox/{station_label}-sb{int(smartbox_id):02}"
        ):
            desired_tango_state = state_mapping[desired_state]
            if smartbox_proxy.state() != tango.DevState.OFF:
                set_device_state(
                    device_proxy=smartbox_proxy,
                    device_ref="",
                    state=desired_tango_state,
                    mode=AdminMode.ONLINE,
                    simulation_mode=SimulationMode.TRUE,
                )
            return smartbox_proxy
    assert False, "Device not found"


@given(parsers.parse("the smartbox port {smartbox_port} is {desired_state}"))
def set_smartbox_port_off(
    smartbox_under_test: tango.DeviceProxy,
    smartbox_port: str,
    state_mapping: dict[str, tango.DevState],
    desired_state: str,
) -> None:
    """
    Check that the fieldstation exists.

    :param smartbox_under_test: the smartbox of interest.
    :param smartbox_port: the port of interest
    :param state_mapping: mapping from the reference Gherkin state to
        a `tango.DevState`.
    :param desired_state: a Gherkin reference state.
    """
    desired_tango_state = state_mapping[desired_state]
    if desired_tango_state == tango.DevState.OFF:
        assert not smartbox_under_test.portspowersensed[int(smartbox_port) - 1]
    else:
        assert smartbox_under_test.portspowersensed[int(smartbox_port) - 1]


@given(parsers.parse("antenna {antenna_no} is {desired_state}"))
def assert_antenna_on(
    field_station_device: tango.DeviceProxy,
    antenna_no: str,
    state_mapping: dict[str, tango.DevState],
    desired_state: str,
) -> None:
    """
    Check that the antenna is reported in the correct state.

    :param field_station_device: a proxy to the fieldstation device.
    :param antenna_no: the logical antenna to check.
    :param state_mapping: mapping from the reference Gherkin state to
        a `tango.DevState`.
    :param desired_state: a Gherkin reference state.
    """
    desired_tango_state = state_mapping[desired_state]
    ticks = 10
    tick = 0
    while tick < ticks:
        try:
            antenna_power = json.loads(field_station_device.antennapowerstates)[
                antenna_no
            ]

            if desired_tango_state == tango.DevState.OFF:
                assert antenna_power == PowerState.OFF
            else:
                assert antenna_power == PowerState.ON
            return
        except AssertionError:
            time.sleep(1)
            tick += 1
    pytest.fail(reason=f"Antennas didn't reach correct state : {antenna_power}")


@when(parsers.parse("we turn {desired_state} antenna {antenna_number}"))
def turn_antenna_state(
    field_station_device: tango.DeviceProxy,
    antenna_number: str,
    desired_state: str,
) -> None:
    """
    Ask for the port mapping.

    :param field_station_device: a proxy to the field station device.
    :param antenna_number: the logical antenna to turn on.
    :param desired_state: a Gherkin reference state.
    """
    if desired_state == "OFF":
        field_station_device.PowerOffAntenna(antenna_number)
    elif desired_state == "ON":
        field_station_device.PowerOnAntenna(antenna_number)
    else:
        assert False


@then(parsers.parse("antenna {antenna_number} turns {desired_state}"))
def correct_antenna_turns_on(
    field_station_device: tango.DeviceProxy,
    antenna_number: str,
    desired_state: str,
) -> None:
    """
    Check that the correct antenna turns ON or OFF.

    :param field_station_device: a proxy to the field station device.
    :param antenna_number: the logical antenna to turn on/off.
    :param desired_state: a Gherkin reference state.
    """
    if desired_state == "OFF":
        desired_power = PowerState.OFF
    elif desired_state == "ON":
        desired_power = PowerState.ON

    ticks = 20
    tick = 0
    while tick < ticks:
        power = json.loads(field_station_device.antennaPowerStates)[antenna_number]
        if power == desired_power:
            break
        time.sleep(3)
        tick += 1
    assert power == desired_power


@then(parsers.parse("the correct smartbox is {desired_state}"))
def correct_smartbox_turns_on(
    smartbox_under_test: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
    desired_state: str,
) -> None:
    """
    Check the correct smartbox is on.

    :param smartbox_under_test: the smartbox of interest.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param desired_state: a Gherkin reference state.
    """
    if desired_state == "OFF":
        if smartbox_under_test.state() != tango.DevState.OFF:
            subscription_id = smartbox_under_test.subscribe_event(
                "state",
                tango.EventType.CHANGE_EVENT,
                change_event_callbacks[f"{smartbox_under_test.dev_name()}/state"],
            )
            change_event_callbacks[
                f"{smartbox_under_test.dev_name()}/state"
            ].assert_change_event(tango.DevState.OFF, lookahead=2)
            smartbox_under_test.unsubscribe_event(subscription_id)

        assert smartbox_under_test.state() == tango.DevState.OFF

    elif desired_state == "ON":
        subscription_id = smartbox_under_test.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"{smartbox_under_test.dev_name()}/state"],
        )
        change_event_callbacks[
            f"{smartbox_under_test.dev_name()}/state"
        ].assert_change_event(tango.DevState.ON, lookahead=2)
        smartbox_under_test.unsubscribe_event(subscription_id)

        assert smartbox_under_test.state() == tango.DevState.ON
    else:
        assert False


@then(parsers.parse("smartbox port {smartbox_port} turns {desired_state}"))
def correct_smartbox_port_turns_off(
    smartbox_under_test: tango.DeviceProxy,
    smartbox_port: str,
    desired_state: str,
) -> None:
    """
    Check that the smartbox under test turns OFF.

    :param smartbox_under_test: the smartbox of interest.
    :param smartbox_port: the port of interest
    :param desired_state: a Gherkin reference state.
    """
    if desired_state == "OFF":
        port_has_power = False
    elif desired_state == "ON":
        port_has_power = True
    else:
        assert False
    smartbox_index = int(smartbox_port) - 1
    assert smartbox_under_test.portspowersensed[smartbox_index] == port_has_power


@when("we check the fieldstations maps", target_fixture="maps")
def check_port_mapping(
    field_station_device: tango.DeviceProxy,
) -> dict[str, dict[Any, Any]]:
    """
    Ask for the port mapping.

    :param field_station_device: a proxy to the field station device.

    :return: the maps reported by the field station.
    """
    return {
        "antenna_map": json.loads(field_station_device.antennaMapping),
        "smartbox_map": json.loads(field_station_device.smartboxMapping),
        "antenna_mask": json.loads(field_station_device.antennaMask),
    }


@then("we get valid mappings")
def check_the_mapping_is_valid(
    maps: dict[str, dict], smartboxes_under_test: list, is_true_context: bool
) -> None:
    """
    Check that the mapping passes the validation.

    :param smartboxes_under_test: a list of the smartboxes under test.
    :param maps: the maps reported by the field station.
    :param is_true_context: Is this test runnning in a true context.
    """
    # Validate against the
    jsonschema.validate(maps["antenna_map"], ANTENNA_MAPPING_SCHEMA)

    jsonschema.validate(maps["smartbox_map"], SMARTBOX_MAPPING_SCHEMA)

    jsonschema.validate(maps["antenna_mask"], ANTENNA_MASK_SCHEMA)

    # Check that we have a configuration for every smartbox under test.
    number_of_configured_smartboxes = 0
    for smartbox_config in maps["smartbox_map"]["smartboxMapping"]:
        number_of_configured_smartboxes += 1
    if is_true_context:
        # Currently the store is configured with the deployed configuration from
        # helm. We check that for the devices deployed we have a configuration.
        assert number_of_configured_smartboxes == len(smartboxes_under_test)
    else:
        # We have mocked the store with a configuration for all 24 smartboxes
        assert number_of_configured_smartboxes == MAX_NUMBER_OF_SMARTBOXES_PER_STATION
