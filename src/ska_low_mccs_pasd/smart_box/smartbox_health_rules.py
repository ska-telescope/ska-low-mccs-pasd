#  -*- coding: utf-8 -*
# pylint: disable=arguments-differ
#
# This file is part of the SKA Low MCCS PaSD project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""A file to store health rules for smartbox devices."""
from __future__ import annotations

from typing import Any

import numpy
from ska_control_model import HealthState
from ska_low_mccs_common.health import HealthRules

DEGRADED_STATES = frozenset({HealthState.DEGRADED, HealthState.FAILED, None})


class SmartboxHealthRules(HealthRules):
    """A class to handle transition rules for station."""

    def __init__(self, *args: Any, **kwargs: Any):
        """
        Initialise this device object.

        :param args: positional args to the init
        :param kwargs: keyword args to the init
        """
        super().__init__(*args, **kwargs)
        self.logger = None

    def set_logger(self: SmartboxHealthRules, logger: Any) -> None:
        """
        Set logger for debugging.

        :param logger: a logger.
        """
        self.logger = logger

    def unknown_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
    ) -> tuple[bool, str]:
        """
        Test whether UNKNOWN is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths

        :return: True if UNKNOWN is a valid state, along with a text report.
        """
        for key, value in intermediate_healths.items():
            if value[0] == HealthState.UNKNOWN:
                return (
                    True,
                    f"Intermediate health {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    def failed_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
    ) -> tuple[bool, str]:
        """
        Test whether FAILED is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths

        :return: True if FAILED is a valid state, along with a text report.
        """
        for key, value in intermediate_healths.items():
            if value[0] == HealthState.FAILED:
                return (
                    True,
                    f"Intermediate health {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    def degraded_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
    ) -> tuple[bool, str]:
        """
        Test whether DEGRADED is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths

        :return: True if DEGRADED is a valid state, along with a text report.
        """
        for key, value in intermediate_healths.items():
            if value[0] == HealthState.DEGRADED:
                return (
                    True,
                    f"Intermediate health {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    def healthy_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
    ) -> tuple[bool, str]:
        """
        Test whether OK is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths

        :return: True if OK is a valid state
        """
        if all(state == HealthState.OK for state, _ in intermediate_healths.values()):
            return True, "Health is OK"
        return False, "Health not OK"

    # pylint: disable=too-many-return-statements
    def compute_intermediate_state(
        self: SmartboxHealthRules,
        monitoring_point: str,
        monitoring_value: Any,
        min_max: dict[str, Any],
    ) -> tuple[HealthState, str]:
        """
        Compute the intermediate health state for the Smartbox.

        This is computed for a particular category of monitoring points

        :param monitoring_point: the smartbox monitoring name
        :param monitoring_value: the smartbox monitoring value
        :param min_max: minimum/maximum/expected values for the monitoring points.
            For monitoring points where a minimum/maximum doesn't make sense,
            the value provided will be that which the monitoring point is required
            to have for the device to be healthy
        :return: the computed health state and health report
        """
        if monitoring_value is None:
            return (
                HealthState.UNKNOWN,
                f"Monitoring point {monitoring_point} is None.",
            )

        if isinstance(min_max, (int, float)):
            return (
                (HealthState.OK, "")
                if monitoring_value < min_max
                else (
                    HealthState.FAILED,
                    f"Monitoring point {monitoring_point}: "
                    f"{monitoring_value} > {min_max}",
                )
            )
        if isinstance(min_max, (list, numpy.ndarray)):
            min_max.sort()

            if len(min_max) == 1:
                return (
                    (HealthState.OK, "")
                    if monitoring_value < min_max[0]
                    else (
                        HealthState.FAILED,
                        f"Monitoring point {monitoring_point}: "
                        f"{monitoring_value} > {min_max[0]}",
                    )
                )
            if len(min_max) == 4:
                # all the values are 0 or 0.0, not a point we care about
                if all(value == 0 for value in min_max):
                    return (HealthState.OK, "")

                min_fault = min_max[0]
                min_warning = min_max[1]
                max_warning = min_max[2]
                max_fault = min_max[3]

                if monitoring_value < min_fault or monitoring_value > max_fault:
                    return (
                        HealthState.FAILED,
                        f"Monitoring point {monitoring_point}: "
                        "out side of max/min values, "
                        f"value: {monitoring_value},max: {max_fault}, min: {min_fault}",
                    )
                if monitoring_value < min_warning or monitoring_value > max_warning:
                    return (
                        HealthState.DEGRADED,
                        f"Monitoring point {monitoring_point}: "
                        f"in warning range, value: {monitoring_value}, "
                        f"max: {max_warning}, min: {min_warning}",
                    )
                return (HealthState.OK, "")

        return (HealthState.UNKNOWN, "")

    def _combine_states(
        self: HealthRules, *args: tuple[HealthState, str]
    ) -> tuple[HealthState, str]:
        states = [
            HealthState.FAILED,
            HealthState.UNKNOWN,
            HealthState.DEGRADED,
            HealthState.OK,
        ]
        filtered_results = {
            state: [report for health, report in args if health == state]
            for state in states
        }
        for state in states:
            if len(filtered_results[state]) > 0:
                if state == HealthState.OK:
                    return state, ""
                return state, " | ".join(filtered_results[state])

        return (
            HealthState.UNKNOWN,
            f"No health state matches: args:{args} filtered results:{filtered_results}",
        )

    @property
    def default_thresholds(self: HealthRules) -> dict[str, float | bool]:
        """
        Get the default thresholds for this device.

        :return: the default thresholds
        """
        return {}
