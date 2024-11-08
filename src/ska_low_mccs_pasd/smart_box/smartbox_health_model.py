# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a PaSD bus."""
from __future__ import annotations

from logging import Logger
from typing import Any, Optional

from ska_control_model import HealthState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol

from .smartbox_health_rules import SmartboxHealthRules

__all__ = ["SmartBoxHealthModel"]


class SmartBoxHealthModel(BaseHealthModel):
    """
    A health model for a PaSD bus.

    # TODO: [MCCS-2087] Implement the evaluate_health method
    """

    _health_rules: SmartboxHealthRules

    def __init__(
        self: SmartBoxHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
        logger: Optional[Logger],
        thresholds: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        :param logger: logger for this device
        :param thresholds: the threshold parameters for the health rules
        """
        self.logger = logger
        self._health_rules = SmartboxHealthRules(thresholds)
        super().__init__(health_changed_callback, pasdbus_status=None)

    def evaluate_health(
        self: SmartBoxHealthModel,
    ) -> tuple[HealthState, str]:
        """
        Compute overall health of the smartbox.

        The overall health is based on the monitoring points of the smartbox

        :return: an overall health of the smartbox
        """
        smartbox_health, smartbox_report = super().evaluate_health()
        intermediate_healths = self.intermediate_healths
        for health in [
            HealthState.FAILED,
            HealthState.UNKNOWN,
            HealthState.DEGRADED,
            HealthState.OK,
        ]:
            if health == smartbox_health:
                return smartbox_health, smartbox_report
            result, report = self._health_rules.rules[health](intermediate_healths)
            if result:
                return health, report
        return HealthState.UNKNOWN, "No rules matched"

    @property
    def intermediate_healths(
        self: SmartBoxHealthModel,
    ) -> dict[str, tuple[HealthState, str]]:
        """
        Get the intermediate health roll-up states.

        :return: the intermediate health roll-up states
        """
        monitoring_points: dict[str, Any] = self._state.get("monitoring_points", {})

        return {
            health_key: self._health_rules.compute_intermediate_state(
                health_key,
                monitoring_points.get(health_key, {}),
                parameters,
            )
            for health_key, parameters in self.health_params.items()
        }

    @property
    def health_params(self: SmartBoxHealthModel) -> dict[str, Any]:
        """
        Get the thresholds for health rules.

        :return: the thresholds for health rules
        """
        return self._health_rules._thresholds

    @health_params.setter
    def health_params(self: SmartBoxHealthModel, params: dict[str, Any]) -> None:
        """
        Set the thresholds for health rules.

        :param params: A dictionary of parameters with the param name as key and
            threshold as value
        """
        self._health_rules._thresholds = self._merge_dicts(
            self._health_rules.default_thresholds, params
        )

    def update_data(self: SmartBoxHealthModel, new_states: dict) -> None:
        """
        Update this health model with state relevant to evaluating health.

        :param new_states: New states of the data points.
        """
        self._state.update(new_states)
        self.update_health()
