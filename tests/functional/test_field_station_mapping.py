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
from typing import Any, Callable, Final

import jsonschema
import tango
from pytest_bdd import given, parsers, scenario, then, when
from ska_control_model import AdminMode

gc.disable()

NUMBER_OF_SMARTBOX = 24

ANTENNA_MAPPING_SCHEMA: Final = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://skao.int/UpdateAntennaMapping.json",
    "title": "MccsFieldStation UpdateAntennaMapping schema",
    "description": "Schema for MccsFieldStation's UpdateAntennaMapping command",
    "type": "object",
    "properties": {
        "antennaMapping": {
            "type": "array",
            "minItems": 256,
            "maxItems": 256,
            "items": {
                "type": "object",
                "properties": {
                    "antennaID": {"type": "integer"},
                    "smartboxID": {"type": "integer"},
                    "smartboxPort": {"type": "integer"},
                },
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
            "type": "array",
            "minItems": 256,
            "maxItems": 256,
            "items": {
                "type": "object",
                "properties": {
                    "antennaID": {"type": "integer"},
                    "maskingState": {"type": "boolean"},
                },
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
            "type": "array",
            "minItems": 24,
            "maxItems": 24,
            "items": {
                "type": "object",
                "properties": {
                    "smartboxID": {"type": "integer"},
                    "fndhPort": {"type": "integer"},
                },
            },
        }
    },
    "required": ["smartboxMapping"],
}


@scenario(
    "features/field_station_mapping.feature",
    "field station initialises with valid mapping",
)
def test_field_station() -> None:
    """
    Test that the fieldstation initialised with a mapping.

    This will test that the fieldstation can contact the configuration
    server, get the configMap and load it into the FieldStation
    succesfully.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given(parsers.parse("A {device_ref} which is ready"))
def get_ready_device(device_ref: str, set_device_state: Callable) -> None:
    """
    Get device in state ON and adminmode ONLINE.

    :param device_ref: Gherkin reference to device under test.
    :param set_device_state: function to set device state.
    """
    print(f"Setting device {device_ref} ready...")
    set_device_state(device_ref, state=tango.DevState.ON, mode=AdminMode.ONLINE)


@given("PasdBus is initialised")
def pasd_is_initialised(pasd_bus_device: tango.DeviceProxy) -> None:
    """
    Get PaSD devices initialised.

    :param pasd_bus_device: A `tango.DeviceProxy` to the PaSD
        device.
    """
    pasd_bus_device.initializefndh()
    for i in range(1, NUMBER_OF_SMARTBOX + 1):
        pasd_bus_device.initializesmartbox(i)


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
        )


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
        if "smartboxID" in smartbox_config:
            number_of_configured_smartboxes += 1
    if is_true_context:
        # Currently the store if configured with the deployed configuration from
        # helm. We check that for the devices deployed we have a configuration.
        assert number_of_configured_smartboxes == len(smartboxes_under_test)
    else:
        # We have mocked the store with a configuration for all 24 smartbox
        assert number_of_configured_smartboxes == NUMBER_OF_SMARTBOX
