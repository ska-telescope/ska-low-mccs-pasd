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
from typing import Dict

from ska_ser_devices.client_server import (
    ApplicationServer,
    SentinelBytesMarshaller,
    TcpServer,
)

from .pasd_bus_json_api import PasdBusJsonApi
from .pasd_bus_simulator import FndhSimulator, PasdBusSimulator, SmartboxSimulator


# pylint: disable-next=too-few-public-methods
class PasdBusSimulatorJsonServer(ApplicationServer):
    """An application-layer server that provides JSON access to a PasdBusSimulator."""

    def __init__(
        self: PasdBusSimulatorJsonServer,
        fndh_simulator: FndhSimulator,
        smartbox_simulators: Dict[int, SmartboxSimulator],
    ) -> None:
        """
        Initialise a new instance.

        :param fndh_simulator: the FNDH simulator backend to which this
            server provides access.
        :param smartbox_simulators: the smartbox simulator backends to
            which this server provides access.
        """
        simulators: Dict[int, FndhSimulator | SmartboxSimulator] = {0: fndh_simulator}
        simulators.update(smartbox_simulators)
        simulator_api = PasdBusJsonApi(simulators)
        marshaller = SentinelBytesMarshaller(b"\n")
        super().__init__(marshaller.unmarshall, marshaller.marshall, simulator_api)


def main() -> None:
    """
    Run the simulator server.

    :raises ValueError: if SIMULATOR_CONFIG_PATH is not set in the environment.
    """
    logger = logging.getLogger()

    station_id = os.getenv("SIMULATOR_STATION", "1")
    config_path = os.getenv("SIMULATOR_CONFIG_PATH")
    host = os.getenv("SIMULATOR_HOST", gethostname())
    port = int(os.getenv("SIMULATOR_PORT", "502"))

    if config_path is None:
        raise ValueError("SIMULATOR_CONFIG_PATH environment variable must be set.")

    simulator = PasdBusSimulator(config_path, int(station_id), logging.DEBUG)
    simulator_server = PasdBusSimulatorJsonServer(
        simulator.get_fndh(), simulator.get_smartboxes()
    )
    server = TcpServer(host, port, simulator_server, logger=logger)
    with server:
        server.serve_forever()
