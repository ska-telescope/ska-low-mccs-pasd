# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FieldStation device."""

from __future__ import annotations

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
    """
    An implementation of the FieldStation device.

    Note: this is a initial Stub device.
    Note: this cannot be tested using the MultiDeviceTestContext
    due to lack of support for Forwarded Attributes.
    """

    # -----------------
    # Device Properties
    # -----------------
    FndhFQDN = device_property(dtype=(str), mandatory=True)
    SmartBoxFQDNs = device_property(dtype=(str,), mandatory=True)

    OutsideTemperature = attribute(
        name="outsideTemperature", label="outsideTemperature", forwarded=True
    )
    # --------------
    # Initialisation
    # --------------

    def init_device(self: MccsFieldStation) -> None:
        """Initialise the device."""
        self._antenna_mask = [False for _ in range(256 + 1)]
        self._antenna_mapping = {
            smartbox_no * SMARTBOX_PORTS
            + smartbox_port
            + 1: [smartbox_no + 1, smartbox_port + 1]
            for smartbox_no in range(0, SMARTBOX_NUMBER)
            for smartbox_port in range(0, SMARTBOX_PORTS)
            if smartbox_no * SMARTBOX_PORTS + smartbox_port < 256
        }
        self._smartbox_mapping = {
            port + 1: port + 1 for port in range(0, SMARTBOX_NUMBER)
        }
        super().init_device()

        message = (
            "Initialised MccsFieldStation device with properties:\n"
            f"\tFndhFQDN: {self.FndhFQDN}\n"
            f"\tSmartBoxFQDNs: {self.SmartBoxFQDNs}\n"
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
            self.FndhFQDN,
            self.SmartBoxFQDNs,
            self._antenna_mask,
            self._antenna_mapping,
            self._smartbox_mapping,
            self._communication_state_callback,
            self._component_state_callback,
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
            ("PowerOnAntenna", "turn_on_antenna", None),
            ("PowerOffAntenna", "turn_off_antenna", None),
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

    # ----------
    # Callbacks
    # ----------
    def _communication_state_callback(
        self: MccsFieldStation,
        communication_state: CommunicationStatus,
        device_name: Optional[str] = None,
    ) -> None:
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
        super()._component_state_changed(fault=fault, power=power)

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

    @command(dtype_in="DevShort", dtype_out="DevVarLongStringArray")
    def PowerOnAntenna(
        self: MccsFieldStation, antenna_no: int
    ) -> DevVarLongStringArrayType:
        """
        Turn on an antenna.

        :param argin: the configuration for the device in stringified json format

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

        :param argin: the configuration for the device in stringified json format

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("PowerOffAntenna")
        (return_code, message) = handler(antenna_no)
        return ([return_code], [message])


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
