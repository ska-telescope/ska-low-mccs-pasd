# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides common code for all PaSD devices."""


from __future__ import annotations

import logging
from typing import Any

from tango import Database, DevFailed

from .pasd_controllers_configuration import ControllerDict

__all__ = ["PasdThresholds"]


def join_health_reports(messages: list[str]) -> str:
    """
    Join the messages removing duplicates and empty strings.

    :param messages: a list of messages.

    :returns: a string with result.
    """
    seen = set()
    unique_messages = []

    for message in messages:
        # Ignore empty strings and duplicates
        if message and message not in seen:
            seen.add(message)
            unique_messages.append(message)

    return "\n".join(unique_messages)


class PasdThresholds:
    """Pasd thresholds."""

    def __init__(self: PasdThresholds, config: ControllerDict) -> None:
        """
        Init thresholds.

        :param config: Pasd config
        """
        self._thresholds: dict = {}
        for register in config["registers"].values():
            name = register["tango_attr_name"]
            if name.endswith("thresholds"):
                setattr(self, name, {})
                self._thresholds[name] = []

    def update(self: PasdThresholds, new_thresholds: dict) -> None:
        """
        Update the thresholds with new values.

        :param new_thresholds: New thresholds to be updated.
        """
        for name, values in new_thresholds.items():
            setattr(self, name, values)
            self._thresholds[name] = values

    @property
    def all_thresholds(self: PasdThresholds) -> dict:
        """
        Return all thresholds in dict.

        :return: all thresholds in dict.
        """
        return self._thresholds


class PasdDatabase:
    """Wrapper around the tango database for testing purposes."""

    def __init__(self) -> None:
        self._database: Database | None = None

    def _get_database(self: PasdDatabase) -> Database | None:
        """
        Lazily connect to the tango database, retrying on each call if needed.

        The Tango database may be unreachable (e.g. not yet started, or this
        device is being run standalone for documentation generation), in
        which case we fall back to default threshold values rather than
        taking down the whole device.

        :return: the connected database, or None if it could not be reached.
        """
        if self._database is None:
            try:
                self._database = Database()
            except DevFailed as db_error:
                logging.getLogger(__name__).warning(
                    "Could not connect to the Tango database: %s", db_error
                )
        return self._database

    def put_value(self: PasdDatabase, dev_name: str, all_thresholds: dict) -> None:
        """
        Put the value to the tango database.

        :param dev_name: name of the device.
        :param all_thresholds: dict of all the thresholds
        """
        database = self._get_database()
        if database is None:
            return
        try:
            database.put_device_attribute_property(
                dev_name, {"cache_threshold": all_thresholds}
            )
        except DevFailed as db_error:
            logging.getLogger(__name__).warning(
                "Could not persist thresholds to the Tango database: %s", db_error
            )

    def get_value(self: PasdDatabase, dev_name: str, attr_name: str) -> Any:
        """Get the value from the database.

        :param dev_name: Name of the device.
        :param attr_name: Name of the attribute.

        :return: The value from the tango database, or None if unavailable.
        """
        database = self._get_database()
        if database is None:
            return None
        try:
            tmp = database.get_device_attribute_property(
                dev_name, {"cache_threshold": attr_name}
            )
            return tmp["cache_threshold"]
        except DevFailed as db_error:
            logging.getLogger(__name__).warning(
                "Could not read thresholds from the Tango database: %s", db_error
            )
            return None

    def clear_thresholds(
        self: PasdDatabase, dev_name: str, all_thresholds: dict
    ) -> None:
        """Clear the database of threshold values.

        :param dev_name: Name of the device.
        :param all_thresholds: dict of all the thresholds
        """
        database = self._get_database()
        if database is None:
            return
        empty_dict: dict = {}
        for name in all_thresholds.keys():
            empty_dict[name] = []
        try:
            database.put_device_attribute_property(
                dev_name, {"cache_threshold": empty_dict}
            )
        except DevFailed as db_error:
            logging.getLogger(__name__).warning(
                "Could not clear thresholds in the Tango database: %s", db_error
            )
