# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a PaSD bus."""
from __future__ import annotations

from ska_control_model import HealthState
from ska_low_mccs_common.health import (
    BaseHealthModel,
    HealthChangedCallbackProtocol,
)


class PasdBusHealthModel(BaseHealthModel):
    """
    A health model for a PaSD bus.

    At present this uses the base health model; this is a placeholder
    for a future, better implementation.
    """

    def __init__(
        self: PasdBusHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
    ) -> None:
        """
        Initialise a new instance.

        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        """
        super().__init__(health_changed_callback, fndh_status=None)

    def evaluate_health(self: PasdBusHealthModel) -> HealthState:
        """
        Evaluate the health of the device.

        :return: the evaluated health of the device, based on previously
            reported device state.
        """
        super_health = super().evaluate_health()

        if super_health != HealthState.OK:
            return super_health

        if self._state["fndh_status"] != "OK":
            return HealthState.DEGRADED

        return HealthState.OK
