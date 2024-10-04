# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS SmartBox module."""
from __future__ import annotations

import json
import unittest.mock
from typing import Any

import pytest
import tango
from ska_control_model import ResultCode
from ska_low_mccs_common.testing.mock import MockDeviceBuilder

from ska_low_mccs_pasd import PasdData


@pytest.fixture(name="smartbox_number")
def smartbox_number_fixture() -> int:
    """
    Return the logical number assigned to this smartbox.

    :return: the logical number of the smartbox under test.
    """
    return 18


@pytest.fixture(name="mocked_initial_port_power_state")
def mocked_initial_port_power_state_fixture() -> bool:
    """
    Return the initial power state of the FNDH port.

    :return: the initial power state. True if ON.
    """
    return True


@pytest.fixture(name="fndh_port")
def fndh_port_fixture() -> int:
    """
    Return the fndh port the smartbox is attached to.

    :return: the fndh port this smartbox is attached.
    """
    return 2


@pytest.fixture(name="changed_fndh_port")
def changed_fndh_port_fixture() -> int:
    """
    Return the fndh port the smartbox is attached to.

    :return: the fndh port this smartbox is attached.
    """
    return 1


@pytest.fixture(name="mocked_initial_smartbox_ports")
def mocked_initial_smartbox_ports_fixture(
    mocked_initial_port_power_state: bool,
    fndh_port: int,
) -> list[bool]:
    """
    Return the initial power states of the FNDH ports.

    :param fndh_port: the FNDH port this smartbox is attached to.
    :param mocked_initial_port_power_state: the initial power state of
        the port the smartbox is attached to.

    :return: a list containing the smartbox port powers.
    """
    initial_port_power_sensed: list[bool] = [False] * 28
    initial_port_power_sensed[fndh_port - 1] = mocked_initial_port_power_state
    return initial_port_power_sensed


@pytest.fixture(name="mock_pasdbus")
def mock_pasdbus_fixture(
    mocked_initial_smartbox_ports: list[bool],
    smartbox_number: int,
) -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsPaSDBus device.

    :param mocked_initial_smartbox_ports: the initial power state of
        the port the smartbox is attached to.
    :param smartbox_number: The logical id given of the smartbox.

    :return: a mock MccsPaSDBus device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_command("GetPasdDeviceSubscriptions", {})

    builder.add_attribute("fndhPortsPowerSensed", mocked_initial_smartbox_ports)
    builder.add_attribute(f"smartbox{smartbox_number}PortsPowerSensed", [True] * 12)
    builder.add_command(
        "GetPasdDeviceSubscriptions", [f"smartbox{smartbox_number}PortsPowerSensed"]
    )
    builder.add_result_command("SetSmartboxPortPowers", ResultCode.OK)
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    return builder()


@pytest.fixture(name="input_smartbox_mapping")
def input_smartbox_mapping_fixture(
    smartbox_number: int, fndh_port: int
) -> dict[str, Any]:
    """
    Fixture providing a made up smartboxMapping in FieldStation.

    :param smartbox_number: The logical id given to this smartbox.
    :param fndh_port: The port under test.

    :returns: the smartboxMapping.
    """
    smartbox_mapping: dict = {}
    for fndh_port_idx in range(1, PasdData.NUMBER_OF_FNDH_PORTS + 1):
        smartbox_mapping[f"sb{fndh_port_idx:02d}"] = fndh_port_idx

    # The smartbox under test is attached to the port
    # given by fixture fndh_port!!
    smartbox_mapping[f"sb{smartbox_number:02d}"] = fndh_port

    return {"smartboxMapping": smartbox_mapping}


@pytest.fixture(name="mock_field_station")
def mock_field_station_fixture(
    input_smartbox_mapping: dict[str, Any]
) -> unittest.mock.Mock:
    """
    Fixture that provides a mock FieldStation device.

    :param input_smartbox_mapping: the mocked smartboxMapping
        attribute value.

    :return: a mock FieldStation device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_attribute("smartboxMapping", json.dumps(input_smartbox_mapping))
    return builder()
