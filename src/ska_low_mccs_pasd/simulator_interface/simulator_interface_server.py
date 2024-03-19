# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides an entry point for a PaSD bus simulator TCP server."""
from __future__ import annotations

import logging
import os
from socket import gethostname
from typing import Iterator

from ska_ser_devices.client_server import (
    ApplicationServer,
    SentinelBytesMarshaller,
    TcpServer,
)

from .simulator_interface_modbus_client import SimulatorInterfaceModbusClient
from .simulator_interface_api import SimulatorInterfaceAPI



# pylint: disable-next=too-few-public-methods
class SimulatorInterfaceServer(ApplicationServer):
    """An application-layer server that provides Modbus access to a PasdBusSimulator."""

    def __init__(
        self: SimulatorInterfaceServer,
        simulator_host: str,
        simulator_port: int,
    ) -> None:
        """
        Initialise a new instance.

        :param pasd_hw_simulators: FNDH and Smartbox simulator backends to which this
            server provides access.
        """
        self.client = SimulatorInterfaceModbusClient(simulator_host, simulator_port, logging.getLogger(), timeout=10)
        simulator_api = SimulatorInterfaceAPI(self._handle_json)
        marshaller = SentinelBytesMarshaller(b"\n")
        super().__init__(marshaller.unmarshall, marshaller.marshall, simulator_api)

    def _handle_json(self: SimulatorInterfaceServer, json_request: dict) -> str:
        self.client.write_attribute(json_request["device_id"], json_request["name"], json_request["value"])
        return "Success"

def main() -> None:
    """
    Run the simulator server.

    :raises ValueError: if SIMULATOR_CONFIG_PATH is not set in the environment.
    """
    simulator_host = os.getenv("SIMULATOR_HOST")
    simulator_port = int(os.getenv("SIMULATOR_PORT", "502"))
    interface_host = os.getenv("INTERFACE_HOST", gethostname())
    interface_port = int(os.getenv("INTERFACE_PORT", "503"))

    if simulator_host is None:
        raise ValueError("SIMULATOR_CONFIG_PATH environment variable must be set.")

    interface_server = SimulatorInterfaceServer(simulator_host, simulator_port)
    server = TcpServer(interface_host, interface_port, interface_server)
    with server:
        server.serve_forever()
