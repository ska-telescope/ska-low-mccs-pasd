# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS SmartBox module."""
from __future__ import annotations

import pytest


@pytest.fixture(name="pasdbus_fqdn", scope="session")
def pasdbus_fqdn_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs-pasd/pasd-bus/001"


@pytest.fixture(name="fndh_bus_fndh", scope="session")
def fndh_bus_fndh_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs-pasd/fndh/001"
