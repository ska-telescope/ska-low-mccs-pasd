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
import math
from dataclasses import dataclass
from enum import Enum, IntEnum, IntFlag
from typing import Any, Callable, Final, Optional, Sequence

from ..pasd_controllers_configuration import PasdControllersConfig, RegisterDict
from .pasd_bus_conversions import LedServiceMap, PasdConversionUtility

logger = logging.getLogger()


class RequestErrors(Enum):
    """Type of PaSD bus request errors."""

    NonExistentAttribute = 1
    NonContiguousRegisters = 2
    NonWritableAttribute = 3
    NonExistentCommand = 4
    MissingCommandArgument = 5
    InvalidCommandArgument = 6


class PasdBusRequestError(Exception):
    """Exception to be raised for invalid PaSD bus requests."""

    def __init__(self: PasdBusRequestError, error: RequestErrors, *args: Any):
        """Initialize new instance.

        :param error: type of PaSD bus request error.
        :param args: attributes, command or other arguments in the request.
        """
        match error:
            case RequestErrors.NonExistentAttribute:
                message = f"No attributes matching {args} in register map"
            case RequestErrors.NonContiguousRegisters:
                message = f"Non-contiguous registers: {args[0]}, {args[1]}"
            case RequestErrors.NonWritableAttribute:
                message = f"Non-writable register(s): {args}"
            case RequestErrors.NonExistentCommand:
                message = f"No command matching '{args[0]}', argument(s): {args[1]}"
            case RequestErrors.MissingCommandArgument:
                message = f"Missing argument for command '{args[0]}': {args[1]}"
            case RequestErrors.InvalidCommandArgument:
                message = (
                    f"Invalid argument(s) for command '{args[0]}': "
                    f"{args[1]} = {args[2]}"
                )
        logger.error(message)
        super().__init__(message)


class PortStatusBits(IntFlag):
    """
    Enum type for PDOC/FEM port status bits.

    Corresponds to register bit names in PaSD firmware description document.
    """

    ENABLE = 0x8000
    ONLINE = 0x4000
    DSON = 0x3000
    DSOFF = 0x0C00
    TO = 0x0300
    PWRSENSE_BREAKER = 0x0080
    POWER = 0x0040
    NONE = 0x0


class PortDesiredStateOnline(IntEnum):
    """Port desired state when device is online."""

    OFF = 0x2000
    ON = 0x3000
    DEFAULT = 0x0000


class PortDesiredStateOffline(IntEnum):
    """Port desired state when device is offline."""

    OFF = 0x800
    ON = 0xC00
    DEFAULT = 0x0000


class DesiredPowerEnum(IntEnum):
    """
    Enum type for the DSON and DSOFF attributes.

    Note that DevEnum types must start at 0 and increment by 1.
    """

    DEFAULT = 0
    OFF = 1
    ON = 2
    INVALID = 3


class PortOverride(IntEnum):
    """Port override for field maintenance."""

    ALLOW_ON = 0x100
    FORCE_OFF = 0x200


class PasdCommandStrings(Enum):
    """Enum type for PaSD command strings."""

    TURN_PORT_ON = "turn_port_on"
    TURN_PORT_OFF = "turn_port_off"
    SET_PORT_POWERS = "set_port_powers"
    RESET_PORT_BREAKER = "reset_port_breaker"
    SET_LED_PATTERN = "set_led_pattern"
    SET_LOW_PASS_FILTER = "set_low_pass_filter"
    INITIALIZE = "initialize"
    RESET_STATUS = "reset_status"
    RESET_ALARMS = "reset_alarms"
    RESET_WARNINGS = "reset_warnings"


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
        writable: bool = False,
    ):
        """Initialise a new instance.

        :param address: starting register address
        :param count: number of registers containing the attribute
        :param conversion_function: callable function to scale the value
        :param writable: True if the attribute is read/write
        """
        self._address = address
        self._count = count
        self._conversion_function = conversion_function
        self._writable = writable

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
    def value(self: PasdBusAttribute) -> int | list[int]:
        """
        Return the value to be set for this attribute.

        :return: the desired value as a raw integer or list of ints.
        """
        return self._value

    @value.setter
    def value(self: PasdBusAttribute, value: int | list[int]) -> None:
        """
        Set a new value for this attribute.

        :param value: the desired new value(s) as raw integer(s)
        """
        self._value = value

    def convert_value(self: PasdBusAttribute, values: list[Any]) -> Any:
        """
        Execute the attribute's conversion function on the supplied value.

        Convert the raw register value(s) into a meaningful value

        :param values: a list of the raw value(s) to convert
        :return: the converted value
        """
        return self._conversion_function(values)

    def convert_write_value(self: PasdBusAttribute, values: list[Any]) -> Any:
        """
        Execute the attribute's conversion function on the supplied value.

        Convert the desired user value into a raw register value

        :param values: a list of the user values to convert
        :return: the raw converted values
        """
        return self._conversion_function(values, inverse=True)


class PasdBusPortAttribute(PasdBusAttribute):
    """Class representing the power status for one or more ports."""

    def __init__(
        self: PasdBusPortAttribute,
        address: int,
        count: int,
        desired_info: PortStatusBits = PortStatusBits.NONE,
    ):
        """Initialise a new instance.

        :param address: starting register address
        :param count: number of registers containing the port data
        :param desired_info: port status attribute of interest if
            reading status (must match member of PortStatusBits)
        """
        super().__init__(address, count, self._parse_port_bitmaps)
        self.desired_info = desired_info
        self.value = [0] * count

    # pylint: disable=too-many-branches
    def _parse_port_bitmaps(
        self: PasdBusPortAttribute,
        values: list[int | bool | str],
        inverse: bool = False,
    ) -> list[int] | list[int | str]:
        """
        Parse the port register bitmap data into the desired port information.

        :param values: list of raw port bitmaps (one per port)
        :param inverse: convert port information into bitmap instead
        :return: list of flags representing the desired port information
        """
        forcing_map = {
            True: "ON",
            False: "OFF",
            None: "NONE",
        }
        if inverse:
            inv_results: list[int] = []
            for value in values:
                bitmap: int = 0
                match self.desired_info:
                    case PortStatusBits.DSON:
                        if value == DesiredPowerEnum.ON:
                            bitmap = PortDesiredStateOnline.ON
                        elif value == DesiredPowerEnum.OFF:
                            bitmap = PortDesiredStateOnline.OFF
                    case PortStatusBits.DSOFF:
                        if value == DesiredPowerEnum.ON:
                            bitmap = PortDesiredStateOffline.ON
                        elif value == DesiredPowerEnum.OFF:
                            bitmap = PortDesiredStateOffline.OFF
                    case PortStatusBits.TO:
                        if value == forcing_map[True]:
                            bitmap = PortOverride.ALLOW_ON
                        elif value == forcing_map[False]:
                            bitmap = PortOverride.FORCE_OFF
                    case PortStatusBits.PWRSENSE_BREAKER | PortStatusBits.POWER:
                        if value:
                            bitmap = self.desired_info
                inv_results.append(bitmap)
            return inv_results
        results: list[int | str] = []
        for status_bitmap in values:
            status = int(status_bitmap) & self.desired_info
            match self.desired_info:
                case PortStatusBits.DSON:
                    try:
                        state = PortDesiredStateOnline(status).name
                    except ValueError:
                        state = DesiredPowerEnum.INVALID.name
                    results.append(DesiredPowerEnum[state])
                case PortStatusBits.DSOFF:
                    try:
                        state = PortDesiredStateOffline(status).name
                    except ValueError:
                        state = DesiredPowerEnum.INVALID.name
                    results.append(DesiredPowerEnum[state])
                case PortStatusBits.TO:
                    if status == PortOverride.FORCE_OFF:
                        results.append(forcing_map[False])
                    elif status == PortOverride.ALLOW_ON:
                        results.append(forcing_map[True])
                    else:
                        results.append(forcing_map[None])
                case PortStatusBits.PWRSENSE_BREAKER | PortStatusBits.POWER:
                    results.append(bool(status))
        return results

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def _set_bitmap_value(
        self: PasdBusPortAttribute,
        port_number_offset: int,
        desired_on_online: Optional[bool] = None,
        desired_on_offline: Optional[bool] = None,
        reset_breaker: bool = False,
        force_off: bool = False,
    ) -> None:
        value = 0
        if desired_on_online:
            value ^= PortDesiredStateOnline.ON
        elif desired_on_online is False:
            value ^= PortDesiredStateOnline.OFF
        if desired_on_offline:
            value ^= PortDesiredStateOffline.ON
        elif desired_on_offline is False:
            value ^= PortDesiredStateOffline.OFF
        if force_off:
            value ^= PortOverride.FORCE_OFF
        if reset_breaker:
            value ^= PortStatusBits.PWRSENSE_BREAKER
        assert isinstance(self.value, list)
        self.value[port_number_offset] = value


@dataclass
class PasdBusRegisterInfo:
    """Hold register information for a PaSD device."""

    register_map: dict[str, PasdBusAttribute | PasdBusPortAttribute]
    number_of_sensors: int = 0
    first_sensor_register: int = 0
    number_of_extra_sensors: int = 0
    first_extra_sensor_register: int = 0
    number_of_ports: int = 0
    starting_port_register: int = 0


class PasdBusRegisterMap:
    """A register mapping utility for the PaSD."""

    CONFIG_BASE: Final = PasdControllersConfig.get_all()
    CONFIG_REVISIONS: Final = PasdControllersConfig.get_register_map_revisions()
    FNCC_MODBUS_ADDRESS: Final = CONFIG_BASE["FNCC"]["modbus_address"]
    FNDH_MODBUS_ADDRESS: Final = CONFIG_BASE["FNPC"]["modbus_address"]
    FNCC_DEVICE_ID: Final = CONFIG_BASE["FNCC"]["pasd_number"]
    FNDH_DEVICE_ID: Final = CONFIG_BASE["FNPC"]["pasd_number"]
    MODBUS_REGISTER_MAP_REVISION: Final = "modbus_register_map_revision"
    LED_PATTERN: Final = "led_pattern"
    STATUS: Final = "status"
    ALARM_FLAGS: Final = "alarm_flags"
    WARNING_FLAGS: Final = "warning_flags"

    def __init__(self, revision_number: int = 1):
        """
        Initialize a new instance.

        :param revision_number: Modbus register map revision number,
            if known (this will be set later after interrogating
            the h/w)
        """
        self._revision_number = revision_number

        # Register maps for the attributes which might change across versions
        # NB: The attributes must be inserted in register number order
        self._FNCC_REGISTER_MAP_V1 = self._create_register_map(
            self.CONFIG_BASE["FNCC"]["registers"]
        )
        self._FNDH_REGISTER_MAP_V1 = self._create_register_map(
            self.CONFIG_BASE["FNPC"]["registers"]
        )
        self._FNDH_REGISTER_MAP_V1["dummy_for_test"] = PasdBusAttribute(
            1100, 4, writable=True
        )
        self._SMARTBOX_REGISTER_MAP_V1 = self._create_register_map(
            self.CONFIG_BASE["FNSC"]["registers"]
        )

        # Map modbus register revision number to the corresponding PasdRegisterInfo
        self._FNCC_REGISTER_MAPS: Final = {
            1: PasdBusRegisterInfo(self._FNCC_REGISTER_MAP_V1)
        }
        self._FNDH_REGISTER_MAPS: Final = {
            1: PasdBusRegisterInfo(
                self._FNDH_REGISTER_MAP_V1,
                number_of_sensors=8,
                first_sensor_register=16,
                number_of_extra_sensors=4,
                first_extra_sensor_register=26,
                number_of_ports=self.CONFIG_BASE["FNPC"]["number_of_ports"],
                starting_port_register=35,
            )
        }
        self._SMARTBOX_REGISTER_MAPS: Final = {
            1: PasdBusRegisterInfo(
                self._SMARTBOX_REGISTER_MAP_V1,
                number_of_sensors=5,
                first_sensor_register=16,
                number_of_extra_sensors=4,
                first_extra_sensor_register=23,
                number_of_ports=self.CONFIG_BASE["FNSC"]["number_of_ports"],
                starting_port_register=35,
            )
        }

        # TODO: This part is supposed to generate revision register maps if they exist,
        # but cannot be tested currently as the simulator and tests are not setup for
        # firmware revisions - So this is not guaranteed to be correct.
        if self.CONFIG_REVISIONS is not None and self._revision_number > 1:
            for revision in range(2, self._revision_number):
                for key, changes in self.CONFIG_REVISIONS[f"v{revision}"].items():
                    merged = self._merge_dicts(
                        self.CONFIG_BASE[key]["registers"], changes["registers"]
                    )
                    if key == "FNCC":
                        self._FNCC_REGISTER_MAPS[revision] = PasdBusRegisterInfo(
                            self._create_register_map(merged)
                        )
                    elif key == "FNPC":
                        self._FNDH_REGISTER_MAPS[revision] = PasdBusRegisterInfo(
                            self._create_register_map(merged),
                            number_of_sensors=8,
                            first_sensor_register=16,
                            number_of_extra_sensors=4,
                            first_extra_sensor_register=26,
                            number_of_ports=self.CONFIG_BASE["FNPC"]["number_of_ports"],
                            starting_port_register=35,
                        )
                    elif key == "FNSC":
                        self._FNDH_REGISTER_MAPS[revision] = PasdBusRegisterInfo(
                            self._create_register_map(merged),
                            number_of_sensors=5,
                            first_sensor_register=16,
                            number_of_extra_sensors=4,
                            first_extra_sensor_register=23,
                            number_of_ports=self.CONFIG_BASE["FNSC"]["number_of_ports"],
                            starting_port_register=35,
                        )

    @staticmethod
    def _create_register_map(
        registers: dict[str, RegisterDict]
    ) -> dict[str, PasdBusAttribute | PasdBusPortAttribute]:
        def _instantiate_attribute(
            class_name: str, *args: Any, **kwargs: Any
        ) -> PasdBusAttribute | PasdBusPortAttribute:
            cls = globals().get(class_name)
            if cls is None:
                raise ValueError(f"Class {class_name} not found.")
            return cls(*args, **kwargs)

        register_map = {}
        for key, register in registers.items():
            if register["modbus_class"] == "PasdBusAttribute":
                register_map[key] = _instantiate_attribute(
                    register["modbus_class"],
                    register["address"],
                    register["size"],
                    getattr(PasdConversionUtility, register["conversion_function"]),
                    register["writable"],
                )
            elif register["modbus_class"] == "PasdBusPortAttribute":
                register_map[key] = _instantiate_attribute(
                    register["modbus_class"],
                    register["address"],
                    register["size"],
                    getattr(
                        PortStatusBits,
                        register.get("desired_info", "NONE"),
                    ),
                )
        return register_map

    @classmethod
    def _merge_dicts(cls, base: dict, changes: dict) -> dict:
        result = base.copy()
        for key, value in changes.items():
            if isinstance(value, dict) and key in result:
                result[key] = cls._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result

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
        if device_id == self.FNDH_DEVICE_ID:
            return self._FNDH_REGISTER_MAPS[self.revision_number]
        if device_id == self.FNCC_DEVICE_ID:
            return self._FNCC_REGISTER_MAPS[self.revision_number]
        return self._SMARTBOX_REGISTER_MAPS[self.revision_number]

    def get_writable_attribute(
        self, device_id: int, attribute_name: str, write_values: list[Any]
    ) -> PasdBusAttribute:
        """
        Return a PasdAttribute object for a writable object.

        :raises PasdBusRequestError: If a non-existing or non-writable register is
            requested

        :param device_id: The ID (address) of the smartbox / FNDH device
        :param attribute_name: name of the attribute
        :param write_values: the requested user values to write

        :return: A PasdAttribute object for this attribute
        """
        # Get the register map for the current revision number
        attribute_map = self._get_register_info(device_id).register_map
        attribute = attribute_map.get(attribute_name)
        if attribute is None:
            raise PasdBusRequestError(
                RequestErrors.NonExistentAttribute, attribute_name
            )
        if attribute._writable is False:
            raise PasdBusRequestError(
                RequestErrors.NonWritableAttribute, attribute_name
            )
        attribute.value = attribute.convert_write_value(write_values)
        return attribute

    def get_attributes(
        self, device_id: int, attribute_names: list[str]
    ) -> dict[str, PasdBusAttribute]:
        """
        Map a list of attribute names to PasdAttribute objects.

        :raises PasdBusRequestError: If attributes do not match register map or
            non-contiguous set of registers requested

        :param device_id: the ID (address) of the smartbox / FNDH device
        :param attribute_names: name of the attribute(s)

        :return: A dictionary mapping attribute names to PasdAttributes,
            inserted in Modbus address order
        """
        # Get the register map for the current revision number
        attribute_map = self._get_register_info(device_id).register_map
        attributes = {
            name: attr
            for name, attr in attribute_map.items()
            if name in attribute_names
        }
        if len(attributes) == 0:
            raise PasdBusRequestError(
                RequestErrors.NonExistentAttribute, *attribute_names
            )

        # Check a contiguous set of registers has been requested
        last_attr = None
        last_name = None
        for name, attr in attributes.items():
            if (
                not last_attr
                or last_attr.address + last_attr.count == attr.address
                or last_attr.address == attr.address
            ):
                last_attr = attr
                last_name = name
                continue
            raise PasdBusRequestError(
                RequestErrors.NonContiguousRegisters, last_name, name
            )

        # Check all attribute names have been found in the map
        for name in attribute_names:
            if name not in attributes:
                logger.warning(f"Couldn't find {name} in attribute map")

        return attributes

    def get_attribute_names(self, device_id: int, addresses: list[int]) -> list[str]:
        """
        Map a list of register numbers to attribute names.

        :param device_id: The ID of the smartbox / FNDH device
        :param addresses: Starting address(es) of the desired Modbus registers

        :return: A list of the corresponding string attribute names
        """
        register_map = self._get_register_info(device_id).register_map
        return [
            name
            for name, attribute in register_map.items()
            if attribute.address in addresses
        ]

    def get_attributes_from_address_and_count(
        self, device_id: int, first_address: int, count: int
    ) -> dict[str, PasdBusAttribute]:
        """
        Map initial register address and count to attributes.

        :param device_id: The ID of the smartbox / FNDH device
        :param first_address: Starting address of the desired Modbus registers
        :param count: number of registers

        :return: A dictionary of the corresponding string attribute names and attribute
            instances
        """
        register_map = self._get_register_info(device_id).register_map
        attributes = {
            name: attribute
            for name, attribute in register_map.items()
            if first_address <= attribute.address < first_address + count
            or (
                attribute.address <= first_address
                and first_address + count <= attribute.address + attribute.count
            )
        }
        return attributes

    def _create_led_pattern_command(
        self, device_id: int, arguments: Sequence[Any]
    ) -> PasdBusAttribute:
        attribute_map = self._get_register_info(device_id).register_map

        attribute = PasdBusAttribute(attribute_map[self.LED_PATTERN].address, 1)
        try:
            # First argument is the pattern string for the service LED
            attribute.value = LedServiceMap[arguments[0]].value
            return attribute
        except KeyError as e:
            raise PasdBusRequestError(
                RequestErrors.InvalidCommandArgument,
                PasdCommandStrings.SET_LED_PATTERN.value,
                "service_pattern",
                arguments[0],
            ) from e

    def _create_initialize_command(self, device_id: int) -> PasdBusAttribute:
        attribute_map = self._get_register_info(device_id).register_map
        attribute = PasdBusAttribute(attribute_map[self.STATUS].address, 1)
        attribute.value = 1  # Write any value to initialize the device
        return attribute

    def _create_reset_status_command(self, device_id: int) -> PasdBusAttribute:
        attribute_map = self._get_register_info(device_id).register_map
        attribute = PasdBusAttribute(attribute_map[self.STATUS].address, 1)
        attribute.value = 1  # Write any value to reset the STATUS register
        return attribute

    def _create_port_powers_command(
        self, device_id: int, arguments: Sequence[Any]
    ) -> PasdBusAttribute:
        register_info = self._get_register_info(device_id)
        if len(arguments) > register_info.number_of_ports:
            raise PasdBusRequestError(
                RequestErrors.InvalidCommandArgument,
                PasdCommandStrings.SET_PORT_POWERS.value,
                "Too many ports' statuses",
                arguments,
            )

        attribute = PasdBusPortAttribute(
            register_info.starting_port_register, len(arguments)
        )
        for offset, desired_power_setting in enumerate(arguments):
            if desired_power_setting is None:
                attribute._set_bitmap_value(offset, None, None)
            else:
                dson = desired_power_setting[0]
                dsoff = desired_power_setting[1]
                if dson:
                    attribute._set_bitmap_value(offset, dson, dsoff)
                else:
                    # We are turning a port OFF, so set the DSOFF value
                    # also to OFF.
                    attribute._set_bitmap_value(offset, dson, False)
        return attribute

    def _create_single_port_command(
        self, device_id: int, command: PasdCommandStrings, arguments: Sequence[Any]
    ) -> PasdBusPortAttribute:
        register_info = self._get_register_info(device_id)
        first_port_address = register_info.starting_port_register
        last_port_address = first_port_address + register_info.number_of_ports - 1

        # First argument is the port number
        if len(arguments) == 0:
            raise PasdBusRequestError(
                RequestErrors.MissingCommandArgument, command.value, "port_number"
            )
        port_number = arguments[0]
        if (
            not isinstance(port_number, int)
            or not first_port_address
            <= (port_address := first_port_address + port_number - 1)
            <= last_port_address
        ):
            raise PasdBusRequestError(
                RequestErrors.InvalidCommandArgument,
                command.value,
                "port_number",
                port_number,
            )

        attribute = PasdBusPortAttribute(port_address, 1)
        match command:
            case PasdCommandStrings.TURN_PORT_ON:
                if len(arguments) == 2 and isinstance(arguments[1], bool):
                    desired_on_offline = arguments[1]
                else:
                    desired_on_offline = True  # default case
                attribute._set_bitmap_value(0, True, desired_on_offline)
            case PasdCommandStrings.TURN_PORT_OFF:
                attribute._set_bitmap_value(0, False, False)
            case PasdCommandStrings.RESET_PORT_BREAKER:
                attribute._set_bitmap_value(0, reset_breaker=True)
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

    def _create_low_pass_filter_command(
        self, device_id: int, arguments: Sequence[Any]
    ) -> PasdBusAttribute:
        if arguments[0]:  # Cut-off frequency
            filter_constant = self._calculate_filter_decay_constant(arguments[0])
            if filter_constant is None:
                raise PasdBusRequestError(
                    RequestErrors.InvalidCommandArgument,
                    PasdCommandStrings.SET_LOW_PASS_FILTER.value,
                    "cutoff",
                    arguments[0],
                )
        else:
            filter_constant = 0  # Disable filtering

        register_info = self._get_register_info(device_id)
        if arguments[1]:  # Write extra sensors' registers (block after LED status)
            attribute = PasdBusAttribute(
                register_info.first_extra_sensor_register,
                register_info.number_of_extra_sensors,
                writable=True,
            )
            attribute.value = [
                filter_constant for _ in range(register_info.number_of_extra_sensors)
            ]
        else:
            attribute = PasdBusAttribute(
                register_info.first_sensor_register,
                register_info.number_of_sensors,
                writable=True,
            )
            attribute.value = [
                filter_constant for _ in range(register_info.number_of_sensors)
            ]
        return attribute

    def get_command(
        self, device_id: int, command_string: str, arguments: Sequence[Any]
    ) -> PasdBusAttribute:
        """
        Get a PasdBusAttribute object for the specified command.

        :param device_id: Device (responder) id
        :param command_string: String command
        :param arguments: arguments (if any)

        :return: PasdBusAttribute object populated with converted value
            ready to send over Modbus

        :raises PasdBusRequestError: if the given string does not match any command
            or the arguments are invalid
        """
        try:
            command = PasdCommandStrings(command_string)
        except ValueError as e:
            raise PasdBusRequestError(
                RequestErrors.NonExistentCommand, command_string, arguments
            ) from e

        if command == PasdCommandStrings.SET_LED_PATTERN:
            attribute = self._create_led_pattern_command(device_id, arguments)
        elif command == PasdCommandStrings.SET_LOW_PASS_FILTER:
            attribute = self._create_low_pass_filter_command(device_id, arguments)
        elif command == PasdCommandStrings.INITIALIZE:
            attribute = self._create_initialize_command(device_id)
        elif command == PasdCommandStrings.RESET_STATUS:
            attribute = self._create_reset_status_command(device_id)
        elif command == PasdCommandStrings.RESET_ALARMS:
            attribute = self._create_reset_alarms_command(device_id)
        elif command == PasdCommandStrings.RESET_WARNINGS:
            attribute = self._create_reset_warnings_command(device_id)
        elif command == PasdCommandStrings.SET_PORT_POWERS:
            attribute = self._create_port_powers_command(device_id, arguments)
        else:
            # All other commands relate to individual port control
            attribute = self._create_single_port_command(device_id, command, arguments)

        return attribute

    def _calculate_filter_decay_constant(self, cutoff: float) -> int | None:
        """
        Calculate recursive filter decay constant to write to telemetry register.

        A digital low-pass single-pole recursive (IIR) filter is implemented in the PaSD
        firmware for all polling telemetry. Given a target cut-off frequency in Hz,
        return a custom unsigned 16-bit floating point format decay constant that can be
        written to a Smartbox or FNDH telemetry register to enable low-pass filtering
        with the approximated cut-off frequency.

        NOTE: This function was copied from Curtin's codebase. We cannot validate it
        independently from the original firmware author. The exponent/mantissa packing
        was chosen to represent a reasonable range of numbers that are sensible to use,
        with sufficient precision, and yield a result that fitted within a single
        16-bit modbus register.

        :param cutoff: Low-pass cut-off frequency in Hz.
        :return: 16-bit floating point decay constant to write to enable filtering,
            or None if given cutoff is invalid.
        """
        time_delta = 0.001  # internal sensor sampling interval in seconds
        if cutoff * time_delta > 1 or cutoff < 0.1:
            logger.error(
                f"Given cut-off frequency ({cutoff}Hz) is higher than sampling rate,"
                "or lower than 0.1Hz. Filter decay constant not set."
            )
            return None
        time_constant = 1 / (2 * math.pi * cutoff)
        alpha = time_delta / (time_constant + time_delta)  # decay constant
        # Convert to unsigned 5-bit exponent, 11-bit mantissa floating point format
        base = math.log(alpha) / math.log(2)
        right_shift = -int(base)  # exponent
        lower_range = 2 ** (-right_shift)
        upper_range = 2 ** (-right_shift - 1)
        mantissa_bits = 11
        mantissa_step = (lower_range - upper_range) / (2 ** (mantissa_bits - 1))
        mantissa = int((alpha - upper_range) / mantissa_step)
        ubinary16 = right_shift * (2**mantissa_bits) + mantissa
        return ubinary16
