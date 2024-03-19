
# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a JSON API to testing interface to the PaSD simulators."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Final

import jsonschema

class SimulatorInterfaceAPI:
    """A JSON-based API for a PaSD bus simulator."""

    # This schema is loosely adapted from jsonapi.org.
    REQUEST_SCHEMA: Final = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://skao.int/Pasd.json",
        "title": "JSON API to interface directly with simulators.",
        "description": "JSON API to allow write operations on read-only parameters on the PaSD simulators",
        "type": "object",
        "properties": {
            "device_id": {
                "description": (
                    "ID of the PaSD device being addressed. "
                    "The FNDH has device ID 0. "
                    "All other device IDs refer to a smartbox."
                ),
                "type": "integer",
                "minimum": 0,
                "maximum": 24,
            },
            "attribute": {
                "description": "Name of the attribute to write",
                "type": "string",
            },
            "value": {
                "description": "Value of the attribute",
                "oneOf": [{"type": "array"}, {"type": "number"}]
            },
        },
        "additionalProperties": False,
        "required": ["device_id", "attribute", "value"],
    }

    def __init__(
        self,
        handle_json: Callable[[dict], str],
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialise a new instance.

        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self._encoding = encoding
        self._handle_json = handle_json


    def __call__(self, json_request_bytes: bytes) -> bytes:
        """
        Call this API object with a new JSON request, encoded as bytes.

        :param json_request_bytes: the JSON-encoded request string,
            encoded as bytes.

        :return: a JSON-encoded response string, encoded as bytes.
        """
        json_request_str = json_request_bytes.decode(self._encoding)
        json_request = json.loads(json_request_str)

        try:
            jsonschema.validate(json_request, self.REQUEST_SCHEMA)
        except jsonschema.ValidationError as error:
            response = {
                "error": {
                    "code": "schema",
                    "detail": error.message,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
            return json.dumps(response)

        json_response_str: str = self._handle_json(json_request)
        return json_response_str.encode(self._encoding)