# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a Modbus API to the PaSD bus."""
from __future__ import annotations

from typing import Any, Callable, Sequence

from pymodbus.factory import ClientDecoder, ServerDecoder
from pymodbus.framer.ascii_framer import ModbusAsciiFramer
from pymodbus.register_read_message import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
)

from .pasd_bus_simulator import FndhSimulator, SmartboxSimulator


# pylint: disable=too-few-public-methods
class PasdBusModbusApi:
    """A Modbus API for a PaSD bus simulator."""

    def __init__(
        self,
        simulators: Sequence[FndhSimulator | SmartboxSimulator],
    ) -> None:
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
                        slave=message.slave_id, address=message.address, values=values
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
        self: PasdBusModbusApiClient, transport: Callable[[bytes], bytes]
    ) -> None:
        """
        Initialise a new instance.

        :param transport: the transport layer client; a callable that
            accepts request bytes and returns response bytes.
        """
        self._transport = transport
        self._framer = ModbusAsciiFramer(None)
        self._decoder = ModbusAsciiFramer(ClientDecoder())

    def _do_read_request(self, request: dict) -> dict:
        attribute_names = request["read"]
        slave_id = request["device_id"]

        # TODO: Map requested attribute names to holding register numbers
        starting_register = 23
        message = ReadHoldingRegistersRequest(
            address=starting_register, slave=slave_id, count=1
        )
        request_bytes = self._framer.buildPacket(message)
        response_bytes = self._transport(request_bytes)
        response = {}

        def process_read_reply(reply: Any) -> None:
            nonlocal response
            match reply:
                case ReadHoldingRegistersResponse():
                    attributes_dict = {}
                    for attr, register in zip(attribute_names, reply.registers):
                        attributes_dict[attr] = register
                    response = {
                        "source": slave_id,
                        "data": {
                            "type": "reads",
                            "attributes": attributes_dict,
                        },
                    }
                case _:
                    # TODO
                    pass

        self._decoder.processIncomingPacket(
            response_bytes, process_read_reply, slave=slave_id
        )
        return response

    def _do_write_request(self, request: dict) -> dict:
        # TODO
        raise NotImplementedError

    def read_attributes(self, device_id: int, *names: str) -> dict[str, Any]:
        """
        Read attribute values from the server.

        :param device_id: id of the device to be read from.
        :param names: names of the attributes to be read.

        :return: dictionary of attribute values keyed by name
        """
        response = self._do_read_request({"device_id": device_id, "read": names})
        assert response["source"] == device_id
        assert response["data"]["type"] == "reads"
        return response["data"]["attributes"]

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
