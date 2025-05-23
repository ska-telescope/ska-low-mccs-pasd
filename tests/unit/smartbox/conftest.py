# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS SmartBox module."""
from __future__ import annotations

import unittest.mock

import pytest
import tango
from ska_control_model import ResultCode
from ska_low_mccs_common.testing.mock import MockDeviceBuilder


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
    return 1


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
