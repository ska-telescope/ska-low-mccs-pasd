#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for FieldStation."""
from __future__ import annotations

import functools
import json
import logging
import threading
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import EventSerialiser
from ska_low_mccs_common.communication_manager import CommunicationManager
from ska_low_mccs_common.component import DeviceComponentManager
from ska_low_mccs_common.component.command_proxy import MccsCommandProxy
from ska_low_mccs_common.component.composite_command_proxy import (
    CompositeCommandResultEvaluator,
    MccsCompositeCommandProxy,
    pretty_format,
)
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

__all__ = ["FieldStationComponentManager"]


class _SmartboxProxy(DeviceComponentManager):
    """A proxy to a MccsSmartbox device, for a station to use."""

    def __init__(
        self: _SmartboxProxy,
        trl: str,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        antenna_powers_changed_callback: Callable,
        event_serialiser: Optional[EventSerialiser] = None,
    ) -> None:
        super().__init__(
            trl,
            logger,
            communication_state_callback,
            component_state_callback,
            event_serialiser=event_serialiser,
        )
        self._antenna_powers_changed_callback = antenna_powers_changed_callback

    def get_change_event_callbacks(self) -> dict[str, Callable]:
        return {
            **super().get_change_event_callbacks(),
            "AntennaPowers": self._antenna_powers_changed_callback,
        }


# pylint: disable=too-many-arguments, too-many-positional-arguments
class _FndhProxy(DeviceComponentManager):
    """A proxy to a MccsFndh device, for a station to use."""

    def __init__(
        self: _FndhProxy,
        trl: str,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        field_conditions_changed_callback: Callable,
        event_serialiser: Optional[EventSerialiser] = None,
    ) -> None:
        super().__init__(
            trl,
            logger,
            communication_state_callback,
            component_state_callback,
            event_serialiser=event_serialiser,
        )
        self._field_conditions_changed_callback = field_conditions_changed_callback

    def get_change_event_callbacks(self) -> dict[str, Callable]:
        return {
            **super().get_change_event_callbacks(),
            "OutsideTemperature": self._field_conditions_changed_callback,
        }


# pylint: disable=too-many-instance-attributes, abstract-method
class FieldStationComponentManager(TaskExecutorComponentManager):
    """A component manager for MccsFieldStation."""

    FIELDSTATION_ON_COMMAND_TIMEOUT = 600  # seconds

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self: FieldStationComponentManager,
        logger: logging.Logger,
        station_name: str,
        fndh_name: str,
        smartbox_names: list[str],
        communication_state_callback: Callable[..., None],
        component_state_changed: Callable[..., None],
        event_serialiser: Optional[EventSerialiser] = None,
        _fndh_proxy: Optional[DeviceComponentManager] = None,
        _smartbox_proxys: Optional[dict[str, DeviceComponentManager]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param station_name: the station name.
        :param fndh_name: the name of the fndh this field station
            encompasses
        :param smartbox_names: the names of the smartboxes this field station
            encompasses
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed: callback to be
            called when the component state changes
        :param event_serialiser: the event serialiser to be used by this object.
        :param _fndh_proxy: a injected fndh proxy for purposes of testing only.
        :param _smartbox_proxys: injected smartbox proxys for purposes of testing only.
        """
        self._event_serialiser = event_serialiser
        self._communication_state_callback: Callable[..., None]
        self._component_state_callback: Callable[..., None]
        self.outsideTemperature: Optional[float] = None
        self._power_state: Optional[PowerState] = None
        self._power_state_lock = threading.RLock()

        self.smartbox_power_change = threading.Event()
        self.station_name = station_name
        super().__init__(
            logger,
            communication_state_callback,
            component_state_changed,
            power=PowerState.UNKNOWN,
            fault=None,
        )
        self._communication_states = {
            fqdn: CommunicationStatus.DISABLED
            for fqdn in [fndh_name] + list(smartbox_names)
        }

        self._fndh_name = fndh_name
        self._fndh_proxy = _fndh_proxy or _FndhProxy(
            fndh_name,
            logger,
            functools.partial(self._device_communication_state_changed, fndh_name),
            functools.partial(self._component_state_callback, device_name=fndh_name),
            self._on_field_conditions_change,
            event_serialiser=self._event_serialiser,
        )
        self._smartbox_power_state = {}
        self._smartbox_proxys = {}
        if _smartbox_proxys:
            self._smartbox_proxys = _smartbox_proxys
        else:
            for smartbox_trl in smartbox_names:
                self._smartbox_power_state[smartbox_trl] = PowerState.UNKNOWN
                self._smartbox_proxys[smartbox_trl] = _SmartboxProxy(
                    smartbox_trl,
                    logger,
                    functools.partial(
                        self._device_communication_state_changed, smartbox_trl
                    ),
                    functools.partial(
                        self._component_state_callback, device_name=smartbox_trl
                    ),
                    self._on_antenna_powers_change,
                    event_serialiser=self._event_serialiser,
                )

        self._communication_manager = CommunicationManager(
            self._update_communication_state,
            self._update_component_state,
            self.logger,
            self._smartbox_proxys,
            {self._fndh_name: self._fndh_proxy},
        )

    def start_communicating(self: FieldStationComponentManager) -> None:
        """Establish communication."""
        self._communication_manager.start_communicating()

    def stop_communicating(self: FieldStationComponentManager) -> None:
        """Break off communication with the PasdData."""
        self._communication_manager.stop_communicating()

    def _on_field_conditions_change(
        self: FieldStationComponentManager,
        event_name: str,
        event_value: Any,
        event_quality: tango.AttrQuality,
    ) -> None:
        match event_name.lower():
            case "outsidetemperature":
                if event_quality == tango.AttrQuality.ATTR_VALID:
                    assert isinstance(event_value, float)
                    self.outsideTemperature = event_value
                    self._component_state_callback(
                        outsidetemperature=self.outsideTemperature
                    )
            case _:
                self.logger.error(f"Attribute name {event_name} Unknown")

    def _on_antenna_powers_change(
        self: FieldStationComponentManager,
        event_name: str,
        event_value: Any,
        event_quality: tango.AttrQuality,
    ) -> None:
        match event_name.lower():
            case "antennapowers":
                if event_quality == tango.AttrQuality.ATTR_VALID:
                    assert isinstance(event_value, str)
                    self._component_state_callback(antenna_powers=event_value)
            case _:
                self.logger.error(f"Attribute name {event_name} Unknown")

    def smartbox_state_change(
        self: FieldStationComponentManager, smartbox_trl: str, power: PowerState
    ) -> None:
        """
        Register a state change for a smartbox.

        :param smartbox_trl: the name of the smartbox with a state change
        :param power: the power state of the smartbox.
        """
        self._smartbox_power_state[smartbox_trl] = power
        self.smartbox_power_change.set()
        self._evaluate_power_state()

    def _device_communication_state_changed(
        self: FieldStationComponentManager,
        fqdn: str,
        communication_state: CommunicationStatus,
    ) -> None:
        self._communication_manager.update_communication_status(
            fqdn, communication_state
        )

    def on(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn on the FieldStation.

        Turning on the FieldStation will distribute power
        to all antennas that make up that FieldStation.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._on,
            args=[],
            task_callback=task_callback,
        )

    def _on(  # noqa: C901
        self: FieldStationComponentManager,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)
        failure_log = ""

        timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
        fndh_on_command = MccsCommandProxy(self._fndh_name, "On", self.logger)
        result, message = fndh_on_command(timeout=timeout, run_in_thread=False)

        if result == ResultCode.OK:
            smartbox_on_commands = MccsCompositeCommandProxy(self.logger)
            for smartbox_trl in self._smartbox_proxys:
                smartbox_on_commands += MccsCommandProxy(
                    smartbox_trl, "On", self.logger
                )
            result, message = smartbox_on_commands(
                command_evaluator=CompositeCommandResultEvaluator(),
                timeout=timeout,
            )
            if result != ResultCode.OK:
                failure_log += (
                    f"MccsCompositeCommandProxy was not happy {result=}"
                    f" {pretty_format(message)}"
                )

        if failure_log:
            self.logger.error(f"Failure in the `ON` command -> {failure_log}")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(result, message),
            )
            return

        self.logger.info("All unmasked antennas turned on.")
        task_callback(
            status=TaskStatus.COMPLETED,
            result=(ResultCode.OK, "All unmasked antennas turned on."),
        )

    def standby(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn the FieldStation to Standby.

        Turning the FieldStation to Standby will turn on all smartboxes,
        but leave their ports turned off.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._standby,
            args=[],
            task_callback=task_callback,
        )

    def _standby(  # noqa: C901
        self: FieldStationComponentManager,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)

        failure_log = ""

        timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
        fndh_on_command = MccsCommandProxy(self._fndh_name, "On", self.logger)
        result, message = fndh_on_command(timeout=timeout)

        if result == ResultCode.OK:
            smartbox_standby_commands = MccsCompositeCommandProxy(self.logger)
            for smartbox_trl in self._smartbox_proxys:
                smartbox_standby_commands += MccsCommandProxy(
                    smartbox_trl, "Standby", self.logger
                )
            result, message = smartbox_standby_commands(
                command_evaluator=CompositeCommandResultEvaluator(),
                timeout=timeout,
            )
            if result != ResultCode.OK:
                failure_log = (
                    f"MccsCompositeCommandProxy was not happy {result=}"
                    f" {pretty_format(message)}"
                )

        if failure_log:
            self.logger.error(f"Failure in the `STANDBY` command -> {failure_log}")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(result, message),
            )
            return

        self.logger.info("All FNDH ports turned on. All Smartbox ports turn off.")
        task_callback(
            status=TaskStatus.COMPLETED,
            result=(
                ResultCode.OK,
                "All FNDH ports turned on. All Smartbox ports turn off.",
            ),
        )

    def off(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn off the FieldStation.

        Turning off the FieldStation will cut off power
        to all antennas that make up that FieldStation.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,
            args=[],
            task_callback=task_callback,
        )

    def _off(
        self: FieldStationComponentManager,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)

        failure_log = ""

        timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
        fndh_on_command = MccsCommandProxy(self._fndh_name, "Standby", self.logger)
        result, message = fndh_on_command(timeout=timeout, run_in_thread=False)

        if failure_log:
            self.logger.error(f"Failure in the `OFF` command -> {failure_log}")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(result, failure_log),
            )
            return

        self.logger.info("All FNDH ports turned off. All Smartbox ports turned off.")
        task_callback(
            status=TaskStatus.COMPLETED,
            result=(
                result,
                "All FNDH ports turned off. All Smartbox ports turned off.",
            ),
        )

    @check_communicating
    def power_on_antenna(
        self: FieldStationComponentManager,
        antenna_name: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn on an antenna on this station.

        :param antenna_name: (one-based) number of the Antenna to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._power_on_antenna,  # type: ignore[arg-type]
            args=[antenna_name],
            task_callback=task_callback,
        )

    def _power_on_antenna(
        self: FieldStationComponentManager,
        antenna_name: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)
        for smartbox_trl, smartbox_proxy in self._smartbox_proxys.items():
            if (
                smartbox_proxy._proxy is not None
                and antenna_name in smartbox_proxy._proxy.antennaNames
            ):
                antenna_on_command = MccsCommandProxy(
                    smartbox_trl, "PowerOnAntenna", self.logger
                )
                result, message = antenna_on_command(antenna_name, run_in_thread=False)
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=(result, message),
                )

    @check_communicating
    def power_off_antenna(
        self: FieldStationComponentManager,
        antenna_name: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn off an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        :param antenna_name: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._power_off_antenna,  # type: ignore[arg-type]
            args=[antenna_name],
            task_callback=task_callback,
        )

    def _power_off_antenna(
        self: FieldStationComponentManager,
        antenna_name: str,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)
        for smartbox_trl, smartbox_proxy in self._smartbox_proxys.items():
            if (
                smartbox_proxy._proxy is not None
                and antenna_name in smartbox_proxy._proxy.antennaNames
            ):
                antenna_on_command = MccsCommandProxy(
                    smartbox_trl, "PowerOffAntenna", self.logger
                )
                result, message = antenna_on_command(antenna_name, run_in_thread=False)
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=(result, message),
                )

    def configure(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus | ResultCode, str]:
        """
        Configure the field station.

        Currently this only supports configuring FNDH alarm thresholds.

        :param task_callback: callback to be called when the status of
            the command changes
        :param kwargs: keyword arguments extracted from the JSON string.

        :return: the task status and a human-readable status message
        """
        command_proxy = MccsCommandProxy(self._fndh_name, "Configure", self.logger)
        return command_proxy(json.dumps(kwargs), task_callback=task_callback)

    def _evaluate_power_state(self: FieldStationComponentManager) -> None:  # noqa: C901
        """
        Evaluate the power state of the FieldStation.

        * FieldStation is ON if any smartboxes are ON.
        * FieldStation is STANDBY if any smartboxes are STANDBY.
        * FieldStation is OFF if all smartboxes are OFF.
        * FieldStation is UNKNOWN if none of these were matched.
        """
        # We don't want to take into account UNKNOWN smartboxes here, that's taken care
        # in the healthState.
        trimmed_smartbox_power_states = [
            smartbox_power_state
            for smartbox_power_state in self._smartbox_power_state.values()
            if smartbox_power_state != PowerState.UNKNOWN
        ]

        def transition_to(power_state: PowerState, msg: str | None = None) -> None:
            if self._power_state != power_state:
                self.logger.info(
                    msg
                    or f"At least one Smartbox is {power_state.name}, "
                    f"FieldStation transitioning to {power_state.name} state ...."
                )
                self._power_state = power_state
                self._component_state_callback(power=power_state)

        if trimmed_smartbox_power_states:
            with self._power_state_lock:
                match self._smartbox_power_state:
                    case _ if PowerState.ON in trimmed_smartbox_power_states:
                        transition_to(PowerState.ON)
                    case _ if PowerState.STANDBY in trimmed_smartbox_power_states:
                        transition_to(PowerState.STANDBY)
                    case _ if all(
                        power == PowerState.OFF
                        for power in trimmed_smartbox_power_states
                    ):
                        transition_to(
                            PowerState.OFF,
                            msg=(
                                "All smartboxes are `OFF`, "
                                "FieldStation transitioning to `OFF` state ...."
                            ),
                        )
                    case _:
                        transition_to(
                            PowerState.UNKNOWN,
                            msg=(
                                "No PowerState rules matched, "
                                "FieldStation transitioning to `UNKNOWN` state ...."
                            ),
                        )
