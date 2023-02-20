# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple tests of the MCCS PaSD bus Tango device."""
from __future__ import annotations

from pytest_bdd import given, scenario  # , then, when
from ska_tango_testing.context import TangoContextProtocol
from tango import DeviceProxy


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
def pasd_bus_device(tango_harness: TangoContextProtocol) -> DeviceProxy:
    """
    Return a DeviceProxy to an instance of MccsPasdBus.

    :param tango_harness: a test harness for Tango devices

    :return: A proxy to an instance of MccsPasdBus.
    """
    return tango_harness.get_device("low-mccs/pasdbus/001")
