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
from typing import Any, Final, Optional, cast

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
        self._health_thresholds: dict[str, Any] = {
            "fndh": (1, 1, 1),  # Default thresholds for FNDH
            "smartboxes": (0, 1, 1),  # Default thresholds for SmartBoxes
        }

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

        self._health_rollup = self._setup_health_rollup()

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

    def _setup_health_rollup(
        self: MccsFieldStation,
    ) -> HealthRollup:
        #   Rollup is based on three configurable thresholds:
        # * the number of FAILED (or UNKNOWN) sources that cause health
        #   to roll up to overall FAILED;
        # * the number of FAILED (or UNKNOWN) sources that cause health
        #   to roll up to overall DEGRADED;
        # * the number of DEGRADED sources that cause health to roll up to
        #   overall DEGRADED.

        rollup_members = [self.FndhFQDN]
        # TODO: Make these thresholds fully dynamic based on deployment.
        thresholds = {}
        thresholds["fndh"] = self._health_thresholds["fndh"]
        if len(self.SmartBoxFQDNs) > 0:
            rollup_members.append("smartboxes")
            thresholds["smartboxes"] = self._health_thresholds["smartboxes"]

        health_rollup = HealthRollup(
            rollup_members,
            thresholds["fndh"],
            self._health_changed,
            self._health_summary_changed,
        )

        # Fndh Default Thresholds: 1 failed = failed, 1 failed = deg, 1 deg = deg
        if "smartboxes" in rollup_members:
            # SmartBox Default Thresholds: zero ok/all fail=fail, 1 fail=deg, 1 deg=deg
            health_rollup.define(
                "smartboxes", self.SmartBoxFQDNs, thresholds["smartboxes"]
            )

        return health_rollup

    def _redefine_health_rollup(self: MccsFieldStation) -> None:
        """
        Redefine the health rollup members and thresholds.

        Redefines the health rollup following a change in subdevice thresholds.
        This pulls the old/current healths from the health report, instantiates
        a new health_rollup instance and restores those healthstates.
        """

        def _flatten_dict(d: dict[str, Any]) -> dict[str, Any]:
            """
            Return a flattened dictionary given nested dicts.

            Returns a flattened dictionary containing the key-value pairs
            of the nested dictionaries. Where a key-value pair is itself
            a dictionary this will also be flattened and the parent key
            omitted.

            :param d: the nested dictionary to flatten
            :return: flattened dictionary.
            """

            def _flatten(d: dict[str, Any]) -> dict[str, Any]:
                items: list[Any] = []
                for k, v in d.items():
                    if isinstance(v, dict):
                        items.extend(_flatten(v).items())
                    else:
                        items.append((k, v))
                return dict(items)

            return _flatten(d)

        # Pull out the old healthstates.
        old_report = json.loads(self._health_report)
        old_subdevice_healths = _flatten_dict(old_report)
        old_online = self._health_rollup.online
        self._health_rollup = self._setup_health_rollup()
        self._health_rollup.online = old_online
        # Restore old healthstates.
        for subdevice, health in old_subdevice_healths.items():
            self._health_rollup.health_changed(subdevice, cast(HealthState, health))

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

    @attribute(
        dtype="DevString",
        format="%s",
    )
    def healthThresholds(self: MccsFieldStation) -> str:
        """
        Get the health params from the health model.

        Default health thresholds:

            "fndh": (f2f, d2f, d2d),
                tuple(int, int, int): Number of fndh failed before health failed,
                                      Number of fndh degraded before health failed,
                                      Number of fndh degraded before health degraded
            "smartboxes": (f2f, d2f, d2d),
                tuple(int, int, int): Number of smartboxes failed before health failed,
                                      Number of smartboxes degraded before health fail,
                                      Number of smartboxes degraded before health deg.

        :return: the health params
        """
        return json.dumps(self._health_thresholds)

    @healthThresholds.write  # type: ignore[no-redef]
    def healthThresholds(self: MccsFieldStation, argin: str) -> None:
        """
        Set the params for health transition rules.

        Default health thresholds:

            "fndh": (f2f, d2f, d2d),
                tuple(int, int, int): Number of fndh failed before health failed,
                                      Number of fndh degraded before health failed,
                                      Number of fndh degraded before health degraded
            "smartboxes": (f2f, d2f, d2d),
                tuple(int, int, int): Number of smartboxes failed before health failed,
                                      Number of smartboxes degraded before health fail,
                                      Number of smartboxes degraded before health deg.


        :param argin: JSON-string of dictionary of health thresholds
        """
        thresholds = json.loads(argin)
        for key, threshold in thresholds.items():
            if key not in self._health_thresholds:
                self.logger.info(
                    f"Invalid Key Supplied: {key}. "
                    f"Allowed keys: {self._health_thresholds.keys()}"
                )
                continue
            self._health_thresholds[key] = threshold

            # TODO: Modify rollup classes to allow this.
            # Redefine health thresholds if needed.
            # if key == "fndh":
            #     self._health_rollup.define("fndh", self.FndhFQDNs, threshold)
            # if key == "smartboxes":
            #     self._health_rollup.define("smartboxes", self.SmartBoxFQDNs, thresh)
        # If we changed thresholds for subdevices, redefine health rollup.
        if any(subdevice in thresholds for subdevice in ["fndh", "smartboxes"]):
            self.logger.info("Reconfiguring subdevice health thresholds.")
            self._redefine_health_rollup()
