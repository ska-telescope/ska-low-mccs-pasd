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

from ska_low_mccs_pasd.pasd_bus.pasd_bus_register_map import (
    PasdBusRegisterMap,
    PasdBusAttribute,
    PasdBusRequestError,
)

FNDH_MODBUS_ADDRESS: Final = 101

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

class SimulatorInterfaceModbusClient:
    """A client class for a PaSD (simulator or h/w) with a Modbus API."""

    def __init__(
        self: SimulatorInterfaceModbusClient,
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
        modbus_address = (
            FNDH_MODBUS_ADDRESS if request["device_id"] == 0 else request["device_id"]
        )

        # Get a PasdBusAttribute object for this request
        try:
            attribute: PasdBusAttribute = self._register_map.get_attributes(
                request["device_id"], request["write"], list(request["values"])
            )[0]
            attribute.value = attribute.convert_write_value(list(request["values"]))
        except PasdBusRequestError as e:
            return self._create_write_error_response(
                "request", f"Exception for slave {modbus_address} write request: {e}"
            )

        return self._write_registers(modbus_address, attribute.address, attribute.value)

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
