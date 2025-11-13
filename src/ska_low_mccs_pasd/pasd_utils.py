# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides common code for all PaSD devices."""


from __future__ import annotations

from typing import Any

from tango import Database

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
        self.database = Database()

    def put_value(self: PasdDatabase, dev_name: str, all_thresholds: dict) -> None:
        """
        Put the value to the tango database.

        :param dev_name: name of the device.
        :param all_thresholds: dict of all the thresholds
        """
        self.database.put_device_attribute_property(
            dev_name, {"cache_threshold": all_thresholds}
        )

    def get_value(self: PasdDatabase, dev_name: str, attr_name: str) -> Any:
        """Get the value from the database.

        :param dev_name: Name of the device.
        :param attr_name: Name of the attribute.

        :return: The value from the tango database.
        """
        tmp = self.database.get_device_attribute_property(
            dev_name, {"cache_threshold": attr_name}
        )
        return tmp["cache_threshold"]

    def clear_thresholds(self: PasdDatabase, dev_name: str) -> None:
        """Clear the database of threshold values.

        :param dev_name: Name of the device.
        """
        self.database.delete_device_attribute_property(dev_name, "cache_threshold")
