# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS FNDH module."""


from __future__ import annotations

import pytest


@pytest.fixture(name="pasdbus_fqdn", scope="session")
def pasdbus_fqdn_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs/pasdbus/001"
