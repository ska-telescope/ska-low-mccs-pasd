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
from ska_control_model import HealthState
from ska_low_mccs_common.health import HealthRules

from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import FndhStatusMap
from ska_low_mccs_pasd.pasd_utils import join_health_reports

__all__ = ["FndhHealthRules", "join_health_reports"]


def merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]) -> dict[str, Any]:
    """
    Return a new dictionary containing a merged dictionary.

    :param dict1: first dictionary to merge.
    :param dict2: second dictionary to merge.

    :returns: a dictionary containing the merge of dict1 and dict2
    """
    return {**dict1, **dict2}


def _calculate_pdoc_fault(
    power_sensed: bool, power_control: bool, port_number: int
) -> tuple[bool, str]:
    """
    Calculate if the pdoc is faulty.

    Below is a summary of evaluation:

    :example:
        >>> [power_sensed, power_control] -> isFaulty:
        >>> [True, True] -> False
        >>> [False, True] -> True, PDOC stuck OFF,
        >>> could be a fault within the PDOC, damaged PDOC cable, or faulty SMART Box EP
        >>> [True, False] -> True, PDOC stuck ON, fault within the PDOC,
        >>> cannot turn OFF PDOC port
        >>> in response to a POWERDOWN from the SMART Box
        >>> [False, False] -> False


    :param power_sensed: PDOC Hot Swap Controller ON/OFF.
        False is OFF, True is ON.
    :param power_control: PDOC port power control ON/OFF.
        False = Control line to PDOC is OFF. PDOC port cannot be turned ON.
        True = Control line to PDOC is ON. PDOC port can be turned ON
    :param port_number: the id given to the port of interest,
        for informational purposes only.

    :returns: a tuple with the fault state of the pdoc port and
        a message with information.
    """
    if power_control and not power_sensed:
        return (
            True,
            (
                f"PDOC {port_number} stuck OFF, "
                "could be a fault within the PDOC, "
                "damaged PDOC cable, or faulty SMART Box EP"
            ),
        )
    if power_sensed and not power_control:
        return (
            True,
            (
                f"PDOC {port_number} stuck ON, "
                "fault within the PDOC, "
                "cannot turn OFF PDOC port "
                "in response to a POWERDOWN from the SMART Box"
            ),
        )
    # Port is considered ok, no information required.
    return False, ""


def _get_faulty_smartbox_reports(
    ports_with_smartbox: list[int],
    ports_power_sensed: list[bool],
    ports_power_control: list[bool],
) -> list[tuple[int, str]]:
    """
    Return a fault report for faulty smartbox.

    :param ports_with_smartbox: a list of the ids of the Fndh
        ports with a smartbox attached (1 based).
    :param ports_power_sensed: a list for booleans to represent
        the state of the PDOC Hot Swap Controller True being ON.
    :param ports_power_control: a list for booleans to represent
        the state of the PDOC port power control, True being ON.

    :returns: a list of tuples containing the faulty port with
        a message for information
    """
    report: list[tuple[int, str]] = []

    for port_no in ports_with_smartbox:
        power_control = ports_power_control[port_no - 1]
        power_sensed = ports_power_sensed[port_no - 1]
        is_faulty, message = _calculate_pdoc_fault(
            power_sensed=power_sensed,
            power_control=power_control,
            port_number=port_no,
        )
        if is_faulty:
            report.append((port_no, message))

    return report


def _generate_smartbox_pdoc_fault_report(
    percentage_threshold: float,
    ports_with_smartbox: list[int],
    ports_power_sensed: list[bool],
    ports_power_control: list[bool],
) -> str | None:
    """
    Return a fault report when exceeding thresholds.

    :param percentage_threshold: the percentage threshold to
        check the fault smarbox configured ports against.
    :param ports_with_smartbox: a list of the ids of the Fndh
        ports with a smartbox attached (1 based).
    :param ports_power_sensed: a list for booleans to represent
        the state of the PDOC Hot Swap Controller True being ON.
    :param ports_power_control: a list for booleans to represent
        the state of the PDOC port power control, True being ON.

    :return: a string with the fault report, or None if
        the number of faults do not exceed thresholds.
    """
    faulty_ports: tuple = ()
    fault_reports: tuple = ()

    faulty_smartbox_reports: list[tuple[int, str]] = _get_faulty_smartbox_reports(
        ports_with_smartbox=ports_with_smartbox,
        ports_power_sensed=ports_power_sensed,
        ports_power_control=ports_power_control,
    )
    if faulty_smartbox_reports:
        faulty_ports, fault_reports = zip(*faulty_smartbox_reports, strict=True)

    percent_of_faulty_smartbox_ports = _calculate_percent_faulty_smartbox_ports(
        len(faulty_ports), len(ports_with_smartbox)
    )

    if percent_of_faulty_smartbox_ports > percentage_threshold:
        return (
            f"Percent of faulty smartbox-configured-ports is "
            f"{percent_of_faulty_smartbox_ports}%, "
            "this is above the configurable threshold of "
            f"{percentage_threshold}%. Details: ["
            f"{fault_reports}]"
        )
    return None


def _calculate_percent_faulty_smartbox_ports(
    number_of_faulty_smartbox_configured_ports: int,
    number_of_smartbox_configured_ports: int,
) -> int:
    """
    Return the percent of faulty ports.

    :param number_of_faulty_smartbox_configured_ports: a integer
        representing the number of smartbox configured ports
        without control.
    :param number_of_smartbox_configured_ports: an integer
        representing the number of smartbox configured ports.

    :return: the percent of smartboxes with power control
        to the nearest integer.

    :raises ValueError: when the number of faulty smartbox configured ports
        is larger than the number of smartbox configured ports.
    """
    if number_of_smartbox_configured_ports == 0:
        return 0

    if number_of_faulty_smartbox_configured_ports > number_of_smartbox_configured_ports:
        raise ValueError(
            "Number of faulty smartbox configured ports exceeds "
            "the total number of smartbox configured ports."
        )

    faulty_smartbox_fraction = (
        number_of_faulty_smartbox_configured_ports / number_of_smartbox_configured_ports
    )

    return int(faulty_smartbox_fraction * 100)


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

    # Status register mapping to health:
    # UNINITIALISED -> OK
    # OK -> OK
    # WARNING -> DEGRADED
    # ALARM -> FAILED
    # RECOVERY -> FAILED
    # POWERUP -> UNKNOWN (this should not be seen in normal operation)

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

        ports_power_sensed = kwargs.get("ports_power_sensed")
        ports_power_control = kwargs.get("ports_power_control")
        ports_with_smartbox = kwargs.get("ports_with_smartbox")
        pasd_status = kwargs.get("status")

        if ports_with_smartbox is None:
            unknown_points.append(
                "Unable to determine health, "
                "We have no information about the ports with smartbox configured."
                "Suggested debug hint: Check the portsWithSmartbox attribute."
                "This should be written to by FieldStation."
            )

        if (
            ports_power_sensed is None
            or ports_power_control is None
            or ports_with_smartbox is None
        ):
            # Unable to determine if smartbox configure ports are faulty.
            unknown_points.append(
                "Unable to evaluate PDOC port faults in configured smartbox: "
                f"{ports_with_smartbox=}, "
                f"{ports_power_control=}, "
                f"{ports_power_sensed=}, "
            )
        if pasd_status is None:
            unknown_points.append(
                "No value has been read from the FNDH pasdStatus register."
            )
        elif pasd_status == FndhStatusMap.POWERUP.name:
            unknown_points.append(f"FNDH is in {FndhStatusMap.POWERUP.name} state.")
        elif pasd_status not in FndhStatusMap.__members__:
            unknown_points.append(f"FNDH is reporting unknown status: {pasd_status}.")

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
            >>>     "status": "OK",
            >>> }
            >>> failed_rule(monitoring_points=monitoring_points, **kwargs)
        """
        failed_points: list[str] = []
        ports_power_sensed = kwargs.get("ports_power_sensed")
        ports_power_control = kwargs.get("ports_power_control")
        ports_with_smartbox = kwargs.get("ports_with_smartbox")
        pasd_status = kwargs.get("status")

        if pasd_status is not None and pasd_status in [
            FndhStatusMap.ALARM.name,
            FndhStatusMap.RECOVERY.name,
        ]:
            failed_points.append(f"FNDH is reporting {pasd_status}.")

        # Only evaluate pdoc faults if we can work out this information.
        if (ports_with_smartbox is not None and len(ports_with_smartbox) > 0) and (
            ports_power_sensed is not None and ports_power_control is not None
        ):
            smartbox_pdoc_fault = _generate_smartbox_pdoc_fault_report(
                percentage_threshold=self._thresholds[
                    "failed_percent_uncontrolled_smartbox"
                ],
                ports_with_smartbox=ports_with_smartbox,
                ports_power_sensed=ports_power_sensed,
                ports_power_control=ports_power_control,
            )
            if smartbox_pdoc_fault:
                failed_points.append(smartbox_pdoc_fault)

        for key, value in monitoring_points.items():
            if value[0] == HealthState.FAILED:
                failed_points.append(
                    f"Monitoring point {key} is in {value[0].name} HealthState. "
                    f"Cause: {value[1]}"
                )

        # If there are any FAILED points,
        # return True and a concatenated message.
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
            >>>     "status": "OK",
            >>> }
            >>> degraded_rule(monitoring_points=monitoring_points, **kwargs)
        """
        degraded_points: list[str] = []
        ports_power_sensed = kwargs.get("ports_power_sensed")
        ports_power_control = kwargs.get("ports_power_control")
        ports_with_smartbox = kwargs.get("ports_with_smartbox")
        pasd_status = kwargs.get("status")

        if pasd_status == FndhStatusMap.WARNING.name:
            degraded_points.append(f"FNDH is reporting {pasd_status}.")

        # Only evaluate pdoc faults if we can work out this information.
        if (ports_with_smartbox is not None and len(ports_with_smartbox) > 0) and (
            ports_power_sensed is not None and ports_power_control is not None
        ):
            smartbox_pdoc_fault_message: str | None = (
                _generate_smartbox_pdoc_fault_report(
                    percentage_threshold=self._thresholds[
                        "degraded_percent_uncontrolled_smartbox"
                    ],
                    ports_with_smartbox=ports_with_smartbox,
                    ports_power_sensed=ports_power_sensed,
                    ports_power_control=ports_power_control,
                )
            )
            if smartbox_pdoc_fault_message:
                degraded_points.append(smartbox_pdoc_fault_message)

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
            >>>    "status": "OK"
            >>> }
            >>> healthy_rule(monitoring_points=monitoring_points, **kwargs)
        """
        messages: list[str] = []
        states: list[bool] = []

        pasd_status = kwargs.get("status")
        states.append(
            pasd_status in [FndhStatusMap.OK.name, FndhStatusMap.UNINITIALISED.name]
        )
        messages.append(f"FNDH is reporting {pasd_status}.")

        # Iterate through monitoring_points, appending to messages and states
        for state, message in monitoring_points.values():
            messages.append(message)
            states.append(state == HealthState.OK)

        # 'Health is OK' message is added by the BaseHealthModel
        return all(states), join_health_reports(messages)

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

        extra_info = ""
        if monitoring_point_name in ["psu48vvoltage2", "paneltemperature"]:
            # Some extra information to user
            extra_info += " Note: this monitoring point is not implemented in hardware "

        if (monitoring_point >= max_warn) or (monitoring_point <= min_warn):
            if (monitoring_point >= max_alm) or (monitoring_point <= min_alm):
                return (
                    HealthState.FAILED,
                    f"Monitoring point {monitoring_point_name} has value "
                    f"{monitoring_point}, this is in the alarm region for thresholds "
                    f"{max_alm=}, {min_alm=}" + extra_info,
                )
            return (
                HealthState.DEGRADED,
                f"Monitoring point {monitoring_point_name} has value "
                f"{monitoring_point}, this is in the warning region for thresholds "
                f"{max_warn=}, {min_warn=}" + extra_info,
            )
        return (
            HealthState.OK,
            f"Monitoring point {monitoring_point_name} has value "
            f"{monitoring_point}, this is within limits" + extra_info,
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
                f"initialised to {new_threshold}"
            )
        elif old_threshold != new_threshold:
            self._logger.info(
                f"Threshold for {attribute_name} has been updated "
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
