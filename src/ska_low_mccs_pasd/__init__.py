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

__version__ = "0.10.0"

__version_info__ = (
    "ska-low-mccs-pasd",
    __version__,
    "This package implements SKA Low's MCCS PASD subsystem.",
)

__all__ = [
    # devices
    "MccsPasdBus",
    "MccsSmartBox",
    "MccsFieldStation",
    # device subpackages
    "pasd_bus",
    "smart_box",
    "fndh",
    "fncc",
    "PasdData",
    "MccsFNDH",
    "MccsFNCC",
    "reference_data_store",
]
from .field_station import MccsFieldStation
from .fncc import MccsFNCC
from .fndh import MccsFNDH
from .pasd_bus import MccsPasdBus
from .pasd_data import PasdData
from .smart_box import MccsSmartBox
