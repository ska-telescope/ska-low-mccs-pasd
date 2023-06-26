# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a register mapping utility for the PaSD bus."""
from __future__ import annotations

from typing import Any, Callable, Final, List

from .pasd_bus_conversions import PasdConversionUtility


class PasdBusAttribute:
    """Class representing a Modbus attribute stored on a Smartbox or FNDH."""

    def __init__(
        self: PasdBusAttribute,
        address: int,
        count: int,
        conversion_function: Callable = PasdConversionUtility.default_conversion,
    ):
        """Initialise a new instance.

        :param address: starting register address
        :param count: number of registers containing the attribute
        :param conversion_function: callable function to scale the value
        """
        self._address = address
        self._count = count
        self._conversion_function = conversion_function

    @property
    def address(self: PasdBusAttribute) -> int:
        """
        Return the starting register address.

        :return: the starting register address
        """
        return self._address

    @property
    def count(self: PasdBusAttribute) -> int:
        """
        Return the number of registers containing this attribute.

        :return: the register count for this attribute
        """
        return self._count

    def convert_value(self: PasdBusAttribute, values: List[Any]) -> Any:
        """
        Execute the attribute's conversion function on the supplied value.

        Convert the raw register value(s) into a meaningful value

        :param values: a list of the raw value(s) to convert
        :return: the converted value
        """
        return self._conversion_function(values)


class PasdBusRegisterMap:
    """A register mapping utility for the PaSD."""

    _FNDH_ADDRESS: Final = 101

    # Dictionary mapping FNDH attribute name (as used by clients) to
    # PasdBusAttribute
    _FNDH_REGISTER_MAP: Final = {
        "modbus_register_map_revision": PasdBusAttribute(0, 1),
        "pcb_revision": PasdBusAttribute(1, 1),
        "cpu_id": PasdBusAttribute(2, 2, PasdConversionUtility.convert_cpu_id),
        "chip_id": PasdBusAttribute(4, 8, PasdConversionUtility.convert_chip_id),
        "firmware_version": PasdBusAttribute(12, 1),
        "uptime": PasdBusAttribute(13, 2, PasdConversionUtility.bytes_to_n),
        "sys_address": PasdBusAttribute(15, 1),
        "psu48v_voltages": PasdBusAttribute(16, 2, PasdConversionUtility.scale_48v),
        "psu48v_current": PasdBusAttribute(
            18, 1, PasdConversionUtility.scale_48vcurrent
        ),
        "psu48v_temperature": PasdBusAttribute(19, 2, PasdConversionUtility.scale_temp),
        "pcb_temperature": PasdBusAttribute(21, 1, PasdConversionUtility.scale_temp),
        "outside_temperature": PasdBusAttribute(
            22, 1, PasdConversionUtility.scale_temp
        ),
        "humidity": PasdBusAttribute(23, 1),
        "status": PasdBusAttribute(24, 1),
        "led_pattern": PasdBusAttribute(25, 1),
        # TODO: Handle port attributes
        # "ports_connected": PortStatus(36, 28),
        # "port_forcings": PortStatus(36, 28),
        # "ports_power_sensed": PortStatus(36, 28),
        # "ports_desired_power_when_online": PortStatus(36, 28),
        # "ports_desired_power_when_offline": PortStatus(36, 28),
    }

    # Inverse dictionary mapping register number (address) to
    # attribute name, to be used by the server simulation
    _FNDH_REGISTER_INVERSE_MAP: Final = {
        v.address: k for k, v in _FNDH_REGISTER_MAP.items()
    }

    # Dictionary mapping smartbox attribute name (as used by clients) to
    # PasdAttribute
    _SMARTBOX_REGISTER_MAP: Final = {
        "modbus_register_map_revision": PasdBusAttribute(0, 1),
        "pcb_revision": PasdBusAttribute(1, 1),
        "cpu_id": PasdBusAttribute(2, 2, PasdConversionUtility.convert_cpu_id),
        "chip_id": PasdBusAttribute(4, 8),
        "firmware_version": PasdBusAttribute(12, 1),
        "uptime": PasdBusAttribute(13, 2, PasdConversionUtility.bytes_to_n),
        "sys_address": PasdBusAttribute(15, 1),
        "input_voltage": PasdBusAttribute(16, 1, PasdConversionUtility.scale_48v),
        "power_supply_output_voltage": PasdBusAttribute(
            18, 1, PasdConversionUtility.scale_5v
        ),
        "psu_temperature": PasdBusAttribute(18, 1, PasdConversionUtility.scale_temp),
        "pcb_temperature": PasdBusAttribute(19, 1, PasdConversionUtility.scale_temp),
        "outside_temperature": PasdBusAttribute(
            20, 1, PasdConversionUtility.scale_temp
        ),
        "status": PasdBusAttribute(21, 1),
        "led_pattern": PasdBusAttribute(22, 1),
        # TODO: Handle port attributes
        # "ports_connected": PortStatus(36, 12),
        # "port_forcings": PortStatus(36, 12),
        # "port_breakers_tripped": PortStatus(36, 12),
        # "ports_desired_power_when_online": PortStatus(36, 12),
        # "ports_desired_power_when_offline": PortStatus(36, 12),
        # "ports_current_draw": PortStatus(48, 12),
    }

    # Inverse dictionary mapping register number to attribute name
    # (to be used by the server simulation)
    _SMARTBOX_REGISTER_INVERSE_MAP: Final = {
        v.address: k for k, v in _SMARTBOX_REGISTER_MAP.items()
    }

    @classmethod
    def get_attributes(
        cls, device_id: int, attribute_names: list[str]
    ) -> dict[str, PasdBusAttribute]:
        """
        Map a list of attribute names to PasdAttribute objects.

        :param device_id: the ID of the smartbox / FNDH device
        :param attribute_names: name of the attribute(s)

        :return: A dictionary mapping attribute names to PasdAttributes,
            inserted in Modbus address order
        """
        if device_id == cls._FNDH_ADDRESS:
            return {
                name: attr
                for name, attr in cls._FNDH_REGISTER_MAP.items()
                if name in attribute_names
            }
        return {
            name: attr
            for name, attr in cls._SMARTBOX_REGISTER_MAP.items()
            if name in attribute_names
        }

    @classmethod
    def get_attribute_names(cls, device_id: int, addresses: list[int]) -> list[str]:
        """
        Map a list of register numbers to attribute names.

        :param device_id: The ID of the smartbox / FNDH device
        :param addresses: Starting address(es) of the desired Modbus registers

        :return: A list of the corresponding string attribute names
        """
        if device_id == cls._FNDH_ADDRESS:
            return [cls._FNDH_REGISTER_INVERSE_MAP[address] for address in addresses]
        return [cls._SMARTBOX_REGISTER_INVERSE_MAP[address] for address in addresses]
