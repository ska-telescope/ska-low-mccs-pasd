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

from typing import Mapping

from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.health import HealthRules

DEGRADED_HEALTH_STATES = frozenset({HealthState.DEGRADED, HealthState.FAILED, None})
DEGRADED_POWER_STATES = frozenset(
    {PowerState.UNKNOWN, PowerState.OFF, PowerState.STANDBY, None}
)
DEGRADED_STATES = {"health": DEGRADED_HEALTH_STATES, "power": DEGRADED_POWER_STATES}


class FieldStationHealthRules(HealthRules):
    """A class to handle transition rules for station."""

    def _generate_report(
        self: FieldStationHealthRules,
        smartbox_states: Mapping[str, HealthState | PowerState | None],
        threshold_key: str,
        fndh_state: HealthState | PowerState,
        state_type: str,
    ) -> tuple[bool, str]:
        result = self.get_fraction_in_states(
            smartbox_states,
            DEGRADED_STATES[state_type],
            default=0,
        ) >= self._thresholds[threshold_key] or (
            fndh_state == HealthState.FAILED
            if state_type == "health"
            else fndh_state == PowerState.UNKNOWN
        )
        if result:
            subdevice_states = [
                f"{trl} - {state.name}"
                for trl, state in smartbox_states.items()
                if state is not None and state in DEGRADED_STATES[state_type]
            ]
            fndh_report = fndh_state.name if fndh_state is not None else fndh_state
            report = (
                f"Too many subdevices are in a bad {state_type} state: "
                f"Smartboxes: {subdevice_states} FNDH: {fndh_report}"
            )
            return result, report
        return result, ""

    def unknown_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState | None,
        fndh_power: PowerState | None,
        smartbox_healths: dict[str, HealthState | None],
        smartbox_powers: dict[str, PowerState | None],
    ) -> tuple[bool, str]:
        """
        Test whether UNKNOWN is valid for the station.

        :param fndh_health: fndh health
        :param fndh_power: fndh power
        :param smartbox_healths: dictionary of smartbox healths
        :param smartbox_powers: dictionary of smartbox powers

        :return: True if UNKNOWN is a valid state, along with a text report.
        """
        return False, ""

    def failed_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState,
        fndh_power: PowerState,
        smartbox_healths: dict[str, HealthState | None],
        smartbox_powers: dict[str, PowerState | None],
    ) -> tuple[bool, str]:
        """
        Test whether FAILED is valid for the station.

        :param fndh_health: fndh health
        :param fndh_power: fndh power
        :param smartbox_healths: dictionary of smartbox healths
        :param smartbox_powers: dictionary of smartbox powers

        :return: True if FAILED is a valid state, along with a text report.
        """
        result, report = self._generate_report(
            smartbox_healths, "smartbox_failed", fndh_health, "health"
        )
        if result:
            return result, report
        return self._generate_report(
            smartbox_powers, "smartbox_failed", fndh_power, "power"
        )

    def degraded_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState,
        fndh_power: PowerState,
        smartbox_healths: dict[str, HealthState | None],
        smartbox_powers: dict[str, PowerState | None],
    ) -> tuple[bool, str]:
        """
        Test whether DEGRADED is valid for the station.

        :param fndh_health: fndh health
        :param fndh_power: fndh power
        :param smartbox_healths: dictionary of smartbox healths
        :param smartbox_powers: dictionary of smartbox powers

        :return: True if DEGRADED is a valid state, along with a text report.
        """
        result, report = self._generate_report(
            smartbox_healths, "smartbox_degraded", fndh_health, "health"
        )
        if result:
            return result, report
        return self._generate_report(
            smartbox_powers, "smartbox_degraded", fndh_power, "power"
        )

    def healthy_rule(  # type: ignore[override]
        self: FieldStationHealthRules,
        fndh_health: HealthState,
        fndh_power: PowerState,
        smartbox_healths: dict[str, HealthState | None],
        smartbox_powers: dict[str, PowerState | None],
    ) -> tuple[bool, str]:
        """
        Test whether OK is valid for the station.

        :param fndh_health: fndh health
        :param fndh_power: fndh power
        :param smartbox_healths: dictionary of smartbox healths
        :param smartbox_powers: dictionary of smartbox powers

        :return: True if OK is a valid state, along with a text report.
        """
        return True, "Health is OK."

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
