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
from typing import Any, Optional

from ska_ser_devices.client_server import (
    ApplicationServer,
    SentinelBytesMarshaller,
    TcpServer,
)

from .field_station_configmap_interface import FieldStationConfigurationInterface


# pylint: disable-next=too-few-public-methods
class FieldStationConfigurationJsonServer(ApplicationServer):
    """An application-layer server that provides JSON access to a ConfigMap."""

    def __init__(
        self: FieldStationConfigurationJsonServer,
        station_name: str,
        namespace: str,
        _config_manager: Optional[Any] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param station_name: the name of the station used to locate configMap
            resource
        :param namespace: the namespace of the configMap for configuration.
        :param _config_manager: configuration manager for testing.
        """
        store = FieldStationConfigurationInterface(
            station_name, namespace, _config_manager
        )
        marshaller = SentinelBytesMarshaller(b"\n")
        super().__init__(marshaller.unmarshall, marshaller.marshall, store)


def main() -> None:
    """
    Run a server to allow the FieldStation connection to a configmap server.

    :raises ValueError: if STATION_NAME or NAMESPACE is not set in the environment.
    """
    logger = logging.getLogger()

    station_name = os.getenv("STATION_NAME")
    namespace = os.getenv("NAMESPACE")

    if namespace is None:
        raise ValueError("NAMESPACE environment variable must be set.")
    if station_name is None:
        raise ValueError("STATION_NAME environment variable must be set.")

    host = os.getenv("SIMULATOR_HOST", gethostname())
    port = int(os.getenv("SIMULATOR_PORT", "8081"))

    simulator_server = FieldStationConfigurationJsonServer(station_name, namespace)
    server = TcpServer(host, port, simulator_server, logger=logger)
    with server:
        server.serve_forever()
