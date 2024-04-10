# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""
This module provides a PaSD Configuration service.

It is fronted by the server defined in the `pasd_config_client_server` module.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import yaml
from kubernetes import config, dynamic
from kubernetes.client import api_client


# pylint: disable=too-few-public-methods
class ConfigMapManager:
    """A class that manages access to a configMap."""

    def __init__(
        self: ConfigMapManager,
        name: str,
        namespace: str,
        label_selector: str,
    ) -> None:
        """
        Manage read requests to a ConfigMap.

        :param name: The name of the configmap to manage.
        :param namespace: The namespace the configmap resides
        :param label_selector: a string with a key/value pair
            e.g. "findme=true"
        """
        self._configmap_name = name
        self._configmap_namespace = namespace
        self._configmap_label = label_selector

        client = dynamic.DynamicClient(
            api_client.ApiClient(configuration=config.load_incluster_config())
        )
        self._api = client.resources.get(api_version="v1", kind="ConfigMap")

    def read_data(self) -> dict:
        """
        Read the data from the configmap.

        :returns: a empty dictionary if unsuccessful
            or a dictionary containing data from configMap.
        """
        configmap_list = self._api.get(
            name=self._configmap_name,
            namespace=self._configmap_namespace,
            label_selector=self._configmap_label,
        )
        config_data = configmap_list.data
        for _, data_yaml in config_data.items():
            data = yaml.safe_load(data_yaml)
        return data


# pylint: disable=too-few-public-methods
class PasdConfigurationService:
    """A service that provides PaSD configuration for a station."""

    def __init__(
        self: PasdConfigurationService,
        namespace: str,
        station_name: str,
        logger: logging.Logger,
        _config_manager: Optional[Any] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param namespace: the namespace of the configMap.
        :param station_name: the station name used to locate the configmap.
        :param logger: an injected logger for information.
        :param _config_manager: _config_manager to use for testing.
        """
        self.logger = logger
        self._station_name = station_name
        self.configmanager = _config_manager or ConfigMapManager(
            name=f"pasd-configuration-{station_name}",
            namespace=namespace,
            label_selector="findme=configmap-to-watch",
        )

    def get_config(self: PasdConfigurationService, station_name: str) -> dict[str, Any]:
        """
        Return the PaSD configuration for the specified station.

        :param station_name: name of the station for which to return
            PaSD configuration.

        :return: configuration dictionary for the station

        :raises PermissionError: if the station name requested doesn't match
            the station served by this service.
        """
        self.logger.info(f"station name requesting {station_name} ...")
        if not self._station_name == station_name:
            self.logger.warning(f"access refused to station {self._station_name}")
            raise PermissionError(
                f"only {self._station_name} has permission to access configuration.",
            )

        self.logger.info(f"access granted to {self._station_name}")
        return self.configmanager.read_data()
