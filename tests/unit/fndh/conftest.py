# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS Fndh."""
import unittest.mock

import pytest
import tango
from ska_low_mccs_common.testing.mock import MockDeviceBuilder


@pytest.fixture(name="default_monitoring_point_thresholds")
def default_monitoring_point_thresholds_fixture() -> dict[str, list[float]]:
    """
    Return a dictionary with monitoring points thresholds.

    :returns: a dictionary with monitoring points thresholds.
    """
    return {
        "psu48vvoltage1": [100.0, 80.0, 2.0, 0.0],
        "psu48vvoltage2": [100.0, 80.0, 2.0, 0.0],
        "psu48vcurrent": [100.0, 80.0, 2.0, 0.0],
        "psu48vtemperature1": [100.0, 80.0, 2.0, 0.0],
        "psu48vtemperature2": [100.0, 80.0, 2.0, 0.0],
        "paneltemperature": [100.0, 80.0, 2.0, 0.0],
        "fncbtemperature": [100.0, 80.0, 2.0, 0.0],
        "fncbhumidity": [100.0, 80.0, 2.0, 0.0],
        "commsgatewaytemperature": [100.0, 80.0, 2.0, 0.0],
        "powermoduletemperature": [100.0, 80.0, 2.0, 0.0],
        "outsidetemperature": [100.0, 80.0, 2.0, 0.0],
        "internalambienttemperature": [100.0, 80.0, 2.0, 0.0],
    }


@pytest.fixture(name="healthy_monitoring_points")
def healthy_monitoring_points_fixture(
    default_monitoring_point_thresholds: dict[str, list[float]],
) -> dict[str, float]:
    """
    Return a dictionary with monitoring points considered healthy.

    :param default_monitoring_point_thresholds: a dictionary with
        monitoring points thresholds.

    :returns: a dictionary with monitoring points considered healthy.
    """
    mon_value = {}
    for key, threshold in default_monitoring_point_thresholds.items():
        mon_value[key] = (threshold[1] + threshold[2]) / 2

    return mon_value


@pytest.fixture(name="mock_pasdbus")
def mock_pasdbus_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsPaSDBus device.

    :return: a mock MccsPaSDBus device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_command("GetPasdDeviceSubscriptions", {})

    builder.add_attribute("fndhPortsPowerSensed", [True] * 28)

    attrs = {
        "fndhpsu48vvoltage1": [51, 49, 46, 41],
        "fndhpsu48vvoltage2": [51, 49, 46, 41],
        "fndhpsu48vcurrent": [17, 15, 0, -4],
        "fndhpsu48vtemperature1": [95, 80, 5, -2],
        "fndhpsu48vtemperature2": [95, 80, 5, -2],
        "fndhpaneltemperature": [80, 65, 5, -2],
        "fndhfncbtemperature": [80, 65, 5, -2],
        "fndhfncbhumidity": [80, 65, 15, 5],
        "fndhcommsgatewaytemperature": [80, 65, 5, -2],
        "fndhpowermoduletemperature": [80, 65, 5, -2],
        "fndhoutsidetemperature": [80, 65, 5, -2],
        "fndhinternalambienttemperature": [80, 65, 5, -2],
    }
    for attr, thresholds in attrs.items():
        value = float((thresholds[1] + thresholds[2]) / 2)
        builder.add_attribute(attr, value)

    builder.add_command("GetPasdDeviceSubscriptions", list(attrs.keys()))
    return builder()
