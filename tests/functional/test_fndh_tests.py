# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains a simple tests of the MCCS FNDH Tango device."""
from __future__ import annotations

import gc
import json
from typing import Literal, Callable

import tango
from pytest_bdd import given, parsers, scenario, then, when
from ska_control_model import AdminMode, HealthState
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

gc.disable()

@scenario("features/fndh_deployment.feature","Fndh can change port power")
def test_fndh() -> None:
    """
    Test basic monitoring of a FNDH.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


