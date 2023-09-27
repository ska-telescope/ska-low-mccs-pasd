#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for smartbox."""
from __future__ import annotations

import functools
import json
import logging
import re
import threading
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus, HealthState, PowerState, TaskStatus
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

__all__ = ["SmartBoxComponentManager"]


class _PasdBusProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus specific to this smartbox."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _PasdBusProxy,
        fqdn: str,
        fndh_port: int,
        logger: logging.Logger,
        max_workers: int,
        smartbox_communication_state_callback: Callable[[CommunicationStatus], None],
        smartbox_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the PasdBus device
        :param fndh_port: The FNDH port this smartbox is attached to.
        :param logger: the logger to be used by this object.
        :param max_workers: the maximum worker threads for the slow commands
            associated with this component manager.
        :param smartbox_communication_state_callback: callback to be
            called when the status of the communications change.
        :param smartbox_state_callback: callback to be called when the
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
            smartbox_communication_state_callback,
            smartbox_state_callback,
        )

    def subscribe_to_attributes(self: _PasdBusProxy) -> None:
        """Subscribe to attributes relating to this SmartBox."""
        assert self._proxy is not None  # type checker
        # Ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self._fndh_port)
        for attribute in subscriptions:
            if attribute not in self._proxy._change_event_subscription_ids.keys():
                self._proxy.add_change_event_callback(
                    attribute, self._on_attribute_change
                )

    def _on_attribute_change(
        self: _PasdBusProxy,
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

        # Are really receiving from a pasd smartbox device between 1-24
        is_a_smartbox = re.search("^smartbox([1-9]|1[0-9]|2[0-4])", attr_name)

        if is_a_smartbox:
            tango_attribute_name = attr_name[is_a_smartbox.end() :].lower()

            # Status is a bad name since it conflicts with TANGO status.
            if tango_attribute_name.lower() == "status":
                tango_attribute_name = "pasdstatus"

            self._attribute_change_callback(tango_attribute_name, attr_value)
            return

        self.logger.error(
            f"Attribute subscription {attr_name} does not seem to begin",
            "with 'smartbox' string so it is not handled.",
        )
        return

    def turn_smartbox_port_on(
        self: _PasdBusProxy, json_argument: str
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
        self: _PasdBusProxy, json_argument: str
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
        self: _PasdBusProxy, port_number: int
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
        self: _PasdBusProxy, json_argument: str
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
    """A proxy to the pasd FNDH device."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _FndhProxy,
        fqdn: str,
        fndh_port: int,
        logger: logging.Logger,
        max_workers: int,
        fndh_communication_state_callback: Callable[[CommunicationStatus], None],
        fndh_state_callback: Callable[..., None],
        port_power_callback: Callable[[str, Any, Any], None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the Tile device
        :param fndh_port: this FNDH port this smartbox is attached to.
        :param logger: the logger to be used by this object.
        :param max_workers: the maximum worker threads for the slow commands
            associated with this component manager.
        :param fndh_communication_state_callback: callback to be
            called when the status of the communications change.
        :param fndh_state_callback: callback to be called when the
            component state changes
        :param port_power_callback: callback for when the
            power delivered to this device changes.
        """
        self._fndh_port = fndh_port
        self._port_power_callback = port_power_callback

        assert (
            0 < fndh_port < 29
        ), "The smartbox must be attached to a valid FNDH port in range (1-28)"
        super().__init__(
            fqdn,
            logger,
            max_workers,
            fndh_communication_state_callback,
            fndh_state_callback,
        )

    def subscribe_to_attributes(self: _FndhProxy) -> None:
        """Subscribe to power state of this SmartBox's port."""
        assert self._proxy is not None
        if (
            f"port{self._fndh_port}powerstate"
            not in self._proxy._change_event_subscription_ids.keys()
        ):
            self._proxy.add_change_event_callback(
                f"Port{self._fndh_port}PowerState", self._port_power_callback
            )


# pylint: disable-next=abstract-method
class SmartBoxComponentManager(
    TaskExecutorComponentManager
):  # pylint: disable=too-many-instance-attributes
    """
    A component manager for MccsSmartBox.

    This communicates with system under control
    via a proxy to the ``MccsPasdBus`` and ``MccsFndh``.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self: SmartBoxComponentManager,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        port_count: int,
        fndh_port: int,
        pasd_fqdn: str,
        fndh_fqdn: str,
        _pasd_bus_proxy: Optional[MccsDeviceProxy] = None,
        _fndh_bus_proxy: Optional[MccsDeviceProxy] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_callback: callback to be
            called when the component state changes
        :param attribute_change_callback: callback to be called when a attribute
            of interest changes.
        :param port_count: the number of smartbox ports.
        :param fndh_port: the fndh port this smartbox is attached.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param fndh_fqdn: the fqdn of the fndh to connect to.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
        :param _fndh_bus_proxy: a optional injected device proxy for testing
            purposes only. defaults to None
        """
        max_workers = 1
        self._fndh_fqdn = fndh_fqdn
        self._pasd_fqdn = pasd_fqdn
        self.logger = logger
        self._power_state = PowerState.UNKNOWN
        self._fndh_port = fndh_port

        self._pasd_bus_proxy = _pasd_bus_proxy or _PasdBusProxy(
            pasd_fqdn,
            fndh_port,
            logger,
            max_workers,
            self._smartbox_communication_state_changed,
            functools.partial(component_state_callback, fqdn=self._pasd_fqdn),
            attribute_change_callback,
        )
        self._fndh_proxy = _fndh_bus_proxy or _FndhProxy(
            fndh_fqdn,
            fndh_port,
            logger,
            max_workers,
            self._fndh_communication_state_changed,
            functools.partial(component_state_callback, fqdn=self._fndh_fqdn),
            self._power_state_change,
        )
        self._fndh_communication_state = CommunicationStatus.NOT_ESTABLISHED
        self._pasd_communication_state = CommunicationStatus.NOT_ESTABLISHED
        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
            max_workers=max_workers,
            power=None,
            health=None,
            fault=None,
            pasdbus_status=None,
        )

    def _smartbox_communication_state_changed(
        self: SmartBoxComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        self._pasd_communication_state = communication_state
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._pasd_bus_proxy.subscribe_to_attributes()
        # Only update state on change.
        if communication_state != self._communication_state:
            self.update_device_communication_state()

    def _fndh_communication_state_changed(
        self: SmartBoxComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        self._fndh_communication_state = communication_state
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._fndh_proxy.subscribe_to_attributes()
        # Only update state on change.
        if communication_state != self._communication_state:
            self.update_device_communication_state()

    def update_device_communication_state(
        self: SmartBoxComponentManager,
    ) -> None:
        """
        Update the communication state.

        The communication state of the MccsSmartbox is derived
        from the ``MccsPasdBus`` and ``MccsFndh`` devices
        it proxies to.

        If either is `DISABLED`, ``MccsSmartBox`` is `DISABLED`
        If both `ESTABLISHED`, ``MccsSmartBox`` is `ESTABLISHED`
        all other combinations ``MccsSmartBox`` is `NOT_ESTABLISHED`

        :return: none
        """
        # TODO: We may want a more complex evaluation of communication state.
        fndh_communication = self._fndh_communication_state
        pasd_communication = self._pasd_communication_state

        if CommunicationStatus.DISABLED in [
            fndh_communication,
            pasd_communication,
        ]:
            self._update_communication_state(CommunicationStatus.DISABLED)
            return
        if (
            fndh_communication == CommunicationStatus.ESTABLISHED
            and pasd_communication == CommunicationStatus.ESTABLISHED
        ):
            self._update_communication_state(CommunicationStatus.ESTABLISHED)
            return

        self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """
        Establish communication with system under control.

        Establish communication to the ``MccsPasdBus`` and ``MccsFndh``
        devices it proxies to.

        :raises AttributeError: the smartbox/fndh proxy is None.
        """
        if None in [self._pasd_bus_proxy, self._fndh_proxy]:
            raise AttributeError("smartbox_proxy or fndh_proxy has None value.")
        self._pasd_bus_proxy.start_communicating()
        self._fndh_proxy.start_communicating()

    def _power_state_change(
        self: SmartBoxComponentManager,
        attribute_name: str,
        attribute_value: PowerState,
        attribute_quality: Optional[tango.AttrQuality] = None,
    ) -> None:
        """
        Power change reported.

        A callback to be called when the FNDH under control
        reports a power change in the port this smartbox is
        attached to.

        :param attribute_name: The name of the tango attribute pushing the
            change event.
        :param attribute_value: The power state of the port.
        :param attribute_quality: The attribute_quality
        """
        try:
            if attribute_name.lower() != f"port{self._fndh_port}powerstate":
                raise AttributeError(
                    f"Unexpected attribute {attribute_name}",
                    "attmpting to update device power state",
                )
            if attribute_name.lower() == f"port{self._fndh_port}powerstate":
                self._power_state = attribute_value
                self._update_component_state(power=self._power_state)
        except AttributeError as error_message:
            self.logger.error(f"Attribute Error: {error_message}")
        except Exception as error_message:  # pylint: disable=broad-exception-caught
            self.logger.error(f"Uncaught Exception: {error_message}")

    def stop_communicating(self: SmartBoxComponentManager) -> None:
        """Stop communication with components under control."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._pasd_bus_proxy.stop_communicating()
        self._fndh_proxy.stop_communicating()
        self._update_component_state(power=None, fault=None)

    @check_communicating
    def on(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox on.

        :param task_callback: A `Callable` to be called with updates
            on task execution.

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._on,  # type: ignore[arg-type]
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
                if self._power_state in [
                    PowerState.UNKNOWN,
                ]:
                    raise PermissionError(
                        "turn on command not allowed when in state",
                        f"{PowerState(self._power_state).name}",
                    )
                json_argument = json.dumps(
                    {
                        "port_number": self._fndh_port,
                        "stay_on_when_offline": True,  # TODO: make public.
                    }
                )
                (
                    result_code,
                    return_message,
                ) = self._pasd_bus_proxy.turn_fndh_port_on(json_argument)
            else:
                self.logger.info(
                    "Cannot turn off SmartBox, we do not yet know what port it is on"
                )
                raise ValueError("cannot turn on Unknown FNDH port.")

        except Exception as error_message:  # pylint: disable=broad-except
            self.logger.error(f"error {error_message}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"{error_message}",
                )

            return ResultCode.FAILED, str(error_message)

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on smartbox '{self._fndh_port}  success'",
            )
        return result_code, return_message

    @check_communicating
    def off(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox off.

        :param task_callback: A `Callable` to be called with updates
            on task execution.

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,  # type: ignore[arg-type]
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
                    raise ConnectionError(
                        "Unable to talk to system under control",
                        "proxy to pasdbus is None.",
                    )

                (
                    result_code,
                    return_message,
                ) = self._pasd_bus_proxy.turn_fndh_port_off(self._fndh_port)
            else:
                self.logger.info(
                    "Cannot turn off SmartBox, we do not yet know what port it is on"
                )
                raise ValueError("cannot turn off Unknown FNDH port.")

        except Exception as error_message:  # pylint: disable=broad-except
            self.logger.error(f"error {error_message}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"{error_message}",
                )

            return ResultCode.FAILED, str(error_message)

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
            self._turn_off_port,  # type: ignore[arg-type]
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
                raise ConnectionError(
                    "Unable to talk to system under control",
                    "proxy to pasdbus is None.",
                )
            json_argument = json.dumps(
                {
                    "smartbox_number": self._fndh_port,
                    "port_number": port_number,
                }
            )
            (
                result_code,
                return_message,
            ) = self._pasd_bus_proxy.turn_smartbox_port_off(json_argument)

        except Exception as error_message:  # pylint: disable=broad-except
            self.logger.error(f"error {error_message}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power off port '{port_number} failed'",
                )

            return ResultCode.FAILED, str(error_message)

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
            self._turn_on_port,  # type: ignore[arg-type]
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
                raise ConnectionError(
                    "Unable to talk to system under control",
                    "proxy to pasdbus is None.",
                )
            if self._power_state in [
                PowerState.UNKNOWN,
                PowerState.NO_SUPPLY,
                PowerState.OFF,
            ]:
                raise PermissionError(
                    "turn on port not allowed when in state",
                    f"{PowerState(self._power_state).name}",
                )
            json_argument = json.dumps(
                {
                    "smartbox_number": self._fndh_port,
                    "port_number": port_number,
                    "stay_on_when_offline": True,  # TODO: make public.
                }
            )

            (
                result_code,
                return_message,
            ) = self._pasd_bus_proxy.turn_smartbox_port_on(json_argument)

        except Exception as error_message:  # pylint: disable=broad-except
            self.logger.error(f"error: {error_message}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power on port '{port_number} failed'",
                )

            return ResultCode.FAILED, str(error_message)

        if task_callback:
            self.logger.info(f"Port {port_number} turned on!")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on port '{port_number} success'",
            )
        return result_code, return_message
