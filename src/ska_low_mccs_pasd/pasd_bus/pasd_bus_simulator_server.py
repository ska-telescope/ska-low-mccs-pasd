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

from .pasd_bus_modbus_api import PasdBusModbusApi
from .pasd_bus_simulator import PasdBusSimulator, PasdHardwareSimulator


class CustomMarshaller(SentinelBytesMarshaller):
    r"""
    Custom marshaller that doesn't remove sentinel and only adds if not present.

    This is necessary as Modbus uses \r\n as a sentinel, but the sentinel needs to
        remain when pymodbus processes the packet.
    """

    def __init__(self, sentinel: bytes) -> None:
        """
        Create new instance.

        :param sentinel: the sentinel to indicate end of message
        """
        super().__init__(sentinel)

    def marshall(self, payload: bytes) -> bytes:
        """
        Marshall application-layer payload bytes into bytes to be transmitted.

        This class simply appends the sentinel character sequence if it isn't present.

        :param payload: the application-layer payload bytes.

        :return: the bytes to be transmitted.
        """
        if not payload.endswith(self._sentinel):
            payload += self._sentinel
        return payload

    def unmarshall(self, bytes_iterator: Iterator[bytes]) -> bytes:
        """
        Unmarshall transmitted bytes into application-layer payload bytes.

        This method is implemented to continually receive bytestrings
        until it receives a bytestring terminated by the sentinel.

        :param bytes_iterator: an iterator of bytestrings received
            by the server

        :return: the application-layer bytestring.
        """
        payload = b""
        more_bytes = next(bytes_iterator)
        payload = payload + more_bytes

        while not more_bytes.endswith(self._sentinel):
            more_bytes = next(bytes_iterator)
            payload = payload + more_bytes
        return payload


# pylint: disable-next=too-few-public-methods
class PasdBusSimulatorModbusServer(ApplicationServer):
    """An application-layer server that provides Modbus access to a PasdBusSimulator."""

    def __init__(
        self: PasdBusSimulatorModbusServer,
        pasd_hw_simulators: dict[int, PasdHardwareSimulator],
    ) -> None:
        """
        Initialise a new instance.

        :param pasd_hw_simulators: FNDH and Smartbox simulator backends to which this
            server provides access.
        """
        simulator_api = PasdBusModbusApi(pasd_hw_simulators, logging.getLogger())
        marshaller = CustomMarshaller(b"\r\n")
        super().__init__(marshaller.unmarshall, marshaller.marshall, simulator_api)


def main() -> None:
    """
    Run the simulator server.

    :raises ValueError: if SIMULATOR_CONFIG_PATH is not set in the environment.
    """
    station_label = os.getenv("SIMULATOR_STATION", "ci-1")
    config_path = os.getenv("SIMULATOR_CONFIG_PATH")
    host = os.getenv("SIMULATOR_HOST", gethostname())
    port = int(os.getenv("SIMULATOR_PORT", "502"))
    time_multiplier = int(os.getenv("SIMULATOR_TIME_MULTIPLIER", "1"))

    if config_path is None:
        raise ValueError("SIMULATOR_CONFIG_PATH environment variable must be set.")

    pasd_bus_simulator = PasdBusSimulator(
        config_path,
        station_label,
        logging.DEBUG,
        smartboxes_depend_on_attached_ports=True,
        time_multiplier=time_multiplier,
    )
    pasd_hw_simulators = pasd_bus_simulator.get_fndh_and_smartboxes()
    simulator_server = PasdBusSimulatorModbusServer(pasd_hw_simulators)
    server = TcpServer(host, port, simulator_server)
    with server:
        server.serve_forever()
