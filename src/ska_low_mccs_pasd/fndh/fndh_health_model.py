# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a FNDH."""
from __future__ import annotations

from ska_control_model import HealthState
from ska_low_mccs_common.health import (
    BaseHealthModel,
    HealthChangedCallbackProtocol,
)


class FndhHealthModel(BaseHealthModel):
    """
    A health model for a FNDH.

    At present this uses the base health model; this is a placeholder
    for a future, better implementation.
    """

    def __init__(
        self: FndhHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
    ) -> None:
        """
        Initialise a new instance.

        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        """
        super().__init__(health_changed_callback, pasdbus_status=None)

    def evaluate_health(self: FndhHealthModel) -> HealthState:
        """
        Evaluate the health of the device.

        :return: the evaluated health of the device, based on previously
            reported device state.
        """
        # TODO: this is incomplete.
        super_health = super().evaluate_health()
        if super_health != HealthState.OK:
            return super_health
        if self._state["pasdbus_status"] != "OK":
            # TODO: it is possible that the pasdBus is not ok
            # but all objects are ok for this smartbox to use
            return HealthState.FAILED

        return HealthState.OK
