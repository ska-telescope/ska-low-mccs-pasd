# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""An implementation of a health model for a PaSD bus."""
from __future__ import annotations

from ska_low_mccs_common.health import BaseHealthModel


class PasdBusHealthModel(BaseHealthModel):
    """
    A health model for a PaSD bus.

    At present this uses the base health model; this is a placeholder
    for a future, better implementation.

    Even when updated, this health model should only ever represent the
    health of the PaSD bus itself. The health of individual PaSD devices
    (FNDH and smartboxes) will be represented by upstream Tango devices.
    """
