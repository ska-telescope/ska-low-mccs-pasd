# -*- coding: utf-8 -*
# pylint: disable=too-many-arguments
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsFndh healthModel."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pytest
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.testing.mock import MockCallable

from ska_low_mccs_pasd.fndh.fndh_health_model import FndhHealthModel
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import FndhStatusMap, LedServiceMap


class TestFNDHHealthModel:
    """A class for tests of the FNDH health model."""

    @pytest.fixture
    def health_model(
        self: TestFNDHHealthModel, logger: logging.Logger
    ) -> FndhHealthModel:
        """
        Fixture to return the FNDH health model.

        :param logger: a fixture with the logger to use.

        :return: Health model to be used.
        """
        health_model = FndhHealthModel(MockCallable(), logger)
        health_model.update_state(communicating=True, power=PowerState.ON)

        return health_model

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        ("thresholds", "data", "expected_final_health", "expected_final_report"),
        [
            pytest.param(
                {"psu48vvoltage1": [100.0, 84.0, 43.0, 0.0]},
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "psu48vvoltage1": 81.0,
                    "status": FndhStatusMap.UNINITIALISED.name,
                },
                HealthState.OK,
                "Health is OK.\n"
                f"FNDH is reporting {FndhStatusMap.UNINITIALISED.name}.",
                id="All devices healthy and FNDH uninitialised, expect OK",
            ),
            pytest.param(
                {"psu48vvoltage1": [100.0, 84.0, 43.0, 0.0]},
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "psu48vvoltage1": 81.0,
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.OK,
                f"Health is OK.\nFNDH is reporting {FndhStatusMap.OK.name}.",
                id="All devices healthy, expect OK",
            ),
            pytest.param(
                {"psu48vvoltage1": [100.0, 84.0, 43.0, 0.0]},
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "psu48vvoltage1": 85.0,
                    "status": FndhStatusMap.WARNING.name,
                },
                HealthState.DEGRADED,
                "Monitoring point psu48vvoltage1 is in DEGRADED HealthState. "
                "Cause: Monitoring point psu48vvoltage1 has value 85.0, "
                "this is in the warning region for thresholds "
                "max_warn=84.0, min_warn=43.0",
                id="voltage in warning, expect OK",
            ),
            pytest.param(
                {"psu48vvoltage1": [100.0, 84.0, 43.0, 0.0]},
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "psu48vvoltage1": 105.0,
                    "status": FndhStatusMap.ALARM.name,
                },
                HealthState.FAILED,
                "Monitoring point psu48vvoltage1 is in FAILED HealthState. "
                "Cause: Monitoring point psu48vvoltage1 has value 105.0, "
                "this is in the alarm region for thresholds "
                "max_alm=100.0, min_alm=0.0",
                id="voltage too high, expect FAILED",
            ),
            pytest.param(
                {"psu48vvoltage1": [100.0, 84.0, 43.0, 0.0]},
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "psu48vvoltage1": 81.0,
                    "status": FndhStatusMap.ALARM.name,
                },
                HealthState.FAILED,
                "FNDH is reporting ALARM.",
                id="Status register is reporting ALARM, expect FAILED",
            ),
            pytest.param(
                {"psu48vvoltage1": [100.0, 84.0, 43.0, 0.0]},
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "psu48vvoltage1": 81.0,
                    "status": FndhStatusMap.WARNING.name,
                },
                HealthState.DEGRADED,
                "FNDH is reporting WARNING.",
                id="Status register is reporting WARNING, expect DEGRADED",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [True] * 28,
                    "portspowersensed": [True] * 28,
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.OK,
                "Health is OK.",
                id="All smartbox-configured ports are healthy.",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": [i + 1 for i in range(22)] + [25, 28],
                    "portspowercontrol": [False] * 27 + [True],
                    "portspowersensed": [True] * 27 + [False],
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.FAILED,
                "Percent of faulty smartbox-configured-ports is 100%, "
                "this is above the configurable threshold of 25%. "
                "Details: [('PDOC 1 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 2 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 3 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 4 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 5 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 6 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 7 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 8 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 9 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 10 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 11 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 12 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 13 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 14 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 15 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 16 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 17 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 18 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 19 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 20 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 21 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 22 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 25 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box', "
                "'PDOC 28 stuck OFF, could be a fault within the PDOC, "
                "damaged PDOC cable, or faulty SMART Box EP')]",
                id=(
                    "All smartbox-configured-ports are faulty with PDOC stuck ON"
                    "the 28th smartbox is faulty with ports stuck OFF"
                ),
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowersensed": [True] * 28,
                    "portspowercontrol": [False] + [True] * 27,
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.DEGRADED,
                "Percent of faulty smartbox-configured-ports is 4%, "
                "this is above the configurable threshold of 0%. "
                "Details: [('PDOC 1 stuck ON, fault within the PDOC, "
                "cannot turn OFF PDOC port in response to a "
                "POWERDOWN from the SMART Box'",
                id="No power control over some smartbox.",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [i + 1 for i in range(24)],
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.UNKNOWN,
                "Unable to evaluate PDOC port faults in configured smartbox",
                id="Health before portspowercontrol is known",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": [i + 1 for i in range(24)],
                    "portspowercontrol": [False] + [True] * 27,
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.UNKNOWN,
                "Unable to evaluate PDOC port faults in configured smartbox",
                id="Health before ports_power_sensed is known",
            ),
            pytest.param(
                {
                    "degraded_percent_uncontrolled_smartbox": 0,
                    "failed_percent_uncontrolled_smartbox": 25,
                },
                {
                    "ports_with_smartbox": [],
                    "portspowercontrol": [],
                    "portspowersensed": [],
                    "status": FndhStatusMap.OK.name,
                },
                HealthState.OK,
                "Health is OK",
                id="Health with no smartbox configured ports.",
            ),
        ],
    )
    def test_fndh_evaluate_health(
        self: TestFNDHHealthModel,
        health_model: FndhHealthModel,
        default_monitoring_point_thresholds: dict[str, list[float]],
        healthy_monitoring_points: dict[str, Any],
        thresholds: dict[str, list[float]],
        data: dict[str, Any],
        expected_final_health: HealthState,
        expected_final_report: str,
    ) -> None:
        """
        Tests for evaluating FNDH health.

        :param thresholds: the thresholds defined for this monitoring point.
        :param health_model: Health model fixture.
        :param default_monitoring_point_thresholds: a fixture containing some default
            monitoring point thresholds to use
        :param healthy_monitoring_points: a fixture containing monitoring points in
            the health range.
        :param data: Health data values for health model.
        :param expected_final_health: Expected final health.
        :param expected_final_report: Expected final health report.
        """
        # Monitoring points thresholds not yet updated
        health, _ = health_model.evaluate_health()
        assert health == HealthState.UNKNOWN

        # Monitoring points not yet updated
        monitoring_point_thresholds = default_monitoring_point_thresholds.copy()
        monitoring_point_thresholds.update(thresholds)
        health_model.health_params = monitoring_point_thresholds
        health, report = health_model.evaluate_health()
        assert health == HealthState.UNKNOWN
        assert "No value has been read from the FNDH pasdStatus register." in report

        health_model.update_state(status=data.get("status"))
        health_model.update_state(ports_with_smartbox=data.get("ports_with_smartbox"))
        monitoring_points = healthy_monitoring_points.copy()
        monitoring_points.update(data)
        health_model.update_state(monitoring_points=monitoring_points)

        final_health, final_report = health_model.evaluate_health()
        assert final_health == expected_final_health
        assert expected_final_report in final_report

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
                    "status": FndhStatusMap.OK.name,
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
                    "status": FndhStatusMap.OK.name,
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
                    "status": FndhStatusMap.UNDEFINED.name,
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
                    "status": FndhStatusMap.UNDEFINED.name,
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
            "health_data",
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
                    "monitoring_points": {
                        "psu48vvoltage1": 55.0,
                        "psu48vvoltage2": 56.0,
                        "psu48vcurrent": 56.0,
                        "psu48vtemperature1": 56.0,
                        "psu48vtemperature2": 56.0,
                        "paneltemperature": 56.0,
                        "fncbtemperature": 56.0,
                        "fncbhumidity": 54.0,
                        "status": FndhStatusMap.OK.name,
                        "ledpattern": LedServiceMap.ON,
                        "commsgatewaytemperature": 56.0,
                        "powermoduletemperature": 56.0,
                        "outsidetemperature": 46.0,
                        "internalambienttemperature": 56.0,
                        "portforcings": np.array([False] * 12),
                        "portsdesiredpowerwhenonline": np.array([False] * 28),
                        "portsdesiredpowerwhenoffline": np.array([False] * 28),
                        "portspowersensed": np.array([False] * 28),
                        "portspowercontrol": np.array([False] * 28),
                    },
                    "status": FndhStatusMap.OK.name,
                },
                {
                    "psu48vvoltage1thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48vvoltage2thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48vcurrentthresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48vtemperature1thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "psu48vtemperature2thresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "paneltemperaturethresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "fncbhumiditythresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "fncbtemperaturethresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "commsgatewaytemperaturethresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "powermoduletemperaturethresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                    "outsidetemperaturethresholds": np.array([100.0, 84.0, 43.0, 0.0]),
                    "internalambienttemperaturethresholds": np.array(
                        [100.0, 84.0, 43.0, 0.0]
                    ),
                },
                {
                    "commsgatewaytemperaturethresholds": np.array(
                        [33.0, 22.0, 10.0, 0.0]
                    ),
                },
                HealthState.OK,
                "Health is OK.",
                HealthState.FAILED,
                "Monitoring point commsgatewaytemperature "
                "is in FAILED HealthState. "
                "Cause: Monitoring point commsgatewaytemperature has value 56.0, "
                "this is in the alarm region for thresholds "
                "max_alm=33.0, min_alm=0.0",
                id="Update thresholds so that now the device reports FAILED",
            ),
        ],
    )
    def test_fndh_can_change_thresholds(
        self: TestFNDHHealthModel,
        health_model: FndhHealthModel,
        health_data: dict[str, Any],
        init_thresholds: dict[str, np.ndarray],
        end_thresholds: dict[str, np.ndarray],
        init_expected_health: HealthState,
        init_expected_report: str,
        end_expected_health: HealthState,
        end_expected_report: str,
    ) -> None:
        """
        Test FNDH can change threshold values.

        :param health_data: the health model data.
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
        assert initial_health == HealthState.UNKNOWN, initial_report
        health_model.update_state(ports_with_smartbox=[i + 1 for i in range(24)])
        health_model.update_state(**health_data)
        for threshold, values in init_thresholds.items():
            health_model.update_monitoring_point_threshold(
                threshold.removesuffix("thresholds"), values
            )
        initial_health, initial_report = health_model.evaluate_health()

        assert initial_health == init_expected_health, initial_report
        assert init_expected_report in initial_report
        for threshold, values in end_thresholds.items():
            health_model.update_monitoring_point_threshold(
                threshold.removesuffix("thresholds"), values
            )

        final_health, final_report = health_model.evaluate_health()
        assert final_health == end_expected_health, final_report
        assert end_expected_report in final_report
