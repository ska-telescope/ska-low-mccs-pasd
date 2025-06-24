# -*- coding: utf-8 -*
# pylint: disable=too-many-arguments
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for smartbox."""
from __future__ import annotations

from logging import Logger
from typing import Any

import numpy as np
import pytest
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.testing.mock import MockCallable

from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import SmartboxStatusMap
from ska_low_mccs_pasd.smart_box.smartbox_health_model import SmartBoxHealthModel


class TestSmartboxHealthModel:
    """A class for tests of the smartbox health model."""

    @pytest.fixture
    def health_model(self: TestSmartboxHealthModel) -> SmartBoxHealthModel:
        """
        Fixture to return the smartbox health model.

        :return: Health model to be used.
        """
        health_model = SmartBoxHealthModel(MockCallable(), Logger("test"))
        health_model.update_state(
            communicating=True,
            power=PowerState.ON,
            status=SmartboxStatusMap.OK.name,
            port_breakers_tripped=[],
        )

        return health_model

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        (
            "thresholds",
            "monitoring_points",
            "port_breakers_tripped",
            "status",
            "expected_final_health",
            "expected_final_report",
        ),
        [
            pytest.param(
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"SYS_48V_V_TH": 81.0, "SYS_PSU_V_TH": 4.7},
                [],
                "OK",
                HealthState.OK,
                "Health is OK.",
                id="All devices healthy, expect OK",
            ),
            pytest.param(
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"SYS_48V_V_TH": 110.0, "SYS_PSU_V_TH": 4.7},
                [],
                "ALARM",
                HealthState.FAILED,
                f"Smartbox is reporting {SmartboxStatusMap.ALARM.name}.\n"
                "Intermediate health SYS_48V_V_TH is in FAILED HealthState. "
                "Cause: Monitoring point SYS_48V_V_TH: outside of max/min "
                "values, value: 110.0, max: 100.0, min: 0.0",
                id="value too high, expect failed",
            ),
            pytest.param(
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"SYS_48V_V_TH": -10.0, "SYS_PSU_V_TH": 4.7},
                [],
                "OK",  # Normally should be "ALARM" but health model should
                # not solely depend on the status register value.
                HealthState.FAILED,
                "Intermediate health SYS_48V_V_TH is in FAILED HealthState. "
                "Cause: Monitoring point SYS_48V_V_TH: outside of max/min "
                "values, value: -10.0, max: 100.0, min: 0.0",
                id="value too low, expect failed",
            ),
            pytest.param(
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"SYS_48V_V_TH": 90.0, "SYS_PSU_V_TH": 4.7},
                [],
                "WARNING",
                HealthState.DEGRADED,
                f"Smartbox is reporting {SmartboxStatusMap.WARNING.name}.\n"
                "Intermediate health SYS_48V_V_TH is in DEGRADED HealthState. "
                "Cause: Monitoring point SYS_48V_V_TH: in warning range, "
                "max fault: 100.0 > value: 90.0 > max warning: 84.0",
                id="value in high warning range, expect degraded",
            ),
            pytest.param(
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"SYS_48V_V_TH": 40.0, "SYS_PSU_V_TH": 4.7},
                [],
                "OK",  # Normally should be "WARNING" but health model should
                # not solely depend on the status register value.
                HealthState.DEGRADED,
                "Intermediate health SYS_48V_V_TH is in DEGRADED HealthState. "
                "Cause: Monitoring point SYS_48V_V_TH: in warning range, "
                "min fault: 0.0 < value: 40.0 < min warning: 43.0",
                id="value in low warning range, expect degraded",
            ),
            pytest.param(
                {
                    "P05_CURRENT_TH": [496],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"P05_CURRENT_TH": 400, "SYS_PSU_V_TH": 4.7},
                [],
                "OK",
                HealthState.OK,
                "Health is OK.",
                id="single point within range, expect ok",
            ),
            pytest.param(
                {
                    "P05_CURRENT_TH": [496],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"P05_CURRENT_TH": 500, "SYS_PSU_V_TH": 4.7},
                [],
                "OK",
                HealthState.FAILED,
                "Monitoring point P05_CURRENT_TH: 500 > 496",
                id="single point outside range, expect failed",
            ),
            pytest.param(
                {
                    "P05_CURRENT_TH": [496],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"P05_CURRENT_TH": 400, "SYS_PSU_V_TH": 4.7},
                [],
                "ALARM",
                HealthState.FAILED,
                f"Smartbox is reporting {SmartboxStatusMap.ALARM.name}.",
                id="Status register is reporting ALARM, expect failed",
            ),
            pytest.param(
                {
                    "P05_CURRENT_TH": [496],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"P05_CURRENT_TH": 400, "SYS_PSU_V_TH": 4.7},
                [
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                    True,
                ],
                "OK",
                HealthState.FAILED,
                "FEM circuit breakers have tripped on ports [2, 7, 12]",
                id="FEM port breakers have tripped, expect failed",
            ),
            pytest.param(
                {
                    "P05_CURRENT_TH": [496],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"P05_CURRENT_TH": 400, "SYS_PSU_V_TH": 4.7},
                [
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                ],
                "OK",
                HealthState.FAILED,
                "FEM circuit breakers have tripped on ports [9]",
                id="Single FEM port breaker has tripped, expect failed",
            ),
            pytest.param(
                {
                    "P05_CURRENT_TH": [496],
                    "SYS_PSU_V_TH": [4.0, 4.4, 4.9, 5.0],
                },
                {"P05_CURRENT_TH": 497, "SYS_PSU_V_TH": 4.5},
                [
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                ],
                "ALARM",
                HealthState.FAILED,
                f"Smartbox is reporting {SmartboxStatusMap.ALARM.name}.\n"
                "FEM circuit breakers have tripped on ports [12]\n"
                "Intermediate health P05_CURRENT_TH is in FAILED HealthState. "
                "Cause: Monitoring point P05_CURRENT_TH: 497 > 496",
                id="FEM port breaker has tripped and monitoring points "
                "out of range, expect failed",
            ),
        ],
    )
    def test_smartbox_evaluate_health(
        self: TestSmartboxHealthModel,
        health_model: SmartBoxHealthModel,
        thresholds: dict[str, np.ndarray],
        monitoring_points: dict[str, Any],
        port_breakers_tripped: list[bool],
        status: str,
        expected_final_health: HealthState,
        expected_final_report: str,
    ) -> None:
        """
        Tests for evaluating smartbox health.

        :param thresholds: the thresholds defined for this monitoring point.
        :param health_model: Health model fixture.
        :param monitoring_points: Health data values for health model.
        :param port_breakers_tripped: Port breaker trip status.
        :param status: Smartbox status register value.
        :param expected_final_health: Expected final health.
        :param expected_final_report: Expected final health report.
        """
        health_model.health_params = thresholds

        health_model.update_state(
            monitoring_points=monitoring_points,
            port_breakers_tripped=port_breakers_tripped,
            status=status,
        )

        final_health, final_report = health_model.evaluate_health()
        assert final_health == expected_final_health
        assert expected_final_report in final_report

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        ("init_data", "expected_state_init", "end_data", "expected_state_end"),
        [
            pytest.param(
                {
                    "SYS_48V_V_TH": 45.0,
                    "SYS_PSU_V_TH": 46.0,
                    "SYS_PSUTEMP_TH": 6.0,
                },
                {
                    "SYS_48V_V_TH": 45.0,
                    "SYS_PSU_V_TH": 46.0,
                    "SYS_PSUTEMP_TH": 6.0,
                },
                {
                    "SYS_48V_V_TH": 55.0,
                    "SYS_PSU_V_TH": 56.0,
                    "SYS_PSUTEMP_TH": 16.0,
                },
                {
                    "SYS_48V_V_TH": 55.0,
                    "SYS_PSU_V_TH": 56.0,
                    "SYS_PSUTEMP_TH": 16.0,
                },
                id="Health data is updated succesfully",
            ),
        ],
    )
    def test_smartbox_update_data(
        self: TestSmartboxHealthModel,
        health_model: SmartBoxHealthModel,
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
                    "SYS_48V_V_TH": 45.0,
                    "SYS_PSU_V_TH": 46.0,
                    "SYS_PSUTEMP_TH": 46.0,
                },
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSUTEMP_TH": [0.0, 43.0, 84.0, 100.0],
                },
                {"SYS_PSU_V_TH": [0.0, 10.0, 22.0, 33.0]},
                HealthState.OK,
                "Health is OK.",
                HealthState.FAILED,
                "Intermediate health SYS_PSU_V_TH is in FAILED HealthState. "
                "Cause: Monitoring point SYS_PSU_V_TH: outside of max/min values, "
                "value: 46.0, max: 33.0, min: 0.0",
                id="Update thresholds so that now the device reports FAILED",
            ),
            pytest.param(
                {
                    "SYS_48V_V_TH": 45.0,
                    "SYS_PSU_V_TH": 46.0,
                    "SYS_PSUTEMP_TH": 46.0,
                },
                {
                    "SYS_48V_V_TH": [0.0, 43.0, 84.0, 100.0],
                    "SYS_PSU_V_TH": [0.0, 10.0, 22.0, 33.0],
                    "SYS_PSUTEMP_TH": [0.0, 43.0, 84.0, 100.0],
                },
                {"SYS_PSU_V_TH": [0.0, 43.0, 84.0, 100.0]},
                HealthState.FAILED,
                "Intermediate health SYS_PSU_V_TH is in FAILED HealthState. "
                "Cause: Monitoring point SYS_PSU_V_TH: outside of max/min values, "
                "value: 46.0, max: 33.0, min: 0.0",
                HealthState.OK,
                "Health is OK.",
                id="Update thresholds so that now the device reports OK",
            ),
        ],
    )
    def test_smartbox_can_change_thresholds(
        self: TestSmartboxHealthModel,
        health_model: SmartBoxHealthModel,
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
        initial_health, initial_report = health_model.evaluate_health()
        assert initial_health == HealthState.OK
        assert "Health is OK." in initial_report

        health_model.update_state(monitoring_points=monitoring_values)
        health_model.health_params = init_thresholds

        initial_health, initial_report = health_model.evaluate_health()
        assert initial_health == init_expected_health
        assert init_expected_report in initial_report
        health_model.health_params = end_thresholds

        final_health, final_report = health_model.evaluate_health()
        assert final_health == end_expected_health
        assert end_expected_report in final_report
