# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a Smartbox."""
from __future__ import annotations

from logging import Logger
from typing import Any, Optional

from ska_control_model import HealthState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol

from .smartbox_health_rules import SmartboxHealthRules

__all__ = ["SmartBoxHealthModel"]


class SmartBoxHealthModel(BaseHealthModel):
    """A health model for a smartbox."""

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
        self._use_new_health_rules = True
        super().__init__(health_changed_callback)

    @property
    def use_new_health_rules(self: SmartBoxHealthModel) -> bool:
        """
        A flag to represent if new healthRules are active.

        :returns: True if the new health rule is active.
        """
        return self._use_new_health_rules

    @use_new_health_rules.setter
    def use_new_health_rules(self: SmartBoxHealthModel, val: bool) -> None:
        """
        Toggle the use of the new health rules.

        :param val: True if we want to use new healthRules.
        """
        if self._use_new_health_rules != val:
            self._use_new_health_rules = val
            # force a re-evaluation
            self.evaluate_health()

    def evaluate_health(
        self: SmartBoxHealthModel,
    ) -> tuple[HealthState, str]:
        """
        Compute overall health of the smartbox.

        The overall health is based on the monitoring points of the smartbox

        :return: an overall health of the smartbox
        """
        smartbox_health, smartbox_report = super().evaluate_health()
        if not self._use_new_health_rules:
            return smartbox_health, smartbox_report
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

        intermediate_healths = {}
        for health_key, parameters in self.health_params.items():
            intermediate_healths[health_key] = (
                self._health_rules.compute_intermediate_state(
                    health_key,
                    monitoring_points.get(health_key),
                    parameters,
                )
            )
        return intermediate_healths

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
        if params.get("pcbtemperature") is not None:
            # Monitoring point pcbtemperature is not implemented in h/w
            # and is not rolled up in health. see SPRTS-347
            params.pop("pcbtemperature")
        self._health_rules._thresholds = self._merge_dicts(
            self._health_rules._thresholds, params
        )
