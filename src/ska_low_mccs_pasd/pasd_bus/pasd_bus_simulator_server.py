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
from typing import Sequence

from ska_ser_devices.client_server import (
    ApplicationServer,
    SentinelBytesMarshaller,
    TcpServer,
)

from ska_low_mccs_pasd.pasd_bus.pasd_bus_json_api import PasdBusJsonApi
from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import FndhSimulator, PasdBusSimulator, SmartboxSimulator


# pylint: disable-next=too-few-public-methods
class PasdBusSimulatorJsonServer(ApplicationServer):
    """An application-layer server that provides JSON access to a PasdBusSimulator."""

    def __init__(
        self: PasdBusSimulatorJsonServer,
        fndh_simulator: FndhSimulator,
        smartbox_simulators: Sequence[SmartboxSimulator],
    ) -> None:
        """
        Initialise a new instance.

        :param fndh_simulator: the FNDH simulator backend to which this
            server provides access.
        :param smartbox_simulators: the smartbox simulator backends to
            which this server provides access.
        """
        simulators: list[FndhSimulator | SmartboxSimulator] = [fndh_simulator]
        simulators.extend(smartbox_simulators)
        simulator_api = PasdBusJsonApi(simulators)
        marshaller = SentinelBytesMarshaller(b"\n")
        super().__init__(marshaller.unmarshall, marshaller.marshall, simulator_api)


def main() -> None:
    """Run the simulator server."""
    print("Starting daq server...", flush=True)
    logger = logging.getLogger()

    station_id = os.getenv("SIMULATOR_STATION", "1")
    host = os.getenv("SIMULATOR_HOST", "xyz.xyz.xyz.xyz")
    port = int(os.getenv("SIMULATOR_PORT", "50051"))

    simulator = PasdBusSimulator(int(station_id), logging.DEBUG)
    simulator_server = PasdBusSimulatorJsonServer(
        simulator.get_fndh(), simulator.get_smartboxes()
    )
    print(f"Starting daq server...port:{port}, host:{host}", flush=True)
    server = TcpServer(host, port, simulator_server, logger=logger)
    with server:
        server.serve_forever()

if __name__ == "__main__":
    main()
