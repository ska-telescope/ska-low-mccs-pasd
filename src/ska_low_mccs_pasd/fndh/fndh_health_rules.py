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


def _calculate_percent_smartbox_without_control(
    ports_with_smartbox: list[int] | None, ports_power_control: list[bool] | None
) -> int:
    """
    Return the percent of smartbox with control.

    :param ports_with_smartbox: the id of the Fndh ports
        with a smartbox attached (1 based).
    :param ports_power_control: a list of bools representing
        if we have control over the power of ports.

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

    # pylint: disable=too-many-positional-arguments, too-many-arguments
    def unknown_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        pasd_power: PowerState | None = None,
        ignore_pasd_power: bool = False,
        ports_with_smartbox: list[int] | None = None,
        ports_power_control: list[bool] | None = None,
    ) -> tuple[bool, str]:
        """
        Return True if we have UNKNOWN healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param pasd_power: The power reported by the PaSDBus.
        :param ignore_pasd_power: True if we are ignoring the rollup of the pasd
            power
        :param ports_with_smartbox: The ports configured with a smartbox.
        :param ports_power_control: Port that have control.

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

    # pylint: disable=too-many-positional-arguments, too-many-arguments
    def failed_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        pasd_power: PowerState | None = None,
        ignore_pasd_power: bool = False,
        ports_with_smartbox: list[int] | None = None,
        ports_power_control: list[bool] | None = None,
    ) -> tuple[bool, str]:
        """
        Return True if we have FAILED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param pasd_power: The power reported by the PaSDBus.
        :param ignore_pasd_power: True if we are ignoring the rollup of the pasd
            power.
        :param ports_with_smartbox: The ports configured with a smartbox.
        :param ports_power_control: Port that have control.

        :returns: True if we are in a FAILED healthstate.
        """
        percent_of_uncontrollable_smartbox = (
            _calculate_percent_smartbox_without_control(
                ports_with_smartbox=ports_with_smartbox,
                ports_power_control=ports_power_control,
            )
        )
        if (
            percent_of_uncontrollable_smartbox
            > self._thresholds["failed_percent_uncontrolled_smartbox"]
        ):
            return (
                True,
                f"Number of smartbox without control is "
                f"{percent_of_uncontrollable_smartbox}, "
                "this is above the configured limit of "
                f"{self._thresholds['failed_percent_uncontrolled_smartbox']}.",
            )
        for key, value in monitoring_points.items():
            if value[0] == HealthState.FAILED:
                return (
                    True,
                    f"Monitoring point {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    # pylint: disable=too-many-positional-arguments, too-many-arguments
    def degraded_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        pasd_power: PowerState | None = None,
        ignore_pasd_power: bool = False,
        ports_with_smartbox: list[int] | None = None,
        ports_power_control: list[bool] | None = None,
    ) -> tuple[bool, str]:
        """
        Return True if we have DEGRADED healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param pasd_power: The power reported by the PaSDBus.
        :param ignore_pasd_power: True if we are ignoring the rollup of the pasd
            power.
        :param ports_with_smartbox: The ports configured with a smartbox.
        :param ports_power_control: Port that have control.

        :returns: True if we are in a DEGRADED healthstate.
        """
        percent_of_uncontrollable_smartbox = (
            _calculate_percent_smartbox_without_control(
                ports_with_smartbox=ports_with_smartbox,
                ports_power_control=ports_power_control,
            )
        )
        print(f"{percent_of_uncontrollable_smartbox=}")
        if (
            percent_of_uncontrollable_smartbox
            > self._thresholds["degraded_percent_uncontrolled_smartbox"]
        ):
            return (
                True,
                "Number of smartbox without control is "
                f"{percent_of_uncontrollable_smartbox }, "
                "this is above the configured limit of "
                f"{self._thresholds['degraded_percent_uncontrolled_smartbox']}.",
            )

        if (
            (not ignore_pasd_power)
            and (pasd_power is not None)
            and (pasd_power == PowerState.UNKNOWN)
        ):
            return (
                True,
                "The PaSDBus has a UNKNOWN PowerState. "
                "FNDH HealthState evaluated as DEGRADED.",
            )
        for key, value in monitoring_points.items():
            if value[0] == HealthState.DEGRADED:
                return (
                    True,
                    f"Monitoring point {key} is in "
                    f"{value[0].name} HealthState. "
                    f"Cause: {value[1]}",
                )
        return False, ""

    # pylint: disable=too-many-positional-arguments, too-many-arguments
    def healthy_rule(  # type: ignore[override]
        self: FndhHealthRules,
        monitoring_points: dict[str, Any],
        pasd_power: PowerState | None = None,
        ignore_pasd_power: bool = False,
        ports_with_smartbox: list[int] | None = None,
        ports_power_control: list[bool] | None = None,
    ) -> tuple[bool, str]:
        """
        Return True if we have OK healthstate.

        :param monitoring_points: A dictionary containing the monitoring points.
        :param pasd_power: The power reported by the PaSDBus.
        :param ignore_pasd_power: True if we are ignoring the rollup of the pasd
            power
        :param ports_with_smartbox: The ports configured with a smartbox.
        :param ports_power_control: Port that have control.

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
        self: FndhHealthRules, threshold_name: str, threshold_value: np.ndarray
    ) -> None:
        """
        Update the thresholds for attributes.

        :param threshold_name: the name of the threshold to update
        :param threshold_value: A numpy.array containing the
            [max_alm, max_warn, min_warn, min_alm]
        """
        self._thresholds[threshold_name] = threshold_value.tolist()
