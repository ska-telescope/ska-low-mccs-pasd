# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a FNCC."""
from __future__ import annotations

import logging

from ska_control_model import HealthState
from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol
from ska_low_pasd_driver.pasd_bus_conversions import FnccStatusMap

from ska_low_mccs_pasd.pasd_utils import join_health_reports


class FnccHealthModel(BaseHealthModel):
    """A health model for a FNCC."""

    # The evaluation of HealthState will check for matches specified by the
    # precedence of HealthStates defined by this list.
    ORDERED_HEALTH_PRECEDENCE = [
        HealthState.FAILED,
        HealthState.UNKNOWN,
        HealthState.DEGRADED,
        HealthState.OK,
    ]

    def __init__(
        self: FnccHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param health_changed_callback: callback to be called whenever
            there is a change to this health model's evaluated
            health state.
        :param logger: logging object to use
        """
        super().__init__(health_changed_callback, pasdbus_status=None)
        self._logger = logger

    def evaluate_health(
        self: FnccHealthModel,
    ) -> tuple[HealthState, str]:
        """
        Compute overall health of the FNCC.

        FNCC has only a single register, status, which is
        reflected in the health model.

        :return: an overall health of the FNCC.
        """
        base_health, base_report = super().evaluate_health()

        status = self._state.get("status")
        if status is not None:
            rules_report = f"FNCC is reporting {status}."
            match status:
                case FnccStatusMap.OK.name:
                    rules_health = HealthState.OK
                case FnccStatusMap.RESET.name:
                    rules_health = HealthState.DEGRADED
                case _:
                    rules_health = HealthState.FAILED
        else:
            rules_report = "FNCC has not received a status value."
            rules_health = HealthState.UNKNOWN

        if base_health == rules_health:
            # If both health states match, return them together
            return base_health, join_health_reports([base_report, rules_report])

        # Return report with highest health concern.
        for health in self.ORDERED_HEALTH_PRECEDENCE:
            if base_health == health:
                return base_health, base_report

            if rules_health == health:
                return rules_health, rules_report

        # Default case if no health states matched any precedence order
        return HealthState.UNKNOWN, "No rules matched"
