# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides scaling and other conversion functions for the PaSD."""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger()


class FndhStatusMap(Enum):
    """Enum type for FNDH health status strings."""

    UNDEFINED = -1  # We should never receive an undefined status
    OK = 0  # Initialised, system health OK
    WARNING = 1  # Initialised, and at least one sensor in WARNING
    ALARM = 2  # Initialised, and at least one sensor in ALARM
    RECOVERY = 3  # Initialised, and at least one sensor in RECOVERY
    UNINITIALISED = 4  # NOT initialised, regardless of sensor states
    POWERUP = 5  # Local tech wants to turn off all ports,
    # then go through full powerup sequence


class SmartBoxStatusMap(Enum):
    """Enum type for SmartBox health status strings."""

    UNDEFINED = -1  # We should never receive an undefined status
    OK = 0  # Initialised, system health OK
    WARNING = 1  # Initialised, and at least one sensor in WARNING
    ALARM = 2  # Initialised, and at least one sensor in ALARM
    RECOVERY = 3  # Initialised, and at least one sensor in RECOVERY
    UNINITIALISED = 4  # NOT initialised, regardless of sensor states
    POWERDOWN = 5  # Local tech wants to turn off 48V to all ports in the station


class LEDServiceMap(Enum):
    """Enum type for the service LED (MSB in SYS_LIGHTS register)."""

    UNDEFINED = -1
    OFF = 0
    ON = 255


class LEDStatusMap(Enum):
    """Enum type for the status LED (LSB in SYS_LIGHTS_REGISTER)."""

    UNDEFINED = -1  # We should never receive an undefined status
    OFF = 0
    GREEN = 10  # always ON - used for 'OK and OFFLINE'
    GREENSLOW = 11  # 1.25 Hz strobe  - used for 'OK and ONLINE'
    GREENFAST = 12  # 2.5 Hz strobe
    GREENVFAST = 13  # 5 Hz strobe
    GREENDOTDASH = 14  # SOS in Morse code
    YELLOW = 20  # always ON  - used for 'WARNING and OFFLINE'
    YELLOWSLOW = 21  # 1.25 Hz strobe  - used for 'WARNING and ONLINE'
    YELLOWFAST = 22  # 2.5 Hz strobe  - used for 'UNINITIALISED'
    YELLOWVFAST = 23  # 5 Hz strobe
    YELLOWDOTDASH = 24  # SOS in Morse code
    RED = 30  # always ON
    REDSLOW = 31  # 1.25 Hz strobe
    REDFAST = 32  # 2.5 Hz strobe
    REDVFAST = 33  # 5 Hz strobe
    REDDOTDASH = 34  # SOS in Morse code
    YELLOWRED = 40  # Alternating yellow and red at 1.25 Hz
    YELLOWREDSLOW = 41  # red 0.5sec, 0.3 sec off, yellow 0.5 sec, 0.3 sec off pattern
    GREENRED = 50  # Alternating green and red at 1.25 Hz - used for 'POWERDOWN'


class PasdConversionUtility:
    """Conversion utility to provide scaling functions for PaSD registers."""

    @classmethod
    def bytes_to_n(cls, value_list: list[int]) -> int:
        """
        Convert a list of bytes to an integer.

        Given a list of integers in network order (MSB first),
        convert to an integer.

        :raises ValueError: If odd number of bytes given to convert

        :param value_list: A list of integers
        :return: The integer result
        """
        nbytes = len(value_list)
        if nbytes % 2:
            raise ValueError(f"Odd number of bytes to convert: {value_list}")

        return sum(
            value * (256 ** (nbytes - i - 1)) for i, value in enumerate(value_list)
        )

    @classmethod
    def n_to_bytes(cls, value: int, nbytes: int = 2) -> list[int]:
        """
        Convert a value into a list of bytes.

        Given an integer value 'value' and a word length 'nbytes',
        convert 'value' into a list of integers from 0-255,  with MSB first
        and LSB last.

        :raises ValueError: If nbytes is not equal to 1, 2 or 4
            or value not in range

        :param value: An integer small enough to fit into the given word length
        :param nbytes: The word length to return
        :return: a list of integers, each in the range 0-255
        """
        if nbytes == 1:
            if 0 <= value < 256:
                return [value]
        elif nbytes == 2:
            if 0 <= value < 65536:
                return list(divmod(value, 256))
        elif nbytes == 4:
            if 0 <= value < 4294967296:
                high_word, low_word = divmod(value, 65536)
                return list(divmod(high_word, 256)) + list(divmod(low_word, 256))
        else:
            raise ValueError(f"Invalid number of bytes to convert: {nbytes}")
        raise ValueError(f"Value out of range: {value}")

    # ##########################################################################
    # The following methods each accept and return a list of values to simplify
    # the calling code
    # ##########################################################################

    @classmethod
    def default_conversion(cls, values: list[Any]) -> list[Any]:
        """
        Return the supplied raw value(s) with no conversion.

        :param values: raw value(s)
        :return: the value(s) unchanged
        """
        return values

    @classmethod
    def scale_volts(
        cls, value_list: list[int | float], inverse: bool = False
    ) -> list[int | float]:
        """
        Convert raw register value(s) to Volts.

        For now, raw values are hundredths of a volt, positive only.

        :param value_list: raw register contents as a list of values from 0-65535, or a
            list of voltages

        :param inverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :return: output_values in Volts
        """
        if inverse:
            return [int(value * 100) & 0xFFFF for value in value_list]
        return [value / 100.0 for value in value_list]

    @classmethod
    def scale_temps(
        cls, value_list: list[int | float], inverse: bool = False
    ) -> list[int | float]:
        """
        Convert raw register value(s) to deg C.

        For now, raw values are hundredths of a deg C, as a
        signed 16-bit integer value

        :param value_list: raw register contents as a list of values from 0-65535, or
            floating point temperatures in degrees

        :param inverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :return: value in deg C (if inverse=False), or raw value as an
            unsigned 16 bit integer

        """

        def raw_to_deg(value: int) -> float:
            if value >= 32768:
                value -= 65536
            return value / 100.0

        def deg_to_raw(value: float) -> int:
            if value < 0:
                return (int(value * 100) + 65536) & 0xFFFF
            return int(value * 100) & 0xFFFF

        if inverse:
            return [deg_to_raw(value) for value in value_list]

        return [raw_to_deg(int(value)) for value in value_list]

    @classmethod
    def scale_48vcurrents(
        cls, value_list: list[int | float], inverse: bool = False
    ) -> list[int | float]:
        """
        Convert raw register value(s) to Amps.

        For now, raw values are hundredths of an Amp, positive only.

        :param value_list: raw register contents as a list of values from 0-65535 or
            list of currents in amps

        :param inverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :return: list of output_values
        """
        if inverse:
            return [int(value * 100) & 0xFFFF for value in value_list]
        return [value / 100.0 for value in value_list]

    @classmethod
    def convert_cpu_id(cls, value_list: list[int]) -> list[str]:
        """
        Convert a number of raw register values to a CPU ID.

        :param value_list: list of raw register contents
        :return: string ID
        """
        try:
            return [hex(cls.bytes_to_n(value_list))]
        except ValueError:
            logger.error(f"Invalid CPU ID value received: {value_list}")
            return []

    @classmethod
    def convert_uptime(cls, value_list: list[int]) -> list[int]:
        """
        Convert the raw register values to an uptime in seconds.

        :param value_list: list of raw register contents
        :return: integer number of seconds
        """
        try:
            return [cls.bytes_to_n(value_list)]
        except ValueError:
            logger.error(f"Invalid uptime value received: {value_list}")
            return []

    @classmethod
    def convert_chip_id(cls, value_list: list[int]) -> list[str]:
        """
        Convert the raw register values to a string chip id.

        :param value_list: list of raw register contents
        :return: string chip identification
        """
        bytelist = []
        try:
            for raw_value in value_list:
                bytelist += cls.n_to_bytes(raw_value)
            return ["".join([f"{v:02X}" for v in bytelist])]
        except ValueError:
            logger.error(f"Invalid chip ID value received: {value_list}")
            return []

    @classmethod
    def convert_fndh_status(cls, value_list: list[int]) -> list[str]:
        """
        Convert the raw register value to a string status.

        :param value_list: raw register contents
        :return: string status representation
        """
        try:
            return [FndhStatusMap(value_list[0]).name]
        except ValueError:
            logger.error(f"Invalid FNDH status value received: {value_list[0]}")
            return [FndhStatusMap.UNDEFINED.name]

    @classmethod
    def convert_smartbox_status(cls, value_list: list[int]) -> list[str]:
        """
        Convert the raw register value to a string status.

        :param value_list: raw register contents
        :return: string status representation
        """
        try:
            return [SmartBoxStatusMap(value_list[0]).name]
        except ValueError:
            logger.error(f"Invalid Smartbox status value received: {value_list[0]}")
            return [SmartBoxStatusMap.UNDEFINED.name]

    @classmethod
    def convert_led_status(cls, value_list: list[int]) -> dict:
        """
        Convert the raw register value to LED status strings.

        :param value_list: raw register contents
            (MSB represents service LED and LSB represents status LED)
        :return: dictionary with keys 'service' and 'status' mapping
            to members of LED_SERVICE_MAP and LED_STATUS_MAP respectively
        """
        raw_value = value_list[0]
        try:
            byte_list = cls.n_to_bytes(raw_value)
        except ValueError:
            logger.error(f"Invalid LED register value received: {raw_value}")
            return {
                "service": LEDServiceMap.UNDEFINED.name,
                "status": LEDStatusMap.UNDEFINED.name,
            }

        try:
            service = LEDServiceMap(byte_list[0]).name
        except ValueError:
            logger.error(f"Invalid service LED value received: {byte_list[0]}")
            service = LEDServiceMap.UNDEFINED.name

        try:
            status = LEDStatusMap(byte_list[1]).name
        except ValueError:
            logger.error(f"Invalid status LED value received: {byte_list[1]}")
            status = LEDStatusMap.UNDEFINED.name

        return {"service": service, "status": status}