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
from typing import Final

import pytest
import tango
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

MAX_NUMBER_OF_SMARTBOXES_PER_STATION: Final = 24
NUMBER_OF_ANTENNAS: Final = 256
NUMBER_OF_SMARTBOX_PORTS: Final = 12
NUMBER_OF_FNDH_PORTS: Final = 28
FEM_CURRENT_TRIP_THRESHOLD: Final = 496
INPUT_VOLTAGE_THRESHOLDS: Final = [50.0, 49.0, 45.0, 40.0]


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


# pylint: disable=too-few-public-methods
class Helpers:
    """Static helper functions for tests."""

    @staticmethod
    def print_change_event_queue(
        change_event_callbacks: MockTangoEventCallbackGroup,
        attr_name: str,
    ) -> None:
        """
        Print the change event callback queue of the given attribute for debugging.

        :param change_event_callbacks: dictionary of mock change event callbacks
        :param attr_name: attribute in the change event callback group to print
        """
        print(f"{attr_name} change event queue:")
        for node in change_event_callbacks[
            attr_name
        ]._callable._consumer_view._iterable:
            print(node.payload["attribute_value"])
