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
class FndhComponentManager(
    TaskExecutorComponentManager
):  # pylint: disable=too-many-instance-attributes
    """
    A component manager for an fndh.

    This communicates via a proxy to a MccsPadsBus that talks to a simulator
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
        self._attribute_change_callback = attribute_change_callback
        self._update_port_power_states = update_port_power_states
        self._pasd_fqdn = pasd_fqdn
        self.fndh_number = 1  # TODO: this should a property set during device setup
        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self.logger = logger
        self._pasd_device_number = 0

    def _subscribe_to_attributes(self: FndhComponentManager) -> None:
        """Subscribe to attributes on the MccsPasdBus."""
        assert self._pasd_bus_proxy

        # ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._pasd_bus_proxy.GetPasdDeviceSubscriptions(
            self._pasd_device_number
        )
        for attribute in subscriptions:
            self._pasd_bus_proxy.add_change_event_callback(
                attribute, self._handle_change_event
            )

        if (
            "healthstate"
            not in self._pasd_bus_proxy._change_event_subscription_ids.keys()
        ):
            self._pasd_bus_proxy.add_change_event_callback(
                "healthstate", self._pasd_health_state_changed
            )

        if (
            "fndhPortsPowerSensed"
            not in self._pasd_bus_proxy._change_event_subscription_ids.keys()
        ):
            self._pasd_bus_proxy.add_change_event_callback(
                "fndhPortsPowerSensed", self._port_power_state_change
            )

    def start_communicating(self: FndhComponentManager) -> None:
        """
        Establish communication with the pasdBus via a proxy.

        This checks:
            - A proxy can be formed with the MccsPasdBus
            - We can subscribe to the attribes suggested by the
                pasd bus
            - Update the initial state of the FNDH.
        """
        # Form proxy if not done yet.
        if self._pasd_bus_proxy is None:
            try:
                self.logger.info(f"attempting to form proxy with {self._pasd_fqdn}")

                self._pasd_bus_proxy = MccsDeviceProxy(
                    self._pasd_fqdn, self.logger, connect=True
                )
            except Exception as e:  # pylint: disable=broad-except
                self._update_component_state(fault=True)
                self.logger.error("Caught exception in start_communicating: %s", e)
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                return

        try:
            # Ask the MccsPasdBus what attributes we should subscribe.
            self._subscribe_to_attributes()
        except Exception as e:  # pylint: disable=broad-except
            self._update_component_state(fault=True)
            self.logger.error("Caught exception in attribute subscriptios: %s", e)
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            return

        try:
            # If we are not established attempt for establish communication.
            if self.communication_state != CommunicationStatus.ESTABLISHED:
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                # first check the proxy is reachable
                self._pasd_bus_proxy.ping()
                # TODO: then check the pasd_bus is communicating.
                # here we just assume it is.
                self._update_communication_state(CommunicationStatus.ESTABLISHED)
                # Check the ports on the fndh for power.
                if any(self._pasd_bus_proxy.fndhPortsPowerSensed):  # type: ignore
                    self._update_component_state(power=PowerState.ON)
                else:
                    self._update_component_state(power=PowerState.OFF)

        except Exception as e:  # pylint: disable=broad-except
            self._update_component_state(fault=True)
            self.logger.error("Caught exception in start_communicating: %s", e)
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            return

    def _handle_change_event(
        self: FndhComponentManager,
        attr_name: str,
        attr_value: HealthState,
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
            self._attribute_change_callback(attribute, attr_value)
            return

        self.logger.info(
            f"""Attribute subscription {attr_name} does not seem to begin
             with 'fndh' string so it is assumed it is a incorrect subscription"""
        )
        return

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

    def _port_power_state_change(
        self: FndhComponentManager,
        event_name: str,
        port_power_states: list[bool],
        event_quality: tango.AttrQuality,
    ) -> None:
        """
        Pasdbus health state callback.

        :param event_name: The event_name
        :param port_power_states: The port_power_states
        :param event_quality: The event_quality
        """
        try:
            assert event_name.lower() == "fndhportspowersensed"
        except AssertionError:
            self.logger.debug(
                f"""callback called with unexpected
            attribute expected fndhportspowersensed got {event_name}"""
            )
            return

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
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

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
            if self._pasd_bus_proxy is None:
                raise ValueError("pasd_bus_proxy is None")
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
        Turn a Smartbox off.

        :param port_number: The logical id of the port.

        :return: The power state of the requested port.
        """
        assert self._pasd_bus_proxy
        return self._pasd_bus_proxy.fndhPortsPowerSensed[port_number]  # type: ignore
