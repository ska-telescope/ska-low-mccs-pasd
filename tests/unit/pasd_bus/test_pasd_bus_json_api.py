# -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Tests of the PasdBusSimulatorApi."""
from __future__ import annotations

import json
from typing import Dict
from unittest import mock

import pytest

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusJsonApi,
    PasdBusSimulator,
    SmartboxSimulator,
)


class TestPasdBusJsonApi:
    """Tests of the PaSD bus JSON-based API."""

    @pytest.fixture(name="backend_pasd_bus")
    def backend_pasd_bus_fixture(
        self: TestPasdBusJsonApi,
        pasd_bus_simulator: PasdBusSimulator,
    ) -> mock.Mock:
        """
        Return a mock backend to test the API against.

        :param pasd_bus_simulator: a PasdBusSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock with the same interface.

        :return: a mock backend to test the API against.
        """
        backend_pasd_bus = mock.create_autospec(
            pasd_bus_simulator,
            spec_set=True,
            instance=True,
        )
        return backend_pasd_bus

    @pytest.fixture(name="backend_fndh")
    def backend_fndh_fixture(
        self: TestPasdBusJsonApi, pasd_bus_simulator: PasdBusSimulator
    ) -> mock.Mock:
        """
        Return a mock backend FNDH to test the API against.

        :param pasd_bus_simulator: a PasdBusSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock
            with the same interface as its FNDH.

        :return: a mock backend to test the API against.
        """
        backend_fndh = mock.create_autospec(
            pasd_bus_simulator.get_fndh(),
            spec_set=True,
            instance=True,
            fncb_temperature=4150,
        )
        backend_fndh.set_led_pattern.return_value = True
        backend_fndh.turn_port_off.side_effect = ValueError("Mock error")
        return backend_fndh

    @pytest.fixture(name="backend_smartboxes")
    def backend_smartboxes_fixture(self: TestPasdBusJsonApi) -> Dict[int, mock.Mock]:
        """
        Return a dictionary of mock backend smartboxes to test the API against.

        :return: mock backends to test the API against.
        """
        backend_smartbox = mock.create_autospec(
            SmartboxSimulator(),
            spec_set=True,
            instance=True,
            input_voltage=4800,
        )
        return {i: backend_smartbox for i in range(1, 4)}

    @pytest.fixture(name="encoding")
    def encoding_fixture(
        self: TestPasdBusJsonApi,
    ) -> str:
        """
        Return the encoding to use when converting between string and bytes.

        :return: the encoding to use when converting between string and
            bytes.
        """
        return "utf-8"

    @pytest.fixture(name="api")
    def api_fixture(
        self: TestPasdBusJsonApi,
        backend_fndh: mock.Mock,
        backend_smartboxes: Dict[int, mock.Mock],
        encoding: str,
    ) -> PasdBusJsonApi:
        """
        Return an API instance against which to test.

        :param backend_fndh: a mock backend FNDH for the API to front.
        :param backend_smartboxes: dictionary of mock backend smartboxes for
            the API to front.
        :param encoding: the encoding to use when converting between string
            and bytes

        :return: an API instance against which to test
        """
        backend_mocks: Dict[int, FndhSimulator | SmartboxSimulator] = {0: backend_fndh}
        backend_mocks.update(backend_smartboxes)
        return PasdBusJsonApi(backend_mocks, encoding)

    def test_nonjson(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of a request with non-JSON.

        The expected response looks like:

        .. code-block:: json

            {
                "error": {
                    "code": "decode",
                    "detail": "Error message from JSONDecodeError",
                },
                "timestamp": "2023-04-05T05:33:26.730023",
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request_str = "{ This isn't valid json."
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["error"]["code"] == "decode"

    def test_schema_error(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of a request with valid JSON that doesn't validate.

        The expected response looks like:

        .. code-block: json::

            {
                "error": {
                    "code": "schema",
                    "detail": "Error message from JSONValidationError",
                },
                "timestamp": "2023-04-05T05:33:26.730023",
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        # Without a device ID, this won't validate
        request = {"read": ["nonexistent_attribute"]}
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["error"]["code"] == "schema"

    def test_read_nonexistent_attribute(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of an attribute read request for a nonexistent attribute.

        The expected response looks like:

        .. code-block: json::

            {
                "error": {
                    "code": "attribute",
                    "detail": "Attribute 'nonexistent_attribute' does not exist",
                },
                "timestamp": "2023-04-05T05:33:26.730023",
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request = {"device_id": 0, "read": ["nonexistent_attribute"]}
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["error"]["code"] == "attribute"
        assert (
            response["error"]["detail"]
            == "Attribute 'nonexistent_attribute' does not exist"
        )

    def test_read_unresponsive_device(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of an attribute read request from a nonexistent device.

        The expected response looks like:

        .. code-block: json::

            {
                "error": {
                    "code": "device",
                    "detail": "Device 10 is unresponsive",
                },
                "timestamp": "2023-04-05T05:33:26.730023",
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request = {"device_id": 10, "read": ["input_voltage"]}
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        print(response)
        assert response["error"]["code"] == "device"
        assert response["error"]["detail"] == "Device 10 is unresponsive"

    def test_read_attribute(
        self: TestPasdBusJsonApi,
        api: PasdBusJsonApi,
        encoding: str,
        backend_fndh: mock.Mock,
    ) -> None:
        """
        Test handling of an attribute read request for an attribute.

        The expected response looks like:

        .. code-block: json::

            {
                "source": 0,
                "data":
                {
                    "type": "reads",
                    "attributes":
                    {
                        "fncb_temperature": 4150,
                    }
                },
                "timestamp": "2023-04-05T05:33:26.730023",
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        :param backend_fndh: a mock backend FNDH for this command to execute
            against.
        """
        request = {"device_id": 0, "read": ["fncb_temperature"]}
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["source"] == 0
        assert response["data"]["type"] == "reads"
        assert (
            response["data"]["attributes"]["fncb_temperature"]
            == backend_fndh.fncb_temperature
        )

    def test_execute_nonexistent_command(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of an execution request for a nonexistent command.

        The expected response looks like:

        .. code-block: json::

            {
                'source': 0,
                'error': {
                    'code': 'attribute',
                    'detail': "Command 'nonexistent_command' does not exist",
                },
                'timestamp': '2023-04-05T05:45:22.430058',
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request = {
            "device_id": 0,
            "execute": "nonexistent_command",
            "arguments": [],
        }
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["source"] == 0
        assert response["error"]["code"] == "attribute"
        assert (
            response["error"]["detail"]
            == "Command 'nonexistent_command' does not exist"
        )

    def test_execute_error_command(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of an execution request for a command that errors.

        The expected response looks like:

        .. code-block: json::

            {
                'source': 0,
                'error': {
                    'code': 'command',
                    'detail': "Exception in command 'turn_port_off': Mock error.",
                },
                'timestamp': '2023-04-05T05:45:22.430058',
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request = {
            "device_id": 0,
            "execute": "turn_port_off",
            "arguments": [2],
        }
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["source"] == 0
        assert response["error"]["code"] == "command"
        assert (
            response["error"]["detail"]
            == "Exception in command 'turn_port_off': Mock error."
        )

    def test_execute_command(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of a command execution request.

        The expected response looks like:

        .. code-block: json::

            {
                'source': 0,
                'data': [
                    {
                        'type': 'command_result',
                        'attributes': {
                            'result': True
                        }
                    }
                ],
                'timestamp': '2023-04-05T05:57:43.049469'
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request = {
            "device_id": 0,
            "execute": "set_led_pattern",
            "arguments": ["SERVICE"],
        }
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["source"] == 0
        assert response["data"]["type"] == "command_result"
        assert response["data"]["attributes"]["set_led_pattern"] is True
