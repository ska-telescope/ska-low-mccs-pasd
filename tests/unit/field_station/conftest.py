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


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFNDH device.

    :return: a mock MccsFNDH device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
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
