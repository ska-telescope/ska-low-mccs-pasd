# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""
This module contains pytest fixtures other test setups.

These are common to all ska-low-mccs tests: unit, integration and
functional (BDD).
"""
from __future__ import annotations

import logging
from typing import Any, Final

import pytest
import tango

NUMBER_OF_ANTENNA = 256
NUMBER_OF_SMARTBOX = 24
NUMBER_OF_SMARTBOX_PORTS = 12


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Pytest hook; prints info about tango version.

    :param session: a pytest Session object
    """
    print(tango.utils.info())


@pytest.fixture(name="pasd_config_path", scope="session")
def pasd_config_path_fixture() -> str:
    """
    Return the path to the PaSD configuration file to be used in these tests.

    :return: path to the PaSD configuration file to be used in these tests.
    """
    return "tests/data/pasd_configuration.yaml"


@pytest.fixture(scope="session", name="logger")
def logger_fixture() -> logging.Logger:
    """
    Fixture that returns a default logger.

    The logger will be set to DEBUG level, as befits testing.

    :returns: a logger.
    """
    debug_logger = logging.getLogger()
    debug_logger.setLevel(logging.DEBUG)
    return debug_logger


@pytest.fixture(name="simulated_configuration", scope="session")
def simulated_configuration_fixture() -> dict[Any, Any]:
    """
    Return a configuration for the fieldstation.

    :return: a configuration for representing the antenna port mapping information.
    """
    number_of_antenna = NUMBER_OF_ANTENNA
    antennas = {}
    smartboxes = {}
    for i in range(1, number_of_antenna + 1):
        antennas[str(i)] = {
            "smartbox": str(i % NUMBER_OF_SMARTBOX + 1),
            "smartbox_port": i % (NUMBER_OF_SMARTBOX_PORTS - 1),
            "masked": False,
        }
    for i in range(1, NUMBER_OF_SMARTBOX + 1):
        smartboxes[str(i)] = {"fndh_port": i}

    configuration: Final = {"antennas": antennas, "pasd": {"smartboxes": smartboxes}}
    return configuration
