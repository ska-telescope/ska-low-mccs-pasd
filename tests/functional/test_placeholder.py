# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple tests of the MCCS PaSD bus Tango device."""
from __future__ import annotations

import pytest
from pytest_bdd import given, scenario  # , then, when
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.testing.tango_harness import DevicesToLoadType, TangoHarness


@pytest.fixture(scope="module")
def devices_to_load() -> DevicesToLoadType:
    """
    Fixture that specifies the devices to be loaded for testing.

    Here we specify that we want a daq receiver from the ska-low-mccs-daq chart.

    :return: specification of the devices to be loaded
    """
    return {
        "path": "tests/data/configuration.json",
        "package": "ska_low_mccs_daq",
        "devices": [
            {"name": "pasdbus_001", "proxy": MccsDeviceProxy},
        ],
    }


@scenario(
    "features/placeholder.feature",
    "Placeholder",
)
def test_placeholder() -> None:
    """
    Run a placeholder test scenario.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given("an MccsPasdBus")
def pasd_bus_device(tango_harness: TangoHarness) -> MccsDeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsDaqReceiver.

    :param tango_harness: a test harness for Tango devices

    :return: A MccsDeviceProxy instance to MccsDaqReceiver stored in the target_fixture
        `daq_receiver_bdd`.
    """
    return tango_harness.get_device("low-mccs/pasdbus/001")
