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

__all__ = ["FndhHealthRules", "join_health_reports"]


def join_health_reports(messages: list[str]) -> str:
    """
    Join the messages removing duplicates and empty strings.

    :param messages: a list of messages.

    :returns: a string with result.
    """
    seen = set()
    unique_messages = []

    for message in messages:
        # Ignore empty strings and duplicates
        if message and message not in seen:
            seen.add(message)
            unique_messages.append(message)

    return "\n".join(unique_messages)


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
        monitoring_points: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have UNKNOWN healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.

        :returns: True if we are in a UNKNOWN healthstate.

        :example:
            >>> monitoring_points = {
            >>>     "portspowercontrol": (HealthState.OK, ""),
            >>>     "psu48vvoltage1": (HealthState.FAILED, "too high"),
            >>>     ...
            >>> }
            >>> kwargs = {
            >>>    ...
            >>> }
            >>> unknown_rule(monitoring_points=monitoring_points, **kwargs)
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
            return True, join_health_reports(unknown_points)

        # Return False and an empty message if no UNKNOWN points found
        return False, ""

    def failed_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have FAILED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.

        :returns: True if we are in a FAILED healthstate.

        :example:
            >>> monitoring_points = {
            >>>     "portspowercontrol": (HealthState.OK, ""),
            >>>     "psu48vvoltage1": (HealthState.FAILED, "too high"),
            >>>     ...
            >>> }
            >>> kwargs = {
            >>>    "ports_with_smartbox": [1,2,6],
            >>>    "ports_power_control": [True]*28,
            >>> }
            >>> failed_rule(monitoring_points=monitoring_points, **kwargs)
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
            return (
                True,
                join_health_reports(failed_points)
                or "Health is failed with no extra information",
            )

        # Return False and an empty message if no FAILED points found
        return False, ""

    def degraded_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have DEGRADED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.
        :returns: True if we are in a DEGRADED healthstate.

        :example:
            >>> monitoring_points = {
            >>>     "portspowercontrol": (HealthState.OK, ""),
            >>>     "psu48vvoltage1": (HealthState.FAILED, "too high"),
            >>>     ...
            >>> }
            >>> kwargs = {
            >>>    "pasd_power": PowerState.ON,
            >>>    "ignore_pasd_power": True,
            >>>    "ports_with_smartbox": [1,2,6],
            >>>    "ports_power_control": [True]*28,
            >>> }
            >>> degraded_rule(monitoring_points=monitoring_points, **kwargs)
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
            return (
                True,
                join_health_reports(degraded_points)
                or "Health is degraded with no extra information",
            )

        # Return False and an empty message if no DEGRADED points found
        return False, ""

    def healthy_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Return True if we have OK healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param kwargs: optional kwargs.

        :returns: True if we are in a OK healthstate.

        :example:
            >>> monitoring_points = {
            >>>     "portspowercontrol": (HealthState.OK, ""),
            >>>     "psu48vvoltage1": (HealthState.FAILED, "too high"),
            >>>     ...
            >>> }
            >>> kwargs = {
            >>>    ...
            >>> }
            >>> healthy_rule(monitoring_points=monitoring_points, **kwargs)
        """
        messages: list[str] = []
        states: list[bool] = []

        # Iterate through monitoring_points, appending to messages and states
        for state, message in monitoring_points.values():
            messages.append(message)
            states.append(state == HealthState.OK)

        if all(states):
            return True, join_health_reports(messages) or "Health is OK"
        return False, "Health not OK"

    def compute_monitoring_point_health(
        self: FndhHealthRules,
        monitoring_point_name: str,
        monitoring_point: float | None,
        thresholds: list[float],
    ) -> tuple[HealthState, str]:
        """
        Compute the Health of a monitoring point.

        A monitoring point is evaluated against a set of thresolds
        with structure [high_alm, high_warn, low_warn, low_alm].
        If the monitoring point is above specified max_alm or
        below min_alm it is HealthState.FAILED.
        If the monitoring point is max_alm > p >= max_warn or
        min_warn >= p > min_alm it is HealthState.DEGRADED.
        Otherwise we return HealthState.OK with an informational message.

        :param monitoring_point_name: the name of the monitoring point.
        :param monitoring_point: the monitoring point value to evaluate.
        :param thresholds: the thresholds defined for this attribute.

        :return: the computed health state and health report
        """
        if monitoring_point is None:
            return (HealthState.OK, "")
        max_alm, max_warn, min_warn, min_alm = thresholds

        if (monitoring_point >= max_warn) or (monitoring_point <= min_warn):
            if (monitoring_point >= max_alm) or (monitoring_point <= min_alm):
                return (
                    HealthState.FAILED,
                    f"Monitoring point {monitoring_point_name} has value "
                    f"{monitoring_point}, this is in the alarm region for thresholds "
                    f"{max_alm=}, {min_alm=}",
                )
            return (
                HealthState.DEGRADED,
                f"Monitoring point {monitoring_point_name} has value "
                f"{monitoring_point}, this is in the warning region for thresholds "
                f"{max_warn=}, {min_warn=}",
            )
        return (
            HealthState.OK,
            f"Monitoring point {monitoring_point_name} has value "
            f"{monitoring_point}, this is within limits",
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
