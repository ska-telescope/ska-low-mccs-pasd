# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FieldStation device."""

from __future__ import annotations

from typing import Any, Optional

from ska_control_model import CommunicationStatus, PowerState
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import SubmittedSlowCommand
from tango.server import attribute, device_property

from .field_station_component_manager import FieldStationComponentManager

__all__ = ["MccsFieldStation", "main"]


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
        super().init_device()

        message = (
            "Initialised MccsFieldStation device with properties:\n"
            f"type:{type(self.SmartBoxFQDNs)}"
            f"\tFndhFQDN: {self.FndhFQDN}\n"
            f"\tSmartBoxFQDN: {self.SmartBoxFQDNs}\n"
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
            self._communication_state_changed_callback,
            self._component_state_callback,
        )

    def init_command_objects(self: MccsFieldStation) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for (command_name, method_name) in [
            ("PowerOnAntenna", "turn_on_antenna"),
        ]:
            self.register_command_object(
                command_name,
                SubmittedSlowCommand(
                    command_name,
                    self._command_tracker,
                    self.component_manager,
                    method_name,
                    callback=None,
                    logger=self.logger,
                ),
            )

    # ----------
    # Callbacks
    # ----------
    def _communication_state_callback(
        self: MccsFieldStation,
        communication_state: CommunicationStatus,
        device_name: str,
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
