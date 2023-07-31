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
import unittest
from typing import Sequence

import pytest

from ska_low_mccs_pasd.pasd_bus import PasdBusJsonApi, PasdBusSimulator


class TestPasdBusJsonApi:
    """Tests of the PaSD bus JSON-based API."""

    @pytest.fixture(name="backend_pasd_bus")
    def backend_pasd_bus_fixture(
        self: TestPasdBusJsonApi,
        pasd_bus_simulator: PasdBusSimulator,
    ) -> unittest.mock.Mock:
        """
        Return a mock backend to test the API against.

        :param pasd_bus_simulator: a PasdBusSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock with the same interface.

        :return: a mock backend to test the API against.
        """
        mock = unittest.mock.create_autospec(
            pasd_bus_simulator,
            spec_set=True,
            instance=True,
        )
        return mock

    @pytest.fixture(name="backend_fndh")
    def backend_fndh_fixture(
        self: TestPasdBusJsonApi, pasd_bus_simulator: PasdBusSimulator
    ) -> unittest.mock.Mock:
        """
        Return a mock backend FNDH to test the API against.

        :param pasd_bus_simulator: a PasdBusSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock
            with the same interface as its FNDH.

        :return: a mock backend to test the API against.
        """
        mock = unittest.mock.create_autospec(
            pasd_bus_simulator.get_fndh(),
            spec_set=True,
            instance=True,
            fncb_temperature=40.0,
        )
        mock.set_led_pattern.return_value = True
        mock.reset_port_breaker.side_effect = ValueError("Mock error")
        return mock

    @pytest.fixture(name="backend_smartboxes")
    def backend_smartboxes_fixture(
        self: TestPasdBusJsonApi,
    ) -> Sequence[unittest.mock.Mock]:
        """
        Return a sequence of mock backend smartboxes to test the API against.

        :return: mock backends to test the API against.
        """
        return [unittest.mock.Mock() for _ in range(25)]

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
        backend_fndh: unittest.mock.Mock,
        backend_smartboxes: Sequence[unittest.mock.Mock],
        encoding: str,
    ) -> PasdBusJsonApi:
        """
        Return an API instance against which to test.

        :param backend_fndh: a mock backend FNDH for the API to front.
        :param backend_smartboxes: sequence of mock backend smartboxes for
            the API to front.
        :param encoding: the encoding to use when converting between string
            and bytes

        :return: an API instance against which to test
        """
        return PasdBusJsonApi([backend_fndh] + list(backend_smartboxes), encoding)

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

    def test_read_attribute(
        self: TestPasdBusJsonApi,
        api: PasdBusJsonApi,
        encoding: str,
        backend_fndh: unittest.mock.Mock,
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
        assert response["data"]["attributes"]["fncb_temperature"] == pytest.approx(
            backend_fndh.fncb_temperature
        )

    def test_execute_nonexistent_command(
        self: TestPasdBusJsonApi, api: PasdBusJsonApi, encoding: str
    ) -> None:
        """
        Test handling of an execution request for a nonexistent command.

        The expected response looks like:

        .. code-block: json::

            {
                'error': {
                    'source': 0,
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
        assert response["error"]["source"] == 0
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
                'error': {
                    'source': 0,
                    'code': 'command',
                    'detail': "Exception in command 'reset_port_breaker': Mock error.",
                },
                'timestamp': '2023-04-05T05:45:22.430058',
            }

        :param api: the API under test
        :param encoding: the encoding to use when converting between string
            and bytes
        """
        request = {
            "device_id": 0,
            "execute": "reset_port_breaker",
            "arguments": [2],
        }
        request_str = json.dumps(request)
        request_bytes = request_str.encode(encoding)
        response_bytes = api(request_bytes)
        response_str = response_bytes.decode(encoding)
        response = json.loads(response_str)
        assert response["error"]["source"] == 0
        assert response["error"]["code"] == "command"
        assert (
            response["error"]["detail"]
            == "Exception in command 'reset_port_breaker': Mock error."
        )

    def test_execute_command(
        self: TestPasdBusJsonApi,
        api: PasdBusJsonApi,
        encoding: str,
        backend_fndh: unittest.mock.Mock,
    ) -> None:
        """
        Test handling of a command execution request.

        The expected response looks like:

        .. code-block: json::

            {
                'data': [
                    {
                        'source': 0,
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
        :param backend_fndh: a mock backend FNDH for this command to execute
            against.
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
        assert response["data"]["source"] == 0
        assert response["data"]["type"] == "command_result"
        assert response["data"]["attributes"]["set_led_pattern"] is True
