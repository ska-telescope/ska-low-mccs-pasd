# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a Modbus API to the PaSD bus."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Final

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.factory import ServerDecoder
from pymodbus.framer.ascii_framer import ModbusAsciiFramer
from pymodbus.pdu import ExceptionResponse, ModbusExceptions
from pymodbus.register_read_message import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
)
from pymodbus.register_write_message import (
    WriteMultipleRegistersRequest,
    WriteMultipleRegistersResponse,
    WriteSingleRegisterRequest,
)

from ska_low_mccs_pasd.pasd_data import PasdData

from .pasd_bus_register_map import (
    PasdBusAttribute,
    PasdBusPortAttribute,
    PasdBusRegisterMap,
    PasdBusRequestError,
)

FNDH_MODBUS_ADDRESS: Final = 101
FNCC_MODBUS_ADDRESS: Final = 100

# Modbus Function/Exception Codes implemented in PaSD firmware
MODBUS_FUNCTIONS: Final = {
    ReadHoldingRegistersRequest.function_code: "Read register(s)",
    WriteSingleRegisterRequest.function_code: "Write single register",
    WriteMultipleRegistersRequest.function_code: "Write multiple registers",
}
MODBUS_EXCEPTIONS: Final = {
    ModbusExceptions.IllegalFunction: "Illegal function",
    ModbusExceptions.IllegalAddress: "Illegal data address",
    ModbusExceptions.GatewayNoResponse: "Gateway target device failed to respond",
}


# pylint: disable=too-few-public-methods
class PasdBusModbusApi:
    """A Modbus API for a PaSD bus simulator."""

    def __init__(self, simulators: dict, logger: logging.Logger) -> None:
        """
        Initialise a new instance.

        :param simulators: dictionary of simulators (FNDH, FNCC and smartbox)
            that this API fronts.
        :param logger: the logger to use

        """
        self._simulators = simulators
        self._framer = ModbusAsciiFramer(None)
        self._decoder = ModbusAsciiFramer(ServerDecoder(), client=None)
        self.responder_ids = list(range(len(simulators)))
        self._register_map = PasdBusRegisterMap()
        self._logger = logger

    # pylint: disable=too-many-return-statements
    def _convert_value(
        self, value: Any, attribute: PasdBusAttribute
    ) -> int | list[int]:
        if isinstance(attribute, PasdBusPortAttribute):
            return attribute.convert_write_value(value)
        if isinstance(value, list):
            try:
                return [(v + 65536) & 0xFFFF if v < 0 else v for v in value]
            except TypeError:
                return attribute.convert_write_value(value)
        if isinstance(value, int):
            if value < 0:
                value = (value + 65536) & 0xFFFF
            return [value]
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return attribute.convert_write_value([value])
        return attribute.convert_write_value([value])

    def _handle_read_attributes(
        self, device_id: int, names: dict[str, PasdBusAttribute]
    ) -> list[Any] | ExceptionResponse:
        """
        Return list of attribute values.

        :param device_id: The responder ID
        :param names: dict of string attribute names to read, with register counts

        :raises ValueError: if value read is invalid

        :return: List of attribute values
        """
        values: list[Any] = []
        last_address = -1
        last_count = -1
        for name, attr in names.items():
            try:
                unconverted_value = getattr(self._simulators[device_id], name)
            except KeyError:
                self._logger.error(f"Simulator {device_id} not available")
                return ExceptionResponse(
                    ReadHoldingRegistersRequest.function_code,
                    ModbusExceptions.GatewayNoResponse,
                    slave=device_id,
                )
            except AttributeError:
                self._logger.error(
                    f"No attribute exists at address {attr.address}: {name}"
                )
                return ExceptionResponse(
                    ReadHoldingRegistersRequest.function_code,
                    ModbusExceptions.IllegalAddress,
                    slave=device_id,
                )
            value = self._convert_value(unconverted_value, attr)
            if isinstance(value, list):
                if isinstance(value[0], list):
                    value = value[0]
                for index, char in enumerate(value):
                    if attr.address == last_address:
                        values[index - last_count] |= char
                    else:
                        values.append(int(char))
            else:
                raise ValueError(f"Expected a list from {value}")
            last_address = attr.address
            last_count = attr.count
        return values

    def _handle_write_attributes(
        self,
        device_id: int,
        names: dict[str, PasdBusAttribute],
        starting_address: int,
        values: list,
    ) -> ExceptionResponse | None:
        for name, attr in names.items():
            try:
                # This getattr call is to induce an AttributeError for a nonexistent
                # property in the simulator
                getattr(self._simulators[device_id], name)
                if attr.address < starting_address:
                    list_index = 0
                else:
                    list_index = attr.address - starting_address
                # Get values from list for current register in loop
                if attr.count == 1:
                    reg_vals = values[list_index]
                else:
                    reg_vals = values[list_index : list_index + attr.count]
                # Set (write) attributes in simulator
                if isinstance(attr, PasdBusPortAttribute):
                    converted_values = attr.convert_value(reg_vals)
                    start_port = starting_address - attr.address
                    for port_index, value in enumerate(converted_values):
                        reg_tuple = (value, start_port + port_index)
                        setattr(self._simulators[device_id], name, reg_tuple)
                else:
                    setattr(self._simulators[device_id], name, reg_vals)
            except KeyError:
                self._logger.error(f"Simulator {device_id} not available")
                return ExceptionResponse(
                    WriteMultipleRegistersRequest.function_code,
                    ModbusExceptions.GatewayNoResponse,
                    slave=device_id,
                )
            except AttributeError:
                self._logger.error(
                    f"No attribute exists at address {attr.address}: {name}"
                )
                return ExceptionResponse(
                    WriteMultipleRegistersRequest.function_code,
                    ModbusExceptions.IllegalAddress,
                    slave=device_id,
                )
        return None

    def _handle_no_match(self, message: Any) -> ExceptionResponse:
        self._logger.error(f"No match found for request {message}")
        return ExceptionResponse(
            message.function_code,
            ModbusExceptions.IllegalFunction,
            slave=message.slave_id,
        )

    def _get_device_id(self, modbus_address: int) -> int:
        if modbus_address == FNDH_MODBUS_ADDRESS:
            return PasdData.FNDH_DEVICE_ID
        if modbus_address == FNCC_MODBUS_ADDRESS:
            return PasdData.FNCC_DEVICE_ID
        # Smartbox Modbus addresses are the same as their device ids
        return modbus_address

    def _handle_modbus(self, modbus_request_str: bytes) -> bytes:
        response: (
            ReadHoldingRegistersResponse
            | WriteMultipleRegistersResponse
            | ExceptionResponse
            | None
        ) = None

        def handle_request(message: Any) -> None:
            nonlocal response
            device_id = self._get_device_id(message.slave_id)
            match message:
                case ReadHoldingRegistersRequest():
                    filtered_register_map = (
                        self._register_map.get_attributes_from_address_and_count(
                            device_id, message.address, message.count
                        )
                    )
                    if filtered_register_map == {}:
                        filtered_register_map = {
                            "Illegal address": PasdBusAttribute(
                                message.address, message.count
                            )
                        }
                    values = self._handle_read_attributes(
                        device_id, filtered_register_map
                    )
                    if isinstance(values, ExceptionResponse):
                        response = values
                    else:
                        response = ReadHoldingRegistersResponse(
                            slave=message.slave_id,
                            address=message.address,
                            values=values,
                        )
                case WriteMultipleRegistersRequest():
                    writable_port_attrs = [
                        "ports_desired_power_when_online",
                        "ports_desired_power_when_offline",
                        "port_breakers_tripped",
                    ]
                    filtered_register_map = {
                        k: v
                        for k, v in (
                            self._register_map.get_attributes_from_address_and_count(
                                device_id, message.address, message.count
                            ).items()
                        )
                        if k != "dummy_for_test"
                        and (
                            k in writable_port_attrs
                            or not isinstance(v, PasdBusPortAttribute)
                        )
                    }
                    if filtered_register_map == {}:
                        filtered_register_map = {
                            "Illegal address": PasdBusAttribute(
                                message.address, message.count
                            )
                        }
                    result = self._handle_write_attributes(
                        device_id,
                        filtered_register_map,
                        message.address,
                        message.values,
                    )
                    if result is not None:
                        response = result
                    else:
                        response = WriteMultipleRegistersResponse(
                            slave=message.slave_id,
                            address=message.address,
                            count=message.count,
                        )
                case _:
                    response = self._handle_no_match(message)

        self._decoder.processIncomingPacket(
            modbus_request_str, handle_request, slave=self.responder_ids
        )
        packet = self._framer.buildPacket(response)
        return packet

    def __call__(self, modbus_request_bytes: bytes) -> bytes:
        """
        Call this API object with a new Modbus request, encoded as bytes.

        :param modbus_request_bytes: the Modbus-encoded request string,
            encoded as bytes.

        :return: a Modbus-encoded response string, encoded as bytes.
        """
        return self._handle_modbus(modbus_request_bytes)


class PasdBusModbusApiClient:
    """A client class for a PaSD (simulator or h/w) with a Modbus API."""

    def __init__(
        self: PasdBusModbusApiClient,
        host: str,
        port: int,
        logger_object: logging.Logger,
        timeout: float,
    ) -> None:
        """
        Initialise a new instance.

        :param host: the host IP address for the PaSD
        :param port: the PaSD port
        :param logger_object: the logger to use
        :param timeout: the timeout period in seconds
        """
        self._client = ModbusTcpClient(host, port, ModbusAsciiFramer, timeout=timeout)
        logger_object.info(f"Created Modbus TCP client for address {host}, port {port}")
        self._logger = logger_object

        # Initialise a default register map
        self._register_map = PasdBusRegisterMap()

    def connect(self) -> None:
        """Establish a connection to the remote API."""
        self._client.connect()

    def close(self) -> None:
        """Close the connection to the remote API."""
        self._client.close()

    def _create_read_error_response(
        self, error_code: str, attributes: list[str], message: str
    ) -> dict:
        self._logger.error(message)
        # TODO: What error codes to use? Currently used is [request, read, write]
        return {
            "error": {
                "code": error_code,
                "detail": message,
            },
            "attributes": attributes,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _create_write_error_response(self, error_code: str, message: str) -> dict:
        self._logger.error(message)
        # TODO: What error codes to use? Currently used is [request, read, write]
        return {
            "error": {
                "code": error_code,
                "detail": message,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _get_modbus_address(self, device_id: int) -> int:
        if device_id == PasdData.FNDH_DEVICE_ID:
            return FNDH_MODBUS_ADDRESS
        if device_id == PasdData.FNCC_DEVICE_ID:
            return FNCC_MODBUS_ADDRESS
        # Smartbox Modbus addresses are the same as their device ids
        return device_id

    def _do_read_request(self, request: dict) -> dict:
        modbus_address = self._get_modbus_address(request["device_id"])

        # Get a dictionary mapping the requested attribute names to
        # PasdBusAttributes
        try:
            attributes = self._register_map.get_attributes(
                request["device_id"], request["read"]
            )
        except PasdBusRequestError as e:
            return self._create_read_error_response(
                "request",
                request["read"],
                f"Exception for slave {modbus_address} read request: {e}",
            )

        # Retrieve the list of keys (attribute names) in Modbus address order
        keys = list(attributes)

        # Calculate the number of registers to read
        count = (
            attributes[keys[-1]].address
            + attributes[keys[-1]].count
            - attributes[keys[0]].address
        )
        self._logger.debug(
            f"Modbus read request for slave {modbus_address}: "
            f"Register address {attributes[keys[0]].address}, count {count}"
        )

        reply = self._client.read_holding_registers(
            attributes[keys[0]].address, count, modbus_address
        )

        match reply:
            case ReadHoldingRegistersResponse():
                results = {}  # attributes dict to be returned
                register_index = 0  # current index into the register list
                last_attribute = None  # last handled attribute

                # Iterate through the requested attribute names, converting the raw
                # received register values into meaningful data and adding
                # to the attributes dictionary to be returned
                for key in keys:
                    current_attribute = attributes[key]

                    # Check if we're moving on from reading a set of port attribute data
                    # as we'll need to increment the register index
                    if isinstance(
                        last_attribute, PasdBusPortAttribute
                    ) and not isinstance(current_attribute, PasdBusPortAttribute):
                        register_index += last_attribute.count

                    converted_values = current_attribute.convert_value(
                        reply.registers[
                            register_index : register_index + current_attribute.count
                        ]
                    )
                    results[key] = (
                        converted_values[0]
                        if len(converted_values) == 1
                        else converted_values
                    )

                    # Check if we need to update the register map revision number
                    if key == self._register_map.MODBUS_REGISTER_MAP_REVISION:
                        self._register_map.revision_number = results[key]

                    # Only increment the register index if we are not
                    # parsing a port status attribute as there might be more to come
                    if not isinstance(current_attribute, PasdBusPortAttribute):
                        register_index += current_attribute.count
                    last_attribute = current_attribute
                response = {
                    "source": request["device_id"],
                    "data": {
                        "type": "reads",
                        "attributes": results,
                    },
                }
            case ModbusIOException():
                # No reply: pass this exception on up to the caller
                raise reply
            case ExceptionResponse():
                response = self._create_read_error_response(
                    "read",
                    request["read"],
                    f"Modbus exception for slave {reply.slave_id}: "
                    f"{MODBUS_EXCEPTIONS.get(reply.exception_code, 'UNKNOWN')}, "
                    f"Function: "
                    f"{MODBUS_FUNCTIONS.get(reply.original_code, 'UNKNOWN')}",
                )
            case _:
                response = self._create_read_error_response(
                    "read",
                    request["read"],
                    f"Unexpected response type for slave {modbus_address}: "
                    f"{type(reply)}",
                )

        return response

    def _write_registers(
        self, modbus_address: int, start_address: int, values: int | list[int]
    ) -> dict:
        self._logger.debug(
            f"Modbus write request for slave {modbus_address}: "
            f"Register address {start_address}, Values: {values}"
        )

        reply = self._client.write_registers(start_address, values, modbus_address)

        match reply:
            case WriteMultipleRegistersResponse():
                # A normal echo response has been received
                response = {
                    "source": modbus_address,
                    "data": {"type": "command_result", "result": True},
                }
            case ModbusIOException():
                # No reply: pass this exception on up to the caller
                raise reply
            case ExceptionResponse():
                response = self._create_write_error_response(
                    "write",
                    f"Modbus exception for slave {reply.slave_id}: "
                    f"{MODBUS_EXCEPTIONS.get(reply.exception_code, 'UNKNOWN')}, "
                    f"Function: "
                    f"{MODBUS_FUNCTIONS.get(reply.original_code, 'UNKNOWN')}",
                )
            case _:
                response = self._create_write_error_response(
                    "write",
                    f"Unexpected response type for slave {modbus_address}: "
                    f"{type(reply)}",
                )

        return response

    def _do_write_request(self, request: dict) -> dict:
        modbus_address = self._get_modbus_address(request["device_id"])

        # Get a PasdBusAttribute object for this request
        try:
            attribute = self._register_map.get_writeable_attribute(
                request["device_id"], request["write"], list(request["values"])
            )
        except PasdBusRequestError as e:
            return self._create_write_error_response(
                "request", f"Exception for slave {modbus_address} write request: {e}"
            )

        return self._write_registers(modbus_address, attribute.address, attribute.value)

    def _do_command_request(self, request: dict) -> dict:
        modbus_address = self._get_modbus_address(request["device_id"])

        # Get a PasdBusCommand object for this command
        try:
            command = self._register_map.get_command(
                request["device_id"], request["execute"], request["arguments"]
            )
        except PasdBusRequestError as e:
            return self._create_write_error_response(
                "request", f"Exception for slave {modbus_address} command request: {e}"
            )

        return self._write_registers(modbus_address, command.address, command.value)

    def read_attributes(self, device_id: int, *names: str) -> dict[str, Any]:
        """
        Read attribute values from the server.

        Note these must be stored in contiguous Modbus registers in the h/w.

        :param device_id: id of the device to be read from.
        :param names: names of the attributes to be read.

        :raises: ModbusIOException if the h/w failed to respond
        :return: dictionary of attribute values keyed by name
        """
        response = self._do_read_request({"device_id": device_id, "read": names})
        if "data" in response:
            return response["data"]["attributes"]
        return response

    def write_attribute(
        self, device_id: int, name: str, *values: Any
    ) -> dict[str, Any]:
        """
        Write a new attribute value.

        :param device_id: id of the device to write to.
        :param: name: attribute name to write.
        :param: values: new value(s).

        :return: dictionary mapping attribute name to new value.
        :raises: ModbusIOException if the h/w failed to respond.
        """
        response = self._do_write_request(
            {"device_id": device_id, "write": name, "values": values}
        )
        if "data" in response and response["data"]["result"] is True:
            response = {name: values}
        return response

    def execute_command(self, device_id: int, name: str, *args: Any) -> dict[str, Any]:
        """
        Execute a command and return the results.

        :param device_id: ID of the device to be commanded.
        :param name: name of the command.
        :param args: positional arguments to the command.

        :return: the results of the command execution.
        """
        response = self._do_command_request(
            {"device_id": device_id, "execute": name, "arguments": args}
        )
        if "data" in response:
            return response["data"]["result"]
        return response
