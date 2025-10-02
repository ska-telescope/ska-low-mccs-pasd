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
import time
from typing import Callable

import tango
from pytest_bdd import given, parsers, scenario, then, when
from ska_control_model import AdminMode, PowerState, ResultCode, SimulationMode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from tests.harness import get_pasd_bus_name

gc.disable()


@scenario("features/fndh_deployment.feature", "Fndh can change port power")
def test_fndh() -> None:
    """
    Test basic monitoring of a FNDH.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given(parsers.parse("A {device_ref} which is ready"))
def get_ready_device(device_ref: str, set_device_state: Callable) -> None:
    """
    Get device in state ON and adminmode ONLINE.

    :param device_ref: Gherkin reference to device under test.
    :param set_device_state: function to set device state.
    """
    print(f"Setting device {device_ref} ready...")
    set_device_state(
        device_ref,
        state=tango.DevState.ON,
        mode=AdminMode.ONLINE,
        simulation_mode=SimulationMode.TRUE,
    )


@then(
    parsers.parse("they both agree on the power state of port {port_no}"),
    converters={"port_no": int},
)
@given(
    parsers.parse("they both agree on the power state of port {port_no}"),
    converters={"port_no": int},
)
def check_power_states(
    pasd_bus_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    port_no: int,
    check_attribute: Callable,
    check_fastcommand: Callable,
) -> None:
    """
    Compare power states.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param fndh_device: a proxy to the FNDH device.
    :param port_no: the port number of the FNDH.
    :param check_attribute: fixture for checking device attribute.
    :param check_fastcommand: fixture for checking fast command result.
    """
    assert pasd_bus_device.InitializeFndh()[0] == ResultCode.OK

    power_map = {False: PowerState.OFF, True: PowerState.ON, None: PowerState.UNKNOWN}
    timeout = 120  # Seconds
    current_time = time.time()  # Seconds
    while time.time() < current_time + timeout:
        try:
            assert power_map[
                check_attribute(pasd_bus_device, "fndhPortsPowerSensed")[port_no - 1]
            ] == check_fastcommand(fndh_device, "PortPowerState", port_no)
        except AssertionError:
            print("Power states don't yet agree.")
            time.sleep(0.1)
        else:
            break
    assert power_map[
        check_attribute(pasd_bus_device, "fndhPortsPowerSensed")[port_no - 1]
    ] == check_fastcommand(
        fndh_device, "PortPowerState", port_no
    ), "Power states don't agree after timeout."


@when(
    parsers.parse(
        "I ask the MccsFndh device to change the power state of port {port_no}"
    ),
    converters={"port_no": int},
)
def command_port_power_state(
    pasd_bus_device: tango.DeviceProxy,
    fndh_device: tango.DeviceProxy,
    port_no: int,
    check_fastcommand: Callable,
    clipboard: dict,
) -> None:
    """
    Power on port given by port no.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param fndh_device: a proxy to the FNDH device.
    :param port_no: the port number of the FNDH.
    :param check_fastcommand: fixture for checking fast command result.
    :param clipboard: a place to store information across BDD steps.
    """
    clipboard["expected_power_sensed"] = list(pasd_bus_device.fndhPortsPowerSensed)

    if check_fastcommand(fndh_device, "PortPowerState", port_no) == PowerState.OFF:
        clipboard["expected_power_sensed"][port_no - 1] = True
        assert fndh_device.PowerOnPort(port_no)[0] == ResultCode.QUEUED
    else:
        clipboard["expected_power_sensed"][port_no - 1] = False
        assert fndh_device.PowerOffPort(port_no)[0] == ResultCode.QUEUED


@then(
    parsers.parse("MCCS-for-PaSD reports that port {port_no} has changed"),
    converters={"port_no": int},
)
def check_pasd_port_power_changed(
    change_event_callbacks: MockTangoEventCallbackGroup,
    clipboard: dict,
) -> None:
    """
    Check the power state of port given by port no has/will change.

    :param change_event_callbacks: dictionary of Tango change event
        callbacks with asynchrony support.
    :param clipboard: a place to store information across BDD steps.
    """
    change_event_callbacks[
        f"{get_pasd_bus_name()}/fndhPortsPowerSensed"
    ].assert_change_event(
        clipboard["expected_power_sensed"],
        lookahead=3,  # TODO: This isn't needed at all in lightweight testing
        consume_nonmatches=True,
    )
