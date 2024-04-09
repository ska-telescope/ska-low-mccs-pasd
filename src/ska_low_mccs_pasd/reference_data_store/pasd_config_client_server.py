# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a PaSD configuration client and server."""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import urllib.request
from types import TracebackType
from typing import Any, Literal, Optional, Type

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request

from .pasd_config_service import PasdConfigurationService

CONFIG_HTTP_PATH = "/api/v1/config/{station}"


class PasdConfigurationClient:  # pylint: disable=too-few-public-methods
    """A client for retrieving PaSD configuration."""

    def __init__(
        self: PasdConfigurationClient,
        host: str,
        port: int,
        station: str,
    ):
        """
        Initialise a new client instance.

        :param host: hostname of the HTTP server
        :param port: port of the HTTP server
        :param station: name of the station for which config is to be retrieved
        """
        path = CONFIG_HTTP_PATH.format(station=station)
        self._url = f"http://{host}:{port}{path}"

    def get_config(self: PasdConfigurationClient) -> dict[str, Any]:
        """
        Get the station config from the server.

        :return: a configuration dictionary.
        """
        with urllib.request.urlopen(self._url) as http_response:
            response_str = http_response.read()
            return json.loads(response_str)


router = APIRouter()


@router.get(CONFIG_HTTP_PATH)
async def get_config(
    request: Request,
    station: str,
) -> dict[str, Any]:
    """
    Handle a GET request for PaSD config for a specified station.

    :param request: information about this request (used to get access
        to the backend configuration service)
    :param station: name of the station for which PaSD config is requested.

    :return: a result dictionary

    :raises HTTPException: if the request could not be handled
    """
    service = request.app.state.backend

    try:
        return service.get_config(station)
    except PermissionError as pe:
        raise HTTPException(
            status_code=403,
            detail=f"Only station '{station}' can access its config",
        ) from pe
    except Exception as e:
        raise HTTPException(status_code=500) from e


@router.get("{path}")
async def get_bad_path(path: str) -> None:
    """
    Handle a GET request for any path not handled by one of the above routes.

    The above routes handle all valid paths, so any path not already
    handled must be an invalid path. Therefore this method raises a 404
    HTTP exception.

    :param path: the requested path.

    :raises HTTPException: because this path is not valid.
    """
    raise HTTPException(status_code=404, detail=f"Path '{path}' not found")


def _configure_server(
    backend: PasdConfigurationService,
    host: str = "0.0.0.0",
    port: int = 8081,
) -> uvicorn.Config:
    """
    Configure a PaSD configuration server.

    :param backend: the backend PaSD configuration_service
        to which this server will provide an interface.
    :param host: name of the interface on which to make the server
        available; defaults to "0.0.0.0" (all interfaces).
    :param port: port number on which to run the server; defaults to
        8081

    :return: a server that is ready to be run
    """
    pasd_configuration_service_api = FastAPI()
    pasd_configuration_service_api.state.backend = backend
    pasd_configuration_service_api.include_router(router)
    return uvicorn.Config(pasd_configuration_service_api, host=host, port=port)


class _ThreadableServer(uvicorn.Server):
    """A subclass of `uvicorn.Server` that can be run in a thread."""

    def install_signal_handlers(self: _ThreadableServer) -> None:
        """
        Overide this method to do nothing.

        This is necessary to allow this server to be run in a thread.
        """


class PasdConfigurationServerContextManager:
    """A context manager for a PaSD configuration_service."""

    def __init__(
        self: PasdConfigurationServerContextManager,
        backend: PasdConfigurationService,
    ) -> None:
        """
        Initialise a new instance.

        :param backend: the backend for which
            this PaSD configuration service provides web access.
        """
        self._socket = socket.socket()
        server_config = _configure_server(backend, host="127.0.0.1", port=0)
        self._server = _ThreadableServer(config=server_config)
        self._thread = threading.Thread(
            target=self._server.run, args=([self._socket],), daemon=True
        )

    def __enter__(
        self: PasdConfigurationServerContextManager,
    ) -> tuple[str, int]:
        """
        Enter the context in which the PaSD configuration server is running.

        That is, start up the PaSD configuration server.

        :return: the host and port of the running PaSD configuratino  server.
        """
        self._thread.start()

        while not self._server.started:
            time.sleep(1e-3)
        _, port = self._socket.getsockname()
        return "127.0.0.1", port

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exception: Optional[BaseException],
        trace: Optional[TracebackType],
    ) -> Literal[False]:
        """
        Exit the context in which the PaSD configuration server is running.

        That is, shut down the server.

        :param exc_type: the type of exception thrown in the with block
        :param exception: the exception thrown in the with block
        :param trace: a traceback

        :returns: whether the exception (if any) has been fully handled
            by this method and should be swallowed i.e. not re-raised
        """
        self._server.should_exit = True
        self._thread.join()
        return False


def run_server_forever(backend: PasdConfigurationService, port: int) -> None:
    """
    Run the PaSD configuration_service until terminated.

    :param backend: the backend for which this server provides an interface.
    :param port: the port on which to run the server.
        If set to 0, the server will be run on any available port.
        The actual port on which the server is running
        will be printed to stdout.
    """
    print("Starting PaSD configuration server...", flush=True)
    server_config = _configure_server(backend, port=port)
    the_server = uvicorn.Server(config=server_config)
    the_server.run()
    print("Stopping PaSD configuration server.")


def main() -> None:
    """
    Entry point for an HTTP server that fronts a PaSD configuration service.

    :raises ValueError: if required environment variables are missing.
    """
    namespace = os.getenv("NAMESPACE")
    if namespace is None:
        raise ValueError("NAMESPACE environment variable must be set.")

    station_name = os.getenv("STATION_NAME")
    if station_name is None:
        raise ValueError("STATION_NAME environment variable must be set.")

    logger = logging.getLogger()

    configuration_service = PasdConfigurationService(namespace, station_name, logger)

    port = int(os.getenv("PASD_CONFIGURATION_SERVER_PORT", "8081"))
    run_server_forever(configuration_service, port)


if __name__ == "__main__":
    main()
