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
from typing import Any, Sequence

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.factory import ServerDecoder
from pymodbus.framer.ascii_framer import ModbusAsciiFramer
from pymodbus.pdu import ExceptionResponse
from pymodbus.register_read_message import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
)

from .pasd_bus_custom_pymodbus import CustomReadHoldingRegistersResponse
from .pasd_bus_register_map import PasdBusRegisterMap
from .pasd_bus_simulator import FndhSimulator, SmartboxSimulator

logger = logging.getLogger()


# pylint: disable=too-few-public-methods
class PasdBusModbusApi:
    """A Modbus API for a PaSD bus simulator."""

    def __init__(self, simulators: Sequence[FndhSimulator | SmartboxSimulator]) -> None:
        """
        Initialise a new instance.

        :param simulators: sequence of simulators (fndh and smartbox)
            that this API fronts.

        """
        self._simulators = simulators
        self._framer = ModbusAsciiFramer(None)
        self._decoder = ModbusAsciiFramer(ServerDecoder(), client=None)
        self._slave_ids = list(range(len(simulators)))

    def _handle_read_attributes(self, device_id: int, names: list[str]) -> list[Any]:
        """
        Return list of attribute values.

        :param device_id: The slave ID
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
                pass
            values.append(value)
        return values

    def _handle_command(self, device_id: int, name: str, args: tuple) -> dict:
        # TODO
        raise NotImplementedError

    def _handle_no_match(self, request: dict) -> bytes:
        # TODO
        raise NotImplementedError

    def _handle_modbus(self, modbus_request_str: bytes) -> bytes:
        response = None

        def handle_request(message: Any) -> None:
            nonlocal response

            match message:
                case ReadHoldingRegistersRequest():
                    # TODO: Map register numbers from message.address and
                    # message.count to the corresponding attribute names
                    attr_names = ["outside_temperature"]
                    values = self._handle_read_attributes(message.slave_id, attr_names)
                    response = ReadHoldingRegistersResponse(
                        slave=message.slave_id,
                        address=message.address,
                        values=values,
                    )
                case _:
                    self._handle_no_match(message)

        self._decoder.processIncomingPacket(
            modbus_request_str, handle_request, slave=self._slave_ids
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
    """A client class for a PaSD bus simulator with a Modbus API."""

    def __init__(
        self: PasdBusModbusApiClient,
        ip_address: str,
        port: str,
        logging_level: int = logging.INFO,
    ) -> None:
        """
        Initialise a new instance.

        :param ip_address: the IP address for the PaSD
        :param port: the PaSD port
        :param logging_level: the logging level to use
        """
        logger.setLevel(logging_level)
        self._client = ModbusTcpClient(ip_address, port, ModbusAsciiFramer)
        # Register a custom response as a workaround to the firmware issue
        # (see JIRA ticket PRTS-255)
        self._client.register(CustomReadHoldingRegistersResponse)

    def _do_read_request(self, request: dict) -> dict:
        slave_id = request["device_id"]

        # Get a dictionary mapping the requested attribute names to
        # PasdAttributes
        attributes = PasdBusRegisterMap.get_attributes(slave_id, request["read"])

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
            f"MODBUS Request: slave {slave_id}, "
            f"start address {attributes[keys[0]].address}, count {count}"
        )

        reply = self._client.read_holding_registers(
            attributes[keys[0]].address, count, slave_id
        )

        match reply:
            case ReadHoldingRegistersResponse():
                results = {}
                register_index = 0
                for key in keys:
                    # Convert the raw register value(s) into meaningful
                    # data and add to the attributes dictionary to be returned
                    converted_values = attributes[key].convert_value(
                        reply.registers[
                            register_index : register_index + attributes[key].count
                        ]
                    )
                    results[key] = (
                        converted_values[0]
                        if len(converted_values) == 1
                        else converted_values
                    )
                    register_index += attributes[key].count
                response = {
                    "source": slave_id,
                    "data": {
                        "type": "reads",
                        "attributes": results,
                    },
                }
            case ModbusIOException():
                message = f"Modbus IO exception: {reply.message}"
                logger.error(message)
                response = {
                    "error": {
                        "code": "i/o",
                        "detail": message,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            case ExceptionResponse():
                message = f"Modbus exception response: {reply}"
                logger.error(message)
                response = {
                    "error": {
                        "code": "decode",
                        "detail": message,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            case _:
                message = f"Unexpected response type: {type(reply)}"
                logger.error(message)
                response = {
                    "error": {
                        "code": "decode",
                        "detail": message,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }

        return response

    def _do_write_request(self, request: dict) -> dict:
        # TODO
        raise NotImplementedError

    def read_attributes(self, device_id: int, *names: str) -> dict[str, Any]:
        """
        Read attribute values from the server.

        Note these must be stored in contiguous Modbus registers in the h/w.

        :param device_id: id of the device to be read from.
        :param names: names of the attributes to be read.

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
        assert response["data"]["source"] == device_id
        assert response["data"]["type"] == "command_result"
        return response["data"]["attributes"]
