# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a FNCC."""
from __future__ import annotations

from ska_low_mccs_common.health import BaseHealthModel, HealthChangedCallbackProtocol


class FnccHealthModel(BaseHealthModel):
    """
    A health model for a FNCC.

    At present this uses the base health model; this is a placeholder
    for a future, better implementation.
    """

    def __init__(
        self: FnccHealthModel,
        health_changed_callback: HealthChangedCallbackProtocol,
    ) -> None:
        """
        Initialise a new instance.

        :param health_changed_callback: callback to be called whenever
            there is a change to this this health model's evaluated
            health state.
        """
        super().__init__(health_changed_callback, pasdbus_status=None)
