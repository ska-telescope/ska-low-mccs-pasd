# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides common code for all PaSD devices."""

from logging import Logger

from tango import Attribute


def configure_alarms(
    attribute: Attribute, alarm_values: list[float], logger: Logger
) -> None:
    """Configure the alarm properties for a Tango attribute.

    :param attribute: Tango Attribute to configure
    :param alarm_values: list of alarm threshold values in the order:
        max_alarm; max_warning; min_warning; min_alarm
    :param logger: Logger object to log warning messages with
    """
    multi_prop = attribute.get_properties()
    # Threshold values always reported in the order:
    # high alarm - high warning - low warning - low alarm
    if min(alarm_values[0], alarm_values[1]) <= max(alarm_values[2], alarm_values[3]):
        logger.warn(
            f"Invalid alarm configuration detected for {attribute.get_name()}: "
            f"[{alarm_values[0]}, {alarm_values[1]}, "
            f"{alarm_values[2]}, {alarm_values[3]}]"
        )
        return

    if alarm_values[0] <= alarm_values[1]:
        logger.warn(
            f"High alarm value {alarm_values[0]} for {attribute.get_name()} "
            f"is <= warning value {alarm_values[1]}"
        )
        multi_prop.max_alarm = max(alarm_values[0], alarm_values[1])
    else:
        multi_prop.max_alarm = alarm_values[0]
        multi_prop.max_warning = alarm_values[1]

    if alarm_values[2] <= alarm_values[3]:
        logger.warn(
            f"Low warning value {alarm_values[2]} for {attribute.get_name()} "
            f"is <= alarm value {alarm_values[3]}"
        )
        multi_prop.min_alarm = min(alarm_values[2], alarm_values[3])
    else:
        multi_prop.min_warning = alarm_values[2]
        multi_prop.min_alarm = alarm_values[3]
    attribute.set_properties(multi_prop)
