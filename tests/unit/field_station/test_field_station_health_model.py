# -*- coding: utf-8 -*
# pylint: disable=too-many-arguments
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for FieldStation."""
from __future__ import annotations

import pytest
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.testing.mock import MockCallable

from ska_low_mccs_pasd.field_station.field_station_health_model import (
    FieldStationHealthModel,
)
from ska_low_mccs_pasd.pasd_data import PasdData
from tests.harness import get_fndh_name, get_smartbox_name


class TestFieldStationHealthModel:
    """A class for tests of the station health model."""

    @pytest.fixture
    def health_model(self: TestFieldStationHealthModel) -> FieldStationHealthModel:
        """
        Fixture to return the station health model.

        :return: Health model to be used.
        """
        health_model = FieldStationHealthModel(
            get_fndh_name(), [get_smartbox_name(1)], MockCallable()
        )
        health_model.update_state(communicating=True, power=PowerState.ON)

        return health_model

    @pytest.mark.parametrize(
        ("sub_devices", "thresholds", "expected_health", "expected_report"),
        [
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): HealthState.OK
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                None,
                HealthState.OK,
                "Health is OK.",
                id="All devices healthy, expect OK",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED if i == 0 else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                None,
                HealthState.DEGRADED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(0)} - FAILED'] FNDH: OK",
                id="1/5 smartboxes unhealthy, expect DEGRADED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.FAILED,
                    "smartbox": {
                        get_smartbox_name(i): HealthState.OK
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                None,
                HealthState.FAILED,
                "Too many subdevices are in a bad state: "
                "Smartboxes: [] FNDH: FAILED",
                id="FNDH unhealthy, expect FAILED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED if i == 0 else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {"smartbox_degraded": 0.00001, "smartbox_failed": 0.02},
                HealthState.FAILED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(0)} - FAILED'] FNDH: OK",
                id="One smartbox unhealthy, lowered thresholds, expect FAILED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED
                            if i < PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION / 2
                            else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                None,
                HealthState.FAILED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: {[f'{get_smartbox_name(i)} - FAILED' for i in range(12)]}"
                " FNDH: OK",
                id="1/2 smartboxes unhealthy, expect FAILED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.UNKNOWN,
                    "smartbox": {
                        get_smartbox_name(i): HealthState.OK
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                None,
                HealthState.UNKNOWN,
                "Some devices are unknown: Smartboxes: [] FNDH: UNKNOWN",
                id="FNDH UNKNOWN, expect UNKNOWN",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.UNKNOWN if i == 0 else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                None,
                HealthState.UNKNOWN,
                (
                    "Some devices are unknown: Smartboxes: "
                    f"['{get_smartbox_name(0)}'] FNDH: OK"
                ),
                id="One smartbox UNKNOWN, expect UNKNOWN",
            ),
        ],
    )
    def test_station_evaluate_health(
        self: TestFieldStationHealthModel,
        health_model: FieldStationHealthModel,
        sub_devices: dict,
        thresholds: dict[str, float],
        expected_health: HealthState,
        expected_report: str,
    ) -> None:
        """
        Tests for evaluating station health.

        :param health_model: The station health model to use
        :param sub_devices: the devices for which the station cares about health,
            and their healths
        :param thresholds: A dictionary of thresholds with the param name as key
            and threshold as value
        :param expected_health: the expected health values
        :param expected_report: the expected health report
        """
        health_model._fndh_health = sub_devices["fndh"]
        health_model._smartbox_health = sub_devices["smartbox"]

        if thresholds is not None:
            health_model.health_params = thresholds

        assert health_model.evaluate_health() == (expected_health, expected_report)

    @pytest.mark.parametrize(
        (
            "sub_devices",
            "health_change",
            "expected_init_health",
            "expected_init_report",
            "expected_final_health",
            "expected_final_report",
        ),
        [
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): HealthState.OK
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {
                    "fndh": HealthState.FAILED,
                },
                HealthState.OK,
                "Health is OK.",
                HealthState.FAILED,
                "Too many subdevices are in a bad state: "
                "Smartboxes: [] FNDH: FAILED",
                id="FNDH unhealthy, expect FAILED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): HealthState.OK
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {
                    "smartbox": {get_smartbox_name(1): HealthState.FAILED},
                },
                HealthState.OK,
                "Health is OK.",
                HealthState.DEGRADED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(1)} - FAILED'] FNDH: OK",
                id="All devices healthy, expect OK, then 1 smartbox FAILED,"
                "expect DEGRADED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED if i == 0 else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {
                    "smartbox": {get_smartbox_name(0): HealthState.OK},
                },
                HealthState.DEGRADED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(0)} - FAILED'] FNDH: OK",
                HealthState.OK,
                "Health is OK.",
                id="One smartbox unhealthy, expect DEGRADED, then smartbox becomes OK, "
                "expect OK",
            ),
        ],
    )
    def test_station_evaluate_changed_health(
        self: TestFieldStationHealthModel,
        health_model: FieldStationHealthModel,
        sub_devices: dict,
        health_change: dict[str, dict[str, HealthState]],
        expected_init_health: HealthState,
        expected_init_report: str,
        expected_final_health: HealthState,
        expected_final_report: str,
    ) -> None:
        """
        Tests of the station health model for a changed health.

        The properties of the health model are set and checked, then the health states
        of subservient devices are updated and the health is checked against the new
        expected value.

        :param health_model: The station health model to use
        :param sub_devices: the devices for which the station cares about health,
            and their healths
        :param health_change: a dictionary of the health changes, key device and value
            dictionary of fqdn:HealthState
        :param expected_init_health: the expected initial health
        :param expected_init_report: the expected initial health report
        :param expected_final_health: the expected final health
        :param expected_final_report: the expected final health report
        """
        health_model._fndh_health = sub_devices["fndh"]
        health_model._smartbox_health = sub_devices["smartbox"]

        assert health_model.evaluate_health() == (
            expected_init_health,
            expected_init_report,
        )

        health_update = {
            "fndh": health_model.fndh_health_changed,
            "smartbox": health_model.smartbox_health_changed,
        }

        for device in health_change:
            changes = health_change[device]
            if isinstance(changes, HealthState):
                health_update[device](get_fndh_name(), changes)
            else:
                for change in changes:
                    health_update[device](change, changes[change])

        assert health_model.evaluate_health() == (
            expected_final_health,
            expected_final_report,
        )

    @pytest.mark.parametrize(
        (
            "sub_devices",
            "init_thresholds",
            "expected_init_health",
            "expected_init_report",
            "final_thresholds",
            "expected_final_health",
            "expected_final_report",
        ),
        [
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED if i == 0 else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {"smartbox_degraded": 0.04, "smartbox_failed": 0.2},
                HealthState.DEGRADED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(0)} - FAILED'] FNDH: OK",
                {"smartbox_degraded": 0.05, "smartbox_failed": 0.2},
                HealthState.OK,
                "Health is OK.",
                id="One smartbox unhealthy, expect DEGRADED, then "
                "raise DEGRADED threshold, expect OK",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED if i == 0 else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {"smartbox_degraded": 0.04, "smartbox_failed": 0.2},
                HealthState.DEGRADED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(0)} - FAILED'] FNDH: OK",
                {"smartbox_degraded": 0.08, "smartbox_failed": 0.04},
                HealthState.FAILED,
                "Too many subdevices are in a bad state: "
                f"Smartboxes: ['{get_smartbox_name(0)} - FAILED'] FNDH: OK",
                id="One smartbox unhealthy, expect DEGRADED, then lower DEGRADED and "
                "FAILED threshold, expect FAILED",
            ),
            pytest.param(
                {
                    "fndh": HealthState.OK,
                    "smartbox": {
                        get_smartbox_name(i): (
                            HealthState.FAILED
                            if i < PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION / 5
                            else HealthState.OK
                        )
                        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
                    },
                },
                {"smartbox_degraded": 0.6, "smartbox_failed": 0.8},
                HealthState.OK,
                "Health is OK.",
                {"smartbox_degraded": 0.5, "smartbox_failed": 0.6},
                HealthState.OK,
                "Health is OK.",
                id="Few subracks unhealthy with high thresholds, expect OK, then lower"
                "DEGRADED and FAILED threshold but not by much, expect OK",
            ),
        ],
    )
    def test_station_evaluate_health_changed_thresholds(
        self: TestFieldStationHealthModel,
        health_model: FieldStationHealthModel,
        sub_devices: dict,
        init_thresholds: dict[str, float],
        expected_init_health: HealthState,
        expected_init_report: str,
        final_thresholds: dict[str, float],
        expected_final_health: HealthState,
        expected_final_report: str,
    ) -> None:
        """
        Tests of the station health model for changed thresholds.

        The properties of the health model are set and checked, then the thresholds for
        the health rules are changed and the new health is checked against the expected
        value

        :param health_model: The station health model to use
        :param sub_devices: the devices for which the station cares about health,
            and their healths
        :param init_thresholds: the initial thresholds of the health rules
        :param expected_init_health: the expected initial health
        :param expected_init_report: the expected initial health report
        :param final_thresholds: the final thresholds of the health rules
        :param expected_final_health: the expected final health
        :param expected_final_report: the expected final health report
        """
        health_model._fndh_health = sub_devices["fndh"]
        health_model._smartbox_health = sub_devices["smartbox"]

        health_model.health_params = init_thresholds
        assert health_model.evaluate_health() == (
            expected_init_health,
            expected_init_report,
        )

        health_model.health_params = final_thresholds
        assert health_model.evaluate_health() == (
            expected_final_health,
            expected_final_report,
        )
