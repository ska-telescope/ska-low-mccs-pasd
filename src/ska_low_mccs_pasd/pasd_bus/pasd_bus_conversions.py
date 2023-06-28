# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides scaling and other conversion functions for the PaSD."""

from typing import Any


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
        if nbytes != 2 * (nbytes // 2):
            raise ValueError(f"Odd number of bytes to convert: {value_list}")

        return sum(value_list[i] * (256 ** (nbytes - i - 1)) for i in range(nbytes))

    @classmethod
    def n_to_bytes(cls, value: int, nbytes: int = 2) -> list[int]:
        """
        Convert a value into a list of bytes.

        Given an integer value 'value' and a word length 'nbytes',
        convert 'value' into a list of integers from 0-255,  with MSB first
        and LSB last.

        :raises ValueError: If nbytes is not equal to 1, 2 or 4

        :param value: An integer small enough to fit into the given word length
        :param nbytes: The word length to return
        :return: a list of integers, each in the range 0-255
        """
        if nbytes == 1:
            assert 0 <= value < 256
            return [value]
        if nbytes == 2:
            assert 0 <= value < 65536
            return list(divmod(value, 256))
        if nbytes == 4:
            assert 0 <= value < 4294967296
            high_word, low_word = divmod(value, 65536)
            return list(divmod(high_word, 256)) + list(divmod(low_word, 256))
        raise ValueError(f"Received invalid number of bytes to convert: {nbytes}")

    # The following methods each accept and return a list of values, to simplify
    # the calling code

    @classmethod
    def default_conversion(cls, values: list[Any]) -> list[Any]:
        """
        Return the supplied raw value(s) with no conversion.

        :param values: raw value(s)
        :return: the value(s) unchanged
        """
        return values

    @classmethod
    def scale_5vs(
        cls, value_list: list[int | float], reverse: bool = False, pcb_version: int = 0
    ) -> list[int | float]:
        """
        Convert raw register value(s) to Volts.

        For now, raw values are hundredths of a volt, positive only.

        :param value_list: raw register contents as a list of values from 0-65535, or a
            list of voltages

        :param reverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :param pcb_version: integer PCB version number, 0-65535
        :return: output_values in Volts
        """
        if reverse:
            return [int(value * 100) & 0xFFFF for value in value_list]
        return [value / 100.0 for value in value_list]

    @classmethod
    def scale_48vs(
        cls, value_list: list[int | float], reverse: bool = False, pcb_version: int = 0
    ) -> list[int | float]:
        """
        Convert raw register value(s) to Volts.

        For now, raw values are hundredths of a volt, positive only.

        :param value_list: raw register contents as a list of  values from 0-65535, or a
            list of voltages

        :param reverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :param pcb_version: integer PCB version number, 0-65535
        :return: list of output_values in Volts
        """
        if reverse:
            return [int(value * 100) & 0xFFFF for value in value_list]
        return [value / 100.0 for value in value_list]

    @classmethod
    def scale_temps(
        cls, value_list: list[int | float], reverse: bool = False, pcb_version: int = 0
    ) -> list[int | float]:
        """
        Convert raw register value(s) to deg C.

        For now, raw values are hundredths of a deg C, as a
        signed 16-bit integer value

        :param value_list: raw register contents as a list of values from 0-65535, or
            floating point temperatures in degrees

        :param reverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :param pcb_version: integer PCB version number, 0-65535
        :return: value in deg C (if reverse=False), or raw value as an
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

        if reverse:
            return [deg_to_raw(value) for value in value_list]

        return [raw_to_deg(int(value)) for value in value_list]

    @classmethod
    def scale_48vcurrents(
        cls, value_list: list[int | float], reverse: bool = False, pcb_version: int = 0
    ) -> list[int | float]:
        """
        Convert raw register value(s) to Amps.

        For now, raw values are hundredths of an Amp, positive only.

        :param value_list: raw register contents as a list of values from 0-65535 or
            list of currents in amps

        :param reverse: Boolean, True to perform physical->raw conversion
            instead of raw->physical

        :param pcb_version: integer PCB version number, 0-65535
        :return: list of output_values
        """
        if reverse:
            return [int(value * 100) & 0xFFFF for value in value_list]
        return [value / 100.0 for value in value_list]

    @classmethod
    def convert_to_hex(cls, value_list: list[int], pcb_version: int = 0) -> list[str]:
        """
        Convert a number of raw register values to a hex string.

        :param value_list: list of raw register contents
        :param pcb_version: integer PCB version number, 0-65535
        :return: string ID
        """
        return [hex(cls.bytes_to_n(value_list))]

    @classmethod
    def convert_uptime(cls, value_list: list[int], pcb_version: int = 0) -> list[int]:
        """
        Convert the raw register values to an uptime in seconds.

        :param value_list: list of raw register contents
        :param pcb_version: integer PCB version number, 0-65535
        :return: integer number of seconds
        """
        return [cls.bytes_to_n(value_list)]
