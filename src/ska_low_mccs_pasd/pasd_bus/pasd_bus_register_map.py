# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a register mapping utility for the PaSD bus."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Final, List

from .pasd_bus_conversions import PasdConversionUtility

logger = logging.getLogger()


class PortStatusString(Enum):
    """Enum type for port status strings."""

    PORTS_CONNECTED = "ports_connected"
    PORT_FORCINGS = "port_forcings"
    BREAKERS_TRIPPED = "port_breakers_tripped"
    DSON = "ports_desired_power_when_online"
    DSOFF = "ports_desired_power_when_offline"
    POWER_SENSED = "ports_power_sensed"


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


class PasdBusPortAttribute(PasdBusAttribute):
    """Class representing a port status attribute."""

    def __init__(
        self: PasdBusPortAttribute,
        address: int,
        count: int,
        desired_info: PortStatusString,
    ):
        """Initialise a new instance.

        :param address: starting register address
        :param count: number of registers containing the port data
        :param desired_info: port status attribute of interest
            (must match member of PortStatusStrings)
        """
        super().__init__(address, count, self.parse_port_bitmaps)
        self.desired_info = desired_info

    def parse_port_bitmaps(
        self: PasdBusPortAttribute, values: List[int]
    ) -> List[bool | str | None]:
        """
        Parse the port register bitmap data into the desired port information.

        :param: values: list of raw port bitmaps (one per port)
        :return: list of flags representing the desired port information
        """
        forcing_map = {
            True: "ON",
            False: "OFF",
            None: "NONE",
        }
        results: List[bool | str | None] = []
        for status_bitmap, port_number in zip(values, range(1, len(values) + 1)):
            bitstring = f"{status_bitmap:016b}"
            match (self.desired_info):
                case PortStatusString.DSON | PortStatusString.DSOFF:
                    if bitstring[2:4] == "10":
                        results.append(False)
                    elif bitstring[2:4] == "11":
                        results.append(True)
                    else:
                        logger.warning(
                            f"Unknown {self.desired_info.value} flag {bitstring[2:4]}"
                            f" for port {port_number}"
                        )
                        results.append(None)
                case PortStatusString.PORT_FORCINGS:
                    if bitstring[6:8] == "10":
                        results.append(forcing_map[False])
                    elif bitstring[6:8] == "11":
                        results.append(forcing_map[True])
                    elif bitstring[6:8] == "01":
                        results.append(forcing_map[None])
                    else:
                        logger.warning(
                            f"Unknown port forcing: {bitstring[2:4]}"
                            f" for port {port_number}"
                        )
                        results.append(forcing_map[None])
                case PortStatusString.BREAKERS_TRIPPED:
                    results.append(bitstring[8] == "1")
                case PortStatusString.POWER_SENSED:
                    results.append(bitstring[9] == "1")
        return results


class PasdBusRegisterMap:
    """A register mapping utility for the PaSD."""

    _FNDH_ADDRESS: Final = 101

    # Dictionary mapping FNDH attribute name (as used by clients) to
    # PasdBusAttribute. These must be stored in Modbus address order
    _FNDH_REGISTER_MAP: Final = {
        "modbus_register_map_revision": PasdBusAttribute(0, 1),
        "pcb_revision": PasdBusAttribute(1, 1),
        "cpu_id": PasdBusAttribute(2, 2, PasdConversionUtility.convert_to_hex),
        "chip_id": PasdBusAttribute(4, 8, PasdConversionUtility.convert_to_hex),
        "firmware_version": PasdBusAttribute(12, 1),
        "uptime": PasdBusAttribute(13, 2, PasdConversionUtility.convert_uptime),
        "sys_address": PasdBusAttribute(15, 1),
        "psu48v_voltages": PasdBusAttribute(16, 2, PasdConversionUtility.scale_48vs),
        "psu48v_current": PasdBusAttribute(
            18, 1, PasdConversionUtility.scale_48vcurrents
        ),
        "psu48v_temperature": PasdBusAttribute(
            19, 2, PasdConversionUtility.scale_temps
        ),
        "pcb_temperature": PasdBusAttribute(21, 1, PasdConversionUtility.scale_temps),
        "outside_temperature": PasdBusAttribute(
            22, 1, PasdConversionUtility.scale_temps
        ),
        "humidity": PasdBusAttribute(23, 1),
        "status": PasdBusAttribute(24, 1),
        "led_pattern": PasdBusAttribute(25, 1),
        "ports_connected": PasdBusPortAttribute(
            35, 28, PortStatusString.PORTS_CONNECTED
        ),
        "port_forcings": PasdBusPortAttribute(35, 28, PortStatusString.PORT_FORCINGS),
        "port_breakers_tripped": PasdBusPortAttribute(
            35, 28, PortStatusString.BREAKERS_TRIPPED
        ),
        "ports_desired_power_when_online": PasdBusPortAttribute(
            35, 28, PortStatusString.DSON
        ),
        "ports_desired_power_when_offline": PasdBusPortAttribute(
            35, 28, PortStatusString.DSOFF
        ),
        "ports_power_sensed": PasdBusPortAttribute(
            35, 28, PortStatusString.POWER_SENSED
        ),
    }

    # Inverse dictionary mapping register number (address) to
    # attribute name, to be used by the server simulation
    _FNDH_REGISTER_INVERSE_MAP: Final = {
        v.address: k for k, v in _FNDH_REGISTER_MAP.items()
    }

    # Dictionary mapping smartbox attribute name (as used by clients) to
    # PasdAttribute. These must be stored in Modbus address order
    _SMARTBOX_REGISTER_MAP: Final = {
        "modbus_register_map_revision": PasdBusAttribute(0, 1),
        "pcb_revision": PasdBusAttribute(1, 1),
        "cpu_id": PasdBusAttribute(2, 2, PasdConversionUtility.convert_to_hex),
        "chip_id": PasdBusAttribute(4, 8, PasdConversionUtility.convert_to_hex),
        "firmware_version": PasdBusAttribute(12, 1),
        "uptime": PasdBusAttribute(13, 2, PasdConversionUtility.convert_uptime),
        "sys_address": PasdBusAttribute(15, 1),
        "input_voltage": PasdBusAttribute(16, 1, PasdConversionUtility.scale_48vs),
        "power_supply_output_voltage": PasdBusAttribute(
            18, 1, PasdConversionUtility.scale_5vs
        ),
        "psu_temperature": PasdBusAttribute(18, 1, PasdConversionUtility.scale_temps),
        "pcb_temperature": PasdBusAttribute(19, 1, PasdConversionUtility.scale_temps),
        "outside_temperature": PasdBusAttribute(
            20, 1, PasdConversionUtility.scale_temps
        ),
        "status": PasdBusAttribute(21, 1),
        "led_pattern": PasdBusAttribute(22, 1),
        "sensor_status": PasdBusAttribute(23, 12),
        "ports_connected": PasdBusPortAttribute(
            35, 12, PortStatusString.PORTS_CONNECTED
        ),
        "port_forcings": PasdBusPortAttribute(35, 12, PortStatusString.PORT_FORCINGS),
        "port_breakers_tripped": PasdBusPortAttribute(
            35, 12, PortStatusString.BREAKERS_TRIPPED
        ),
        "ports_desired_power_when_online": PasdBusPortAttribute(
            35, 12, PortStatusString.DSON
        ),
        "ports_desired_power_when_offline": PasdBusPortAttribute(
            35, 12, PortStatusString.DSOFF
        ),
        "ports_power_sensed": PasdBusPortAttribute(
            35, 12, PortStatusString.POWER_SENSED
        ),
        "ports_current_draw": PasdBusAttribute(47, 12),
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
