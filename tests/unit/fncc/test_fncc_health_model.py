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

import pytest
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.testing.mock import MockCallable
from ska_low_pasd_driver.pasd_bus_conversions import FnccStatusMap

from ska_low_mccs_pasd.fncc.fncc_health_model import FnccHealthModel


class TestFnccHealthModel:
    """A class for tests of the FNCC health model."""

    @pytest.fixture
    def health_model(
        self: TestFnccHealthModel, logger: logging.Logger
    ) -> FnccHealthModel:
        """
        Fixture to return the FNCC health model.

        :param logger: a fixture with the logger to use.

        :return: Health model to be used.
        """
        health_model = FnccHealthModel(MockCallable(), logger)
        health_model.update_state(communicating=True, power=PowerState.ON)

        return health_model

    @pytest.mark.parametrize(
        ("data", "expected_final_health", "expected_final_report"),
        [
            pytest.param(
                {
                    "status": FnccStatusMap.OK.name,
                },
                HealthState.OK,
                f"FNCC is reporting {FnccStatusMap.OK.name}.",
                id="FNCC reporting OK, expect OK",
            ),
            pytest.param(
                {
                    "status": FnccStatusMap.RESET.name,
                },
                HealthState.DEGRADED,
                f"FNCC is reporting {FnccStatusMap.RESET.name}.",
                id="FNCC reporting RESET, expect DEGRADED",
            ),
            pytest.param(
                {
                    "status": FnccStatusMap.FRAME_ERROR.name,
                },
                HealthState.FAILED,
                f"FNCC is reporting {FnccStatusMap.FRAME_ERROR.name}.",
                id="FNCC reporting FRAME_ERROR, expect FAILED",
            ),
            pytest.param(
                {
                    "status": FnccStatusMap.MODBUS_STUCK.name,
                },
                HealthState.FAILED,
                f"FNCC is reporting {FnccStatusMap.MODBUS_STUCK.name}.",
                id="FNCC reporting MODBUS_STUCK, expect FAILED",
            ),
            pytest.param(
                {
                    "status": FnccStatusMap.FRAME_ERROR_MODBUS_STUCK.name,
                },
                HealthState.FAILED,
                f"FNCC is reporting {FnccStatusMap.FRAME_ERROR_MODBUS_STUCK.name}.",
                id="FNCC reporting FRAME_ERROR_MODBUS_STUCK, expect FAILED",
            ),
        ],
    )
    def test_fncc_evaluate_health(
        self: TestFnccHealthModel,
        health_model: FnccHealthModel,
        data: dict[str, Any],
        expected_final_health: HealthState,
        expected_final_report: str,
    ) -> None:
        """
        Tests for evaluating FNCC health.

        :param health_model: Health model fixture.
        :param data: Health data values for health model.
        :param expected_final_health: Expected final health.
        :param expected_final_report: Expected final health report.
        """
        # Status register not yet updated
        health, report = health_model.evaluate_health()
        assert health == HealthState.UNKNOWN
        assert "FNCC has not received a status value." in report

        health_model.update_state(status=data.get("status"))

        final_health, final_report = health_model.evaluate_health()
        assert final_health == expected_final_health
        assert expected_final_report in final_report

    # pylint: disable=too-many-positional-arguments
    @pytest.mark.parametrize(
        ("init_data", "expected_state_init", "end_data", "expected_state_end"),
        [
            pytest.param(
                {
                    "status": FnccStatusMap.OK.name,
                },
                {
                    "status": FnccStatusMap.OK.name,
                },
                {
                    "status": FnccStatusMap.FRAME_ERROR.name,
                },
                {
                    "status": FnccStatusMap.FRAME_ERROR.name,
                },
                id="Health data is updated successfully",
            ),
            pytest.param(
                {
                    "status": FnccStatusMap.FRAME_ERROR_MODBUS_STUCK.name,
                },
                {
                    "status": FnccStatusMap.FRAME_ERROR_MODBUS_STUCK.name,
                },
                {
                    "status": FnccStatusMap.OK.name,
                },
                {
                    "status": FnccStatusMap.OK.name,
                },
                id="Health data is updated successfully",
            ),
        ],
    )
    def test_fncc_update_data(
        self: TestFnccHealthModel,
        health_model: FnccHealthModel,
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
        health_model.update_state(status=init_data)
        assert health_model._state.get("status") == expected_state_init

        health_model.update_state(status=end_data)
        assert health_model._state.get("status") == expected_state_end
