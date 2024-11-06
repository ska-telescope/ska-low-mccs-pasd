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

import numpy as np
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.health import HealthRules


def _join_health_messages(messages: list[str]) -> str:
    return "\n".join(messages)


def _calculate_percent_smartbox_without_control(
    ports_with_smartbox: list[int] | None, ports_power_control: list[bool] | None
) -> int:
    """
    Return the percent of smartbox with control.

    :param ports_with_smartbox: a list of the ids of the Fndh
        ports with a smartbox attached (1 based).
    :param ports_power_control: a list of bools, one per
        Fndh port, each one representing if we have control
        over its power (0 based).

    :return: the percent of smartboxes with power control
        to the nearest integer.
    """
    if (
        ports_with_smartbox is None
        or len(ports_with_smartbox) == 0
        or ports_power_control is None
    ):
        return 0
    nof_smartbox_without_control = 0
    for port_no in ports_with_smartbox:
        if not ports_power_control[port_no - 1]:
            nof_smartbox_without_control += 1
    return int((nof_smartbox_without_control * 100) / len(ports_with_smartbox))


class FndhHealthRules(HealthRules):
    """A class to handle transition rules for the FNDH."""

    # Default percentages of uncontrolled smartboxes
    # required for degraded and failed status
    DEFAULT_DEGRADED_PERCENT_UNCONTROLLED_SMARTBOX = 0
    DEFAULT_FAILED_PERCENT_UNCONTROLLED_SMARTBOX = 20

    def __init__(self, *args: Any, **kwargs: Any):
        """
        Initialise this device object.

        :param args: positional args to the init
        :param kwargs: keyword args to the init
        """
        super().__init__(*args, **kwargs)
        self.logger = None
        self._thresholds: dict[str, Any]
        self._thresholds[
            "failed_percent_uncontrolled_smartbox"
        ] = self.DEFAULT_FAILED_PERCENT_UNCONTROLLED_SMARTBOX
        self._thresholds[
            "degraded_percent_uncontrolled_smartbox"
        ] = self.DEFAULT_DEGRADED_PERCENT_UNCONTROLLED_SMARTBOX

    def unknown_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have UNKNOWN healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.

        :returns: True if we are in a UNKNOWN healthstate.
        """
        unknown_points: list[str] = []
        # Iterate over monitoring points and check for UNKNOWN health state
        for attribute_name, attr_health_info in monitoring_points.items():
            if attr_health_info[0] == HealthState.UNKNOWN:
                unknown_points.append(
                    f"Monitoring point {attribute_name} is in "
                    f"{attr_health_info[0].name} HealthState. "
                    f"Cause: {attr_health_info[1]}"
                )

        # If there are any UNKNOWN points, return True and a concatenated message
        if unknown_points:
            return True, _join_health_messages(unknown_points)

        # Return False and an empty message if no UNKNOWN points found
        return False, ""

    def failed_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have FAILED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.

        :returns: True if we are in a FAILED healthstate.
        """
        failed_points: list[str] = []
        percent_of_uncontrollable_smartbox = (
            _calculate_percent_smartbox_without_control(
                ports_with_smartbox=kwargs.get("ports_with_smartbox"),
                ports_power_control=kwargs.get("ports_power_control"),
            )
        )
        if (
            percent_of_uncontrollable_smartbox
            > self._thresholds["failed_percent_uncontrolled_smartbox"]
        ):
            failed_points.append(
                f"Number of smartbox without control is "
                f"{percent_of_uncontrollable_smartbox}, "
                "this is above the configured limit of "
                f"{self._thresholds['failed_percent_uncontrolled_smartbox']}."
            )

        for key, value in monitoring_points.items():
            if value[0] == HealthState.FAILED:
                failed_points.append(
                    f"Monitoring point {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}"
                )

        # If there are any FAILED points, return True and a concatenated message
        if failed_points:
            return True, _join_health_messages(failed_points)

        # Return False and an empty message if no FAILED points found
        return False, ""

    def degraded_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have DEGRADED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.
        :returns: True if we are in a DEGRADED healthstate.
        """
        degraded_points: list[str] = []

        percent_of_uncontrollable_smartbox = (
            _calculate_percent_smartbox_without_control(
                ports_with_smartbox=kwargs.get("ports_with_smartbox"),
                ports_power_control=kwargs.get("ports_power_control"),
            )
        )
        if (
            percent_of_uncontrollable_smartbox
            > self._thresholds["degraded_percent_uncontrolled_smartbox"]
        ):
            degraded_points.append(
                "Number of smartbox without control is "
                f"{percent_of_uncontrollable_smartbox }, "
                "this is above the configured limit of "
                f"{self._thresholds['degraded_percent_uncontrolled_smartbox']}."
            )

        if (not kwargs.get("ignore_pasd_power", False)) and (
            kwargs.get("pasd_power") == PowerState.UNKNOWN
        ):
            degraded_points.append(
                "The PaSDBus has a UNKNOWN PowerState. "
                "FNDH HealthState evaluated as DEGRADED."
            )
        for key, value in monitoring_points.items():
            if value[0] == HealthState.DEGRADED:
                degraded_points.append(
                    f"Monitoring point {key} is in "
                    f"{value[0].name} HealthState. "
                    f"Cause: {value[1]}"
                )
        # If there are any DEGRADED points, return True and a concatenated message
        if degraded_points:
            return True, _join_health_messages(degraded_points)

        # Return False and an empty message if no DEGRADED points found
        return False, ""

    def healthy_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have OK healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.

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
                    HealthState.DEGRADED,
                    f"Monitoring point has value {monitoring_point}, "
                    "this is in the alarm region for thresholds "
                    f"{max_alm=}, {min_alm=}",
                )
            return (
                HealthState.OK,
                f"Monitoring point has value {monitoring_point}, "
                "this is in the warning region for thresholds "
                f"{max_warn=}, {min_warn=}",
            )
        return (
            HealthState.OK,
            f"Monitoring point has value {monitoring_point}, this is within limits",
        )

    def update_thresholds(
        self: FndhHealthRules, attribute_name: str, threshold_value: np.ndarray
    ) -> None:
        """
        Update the thresholds for attributes.

        :param attribute_name: the name of the threshold to update
        :param threshold_value: A numpy.array containing the
            [max_alm, max_warn, min_warn, min_alm]
        """
        self._thresholds[attribute_name] = threshold_value.tolist()
