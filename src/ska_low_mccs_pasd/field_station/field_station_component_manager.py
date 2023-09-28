#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for FieldStation."""
from __future__ import annotations

import functools
import json
import logging
import threading
from typing import Any, Callable, Optional

from ska_control_model import TaskStatus
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

from ..command_proxy import MccsCommandProxy

__all__ = ["FieldStationComponentManager"]


class FieldStationComponentManager(TaskExecutorComponentManager):
    """
    A component manager for MccsFieldStation.

    Note: Initial stub device.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self: FieldStationComponentManager,
        logger: logging.Logger,
        fndh_name: str,
        smartbox_names: list[str],
        communication_state_callback: Callable[..., None],
        component_state_changed: Callable[..., None],
        _fndh_proxy: Optional[DeviceComponentManager] = None,
        _smartbox_proxys: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param fndh_name: the name of the fndh this field station
            encompasses
        :param smartbox_names: the names of the smartboxes this field station
            encompasses
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed: callback to be
            called when the component state changes
        :param _fndh_proxy: a injected fndh proxy for purposes of testing only.
        :param _smartbox_proxys: injected smartbox proxys for purposes of testing only.
        """
        self._communication_state_callback: Callable[..., None]
        self._component_state_callback: Callable[..., None]
        max_workers = 1
        super().__init__(
            logger,
            communication_state_callback,
            component_state_changed,
            max_workers=max_workers,
        )
        self._fndh_name = fndh_name
        self._fndh_proxy = _fndh_proxy or DeviceComponentManager(
            fndh_name,
            logger,
            max_workers,
            functools.partial(
                self._communication_state_callback, device_name=fndh_name
            ),
            functools.partial(self._component_state_callback, device_name=fndh_name),
        )

        self._smartbox_proxys = {}
        if _smartbox_proxys:
            self._smartbox_proxys = _smartbox_proxys
        else:
            for smartbox_name in smartbox_names:
                self._smartbox_proxys[smartbox_name] = DeviceComponentManager(
                    smartbox_name,
                    logger,
                    max_workers,
                    functools.partial(
                        self._communication_state_callback, device_name=smartbox_name
                    ),
                    functools.partial(
                        self._component_state_callback, device_name=smartbox_name
                    ),
                )

        self.logger = logger


    def update_configuration(
        self: FieldStationComponentManager,
        configuration: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn on an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        Note: Not implemented yet

        :param antenna_number: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._update_configuration,  # type: ignore[arg-type]
            args=[
                configuration
            ],
            task_callback=task_callback,
        )

    def _update_configuration(
        self: FieldStationComponentManager,
        configuration: str,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        self.logger.info(f"my configuration has been updated with: {configuration}")

    @check_communicating
    def turn_on_antenna(
        self: FieldStationComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn on an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        Note: Not implemented yet

        :param antenna_number: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_on_antenna,  # type: ignore[arg-type]
            args=[
                antenna_number,
            ],
            task_callback=task_callback,
        )

    def _turn_on_antenna(
        self: FieldStationComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        # TODO: Implement
        raise NotImplementedError("turn_on_antenna not yet implemented")

    def start_communicating(self: FieldStationComponentManager) -> None:
        """Establish communication."""
        self._fndh_proxy.start_communicating()
        for proxy in self._smartbox_proxys.values():
            proxy.start_communicating()

    def stop_communicating(self: FieldStationComponentManager) -> None:
        """Break off communication with the pasdBus."""
        self._fndh_proxy.stop_communicating()
        for proxy in self._smartbox_proxys.values():
            proxy.stop_communicating()

    def on(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn on the FieldStation.

        Turning on the FieldStation will distribute power
        to all antennas that make up that FieldStation.

        Note: NotImplemented

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._on,
            args=[],
            task_callback=task_callback,
        )

    def _on(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        # TODO: This will turn on all antennas that make up this station.
        raise NotImplementedError("On functionality not yet implemented")

    def off(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn off the FieldStation.

        Turning off the FieldStation will cut off power
        to all antennas that make up that FieldStation.

        Note: NotImplemented

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,
            args=[],
            task_callback=task_callback,
        )

    def _off(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        # TODO: This will turn off all antennas that make up this station.
        raise NotImplementedError("Off functionality not yet implemented")

    def configure(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus, str]:
        """
        Configure the field station.

        Currently this only supports configuring FNDH alarm thresholds.

        :param task_callback: callback to be called when the status of
            the command changes
        :param kwargs: keyword arguments extracted from the JSON string.

        :return: the task status and a human-readable status message
        """
        command_proxy = MccsCommandProxy(self._fndh_name, "Configure", self.logger)
        return command_proxy(json.dumps(kwargs), task_callback=task_callback)
