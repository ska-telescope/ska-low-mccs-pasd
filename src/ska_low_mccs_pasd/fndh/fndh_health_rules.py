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

import logging
from typing import Any, Final

import numpy as np
from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.health import HealthRules

__all__ = ["FndhHealthRules", "join_health_reports"]


def merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]) -> dict[str, Any]:
    """
    Return a new dictionary containing a merged dictionary.

    :param dict1: first dictionary to merge.
    :param dict2: second dictionary to merge.

    :returns: a dictionary containing the merge of dict1 and dict2
    """
    return {**dict1, **dict2}


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


# pylint: disable=too-few-public-methods
class FndhHealthData:
    """A class containing data used by the healthRules."""

    # Default percentages of uncontrolled smartboxes
    # required for degraded and failed status
    DEFAULT_DEGRADED_PERCENT_UNCONTROLLED_SMARTBOX = 0
    DEFAULT_FAILED_PERCENT_UNCONTROLLED_SMARTBOX = 20


class FndhHealthRules(HealthRules):
    """A class to handle transition rules for the FNDH."""

    DEFAULT_THRESHOLD_VALUES: Final[dict[str, int]] = {
        "failed_percent_uncontrolled_smartbox": (
            FndhHealthData.DEFAULT_FAILED_PERCENT_UNCONTROLLED_SMARTBOX
        ),
        "degraded_percent_uncontrolled_smartbox": (
            FndhHealthData.DEFAULT_DEGRADED_PERCENT_UNCONTROLLED_SMARTBOX
        ),
    }

    def __init__(
        self,
        logger: logging.Logger,
        monitoring_points: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ):
        """
        Initialise this device object.

        :param logger: the logger to use.
        :param monitoring_points: a dictionary containing
            the monitoring points to evaluate.
        :param args: positional args to the init
        :param kwargs: keyword args to the init
        """
        super().__init__(*args, **kwargs)

        self._thresholds = dict(
            merge_dicts(monitoring_points, self.DEFAULT_THRESHOLD_VALUES)
        )
        self._logger = logger

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
        thresholds: list[float] | None,
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
        if thresholds is None:
            return (
                HealthState.UNKNOWN,
                f"Thresholds for {monitoring_point_name} have not yet been updated."
                "We should transition out of this state once we have polled "
                " the hardware for this information.",
            )
        if monitoring_point is None:
            return (
                HealthState.UNKNOWN,
                f"Monitoring point {monitoring_point_name} has not yet been updated.",
            )

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

    def update_monitoring_point_thresholds(
        self: FndhHealthRules, attribute_name: str, threshold_value: np.ndarray
    ) -> None:
        """
        Update the thresholds for monitoring points.

        :param attribute_name: the name of the threshold to update
        :param threshold_value: A numpy.array containing the
            [max_alm, max_warn, min_warn, min_alm]
        """
        old_threshold = self._thresholds[attribute_name]
        new_threshold = threshold_value.tolist()

        self.thresholds = {attribute_name: new_threshold}

        if old_threshold is None:
            self._logger.info(
                f"Threshold for {attribute_name} has been "
                f"initiailsed to {new_threshold}"
            )
        else:
            self._logger.info(
                f"Threshold for {attribute_name} has being updated "
                f"from {old_threshold} to {new_threshold}"
            )

    @property
    def thresholds(self) -> dict[str, Any]:
        """
        Return the threshold values.

        :returns: the merged results of both the monitoring_thresholds
            and _thresholds dictionarys.
        """
        return self._thresholds

    @thresholds.setter
    def thresholds(self, thresholds: dict[str, Any]) -> None:
        """
        Set the threshold values.

        :param thresholds: a dictionary containing the thresholds to set
        """
        threshold_to_update = {}
        for key, value in thresholds.items():
            if key not in self._thresholds:
                self._logger.error(f"{key=} is not supported by FNDH health rules.")
                continue
            threshold_to_update[key] = value
        self._thresholds.update(threshold_to_update)
