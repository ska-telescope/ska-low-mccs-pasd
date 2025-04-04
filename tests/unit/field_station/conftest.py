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


@pytest.fixture(name="mocked_outside_temperature")
def mocked_outside_temperature_fixture() -> float:
    """
    Return a mocked value for the outsideTemperature.

    :returns: a mocked value for the outsideTemperature.
    """
    return 36.5


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture(mocked_outside_temperature: float) -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFndh device.

    :param mocked_outside_temperature: the mocked outside temperature.

    :return: a mock MccsFndh device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_result_command("PowerOnPort", ResultCode.OK)
    builder.add_result_command("SetPortPowers", ResultCode.QUEUED)
    builder.add_attribute("OutsideTemperature", mocked_outside_temperature)
    builder.add_command("PortPowerState", False)
    builder.add_attribute("PortsPowerSensed", [False for _ in range(28)])
    builder.add_command("dev_name", "low-mccs/fndh/ci-1")
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    builder.add_result_command("Standby", ResultCode.OK)
    builder.add_result_command("On", ResultCode.OK)
    return builder()


@pytest.fixture(name="mock_smartbox")
def mock_smartbox_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsSmartBox device.

    :return: a mock MccsSmartBox device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    return builder()
