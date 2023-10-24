# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple test of the MCCS FNDH Tango device."""
from __future__ import annotations

import gc
import logging

import tango
from pytest_bdd import given, scenario, then, when

gc.disable()


@scenario("features/server.feature", "Fndh can change port power")
def test_server() -> None:
    """
    Test basic monitoring of a FNDH.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given("Nothing")
@when("Nothing")
def command_port_power_state() -> None:
    """Nothing."""
    logging.error("Nothing")


@then("two servers hang forever")
def check_pasd_port_power_changed(pasd_bus_device: tango.DeviceProxy) -> None:
    """
    Check the power state of port given by port no has/will change.

    :param pasd_bus_device: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    print("h")
    logging.error("server both")
    pasd_bus_device.adminMOde = 0

    assert False
