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
import importlib.resources
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

NUMBER_OF_SMARTBOXES = 24
NUMBER_OF_SMARTBOX_PORTS = 12
NUMBER_OF_FNDH_PORTS = 28
NUMBER_OF_ANTENNAS = 256


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
        antenna_mask: list[bool],  # 1-indexed, entry 0 corresponds to all antennas
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

        # REMEMBER TO DELETE. This is temporary until we have a real configuration.
        config = importlib.resources.read_text(
            "ska_low_mccs_pasd.field_station.resources",
            "config.json",
        )
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

    def _on(  # pylint: disable=too-many-locals
        self: FieldStationComponentManager,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
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
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = self._get_masked_smartbox_ports()
        results = []
        assert self._fndh_proxy._proxy
        masked_fndh_ports: list = self._get_masked_fndh_ports(masked_smartbox_ports)
        desired_fndh_port_powers: list[bool | None] = [True] * NUMBER_OF_FNDH_PORTS
        for masked_port in masked_fndh_ports:
            desired_fndh_port_powers[masked_port - 1] = None
        json_argument = json.dumps(
            {
                "port_powers": desired_fndh_port_powers,
                "stay_on_when_offline": True,
            }
        )

        result, _ = self._fndh_proxy._proxy.SetPortPowers(json_argument)
        results += result
        masked_ports = []
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys):
            assert smartbox._proxy
            desired_smartbox_port_powers: list[bool | None] = [
                True
            ] * NUMBER_OF_SMARTBOX_PORTS
            masked_ports = masked_smartbox_ports.get(smartbox_no + 1, [])
            for masked_port in masked_ports:
                desired_smartbox_port_powers[masked_port - 1] = None
            json_argument = json.dumps(
                {
                    "smartbox_number": smartbox_no + 1,
                    "port_powers": desired_smartbox_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            result, _ = smartbox._proxy.SetPortPowers(json_argument)
            results += result
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

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,
            args=[],
            task_callback=task_callback,
        )

    def _off(  # pylint: disable=too-many-locals
        self: FieldStationComponentManager,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
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
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = self._get_masked_smartbox_ports()
        results = []
        assert self._fndh_proxy._proxy
        masked_fndh_ports: list = self._get_masked_fndh_ports(masked_smartbox_ports)
        desired_fndh_port_powers: list[int | None] = [False] * NUMBER_OF_FNDH_PORTS
        for masked_port in masked_fndh_ports:
            desired_fndh_port_powers[masked_port - 1] = None

        json_argument = json.dumps(
            {
                "port_powers": desired_fndh_port_powers,
                "stay_on_when_offline": True,
            }
        )

        result, _ = self._fndh_proxy._proxy.SetPortPowers(json_argument)
        results += result
        masked_ports = []
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys):
            assert smartbox._proxy
            desired_smartbox_port_powers: list[int | None] = [
                False
            ] * NUMBER_OF_SMARTBOX_PORTS
            masked_ports = masked_smartbox_ports.get(smartbox_no + 1, [])
            for masked_port in masked_ports:
                desired_smartbox_port_powers[masked_port - 1] = None
            json_argument = json.dumps(
                {
                    "smartbox_number": self._smartbox_mapping[smartbox_no + 1],
                    "port_powers": desired_smartbox_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            result, _ = smartbox._proxy.SetPortPowers(json_argument)
            results += result

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
        # A FNDH port will be masked if either there is no smartbox
        # attached to the port or the smartbox attached to the port is
        # masked
        masked_fndh_ports = []
        for smartbox_id in list(masked_smartbox_ports.keys()):
            if len(masked_smartbox_ports[smartbox_id]) == NUMBER_OF_SMARTBOX_PORTS:
                fndh_port = self._smartbox_mapping[smartbox_id]
                masked_fndh_ports.append(fndh_port)
        for fndh_port, fndh_port_state in enumerate(
            self._get_fndh_ports_with_smartboxes()
        ):
            if fndh_port_state is False:
                masked_fndh_ports.append(fndh_port + 1)

        return masked_fndh_ports

    def _get_masked_smartbox_ports(
        self: FieldStationComponentManager,
    ) -> dict[int, list]:
        # A smartbox port will be masked if either there is no antenna
        # attached to the port or the antenna attached to the port is
        # masked
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

        for smartbox_id in range(1, NUMBER_OF_SMARTBOXES + 1):
            for smartbox_port, smartbox_state in enumerate(
                self._get_smartbox_ports_with_antennas(smartbox_id)
            ):
                if smartbox_state is False:
                    try:
                        masked_smartbox_ports[smartbox_id]
                    except KeyError:
                        masked_smartbox_ports[smartbox_id] = []
                    masked_smartbox_ports[smartbox_id].append(smartbox_port + 1)

        return masked_smartbox_ports

    def _get_smartbox_ports_with_antennas(
        self: FieldStationComponentManager, smartbox_id: int
    ) -> list:
        smartbox_ports = [False] * NUMBER_OF_SMARTBOX_PORTS
        for smartbox in list(self._antenna_mapping.values()):
            if smartbox[0] == smartbox_id:
                smartbox_ports[smartbox[1] - 1] = True
        return smartbox_ports

    def _get_fndh_ports_with_smartboxes(self: FieldStationComponentManager) -> list:
        fndh_ports = [False] * NUMBER_OF_FNDH_PORTS
        for fndh_port in list(self._smartbox_mapping.values()):
            fndh_ports[fndh_port - 1] = True
        return fndh_ports

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
    def _turn_on_antenna(  # noqa: C901, pylint: disable=too-many-branches
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

        smartbox_id, smartbox_port = self._antenna_mapping[antenna_number]
        try:
            smartbox_proxy = self._smartbox_proxys[smartbox_id - 1]
        except KeyError:
            msg = (
                f"Tried to turn on antenna {antenna_number}, this is mapped to "
                f"smartbox {smartbox_id}, port {smartbox_port}. However this smartbox"
                " device is not deployed"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED
        fndh_port = self._smartbox_mapping[smartbox_id]

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

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
        Turn off an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

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
    def _turn_off_antenna(  # noqa: C901, pylint: disable=too-many-branches
        self: FieldStationComponentManager,
        antenna_number: int,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
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

        smartbox_id, smartbox_port = self._antenna_mapping[antenna_number]
        try:
            smartbox_proxy = self._smartbox_proxys[smartbox_id - 1]
        except KeyError:
            msg = (
                f"Tried to turn off antenna {antenna_number}, this is mapped to "
                f"smartbox {smartbox_id}, port {smartbox_port}. However this smartbox"
                " device is not deployed"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED
        fndh_port = self._smartbox_mapping[smartbox_id]

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

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

        Currently this only pulls in mappings from a static source.

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

        antenna_mask: list[bool] = [False] * (NUMBER_OF_ANTENNAS + 1)
        antenna_mapping: dict[int, list] = {}
        all_masked = True
        for antenna_id in list(antennas.keys()):
            antenna_data = antennas[antenna_id]
            antenna_mask[int(antenna_id)] = antenna_data["masked"]
            if not antenna_mask[int(antenna_id)]:
                all_masked = False

            antenna_mapping[int(antenna_id)] = [
                int(antenna_data["smartbox"]),
                antenna_data["smartbox_port"],
            ]
        antenna_mask[0] = all_masked
        smartboxes = self._configuration["pasd"]["smartboxes"]
        smartbox_mapping: dict[int, int] = {}
        for smartbox_id in list(smartboxes.keys()):
            smartbox = smartboxes[smartbox_id]
            smartbox_mapping[int(smartbox_id)] = smartbox["fndh_port"]
        self._antenna_mask = antenna_mask
        self._antenna_mapping = antenna_mapping
        self._smartbox_mapping = smartbox_mapping

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
