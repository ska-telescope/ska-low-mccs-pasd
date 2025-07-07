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

from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import SmartboxStatusMap
from ska_low_mccs_pasd.pasd_utils import join_health_reports


class SmartboxHealthRules(HealthRules):
    """A class to handle transition rules for station."""

    # Status register mapping to health:
    # UNINITIALISED -> OK
    # OK -> OK
    # WARNING -> DEGRADED
    # ALARM -> FAILED
    # RECOVERY -> FAILED
    # POWERDOWN -> UNKNOWN (this should not be seen in normal operation)

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
        status: str | None,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Test whether UNKNOWN is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths
        :param status: reported value of the status register
        :param kwargs: kwargs containing additional parameters

        :return: True if UNKNOWN is a valid state, along with a text report.
        """
        unknown_points: list[str] = []
        port_breakers_tripped: list[bool] | None = kwargs.get(
            "port_breakers_tripped", None
        )

        if status is None:
            unknown_points.append(
                "No value has been read from the pasdStatus register."
            )
        elif status == SmartboxStatusMap.POWERDOWN.name:
            unknown_points.append(
                f"Smartbox is in {SmartboxStatusMap.POWERDOWN.name} state."
            )
        elif status not in SmartboxStatusMap.__members__:
            unknown_points.append(f"Smartbox is reporting unknown status: {status}")

        if port_breakers_tripped is None:
            unknown_points.append(
                "No value has been read from the port breakers tripped register."
            )

        for key, value in intermediate_healths.items():
            if value[0] == HealthState.UNKNOWN:
                unknown_points.append(
                    f"Intermediate health {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}"
                )
        if unknown_points:
            return True, join_health_reports(unknown_points)
        return False, ""

    def failed_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Test whether FAILED is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths
        :param kwargs: kwargs containing additional parameters

        :return: True if FAILED is a valid state, along with a text report.
        """
        status = kwargs.get("status")
        port_breakers_tripped: list[bool] = kwargs.get("port_breakers_tripped", [])
        failed_points: list[str] = []

        if status in [SmartboxStatusMap.ALARM.name, SmartboxStatusMap.RECOVERY.name]:
            failed_points.append(f"Smartbox is reporting {status}.")

        if port_breakers_tripped is not None and any(port_breakers_tripped):
            tripped_ports = [
                port
                for port, tripped in enumerate(port_breakers_tripped, start=1)
                if tripped
            ]
            failed_points.append(
                f"FEM circuit breakers have tripped on ports {tripped_ports}"
            )

        for key, value in intermediate_healths.items():
            if value[0] == HealthState.FAILED:
                failed_points.append(
                    f"Intermediate health {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}"
                )
        if failed_points:
            return True, join_health_reports(failed_points)
        return False, ""

    def degraded_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Test whether DEGRADED is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths
        :param kwargs: kwargs containing additional parameters

        :return: True if DEGRADED is a valid state, along with a text report.
        """
        status = kwargs.get("status")
        degraded_points: list[str] = []
        if status == SmartboxStatusMap.WARNING.name:
            degraded_points.append(f"Smartbox is reporting {status}.")

        for key, value in intermediate_healths.items():
            if value[0] == HealthState.DEGRADED:
                degraded_points.append(
                    f"Intermediate health {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}"
                )
        if degraded_points:
            return True, join_health_reports(degraded_points)
        return False, ""

    def healthy_rule(  # type: ignore[override]
        self: SmartboxHealthRules,
        intermediate_healths: dict[str, tuple[HealthState, str]],
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """
        Test whether OK is valid for the smartbox.

        :param intermediate_healths: dictionary of intermediate healths
        :param kwargs: kwargs containing additional parameters

        :return: True if OK is a valid state
        """
        messages: list[str] = []
        states: list[bool] = []

        status = kwargs.get("status")
        states.append(
            status in [SmartboxStatusMap.OK.name, SmartboxStatusMap.UNINITIALISED.name]
        )
        messages.append(f"Smartbox is reporting {status}")

        # Iterate through monitoring_points, appending to messages and states
        for state, message in intermediate_healths.values():
            messages.append(message)
            states.append(state == HealthState.OK)

        # 'Health is OK' message is added by the BaseHealthModel
        return all(states), join_health_reports(messages)

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
            sorted_min_max = sorted(min_max)

            if len(sorted_min_max) == 1:
                return (
                    (HealthState.OK, "")
                    if monitoring_value < sorted_min_max[0]
                    else (
                        HealthState.FAILED,
                        f"Monitoring point {monitoring_point}: "
                        f"{monitoring_value} > {sorted_min_max[0]}",
                    )
                )
            if len(sorted_min_max) == 4:
                # all the values are 0 or 0.0, not a point we care about
                if all(value == 0 for value in sorted_min_max):
                    return (HealthState.OK, "")

                min_alm = sorted_min_max[0]
                min_warn = sorted_min_max[1]
                max_warn = sorted_min_max[2]
                max_alm = sorted_min_max[3]

                if monitoring_value < min_alm or monitoring_value > max_alm:
                    return (
                        HealthState.FAILED,
                        f"Monitoring point {monitoring_point}: "
                        f"outside of max/min values, value: {monitoring_value}, "
                        f"max: {max_alm}, min: {min_alm}",
                    )
                if monitoring_value < min_warn:
                    return (
                        HealthState.DEGRADED,
                        f"Monitoring point {monitoring_point}: "
                        f"in warning range, min fault: {min_alm} < "
                        f"value: {monitoring_value} < min warning: {min_warn}",
                    )
                if monitoring_value > max_warn:
                    return (
                        HealthState.DEGRADED,
                        f"Monitoring point {monitoring_point}: "
                        f"in warning range, max fault: {max_alm} > "
                        f"value: {monitoring_value} > max warning: {max_warn}",
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
