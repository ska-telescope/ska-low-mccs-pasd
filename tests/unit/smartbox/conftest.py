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
from ska_control_model import PowerState, ResultCode
from ska_low_mccs_common.testing.mock import MockDeviceBuilder


@pytest.fixture(name="smartbox_number")
def smartbox_number_fixture() -> int:
    """
    Return the logical number assigned to this smartbox.

    :return: the logical number of the smartbox under test.
    """
    return 1


@pytest.fixture(name="mocked_initial_port_power_state")
def mocked_initial_port_power_state_fixture() -> PowerState:
    """
    Return the initial power state of the FNDH port.

    :return: the initial power state.
    """
    return PowerState.ON


@pytest.fixture(name="fndh_port")
def fndh_port_fixture() -> int:
    """
    Return the fndh port the smartbox is attached to.

    :return: the fndh port this smartbox is attached.
    """
    return 2


@pytest.fixture(name="mock_pasdbus")
def mock_pasdbus_fixture(
    fndh_port: int, mocked_initial_port_power_state: PowerState
) -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsPaSDBus device.

    :param fndh_port: the FNDH port this smartbox is attached to.
    :param mocked_initial_port_power_state: the initial power state of
        the port the smartbox is attached to.

    :return: a mock MccsPaSDBus device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)

    initial_port_power_sensed = [PowerState.OFF] * 28
    initial_port_power_sensed[fndh_port - 1] = mocked_initial_port_power_state
    builder.add_attribute("fndhPortsPowerSensed", initial_port_power_sensed)
    builder.add_result_command("SetSmartboxPortPowers", ResultCode.OK)
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    return builder()


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFNDH device.

    :return: a mock MccsFNDH device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    return builder()
