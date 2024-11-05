# -*- coding: utf-8 -*
# pylint: disable=too-many-arguments
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsStation."""
from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.testing.mock import MockCallable

from ska_low_mccs_pasd.fndh.fndh_health_model import FndhHealthModel
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import FnccStatusMap, LedServiceMap


class TestFNDHHealthModel:
    """A class for tests of the station health model."""

    @pytest.fixture
    def health_model(self: TestFNDHHealthModel) -> FndhHealthModel:
        """
        Fixture to return the station health model.

        :return: Health model to be used.
        """
        health_model = FndhHealthModel(MockCallable())
        health_model.update_state(communicating=True, power=PowerState.ON)

        return health_model

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        ("thresholds", "data", "expected_final_health", "expected_final_report"),
        [
            pytest.param(
                {"psu48v_voltage_1": np.array([100.0, 84.0, 43.0, 0.0])},
                {
                    "psu48v_voltage_1": 81.0,
                },
                HealthState.OK,
                "Health is OK.",
                id="All devices healthy, expect OK",
            ),
            pytest.param(
                {"psu48v_voltage_1": np.array([100.0, 84.0, 43.0, 0.0])},
                {
                    "psu48v_voltage_1": 85.0,
                },
                HealthState.OK,
                "Health is OK.",
                id="voltage in warning, expect OK",
            ),
            pytest.param(
                {"psu48v_voltage_1": np.array([100.0, 84.0, 43.0, 0.0])},
                {
                    "psu48v_voltage_1": 105.0,
                },
                HealthState.DEGRADED,
                "Monitoring point psu48v_voltage_1 is in DEGRADED HealthState. "
                "Cause: Monitoring point has value 105.0, "
                "this is in the alarm region for thresholds "
                "max_alm=100.0, min_alm=0.0",
                id="voltage too high, expect FAILED",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": np.array([i + 1 for i in range(24)]),
                    "ports_power_control": np.array([True] * 28),
                },
                HealthState.OK,
                "Health is OK.",
                id="All ports with smartbox configured have control.",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": np.array([i + 1 for i in range(24)]),
                    "ports_power_control": np.array([False] * 28),
                },
                HealthState.FAILED,
                "Number of smartbox without control is 100, "
                "this is above the configured limit of 25.",
                id="No power control over any smartbox.",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": np.array([i + 1 for i in range(24)]),
                    "ports_power_control": np.array([False] + [True] * 27),
                },
                HealthState.DEGRADED,
                "Number of smartbox without control is 4, "
                "this is above the configured limit of 0.",
                id="No power control over some smartbox.",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": np.array([i + 1 for i in range(24)]),
                },
                HealthState.OK,
                "Health is OK.",
                id="update before ports_power_control is known",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_power_control": np.array([False] + [True] * 27),
                },
                HealthState.OK,
                "Health is OK.",
                id="update before ports_power_sensed is known",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": np.array([]),
                    "ports_power_control": np.array([]),
                },
                HealthState.OK,
                "Health is OK.",
                id="update with empty lists",
            ),
        ],
    )
    def test_fndh_evaluate_health(
        self: TestFNDHHealthModel,
        health_model: FndhHealthModel,
        thresholds: dict[str, np.ndarray],
        data: dict[str, Any],
        expected_final_health: HealthState,
        expected_final_report: str,
    ) -> None:
        """
        Tests for evaluating FNDH health.

        :param thresholds: the thresholds defined for this monitoring point.
        :param health_model: Health model fixture.
        :param data: Health data values for health model.
        :param expected_final_health: Expected final health.
        :param expected_final_report: Expected final health report.
        """
        health_model.health_params = thresholds

        health_model.update_state(monitoring_points=data)

        assert health_model.evaluate_health() == (
            expected_final_health,
            expected_final_report,
        )
        # Check feature flagging
        assert health_model.health_rule_active is True
        health_model.health_rule_active = False
        assert health_model.evaluate_health() == (
            HealthState.OK,
            "Health is OK.",
        )
        assert health_model.health_rule_active is False

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        ("init_data", "expected_state_init", "end_data", "expected_state_end"),
        [
            pytest.param(
                {
                    "psu48v_voltage_1": 45.0,
                    "psu48v_voltage_2": 46.0,
                    "psu48v_current": 6.0,
                    "psu48v_temperature_1": 66.0,
                    "psu48v_temperature_2": 66.0,
                    "panel_temperature": 67.0,
                    "fncb_temperature": 65.0,
                    "status": FnccStatusMap.OK,
                    "led_pattern": LedServiceMap.OFF,
                    "comms_gateway_temperature": 46.0,
                    "power_module_temperature": 34.0,
                    "internal_ambient_temperature": 35.0,
                    "port_forcings": [True] * 12,
                    "ports_desired_power_when_online": [True] * 12,
                    "ports_desired_power_when_offline": [True] * 12,
                    "ports_power_sensed": [True] * 12,
                    "ports_power_control": [True] * 12,
                },
                {
                    "psu48v_voltage_1": 45.0,
                    "psu48v_voltage_2": 46.0,
                    "psu48v_current": 6.0,
                    "psu48v_temperature_1": 66.0,
                    "psu48v_temperature_2": 66.0,
                    "panel_temperature": 67.0,
                    "fncb_temperature": 65.0,
                    "status": FnccStatusMap.OK,
                    "led_pattern": LedServiceMap.OFF,
                    "comms_gateway_temperature": 46.0,
                    "power_module_temperature": 34.0,
                    "internal_ambient_temperature": 35.0,
                    "port_forcings": [True] * 12,
                    "ports_desired_power_when_online": [True] * 12,
                    "ports_desired_power_when_offline": [True] * 12,
                    "ports_power_sensed": [True] * 12,
                    "ports_power_control": [True] * 12,
                },
                {
                    "psu48v_voltage_1": 55.0,
                    "psu48v_voltage_2": 56.0,
                    "psu48v_current": 16.0,
                    "psu48v_temperature_1": 76.0,
                    "psu48v_temperature_2": 76.0,
                    "panel_temperature": 77.0,
                    "fncb_temperature": 75.0,
                    "status": FnccStatusMap.UNDEFINED,
                    "led_pattern": LedServiceMap.ON,
                    "comms_gateway_temperature": 56.0,
                    "power_module_temperature": 44.0,
                    "internal_ambient_temperature": 45.0,
                    "port_forcings": [False] * 12,
                    "ports_desired_power_when_online": [False] * 12,
                    "ports_desired_power_when_offline": [False] * 12,
                    "ports_power_sensed": [False] * 12,
                    "ports_power_control": [False] * 12,
                },
                {
                    "psu48v_voltage_1": 55.0,
                    "psu48v_voltage_2": 56.0,
                    "psu48v_current": 16.0,
                    "psu48v_temperature_1": 76.0,
                    "psu48v_temperature_2": 76.0,
                    "panel_temperature": 77.0,
                    "fncb_temperature": 75.0,
                    "status": FnccStatusMap.UNDEFINED,
                    "led_pattern": LedServiceMap.ON,
                    "comms_gateway_temperature": 56.0,
                    "power_module_temperature": 44.0,
                    "internal_ambient_temperature": 45.0,
                    "port_forcings": [False] * 12,
                    "ports_desired_power_when_online": [False] * 12,
                    "ports_desired_power_when_offline": [False] * 12,
                    "ports_power_sensed": [False] * 12,
                    "ports_power_control": [False] * 12,
                },
                id="Health data is updated succesfully",
            ),
        ],
    )
    def test_fndh_update_data(
        self: TestFNDHHealthModel,
        health_model: FndhHealthModel,
        init_data: dict[str, Any],
        expected_state_init: dict,
        end_data: dict[str, Any],
        expected_state_end: dict,
    ) -> None:
        """
        Test that we can update the state of the health model.

        :param health_model: Health model fixture.
        :param init_data: Initial health data values for health model.
        :param expected_state_init: Expected init state.
        :param end_data: Final data for health model.
        :param expected_state_end: Expected final state.
        """
        health_model.update_state(monitoring_points=init_data)
        assert health_model._state.get("monitoring_points") == expected_state_init

        health_model.update_state(monitoring_points=end_data)
        assert health_model._state.get("monitoring_points") == expected_state_end

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        (
            "monitoring_values",
            "init_thresholds",
            "end_thresholds",
            "init_expected_health",
            "init_expected_report",
            "end_expected_health",
            "end_expected_report",
        ),
        [
            pytest.param(
                {
                    "psu48v_voltage_1": 55.0,
                    "psu48v_voltage_2": 56.0,
                    "psu48v_current": 56.0,
                    "psu48v_temperature_1": 56.0,
                    "psu48v_temperature_2": 56.0,
                    "panel_temperature": 56.0,
                    "fncb_temperature": 56.0,
                    "status": FnccStatusMap.UNDEFINED,
                    "led_pattern": LedServiceMap.ON,
                    "comms_gateway_temperature": 56.0,
                    "power_module_temperature": 56.0,
                    "internal_ambient_temperature": 56.0,
                    "port_forcings": np.array([False] * 12),
                    "ports_desired_power_when_online": np.array([False] * 12),
                    "ports_desired_power_when_offline": np.array([False] * 12),
                    "ports_power_sensed": np.array([False] * 12),
                    "ports_power_control": np.array([False] * 12),
                },
                {
                    "psu48v_voltage_1_thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48v_voltage_2_thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48v_current_thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48v_temperature_1_thresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "psu48v_temperature_2_thresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "panel_temperature_thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "fncb_humidity_thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "comms_gateway_temperature_thresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "power_module_temperature_thresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "outside_temperature_thresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "internal_ambient_temperature_thresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                },
                {
                    "comms_gateway_temperature_thresholds": np.array(
                        [33.0, 22.0, 10.0, 0.0]
                    ),
                },
                HealthState.OK,
                "Health is OK.",
                HealthState.DEGRADED,
                "Monitoring point comms_gateway_temperature "
                "is in DEGRADED HealthState. "
                "Cause: Monitoring point has value 56.0, "
                "this is in the alarm region for thresholds "
                "max_alm=33.0, min_alm=0.0",
                id="Update thresholds so that now the device reports DEGRADED",
            ),
        ],
    )
    def test_subrack_can_change_thresholds(
        self: TestFNDHHealthModel,
        health_model: FndhHealthModel,
        monitoring_values: dict[str, Any],
        init_thresholds: dict[str, np.ndarray],
        end_thresholds: dict[str, np.ndarray],
        init_expected_health: HealthState,
        init_expected_report: str,
        end_expected_health: HealthState,
        end_expected_report: str,
    ) -> None:
        """
        Test subrack can change threshold values.

        :param monitoring_values: the monitoring values.
        :param health_model: Health model fixture.
        :param init_thresholds: Initial thresholds to set it to.
        :param end_thresholds: End thresholds to set it to.
        :param init_expected_health: Init expected health.
        :param init_expected_report: Init expected health report.
        :param end_expected_health: Final expected health.
        :param end_expected_report: Final expected health report.

        """
        # We are communicating and we have not seen any scary looking monitoring points.
        assert health_model.evaluate_health() == (HealthState.OK, "Health is OK.")

        health_model.update_state(monitoring_points=monitoring_values)
        for threshold, values in init_thresholds.items():
            health_model.update_health_threshold(
                threshold.removesuffix("_thresholds"), values
            )
        assert health_model.evaluate_health() == (
            init_expected_health,
            init_expected_report,
        )
        for threshold, values in end_thresholds.items():
            health_model.update_health_threshold(
                threshold.removesuffix("_thresholds"), values
            )
        assert health_model.evaluate_health() == (
            end_expected_health,
            end_expected_report,
        )
