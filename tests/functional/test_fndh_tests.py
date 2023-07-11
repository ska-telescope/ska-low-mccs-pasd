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
from ska_control_model import AdminMode, PowerState

gc.disable()


@scenario("features/fndh_deployment.feature", "Fndh can change port power")
def test_fndh() -> None:
    """
    Test basic monitoring of a FNDH.

    Any code in this scenario method is run at the *end* of the
    scenario.
    """


@given(parsers.parse("A {device_name} which is ready"))
def get_ready_device(device_name: str, set_device_state: Callable) -> None:
    """
    Get device in state ON and adminmode ONLINE.

    :param device_name: FQDN of device under test.
    :param set_device_state: function to set device state.
    """
    print(f"Setting device {device_name} ready...")
    set_device_state(device=device_name, state=tango.DevState.ON, mode=AdminMode.ONLINE)


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
    power_map = {False: PowerState.OFF, True: PowerState.ON, None: PowerState.UNKNOWN}
    timeout = 10  # Seconds
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
    fndh_device: tango.DeviceProxy,
    port_no: int,
    queue_command: Callable,
    check_fastcommand: Callable,
) -> None:
    """
    Power on port given by port no.

    :param fndh_device: a proxy to the FNDH device.
    :param port_no: the port number of the FNDH.
    :param queue_command: fixture for queuing command on device.
    :param check_fastcommand: fixture for checking fast command result.
    """
    if check_fastcommand(fndh_device, "PortPowerState", port_no) == PowerState.OFF:
        queue_command(fndh_device, "PowerOnPort", port_no)
    else:
        queue_command(fndh_device, "PowerOffPort", port_no)


@then(
    parsers.parse("MCCS-for-PaSD reports that port {port_no} has changed"),
    converters={"port_no": int},
)
def check_pasd_port_power_changed(
    pasd_bus_device: tango.DeviceProxy, check_change_event: Callable
) -> None:
    """
    Check the power state of port given by port no has/will change.

    :param pasd_bus_device: a proxy to the PaSD bus device.
    :param check_change_event: a fixture for checking if change event received.
    """
    check_change_event(pasd_bus_device, "fndhPortsPowerSensed")
