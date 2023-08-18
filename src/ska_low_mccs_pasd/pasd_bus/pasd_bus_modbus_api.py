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
from typing import Any, Dict, Final
from unittest.mock import Mock

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.factory import ServerDecoder
from pymodbus.framer.ascii_framer import ModbusAsciiFramer
from pymodbus.pdu import ExceptionResponse
from pymodbus.register_read_message import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
)
from pymodbus.register_write_message import WriteSingleRegisterResponse

from .pasd_bus_register_map import (
    PasdBusPortAttribute,
    PasdBusRegisterMap,
    PasdReadError,
)
from .pasd_bus_simulator import FndhSimulator, SmartboxSimulator

logger = logging.getLogger()


# pylint: disable=too-few-public-methods
class PasdBusModbusApi:
    """A Modbus API for a PaSD bus simulator."""

    def __init__(
        self, simulators: Dict[int, FndhSimulator | SmartboxSimulator | Mock]
    ) -> None:
        """
        Initialise a new instance.

        :param simulators: sequence of simulators (fndh and smartbox)
            that this API fronts.

        """
        self._simulators = simulators
        self._framer = ModbusAsciiFramer(None)
        self._decoder = ModbusAsciiFramer(ServerDecoder(), client=None)
        self.responder_ids = list(range(len(simulators)))

    def _handle_read_attributes(self, device_id: int, names: list[str]) -> list[Any]:
        """
        Return list of attribute values.

        :param device_id: The responder ID
        :param names: List of string attribute names to read

        :return: List of attribute values
        """
        values = []
        for name in names:
            try:
                value = getattr(self._simulators[device_id], name)
                # TODO: Handle multi-register attributes
            except AttributeError:
                # TODO
                logger.error(f"Attribute not found: {name}")
            values.append(value)
        return values

    def _handle_command(self, device_id: int, name: str, args: tuple) -> dict:
        # TODO
        raise NotImplementedError

    def _handle_no_match(self, request: dict) -> bytes:
        # TODO
        raise NotImplementedError

    def _handle_modbus(self, modbus_request_str: bytes) -> bytes:
        # TODO (temporary placeholder code here only)
        response = None

        def handle_request(message: Any) -> None:
            nonlocal response

            match message:
                case ReadHoldingRegistersRequest():
                    # TODO: Map register numbers from message.address and
                    # message.count to the corresponding attribute names
                    attr_names = ["fncb_temperature"]
                    values = self._handle_read_attributes(message.slave_id, attr_names)
                    response = ReadHoldingRegistersResponse(
                        slave=message.slave_id,
                        address=message.address,
                        values=values,
                    )
                case _:
                    self._handle_no_match(message)

        self._decoder.processIncomingPacket(
            modbus_request_str, handle_request, slave=self.responder_ids
        )

        return self._framer.buildPacket(response)

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

    FNDH_ADDRESS: Final = 101

    def __init__(
        self: PasdBusModbusApiClient,
        host: str,
        port: int,
        logging_level: int = logging.INFO,
    ) -> None:
        """
        Initialise a new instance.

        :param host: the host IP address for the PaSD
        :param port: the PaSD port
        :param logging_level: the logging level to use
        """
        logger.setLevel(logging_level)
        self._client = ModbusTcpClient(host, port, ModbusAsciiFramer)
        logger.info(f"****Created Modbus TCP client for address {host}, port {port}")
        self._client.connect()

        # Initialise a default register map
        self._register_map = PasdBusRegisterMap()

    def _create_error_response(self, error_code: str, message: str) -> dict:
        logger.error(f"Returning error response: {message}")
        return {
            "error": {
                "code": error_code,
                "detail": message,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _do_read_request(self, request: dict) -> dict:
        modbus_address = (
            self.FNDH_ADDRESS if request["device_id"] == 0 else request["device_id"]
        )

        # Get a dictionary mapping the requested attribute names to
        # PasdBusAttributes
        try:
            attributes = self._register_map.get_attributes(
                request["device_id"], request["read"]
            )
        except PasdReadError as e:
            return self._create_error_response(
                "request", f"Exception: {e}"
            )  # TODO: What error code to use?

        if len(attributes) == 0:
            logger.warning(
                f"No attributes matching {request['read']} in PaSD register map"
            )
            return {"data": {"attributes": {}}}

        # Retrieve the list of keys (attribute names) in Modbus address order
        keys = list(attributes)

        # Calculate the number of registers to read
        count = (
            attributes[keys[-1]].address
            + attributes[keys[-1]].count
            - attributes[keys[0]].address
        )
        logger.debug(
            f"MODBUS read request: modbus address {modbus_address}, "
            f"start address {attributes[keys[0]].address}, count {count}"
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
                    if key == PasdBusRegisterMap.MODBUS_REGISTER_MAP_REVISION:
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
                response = self._create_error_response(
                    "read", f"Modbus exception response: {reply}"
                )  # TODO: what error code to use?
            case _:
                response = self._create_error_response(
                    "read", f"Unexpected response type: {type(reply)}"
                )  # TODO: what error code to use?

        return response

    def _do_write_request(self, request: dict) -> dict:
        modbus_address = (
            self.FNDH_ADDRESS if request["device_id"] == 0 else request["device_id"]
        )

        # Get a PasdBusCommand object for this command
        command = self._register_map.get_command(
            request["device_id"], request["execute"], request["arguments"]
        )

        if not command:
            return self._create_error_response(
                "request",
                f"Invalid command request: device: {request['device_id']}, "
                f"command: {request['execute']}, args: {request['arguments']}",
            )  # TODO: what error code to use?

        logger.debug(
            f"MODBUS write request: modbus address {modbus_address}, "
            f"register address {command.address}, value {command.value}"
        )

        reply = self._client.write_register(
            command.address, command.value, modbus_address
        )

        match reply:
            case WriteSingleRegisterResponse():
                # A normal echo response has been received
                response = {
                    "source": request["device_id"],
                    "data": {"type": "command_result", "result": True},
                }
            case ModbusIOException():
                # No reply: pass this exception on up to the caller
                raise reply
            case ExceptionResponse():
                response = self._create_error_response(
                    "write", f"Modbus exception response: {reply}"
                )  # TODO: what error code to use?
            case _:
                response = self._create_error_response(
                    "write", f"Unexpected response type: {type(reply)}"
                )  # TODO: what error code to use?

        return response

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

    def execute_command(self, device_id: int, name: str, *args: Any) -> Any:
        """
        Execute a command and return the results.

        :param device_id: ID of the device to be commanded.
        :param name: name of the command.
        :param args: positional arguments to the command.

        :return: the results of the command execution.
        """
        response = self._do_write_request(
            {"device_id": device_id, "execute": name, "arguments": args}
        )
        if "data" in response:
            return response["data"]["result"]
        return response
