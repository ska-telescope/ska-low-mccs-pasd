#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a station."""
from __future__ import annotations

from typing import Optional, Sequence

from ska_control_model import HealthState, PowerState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol

from .field_station_health_rules import FieldStationHealthRules

__all__ = ["FieldStationHealthModel"]


class FieldStationHealthModel(BaseHealthModel):
    """A health model for a field station."""

    def __init__(
        self: FieldStationHealthModel,
        fndh_fqdn: str,
        smartbox_fqdns: Sequence[str],
        health_changed_callback: HealthChangedCallbackProtocol,
        thresholds: Optional[dict[str, float]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param fndh_fqdn: the FQDN of this station's FNDH.
        :param smartbox_fqdns: the FQDNs of this station's smartboxes
        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        :param thresholds: the threshold parameters for the health rules
        """
        self._smartbox_health: dict[str, Optional[HealthState]] = {
            smartbox_fqdn: HealthState.UNKNOWN for smartbox_fqdn in smartbox_fqdns
        }
        self._smartbox_power: dict[str, Optional[PowerState]] = {
            smartbox_fqdn: PowerState.UNKNOWN for smartbox_fqdn in smartbox_fqdns
        }
        self._fndh_health: Optional[HealthState]
        self._fndh_power: Optional[PowerState]
        if fndh_fqdn == "":
            self._fndh_health = None
            self._fndh_power = None
        else:
            self._fndh_health = HealthState.UNKNOWN
            self._fndh_power = PowerState.UNKNOWN
        self._fndh_fqdn = fndh_fqdn
        self._health_rules = FieldStationHealthRules(thresholds)
        super().__init__(health_changed_callback)

    def fndh_health_changed(
        self: FieldStationHealthModel,
        fndh_fqdn: str,
        fndh_health: Optional[HealthState],
    ) -> None:
        """
        Handle a change in fndh health.

        :param fndh_fqdn: the FQDN of the fndh whose health has changed
        :param fndh_health: the health state of the fndh, or
            None if the fndh's admin mode indicates that its health
            should not be rolled up.
        """
        if self._fndh_health != fndh_health and fndh_fqdn == self._fndh_fqdn:
            self._fndh_health = fndh_health
            self.update_health()

    def fndh_power_changed(
        self: FieldStationHealthModel,
        fndh_fqdn: str,
        fndh_power: Optional[PowerState],
    ) -> None:
        """
        Handle a change in fndh power.

        :param fndh_fqdn: the FQDN of the fndh whose power has changed
        :param fndh_power: the power state of the fndh, or
            None if the fndh's admin mode indicates that its power
            should not be rolled up.
        """
        if self._fndh_power != fndh_power and fndh_fqdn == self._fndh_fqdn:
            self._fndh_power = fndh_power
            self.update_health()

    def smartbox_health_changed(
        self: FieldStationHealthModel,
        smartbox_fqdn: str,
        smartbox_health: Optional[HealthState],
    ) -> None:
        """
        Handle a change in smartbox health.

        :param smartbox_fqdn: the FQDN of the smartbox whose health has changed
        :param smartbox_health: the health state of the specified smartbox, or
            None if the smartbox's admin mode indicates that its health
            should not be rolled up.
        """
        if (
            self._smartbox_health.get(smartbox_fqdn) != smartbox_health
            and smartbox_fqdn in self._smartbox_health
        ):
            self._smartbox_health[smartbox_fqdn] = smartbox_health
            self.update_health()

    def smartbox_power_changed(
        self: FieldStationHealthModel,
        smartbox_fqdn: str,
        smartbox_power: Optional[PowerState],
    ) -> None:
        """
        Handle a change in smartbox power.

        :param smartbox_fqdn: the FQDN of the smartbox whose health has changed
        :param smartbox_power: the power state of the specified smartbox, or
            None if the smartbox's admin mode indicates that its health
            should not be rolled up.
        """
        if (
            self._smartbox_power.get(smartbox_fqdn) != smartbox_power
            and smartbox_fqdn in self._smartbox_power
        ):
            self._smartbox_power[smartbox_fqdn] = smartbox_power
            self.update_health()

    def evaluate_health(
        self: FieldStationHealthModel,
    ) -> tuple[HealthState, str]:
        """
        Compute overall health of the station.

        The overall health is based on the fault and communication
        status of the station overall, together with the health of the
        smartboxes that it manages.

        This implementation simply sets the health of the station to the
        health of its least healthy component.

        :return: an overall health of the station
        """
        station_health, station_report = super().evaluate_health()

        for health in [
            HealthState.FAILED,
            HealthState.UNKNOWN,
            HealthState.DEGRADED,
            HealthState.OK,
        ]:
            if health == station_health:
                return station_health, station_report
            result, report = self._health_rules.rules[health](
                self._state["power"],
                self._fndh_health,
                self._fndh_power,
                self._smartbox_health,
                self._smartbox_power,
            )
            if result:
                return health, report
        return HealthState.UNKNOWN, "No rules matched"
