# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FieldStation device."""

from __future__ import annotations

import importlib.resources
import json
from typing import Any, Final, Optional

from ska_control_model import CommunicationStatus, PowerState, ResultCode
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import JsonValidator, SubmittedSlowCommand
from tango.server import attribute, command, device_property

from .field_station_component_manager import FieldStationComponentManager

__all__ = ["MccsFieldStation", "main"]


DevVarLongStringArrayType = tuple[list[ResultCode], list[str]]

SMARTBOX_NUMBER = 24
SMARTBOX_PORTS = 12


class MccsFieldStation(SKABaseDevice):
    """An implementation of the FieldStation device."""

    # -----------------
    # Device Properties
    # -----------------
    StationName = device_property(dtype=(str), mandatory=True)
    ConfigurationHost = device_property(dtype=(str), mandatory=True)
    FndhFQDN = device_property(dtype=(str), mandatory=True)
    SmartBoxFQDNs = device_property(dtype=(str,), mandatory=True)
    ConfigurationPort = device_property(dtype=(int), default_value=8081)
    ConfigurationTimeout = device_property(dtype=(int), default_value=4)
    # --------------
    # Initialisation
    # --------------

    def init_device(self: MccsFieldStation) -> None:
        """Initialise the device."""
        self._antenna_power_json: Optional[str] = None
        super().init_device()

        message = (
            "Initialised MccsFieldStation device with properties:\n"
            f"\tFndhFQDN: {self.FndhFQDN}\n"
            f"\tSmartBoxFQDNs: {self.SmartBoxFQDNs}\n"
            f"\tConfigurationHost: {self.ConfigurationHost}\n"
            f"\tConfigurationPort: {self.ConfigurationPort}\n"
            f"\tConfigurationTimeout: {self.ConfigurationTimeout}\n"
            f"\tStationName: {self.StationName}\n"
        )
        self.logger.info(message)

    def create_component_manager(
        self: MccsFieldStation,
    ) -> FieldStationComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return FieldStationComponentManager(
            self.logger,
            self.ConfigurationHost,
            self.ConfigurationPort,
            self.ConfigurationTimeout,
            self.StationName,
            self.FndhFQDN,
            self.SmartBoxFQDNs,
            self._communication_state_callback,
            self._component_state_callback,
            self._on_antenna_power_change,
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

        mask_schema: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.field_station.schemas",
                "MccsFieldStation_UpdateAntennaMask.json",
            )
        )

        antenna_mapping_schema: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.field_station.schemas",
                "MccsFieldStation_UpdateAntennaMapping.json",
            )
        )

        smartbox_mapping_schema: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.field_station.schemas",
                "MccsFieldStation_UpdateSmartboxMapping.json",
            )
        )

        for command_name, method_name, schema in [
            ("PowerOnAntenna", "turn_on_antenna", None),
            ("PowerOffAntenna", "turn_off_antenna", None),
            ("UpdateAntennaMask", "update_antenna_mask", mask_schema),
            ("UpdateAntennaMapping", "update_antenna_mapping", antenna_mapping_schema),
            (
                "UpdateSmartboxMapping",
                "update_smartbox_mapping",
                smartbox_mapping_schema,
            ),
            ("LoadConfiguration", "load_configuration", None),
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

    def _communication_state_callback(
        self: MccsFieldStation,
        communication_state: CommunicationStatus,
        device_name: Optional[str] = None,
    ) -> None:
        # We need to subscribe and re-emit change events.
        super()._communication_state_changed(communication_state)

    def _component_state_callback(
        self: MccsFieldStation,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if "outsidetemperature" in kwargs:
            self.push_change_event("outsideTemperature", kwargs["outsidetemperature"])
        super()._component_state_changed(fault=fault, power=power)

    def _on_antenna_power_change(
        self: MccsFieldStation, antenna_powers: dict[int, PowerState]
    ) -> None:
        """
        Handle a change in antenna power.

        :param antenna_powers: a dictionary containing all
            256 antenna power states
        """
        # Antenna powers have changed delete json and reload.
        # pylint: disable=attribute-defined-outside-init
        self._antenna_power_json = None
        self.push_change_event("antennaPowerStates", json.dumps(antenna_powers))

    # --------
    # Commands
    # --------

    @command(dtype_out="DevVarLongStringArray")
    def LoadConfiguration(
        self: MccsFieldStation,
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up a antenna.

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("LoadConfiguration")
        (return_code, message) = handler()
        return ([return_code], [message])

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

    @command(dtype_in="DevShort", dtype_out="DevVarLongStringArray")
    def PowerOnAntenna(
        self: MccsFieldStation, antenna_no: int
    ) -> DevVarLongStringArrayType:
        """
        Turn on an antenna.

        :param antenna_no: Antenna number to turn on.

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("PowerOnAntenna")
        (return_code, message) = handler(antenna_no)
        return ([return_code], [message])

    @command(dtype_in="DevShort", dtype_out="DevVarLongStringArray")
    def PowerOffAntenna(
        self: MccsFieldStation, antenna_no: int
    ) -> DevVarLongStringArrayType:
        """
        Turn off an antenna.

        :param antenna_no: Antenna number to turn on.

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("PowerOffAntenna")
        (return_code, message) = handler(antenna_no)
        return ([return_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def UpdateAntennaMask(
        self: MccsFieldStation, argin: str
    ) -> DevVarLongStringArrayType:
        """
        Manually update the antenna mask.

        :param argin: the configuration for the antenna mask in
            stringified json format

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("UpdateAntennaMask")
        (return_code, message) = handler(argin)
        return ([return_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def UpdateAntennaMapping(
        self: MccsFieldStation, argin: str
    ) -> DevVarLongStringArrayType:
        """
        Manually update the antenna mapping.

        :param argin: the configuration for the antenna mapping in
            stringified json format

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("UpdateAntennaMapping")
        (return_code, message) = handler(argin)
        return ([return_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def UpdateSmartboxMapping(
        self: MccsFieldStation, argin: str
    ) -> DevVarLongStringArrayType:
        """
        Manually update the smartbox mapping.

        :param argin: the configuration for the smartbox mapping in
            stringified json format

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("UpdateSmartboxMapping")
        (return_code, message) = handler(argin)
        return ([return_code], [message])

    @command(dtype_out="DevVarLongStringArray")
    def UpdateConfiguration(self: MccsFieldStation) -> DevVarLongStringArrayType:
        """
        Update the configuration of the FieldStation.

        This updates the antenna mask, antenna mapping and smartbox mapping.

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("UpdateConfiguration")
        (return_code, message) = handler()
        return ([return_code], [message])

    # ----------
    # Attributes
    # ----------

    @attribute(dtype="DevString", label="AntennaMask")
    def antennaMask(self: MccsFieldStation) -> str:
        """
        Return the antenna mask attribute.

        :return: antenna mask
        """
        return json.dumps(self.component_manager._antenna_mask_pretty)

    @attribute(dtype="DevString", label="AntennaMapping")
    def antennaMapping(self: MccsFieldStation) -> str:
        """
        Return the antenna mapping attribute.

        :return: antenna mappping
        """
        return json.dumps(self.component_manager._antenna_mapping_pretty)

    @attribute(dtype="DevString", label="SmartboxMapping")
    def smartboxMapping(self: MccsFieldStation) -> str:
        """
        Return the smartbox mapping attribute.

        :return: smartbox mapping
        """
        return json.dumps(self.component_manager._smartbox_mapping_pretty)

    @attribute(dtype="float", label="OutsideTemperature")
    def outsideTemperature(self: MccsFieldStation) -> float:
        """
        Return the OutsideTemperature.

        :return: the OutsideTemperature
        """
        # TODO: MCCS-1848 will reimplement this.
        return 28.0

    @attribute(dtype="DevString", label="antennaPowerStates")
    def antennaPowerStates(self: MccsFieldStation) -> str:
        """
        Return the logical antenna powers.

        :return: the power of the logical antennas.
        """
        # pylint: disable=attribute-defined-outside-init
        if self._antenna_power_json is None:
            self._antenna_power_json = json.dumps(self.component_manager.antenna_powers)
        return self._antenna_power_json

    @attribute(dtype="float", label="OutsideTemperature")
    def outsideTemperature(self: MccsFieldStation) -> float:
        """
        Return the OutsideTemperature.

        :return: the OutsideTemperature.
        """
        return self.component_manager.outsideTemperature


# ----------
# Run server
# ----------
def main(*args: str, **kwargs: str) -> int:
    """
    Entry point for module.

    :param args: positional arguments
    :param kwargs: named arguments

    :return: exit code
    """
    return MccsFieldStation.run_server(args=args or None, **kwargs)


if __name__ == "__main__":
    main()
