# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS Fndh."""
import pytest


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
