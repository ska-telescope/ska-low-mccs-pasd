# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a FNDH."""
from __future__ import annotations

import logging
from typing import Any, Final

import numpy as np
from ska_control_model import HealthState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol

from .fndh_health_rules import FndhHealthRules, join_health_reports


class FndhHealthModel(BaseHealthModel):
    """
    The health model for a FNDH.

    The health model will contain a dictionary _state
    containing data to feed the healthRules.
    The monitoring_points key maps to a dictionary
    containing the current attribute values which are
    checked against the alarm thresholds. The
    portspowersensed attribute is used to determine
    if the smartbox on the attached port is
    controllable.

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

    # This dictionary contains a list of the FNDH monitoring points supported.
    SUPPORTED_MONITORING_POINTS: Final[dict[str, Any]] = {
        "psu48vvoltage1": None,
        "psu48vvoltage2": None,
        "psu48vcurrent": None,
        "psu48vtemperature1": None,
        "psu48vtemperature2": None,
        "paneltemperature": None,
        "fncbtemperature": None,
        "fncbhumidity": None,
        "commsgatewaytemperature": None,
        "powermoduletemperature": None,
        "outsidetemperature": None,
        "internalambienttemperature": None,
    }

    def __init__(
        self: FndhHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: the logger to use.
        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        """
        self._logger = logger
        self._use_new_rules = True
        self._health_rules: FndhHealthRules = FndhHealthRules(
            self._logger, dict(self.SUPPORTED_MONITORING_POINTS)
        )

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

    def _get_report_from_rules(self: FndhHealthModel) -> tuple[HealthState, str]:
        for health_value in self.ORDERED_HEALTH_PRECEDENCE:
            result, report = self._health_rules.rules[health_value](
                monitoring_points=self.monitoring_points_health_status,
                pasd_power=self._state.get("pasd_power"),
                ignore_pasd_power=self._state.get("ignore_pasd_power"),
                ports_with_smartbox=self._state.get("ports_with_smartbox"),
                ports_power_control=self._state.get("monitoring_points", {}).get(
                    "portspowercontrol"
                ),
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

        rules_health, rules_report = self._get_report_from_rules()

        if base_health == rules_health:
            # If both health states match, return them together
            return base_health, join_health_reports([base_report, rules_report])

        # Return report with highest health concern.
        for health in self.ORDERED_HEALTH_PRECEDENCE:
            if health == base_health:
                return base_health, base_report

            if health == rules_health:
                return rules_health, rules_report

        # Default case if no health states matched any precedence order
        return HealthState.UNKNOWN, "No rules matched"

    @property
    def monitoring_points_health_status(
        self: FndhHealthModel,
    ) -> dict[str, tuple[HealthState, str]]:
        """
        Return a dictionary containing health information about monitoring points.

        For monitoring points with a threshold defined evaluates the health of
        and add to a dictionary.

        :return: health information about monitoring points.
        """
        mon_points = self._state.get("monitoring_points", {})
        return {
            attribute_name: self._health_rules.compute_monitoring_point_health(
                monitoring_point_name=attribute_name,
                monitoring_point=mon_points.get(attribute_name),
                thresholds=self.health_params.get(attribute_name),
            )
            for attribute_name in self.SUPPORTED_MONITORING_POINTS
        }

    def update_monitoring_point_threshold(
        self: FndhHealthModel, monitoring_point: str, threshold_values: np.ndarray
    ) -> None:
        """
        Update the monitoring point threshold.

        :param monitoring_point: the name of this monitoring point.
        :param threshold_values: a list of 4 values containing
            high_alm, high_warn, low_warn, low_alm
        """
        if monitoring_point not in self.SUPPORTED_MONITORING_POINTS:
            self._logger.warning(
                f"Monitoring point {monitoring_point} is not "
                "supported by the health rules"
            )
            return

        self._health_rules.update_monitoring_point_thresholds(
            monitoring_point, threshold_values
        )

        # re-evaluate
        self.evaluate_health()

    @property
    def health_params(self: FndhHealthModel) -> dict[str, Any]:
        """
        Get the thresholds for health rules.

        :return: the thresholds for health rules
        """
        return self._health_rules.thresholds

    @health_params.setter
    def health_params(self: FndhHealthModel, params: dict[str, Any]) -> None:
        """
        Set the thresholds for health rules.

        :param params: A dictionary of parameters with the param name as key and
            threshold as value
        """
        self._health_rules.thresholds = self._merge_dicts(
            self._health_rules.thresholds, params
        )
