#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for fndh."""
from __future__ import annotations

import functools
import json
import logging
import re
import threading
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

__all__ = ["FndhComponentManager", "_PasdBusProxy"]


class _PasdBusProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus bus."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _PasdBusProxy,
        fqdn: str,
        logger: logging.Logger,
        smartbox_communication_state_callback: Callable[[CommunicationStatus], None],
        smartbox_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        update_port_power_states: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the MccsPaSDBus device
        :param logger: the logger to be used by this object.
        :param smartbox_communication_state_callback: callback to be
            called when the status of the communications change.
        :param smartbox_state_callback: callback to be called when the
            component state changes
        :param attribute_change_callback: callback for when a attribute relevant to
            this smartbox changes.
        :param update_port_power_states: callback to be called when the port
            power states changes.
        """
        self._update_port_power_states = update_port_power_states
        self._attribute_change_callback = attribute_change_callback
        self.pasd_device = 0

        super().__init__(
            fqdn,
            logger,
            1,
            smartbox_communication_state_callback,
            smartbox_state_callback,
        )

    def subscribe_to_attributes(self: _PasdBusProxy) -> None:
        """Subscribe to attributes relating to this FNDH."""
        assert self._proxy is not None
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self.pasd_device)
        for attribute in subscriptions:
            if attribute not in self._proxy._change_event_subscription_ids.keys():
                self.logger.info(f"subscribing to attribute {attribute}.....")
                self._proxy.add_change_event_callback(
                    attribute, self._on_attribute_change
                )

    def _on_attribute_change(
        self: _PasdBusProxy,
        attr_name: str,
        attr_value: Any,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle attribute change event.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        is_a_fndh = re.search("^fndh", attr_name)

        if is_a_fndh:
            tango_attribute_name = attr_name[is_a_fndh.end() :].lower()
            if tango_attribute_name.lower() == "portspowersensed":

                def get_power_state(powerstate: bool) -> PowerState:
                    if powerstate:
                        return PowerState.ON
                    return PowerState.OFF

                power_states = map(get_power_state, attr_value)

                self._update_port_power_states(list(power_states))

            if tango_attribute_name.lower() == "status":
                tango_attribute_name = "pasdstatus"

            self._attribute_change_callback(tango_attribute_name, attr_value)
            return

        self.logger.info(
            f"""Attribute subscription {attr_name} does not seem to begin
             with 'fndh' string so it is assumed it is a incorrect subscription"""
        )


# pylint: disable-next=abstract-method
class FndhComponentManager(TaskExecutorComponentManager):
    """
    A component manager for an fndh.

    This communicates via a proxy to a MccsPasdBus that talks to a simulator
    or the real hardware.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self: FndhComponentManager,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        update_port_power_states: Callable[..., None],
        pasd_fqdn: str,
        _pasd_bus_proxy: Optional[MccsDeviceProxy] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_callback: callback to be
            called when the component state changes
        :param attribute_change_callback: callback to be
            called when a attribute changes
        :param update_port_power_states: callback to be
            called when the power state changes.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
            purposes only. defaults to None
        """
        self._component_state_callback = component_state_callback
        self._attribute_change_callback = attribute_change_callback
        self._update_port_power_states = update_port_power_states
        self._pasd_fqdn = pasd_fqdn

        self._pasd_bus_proxy = _pasd_bus_proxy or _PasdBusProxy(
            pasd_fqdn,
            logger,
            self._pasdbus_communication_state_changed,
            functools.partial(component_state_callback, fqdn=self._pasd_fqdn),
            attribute_change_callback,
            update_port_power_states,
        )
        self.logger = logger
        self._pasd_device_number = 0
        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
            max_workers=1,
            power=None,
            fault=None,
            pasdbus_status=None,
        )

    def _pasdbus_communication_state_changed(
        self: FndhComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._pasd_bus_proxy.subscribe_to_attributes()

        self._update_communication_state(communication_state)

    def start_communicating(self: FndhComponentManager) -> None:  # noqa: C901
        """Establish communication with the pasdBus via a proxy."""
        self._pasd_bus_proxy.start_communicating()

    def stop_communicating(self: FndhComponentManager) -> None:
        """Break off communication with the pasdBus."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._pasd_bus_proxy.stop_communicating()
        self._update_component_state(power=None, fault=None)

    @check_communicating
    def on(
        self: FndhComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn on the FNDH.

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
        Turn off the FNDH.

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
        Turn a port off.

        This port may or may not have a smartbox attached.

        :param port_number: port we want to power off.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._power_off_port,  # type: ignore[arg-type]
            args=[port_number],
            task_callback=task_callback,
        )

    def _power_off_port(
        self: FndhComponentManager,
        port_number: str,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            assert self._pasd_bus_proxy._proxy
            (
                [result_code],
                [return_message],
            ) = self._pasd_bus_proxy._proxy.TurnFndhPortOff(port_number)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {repr(ex)}")
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
        Turn a port on.

        This port may or may not have a smartbox attached.

        :param port_number: port we want to power on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._power_on_port,  # type: ignore[arg-type]
            args=[
                port_number,
            ],
            task_callback=task_callback,
        )

    def _power_on_port(
        self: FndhComponentManager,
        port_number: str,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            assert self._pasd_bus_proxy._proxy
            json_argument = json.dumps(
                {"port_number": port_number, "stay_on_when_offline": True}
            )
            ([result_code], [unique_id]) = self._pasd_bus_proxy._proxy.TurnFndhPortOn(
                json_argument
            )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {repr(ex)}")
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
