#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for fndh."""
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

__all__ = ["FndhComponentManager"]


# pylint: disable-next=abstract-method
class FndhComponentManager(TaskExecutorComponentManager):
    """
    A component manager for an fndh.

    This communicates via a proxy to a MccsPadsBus that talks to a simulator
    or the real hardware.
    """

    def __init__(
        self: FndhComponentManager,
        logger: logging.Logger,
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[..., None],
        pasd_fqdn: Optional[str] = None,
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
        :param _pasd_bus_proxy: a optional injected device proxy for testing

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
        self.fndh_number = 1  # TODO: this should a property set during device setup
        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self.logger = logger

    def start_communicating(self: FndhComponentManager) -> None:
        """
        Establish communication with the pasdBus via a proxy.

        This checks:
            - A proxy can be formed with the MccsPasdBus
            - We can ping the device proxy.
            - subscribe to change events on proxy

        TODO: this can probably be refactored.
        """
        # Form proxy if not done yet.
        if self._pasd_bus_proxy is None:
            try:
                self.logger.info(f"attempting to form proxy with {self._pasd_fqdn}")

                self._pasd_bus_proxy = MccsDeviceProxy(
                    "low-mccs-pasd/pasdbus/001", self.logger, connect=True
                )
            except Exception as e:  # pylint: disable=broad-except
                self._update_component_state(fault=True)
                self.logger.error("Caught exception in start_communicating: %s", e)
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                return

        # If we are not established attempt for establish communication.
        if self.communication_state != CommunicationStatus.ESTABLISHED:

            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            try:
                # first check the proxy is reachable
                self._pasd_bus_proxy.ping()
                # TODO: then check the pasd_bus is communicating.
                # here we just assume it is.
                self._update_communication_state(CommunicationStatus.ESTABLISHED)

            except Exception as e:  # pylint: disable=broad-except
                self.logger.error("Unable to form communications: %s", e)
            # Check the ports on the fndh for power.
            if any(self._pasd_bus_proxy.fndhPortsPowerSensed):  # type: ignore
                self._update_component_state(power=PowerState.ON)
            else:
                self._update_component_state(power=PowerState.OFF)

        # subscribe to any change events.
        attributes_to_subscribe = ["healthState"]
        for item in attributes_to_subscribe:
            if (
                item.lower()
                not in self._pasd_bus_proxy._change_event_subscription_ids.keys()
            ):
                self._pasd_bus_proxy.add_change_event_callback(
                    "healthState", self._pasd_health_state_changed
                )

    def _pasd_health_state_changed(
        self: FndhComponentManager,
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

    def stop_communicating(self: FndhComponentManager) -> None:
        """Break off communication with the pasdBus."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return

        self._update_communication_state(CommunicationStatus.DISABLED)
        self._update_component_state(power=None, fault=None)

    @check_communicating
    def on(
        self: FndhComponentManager, task_callback: Optional[Callable] = None
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
        self: FndhComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:

        return

    @check_communicating
    def off(
        self: FndhComponentManager, task_callback: Optional[Callable] = None
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
        self: FndhComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:

        return

    @check_communicating
    def power_off_port(
        self: FndhComponentManager,
        port_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna off.

        :param port_number: (one-based) number of the TPM to turn off.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._power_off_port,
            args=[port_number],
            task_callback=task_callback,
        )

    def _power_off_port(
        self: FndhComponentManager,
        port_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [return_message]) = self._pasd_bus_proxy.TurnSmartboxOff(
                port_number
            )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power off port '{port_number} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power off port '{port_number} success'",
            )
        return result_code, return_message

    @check_communicating
    def power_on_port(
        self: FndhComponentManager,
        port_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna on.

        :param port_number: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._power_on_port,
            args=[
                port_number,
            ],
            task_callback=task_callback,
        )

    def _power_on_port(
        self: FndhComponentManager,
        port_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [unique_id]) = self._pasd_bus_proxy.TurnSmartboxOn(
                port_number
            )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power on port '{port_number} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on port '{port_number} success'",
            )
        return result_code, unique_id

    @check_communicating
    def get_smartbox_info(
        self: FndhComponentManager,
        port_id: int,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Smartbox off.

        :param port_id: (one-based) number of the TPM to turn off.

        :return: the task status and a human-readable status message
        """
        return self._pasd_bus_proxy.GetSmartboxInfo(port_id)  # type: ignore

    def is_port_on(self: FndhComponentManager) -> list[bool]:
        """
        Turn a Smartbox off.

        :return: the task status and a human-readable status message
        """
        return self._pasd_bus_proxy.fndhPortsPowerSensed  # type: ignore

    @property
    def smartbox_statuses(self: FndhComponentManager) -> list[str]:
        """
        Return the status of each smartbox.

        :return: a list of string statuses.
        """
        return self._pasd_bus_proxy.smartboxStatuses  # type: ignore
