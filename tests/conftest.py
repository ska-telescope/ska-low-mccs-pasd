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
import yaml
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

MAX_NUMBER_OF_SMARTBOXES_PER_STATION: Final = 24
NUMBER_OF_ANTENNAS: Final = 256
NUMBER_OF_SMARTBOX_PORTS: Final = 12
NUMBER_OF_FNDH_PORTS: Final = 28


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
def simulated_configuration_fixture(pasd_config_path: str) -> dict[Any, Any]:
    """
    Return a configuration for the fieldstation to use.

    WARNING: the configuration we load into the FieldStation must match that
    we configure the PaSDSimulator with. Otherwise we have a configuration issues.
    i.e. we are simulating that TelModel has the wrong data stored.

    :param pasd_config_path: this is the configuration that the
        PaSDSimulator is configured with.

    :return: a configuration for representing the antenna port mapping information.
    """
    with open(pasd_config_path, "r", encoding="utf-8") as f:
        simulator_configuration = yaml.safe_load(f)

    antennas = simulator_configuration["antennas"]
    for _, config in antennas.items():
        config["masked"] = False

    smartboxes = simulator_configuration["pasd"]["smartboxes"]
    smartbox_mapping = {}
    for smartbox_id, config in smartboxes.items():
        smartbox_mapping[smartbox_id] = {
            "fndh_port": config["fndh_port"],
            "modbus_id": config["fndh_port"],
        }

    configuration: Final = {
        "antennas": antennas,
        "pasd": {"smartboxes": smartbox_mapping},
    }
    return configuration


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
