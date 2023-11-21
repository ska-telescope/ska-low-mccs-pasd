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
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

from ska_low_mccs_pasd.pasd_data import PasdData

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
        assert (
            self._task_callback or task_callback
        ), "We need task callback in order to keep track of command status"

        command_tracker = next(
            item for item in [task_callback, self._task_callback] if item is not None
        )
        self._power_on_callback(  # type: ignore[attr-defined]
            self._port_id, command_tracker
        )

        self.desire_on = False
        self._task_callback = None


class _PasdBusProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus specific to this smartbox."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _PasdBusProxy,
        fqdn: str,
        smartbox_nr: int,
        fndh_port: int,
        logger: logging.Logger,
        max_workers: int,
        smartbox_communication_state_callback: Callable[[CommunicationStatus], None],
        smartbox_component_state_callback: Callable[..., None],
        power_change_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the Tile device.
        :param smartbox_nr: the smartbox's ID number.
        :param fndh_port: this FNDH port this smartbox is attached to.
        :param logger: the logger to be used by this object.
        :param max_workers: the maximum worker threads for the slow commands
            associated with this component manager.
        :param smartbox_communication_state_callback: callback to be
            called when the status of the communications change.
        :param smartbox_component_state_callback: callback to be
            called when the component state changes.
        :param power_change_callback: callback to be called when the
            smartbox power state changes
        :param attribute_change_callback: callback for when a attribute relevant to
            this smartbox changes.
        """
        self._attribute_change_callback = attribute_change_callback
        self._power_change_callback = power_change_callback
        self._smartbox_nr = smartbox_nr
        self._fndh_port = fndh_port
        self._power_state = PowerState.UNKNOWN
        assert (
            0 < fndh_port < 29
        ), "The smartbox must be attached to a valid FNDH port in range (1-28)"
        super().__init__(
            fqdn,
            logger,
            max_workers,
            smartbox_communication_state_callback,
            smartbox_component_state_callback,
        )

    def subscribe_to_attributes(self: _PasdBusProxy) -> None:
        """Subscribe to attributes relating to this SmartBox."""
        assert self._proxy is not None
        # Ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self._smartbox_nr)
        for attribute in subscriptions:
            if attribute not in self._proxy._change_event_subscription_ids.keys():
                self._proxy.add_change_event_callback(
                    attribute, self._on_attribute_change
                )
        # Also subscribe to fndhPortsPowerSensed
        if (
            "fndhPortsPowerSensed"
            not in self._proxy._change_event_subscription_ids.keys()
        ):
            self._proxy.add_change_event_callback(
                "fndhPortsPowerSensed", self._fndh_ports_power_sensed_changed
            )

    def _on_attribute_change(
        self: _PasdBusProxy,
        attr_name: str,
        attr_value: Any,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle attribute change.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        # TODO: MCCS-1481: Update the MccsDeviceProxy to conserve attribute case.

        try:
            # 'smartbox' followed by 1 or 2 digits, followed by a string.
            smartbox_attribute_pattern = re.compile(r"smartbox(\d{1,2})(.*)")

            # Use the pattern to match the input string
            smartbox_attribute = smartbox_attribute_pattern.match(attr_name)

            # Check if we got a match, this checks it starts with 'smartbox'
            assert smartbox_attribute is not None

            # Check we're looking at the correct smartbox
            assert int(smartbox_attribute.group(1)) == self._smartbox_nr

            # If there's a match, return the string after the number
            tango_attribute_name = smartbox_attribute.group(2)

            if tango_attribute_name.lower() == "status":
                tango_attribute_name = "pasdstatus"

            self._attribute_change_callback(tango_attribute_name, attr_value)
        except AssertionError:
            self.logger.error(
                f"Attribute subscription {attr_name} does not seem to belong "
                f"to this smartbox (smartbox {self._smartbox_nr})"
            )

    def _fndh_ports_power_sensed_changed(
        self: _PasdBusProxy,
        attr_name: str,
        attr_value: list[bool],
        attr_quality: tango.AttrQuality,
    ) -> None:
        assert attr_name.lower() == "fndhportspowersensed"
        power = PowerState.ON if attr_value[self._fndh_port - 1] else PowerState.OFF
        if self._power_state != power:
            self._power_state = power
            if power == PowerState.OFF:
                self._attribute_change_callback("portspowersensed", [False] * 12)
            self._power_change_callback(power)

    def set_smartbox_port_powers(
        self: _PasdBusProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the SetSmartboxPortPowers command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        self._proxy.InitializeSmartbox(self._smartbox_nr)
        return self._proxy.SetSmartboxPortPowers(json_argument)

    def set_fndh_port_powers(
        self: _PasdBusProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the SetFndhPortPowers command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        return self._proxy.SetFndhPortPowers(json_argument)


# pylint: disable-next=abstract-method, too-many-instance-attributes
class SmartBoxComponentManager(TaskExecutorComponentManager):
    """
    A component manager for MccsSmartBox.

    This communicates via a proxy to a MccsPasdBus that talks to a simulator
    or the real hardware.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self: SmartBoxComponentManager,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        smartbox_nr: int,
        port_count: int,
        fndh_port: int,
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
        :param attribute_change_callback: callback to be called when a attribute
            of interest changes.
        :param smartbox_nr: the smartbox's ID number.
        :param port_count: the number of smartbox ports.
        :param fndh_port: the fndh port this smartbox is attached to.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
        """
        max_workers = 1
        self._pasd_fqdn = pasd_fqdn
        self.logger = logger
        self.ports = [
            Port(self.turn_on_port, port, logger) for port in range(1, port_count + 1)
        ]
        self._power_state = PowerState.UNKNOWN
        self._smartbox_nr = smartbox_nr
        self._fndh_port = fndh_port

        self._pasd_bus_proxy = _pasd_bus_proxy or _PasdBusProxy(
            pasd_fqdn,
            smartbox_nr,
            fndh_port,
            logger,
            max_workers,
            self._pasd_bus_communication_state_changed,
            self._pasd_bus_component_state_changed,
            self._smartbox_power_state_changed,
            attribute_change_callback,
        )
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

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """Establish communication."""
        self._pasd_bus_proxy.start_communicating()

    def _pasd_bus_communication_state_changed(
        self: SmartBoxComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        self._pasd_communication_state = communication_state
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._pasd_bus_proxy.subscribe_to_attributes()
        # Only update state on change.
        if communication_state != self._communication_state:
            self._update_communication_state(self._pasd_communication_state)

    def _pasd_bus_component_state_changed(
        self: SmartBoxComponentManager,
        power: PowerState | None = None,
        **kwargs: Any,
    ) -> None:
        if power == PowerState.UNKNOWN:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
        elif power == PowerState.ON:
            self._update_communication_state(CommunicationStatus.ESTABLISHED)

    def _smartbox_power_state_changed(
        self: SmartBoxComponentManager,
        power: PowerState | None = None,
    ) -> None:
        if power is None:
            return
        self._power_state = power
        # Turn on any pending ports
        if self._power_state == PowerState.ON:
            for port in self.ports:
                if port.desire_on:
                    port.turn_on()
        self._update_component_state(power=self._power_state)

    def stop_communicating(self: SmartBoxComponentManager) -> None:
        """Stop communication with components under control."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._pasd_bus_proxy.stop_communicating()
        self._update_component_state(power=None, fault=None)

    @check_communicating
    def on(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox on.

        :param task_callback: Update task state, defaults to None

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
                desired_port_powers: list[bool | None] = [
                    None
                ] * PasdData.NUMBER_OF_FNDH_PORTS
                desired_port_powers[self._fndh_port - 1] = True
                json_argument = json.dumps(
                    {
                        "port_powers": desired_port_powers,
                        "stay_on_when_offline": True,
                    }
                )
                (
                    result_code,
                    return_message,
                ) = self._pasd_bus_proxy.set_fndh_port_powers(json_argument)
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
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox off.

        :param task_callback: Update task state, defaults to None

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
                    raise ValueError(f"Power off smartbox '{self._fndh_port} failed'")

                desired_port_powers: list[bool | None] = [
                    None
                ] * PasdData.NUMBER_OF_FNDH_PORTS
                desired_port_powers[self._fndh_port - 1] = False
                json_argument = json.dumps(
                    {
                        "port_powers": desired_port_powers,
                        "stay_on_when_offline": True,
                    }
                )

                (
                    result_code,
                    return_message,
                ) = self._pasd_bus_proxy.set_fndh_port_powers(json_argument)
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
            self._turn_off_port,  # type: ignore[arg-type]
            args=[antenna_number],
            task_callback=task_callback,
        )

    def _turn_off_port(
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
            desired_port_powers: list[bool | None] = [
                None
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            desired_port_powers[port_number - 1] = False
            json_argument = json.dumps(
                {
                    "smartbox_number": self._smartbox_nr,
                    "port_powers": desired_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            (
                result_code,
                return_message,
            ) = self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)

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
                raise NotImplementedError("pasd_bus_proxy is None")
            port = self.ports[port_number - 1]
            # Turn smartbox on if not already.
            if self._power_state != PowerState.ON:
                assert port._port_id == port_number
                port.set_desire_on(task_callback)  # type: ignore[assignment]
                self.on()
                return (
                    ResultCode.STARTED,
                    "The command will continue when the smartbox turns on.",
                )
            desired_port_powers: list[bool | None] = [
                None
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            desired_port_powers[port_number - 1] = True
            json_argument = json.dumps(
                {
                    "smartbox_number": self._smartbox_nr,
                    "port_powers": desired_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            (
                result_code,
                return_message,
            ) = self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)

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

    @check_communicating
    def set_port_powers(
        self: SmartBoxComponentManager,
        json_argument: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Set port powers.

        These ports will not have an antenna attached.

        :param json_argument: desired port powers of unmasked ports with
            smartboxes attached in json form.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._set_port_powers,  # type: ignore[arg-type]
            args=[json_argument],
            task_callback=task_callback,
        )

    def _set_port_powers(
        self: SmartBoxComponentManager,
        json_argument: str,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        try:
            assert self._pasd_bus_proxy._proxy
            (
                result_code,
                unique_id,
            ) = self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {repr(ex)}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result="Set port powers failed",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result="Set port powers success",
            )
        return result_code, unique_id
