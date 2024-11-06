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

import numpy as np
from ska_control_model import HealthState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol

from .fndh_health_rules import FndhHealthRules


class FndhHealthModel(BaseHealthModel):
    """
    The health model for a FNDH.

    The health model will contain a dictionary _state
    containing monitoring points to feed the healthRules.

    :example:
        >>> {
        >>>     "pasd_power": PowerState.ON
        >>>     "ignore_pasd_power": False
        >>>     "ports_with_smartbox": [1, 3, 4, 6]
        >>>     "monitoring_points" :{
        >>>         "portspowercontrol" : [True] * 28,
        >>>         "portspowersensed"  : [True] * 28,
        >>>         ...
        >>>     }
        >>> }
    """

    # The evaluation of HealthState will check for matches specified by the
    # precedence of HealthStates defined by this list.
    ORDERED_HEALTH_PRECEDENCE = [
        HealthState.FAILED,
        HealthState.UNKNOWN,
        HealthState.DEGRADED,
        HealthState.OK,
    ]

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
        self._health_rules: FndhHealthRules = FndhHealthRules()
        super().__init__(
            health_changed_callback,
            pasd_power=None,
            ignore_pasd_power=False,
            ports_with_smartbox=None,
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

    def _get_report_from_rules(
        self: FndhHealthModel, mon_points: dict[str, Any]
    ) -> tuple[HealthState, str]:
        for health_value in self.ORDERED_HEALTH_PRECEDENCE:
            result, report = self._health_rules.rules[health_value](
                monitoring_points=self.monitoring_points_with_thresholds,
                pasd_power=self._state.get("pasd_power"),
                ignore_pasd_power=self._state.get("ignore_pasd_power"),
                ports_with_smartbox=self._state.get("ports_with_smartbox"),
                ports_power_control=mon_points.get("portspowercontrol"),
            )
            if result:
                return health_value, report
        return HealthState.UNKNOWN, "No rules matched"

    def evaluate_health(
        self: FndhHealthModel,
    ) -> tuple[HealthState, str]:
        """
        Compute overall health of the fndh.

        The overall health is determined by a set of monitoring
        points defined in the _state dictionary.

        :example:
            >>> {
            >>>     "pasd_power": PowerState.ON
            >>>     "ignore_pasd_power": False
            >>>     "ports_with_smartbox": [1, 3, 4, 6]
            >>>     "monitoring_points" :{
            >>>         "portspowercontrol" : [True] * 28,
            >>>         "portspowersensed"  : [True] * 28,
            >>>         ...
            >>>     }
            >>> }


        For more details see ``FndhHealthRules``.

        :return: an overall health of the FNDH.
        """
        base_health, base_report = super().evaluate_health()
        if not self._use_new_rules:
            # before MCCS-2245, no rules were used meaning we just returned the
            # evaluation from the HealthModel.
            return base_health, base_report

        mon_points = self._state.get("monitoring_points", {})
        rules_health, rules_report = self._get_report_from_rules(mon_points)

        if base_health == rules_health and base_health != HealthState.OK:
            # If both health states match, return them together
            return base_health, "\n".join([base_report, rules_report])

        # Return report with highest health concern.
        for health in self.ORDERED_HEALTH_PRECEDENCE:
            if health == base_health:
                return base_health, base_report

            if health == rules_health:
                return rules_health, rules_report

        # Default case if no health states matched any precedence order
        return HealthState.UNKNOWN, "No rules matched"

    @property
    def monitoring_points_with_thresholds(
        self: FndhHealthModel,
    ) -> dict[str, tuple[HealthState, str]]:
        """
        Get the monitoring points with thresholds defined.

        :return: monitoring points with thresholds defined.
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
        self: FndhHealthModel, threshold_key: str, threshold_values: np.ndarray
    ) -> None:
        """
        Update the health thresholds.

        :param threshold_key: the name of this threshold.
        :param threshold_values: a list of 4 values containing
            high_alm, high_warn, low_warn, low_alm
        """
        self._health_rules.update_thresholds(threshold_key, threshold_values)

        # re-evaluate
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
