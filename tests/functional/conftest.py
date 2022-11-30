# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains pytest-specific test harness for PaSD functional tests."""
import unittest
from typing import Any, Callable, Generator

import pytest
from ska_low_mccs_common.testing.tango_harness import DevicesToLoadType, TangoHarness


@pytest.fixture(scope="module")
def tango_config() -> dict[str, Any]:
    """
    Fixture that returns basic configuration information for a Tango test harness.

    e.g. such as whether or not to run in a separate process.

    :return: a dictionary of configuration key-value pairs
    """
    return {"process": True}


@pytest.fixture(scope="module")
def tango_harness(
    tango_harness_factory: Callable[
        [
            dict[str, Any],
            DevicesToLoadType,
            Callable[[], unittest.mock.Mock],
            dict[str, unittest.mock.Mock],
        ],
        TangoHarness,
    ],
    tango_config: dict[str, str],
    devices_to_load: DevicesToLoadType,
    mock_factory: Callable[[], unittest.mock.Mock],
    initial_mocks: dict[str, unittest.mock.Mock],
) -> Generator[TangoHarness, None, None]:
    """
    Create a test harness for testing Tango devices.

    (This overwrites the `tango_harness` fixture, in order to change the
    fixture scope.)

    :param tango_harness_factory: a factory that provides a test harness
        for testing tango devices
    :param tango_config: basic configuration information for a tango
        test harness
    :param devices_to_load: fixture that provides a specification of the
        devices that are to be included in the devices_info dictionary
    :param mock_factory: the factory to be used to build mocks
    :param initial_mocks: a pre-build dictionary of mocks to be used
        for particular

    :yields: the test harness
    """
    with tango_harness_factory(
        tango_config, devices_to_load, mock_factory, initial_mocks
    ) as harness:
        yield harness
