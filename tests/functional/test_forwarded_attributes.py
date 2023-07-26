# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of forwarded attribute in FieldStation."""
# TODO: this test starts with the letter z pending MCCS-1474.

from __future__ import annotations

from typing import Callable

import pytest
import tango
from pytest_bdd import given, parsers, scenarios, then, when
from ska_control_model import AdminMode

scenarios("./features/forwarded_attributes.feature")


@given(parsers.parse("A {device_name} which is ready"))
def get_ready_device(
    is_true_context: bool, device_name: str, set_device_state: Callable
) -> None:
    """
    Get device in state ON and adminmode ONLINE.

    :param device_name: FQDN of device under test.
    :param set_device_state: function to set device state.
    :param is_true_context: Are we using a true tango context.
    """
    if not is_true_context:
        # https://gitlab.com/tango-controls/pytango/-/issues/533
        return
    print(f"Setting device {device_name} ready...")
    set_device_state(device=device_name, state=tango.DevState.ON, mode=AdminMode.ONLINE)


@when(
    "we query their outsideTemperature attributes",
    target_fixture="outside_temperatures",
)
def query_attribute(
    field_station_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    is_true_context: bool,
) -> list[float]:
    """
    Return the outsideTemperature as reported by both devices.

    :param field_station_device: a proxy to the field station device.
    :param fndh_device: a proxy to the FNDH device.
    :param is_true_context: Are we using a true tango context.

    :return: a target fixture with the temperature as reported by both devices.
    """
    if not is_true_context:
        # https://gitlab.com/tango-controls/pytango/-/issues/533
        return []
    return [
        fndh_device.outsideTemperature,
        field_station_device.outsideTemperature,
    ]


@then("they agree on the outsideTemperature")
def agree_on_attribute_value(
    outside_temperatures: dict,
    is_true_context: bool,
) -> None:
    """
    Ensure FNDH and fieldStation agree on the attribute value.

    :param outside_temperatures: the outside temperature as reported by both the
        field station and FNDH.
    :param is_true_context: Are we using a true tango context.
    """
    if not is_true_context:
        # https://gitlab.com/tango-controls/pytango/-/issues/533
        return
    assert outside_temperatures[0] == pytest.approx(outside_temperatures[1])
