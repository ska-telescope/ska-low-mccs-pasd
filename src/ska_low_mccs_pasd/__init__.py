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

__version__ = "3.1.3"

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
]


import tango.server

from .field_station import MccsFieldStation
from .fncc import MccsFNCC
from .fndh import MccsFNDH
from .pasd_bus import MccsPasdBus
from .pasd_data import PasdData
from .smart_box import MccsSmartBox


def main(*args: str, **kwargs: str) -> int:  # pragma: no cover
    """
    Entry point for module.

    :param args: positional arguments
    :param kwargs: named arguments

    :return: exit code
    """
    return tango.server.run(
        classes=(MccsFieldStation, MccsFNCC, MccsFNDH, MccsPasdBus, MccsSmartBox),
        args=args or None,
        **kwargs
    )
