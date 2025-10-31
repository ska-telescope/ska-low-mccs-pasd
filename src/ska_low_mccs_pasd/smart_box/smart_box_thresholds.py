#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module gives the thresholds for a smartbox device."""

# pylint: disable-all

from __future__ import annotations

__all__ = ["SmartBoxThresholds"]


# class FNCPThresholds:  # USE LATER
#     psu48v_voltage_1_thresholds: dict[str, float] = {}
#     psu48v_voltage_2_thresholds: dict[str, float] = {}
#     psu48v_current_thresholds: dict[str, float] = {}
#     psu48v_temperature_1_thresholds: dict[str, float] = {}
#     psu48v_temperature_2_thresholds: dict[str, float] = {}
#     panel_temperature_thresholds: dict[str, float] = {}
#     fncb_temperature_thresholds: dict[str, float] = {}
#     fncb_humidity_thresholds: dict[str, float] = {}
#     comms_gateway_temperature_thresholds: dict[str, float] = {}
#     power_module_temperature_thresholds: dict[str, float] = {}
#     outside_temperature_thresholds: dict[str, float] = {}
#     internal_ambient_temperature_thresholds: dict[str, float] = {}


class SmartBoxThresholds:
    """Smartbox thresholds."""

    input_voltage_thresholds: dict[str, float] = {}
    power_supply_output_voltage_thresholds: dict[str, float] = {}
    power_supply_temperature_thresholds: dict[str, float] = {}
    pcb_temperature_thresholds: dict[str, float] = {}
    fem_ambient_temperature_thresholds: dict[str, float] = {}
    fem_case_temperature_1_thresholds: dict[str, float] = {}
    fem_case_temperature_2_thresholds: dict[str, float] = {}
    fem_heatsink_temperature_1_thresholds: dict[str, float] = {}
    fem_heatsink_temperature_2_thresholds: dict[str, float] = {}
    fem_current_trip_thresholds: dict[str, float] = {}

    def update(self: SmartBoxThresholds, new_thresholds: dict[str, dict]) -> None:
        """
        Update the thresholds with new values.

        :param new_thresholds: New thresholds to be updated.
        """
        for name, values in new_thresholds.items():
            setattr(self, name, values)

    def all_thresholds(self: SmartBoxThresholds) -> dict:
        """
        Return all thresholds in dict.

        :return: all thresholds in dict.
        """
        thresholds = {
            "input_voltage_thresholds": self.input_voltage_thresholds,
            "power_supply_output_voltage_thresholds": self.power_supply_output_voltage_thresholds,
            "power_supply_temperature_thresholds": self.power_supply_temperature_thresholds,
            "pcb_temperature_thresholds": self.pcb_temperature_thresholds,
            "fem_ambient_temperature_thresholds": self.fem_ambient_temperature_thresholds,
            "fem_case_temperature_1_thresholds": self.fem_case_temperature_1_thresholds,
            "fem_case_temperature_2_thresholds": self.fem_case_temperature_2_thresholds,
            "fem_heatsink_temperature_1_thresholds": self.fem_heatsink_temperature_1_thresholds,
            "fem_heatsink_temperature_2_thresholds": self.fem_heatsink_temperature_2_thresholds,
            "fem_current_trip_thresholds": self.fem_current_trip_thresholds,
        }
        return thresholds
