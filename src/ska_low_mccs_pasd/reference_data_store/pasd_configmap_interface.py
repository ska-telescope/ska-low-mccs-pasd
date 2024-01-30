# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a JSON API to the Pasd Configuration."""
from __future__ import annotations

import importlib.resources
import json
import logging
import time
from datetime import datetime
from typing import Any, Final, Optional

import jsonschema
import yaml
from kubernetes import config, dynamic
from kubernetes.client import api_client
from ska_ser_devices.client_server import ApplicationClient, ApplicationClientSession


class ConfigMapManager:
    """A class that manages access to a configMap."""

    def __init__(
        self: ConfigMapManager,
        name: str,
        namespace: str,
        label_selector: str,
    ) -> None:
        """
        Manage read requests to a ConfigMap.

        :param name: The name of the configmap to manage.
        :param namespace: The namespace the configmap resides
        :param label_selector: a string with a key/value pair
            e.g. "findme=true"
        """
        self._configmap_name = name
        self._configmap_namespace = namespace
        self._configmap_label = label_selector
        self.api = None

    def connect(self) -> None:
        """Connect to the kubernetes API from inside cluster."""
        client = dynamic.DynamicClient(
            api_client.ApiClient(configuration=config.load_incluster_config())
        )

        # fetching the configmap api
        self.api = client.resources.get(api_version="v1", kind="ConfigMap")

    def read_data(self) -> dict:
        """
        Read the data from the configmap.

        :returns: a empty dictionary if unsuccessful
            or a dictionary containing data from configMap.
        """
        assert self.api is not None

        configmap_list = self.api.get(
            name=self._configmap_name,
            namespace=self._configmap_namespace,
            label_selector=self._configmap_label,
        )
        config_data = configmap_list.data
        for _, data_yaml in config_data.items():
            data = yaml.safe_load(data_yaml)
        return data


# pylint: disable=too-few-public-methods
class PasdConfigurationInterface:
    """A JSON-based API for interfacing with a configmap."""

    # This schema is loosely adapted from jsonapi.org.
    REQUEST_SCHEMA: Final = json.loads(
        importlib.resources.read_text(
            "ska_low_mccs_pasd.reference_data_store.schemas",
            "MccsPasdConfiguration_request.json",
        )
    )

    def __init__(
        self,
        logger: logging.Logger,
        station_name: str,
        namespace: str,
        _config_manager: Optional[Any] = None,
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialise a new instance.

        :param logger: an injected logger for information.
        :param station_name: the station name used to locate the configmap.
        :param namespace: the namespace of the configMap.
        :param _config_manager: _config_manager to use for testing.
        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self.logger = logger
        self._station_name = station_name
        self._encoding = encoding
        self.configmanager = _config_manager or ConfigMapManager(
            name=f"pasd-configuration-{station_name}",
            namespace=namespace,
            label_selector="findme=configmap-to-watch",
        )

    def _handle_read_attributes(self, station_name: str) -> dict:
        value: Any = {}
        try:
            self.logger.info(f"station name requesting {station_name} ...")
            # Only a specific station has permission to access its configuration.
            if not self._station_name == station_name:
                self.logger.warning(f"access refused to station {self._station_name}")
                raise PermissionError(
                    f"only {self._station_name}",
                    "has permission to access configuration.",
                )

            self.logger.info(f"access granted to {self._station_name}")
            # Connect to the kubernetes API and read configmap data.
            self.configmanager.connect()
            value = self.configmanager.read_data()

        except PermissionError:
            return {
                "error": {
                    "code": "permission",
                    "detail": f"Only '{self._station_name}' has read permission",
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:  # pylint: disable=broad-exception-caught
            return {
                "error": {
                    "code": f"Unknown {e}",
                    "detail": "Unknown Exception raised when attempting a read.",
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
        return {
            "data": {"type": "reads", "attributes": value},
            "timestamp": datetime.utcnow().isoformat(),
        }

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
            case {"read": station_name}:
                return self._handle_read_attributes(station_name)
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


class PasdConfigurationJsonApiClient:
    """A client class for interfacing with Pasd Configuration using a JSON API."""

    def __init__(
        self: PasdConfigurationJsonApiClient,
        logger: logging.Logger,
        application_client: ApplicationClient[bytes, bytes],
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialise a new instance.

        :param logger: an injected logger.
        :param application_client: the underlying application client,
            used for communication with the server.
        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self._application_client = application_client
        self._encoding = encoding
        self.logger = logger
        self._session: ApplicationClientSession[bytes, bytes] | None = None

    def connect(self, number_of_attempts: int, wait_time: int) -> None:
        """
        Establish a connection to the remote API.

        This JSON-based API is connectionless:
        a new connection is established for each request-response transaction.
        Therefore this method does nothing.

        :param number_of_attempts: number of attempt to connect
        :param wait_time: the time to wait between attempting a
            connection.

        """
        if number_of_attempts == 1:
            self._session = self._application_client.connect()
        else:
            try:
                self._session = self._application_client.connect()
            except ConnectionRefusedError as e:
                time.sleep(wait_time)
                self.logger.error(f"Connection refused {e}, retrying...")
                self.connect(number_of_attempts - 1, wait_time)
            except Exception as e:  # pylint: disable=broad-exception-caught
                time.sleep(wait_time)
                self.logger.error(f"Uncaught exception {repr(e)}, retrying...")
                self.connect(number_of_attempts - 1, wait_time)

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

    def read_attributes(self, station_name: str) -> dict[str, Any]:
        """
        Read attribute values from the server.

        :param station_name: The name of the station requesting.

        :return: dictionary of attribute values keyed by name
        """
        response = self._do_request({"read": station_name})
        if "data" in response:
            assert response["data"]["type"] == "reads"
            return response["data"]["attributes"]
        return response
