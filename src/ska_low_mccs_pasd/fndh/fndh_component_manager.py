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
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import EventSerialiser, MccsDeviceProxy
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

from ska_low_mccs_pasd.pasd_data import PasdData

__all__ = ["FndhComponentManager", "_PasdBusProxy"]

RESULT_TO_TASK = {
    ResultCode.OK: TaskStatus.COMPLETED,
    ResultCode.FAILED: TaskStatus.FAILED,
}


class _PasdBusProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus bus."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self: _PasdBusProxy,
        fqdn: str,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        state_change_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        update_port_power_states: Callable[..., None],
        event_serialiser: Optional[EventSerialiser] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the MccsPaSDBus device
        :param logger: the logger to be used by this object.
        :param communication_state_callback: callback to be
            called when communication state changes.
        :param state_change_callback: callback to be called when the
            component state changes
        :param attribute_change_callback: callback for when a subscribed attribute
            on the pasdbus changes.
        :param update_port_power_states: callback to be called when the port
            power states changes.
        :param event_serialiser: the event serialiser to be used by this object.
        """
        self._update_port_power_states = update_port_power_states
        self._attribute_change_callback = attribute_change_callback
        self._pasd_device = PasdData.FNDH_DEVICE_ID

        super().__init__(
            fqdn,
            logger,
            communication_state_callback,
            state_change_callback,
            event_serialiser=event_serialiser,
        )

    def subscribe_to_attributes(self: _PasdBusProxy) -> None:
        """Subscribe to attributes relating to this FNDH."""
        assert self._proxy is not None
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self._pasd_device)
        for attribute in subscriptions:
            if attribute not in self._proxy._change_event_subscription_ids.keys():
                self.logger.debug(f"Subscribing to attribute {attribute}.....")
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

                port_power_states = map(get_power_state, attr_value)

                self._update_port_power_states(list(port_power_states))

            # Status is a bad name since it conflicts with TANGO status.
            if tango_attribute_name.lower() == "status":
                tango_attribute_name = "pasdstatus"

            timestamp = datetime.now(timezone.utc).timestamp()
            self._attribute_change_callback(
                tango_attribute_name, attr_value, timestamp, attr_quality
            )
            return

        self.logger.info(
            f"Attribute subscription {attr_name} does not seem to begin"
            "with 'fndh' string so it is assumed it is a incorrect subscription"
        )

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
        self._proxy.InitializeFndh()
        return self._proxy.SetFndhPortPowers(json_argument)

    def write_attribute(
        self: _PasdBusProxy, tango_attribute_name: str, value: Any
    ) -> None:
        """
        Proxy for the generic write attribute function.

        :param tango_attribute_name: the name of the Tango attribute.
        :param value: the value to write.
        """
        assert self._proxy
        setattr(self._proxy, "fndh" + tango_attribute_name, value)


# pylint: disable-next=abstract-method, too-many-instance-attributes
class FndhComponentManager(TaskExecutorComponentManager):
    """
    A component manager for an fndh.

    This communicates via a proxy to a MccsPasdBus that talks to a simulator
    or the real hardware.
    """

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self: FndhComponentManager,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        update_port_power_states: Callable[..., None],
        pasd_fqdn: str,
        ports_with_smartbox: list[int],
        event_serialiser: Optional[EventSerialiser] = None,
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
        :param ports_with_smartbox: the list of ports with smartboxes.
        :param event_serialiser: the event serialiser to be used by this object.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
            purposes only. defaults to None
        """
        self._event_serialiser = event_serialiser
        self._component_state_callback = component_state_callback
        self._attribute_change_callback = attribute_change_callback
        self._update_port_power_states = update_port_power_states
        self._pasd_fqdn = pasd_fqdn
        self._ports_with_smartbox = ports_with_smartbox
        self._fndh_port_powers = [PowerState.UNKNOWN] * PasdData.NUMBER_OF_FNDH_PORTS
        self.fndh_ports_change = threading.Event()
        self._power_state = PowerState.UNKNOWN

        self._pasd_bus_proxy = _pasd_bus_proxy or _PasdBusProxy(
            pasd_fqdn,
            logger,
            self._pasdbus_communication_state_changed,
            functools.partial(component_state_callback, fqdn=self._pasd_fqdn),
            attribute_change_callback,
            update_port_power_states,
            event_serialiser=self._event_serialiser,
        )
        self.logger = logger
        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
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
        port_number: int,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        desired_port_powers: list[bool | None] = [None] * PasdData.NUMBER_OF_FNDH_PORTS
        desired_port_powers[port_number - 1] = False
        json_args = json.dumps(
            {
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )
        try:
            assert self._pasd_bus_proxy._proxy
            (
                [result_code],
                [return_message],
            ) = self._pasd_bus_proxy._proxy.SetFndhPortPowers(json_args)

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
        port_number: int,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        desired_port_powers: list[bool | None] = [None] * PasdData.NUMBER_OF_FNDH_PORTS
        desired_port_powers[port_number - 1] = True
        json_argument = json.dumps(
            {
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )

        try:
            assert self._pasd_bus_proxy._proxy
            (
                [result_code],
                [unique_id],
            ) = self._pasd_bus_proxy._proxy.SetFndhPortPowers(json_argument)

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

    @check_communicating
    def set_port_powers(
        self: FndhComponentManager,
        json_argument: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Set port powers.

        These ports will not have a smartbox attached.

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
        self: FndhComponentManager,
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
            ) = self._pasd_bus_proxy.set_fndh_port_powers(json_argument)

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

    def _power_fndh_ports(
        self: FndhComponentManager, power_state: PowerState, timeout: int
    ) -> tuple[ResultCode, int]:
        desired_port_powers: list[bool] = [False] * PasdData.NUMBER_OF_FNDH_PORTS
        for port in self._ports_with_smartbox:
            desired_port_powers[port - 1] = power_state == PowerState.ON
        json_argument = json.dumps(
            {
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )
        self._pasd_bus_proxy.set_fndh_port_powers(json_argument)
        return self._wait_for_fndh_ports_state(desired_port_powers, timeout)

    def _wait_for_fndh_ports_state(
        self: FndhComponentManager, desired_port_powers: list[bool], timeout: int
    ) -> tuple[ResultCode, int]:
        desired_port_power_states = [
            PowerState.ON if power else PowerState.OFF for power in desired_port_powers
        ]
        while not self._fndh_port_powers == desired_port_power_states:
            self.logger.debug("Waiting for unmasked smartbox ports to change state")
            t1 = time.time()
            self.fndh_ports_change.wait(timeout)
            t2 = time.time()
            timeout -= int(t2 - t1)
            self.fndh_ports_change.clear()
            if timeout <= 0:
                self.logger.error("Timeout reached waiting for Smartbox port state.")
                return ResultCode.FAILED, timeout
        return ResultCode.OK, timeout

    @check_communicating
    def on(
        self: FndhComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Fndh on.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._power_ports,
            args=[PowerState.ON],
            task_callback=task_callback,
        )

    @check_communicating
    def standby(
        self: FndhComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Fndh to standby.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._power_ports,  # type: ignore[arg-type]
            args=[PowerState.OFF],
            task_callback=task_callback,
        )

    def _power_ports(
        self: FndhComponentManager,
        power_state: PowerState,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        result = ResultCode.OK

        try:
            timeout = 60  # seconds
            result, time_left = self._power_fndh_ports(power_state, timeout)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=(ResultCode.FAILED, f"{ex}"),
                )

        if task_callback:
            task_callback(
                status=RESULT_TO_TASK[result],
                result=(
                    result,
                    (
                        f"Powering {power_state.name} FNDH "
                        f"ports {result.name} in {time_left} seconds"
                    ),
                ),
            )

    def _evaluate_power(self: FndhComponentManager) -> None:
        """
        Evaluate the power state of the fndh device.

        * If the FNDH's ports are all OFF, the FNDH is STANDBY.
        * If at least one of the FNDH's ports are ON, the FNDH is ON.
        * If the FNDH is not in any of the states above, it is UNKNOWN.
        """
        if all(power == PowerState.OFF for power in self._fndh_port_powers):
            msg = "All ports are OFF, the FNDH is STANDBY"
            power_state = PowerState.STANDBY
        elif any(power == PowerState.ON for power in self._fndh_port_powers):
            msg = "At least one port is ON, FNDH is ON."
            power_state = PowerState.ON
        else:
            msg = (
                f"FNDH reported port power states are {self._fndh_port_powers}."
                "This is an unexpected state, moving to UNKNOWN."
            )
            power_state = PowerState.UNKNOWN

        if self._power_state != power_state:
            if power_state == PowerState.UNKNOWN:
                self.logger.warning(msg)
            else:
                self.logger.debug(msg)
            self._power_state = power_state
            self._update_component_state(power=power_state)

    @check_communicating
    def write_attribute(
        self: FndhComponentManager,
        attribute_name: str,
        value: Any,
    ) -> None:
        """
        Request to write an attribute via the proxy.

        :param attribute_name: the name of the Tango attribute.
        :param value: the value to write.
        """
        self._pasd_bus_proxy.write_attribute(attribute_name, value)
