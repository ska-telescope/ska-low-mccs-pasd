#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements component management for smartboxs."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, cast

import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import MccsComponentManager
from ska_tango_base.commands import ResultCode

__all__ = ["SmartBoxComponentManager"]


# pylint: disable-next=abstract-method
class SmartBoxComponentManager(MccsComponentManager):
    """
    A component manager for an smartbox.

    This communicates via a proxy to a MccsPadsBus that talks to a simulator
    or the real hardware.
    """

    def __init__(
        self: SmartBoxComponentManager,
        logger: logging.Logger,
        communication_state_changed_callback: Callable[[CommunicationStatus], None],
        component_state_changed_callback: Callable[..., None],
        pasd_fqdn: str = None,
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
            max_workers,
            communication_state_changed_callback,
            component_state_changed_callback,
        )
        self._component_state_changed_callback = component_state_changed_callback
        self._pasd_fqdn = pasd_fqdn

        self._pasd_bus_proxy: Optional[MccsDeviceProxy] = _pasd_bus_proxy
        self.logger = logger

    def on(
        self: SmartBoxComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Tell the upstream power supply proxy to turn the tpm on.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        # TODO: create the proxy to the pasd_bus:
        # here we create the connection to the simulated pasd_bus or we use
        # a mccs deviceproxy to one.
        return self._pasd_bus_proxy.TurnSmartboxOn()

    def off(
        self: SmartBoxComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Tell the upstream power supply proxy to turn the tpm on.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        # TODO: create the proxy to the pasd_bus:
        # here we create the connection to the simulated pasd_bus or we use
        # a mccs deviceproxy to one.
        return self._pasd_bus_proxy.TurnSmartboxOff()

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """Establish communication with the pasdBus via a proxy."""
        exceptions_caught = []
        # Do things that might need to be done.
        if self._pasd_bus_proxy is None:
            try:
                self.logger.info(f"attempting to form proxy with {self._pasd_fqdn}")

                self._pasd_bus_proxy = MccsDeviceProxy(
                    "low-mccs-pasd/pasdbus/001", self.logger, connect=True
                )
            except Exception as e:  # pylint: disable=broad-except
                self.component_state_changed_callback({"fault": True})
                self.logger.error("Caught exception in start_communicating: %s", e)
                exceptions_caught.append(e)

            try:
                # register a callback to any attributes of interest to MccsSmartBox.
                # TODO: Do we want a polling architecture of a event driven architecture?
                # Assumes the pasdBus will fire change events when these attributes
                # change.
                # The MccsSmartBox will resend these change events to any interested parties.
                change_event_callbacks = {
                    "antennasTripped": self._antenna_tripped_callback,
                    # "smartbox_statuses": smartbox_statuses_callback,
                    # "smartboxServiceLedsOn": smartbox_service_led_callback,
                    # "smartboxDesiredPowerOnline":
                    # smartbox_desired_power_online_callback,
                    # "smartboxDesiredPowerOffline":
                    # smartbox_desired_power_offline_callback,
                    # "antennasOnline": antenna_online_callback,
                    # "antennasForced": antenna_forced_callback,
                    # TODO............
                }

                for attribute in change_event_callbacks.items():
                    cast(
                        MccsDeviceProxy, self._pasd_bus_proxy
                    ).add_change_event_callback(*attribute)

            except Exception as e:  # pylint: disable=broad-except
                self.logger.error(
                    "Caught exception in adding change event callback to proxy: %s", e
                )
                exceptions_caught.append(e)

            if len(exceptions_caught) != 0:
                self.logger.error(
                    "Start_communication failed with errors: %s", str(exceptions_caught)
                )
                return

        self.logger.info("start communicating completed")
        self.update_communication_state(CommunicationStatus.ESTABLISHED)

    def _antenna_tripped_callback(
        self: SmartBoxComponentManager,
        event_name: str,
        event_value: PowerState,
        event_quality: tango.AttrQuality,
    ):
        """
        Callback.

        :param event_name: event name.
        """
        # TODO: Is callback the correct mechanism here?
        self._component_state_changed_callback(antennas_tripped=event_value)

    @property
    def antennas_tripped(self: SmartBoxComponentManager) -> list[bool]:
        """
        Return whether each antenna has had its breaker tripped.

        :return: a list of booleans indicating whether each antenna has
            had its breaker tripped.
        """
        return self._pasd_bus_proxy.antennasTripped

    def turn_off_port(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna off.

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
        antenna_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [unique_id]) = self._pasd_bus_proxy.TurnAntennaOff(
                antenna_number
            )

            # Do we want to block progress till we get a response?
            # TODO: requires more thought:
            # should we implement this?
            # how we should implement this

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return result_code, unique_id

    def turn_on_port(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna on.

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
        antenna_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ):
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [unique_id]) = self._pasd_bus_proxy.TurnAntennaOn(
                antenna_number
            )

            # Do we want to block progress till we get a response?
            # TODO: requires more thought:
            # should we implement this?
            # how we should implement this

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return result_code, unique_id

    def get_antenna_info(
        self: SmartBoxComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Antenna off.

        :param antenna_number: (one-based) number of the TPM to turn off.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._get_antenna_info,
            args=[antenna_number],
            task_callback=task_callback,
        )

    def _get_antenna_info(
        self: SmartBoxComponentManager,
        antenna_number: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")

            ([result_code], [unique_id]) = self._pasd_bus_proxy.GetAntennaInfo(
                antenna_number
            )

            # Do we want to block progress till we get a response?
            # TODO: requires more thought:
            # should we implement this?
            # how we should implement this

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(status=TaskStatus.FAILED, result=f"Exception: {ex}")

            return ResultCode.FAILED, "0"

        return result_code, unique_id
