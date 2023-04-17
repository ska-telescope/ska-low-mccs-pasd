#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for smartbox."""
from __future__ import annotations

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
        pasd_fqdn: str,
        fndh_port: int,
        smartbox_number: Optional[int] = None,
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
        :param attribute_change_callback: callback to be called when a attribute
            of interest changes.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param fndh_port: the port of the fndh this smartbox is attached.
        :param smartbox_number: the number assigned to this smartbox by station.
        :param _pasd_bus_proxy: a optional injected device proxy for testing

        purposes only. defaults to None
        """
        max_workers = 1
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
        self._pasd_fqdn = pasd_fqdn
        self.smartbox_number = smartbox_number
        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self.fndh_port = fndh_port
        self.logger = logger

        # This is used in the proxy callback
        # the reason being that it is called with a Capitals during event subscription
        # and with lower case during a push event.
        self.attr_case_map: dict[str, str] = {}

    def _subscribe_to_attributes(self: SmartBoxComponentManager) -> None:
        """Subscribe to attributes on the MccsPasdBus."""
        assert self._pasd_bus_proxy is not None

        # ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._pasd_bus_proxy.GetPasdDeviceSubscriptions(
            self.smartbox_number
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
                "fndhPortsPowerSensed", self._power_state_change
            )

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """
        Establish communication with the pasdBus via a proxy.

        This checks:
            - A proxy can be formed with the MccsPasdBus
            - We can add a health change event callback to that proxy
            - The pasdBus is healthy
        """
        # ------------------------------------
        # FORM PROXY / SUBSCRIBE TO ATTRIBUTES
        # ------------------------------------
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

        # ------------
        # UPDATE STATE
        # ------------
        try:
            # If we are not established attempt for establish communication.
            if self.communication_state != CommunicationStatus.ESTABLISHED:
                self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
                self._pasd_bus_proxy.ping()

                # TODO: check the pasd_bus is communicating modbus
                # here we just assume it is.
                self._update_communication_state(CommunicationStatus.ESTABLISHED)

                port = self.fndh_port
                if self._pasd_bus_proxy.fndhPortsPowerSensed[port]:  # type: ignore
                    self._component_state_changed_callback(power=PowerState.ON)
                else:
                    self._component_state_changed_callback(power=PowerState.OFF)
            else:
                self.logger.info(
                    "communication with the pasd bus is already established"
                )

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
        # TODO: This is called with a uppercase during initial subscription and
        # with lowercase for push_change_events. Update the MccsDeviceProxy to fix
        # this.

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

        # TODO: for the moment we are getting the power states of
        # all the ports on the FNDH. Consider changing this.
        this_smartbox_has_power = port_power_states[self.fndh_port]
        if this_smartbox_has_power:
            self._component_state_changed_callback(power=PowerState.ON)
        else:
            self._component_state_changed_callback(power=PowerState.OFF)

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
                raise ValueError("pasd_bus_proxy is None")
            ([result_code], [return_message]) = self._pasd_bus_proxy.TurnFndhPortOn(
                self.fndh_port
            )
            if result_code == ResultCode.OK:
                self._update_component_state(power=PowerState.ON)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power on smartbox '{self.fndh_port} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on smartbox '{self.fndh_port}  success'",
            )
        return result_code, return_message

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

            ([result_code], [return_message]) = self._pasd_bus_proxy.TurnFndhPortOff(
                self.fndh_port
            )
            if result_code == ResultCode.OK:
                self._update_component_state(power=PowerState.OFF)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power off smartbox '{self.fndh_port} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power off smartbox '{self.fndh_port}  success'",
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

            (
                [result_code],
                [return_message],
            ) = self._pasd_bus_proxy.TurnSmartboxPortOff(port_number)

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
        port_number: str,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [return_message]) = self._pasd_bus_proxy.TurnSmartboxPortOn(
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
        return result_code, return_message
