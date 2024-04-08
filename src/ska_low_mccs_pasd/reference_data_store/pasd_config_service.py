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

    def __init__(self: ConfigMapManager, namespace: str) -> None:
        """
        Manage read requests to a ConfigMap.

        :param namespace: The namespace the configmap resides
        """
        self._configmap_namespace = namespace

        client = dynamic.DynamicClient(
            api_client.ApiClient(configuration=config.load_incluster_config())
        )
        self._configmap_view = client.resources.get(api_version="v1", kind="ConfigMap")

    def read_data(self, station: str) -> dict:
        """
        Read the data from the configmap.

        :param station: The name of the station for which data is to be read.
            The relevant configmaps are expected to be correctly labelled
            e.g. "station=s8-1".

        :returns: a empty dictionary if unsuccessful
            or a dictionary containing data from configMap.
        """
        configmaps = self._configmap_view.get(
            namespace=self._configmap_namespace,
            label_selector=f"platform_spec=pasd, station={station}",
        )
        configmap = next(iter(configmaps.items))
        _, data_yaml = next(iter(configmap.data.items()))
        data = yaml.safe_load(data_yaml)
        return data


# pylint: disable=too-few-public-methods
class PasdConfigurationService:
    """A service that provides PaSD configuration for a station."""

    def __init__(
        self: PasdConfigurationService,
        namespace: str,
        logger: logging.Logger,
        _config_manager: Optional[ConfigMapManager] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param namespace: the namespace of the configMap.
        :param logger: an injected logger for information.
        :param _config_manager: _config_manager to use for testing.
        """
        self.logger = logger
        self._configmanager = _config_manager or ConfigMapManager(namespace)

    def get_config(self: PasdConfigurationService, station_name: str) -> dict[str, Any]:
        """
        Return the PaSD configuration for the specified station.

        :param station_name: name of the station for which to return
            PaSD configuration.

        :return: configuration dictionary for the station
        """
        self.logger.info(f"station name requesting {station_name} ...")
        return self._configmanager.read_data(station_name)
