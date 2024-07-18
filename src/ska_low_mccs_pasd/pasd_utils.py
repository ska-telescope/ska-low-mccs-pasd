# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides common code for all PaSD devices."""

from tango import Attribute


def configure_alarms(attribute: Attribute, alarm_values: list[float]) -> None:
    """Configure the alarm properties for a Tango attribute.

    :param attribute: Tango Attribute to configure
    :param alarm_values: list of alarm threshold values in the order:
        max_alarm; max_warning; min_warning; min_alarm
    """
    multi_prop = attribute.get_properties()
    # Threshold values always reported in the order:
    # high alarm - high warning - low warning - low alarm
    multi_prop.max_alarm = alarm_values[0]
    multi_prop.max_warning = alarm_values[1]
    multi_prop.min_warning = alarm_values[2]
    multi_prop.min_alarm = alarm_values[3]
    attribute.set_properties(multi_prop)
