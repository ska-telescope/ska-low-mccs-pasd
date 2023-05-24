#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for smartbox."""
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

__all__ = ["SmartBoxComponentManager"]


class Port:
    """A instance of a Smartbox Port."""

    def __init__(
        self,
        component_manager: TaskExecutorComponentManager,
        port_id: int,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param port_id: the port id
        :param component_manager: the component_manager
        :param logger: a logger for this object to use
        """
        self.logger = logger
        self._port_id = port_id
        self._component_manager = component_manager

        self.desire_on = False
        self._task_callback = None

    def set_desire_on(self, task_callback: Optional[Callable]) -> None:
        """
        Desire the port to be turned on when the smartbox becomes online.

        :param task_callback: the command_tracker callback
            for this command.
        """
        self.logger.info("Port desired on. To be turned on when smartbox is on.")
        self.desire_on = True
        self._task_callback = task_callback  # type: ignore[assignment]

    def turn_on(self, task_callback: Optional[Callable] = None) -> None:
        """
        Turn the port on.

        :param task_callback: the command_tracker callback
            for this command.
        """
        self.logger.info(f"Turning on Power to port {self._port_id}.......")
        assert self._task_callback or task_callback, (
            "We need task callback inorder to " "keep track of command status"
        )
        if task_callback is not None:
            self._component_manager.turn_on_port(  # type: ignore[attr-defined]
                self._port_id, task_callback
            )
        else:
            self._component_manager.turn_on_port(  # type: ignore[attr-defined]
                self._port_id, self._task_callback
            )
        self.desire_on = False
        self._task_callback = None


# pylint: disable-next=abstract-method
class SmartBoxComponentManager(
    TaskExecutorComponentManager
):  # pylint: disable=too-many-instance-attributes
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
        attribute_change_callback: Callable[..., None],
        port_count: int,
        fndh_port: int,
        pasd_fqdn: str,
        fndh_fqdn: str,
        smartbox_number: Optional[int] = None,
        _pasd_bus_proxy: Optional[MccsDeviceProxy] = None,
        _fndh_bus_proxy: Optional[MccsDeviceProxy] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param communication_state_changed_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed_callback: callback to be
            called when the component state changes
        :param attribute_change_callback: callback to be called when a attribute
            of interest changes.
        :param port_count: the number of smartbox ports.
        :param fndh_port: the fndh port this smartbox is attached.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param fndh_fqdn: the fqdn of the fndh to connect to.
        :param smartbox_number: the number assigned to this smartbox by station.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
        :param _fndh_bus_proxy: a optional injected device proxy for testing

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
        self._pasd_fqdn = pasd_fqdn
        self._fndh_fqdn = fndh_fqdn
        self.smartbox_number = smartbox_number
        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self._fndh_proxy: Optional[MccsDeviceProxy] = _fndh_bus_proxy
        self._fndh_port = fndh_port
        self.logger = logger
        self.ports = [Port(self, port, logger) for port in range(1, port_count + 1)]
        self.power_state = PowerState.UNKNOWN

    def _subscribe_to_attributes(self: SmartBoxComponentManager) -> None:
        """Subscribe to attributes on the MccsPasdBus."""
        assert self._pasd_bus_proxy
        assert self._fndh_proxy
        assert self._fndh_port is not None
        # ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._pasd_bus_proxy.GetPasdDeviceSubscriptions(
            self.smartbox_number
        )
        for attribute in subscriptions:
            self._pasd_bus_proxy.add_change_event_callback(
                attribute, self._handle_change_event
            )
        if (
            f"port{self._fndh_port}powerstate"
            not in self._fndh_proxy._change_event_subscription_ids.keys()
        ):
            self._fndh_proxy.add_change_event_callback(
                f"Port{self._fndh_port}PowerState", self._power_state_change
            )

        if (
            "healthstate"
            not in self._pasd_bus_proxy._change_event_subscription_ids.keys()
        ):
            self._pasd_bus_proxy.add_change_event_callback(
                "healthstate", self._pasd_health_state_changed
            )

    def _evaluate_power_state(self: SmartBoxComponentManager) -> None:
        """
        Evaluate the power state.

        This turns on any ports that are desired on.
        """
        assert self._fndh_proxy
        assert self._fndh_port

        my_power = getattr(self._fndh_proxy, f"Port{self._fndh_port}PowerState")
        self.power_state = my_power
        if my_power == PowerState.ON:
            for port in self.ports:
                if port.desire_on:
                    port.turn_on()
        self._component_state_changed_callback(power=my_power)

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """
        Establish communication with the pasdBus via a proxy.

        This checks:
            - A proxy can be formed with the MccsPasdBus
            - We can subscribe to attributes of interest.
            - The power state of the Smartbox

        TODO: refactor!
        """
        # ------------------------------------
        # FORM PROXY / SUBSCRIBE TO ATTRIBUTES
        # ------------------------------------
        if None in [self._pasd_bus_proxy, self._fndh_proxy]:
            try:
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                self.logger.info(
                    f"attempting to form proxy with {self._pasd_fqdn} {self._fndh_fqdn}"
                )
                self._pasd_bus_proxy = MccsDeviceProxy(
                    self._pasd_fqdn, self.logger, connect=True
                )
                self._fndh_proxy = MccsDeviceProxy(
                    self._fndh_fqdn, self.logger, connect=True
                )
            except Exception as e:  # pylint: disable=broad-except
                self._update_component_state(power=PowerState.UNKNOWN)
                self.logger.error("Caught exception in start_communicating: %s", e)

        try:
            assert self._pasd_bus_proxy
            assert self._fndh_proxy
            assert self._fndh_port is not None
            if self.communication_state != CommunicationStatus.ESTABLISHED:
                self._update_communication_state(CommunicationStatus.ESTABLISHED)
            # Ask the MccsPasdBus what attributes we should subscribe.
            self._subscribe_to_attributes()
        except Exception as e:  # pylint: disable=broad-except
            self._update_component_state(power=PowerState.UNKNOWN)
            self.logger.error("Caught exception in attribute subscriptions: %s", e)
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

        # ------------
        # UPDATE STATE
        # ------------
        try:
            self._evaluate_power_state()

        except Exception as e:  # pylint: disable=broad-except
            self._update_component_state(fault=True)
            self.logger.error("Caught exception in start_communicating: %s", e)
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
            return

        self.logger.info("communication established")

    def _handle_change_event(
        self: SmartBoxComponentManager,
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
        # TODO: MCCS-1481: Update the MccsDeviceProxy to push attribute case.

        # Check if we are really receiving from a pasd smartbox device between 1-25
        is_a_smartbox = re.search("^smartbox[1-2][1-5]|[1-9]", attr_name)

        if is_a_smartbox:
            attribute = attr_name[is_a_smartbox.end() :].lower()
            self._attribute_change_callback(attribute, attr_value)
            return

        self.logger.info(
            f"""Attribute subscription {attr_name} does not seem to begin
             with 'smartbox' string so it is assumed it is a incorrect subscription"""
        )
        return

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
        try:
            assert event_name.lower() == "healthstate"
        except AssertionError:
            self.logger.debug(
                f"""callback called with unexpected
            attribute expected healthstate got {event_name}"""
            )
            return
        self._component_state_changed_callback(pasdbus_status=event_value)

    def _power_state_change(
        self: SmartBoxComponentManager,
        event_name: str,
        power_state: PowerState,
        event_quality: tango.AttrQuality,
    ) -> None:
        """
        Pasdbus health state callback.

        :param event_name: The event_name
        :param power_state: The powerstate of the port.
        :param event_quality: The event_quality
        """
        # TODO: MCCS-1485 - allow unsubscribe event, this will mean will will not need
        # this if statement. Since when
        if event_name.lower() == f"port{self._fndh_port}powerstate":
            self._evaluate_power_state()
        else:
            return

    def stop_communicating(self: SmartBoxComponentManager) -> None:
        """Break off communication with the pasdBus."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._fndh_proxy = None
        self._pasd_bus_proxy = None
        self._update_communication_state(CommunicationStatus.DISABLED)
        self._update_component_state(power=None, fault=None)

    @check_communicating
    def on(
        self: SmartBoxComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox on.

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
            if self._fndh_port:
                if self._pasd_bus_proxy is None:
                    raise ValueError(f"Power on smartbox '{self._fndh_port} failed'")
                json_argument = json.dumps(
                    {"port_number": self._fndh_port, "stay_on_when_offline": True}
                )
                ([result_code], [return_message]) = self._pasd_bus_proxy.TurnFndhPortOn(
                    json_argument
                )
            else:
                self.logger.info(
                    "Cannot turn off SmartBox, we do not yet know what port it is on"
                )
                raise ValueError("cannot turn on Unknown FNDH port.")

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"{ex}",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on smartbox '{self._fndh_port}  success'",
            )
        return result_code, return_message

    @check_communicating
    def off(
        self: SmartBoxComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox off.

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
            if self._fndh_port:
                if self._pasd_bus_proxy is None:
                    raise ValueError(f"Power off smartbox '{self._fndh_port} failed'")

                (
                    [result_code],
                    [return_message],
                ) = self._pasd_bus_proxy.TurnFndhPortOff(self._fndh_port)
            else:
                self.logger.info(
                    "Cannot turn off SmartBox, we do not yet know what port it is on"
                )
                raise ValueError("cannot turn off Unknown FNDH port.")

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"{ex}",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power off smartbox '{self._fndh_port}  success'",
            )
        return result_code, return_message

    @check_communicating
    def turn_off_port(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Port off.

        This may or may not have a Antenna attached.

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
        port_number: str,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")
            json_argument = json.dumps(
                {"smartbox_number": self._fndh_port, "port_number": port_number}
            )
            (
                [result_code],
                [return_message],
            ) = self._pasd_bus_proxy.TurnSmartboxPortOff(json_argument)

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
    def turn_on_port(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a port on.

        This may or may not have a Antenna attached.

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
        port_number: int,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")
            port = self.ports[port_number - 1]
            # Turn smartbox on if not already.
            if self.power_state != PowerState.ON:
                assert port._port_id == port_number
                port.set_desire_on(task_callback)  # type: ignore[assignment]
                self.on()
                return (
                    ResultCode.STARTED,
                    "The command will continue when the smartbox turns on.",
                )
            json_argument = json.dumps(
                {
                    "smartbox_number": self._fndh_port,
                    "port_number": port_number,
                    "stay_on_when_offline": True,
                }
            )

            (
                [result_code],
                [return_message],
            ) = self._pasd_bus_proxy.TurnSmartboxPortOn(json_argument)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power on port '{port_number} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            self.logger.info(f"Port {port_number} turned on!")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on port '{port_number} success'",
            )
        return result_code, return_message
