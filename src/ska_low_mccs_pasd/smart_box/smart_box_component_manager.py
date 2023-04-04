#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements component management for smartboxs."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import tango
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    TaskStatus,
)
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

__all__ = ["SmartBoxComponentManager"]


# pylint: disable-next=abstract-method
class SmartBoxComponentManager(TaskExecutorComponentManager):
    """
    A component manager for an smartbox.

    This communicates via a proxy to a MccsPadsBus that talks to a simulator
    or the real hardware.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self: SmartBoxComponentManager,
        logger: logging.Logger,
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[..., None],
        pasd_fqdn: Optional[str] = None,
        fndh_port: Optional[int] = None,
        pasd_fqdn2: Optional[str] = None,
        _pasd_bus_proxy: Optional[MccsDeviceProxy] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param communication_state_changed_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed_callback: callback to be
            called when the component state changes
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param fndh_port: the port of the fndh this smartbox is attached.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
        :param pasd_fqdn2: the fqdn of the pasdbus to connect to.

        purposes only. defaults to None
        """
        max_workers = 1  # TODO: is this acceptable?
        super().__init__(
            logger,
            communication_state_changed_callback,
            component_state_changed_callback,
            max_workers=max_workers,
            power=None,
            fault=None,
            pasdbus_status=None,
        )
        self._component_state_changed_callback = component_state_changed_callback
        self._pasd_fqdn = pasd_fqdn
        self.smartbox_number = 1  # TODO: this should a property set during device setup
        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self.fndh_port = fndh_port
        self.logger = logger
        self.logger.info(f"The fqdn of pasd is {pasd_fqdn2}")

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """
        Establish communication with the pasdBus via a proxy.

        This checks:
            - A proxy can be formed with the MccsPasdBus
            - We can add a health change event callback to that proxy
            - The pasdBus is healthy
        """
        if self._pasd_bus_proxy is None:
            try:
                self.logger.info(f"attempting to form proxy with {self._pasd_fqdn}")

                self._pasd_bus_proxy = MccsDeviceProxy(
                    "low-mccs-pasd/pasdbus/001", self.logger, connect=True
                )
                self._pasd_bus_proxy.add_change_event_callback(
                    "healthState", self._pasd_health_state_changed
                )

            except Exception as e:  # pylint: disable=broad-except
                self._update_component_state(fault=True)
                self.logger.error("Caught exception in start_communicating: %s", e)
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

        # TODO: check the pasdbus status
        if self._pasd_bus_proxy.healthState == HealthState.OK:  # type: ignore
            self.logger.info(
                "SmartBox has successfully communicated with the MccsPasdBus"
            )
        if self.communication_state == CommunicationStatus.DISABLED:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            self._update_communication_state(CommunicationStatus.ESTABLISHED)

            # Check the port on the fndh which this smartbox is attached to.
            port = self.fndh_port
            if self._pasd_bus_proxy.fndhPortsPowerSensed[port]:  # type: ignore
                self._update_component_state(power=PowerState.ON)
            else:
                self._update_component_state(power=PowerState.OFF)

    def _pasd_health_state_changed(
        self: SmartBoxComponentManager,
        event_name: str,
        event_value: HealthState,
        event_quality: tango.AttrQuality,
    ) -> None:
        """
        Pasdbus health state callback.

        :param event_name: The event_name
        :param event_value: The event_value
        :param event_quality: The event_quality
        """
        self._update_component_state(pasdbus_status=event_value)

    def stop_communicating(self: SmartBoxComponentManager) -> None:
        """Break off communication with the pasdBus."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return

        self._update_communication_state(CommunicationStatus.DISABLED)
        self._update_component_state(power=None, fault=None)

    @check_communicating
    def on(
        self: SmartBoxComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Tell the upstream power supply proxy to turn the tpm on.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._on,
            args=[],
            task_callback=task_callback,
        )

    def _on(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:

        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([status], [result]) = self._pasd_bus_proxy.TurnSmartboxOn(self.fndh_port)
            if status == ResultCode.OK:
                self._update_component_state(power=PowerState.ON)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return (status, result)

    @check_communicating
    def off(
        self: SmartBoxComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Tell the upstream power supply proxy to turn the tpm on.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,
            args=[],
            task_callback=task_callback,
        )

    def _off(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([status], [result]) = self._pasd_bus_proxy.TurnSmartboxOff(self.fndh_port)

            if status == ResultCode.OK:
                self._update_component_state(power=PowerState.OFF)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return (status, result)

    @check_communicating
    def turn_off_port(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna off.

        :param antenna_number: (one-based) number of the TPM to turn off.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_off_port,
            args=[antenna_number],
            task_callback=task_callback,
        )

    def _turn_off_port(
        self: SmartBoxComponentManager,
        antenna_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [return_message]) = self._pasd_bus_proxy.TurnAntennaOff(
                antenna_number
            )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return result_code, return_message

    @check_communicating
    def turn_on_port(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna on.

        :param antenna_number: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_on_port,
            args=[
                antenna_number,
            ],
            task_callback=task_callback,
        )

    def _turn_on_port(
        self: SmartBoxComponentManager,
        antenna_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [unique_id]) = self._pasd_bus_proxy.TurnAntennaOn(
                antenna_number
            )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return result_code, unique_id

    @check_communicating
    def get_antenna_info(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna off.

        :param antenna_number: (one-based) number of the TPM to turn off.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._get_antenna_info,
            args=[antenna_number],
            task_callback=task_callback,
        )

    def _get_antenna_info(
        self: SmartBoxComponentManager,
        antenna_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [unique_id]) = self._pasd_bus_proxy.GetAntennaInfo(
                antenna_number
            )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return result_code, unique_id

    @property
    def antennas_tripped(self: SmartBoxComponentManager) -> list[bool]:
        """
        Return whether each antenna has had its breaker tripped.

        :return: a list of booleans indicating whether each antenna has
            had its breaker tripped.
        """
        return self._pasd_bus_proxy.antennasTripped  # type: ignore
