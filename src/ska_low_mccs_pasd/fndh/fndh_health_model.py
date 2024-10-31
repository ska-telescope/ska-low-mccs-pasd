# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a FNDH."""
from __future__ import annotations

from typing import Any

from ska_control_model import HealthState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol

from .fndh_health_rules import FndhHealthRules


class FndhHealthModel(BaseHealthModel):
    """A health model for a FNDH."""

    _health_rules: FndhHealthRules

    def __init__(
        self: FndhHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
    ) -> None:
        """
        Initialise a new instance.

        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        """
        self.logger = None
        self._use_new_rules = True
        self._health_rules = FndhHealthRules()
        self._ignore_pasd_power = False
        super().__init__(
            health_changed_callback,
            pasd_power=None,
            ignore_pasd_power=False,
        )

    @property
    def health_rule_active(self: FndhHealthModel) -> bool:
        """
        A flag to represent if new healthRules are active.

        :returns: True if the new health rule is active.
        """
        return self._use_new_rules

    @health_rule_active.setter
    def health_rule_active(self: FndhHealthModel, val: bool) -> None:
        """
        Toggle the use of the new health rules.

        :param val: True if we want to use new healthRules.
        """
        if self._use_new_rules != val:
            self._use_new_rules = val
            # force a re-evaluation
            self.evaluate_health()

    def set_logger(self: FndhHealthModel, logger: Any) -> None:
        """
        Set logger for debugging.

        :param logger: a logger.
        """
        self.logger = logger
        self._health_rules.logger = logger

    def evaluate_health(
        self: FndhHealthModel,
    ) -> tuple[HealthState, str]:
        """
        Compute overall health of the fndh.

        The overall health is determined by:
         - PaSDBus state
         - Monitoring point values.

        For more details see ``FndhHealthRules``.

        :return: an overall health of the station
        """
        # if self.logger is not None:
        #     self.logger.error("FNDH is evaluate_health...\n")
        tile_health, tile_report = super().evaluate_health()
        if not self._use_new_rules:
            return tile_health, tile_report
        monitoring_points = self.monitoring_points
        pasd_power = self._state.get("pasd_power", None)
        ignore_pasd_power = self._state.get("ignore_pasd_power")
        for health in [
            HealthState.FAILED,
            HealthState.UNKNOWN,
            HealthState.DEGRADED,
            HealthState.OK,
        ]:
            if health == tile_health:
                return tile_health, tile_report
            result, report = self._health_rules.rules[health](
                monitoring_points=monitoring_points,
                pasd_power=pasd_power,
                ignore_pasd_power=ignore_pasd_power,
            )
            if result:
                return health, report
        return HealthState.UNKNOWN, "No rules matched"

    @property
    def monitoring_points(
        self: FndhHealthModel,
    ) -> dict[str, tuple[HealthState, str]]:
        """
        Get the intermediate health roll-up states.

        :return: the intermediate health roll-up states
        """
        mon_points = self._state.get("monitoring_points", {})
        return {
            attribute_name: self._health_rules.compute_intermediate_state(
                mon_points.get(attribute_name, None),
                threshold,
            )
            for attribute_name, threshold in self.health_params.items()
        }

    def update_health_threshold(
        self: FndhHealthModel, threshold_key: str, threshold_values: list[float]
    ) -> None:
        """
        Update the health thresholds.

        :param threshold_key: the name of this threshold.
        :param threshold_values: a list of 4 values containing
            high_alm, high_warn, low_warn, low_alm
        """
        self._health_rules.update_thresholds(threshold_key, threshold_values)

        # # re-evaluate
        self.evaluate_health()

    @property
    def health_params(self: FndhHealthModel) -> dict[str, Any]:
        """
        Get the thresholds for health rules.

        :return: the thresholds for health rules
        """
        return self._health_rules._thresholds

    @health_params.setter
    def health_params(self: FndhHealthModel, params: dict[str, Any]) -> None:
        """
        Set the thresholds for health rules.

        :param params: A dictionary of parameters with the param name as key and
            threshold as value
        """
        self._health_rules._thresholds = self._merge_dicts(
            self._health_rules._thresholds, params
        )
