# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a FNDH."""
from __future__ import annotations

from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol


class FndhHealthModel(BaseHealthModel):
    """
    A health model for a FNDH.

    # TODO: [MCCS-2087] Implement the evaluate_health method
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
