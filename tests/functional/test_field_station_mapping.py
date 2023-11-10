# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple test of the MCCS FNDH Tango device."""
from __future__ import annotations

import gc
import json
from typing import Any, Callable, Final

import jsonschema
import tango
from pytest_bdd import given, parsers, scenario, then, when
from ska_control_model import AdminMode

gc.disable()


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
                "required": ["antennaID", "smartboxID", "smartboxPort"],
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
                "required": ["antennaID", "maskingState"],
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
                "required": ["smartboxID", "fndhPort"],
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


@when("we check the antennaMapping", target_fixture="maps")
def check_port_mapping(
    field_station_device: tango.DeviceProxy,
) -> dict[str, dict[Any, Any]]:
    """
    Ask for the port mapping.

    :param field_station_device: a proxy to the field station device.

    :return: the antenna mapping reported by the field station.
    """
    return {
        "antenna_map": json.loads(field_station_device.antennaMapping),
        "smartbox_map": json.loads(field_station_device.smartboxMapping),
        "antenna_mask": json.loads(field_station_device.antennaMask),
    }


@then("we get a valid mapping")
def check_the_mapping_is_valid(maps: dict[str, dict]) -> None:
    """
    Check that the mapping passes the validation.

    :param maps: the antenna mapping as reported
        by the FieldStation.
    """
    # Validate against the
    jsonschema.validate(maps["antenna_map"], ANTENNA_MAPPING_SCHEMA)

    jsonschema.validate(maps["smartbox_map"], SMARTBOX_MAPPING_SCHEMA)

    jsonschema.validate(maps["antenna_mask"], ANTENNA_MASK_SCHEMA)
