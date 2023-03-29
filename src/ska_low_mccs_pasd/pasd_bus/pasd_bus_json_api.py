# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a JSON API to the PaSD bus."""
from __future__ import annotations

import json
from typing import Any, Callable, Final, Optional

import jsonschema

from .pasd_bus_simulator import (
    AntennaInfoType,
    FndhInfoType,
    PasdBusSimulator,
    SmartboxInfoType,
)


# pylint: disable=too-few-public-methods
class PasdBusJsonApi:
    """A JSON-based API for a PaSD bus simulator."""

    SCHEMA: Final = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://skao.int/Pasd.json",
        "title": "PaSD bus simulator JSON API",
        "description": "Temporary JSON API for PaSD bus simulator",
        "type": "object",
        "oneOf": [
            {
                "properties": {
                    "read": {
                        "description": "Name of the attribute to read",
                        "type": "string",
                    }
                },
                "additionalProperties": False,
                "required": ["read"],
            },
            {
                "properties": {
                    "execute": {
                        "description": "Name of the command to execute",
                        "type": "string",
                    },
                    "arguments": {
                        "description": "Arguments to the command",
                        "type": "array",
                    },
                },
                "additionalProperties": False,
                "required": ["execute"],
            },
        ],
    }

    def __init__(self, simulator: PasdBusSimulator, encoding: str = "utf-8"):
        """
        Initialise a new instance.

        :param simulator: the PaSD bus simulator that this API acts upon.
        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self._simulator = simulator
        self._encoding = encoding

    def _handle_read_attribute(self, name: str) -> dict:
        try:
            value = getattr(self._simulator, name)
        except AttributeError:
            response = {
                "status": "error",
                "error": "attribute",
                "message": f"Attribute '{name}' does not exist",
            }
        else:
            response = {
                "attribute": name,
                "value": value,
            }
        return response

    def _handle_command(self, name: str, args: tuple) -> dict:
        try:
            command = getattr(self._simulator, name)
        except AttributeError:
            response = {
                "status": "error",
                "error": "attribute",
                "message": f"Command '{name}' does not exist",
            }
        else:
            try:
                result = command(*args)
            except Exception as error:  # pylint: disable=broad-exception-caught
                response = {
                    "status": "error",
                    "error": "command",
                    "message": f"Exception raised from command '{name}': {str(error)}.",
                }
            else:
                response = {
                    "command": name,
                    "result": result,
                }
        return response

    def _handle_no_match(self, json_request: str) -> dict:
        return {
            "status": "error",
            "error": "request",
            "message": f"No match for request '{json_request}'",
        }

    def _handle(self, json_request: str) -> str:
        try:
            request = json.loads(json_request)
        except json.JSONDecodeError as error:
            response = {
                "status": "error",
                "error": "decode",
                "message": error.msg,
            }
            return json.dumps(response)

        try:
            jsonschema.validate(request, self.SCHEMA)
        except jsonschema.ValidationError as error:
            response = {
                "status": "error",
                "error": "schema",
                "message": error.message,
            }
            return json.dumps(response)

        match request:
            case {"read": name}:
                response = self._handle_read_attribute(name)
            case {"execute": name, "arguments": [*args]}:
                response = self._handle_command(name, args)
            case _:
                # This will be unreachable if our schema is specific enough
                response = self._handle_no_match(json_request)
        return json.dumps(response)

    def __call__(self, json_request_bytes: bytes) -> bytes:
        """
        Call this API object with a new JSON request, encoded as bytes.

        :param json_request_bytes: the JSON-encoded request string,
            encoded as bytes.

        :return: a JSON-encoded response string, encoded as bytes.
        """
        json_request_str = json_request_bytes.decode(self._encoding)
        json_response_str = self._handle(json_request_str)
        return json_response_str.encode(self._encoding)


# pylint: disable=too-many-public-methods
class PasdBusJsonApiClient:
    """A client class for a PaSD bus simulator with a JSON API."""

    def __init__(
        self: PasdBusJsonApiClient,
        transport: Callable[[bytes], bytes],
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialise a new instance.

        :param transport: the transport layer client; a callable that
            accepts request bytes and returns response bytes.
        :param encoding: encoding to use for conversion between string
            and bytes.
        """
        self._transport = transport
        self._encoding = encoding

    def _do_request(self, request: dict) -> dict:
        request_str = json.dumps(request)
        request_bytes = request_str.encode(self._encoding)
        response_bytes = self._transport(request_bytes)
        response_str = response_bytes.decode(self._encoding)
        response = json.loads(response_str)
        return response

    def _read(self, name: str) -> Any:
        response = self._do_request({"read": name})
        assert response["attribute"] == name
        return response["value"]

    def _execute(self, name: str, *args: Any) -> Any:
        response = self._do_request({"execute": name, "arguments": args})
        assert response["command"] == name
        return response["result"]

    def reload_database(self: PasdBusJsonApiClient) -> bool:
        """
        Tell the PaSD to reload its configuration data.

        :return: whether successful
        """
        return self._execute("reload_database")

    def get_fndh_info(self: PasdBusJsonApiClient) -> FndhInfoType:
        """
        Return information about an FNDH controller.

        :return: a dictionary containing information about the FNDH
            controller.
        """
        return self._execute("get_fndh_info")

    @property
    def fndh_psu48v_voltages(
        self: PasdBusJsonApiClient,
    ) -> tuple[float, float]:
        """
        Return the output voltages on the two 48V DC power supplies, in volts.

        :return: the output voltages on the two 48V DC power supplies,
             in volts.
        """
        return self._read("fndh_psu48v_voltages")

    @property
    def fndh_psu5v_voltage(self: PasdBusJsonApiClient) -> float:
        """
        Return the output voltage on the 5V power supply, in volts.

        :return: the output voltage on the 5V power supply, in volts.
        """
        return self._read("fndh_psu5v_voltage")

    @property
    def fndh_psu48v_current(self: PasdBusJsonApiClient) -> float:
        """
        Return the total current on the 48V DC bus, in amperes.

        :return: the total current on the 48V DC bus, in amperes.
        """
        return self._read("fndh_psu48v_current")

    @property
    def fndh_psu48v_temperature(self: PasdBusJsonApiClient) -> float:
        """
        Return the common temperature for both 48V power supplies, in celcius.

        :return: the common temperature for both 48V power supplies, in celcius.
        """
        return self._read("fndh_psu48v_temperature")

    @property
    def fndh_psu5v_temperature(self: PasdBusJsonApiClient) -> float:
        """
        Return the temperature of the 5V power supply, in celcius.

        :return: the temperature of the 5V power supply, in celcius.
        """
        return self._read("fndh_psu5v_temperature")

    @property
    def fndh_pcb_temperature(self: PasdBusJsonApiClient) -> float:
        """
        Return the temperature of the FNDH's PCB, in celcius.

        :return: the temperature of the FNDH's PCB, in celcius.
        """
        return self._read("fndh_pcb_temperature")

    @property
    def fndh_outside_temperature(self: PasdBusJsonApiClient) -> float:
        """
        Return the temperature outside the FNDH, in celcius.

        :return: the temperature outside the FNDH, in celcius.
        """
        return self._read("fndh_outside_temperature")

    @property
    def fndh_status(self: PasdBusJsonApiClient) -> str:
        """
        Return the status of the FNDH.

        :return: the status of the FNDH
        """
        return self._read("fndh_status")

    @property
    def fndh_service_led_on(self: PasdBusJsonApiClient) -> bool:
        """
        Whether the FNDH's blue service indicator LED is on.

        :return: whether the FNDH's blue service indicator LED is on.
        """
        return self._read("fndh_service_led_on")

    def set_fndh_service_led_on(
        self: PasdBusJsonApiClient,
        led_on: bool,
    ) -> Optional[bool]:
        """
        Turn on/off the FNDH's blue service indicator LED.

        :param led_on: whether the LED should be on.

        :returns: whether successful, or None if there was nothing to do.
        """
        return self._execute("set_fndh_service_led_on", led_on)

    @property
    def fndh_ports_power_sensed(self: PasdBusJsonApiClient) -> list[bool]:
        """
        Return the actual sensed power state of each FNDH port.

        :return: the actual sensed power state of each FNDH port.
        """
        return self._read("fndh_ports_power_sensed")

    def is_fndh_port_power_sensed(
        self: PasdBusJsonApiClient,
        port_number: int,
    ) -> bool:
        """
        Return whether power is sensed on a specified FNDH port.

        :param port_number: number of the FNDH port for which to check
            if power is sensed.

        :return: whether power is sensed on the port
        """
        return self._execute("is_fndh_port_power_sensed", port_number)

    @property
    def fndh_ports_connected(self: PasdBusJsonApiClient) -> list[bool]:
        """
        Return whether there is a smartbox connected to each FNDH port.

        :return: whether there is a smartbox connected to each FNDH
            port.
        """
        return self._read("fndh_ports_connected")

    @property
    def fndh_port_forcings(self: PasdBusJsonApiClient) -> list[Optional[bool]]:
        """
        Return whether each FNDH port has had its power locally forced.

        :return: a list of values, one for each port. True means the
            port has been locally forced on. False means the port has
            been locally forced off. None means the port has not been
            locally forced.
        """
        return self._read("fndh_port_forcings")

    def get_fndh_port_forcing(
        self: PasdBusJsonApiClient, port_number: int
    ) -> Optional[bool]:
        """
        Return the forcing status of a specified FNDH port.

        :param port_number: number of the FNDH port for which the
            forcing status is sought

        :return: the forcing status of a specified FNDH port. True means
            the port has been locally forced on. False means the port
            has been locally forced off. None means the port has not
            been locally forced.
        """
        return self._execute("get_fndh_port_forcing", port_number)

    @property
    def fndh_ports_desired_power_online(
        self: PasdBusJsonApiClient,
    ) -> list[bool]:
        """
        Return whether each FNDH port is desired to be powered when controlled by MCCS.

        :return: whether each FNDH port is desired to be powered when
            controlled by MCCS
        """
        return self._read("fndh_ports_desired_power_online")

    @property
    def fndh_ports_desired_power_offline(
        self: PasdBusJsonApiClient,
    ) -> list[bool]:
        """
        Return whether each FNDH port should be powered when MCCS control has been lost.

        :return: whether each FNDH port is desired to be powered when
            MCCS control has been lost
        """
        return self._read("fndh_ports_desired_power_offline")

    def get_smartbox_info(
        self: PasdBusJsonApiClient, smartbox_id: int
    ) -> SmartboxInfoType:
        """
        Return information about a smartbox.

        :param smartbox_id: the smartbox number

        :return: a dictionary containing information about the smartbox.
        """
        return self._execute("get_smartbox_info", smartbox_id)

    def turn_smartbox_on(
        self: PasdBusJsonApiClient,
        smartbox_id: int,
        desired_on_if_offline: bool = True,
    ) -> Optional[bool]:
        """
        Turn on a smartbox.

        :param smartbox_id: the (one-based) number of the smartbox to be
            turned on.
        :param desired_on_if_offline: whether the smartbox should stay
            on if the control system goes offline.

        :return: Whether successful, or None if there was nothing to do
        """
        return self._execute("turn_smartbox_on", smartbox_id, desired_on_if_offline)

    def turn_smartbox_off(
        self: PasdBusJsonApiClient, smartbox_id: int
    ) -> Optional[bool]:
        """
        Turn off a smartbox.

        :param smartbox_id: the (one-based) number of the smartbox to be
            turned off.

        :return: Whether successful, or None if there was nothing to do
        """
        return self._execute("turn_smartbox_off", smartbox_id)

    def is_smartbox_port_power_sensed(
        self: PasdBusJsonApiClient,
        smartbox_id: int,
        smartbox_port_number: int,
    ) -> bool:
        """
        Return whether power is sensed at a given smartbox port.

        :param smartbox_id: id of the smartbox to check
        :param smartbox_port_number: number of the port to check

        :return: whether power is sensed that the specified port.
        """
        return self._execute(
            "is_smartbox_port_power_sensed", smartbox_id, smartbox_port_number
        )

    @property
    def smartbox_input_voltages(self: PasdBusJsonApiClient) -> list[float]:
        """
        Return each smartbox's power input voltage, in volts.

        :return: a list of voltages.
        """
        return self._read("smartbox_input_voltages")

    @property
    def smartbox_power_supply_output_voltages(
        self: PasdBusJsonApiClient,
    ) -> list[float]:
        """
        Return each smartbox's power supply output voltage, in volts.

        :return: a list of voltages.
        """
        return self._read("smartbox_power_supply_output_voltages")

    @property
    def smartbox_statuses(self: PasdBusJsonApiClient) -> list[str]:
        """
        Return the status of each smartbox.

        :return: a list of string statuses.
        """
        return self._read("smartbox_statuses")

    @property
    def smartbox_power_supply_temperatures(
        self: PasdBusJsonApiClient,
    ) -> list[float]:
        """
        Return each smartbox's power supply temperature, in celcius.

        :return: a list of temperatures.
        """
        return self._read("smartbox_power_supply_temperatures")

    @property
    def smartbox_outside_temperatures(
        self: PasdBusJsonApiClient,
    ) -> list[float]:
        """
        Return each smartbox's outside temperature, in celcius.

        :return: a list of temperatures.
        """
        return self._read("smartbox_outside_temperatures")

    @property
    def smartbox_pcb_temperatures(self: PasdBusJsonApiClient) -> list[float]:
        """
        Return each smartbox's PCB temperature, in celcius.

        :return: a list of temperatures.
        """
        return self._read("smartbox_pcb_temperatures")

    @property
    def smartbox_service_leds_on(self: PasdBusJsonApiClient) -> list[bool]:
        """
        Whether each smartbox's blue service indicator LED is on.

        :return: whether each smartbox's blue service indicator LED is
            on.
        """
        return self._read("smartbox_service_leds_on")

    def set_smartbox_service_led_on(
        self: PasdBusJsonApiClient,
        smartbox_id: int,
        led_on: bool,
    ) -> Optional[bool]:
        """
        Turn on the blue service indicator LED for a smartbox.

        :param smartbox_id: the smartbox to have its LED switched
        :param led_on: whether the LED should be on.

        :return: whether successful, or None if there was nothing to do
        """
        return self._execute("set_smartbox_service_led_on", smartbox_id, led_on)

    @property
    def smartbox_fndh_ports(self: PasdBusJsonApiClient) -> list[int]:
        """
        Return the physical port in the FNDH into which each smartbox is plugged.

        :return: the physical port in the FNDH into which each smartbox
            is plugged.
        """
        return self._read("smartbox_fndh_ports")

    @property
    def smartboxes_desired_power_online(
        self: PasdBusJsonApiClient,
    ) -> list[bool]:
        """
        Return whether each smartbox should be on when the PaSD is under MCCS control.

        :return: whether each smartbox should be on when the PaSD is
            under MCCS control.
        """
        return self._read("smartboxes_desired_power_online")

    @property
    def smartboxes_desired_power_offline(
        self: PasdBusJsonApiClient,
    ) -> list[bool]:
        """
        Return whether each smartbox should be on when MCCS control of the PaSD is lost.

        :return: whether each smartbox should be on when MCCS control of
            the PaSD is lost.
        """
        return self._read("smartboxes_desired_power_offline")

    def get_smartbox_ports_power_sensed(
        self: PasdBusJsonApiClient, smartbox_id: int
    ) -> list[bool]:
        """
        Return whether power is sensed at each port of a smartbox.

        :param smartbox_id: id of the smartbox for which we want to know
            if power is sensed.

        :return: whether each smartbox should be on when MCCS control of
            the PaSD is lost.
        """
        return self._execute("get_smartbox_ports_power_sensed", smartbox_id)

    def get_antenna_info(
        self: PasdBusJsonApiClient, antenna_id: int
    ) -> AntennaInfoType:
        """
        Return information about relationship of an antenna to other PaSD components.

        :param antenna_id: the antenna number

        :return: a dictionary containing the antenna's smartbox number,
            port number, TPM number and TPM input number.
        """
        return self._execute("get_antenna_info", antenna_id)

    @property
    def antennas_online(self: PasdBusJsonApiClient) -> list[bool]:
        """
        Return whether each antenna is online.

        :return: a list of booleans indicating whether each antenna is
            online.
        """
        return self._read("antennas_online")

    @property
    def antenna_forcings(self: PasdBusJsonApiClient) -> list[Optional[bool]]:
        """
        Return whether each antenna has had its status forced locally.

        :return: a list of booleans indicating the forcing status of
            each antenna. True means the antenna has been locally forced
            on. False means the antenna has been locally forced off.
            None means the antenna has not been locally forced.
        """
        return self._read("antenna_forcings")

    def get_antenna_forcing(
        self: PasdBusJsonApiClient, antenna_id: int
    ) -> Optional[bool]:
        """
        Return the forcing status of a specified antenna.

        :param antenna_id: the id of the antenna for which the forcing
            status is required.

        :return: the forcing status of the antenna. True means the
            antenna is forced on. False means it is forced off. None
            means it is not forced.
        """
        return self._execute("get_antenna_forcing", antenna_id)

    def reset_antenna_breaker(
        self: PasdBusJsonApiClient, antenna_id: int
    ) -> Optional[bool]:
        """
        Reset a tripped antenna breaker.

        :param antenna_id: the (one-based) number of the antenna for
            which a breaker trip is to be reset.

        :return: Whether successful, or None if there was nothing to do
        """
        return self._execute("reset_antenna_breaker", antenna_id)

    @property
    def antennas_tripped(self: PasdBusJsonApiClient) -> list[bool]:
        """
        Return whether each antenna has had its breaker tripped.

        :return: a list of booleans indicating whether each antenna has
            had its breaker tripped.
        """
        return self._read("antennas_tripped")

    def turn_antenna_on(
        self: PasdBusJsonApiClient,
        antenna_id: int,
        desired_on_if_offline: bool = True,
    ) -> Optional[bool]:
        """
        Turn on an antenna.

        :param antenna_id: the (one-based) number of the antenna to
            be turned on.
        :param desired_on_if_offline: whether the antenna should remain
            on if the control system goes offline.

        :return: Whether successful, or None if there was nothing to do
        """
        return self._execute("turn_antenna_on", antenna_id, desired_on_if_offline)

    def turn_antenna_off(self: PasdBusJsonApiClient, antenna_id: int) -> Optional[bool]:
        """
        Turn off an antenna.

        :param antenna_id: the (one-based) number of the antenna to
            be turned off.

        :return: Whether successful, or None if there was nothing to do
        """
        return self._execute("turn_antenna_off", antenna_id)

    @property
    def antennas_power_sensed(self: PasdBusJsonApiClient) -> list[bool]:
        """
        Return whether each antenna is currently powered on.

        :return: a list of booleans indicating whether each antenna is
            powered on.
        """
        return self._read("antennas_power_sensed")

    @property
    def antennas_desired_power_online(
        self: PasdBusJsonApiClient,
    ) -> list[bool]:
        """
        Return the desired power state of each antenna when it is online.

        :return: the desired power state of each antenna when it is
            online.
        """
        return self._read("antennas_desired_power_online")

    @property
    def antennas_desired_power_offline(
        self: PasdBusJsonApiClient,
    ) -> list[bool]:
        """
        Return the desired power state of each antenna when it is offline.

        :return: the desired power state of each antenna when it is
            offline.
        """
        return self._read("antennas_desired_power_offline")

    @property
    def antenna_currents(self: PasdBusJsonApiClient) -> list[float]:
        """
        Return the current at each antenna's power port, in amps.

        :return: a list of currents.
        """
        return self._read("antenna_currents")

    def update_status(
        self: PasdBusJsonApiClient,
    ) -> None:
        """
        Update the status of devices accessible through this bus.

        At present this does nothing except update a timestamp.
        """
        self._execute("update_status")
