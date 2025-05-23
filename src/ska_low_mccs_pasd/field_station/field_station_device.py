# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FieldStation device."""

from __future__ import annotations

import json
from typing import Any, Final, Optional

from ska_control_model import (
    AdminMode,
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
)
from ska_control_model.health_rollup import HealthRollup, HealthSummary
from ska_low_mccs_common import MccsBaseDevice
from ska_tango_base.commands import JsonValidator, SubmittedSlowCommand
from tango.server import attribute, command, device_property

from .field_station_component_manager import FieldStationComponentManager

__all__ = ["MccsFieldStation"]


DevVarLongStringArrayType = tuple[list[ResultCode], list[str]]


class MccsFieldStation(MccsBaseDevice):
    """An implementation of the FieldStation device."""

    # -----------------
    # Device Properties
    # -----------------
    StationName = device_property(dtype=(str), mandatory=True)
    FndhFQDN = device_property(dtype=(str), mandatory=True)
    SmartBoxFQDNs = device_property(dtype=(str,), default_value=[])
    # --------------
    # Initialisation
    # --------------

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialise this device object.

        :param args: positional args to the init
        :param kwargs: keyword args to the init
        """
        # We aren't supposed to define initialisation methods for Tango
        # devices; we are only supposed to define an `init_device` method. But
        # we insist on doing so here, just so that we can define some
        # attributes, thereby stopping the linters from complaining about
        # "attribute-defined-outside-init" etc. We still need to make sure that
        # `init_device` re-initialises any values defined in here.
        super().__init__(*args, **kwargs)

        self.component_manager: FieldStationComponentManager
        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_report: str
        self._health_rollup: HealthRollup
        self._antenna_powers: dict

    def init_device(self: MccsFieldStation) -> None:
        """Initialise the device."""
        self._antenna_powers = {}
        self._component_state_on: Optional[bool] = None

        super().init_device()

        message = (
            "Initialised MccsFieldStation device with properties:\n"
            f"\tFndhFQDN: {self.FndhFQDN}\n"
            f"\tSmartBoxFQDNs: {self.SmartBoxFQDNs}\n"
            f"\tStationName: {self.StationName}\n"
        )
        self.logger.info(message)

    def _init_state_model(self: MccsFieldStation) -> None:
        super()._init_state_model()

        self._health_state = HealthState.UNKNOWN
        self._health_report = ""

        self._health_rollup = HealthRollup(
            [self.FndhFQDN, "smartboxes"],
            (1, 1, 1),
            self._health_changed,
            self._health_summary_changed,
        )
        self._health_rollup.define(
            "smartboxes",
            self.SmartBoxFQDNs,
            (0, 1, 1),
        )

    def create_component_manager(
        self: MccsFieldStation,
    ) -> FieldStationComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return FieldStationComponentManager(
            self.logger,
            self.StationName,
            self.FndhFQDN,
            self.SmartBoxFQDNs,
            self._communication_state_changed,
            self._component_state_callback,
            event_serialiser=self._event_serialiser,
        )

    def init_command_objects(self: MccsFieldStation) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        configure_schema: Final = {
            "type": "object",
            "properties": {
                "overCurrentThreshold": {"type": "number"},
                "overVoltageThreshold": {"type": "number"},
                "humidityThreshold": {"type": "number"},
            },
        }

        for command_name, method_name, schema in [
            ("PowerOnAntenna", "power_on_antenna", None),
            ("PowerOffAntenna", "power_off_antenna", None),
            ("Configure", "configure", configure_schema),
        ]:
            validator = (
                None
                if schema is None
                else JsonValidator(command_name, schema, self.logger)
            )

            self.register_command_object(
                command_name,
                SubmittedSlowCommand(
                    command_name,
                    self._command_tracker,
                    self.component_manager,
                    method_name,
                    callback=None,
                    logger=self.logger,
                    validator=validator,
                ),
            )
        self.set_change_event("antennaPowerStates", True, False)
        self.set_change_event("outsideTemperature", True, False)

    # ----------
    # Callbacks
    # ----------

    def _communication_state_changed(
        self: MccsFieldStation,
        communication_state: CommunicationStatus,
        device_name: Optional[str] = None,
    ) -> None:
        # We need to subscribe and re-emit change events.
        super()._communication_state_changed(communication_state)
        if communication_state != CommunicationStatus.ESTABLISHED:
            self._component_state_callback(power=PowerState.UNKNOWN)
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_callback(power=self.component_manager._power_state)

    def _component_state_callback(  # noqa: C901
        self: MccsFieldStation,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        health: HealthState | int | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component.
        :param health: the health state of the component.
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if "device_name" in kwargs:
            device_name = kwargs["device_name"]
            device_family = "FNDH" if device_name == self.FndhFQDN else "Smartbox"
            health = None if health is None else HealthState(health)

            self.logger.debug(
                f"{device_family} {device_name} changed state to "
                f"power = {power}, "
                f"fault = {fault}, "
                f"health = {None if health is None else health.name} "
            )
            if health is not None:
                self._health_rollup.health_changed(device_name, health)
            if device_family == "Smartbox" and power is not None:
                self.component_manager.smartbox_state_change(device_name, power)
            return

        if "outsidetemperature" in kwargs:
            self.push_change_event("outsideTemperature", kwargs["outsidetemperature"])

        if "antenna_powers" in kwargs:
            self._antenna_powers |= json.loads(kwargs["antenna_powers"])
            self.push_change_event(
                "antennaPowerStates", json.dumps(self._antenna_powers)
            )

        super()._component_state_changed(fault=fault, power=power)

    def _update_admin_mode(self, admin_mode: AdminMode) -> None:
        super()._update_admin_mode(admin_mode)
        self._health_rollup.online = admin_mode in [
            AdminMode.ENGINEERING,
            AdminMode.ONLINE,
        ]

    def _health_changed(self: MccsFieldStation, health: HealthState) -> None:
        """
        Handle change in this device's health state.

        This is a callback hook, called whenever the HealthModel's
        evaluated health state changes. It is responsible for updating
        the tango side of things i.e. making sure the attribute is up to
        date, and events are pushed.

        :param health: the new health value
        """
        self._health_state = health
        self.push_change_event("healthState", health)

    def _health_summary_changed(
        self: MccsFieldStation, health_summary: HealthSummary
    ) -> None:
        """
        Handle change in this device's health summary.

        This is a callback hook, called whenever this device's
        evaluated health summary changes. It is responsible for updating
        the tango side of things i.e. making sure the attribute is up to
        date, and events are pushed.

        :param health_summary: the new health summary
        """
        self._health_report = json.dumps(health_summary)

    # --------
    # Commands
    # --------

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def Configure(self: MccsFieldStation, argin: str) -> DevVarLongStringArrayType:
        """
        Configure the field station.

        Currently this only configures FNDH device attributes.

        :param argin: the configuration for the device in stringified json format

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("Configure")
        (return_code, message) = handler(argin)
        return ([return_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def PowerOnAntenna(
        self: MccsFieldStation, antenna_name: str
    ) -> DevVarLongStringArrayType:
        """
        Turn on an antenna.

        :param antenna_name: Antenna name to turn on.

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("PowerOnAntenna")
        (return_code, message) = handler(antenna_name)
        return ([return_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def PowerOffAntenna(
        self: MccsFieldStation, antenna_name: str
    ) -> DevVarLongStringArrayType:
        """
        Turn off an antenna.

        :param antenna_name: Antenna name to turn on.

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("PowerOffAntenna")
        (return_code, message) = handler(antenna_name)
        return ([return_code], [message])

    # ----------
    # Attributes
    # ----------

    @attribute(dtype="DevString", label="antennaPowerStates")
    def antennaPowerStates(self: MccsFieldStation) -> str:
        """
        Return the logical antenna powers.

        :return: the power of the logical antennas.
        """
        return json.dumps(self._antenna_powers)

    @attribute(dtype="float", label="OutsideTemperature")
    def outsideTemperature(self: MccsFieldStation) -> float:
        """
        Return the OutsideTemperature.

        :return: the OutsideTemperature.
        :raises ValueError: if outside temperature not read yet.
        """
        if self.component_manager.outsideTemperature is None:
            self.logger.warning("Outside temperature not read yet")
            raise ValueError("Outside temperature not read yet")
        return self.component_manager.outsideTemperature

    @attribute(dtype="DevString")
    def healthReport(self: MccsFieldStation) -> str:
        """
        Get the health report.

        :return: the health report.
        """
        return self._health_report
