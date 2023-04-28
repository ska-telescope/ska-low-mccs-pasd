#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for fndh."""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

__all__ = ["FndhComponentManager"]


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
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        update_port_power_states: Callable[..., None],
        pasd_fqdn: str,
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
        :param attribute_change_callback: callback to be
            called when a attribute changes
        :param update_port_power_states: callback to be
            called when the power state changes.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
            purposes only. defaults to None
        """
        super().__init__(
            logger,
            communication_state_changed_callback,
            component_state_changed_callback,
            max_workers=1,
            power=None,
            fault=None,
            pasdbus_status=None,
        )
        self._component_state_changed_callback = component_state_changed_callback
        self._attribute_change_callback = attribute_change_callback
        self._update_port_power_states = update_port_power_states
        self._pasd_fqdn = pasd_fqdn
        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self.logger = logger
        self._pasd_device_number = 0

    def _subscribe_to_attributes(
        self: FndhComponentManager, subscriptions: dict[str, Callable]
    ) -> None:
        """
        Subscribe to attributes.

        :param subscriptions: a dictionary containing the name of the attribute
            and its callback.
        """
        assert self._pasd_bus_proxy

        for attribute in subscriptions:
            self._pasd_bus_proxy.add_change_event_callback(
                attribute, subscriptions[attribute]
            )

    def start_communicating(self: FndhComponentManager) -> None:
        """
        Establish communication with the pasdBus via a proxy.

        This is responsible for:
            - Forming a proxy to MccsPasdBus.
            - Subscribing to attributes of interest.
            - Updating the initial state of the FNDH.
            - Updating the communication state of the FNDH.
        """
        if self._pasd_bus_proxy is None:
            try:
                self.logger.info(f"attempting to form proxy with {self._pasd_fqdn}")

                self._pasd_bus_proxy = MccsDeviceProxy(
                    self._pasd_fqdn, self.logger, connect=True
                )
            except Exception as e:  # pylint: disable=broad-except
                self._component_state_changed_callback(fault=True)
                self.logger.error("Caught exception in forming proxy: %s", e)
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                return

        try:
            subscription_keys = self._pasd_bus_proxy.GetPasdDeviceSubscriptions(
                self._pasd_device_number
            )
            subscriptions = dict.fromkeys(subscription_keys, self._handle_change_event)
            subscriptions.update({"healthstate": self._pasd_health_state_changed})
            self._subscribe_to_attributes(subscriptions)

        except Exception as e:  # pylint: disable=broad-except
            self._component_state_changed_callback(fault=True)
            self.logger.error("Caught exception in attribute subscriptions: %s", e)
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            return

        try:
            if self.communication_state != CommunicationStatus.ESTABLISHED:
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                self._pasd_bus_proxy.ping()
                # TODO: Check the pasd_bus is communicating.
                # here we just assume it is.
                self._update_communication_state(CommunicationStatus.ESTABLISHED)
                # Check the ports on the fndh for power.
                if any(self._pasd_bus_proxy.fndhPortsPowerSensed):  # type: ignore
                    self._component_state_changed_callback(power=PowerState.ON)
                else:
                    self._component_state_changed_callback(power=PowerState.OFF)

        except Exception as e:  # pylint: disable=broad-except
            self._component_state_changed_callback(fault=True)
            self.logger.error("Caught exception in start_communicating: %s", e)
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            return

    def _handle_change_event(
        self: FndhComponentManager,
        attr_name: str,
        attr_value: Any,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle changes to subscribed attributes.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        # TODO: This is called with a uppercase during initial subscription and
        # with lowercase for push_change_events. Update the MccsDeviceProxy to fix
        # this.

        # Check if we are really receiving from a pasd fndh device.
        is_a_fndh = re.search("^fndh", attr_name)

        if is_a_fndh:
            attribute = attr_name[is_a_fndh.end() :].lower()
            if attribute.lower() == "portspowersensed":
                self._port_power_state_change(attribute, attr_value, attr_quality)
            self._attribute_change_callback(attribute, attr_value)
            return

        self.logger.info(
            f"""Attribute subscription {attr_name} does not seem to begin
             with 'fndh' string so it is assumed it is a incorrect subscription"""
        )
        return

    def _pasd_health_state_changed(
        self: FndhComponentManager,
        attr_name: str,
        attr_value: Any,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Pasdbus health state callback.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        self.logger.info(f"The health state of the pasdBus has changed to {attr_value}")
        self._component_state_changed_callback(pasdbus_status=attr_value)

    def _port_power_state_change(
        self: FndhComponentManager,
        event_name: str,
        port_power_states: list[bool],
        event_quality: tango.AttrQuality,
    ) -> None:
        """
        Power state callback.

        :param event_name: The event_name
        :param port_power_states: The port_power_states
        :param event_quality: The event_quality
        """

        def get_power_state(powerstate: bool) -> PowerState:
            if powerstate:
                return PowerState.ON
            return PowerState.OFF

        power_states = map(get_power_state, port_power_states)

        self._update_port_power_states(list(power_states))

    def stop_communicating(self: FndhComponentManager) -> None:
        """Break off communication with the pasdBus."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return

        self._update_communication_state(CommunicationStatus.DISABLED)
        self._component_state_changed_callback(power=None, fault=None)

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
            self._power_off_port,
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
            assert self._pasd_bus_proxy
            ([result_code], [return_message]) = self._pasd_bus_proxy.TurnFndhPortOff(
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
        Turn a port on.

        This port may or may not have a smartbox attached.

        :param port_number: port we want to power on.
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
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            assert self._pasd_bus_proxy
            json_argument = json.dumps(
                {"port_number": port_number, "stay_on_when_offline": True}
            )
            ([result_code], [unique_id]) = self._pasd_bus_proxy.TurnFndhPortOn(
                json_argument
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

    def is_port_on(self: FndhComponentManager, port_number: int) -> bool:
        """
        Check the power for a port.

        :param port_number: The port of interest.

        :return: True if the port is on.
        """
        assert self._pasd_bus_proxy
        return self._pasd_bus_proxy.fndhPortsPowerSensed[port_number]  # type: ignore
