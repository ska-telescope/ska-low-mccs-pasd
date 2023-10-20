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

from ska_control_model import CommunicationStatus, TaskStatus
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

from ..command_proxy import MccsCommandProxy

__all__ = ["FieldStationComponentManager"]

SMARTBOX_NUMBER = 24
SMARTBOX_PORTS = 12
ANTENNA_NUMBER = 256


class FieldStationComponentManager(TaskExecutorComponentManager):
    """
    A component manager for MccsFieldStation.

    Note: Initial stub device.
    """

    # pylint: disable=too-many-arguments, abstract-method, too-many-instance-attributes
    def __init__(
        self: FieldStationComponentManager,
        logger: logging.Logger,
        fndh_name: str,
        smartbox_names: list[str],
        antenna_mask: list[bool],  # 0-indexed
        antenna_mapping: dict[int, list],  # 1-indexed
        smartbox_mapping: dict[int, int],  # 1-indexed
        communication_state_callback: Callable[..., None],
        component_state_changed: Callable[..., None],
        _fndh_proxy: Optional[DeviceComponentManager] = None,
        _smartbox_proxys: Optional[list[DeviceComponentManager]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param fndh_name: the name of the fndh this field station
            encompasses
        :param smartbox_names: the names of the smartboxes this field station
            encompasses
        :param antenna_mask: the default antenna mask, all antennas unmasked.
        :param antenna_mapping: the default antenna mapping, antennas are assigned
            in ascending order of smartbox port and smartbox id.
        :param smartbox_mapping: the fault smartbox mapping, fndh port = smartbox id.
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

        self._communication_states = {
            fqdn: CommunicationStatus.DISABLED
            for fqdn in [fndh_name] + list(smartbox_names)
        }

        self._fndh_name = fndh_name
        self._fndh_proxy = _fndh_proxy or DeviceComponentManager(
            fndh_name,
            logger,
            max_workers,
            functools.partial(self._device_communication_state_changed, fndh_name),
            functools.partial(self._component_state_callback, device_name=fndh_name),
        )

        self._smartbox_proxys = []
        if _smartbox_proxys:
            self._smartbox_proxys = _smartbox_proxys
        else:
            for smartbox_name in smartbox_names:
                self._smartbox_proxys.append(
                    DeviceComponentManager(
                        smartbox_name,
                        logger,
                        max_workers,
                        functools.partial(
                            self._device_communication_state_changed, smartbox_name
                        ),
                        functools.partial(
                            self._component_state_callback, device_name=smartbox_name
                        ),
                    )
                )

        self.logger = logger

        self._configuration = {}
        self._antenna_mask = antenna_mask
        self._antenna_mapping = antenna_mapping
        self._smartbox_mapping = smartbox_mapping

        # REMEMBER TO DELETE
        with open("config.txt", encoding="utf-8") as f:
            config = f.read()
            self._configuration = json.loads(config)

    def start_communicating(self: FieldStationComponentManager) -> None:
        """Establish communication."""
        if self._communication_state == CommunicationStatus.ESTABLISHED:
            return

        if self._communication_state == CommunicationStatus.DISABLED:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

        self._fndh_proxy.start_communicating()
        for proxy in self._smartbox_proxys:
            proxy.start_communicating()

    def stop_communicating(self: FieldStationComponentManager) -> None:
        """Break off communication with the pasdBus."""
        self._fndh_proxy.stop_communicating()
        for proxy in self._smartbox_proxys:
            proxy.stop_communicating()

        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._update_communication_state(CommunicationStatus.DISABLED)

    def _device_communication_state_changed(
        self: FieldStationComponentManager,
        fqdn: str,
        communication_state: CommunicationStatus,
    ) -> None:
        # Many callback threads could be hitting this method at the same time, so it's
        # possible (likely) that the GIL will suspend a thread between checking if it
        # need to update, and actually updating. This leads to callbacks appearing out
        # of order, which breaks tests. Therefore we need to serialise access.

        self._communication_states[fqdn] = communication_state
        self.logger.debug(
            f"device {fqdn} changed communcation state to {communication_state.name}"
        )

        if CommunicationStatus.DISABLED in self._communication_states.values():
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
        elif CommunicationStatus.NOT_ESTABLISHED in self._communication_states.values():
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
        else:
            self._update_communication_state(CommunicationStatus.ESTABLISHED)

    def on(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn on the FieldStation.

        Turning on the FieldStation will distribute power
        to all antennas that make up that FieldStation.

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
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        self.logger.error("on called")
        if not ignore_mask and self._antenna_mask[0]:
            msg = (
                "Antennas in this station are masked, "
                "call with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        self.logger.error("1")
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = self._get_masked_smartbox_ports()

        results = []
        self.logger.error("2")

        assert self._fndh_proxy._proxy
        masked_fndh_ports: list = self._get_masked_fndh_ports(masked_smartbox_ports)
        result, _ = self._fndh_proxy._proxy.PowerOnAllPorts(masked_fndh_ports)
        results += result

        self.logger.error("3")
        masked_ports = []
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys):
            assert smartbox._proxy
            masked_ports = masked_smartbox_ports.get(smartbox_no + 1, [])
            self.logger.error("5")
            self.logger.error(masked_ports)
            result, _ = smartbox._proxy.PowerOnAllPorts(masked_ports)
            self.logger.error("6")
            results += result
        self.logger.error("4")
        if all(result == ResultCode.OK for result in results):
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result="All unmasked antennas turned on.",
                )
            return
        if task_callback:
            task_callback(
                status=TaskStatus.FAILED, result="Didn't turn on all unmasked antennas."
            )

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
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        self.logger.error("off called")
        if not ignore_mask and self._antenna_mask[0]:
            msg = (
                "Antennas in this station are masked, "
                "call with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        self.logger.error("1")
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = self._get_masked_smartbox_ports()

        results = []
        self.logger.error("2")
        assert self._fndh_proxy._proxy
        masked_fndh_ports: list = self._get_masked_fndh_ports(masked_smartbox_ports)
        result, _ = self._fndh_proxy._proxy.PowerOffAllPorts(masked_fndh_ports)
        results += result
        self.logger.error("3")
        masked_ports = []
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys):
            assert smartbox._proxy
            masked_ports = masked_smartbox_ports.get(smartbox_no + 1, [])
            self.logger.error("5")
            result, _ = smartbox._proxy.PowerOffAllPorts(masked_ports)
            self.logger.error("6")
            results += result
        self.logger.error("4")
        if all(result == ResultCode.OK for result in results):
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result="All unmasked antennas turned off.",
                )
            return
        if task_callback:
            task_callback(
                status=TaskStatus.FAILED,
                result="Didn't turn off all unmasked antennas.",
            )

    def _get_masked_fndh_ports(
        self: FieldStationComponentManager, masked_smartbox_ports: dict
    ) -> list:
        masked_fndh_ports = []
        for smartbox_id in list(masked_smartbox_ports.keys()):
            if len(masked_smartbox_ports[smartbox_id]) == SMARTBOX_PORTS:
                fndh_port = self._smartbox_mapping[smartbox_id]
                masked_fndh_ports.append(fndh_port)
        return masked_fndh_ports

    def _get_masked_smartbox_ports(
        self: FieldStationComponentManager,
    ) -> dict[int, list]:
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = {}
        for antenna_id, antenna_masked in enumerate(self._antenna_mask):
            # Checking antenna_id > 0 as 0 corresponds to all antennas
            if antenna_masked and antenna_id > 0:
                smartbox_id, smartbox_port = self._antenna_mapping[antenna_id]
                try:
                    masked_smartbox_ports[smartbox_id]
                except KeyError:
                    masked_smartbox_ports[smartbox_id] = []
                masked_smartbox_ports[smartbox_id].append(smartbox_port)
        return masked_smartbox_ports

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

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_on_antenna(  # noqa: C901
        self: FieldStationComponentManager,
        antenna_number: int,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
        assert self._fndh_proxy._proxy is not None
        if not ignore_mask and (self._antenna_mask[antenna_number]):
            msg = (
                f"Antenna number {antenna_number} is masked, call "
                "with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if ignore_mask:
            self.logger.warning("Turning on masked antenna")

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        smartbox_id, smartbox_port = self._antenna_mapping[antenna_number]
        smartbox_proxy = self._smartbox_proxys[smartbox_id - 1]
        fndh_port = self._smartbox_mapping[smartbox_id]

        if not self._fndh_proxy._proxy.PortPowerState(fndh_port):
            result, _ = self._fndh_proxy._proxy.PowerOnPort(fndh_port)

        if not smartbox_proxy._proxy.PortsPowerSensed[smartbox_port]:
            if result is None or result[0] in [
                ResultCode.OK,
                ResultCode.STARTED,
                ResultCode.QUEUED,
            ]:
                result, _ = smartbox_proxy._proxy.PowerOnPort(smartbox_port)
        if result is None:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"antenna {antenna_number} was already on.",
                )
            return TaskStatus.COMPLETED
        if result[0] in [
            ResultCode.OK,
            ResultCode.STARTED,
            ResultCode.QUEUED,
        ]:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"turn on antenna {antenna_number} success.",
                )
            return TaskStatus.COMPLETED
        if task_callback:
            task_callback(status=TaskStatus.FAILED)

        return TaskStatus.FAILED

    @check_communicating
    def turn_off_antenna(
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
            self._turn_off_antenna,  # type: ignore[arg-type]
            args=[
                antenna_number,
            ],
            task_callback=task_callback,
        )

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_off_antenna(  # noqa: C901
        self: FieldStationComponentManager,
        antenna_number: int,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
        self.logger.error(antenna_number)
        assert self._fndh_proxy._proxy is not None
        if not ignore_mask and self._antenna_mask[antenna_number]:
            msg = (
                f"Antenna number {antenna_number} is masked, call "
                "with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if ignore_mask:
            self.logger.warning("Turning off masked antenna")

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        print(f"{self._antenna_mapping}")
        smartbox_id, smartbox_port = self._antenna_mapping[antenna_number]

        print(f"{self._smartbox_proxys}")
        smartbox_proxy = self._smartbox_proxys[smartbox_id - 1]

        print(f"{self._smartbox_mapping}")
        fndh_port = self._smartbox_mapping[smartbox_id]

        if self._fndh_proxy._proxy.PortPowerState(fndh_port):
            result, _ = self._fndh_proxy._proxy.PowerOffPort(fndh_port)

        if smartbox_proxy._proxy.PortsPowerSensed[smartbox_port]:
            if result is None or result[0] in [
                ResultCode.OK,
                ResultCode.STARTED,
                ResultCode.QUEUED,
            ]:
                result, _ = smartbox_proxy._proxy.PowerOffPort(smartbox_port)
        if result is None:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"antenna {antenna_number} was already off.",
                )
            return TaskStatus.COMPLETED
        if result[0] in [
            ResultCode.OK,
            ResultCode.STARTED,
            ResultCode.QUEUED,
        ]:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"turn off antenna {antenna_number} success.",
                )
            return TaskStatus.COMPLETED
        if task_callback:
            task_callback(status=TaskStatus.FAILED)
        return TaskStatus.FAILED

    def update_configuration(
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
        return self.submit_task(
            self._update_configuration,  # type: ignore[arg-type]
            args=[],
            task_callback=task_callback,
        )

    def _update_configuration(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        antennas = self._configuration["antennas"]

        print(antennas)

        antenna_mask: list[bool] = [False] * (ANTENNA_NUMBER + 1)
        antenna_mapping: dict[int, list] = {}
        all_masked = True
        print("1")
        for antenna_id in list(antennas.keys()):
            print("2")
            antenna_data = antennas[antenna_id]
            print("4")
            antenna_mask[int(antenna_id)] = antenna_data["masked"]
            print("5")
            if not antenna_mask[int(antenna_id)]:
                all_masked = False
            print("6")
            antenna_mapping[int(antenna_id)] = [
                int(antenna_data["smartbox"]),
                antenna_data["smartbox_port"],
            ]
        print("3")
        antenna_mask[0] = all_masked
        smartboxes = self._configuration["pasd"]["smartboxes"]
        print("4")
        smartbox_mapping: dict[int, int] = {}
        for smartbox_id in list(smartboxes.keys()):
            smartbox = smartboxes[smartbox_id]
            smartbox_mapping[int(smartbox_id)] = smartbox["fndh_port"]
        print("6")
        self._antenna_mask = antenna_mask
        self._antenna_mapping = antenna_mapping
        self._smartbox_mapping = smartbox_mapping
        print("7")

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
