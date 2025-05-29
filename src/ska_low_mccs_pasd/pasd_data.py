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

from .pasd_controllers_configuration import PasdControllersConfig

__all__ = ["PasdData"]


class PasdData:  # pylint: disable=too-few-public-methods
    """This class contain data/facts about PaSD that are needed by multiple classes."""

    CONTROLLERS_CONFIG: Final = PasdControllersConfig.get_all()
    """The validated PaSD controllers' configuration."""

    MAX_NUMBER_OF_SMARTBOXES_PER_STATION: Final = 24
    """The maximum number of smartboxes in a Station."""

    NUMBER_OF_ANTENNAS: Final = 256
    """The number of antenna in a Station."""

    NUMBER_OF_SMARTBOX_PORTS: Final = CONTROLLERS_CONFIG["FNSC"]["number_of_ports"]
    """The number of ports on a smartbox instance."""

    NUMBER_OF_FNDH_PORTS: Final = CONTROLLERS_CONFIG["FNPC"]["number_of_ports"]
    """The number of ports on a FNDH instance."""

    FNDH_DEVICE_ID: Final = CONTROLLERS_CONFIG["FNPC"]["pasd_number"]
    """The device identifier for an FNDH"""

    FNCC_DEVICE_ID: Final = CONTROLLERS_CONFIG["FNCC"]["pasd_number"]
    """The device identifier for an FNCC"""

    FNDH_PREFIX: Final = CONTROLLERS_CONFIG["FNPC"]["prefix"]
    """The Tango attribute prefix for an FNDH"""

    FNCC_PREFIX: Final = CONTROLLERS_CONFIG["FNCC"]["prefix"]
    """The Tango attribute prefix for an FNCC"""

    SMARTBOX_PREFIX: Final = CONTROLLERS_CONFIG["FNSC"]["prefix"]
    """The Tango attribute prefix for a smartbox"""
