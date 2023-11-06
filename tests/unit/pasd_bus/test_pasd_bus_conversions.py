# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus conversion functions."""
from typing import Any, Callable

import pytest

from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import (
    FndhAlarmFlags,
    FndhStatusMap,
    LEDServiceMap,
    LEDStatusMap,
    PasdConversionUtility,
    SmartboxAlarmFlags,
    SmartboxStatusMap,
)
from ska_low_mccs_pasd.pasd_bus.pasd_bus_register_map import (
    PasdBusPortAttribute,
    PortStatusBits,
)


@pytest.mark.parametrize(
    ["conversion_function", "forward_input", "expected_forward_result"],
    [
        pytest.param(
            PasdConversionUtility.convert_cpu_id,
            [2, 4],
            ["0x204"],
            id="convert_cpu_id",
        ),
        pytest.param(
            PasdConversionUtility.convert_chip_id,
            [8, 7, 6, 5, 4, 3, 2, 1],
            ["00080007000600050004000300020001"],
            id="convert_chip_id",
        ),
        pytest.param(
            PasdConversionUtility.convert_firmware_version,
            [257],
            ["257"],
            id="convert_firmware_version",
        ),
        pytest.param(
            PasdConversionUtility.convert_uptime,
            [8, 6],
            [2054],
            id="convert_uptime",
        ),
        pytest.param(
            PasdConversionUtility.default_conversion,
            [8, 7, 6, 5, 4, 3, 2, 1],
            [8, 7, 6, 5, 4, 3, 2, 1],
            id="default_conversion",
        ),
        pytest.param(
            PasdConversionUtility.scale_volts,
            [0, 45547, 123, 23, 0, 65535, 1, 10000],
            [0.0, 455.47, 1.23, 0.23, 0.0, 655.35, 0.01, 100.0],
            id="scale_volts",
        ),
        pytest.param(
            PasdConversionUtility.scale_signed_16bit,
            [0, 45547, 123, 23, 0, 65535, 1, 10000],
            [0.0, -199.89, 1.23, 0.23, 0.0, -0.01, 0.01, 100.0],
            id="scale_signed_16bit",
        ),
        pytest.param(
            PasdConversionUtility.scale_48vcurrents,
            [0, 45547, 123, 23, 0, 65535, 1, 10000],
            [0.0, 455.47, 1.23, 0.23, 0.0, 655.35, 0.01, 100.0],
            id="scale_48vcurrents",
        ),
    ],
)
def test_conversion_function(
    conversion_function: Callable, forward_input: Any, expected_forward_result: Any
) -> None:
    """
    Test conversion functions between register values and actual values.

    Also test that the conversion function then the inverse conversion function
    results in no change

    :param conversion_function: the conversion function to test
    :param forward_input: the input for the conversion function, when converting
        not using the inverse. This is the expected result when using the inverse.
    :param expected_forward_result: the expected result for the conversion function,
        when converting not using the inverse. This is the input when using the inverse.
    """
    forward_result = conversion_function(forward_input, inverse=False)
    assert forward_result == expected_forward_result

    # Now test function is reversible

    reverse_result = conversion_function(forward_result, inverse=True)
    assert reverse_result == forward_input


@pytest.mark.parametrize(
    [
        "conversion_function",
        "forward_input",
        "expected_forward_result",
        "reverse_input",
    ],
    [
        pytest.param(
            PasdConversionUtility.convert_fndh_alarm_status,
            [5],
            "SYS_48V1_V, SYS_48V_I",
            [FndhAlarmFlags.SYS_48V1_V, FndhAlarmFlags.SYS_48V_I],
            id="convert_fndh_alarm_status",
        ),
        pytest.param(
            PasdConversionUtility.convert_smartbox_alarm_status,
            [15],
            "SYS_48V_V, SYS_PSU_V, SYS_PSU_TEMP, SYS_PCB_TEMP",
            [
                SmartboxAlarmFlags.SYS_48V_V,
                SmartboxAlarmFlags.SYS_PSU_V,
                SmartboxAlarmFlags.SYS_PSU_TEMP,
                SmartboxAlarmFlags.SYS_PCB_TEMP,
            ],
            id="convert_smartbox_alarm_status",
        ),
        pytest.param(
            PasdConversionUtility.convert_fndh_status,
            [5],
            ["POWERUP"],
            [FndhStatusMap.POWERUP],
            id="convert_fndh_status",
        ),
        pytest.param(
            PasdConversionUtility.convert_smartbox_status,
            [3],
            ["RECOVERY"],
            [SmartboxStatusMap.RECOVERY],
            id="convert_smartbox_status",
        ),
        pytest.param(
            PasdConversionUtility.convert_led_status,
            [289],
            "service: ON, status: REDVFAST",
            [LEDServiceMap.ON, LEDStatusMap.REDVFAST],
            id="convert_led_status",
        ),
    ],
)
def test_non_reversible_conversion_function(
    conversion_function: Callable,
    forward_input: Any,
    expected_forward_result: Any,
    reverse_input: Any,
) -> None:
    """
    Test conversion functions between register values and actual values.

    Also tests the inverse of the conversion function, which will take different inputs
    to the outputs of the forward to conversion function.

    :param conversion_function: the conversion function to test
    :param forward_input: the input for the conversion function, when converting
        not using the inverse. This is the expected result when using the inverse.
    :param expected_forward_result: the expected result for the conversion function,
        when converting not using the inverse.
    :param reverse_input: the input to use when testing the inverse conversion function.
    """
    forward_result = conversion_function(forward_input, inverse=False)
    assert forward_result == expected_forward_result

    # Now test reverse of function

    reverse_result = conversion_function(reverse_input, inverse=True)
    assert reverse_result == forward_input


@pytest.mark.parametrize(
    ["desired_info", "forward_input", "expected_forward_result"],
    [
        pytest.param(
            PortStatusBits.DSON,
            [(1 << 12) + (1 << 13)],
            [True],
            id="DSON_11",
        ),
        pytest.param(
            PortStatusBits.DSON,
            [(1 << 13)],
            [False],
            id="DSON_10",
        ),
        pytest.param(
            PortStatusBits.DSOFF,
            [(1 << 10) + (1 << 11)],
            [True],
            id="DSOFF_11",
        ),
        pytest.param(
            PortStatusBits.DSOFF,
            [(1 << 11)],
            [False],
            id="DSOFF_10",
        ),
        pytest.param(
            PortStatusBits.TO,
            [(1 << 8)],
            ["ON"],
            id="PORT_FORCINGS_01",
        ),
        pytest.param(
            PortStatusBits.TO,
            [(1 << 9)],
            ["OFF"],
            id="PORT_FORCINGS_10",
        ),
        pytest.param(
            PortStatusBits.TO,
            [0],
            ["NONE"],
            id="PORT_FORCINGS_00",
        ),
        pytest.param(
            PortStatusBits.PWRSENSE_BREAKER,
            [(1 << 7)],
            [True],
            id="BREAKERS_TRIPPED_1",
        ),
        pytest.param(
            PortStatusBits.PWRSENSE_BREAKER,
            [0],
            [False],
            id="BREAKERS_TRIPPED_0",
        ),
        pytest.param(
            PortStatusBits.PWRSENSE_BREAKER,
            [(1 << 7)],
            [True],
            id="POWER_SENSED_1",
        ),
        pytest.param(
            PortStatusBits.PWRSENSE_BREAKER,
            [0],
            [False],
            id="POWER_SENSED_0",
        ),
        pytest.param(
            PortStatusBits.POWER,
            [(1 << 6)],
            [True],
            id="POWER_1",
        ),
        pytest.param(
            PortStatusBits.POWER,
            [0],
            [False],
            id="POWER_0",
        ),
    ],
)
def test_port_attribute_conversion(
    desired_info: PortStatusBits, forward_input: Any, expected_forward_result: Any
) -> None:
    """
    Test conversion function for port attributes.

    Also test that the conversion function then the inverse conversion function
    results in no change

    :param desired_info: the info to test conversion for
    :param forward_input: the input for the conversion function, when converting
        not using the inverse. This is the expected result when using the inverse.
    :param expected_forward_result: the expected result for the conversion function,
        when converting not using the inverse. This is the input when using the inverse.
    """
    attribute = PasdBusPortAttribute(0, 1, desired_info)

    forward_result = attribute.convert_value(forward_input)
    assert forward_result == expected_forward_result

    # Now test function is reversible

    reverse_result = attribute.convert_write_value(forward_result)
    assert reverse_result == forward_input
