# -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Tests of the PasdBusSimulatorApi."""
import json
import unittest

import pytest

from ska_low_mccs_pasd.pasd_bus import PasdBusJsonApi, PasdBusSimulator


@pytest.fixture(name="backend")
def backend_fixture(pasd_bus_simulator: PasdBusSimulator) -> unittest.mock.Mock:
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
        fndh_outside_temperature=40.0,
    )
    mock.reset_antenna_breaker.side_effect = ValueError("Mock error")
    mock.turn_antenna_on.return_value = True

    return mock


@pytest.fixture(name="encoding")
def encoding_fixture() -> str:
    """
    Return the encoding to use when converting between string and bytes.

    :return: the encoding to use when converting between string and
         bytes.
    """
    return "utf-8"


@pytest.fixture(name="api")
def api_fixture(
    backend: unittest.mock.Mock,
    encoding: str,
) -> PasdBusJsonApi:
    """
    Return an API instance against which to test.

    :param backend: a mock backend
    :param encoding: the encoding to use when converting between string
        and bytes

    :return: an API instance against which to test
    """
    return PasdBusJsonApi(backend, encoding)


def test_nonjson(api: PasdBusJsonApi, encoding: str) -> None:
    """
    Test handling of a request with non-JSON.

    :param api: the API under test
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request_str = "{ This isn't valid json."
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["status"] == "error"
    assert response["error"] == "decode"


def test_schema_error(api: PasdBusJsonApi, encoding: str) -> None:
    """
    Test handling of a request with valid JSON that doesn't validate.

    :param api: the API under test
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request = "This is valid JSON but it doesn't validate."
    request_str = json.dumps(request)
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["status"] == "error"
    assert response["error"] == "schema"


def test_read_nonexistent_attribute(api: PasdBusJsonApi, encoding: str) -> None:
    """
    Test handling of an attribute read request for a nonexistent attribute.

    :param api: the API under test
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request = {"read": "nonexistent_attribute"}
    request_str = json.dumps(request)
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["status"] == "error"
    assert response["error"] == "attribute"


def test_read_attribute(
    api: PasdBusJsonApi,
    backend: unittest.mock.Mock,
    encoding: str,
) -> None:
    """
    Test handling of an attribute read request for a nonexistent attribute.

    :param api: the API under test
    :param backend: a mock backend
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request = {"read": "fndh_outside_temperature"}
    request_str = json.dumps(request)
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["attribute"] == "fndh_outside_temperature"
    assert response["value"] == pytest.approx(backend.fndh_outside_temperature)


def test_execute_nonexistent_command(api: PasdBusJsonApi, encoding: str) -> None:
    """
    Test handling of an execution request for a nonexistent command.

    :param api: the API under test
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request = {"execute": "nonexistent_command", "arguments": []}
    request_str = json.dumps(request)
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["status"] == "error"
    assert response["error"] == "attribute"


def test_execute_error_command(api: PasdBusJsonApi, encoding: str) -> None:
    """
    Test handling of an execution request for a command that errors.

    :param api: the API under test
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request = {"execute": "reset_antenna_breaker", "arguments": [1000000]}
    request_str = json.dumps(request)
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["status"] == "error"
    assert response["error"] == "command"


def test_execute_command(
    api: PasdBusJsonApi,
    encoding: str,
) -> None:
    """
    Test handling of a command execution request.

    :param api: the API under test
    :param encoding: the encoding to use when converting between string
        and bytes
    """
    request = {"execute": "turn_antenna_on", "arguments": [5]}
    request_str = json.dumps(request)
    request_bytes = request_str.encode(encoding)
    response_bytes = api(request_bytes)
    response_str = response_bytes.decode(encoding)
    response = json.loads(response_str)
    assert response["command"] == "turn_antenna_on"
    assert response["result"] is True
