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
from typing import Any, Callable, Optional

import tango
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    TaskStatus,
)
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import (
    DeviceComponentManager,
    check_communicating,
)
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

__all__ = ["SmartBoxComponentManager"]


class Port:
    """A instance of a Smartbox Port."""

    def __init__(
        self,
        power_on_callback: Callable[..., Any],
        port_id: int,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param port_id: the port id
        :param power_on_callback: a callback hook to turn ON this port.
        :param logger: a logger for this object to use
        """
        self.logger = logger
        self._port_id = port_id
        self._power_on_callback = power_on_callback

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

        command_tracker = next(
            item for item in [task_callback, self._task_callback] if item is not None
        )
        self._power_on_callback(  # type: ignore[attr-defined]
            self._port_id, command_tracker
        )

        self.desire_on = False
        self._task_callback = None


class _SmartBoxProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus specific to this smartbox."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _SmartBoxProxy,
        fqdn: str,
        fndh_port: int,
        logger: logging.Logger,
        max_workers: int,
        smartbox_communication_state_changed_callback: Callable[
            [CommunicationStatus], None
        ],
        smartbox_state_changed_callback: Callable[[dict[str, Any]], None],
        attribute_change_callback: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the Tile device
        :param fndh_port: this FNDH port this smartbox is attached to.
        :param logger: the logger to be used by this object.
        :param max_workers: the maximum worker threads for the slow commands
            associated with this component manager.
        :param smartbox_communication_state_changed_callback: callback to be
            called when the status of the communications change.
        :param smartbox_state_changed_callback: callback to be called when the
            component state changes
        :param attribute_change_callback: callback for when a attribute relevant to
            this smartbox changes.
        """
        self._attribute_change_callback = attribute_change_callback
        self._fndh_port = fndh_port
        assert (
            0 < fndh_port < 29
        ), "The smartbox must be attached to a valid FNDH port in range (1-28)"
        super().__init__(
            fqdn,
            logger,
            max_workers,
            smartbox_communication_state_changed_callback,
            smartbox_state_changed_callback,
        )

    def _subscribe_to_attributes(self: _SmartBoxProxy) -> None:
        """Subscribe to attributes relating to this SmartBox."""
        assert self._proxy is not None
        # Ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self._fndh_port)
        for attribute in subscriptions:
            self._proxy.add_change_event_callback(attribute, self._on_attribute_change)

    def _on_attribute_change(
        self: _SmartBoxProxy,
        attr_name: str,
        attr_value: HealthState,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle attribute change.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        # TODO: MCCS-1481: Update the MccsDeviceProxy to conserve attribute case.

        # Are really receiving from a pasd smartbox device between 1-25
        is_a_smartbox = re.search("^smartbox[1-2][1-5]|[1-9]", attr_name)

        if is_a_smartbox:
            attribute = attr_name[is_a_smartbox.end() :].lower()
            self._attribute_change_callback(attribute, attr_value)
            return

        self.logger.error(
            f"""Attribute subscription {attr_name} does not seem to begin
             with 'smartbox' string so it is not handled."""
        )
        return

    def turn_smartbox_port_on(
        self: _SmartBoxProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the TurnSmartboxPortOn command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        return self._proxy.TurnSmartboxPortOn(json_argument)

    def turn_smartbox_port_off(
        self: _SmartBoxProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the TurnSmartboxPortOff command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        return self._proxy.TurnSmartboxPortOff(json_argument)

    def turn_fndh_port_off(
        self: _SmartBoxProxy, port_number: int
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the TurnFndhPortOff command.

        :param port_number: the port_number formatted to turn off.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        return self._proxy.TurnFndhPortOff(port_number)

    def turn_fndh_port_on(
        self: _SmartBoxProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the TurnFndhPortOn command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        return self._proxy.TurnFndhPortOn(json_argument)


class _FndhProxy(DeviceComponentManager):
    """A proxy to the SmartBox's FNDH via pasdbus."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _FndhProxy,
        fqdn: str,
        fndh_port: int,
        logger: logging.Logger,
        max_workers: int,
        fndh_communication_state_changed_callback: Callable[
            [CommunicationStatus], None
        ],
        fndh_state_changed_callback: Callable[[dict[str, Any]], None],
        port_power_changed_callback: Callable[[str, Any, Any], None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the Tile device
        :param fndh_port: this FNDH port this smartbox is attached to.
        :param logger: the logger to be used by this object.
        :param max_workers: the maximum worker threads for the slow commands
            associated with this component manager.
        :param fndh_communication_state_changed_callback: callback to be
            called when the status of the communications change.
        :param fndh_state_changed_callback: callback to be called when the
            component state changes
        :param port_power_changed_callback: callback for when the
            power delivered to this device changes.
        """
        self._fndh_port = fndh_port
        self._port_power_changed_callback = port_power_changed_callback

        assert (
            0 < fndh_port < 29
        ), "The smartbox must be attached to a valid FNDH port in range (1-28)"
        super().__init__(
            fqdn,
            logger,
            max_workers,
            fndh_communication_state_changed_callback,
            fndh_state_changed_callback,
        )

    def _subscribe_to_attributes(self: _FndhProxy) -> None:
        """Subscribe to power state of this SmartBox's port."""
        assert self._proxy is not None
        if (
            f"port{self._fndh_port}powerstate"
            not in self._proxy._change_event_subscription_ids.keys()
        ):
            self._proxy.add_change_event_callback(
                f"Port{self._fndh_port}PowerState", self._port_power_changed_callback
            )


# pylint: disable-next=abstract-method
class SmartBoxComponentManager(
    TaskExecutorComponentManager
):  # pylint: disable=too-many-instance-attributes
    """
    A component manager for MccsSmartBox.

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
        _smartbox_proxy: Optional[MccsDeviceProxy] = None,
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
        :param _smartbox_proxy: a optional injected device proxy for testing
        :param _fndh_bus_proxy: a optional injected device proxy for testing
            purposes only. defaults to None
        """
        max_workers = 1

        self._smartbox_proxy = _smartbox_proxy or _SmartBoxProxy(
            pasd_fqdn,
            fndh_port,
            logger,
            max_workers,
            self._smartbox_communication_state_changed,
            self._pasdbus_state_changed,
            attribute_change_callback,
        )
        self._fndh_proxy = _fndh_bus_proxy or _FndhProxy(
            fndh_fqdn,
            fndh_port,
            logger,
            max_workers,
            self._fndh_communication_state_changed,
            self._fndh_state_changed,
            self._power_state_change,
        )
        self._fndh_communication_state = CommunicationStatus.NOT_ESTABLISHED
        self._pasd_communication_state = CommunicationStatus.NOT_ESTABLISHED
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
        self._pasd_fqdn = pasd_fqdn
        self._fndh_fqdn = fndh_fqdn
        self.logger = logger
        self.ports = [
            Port(self.turn_on_port, port, logger) for port in range(1, port_count + 1)
        ]
        self.power_state = PowerState.UNKNOWN
        self._fndh_port = fndh_port

    def _pasdbus_state_changed(
        self: SmartBoxComponentManager, state_change: dict[str, Any]
    ) -> None:
        self._component_state_changed_callback(**state_change, fqdn=self._pasd_fqdn)

    def _fndh_state_changed(
        self: SmartBoxComponentManager, state_change: dict[str, Any]
    ) -> None:
        self._component_state_changed_callback(**state_change, fqdn=self._fndh_fqdn)

    def _smartbox_communication_state_changed(
        self: SmartBoxComponentManager, communication_state: CommunicationStatus
    ) -> None:
        self._pasd_communication_state = communication_state
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._smartbox_proxy._subscribe_to_attributes()
        # Only update state on change.
        if communication_state != self._communication_state:
            self.update_device_communication_state()

    def _fndh_communication_state_changed(
        self: SmartBoxComponentManager, communication_state: CommunicationStatus
    ) -> None:
        self._fndh_communication_state = communication_state
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._fndh_proxy._subscribe_to_attributes()
        # Only update state on change.
        if communication_state != self._communication_state:
            self.update_device_communication_state()

    def update_device_communication_state(self: SmartBoxComponentManager) -> None:
        """
        Update the communication state.

        :return: none
        """
        # TODO: We may want a more complex evaluation of communication state.
        for communication_state in [
            CommunicationStatus.DISABLED,
            CommunicationStatus.ESTABLISHED,
        ]:
            if (
                self._fndh_communication_state == communication_state
                and self._pasd_communication_state == communication_state
            ):
                self._update_communication_state(communication_state)
                return
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """Establish communication."""
        self._smartbox_proxy.start_communicating()
        self._fndh_proxy.start_communicating()

    def _power_state_change(
        self: SmartBoxComponentManager,
        event_name: str,
        power_state: PowerState,
        event_quality: Optional[tango.AttrQuality] = None,
    ) -> None:
        """
        Power change reported.

        :param event_name: The event_name
        :param power_state: The powerstate of the port.
        :param event_quality: The event_quality
        """
        if event_name.lower() == f"port{self._fndh_port}powerstate":
            self.power_state = power_state
            # Turn on any pending ports
            if self.power_state == PowerState.ON:
                for port in self.ports:
                    if port.desire_on:
                        port.turn_on()

            self._component_state_changed_callback(power=self.power_state)
        else:
            return

    def stop_communicating(self: SmartBoxComponentManager) -> None:
        """Stop communication with components under control."""
        self._smartbox_proxy.stop_communicating()
        self._fndh_proxy.stop_communicating()

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
                if self._smartbox_proxy is None:
                    raise ValueError(f"Power on smartbox '{self._fndh_port} failed'")
                json_argument = json.dumps(
                    {"port_number": self._fndh_port, "stay_on_when_offline": True}
                )
                (
                    result_code,
                    return_message,
                ) = self._smartbox_proxy.turn_fndh_port_on(json_argument)
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
                if self._smartbox_proxy is None:
                    raise ValueError(f"Power off smartbox '{self._fndh_port} failed'")

                (
                    result_code,
                    return_message,
                ) = self._smartbox_proxy.turn_fndh_port_off(self._fndh_port)
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
            if self._smartbox_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")
            json_argument = json.dumps(
                {"smartbox_number": self._fndh_port, "port_number": port_number}
            )
            (
                result_code,
                return_message,
            ) = self._smartbox_proxy.turn_smartbox_port_off(json_argument)

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
            if self._smartbox_proxy is None:
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
                result_code,
                return_message,
            ) = self._smartbox_proxy.turn_smartbox_port_on(json_argument)

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
