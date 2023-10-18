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
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Final, List, Optional, Sequence

from .pasd_bus_conversions import PasdConversionUtility

logger = logging.getLogger()


class PasdReadError(Exception):
    """Exception to be raised for invalid read requests."""

    def __init__(self: PasdReadError, attribute1: str, attribute2: str):
        """Initialize new instance.

        :param attribute1: name of the first attribute causing the error
        :param attribute2: name of the second
        """
        logger.error(f"Non-contiguous registers requested: {attribute1}, {attribute2}")
        super().__init__(
            f"Non-contiguous registers requested: {attribute1}, {attribute2}"
        )


class PasdWriteError(Exception):
    """Exception to be raised for invalid write requests."""

    def __init__(self: PasdWriteError, attribute: str):
        """Initialize new instance.

        :param attribute: name of the requested attribute
        """
        logger.error(f"Non-writeable register requested for write: {attribute}")
        super().__init__(f"Non-writeable register requestedfor write: {attribute}")


class PortStatusString(Enum):
    """Enum type for port status strings."""

    PORT_FORCINGS = "port_forcings"
    BREAKERS_TRIPPED = "port_breakers_tripped"
    DSON = "ports_desired_power_when_online"
    DSOFF = "ports_desired_power_when_offline"
    POWER_SENSED = "ports_power_sensed"
    POWER = "power"


class PasdCommandStrings(Enum):
    """Enum type for PaSD command strings."""

    TURN_PORT_ON = "turn_port_on"
    TURN_PORT_OFF = "turn_port_off"
    RESET_PORT_BREAKER = "reset_port_breaker"
    SET_LED_PATTERN = "set_led_pattern"
    INITIALIZE = "initialize"
    RESET_ALARMS = "reset_alarms"
    RESET_WARNINGS = "reset_warnings"


class PasdServiceLEDPattern(Enum):
    """Enum type for service LED patterns."""

    OFF = 0
    SERVICE = 256


class PasdBusAttribute:
    """Class representing a Modbus attribute stored on a Smartbox or FNDH.

    This stores the starting register address and count (number of registers)
    containing this attribute, and a conversion function used to convert
    the raw register value into engineering units / status strings for
    read operations.

    It is also used to store the value to be written to the register for
    command operations.
    """

    def __init__(
        self: PasdBusAttribute,
        address: int,
        count: int,
        conversion_function: Callable = PasdConversionUtility.default_conversion,
        writeable: bool = False,
    ):
        """Initialise a new instance.

        :param address: starting register address
        :param count: number of registers containing the attribute
        :param conversion_function: callable function to scale the value
        :param writeable: True if the attribute is read/write
        """
        self._address = address
        self._count = count
        self._conversion_function = conversion_function
        self._writeable = writeable

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

    @property
    def value(self: PasdBusAttribute) -> int | List[int]:
        """
        Return the value to be set for this attribute.

        :return: the desired value as a raw integer or list of ints.
        """
        return self._value

    @value.setter
    def value(self: PasdBusAttribute, value: int | List[int]) -> None:
        """
        Set a new value for this attribute.

        :param value: the desired new value(s) as raw integer(s)
        """
        self._value = value

    def convert_value(self: PasdBusAttribute, values: List[Any]) -> Any:
        """
        Execute the attribute's conversion function on the supplied value.

        Convert the raw register value(s) into a meaningful value

        :param values: a list of the raw value(s) to convert
        :return: the converted value
        """
        return self._conversion_function(values)

    def convert_write_value(self: PasdBusAttribute, values: List[Any]) -> Any:
        """
        Execute the attribute's conversion function on the supplied value.

        Convert the desired user value into a raw register value

        :param values: a list of the user values to convert
        :return: the raw converted values
        """
        return self._conversion_function(values, inverse=True)


class PasdBusPortAttribute(PasdBusAttribute):
    """Class representing a port status attribute."""

    def __init__(
        self: PasdBusPortAttribute,
        address: int,
        count: int,
        desired_info: Optional[PortStatusString] = None,
    ):
        """Initialise a new instance.

        :param address: starting register address
        :param count: number of registers containing the port data
        :param desired_info: port status attribute of interest if
            reading status (must match member of PortStatusStrings)
        """
        super().__init__(address, count, self._parse_port_bitmaps)
        self.desired_info = desired_info

    def _parse_port_bitmaps(
        self: PasdBusPortAttribute,
        values: List[int | bool | str | None],
        inverse: bool = False,
    ) -> List[bool | str | None, int]:
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
        if isinstance(values[0], list):
            values = values[0]
        if inverse:
            results: List[int] = []
            for value in values:
                bitstring = "00"

                if self.desired_info == PortStatusString.DSON:
                    bitstring += "11" if value else "10"
                else:
                    bitstring += "00"

                if self.desired_info == PortStatusString.DSOFF:
                    bitstring += "11" if value else "10"
                else:
                    bitstring += "00"

                if self.desired_info == PortStatusString.PORT_FORCINGS:
                    if value == forcing_map[True]:
                        bitstring += "11"
                    elif value == forcing_map[False]:
                        bitstring += "10"
                    else:
                        bitstring += "00"
                else:
                    bitstring += "00"

                if self.desired_info == PortStatusString.BREAKERS_TRIPPED:
                    bitstring += "1" if value else "0"
                elif self.desired_info == PortStatusString.POWER_SENSED:
                    bitstring += "1" if value else "0"
                else:
                    bitstring += "0"

                if self.desired_info == PortStatusString.POWER:
                    bitstring += "1" if value else "0"
                else:
                    bitstring += "0"

                bitstring += "000000"  # pad to 16 bits
                results.append(int(bitstring, 2))
            return results
        results: List[bool | str | None] = []
        for status_bitmap in values:
            bitstring = f"{status_bitmap:016b}"
            match (self.desired_info):
                case PortStatusString.DSON:
                    if bitstring[2:4] == "11":
                        results.append(True)
                    else:
                        results.append(False)
                case PortStatusString.DSOFF:
                    if bitstring[4:6] == "11":
                        results.append(True)
                    else:
                        results.append(False)
                case PortStatusString.PORT_FORCINGS:
                    if bitstring[6:8] == "10":
                        results.append(forcing_map[False])
                    elif bitstring[6:8] == "11":
                        results.append(forcing_map[True])
                    else:
                        results.append(forcing_map[None])
                case PortStatusString.BREAKERS_TRIPPED:  # Smartboxes only
                    results.append(bitstring[8] == "1")
                case PortStatusString.POWER_SENSED:  # FNDH only
                    results.append(bitstring[8] == "1")
                case PortStatusString.POWER:
                    results.append(bitstring[9] == "1")
        return results

    def _set_bitmap_value(
        self: PasdBusPortAttribute,
        desired_on_online: Optional[bool],
        desired_on_offline: Optional[bool],
        reset_breaker: bool = False,
    ) -> None:
        # First two bits are read-only (ENABLE and ONLINE)
        bitstring = "00"

        if desired_on_online is None:
            bitstring += "00"
        else:
            bitstring += "11" if desired_on_online else "10"

        if desired_on_offline is None:
            bitstring += "00"
        else:
            bitstring += "11" if desired_on_offline else "10"

        # Next two bits are read-only (FORCED ON / OFF)
        bitstring += "00"

        bitstring += "1" if reset_breaker else "0"

        bitstring += "0000000"  # pad to 16 bits
        self.value = int(bitstring, 2)


@dataclass
class PasdBusRegisterInfo:
    """Hold register information for a PaSD device."""

    register_map: dict[str, PasdBusAttribute]
    number_of_ports: int
    starting_port_register: int


class PasdBusRegisterMap:
    """A register mapping utility for the PaSD."""

    MODBUS_REGISTER_MAP_REVISION = "modbus_register_map_revision"
    LED_PATTERN = "led_pattern"
    STATUS = "status"
    ALARM_FLAGS = "alarm_flags"
    WARNING_FLAGS = "warning_flags"

    # Register map for the 'info' registers, guaranteed to be the same
    # across versions. Used for both the FNDH and smartboxes.
    _INFO_REGISTER_MAP: Final = {
        MODBUS_REGISTER_MAP_REVISION: PasdBusAttribute(0, 1),
        "pcb_revision": PasdBusAttribute(1, 1),
        "cpu_id": PasdBusAttribute(2, 2, PasdConversionUtility.convert_cpu_id),
        "chip_id": PasdBusAttribute(4, 8, PasdConversionUtility.convert_chip_id),
        "firmware_version": PasdBusAttribute(
            12, 1, PasdConversionUtility.convert_firmware_version
        ),
    }

    # Inverse dictionary mapping register number (address) to
    # attribute name, to be used by the server simulation
    _INFO_REGISTER_INVERSE_MAP: Final = {
        v.address: k for k, v in _INFO_REGISTER_MAP.items()
    }

    # Register maps for the attributes which might change across versions
    # NB: The attributes must be inserted in register number order
    _FNDH_REGISTER_MAP_V1: Final = {
        "uptime": PasdBusAttribute(13, 2, PasdConversionUtility.convert_uptime),
        "sys_address": PasdBusAttribute(15, 1),
        "psu48v_voltages": PasdBusAttribute(16, 2, PasdConversionUtility.scale_volts),
        "psu48v_current": PasdBusAttribute(
            18, 1, PasdConversionUtility.scale_48vcurrents
        ),
        "psu48v_temperatures": PasdBusAttribute(
            19, 2, PasdConversionUtility.scale_signed_16bit
        ),
        "panel_temperature": PasdBusAttribute(
            21, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "fncb_temperature": PasdBusAttribute(
            22, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "fncb_humidity": PasdBusAttribute(23, 1),
        STATUS: PasdBusAttribute(24, 1, PasdConversionUtility.convert_fndh_status),
        LED_PATTERN: PasdBusAttribute(25, 1, PasdConversionUtility.convert_led_status),
        "comms_gateway_temperature": PasdBusAttribute(
            26, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "power_module_temperature": PasdBusAttribute(
            27, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "outside_temperature": PasdBusAttribute(
            28, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "internal_ambient_temperature": PasdBusAttribute(
            29, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "port_forcings": PasdBusPortAttribute(35, 28, PortStatusString.PORT_FORCINGS),
        "ports_desired_power_when_online": PasdBusPortAttribute(
            35, 28, PortStatusString.DSON
        ),
        "ports_desired_power_when_offline": PasdBusPortAttribute(
            35, 28, PortStatusString.DSOFF
        ),
        "ports_power_sensed": PasdBusPortAttribute(
            35, 28, PortStatusString.POWER_SENSED
        ),
        "ports_power_control": PasdBusPortAttribute(35, 28, PortStatusString.POWER),
        "psu48v_voltage_1_thresholds": PasdBusAttribute(
            1000, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "psu48v_voltage_2_thresholds": PasdBusAttribute(
            1004, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "psu48v_current_thresholds": PasdBusAttribute(
            1008, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "psu48v_temperature_1_thresholds": PasdBusAttribute(
            1012, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "psu48v_temperature_2_thresholds": PasdBusAttribute(
            1016, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "panel_temperature_thresholds": PasdBusAttribute(
            1020, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fncb_temperature_thresholds": PasdBusAttribute(
            1024, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fncb_humidity_thresholds": PasdBusAttribute(1028, 4, writeable=True),
        "comms_gateway_temperature_thresholds": PasdBusAttribute(
            1032, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "power_module_temperature_thresholds": PasdBusAttribute(
            1036, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "outside_temperature_thresholds": PasdBusAttribute(
            1040, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "internal_ambient_temperature_thresholds": PasdBusAttribute(
            1044, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        WARNING_FLAGS: PasdBusAttribute(
            10129, 1, PasdConversionUtility.convert_fndh_alarm_status
        ),
        ALARM_FLAGS: PasdBusAttribute(
            10131, 1, PasdConversionUtility.convert_fndh_alarm_status
        ),
    }

    _SMARTBOX_REGISTER_MAP_V1: Final = {
        "uptime": PasdBusAttribute(13, 2, PasdConversionUtility.convert_uptime),
        "sys_address": PasdBusAttribute(15, 1),
        "input_voltage": PasdBusAttribute(16, 1, PasdConversionUtility.scale_volts),
        "power_supply_output_voltage": PasdBusAttribute(
            17, 1, PasdConversionUtility.scale_volts
        ),
        "power_supply_temperature": PasdBusAttribute(
            18, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "pcb_temperature": PasdBusAttribute(
            19, 1, PasdConversionUtility.scale_signed_16bit
        ),
        "fem_ambient_temperature": PasdBusAttribute(
            20, 1, PasdConversionUtility.scale_signed_16bit
        ),
        STATUS: PasdBusAttribute(21, 1, PasdConversionUtility.convert_smartbox_status),
        LED_PATTERN: PasdBusAttribute(22, 1, PasdConversionUtility.convert_led_status),
        "fem_case_temperatures": PasdBusAttribute(
            23, 2, PasdConversionUtility.scale_signed_16bit
        ),
        "fem_heatsink_temperatures": PasdBusAttribute(
            25, 2, PasdConversionUtility.scale_signed_16bit
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
        "ports_power_sensed": PasdBusPortAttribute(35, 12, PortStatusString.POWER),
        "ports_current_draw": PasdBusAttribute(47, 12),
        "input_voltage_thresholds": PasdBusAttribute(
            1000, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "power_supply_output_voltage_thresholds": PasdBusAttribute(
            1004, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "power_supply_temperature_thresholds": PasdBusAttribute(
            1008, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "pcb_temperature_thresholds": PasdBusAttribute(
            1012, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fem_ambient_temperature_thresholds": PasdBusAttribute(
            1016, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fem_case_temperature_1_thresholds": PasdBusAttribute(
            1020, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fem_case_temperature_2_thresholds": PasdBusAttribute(
            1024, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fem_heatsink_temperature_1_thresholds": PasdBusAttribute(
            1028, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fem_heatsink_temperature_2_thresholds": PasdBusAttribute(
            1032, 4, PasdConversionUtility.scale_signed_16bit, writeable=True
        ),
        "fem1_current_trip_threshold": PasdBusAttribute(
            1068, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem2_current_trip_threshold": PasdBusAttribute(
            1069, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem3_current_trip_threshold": PasdBusAttribute(
            1070, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem4_current_trip_threshold": PasdBusAttribute(
            1071, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem5_current_trip_threshold": PasdBusAttribute(
            1072, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem6_current_trip_threshold": PasdBusAttribute(
            1073, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem7_current_trip_threshold": PasdBusAttribute(
            1074, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem8_current_trip_threshold": PasdBusAttribute(
            1075, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem9_current_trip_threshold": PasdBusAttribute(
            1076, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem10_current_trip_threshold": PasdBusAttribute(
            1077, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem11_current_trip_threshold": PasdBusAttribute(
            1078, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        "fem12_current_trip_threshold": PasdBusAttribute(
            1079, 1, PasdConversionUtility.default_conversion_2, writeable=True
        ),
        WARNING_FLAGS: PasdBusAttribute(
            10129, 1, PasdConversionUtility.convert_smartbox_alarm_status
        ),
        ALARM_FLAGS: PasdBusAttribute(
            10131, 1, PasdConversionUtility.convert_smartbox_alarm_status
        ),
    }

    # Map modbus register revision number to the corresponding PasdRegisterInfo
    _FNDH_REGISTER_MAPS: Final = {
        1: PasdBusRegisterInfo(
            _FNDH_REGISTER_MAP_V1, number_of_ports=28, starting_port_register=35
        )
    }
    _SMARTBOX_REGISTER_MAPS: Final = {
        1: PasdBusRegisterInfo(
            _SMARTBOX_REGISTER_MAP_V1, number_of_ports=12, starting_port_register=35
        )
    }

    def __init__(self, revision_number: int = 1):
        """
        Initialize a new instance.

        :param revision_number: Modbus register map revision number,
            if known (this will be set later after interrogating
            the h/w)
        """
        self._revision_number = revision_number

    @property
    def revision_number(self) -> int:
        """Return the Modbus register map revision number.

        :return: The integer revision number
        """
        return self._revision_number

    @revision_number.setter
    def revision_number(self, value: int) -> None:
        """Set the Modbus register map revision number.

        : param: value: the integer revision number to set
        """
        self._revision_number = value

    def _get_register_info(self, device_id: int) -> PasdBusRegisterInfo:
        if device_id == 0 or device_id == 101:
            return self._FNDH_REGISTER_MAPS[self.revision_number]
        return self._SMARTBOX_REGISTER_MAPS[self.revision_number]

    def get_writeable_attribute(
        self, device_id: int, attribute_name: str, write_values: List[Any]
    ) -> PasdBusAttribute:
        """
        Return a PasdAttribute object for a writeable object.

        :raises PasdWriteError: If a non-existing or non-writeable register is requested

        :param device_id: The ID (address) of the smartbox / FNDH device
        :param attribute_name: name of the attribute
        :param write_values: the requested user values to write

        :return: A PasdAttribute object for this attribute
        """
        # Get the register map for the current revision number
        attribute_map = self._get_register_info(device_id).register_map
        attribute = attribute_map.get(attribute_name)
        if attribute is None or not attribute._writeable:
            raise PasdWriteError(attribute_name)
        attribute.value = attribute.convert_write_value(write_values)
        return attribute

    def get_attributes(
        self, device_id: int, attribute_names: list[str]
    ) -> dict[str, PasdBusAttribute]:
        """
        Map a list of attribute names to PasdAttribute objects.

        :raises PasdReadError: If non-contiguous set of registers requested

        :param device_id: the ID (address) of the smartbox / FNDH device
        :param attribute_names: name of the attribute(s)

        :return: A dictionary mapping attribute names to PasdAttributes,
            inserted in Modbus address order
        """
        # Get the register map for the current revision number
        attribute_map = self._get_register_info(device_id).register_map

        attributes = {
            name: attr
            for name, attr in self._INFO_REGISTER_MAP.items()
            if name in attribute_names
        }
        attributes.update(
            {
                name: attr
                for name, attr in attribute_map.items()
                if name in attribute_names
            }
        )
        # Check a contiguous set of registers has been requested
        last_attr = None
        for name, attr in attributes.items():
            if (
                not last_attr
                or last_attr.address + last_attr.count == attr.address
                or last_attr.address == attr.address
            ):
                last_attr = attr
                last_name = name
                continue
            raise PasdReadError(last_name, name)
        return attributes

    def get_attribute_names(self, device_id: int, addresses: list[int]) -> list[str]:
        """
        Map a list of register numbers to attribute names.

        :param device_id: The ID of the smartbox / FNDH device
        :param addresses: Starting address(es) of the desired Modbus registers

        :return: A list of the corresponding string attribute names
        """
        names = [self._INFO_REGISTER_INVERSE_MAP[address] for address in addresses]
        register_map = self._get_register_info(device_id).register_map
        names.extend(
            [
                name
                for name, attribute in register_map.items()
                if attribute.address in addresses
            ]
        )
        return names

    def get_attributes_from_address_and_count(
        self, device_id: int, first_address: int, count: int
    ) -> dict[str, PasdBusAttribute]:
        print(f"Getting attributes add {first_address} count {count}")
        attributes = {
            name: attribute
            for name, attribute in self._INFO_REGISTER_MAP.items()
            if first_address <= attribute.address < first_address + count
            or (attribute.address <= first_address and first_address + count <= attribute.address + attribute.count)
        }
        register_map = self._get_register_info(device_id).register_map
        attributes |= {
            name: attribute
            for name, attribute in register_map.items()
            if first_address <= attribute.address < first_address + count
            or (attribute.address <= first_address and first_address + count <= attribute.address + attribute.count)
        }
        print(f"Got {attributes}")
        return attributes

    def _create_led_pattern_command(
        self, device_id: int, arguments: Sequence[Any]
    ) -> Optional[PasdBusAttribute]:
        attribute_map = self._get_register_info(device_id).register_map

        attribute = PasdBusAttribute(attribute_map[self.LED_PATTERN].address, 1)
        try:
            # First argument is the pattern string for the service LED
            attribute.value = PasdServiceLEDPattern[arguments[0]].value
            return attribute
        except KeyError:
            logger.error(f"Unknown LED pattern {arguments[0]}")
            return None

    def _create_initialize_command(self, device_id: int) -> PasdBusAttribute:
        attribute_map = self._get_register_info(device_id).register_map
        attribute = PasdBusAttribute(attribute_map[self.STATUS].address, 1)
        attribute.value = 1  # Write any value to initialize the device
        return attribute

    def _create_port_command(
        self, device_id: int, command: PasdCommandStrings, arguments: Sequence[Any]
    ) -> Optional[PasdBusPortAttribute]:
        register_info = self._get_register_info(device_id)
        first_port_address = register_info.starting_port_register
        last_port_address = first_port_address + register_info.number_of_ports - 1

        # First argument is the port number
        if len(arguments) == 0:
            logger.error(f"Missing port argument for command: {command}")
            return None
        port_number = arguments[0]
        if (
            not isinstance(port_number, int)
            or not first_port_address
            <= (port_address := first_port_address + port_number - 1)
            <= last_port_address
        ):
            logger.error(f"Invalid port requested: {port_number}")
            return None

        attribute = PasdBusPortAttribute(port_address, 1)
        match command:
            case PasdCommandStrings.TURN_PORT_ON:
                if len(arguments) == 2 and isinstance(arguments[1], bool):
                    desired_on_offline = arguments[1]
                else:
                    desired_on_offline = True  # default case
                attribute._set_bitmap_value(True, desired_on_offline)
            case PasdCommandStrings.TURN_PORT_OFF:
                attribute._set_bitmap_value(False, False)
            case PasdCommandStrings.RESET_PORT_BREAKER:
                attribute._set_bitmap_value(None, None, True)
        return attribute

    def _create_reset_alarms_command(self, device_id: int) -> PasdBusAttribute:
        attribute_map = self._get_register_info(device_id).register_map

        attribute = PasdBusAttribute(attribute_map[self.ALARM_FLAGS].address, 1)
        attribute.value = 0
        return attribute

    def _create_reset_warnings_command(self, device_id: int) -> PasdBusAttribute:
        attribute_map = self._get_register_info(device_id).register_map

        attribute = PasdBusAttribute(attribute_map[self.WARNING_FLAGS].address, 1)
        attribute.value = 0
        return attribute

    def get_command(
        self, device_id: int, command_string: str, arguments: Sequence[Any]
    ) -> Optional[PasdBusAttribute]:
        """
        Get a PasdBusAttribute object for the specified command.

        :param device_id: Device (responder) id
        :param command_string: String command
        :param arguments: arguments (if any)

        :return: PasdBusAttribute object populated with converted value
            ready to send over Modbus or None if command is invalid
        """
        try:
            command = PasdCommandStrings(command_string)
        except ValueError:
            # No command matching the given string
            return None

        if command == PasdCommandStrings.SET_LED_PATTERN:
            attribute = self._create_led_pattern_command(device_id, arguments)
        elif command == PasdCommandStrings.INITIALIZE:
            attribute = self._create_initialize_command(device_id)
        elif command == PasdCommandStrings.RESET_ALARMS:
            attribute = self._create_reset_alarms_command(device_id)
        elif command == PasdCommandStrings.RESET_WARNINGS:
            attribute = self._create_reset_warnings_command(device_id)
        else:
            # All other commands relate to port control
            attribute = self._create_port_command(device_id, command, arguments)

        return attribute
