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

import tango
from pytest_bdd import given, scenarios, then, when
from ska_control_model import AdminMode
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

scenarios("./features/forwarded_attributes.feature")


@given("we have a fndh device")
def fndh_online(
    pasd_bus_device: tango.DeviceProxy,
    fndh_device_proxy: tango.DeviceProxy,
    change_event_callbacks: MockTangoEventCallbackGroup,
) -> None:
    """
    Ensure Fndh device online.

    TODO: We need a way of confirm that the PaSD is there,
    independently of MCCS.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param fndh_device_proxy: a proxy to the FNDH device.
    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    """
    if pasd_bus_device.adminMode != AdminMode.ONLINE:
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["smartbox1PortsPowerSensed"].assert_change_event(
            Anything
        )

    if fndh_device_proxy.adminMode != AdminMode.ONLINE:
        fndh_device_proxy.adminMode = AdminMode.ONLINE
        change_event_callbacks["state"].assert_change_event(Anything)


@when("we have a fieldstation device")
def fieldstation_online(
    field_station_device: tango.DeviceProxy,
) -> None:
    """
    Ensure field station is online.

    :param field_station_device: a proxy to the field station device.
    """
    if field_station_device.adminMode != AdminMode.ONLINE:
        field_station_device.adminMode = AdminMode.ONLINE


@then("they agree on the outsideTemperature")
def agree_on_attribute_value(
    field_station_device: tango.DeviceProxy,
    fndh_device_proxy: tango.DeviceProxy,
) -> None:
    """
    Ensure FNDH and fieldStation agree on the attribute value.

    :param field_station_device: a proxy to the field station device.
    :param fndh_device_proxy: a proxy to the FNDH device.
    """
    assert (
        fndh_device_proxy.outsideTemperature == field_station_device.outsideTemperature
    )
