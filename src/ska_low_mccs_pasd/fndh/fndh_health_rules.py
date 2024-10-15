#  -*- coding: utf-8 -*
# pylint: disable=arguments-differ
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""A file to store health transition rules for station."""
from __future__ import annotations

from typing import Any

from ska_control_model import HealthState
from ska_low_mccs_common.health import HealthRules


class FndhHealthRules(HealthRules):
    """A class to handle transition rules for the FNDH."""

    def __init__(self, *args: Any, **kwargs: Any):
        """
        Initialise this device object.

        :param args: positional args to the init
        :param kwargs: keyword args to the init
        """
        super().__init__(*args, **kwargs)
        self.logger = None
        self._thresholds: dict[str, Any]

    def unknown_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Return True if we have UNKNOWN healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.

        :returns: True if we are in a UNKNOWN healthstate.
        """
        # Check if we are UNKNOWN
        for attribute_name, attr_health_info in monitoring_points.items():
            if attr_health_info[0] == HealthState.UNKNOWN:
                return (
                    True,
                    f"Monitoring point {attribute_name} is in "
                    f"{attr_health_info[0].name} HealthState. "
                    f"Cause: {attr_health_info[1]}",
                )
        return False, ""

    def failed_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Return True if we have FAILED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.

        :returns: True if we are in a FAILED healthstate.
        """
        for key, value in monitoring_points.items():
            if value[0] == HealthState.FAILED:
                return (
                    True,
                    f"Monitoring point {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    def degraded_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Return True if we have DEGRADED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.

        :returns: True if we are in a DEGRADED healthstate.
        """
        for key, value in monitoring_points.items():
            if value[0] == HealthState.DEGRADED:
                return (
                    True,
                    f"Monitoring point {key} is in "
                    f"{value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    def healthy_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Return True if we have OK healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.

        :returns: True if we are in a OK healthstate.
        """
        if all(state == HealthState.OK for state, _ in monitoring_points.values()):
            return True, "Health is OK"
        return False, "Health not OK"

    def compute_intermediate_state(
        self: FndhHealthRules,
        monitoring_point: float,
        thresholds: list[float],
    ) -> tuple[HealthState, str]:
        """
        Compute the Monitoring point state for the FNDH.

        :param monitoring_point: the monitoring point to evaluate.
        :param thresholds: the thresholds defined for this attribute to
            evaluate the monitoring point against.

        :return: the computed health state and health report
        """
        if monitoring_point is None:
            return (HealthState.OK, "Monitoring point has not yet been updated")
        max_alm, max_warn, min_warn, min_alm = thresholds

        if (monitoring_point >= max_warn) or (monitoring_point <= min_warn):
            if (monitoring_point >= max_alm) or (monitoring_point <= min_alm):
                return (
                    HealthState.FAILED,
                    f"Monitoring point has value {monitoring_point}, "
                    "this is in the alarm region for thresholds "
                    f"{max_alm=}, {min_alm=}",
                )
            return (
                HealthState.DEGRADED,
                f"Monitoring point has value {monitoring_point}, "
                "this is in the warning region for thresholds "
                f"{max_warn=}, {min_warn=}",
            )
        return (
            HealthState.OK,
            f"Monitoring point has value {monitoring_point}, this is within limits",
        )

    def update_thresholds(
        self: FndhHealthRules, threshold_name: str, threshold_value: list[float]
    ) -> None:
        """
        Update the thresholds for attributes.

        :param threshold_name: the name of the threshold to update
        :param threshold_value: A list containing the
            [max_alm, max_warn, min_warn, min_alm]
        """
        print(f"oisadhoiash {threshold_name=},{threshold_value=}")
        self._thresholds[threshold_name] = threshold_value
