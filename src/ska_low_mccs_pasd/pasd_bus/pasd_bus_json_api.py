# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a JSON API to the PaSD bus."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Final

import jsonschema
from ska_ser_devices.client_server import ApplicationClient, ApplicationClientSession

from .pasd_bus_simulator import FndhSimulator, SmartboxSimulator


# pylint: disable=too-few-public-methods
class PasdBusJsonApi:
    """A JSON-based API for a PaSD bus simulator."""

    # This schema is loosely adapted from jsonapi.org.
    REQUEST_SCHEMA: Final = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://skao.int/Pasd.json",
        "title": "PaSD bus simulator JSON API",
        "description": "Temporary JSON API for PaSD bus simulator",
        "type": "object",
        "oneOf": [
            {
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
                    "read": {
                        "description": "List of attributes to read",
                        "type": "array",
                        "items": {
                            "description": "Name of an attribute to read",
                            "type": "string",
                        },
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                },
                "additionalProperties": False,
                "required": ["device_id", "read"],
            },
            {
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
                    "execute": {
                        "description": "Name of the command to execute",
                        "type": "string",
                    },
                    "arguments": {
                        "description": "Arguments to the command",
                        "type": "array",
                    },
                },
                "additionalProperties": False,
                "required": ["device_id", "execute"],
            },
        ],
    }

    def __init__(
        self,
        simulators: Dict[int, FndhSimulator | SmartboxSimulator],
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialise a new instance.

        :param simulators: sequence of smartbox simulators that this API
            fronts.
        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self._simulators = simulators
        self._encoding = encoding

    def _handle_read_attributes(self, device_id: int, names: str) -> dict:
        attributes: dict[str, Any] = {}
        for name in names:
            try:
                # TODO: Not sure how API should handle "unresponsive" smartbox
                value = getattr(self._simulators[device_id], name)
            except AttributeError:
                return {
                    "source": device_id,
                    "error": {
                        "code": "attribute",
                        "detail": f"Attribute '{name}' does not exist",
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            except KeyError:
                return {
                    "source": device_id,
                    "error": {
                        "code": "device",
                        "detail": f"Device {device_id} is unresponsive",
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            attributes[name] = value
        return {
            "source": device_id,
            "data": {"type": "reads", "attributes": attributes},
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _handle_command(self, device_id: int, name: str, args: tuple) -> dict:
        try:
            # TODO: Not sure how API should handle "unresponsive" smartbox
            command = getattr(self._simulators[device_id], name)
        except AttributeError:
            response: dict[str, Any] = {
                "source": device_id,
                "error": {
                    "code": "attribute",
                    "detail": f"Command '{name}' does not exist",
                },
            }
        except KeyError:
            response = {
                "source": device_id,
                "error": {
                    "code": "device",
                    "detail": f"Device {device_id} is unresponsive",
                },
            }
        else:
            try:
                result = command(*args)
            except Exception as error:  # pylint: disable=broad-exception-caught
                response = {
                    "source": device_id,
                    "error": {
                        "code": "command",
                        "detail": f"Exception in command '{name}': {str(error)}.",
                    },
                }
            else:
                response = {
                    "source": device_id,
                    "data": {
                        "type": "command_result",
                        "attributes": {name: result},
                    },
                }
        response["timestamp"] = datetime.utcnow().isoformat()
        return response

    def _handle_no_match(self, request: dict) -> dict:
        return {  # pragma: no cover
            # "no cover" because this should be unreachable
            # if our schema is specific enough
            "error": {
                "code": "request",
                "detail": f"No match for request '{json.dumps(request)}'",
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _handle_request(self, request: dict) -> dict:
        match request:
            case {"device_id": device_id, "read": attr_names}:
                return self._handle_read_attributes(device_id, attr_names)
            case {"device_id": device_id, "execute": name, "arguments": args}:
                return self._handle_command(device_id, name, args)
            case _:  # pragma: no cover
                # "no cover" because this should be unreachable
                # if our schema is specific enough
                return self._handle_no_match(request)

    def _handle_json(self, json_request: str) -> str:
        try:
            request = json.loads(json_request)
        except json.JSONDecodeError as error:
            response = {
                "error": {
                    "code": "decode",
                    "detail": error.msg,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
            return json.dumps(response)

        try:
            jsonschema.validate(request, self.REQUEST_SCHEMA)
        except jsonschema.ValidationError as error:
            response = {
                "error": {
                    "code": "schema",
                    "detail": error.message,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
            return json.dumps(response)

        response = self._handle_request(request)
        return json.dumps(response)

    def __call__(self, json_request_bytes: bytes) -> bytes:
        """
        Call this API object with a new JSON request, encoded as bytes.

        :param json_request_bytes: the JSON-encoded request string,
            encoded as bytes.

        :return: a JSON-encoded response string, encoded as bytes.
        """
        json_request_str = json_request_bytes.decode(self._encoding)
        json_response_str = self._handle_json(json_request_str)
        return json_response_str.encode(self._encoding)


class PasdBusJsonApiClient:
    """A client class for a PaSD bus simulator with a JSON API."""

    def __init__(
        self: PasdBusJsonApiClient,
        application_client: ApplicationClient[bytes, bytes],
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialise a new instance.

        :param application_client: the underlying application client,
            used for communication with the server.
        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self._application_client = application_client
        self._encoding = encoding

        self._session: ApplicationClientSession[bytes, bytes] | None = None

    def connect(self) -> None:
        """
        Establish a connection to the remote API.

        This JSON-based API is connectionless:
        a new connection is established for each request-response transaction.
        Therefore this method does nothing.
        """
        self._session = self._application_client.connect()

    def close(self) -> None:
        """
        Close the connection to the remote API.

        This JSON-based API is connectionless:
        a new connection is established for each request-response transaction.
        Therefore this method does nothing.
        """
        if self._session is not None:
            self._session.close()
            self._session = None

    def _do_request(self, request: dict) -> dict:
        if self._session is None:
            raise ConnectionError("A session is not established.")

        request_str = json.dumps(request)
        request_bytes = request_str.encode(self._encoding)
        response_bytes = self._session.send_receive(request_bytes)
        response_str = response_bytes.decode(self._encoding)
        response = json.loads(response_str)
        return response

    def read_attributes(self, device_id: int, *names: str) -> dict[str, Any]:
        """
        Read attribute values from the server.

        :param device_id: id of the device to be read from.
        :param names: names of the attributes to be read.

        :return: dictionary of attribute values keyed by name
        """
        response = self._do_request({"device_id": device_id, "read": names})
        if "data" in response:
            assert response["source"] == device_id
            assert response["data"]["type"] == "reads"
            return response["data"]["attributes"]
        return response

    # pylint: disable=unused-argument
    def write_attribute(
        self, device_id: int, name: str, *values: Any
    ) -> dict[str, Any]:
        """
        Write a new attribute value.

        :param device_id: id of the device to write to.
        :param: name: attribute name to write.
        :param: values: new value(s).

        :return: dictionary mapping attribute name to new value.
        """
        # Placeholder function until tests have moved over to
        # Modbus API
        return {}

    def execute_command(self, device_id: int, name: str, *args: Any) -> dict[str, Any]:
        """
        Execute a command and return the results.

        :param device_id: ID of the device to be commanded.
        :param name: name of the command.
        :param args: positional arguments to the command.

        :return: the results of the command execution.
        """
        response = self._do_request(
            {"device_id": device_id, "execute": name, "arguments": args}
        )
        if "data" in response:
            assert response["source"] == device_id
            assert response["data"]["type"] == "command_result"
            return response["data"]["attributes"]
        return response
