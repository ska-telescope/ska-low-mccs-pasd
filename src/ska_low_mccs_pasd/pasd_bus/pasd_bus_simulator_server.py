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

from ska_ser_devices.client_server import (
    ApplicationServer,
    SentinelBytesMarshaller,
    TcpServer,
)

from .pasd_bus_json_api import PasdBusJsonApi
from .pasd_bus_simulator import PasdBusSimulator


# pylint: disable-next=too-few-public-methods
class PasdBusSimulatorJsonServer(ApplicationServer):
    """An application-layer server that provides JSON access to a PasdBusSimulator."""

    def __init__(self: PasdBusSimulatorJsonServer, simulator: PasdBusSimulator) -> None:
        """
        Initialise a new instance.

        :param simulator: the simulator backend to which this server
            provides access.
        """
        simulator_api = PasdBusJsonApi(simulator)
        marshaller = SentinelBytesMarshaller(b"\n")
        super().__init__(marshaller.unmarshall, marshaller.marshall, simulator_api)


def main() -> None:
    """Run the simulator server."""
    station_id = os.getenv("SIMULATOR_STATION", "1")
    host = os.getenv("SIMULATOR_HOST", gethostname())
    port = int(os.getenv("SIMULATOR_PORT", "502"))

    simulator = PasdBusSimulator(int(station_id), logging.DEBUG)
    simulator_server = PasdBusSimulatorJsonServer(simulator)
    server = TcpServer(host, port, simulator_server)
    with server:
        server.serve_forever()
