# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""
This package implements SKA Low's MCCS PASD subsystem.

The Monitoring Control and Calibration (MCCS) subsystem is responsible
for, amongst other things, monitoring and control of LFAA.
"""

__all__ = [
    # devices
    "MccsPasdBus",
    # device subpackages
    "pasd_bus",
]

from .pasd_bus import MccsPasdBus
