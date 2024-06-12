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

from ska_control_model import HealthState
from ska_low_mccs_common.health import HealthRules

DEGRADED_STATES = frozenset({HealthState.DEGRADED, HealthState.FAILED, None})


class FieldStationHealthRules(HealthRules):
    """A class to handle transition rules for station."""

    def unknown_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState | None,
        smartbox_healths: dict[str, HealthState | None],
    ) -> tuple[bool, str]:
        """
        Test whether UNKNOWN is valid for the station.

        :param fndh_health: dictionary of fndh healths
        :param smartbox_healths: dictionary of smartbox healths

        :return: True if UNKNOWN is a valid state, along with a text report.
        """
        result = (
            fndh_health == HealthState.UNKNOWN
            or HealthState.UNKNOWN in smartbox_healths.values()
        )
        if result:
            smartbox_states = [
                trl
                for trl, health in smartbox_healths.items()
                if health is None or health == HealthState.UNKNOWN
            ]
            fndh_report = (
                HealthState(fndh_health).name
                if fndh_health is not None
                else fndh_health
            )
            report = (
                "Some devices are unknown: "
                f"Smartboxes: {smartbox_states} FNDH: {fndh_report}"
            )
        else:
            report = ""
        return result, report

    def failed_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState,
        smartbox_healths: dict[str, HealthState | None],
    ) -> tuple[bool, str]:
        """
        Test whether FAILED is valid for the station.

        :param fndh_health: dictionary of fndh healths
        :param smartbox_healths: dictionary of smartbox healths

        :return: True if FAILED is a valid state, along with a text report.
        """
        result = (
            self.get_fraction_in_states(smartbox_healths, DEGRADED_STATES, default=0)
            >= self._thresholds["smartbox_failed"]
            or fndh_health == HealthState.FAILED
        )
        if result:
            smartbox_states = [
                f"{trl} - {HealthState(health).name}"
                for trl, health in smartbox_healths.items()
                if health is not None and health in DEGRADED_STATES
            ]
            fndh_report = (
                HealthState(fndh_health).name
                if fndh_health is not None
                else fndh_health
            )
            report = (
                "Too many subdevices are in a bad state: "
                f"Smartboxes: {smartbox_states} FNDH: {fndh_report}"
            )
        else:
            report = ""
        return result, report

    def degraded_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState,
        smartbox_healths: dict[str, HealthState | None],
    ) -> tuple[bool, str]:
        """
        Test whether DEGRADED is valid for the station.

        :param fndh_health: dictionary of fndh healths
        :param smartbox_healths: dictionary of smartbox healths

        :return: True if DEGRADED is a valid state, along with a text report.
        """
        result = (
            self.get_fraction_in_states(smartbox_healths, DEGRADED_STATES, default=0)
            >= self._thresholds["smartbox_degraded"]
            or fndh_health == HealthState.DEGRADED
        )
        if result:
            smartbox_states = [
                f"{trl} - {HealthState(health).name}"
                for trl, health in smartbox_healths.items()
                if health is not None and health in DEGRADED_STATES
            ]
            fndh_report = (
                HealthState(fndh_health).name
                if fndh_health is not None
                else fndh_health
            )
            report = (
                "Too many subdevices are in a bad state: "
                f"Smartboxes: {smartbox_states} FNDH: {fndh_report}"
            )
        else:
            report = ""
        return result, report

    def healthy_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState,
        smartbox_healths: dict[str, HealthState | None],
    ) -> tuple[bool, str]:
        """
        Test whether OK is valid for the station.

        :param fndh_health: dictionary of fndh healths
        :param smartbox_healths: dictionary of smartbox healths

        :return: True if OK is a valid state, along with a text report.
        """
        result = (
            self.get_fraction_in_states(smartbox_healths, DEGRADED_STATES, default=0)
            < self._thresholds["smartbox_degraded"]
            and fndh_health == HealthState.OK
        )
        if not result:
            smartbox_states = [
                f"{trl} - {HealthState(health).name}"
                for trl, health in smartbox_healths.items()
                if health is not None and health in DEGRADED_STATES
            ]
            fndh_report = (
                HealthState(fndh_health).name
                if fndh_health is not None
                else fndh_health
            )
            report = (
                "Too many subdevices are in a bad state: "
                f"Smartboxes: {smartbox_states} FNDH: {fndh_report}"
            )
        else:
            report = ""
        return result, report

    @property
    def default_thresholds(self: HealthRules) -> dict[str, float]:
        """
        Get the default thresholds for this device.

        :return: the default thresholds
        """
        return {
            "smartbox_degraded": 0.04,
            "smartbox_failed": 0.2,
        }
