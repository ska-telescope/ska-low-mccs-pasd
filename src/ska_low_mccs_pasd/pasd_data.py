#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains base data/facts about a pasd."""


from __future__ import annotations  # allow forward references in type hints

from typing import Final

__all__ = ["PasdData"]


class PasdData:  # pylint: disable=too-few-public-methods
    """This class contain data/facts about PaSD that are needed by multiple classes."""

    NUMBER_OF_SMARTBOXES = 24
    """The number of smartboxes in a Station."""

    NUMBER_OF_ANTENNAS = 256
    """The number of antenna in a Station."""

    NUMBER_OF_SMARTBOX_PORTS: Final = 12
    """The number of ports on a smartbox instance."""

    NUMBER_OF_FNDH_PORTS: Final = 28
    """The number of ports on a FNDH instance."""

    FNDH_DEVICE_ID = 0
    """The device identifier for an FNDH"""

    FNCC_DEVICE_ID = 100
    """The device identifier for an FNCC"""
