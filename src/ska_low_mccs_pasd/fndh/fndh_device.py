# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FNDH device."""

from __future__ import annotations

import logging
import threading
from typing import Any, List, Optional

import tango
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
)
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import (
    DeviceInitCommand,
    FastCommand,
    SubmittedSlowCommand,
)
from tango.server import attribute, command, device_property

from .fndh_component_manager import FndhComponentManager
from .fndh_health_model import FndhHealthModel

__all__ = ["MccsFNDH", "main"]


class MccsFNDH(SKABaseDevice):
    """An implementation of the FNDH device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    PasdFQDNs = device_property(dtype=(str,), default_value=[])

    PORT_COUNT = 28

    # ---------------
    # Initialisation
    # ---------------
    def __init__(self: MccsFNDH, *args: Any, **kwargs: Any) -> None:
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

        # Initialise with unknown.
        self._port_power_states = [PowerState.UNKNOWN] * self.PORT_COUNT
        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_model: FndhHealthModel
        self._port_count = self.PORT_COUNT

    def init_device(self: MccsFNDH) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        util = tango.Util.instance()
        util.set_serial_model(tango.SerialModel.NO_SYNC)
        self._max_workers = 10
        self._power_state_lock = threading.RLock()
        super().init_device()

        message = (
            "Initialised MccsFNDH device with properties:\n"
            f"\tPasdFQDNs: {self.PasdFQDNs}\n"
        )
        self.logger.info(message)

    def _init_state_model(self: MccsFNDH) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = FndhHealthModel(self._health_changed_callback)
        self.set_change_event("healthState", True, False)

    # ----------
    # Properties
    # ----------

    class InitCommand(DeviceInitCommand):
        """Initialisation command class for this base device."""

        def do(
            self: MccsFNDH.InitCommand, *args: Any, **kwargs: Any
        ) -> tuple[ResultCode, str]:
            """
            Initialise the attributes of this MccsFNDH.

            :param args: additional positional arguments; unused here
            :param kwargs: additional keyword arguments; unused here

            :return: a resultcode, message tuple
            """
            self._completed()
            return (ResultCode.OK, "Init command completed OK")

    # --------------
    # Initialization
    # --------------
    def create_component_manager(self: MccsFNDH) -> FndhComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return FndhComponentManager(
            self.logger,
            self._communication_state_changed,
            self._component_state_changed_callback,
            self.PasdFQDNs,
        )

    def init_command_objects(self: MccsFNDH) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for (command_name, method_name) in [
            ("PowerOnPort", "power_on_port"),
            ("PowerOffPort", "power_off_port"),
            ("PowerUp", "power_up"),
            ("PowerDown", "power_down"),
            ("Configure", "configure"),
            ("GetSmartBoxInfo", "get_smartbox_info"),
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
        self.register_command_object(
            "IsPortOn",
            self.IsPortOnCommand(self.component_manager, self.logger),
        )

    # ----------
    # Commands
    # ----------

    class IsPortOnCommand(FastCommand):
        """A class for the MccsAPIU's IsPortOnCommand() command."""

        def __init__(
            self: MccsFNDH.IsPortOnCommand,
            component_manager: FndhComponentManager,
            logger: Optional[logging.Logger] = None,
        ) -> None:
            """
            Initialise a new instance.

            :param component_manager: the device to which this command belongs.
            :param logger: a logger for this command to use.
            """
            self._component_manager = component_manager
            super().__init__(logger)

        def do(
            self: MccsFNDH.IsPortOnCommand,
            *args: int,
            **kwargs: Any,
        ) -> bool:
            """
            Stateless hook for device IsPortOnCommand() command.

            :param args: the logical antenna id of the antenna to power up
            :param kwargs: keyword args to the component manager method

            :return: True if the antenna is on.
            """
            port_id = args[0]
            result = self._component_manager.is_port_on()
            return result[port_id]

    @command(dtype_in="DevULong", dtype_out=bool)
    def IsPortOn(self: MccsFNDH, argin: int) -> bool:  # type: ignore[override]
        """
        Power up the antenna.

        :param argin: the logical antenna id of the antenna to power up

        :return: whether the specified antenna is on or not
        """
        handler = self.get_command_object("IsPortOn")
        return handler(argin)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def PowerOnPort(
        self: MccsFNDH, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up a port.

        This may or may not have a Antenna attached.
        The station has this port:antenna mapping from configuration files.

        :param argin: the logical id of the Antenna (LNA) to power up

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOnPort")

        result_code, message = handler(argin)
        return ([result_code], [message])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def PowerOffPort(
        self: MccsFNDH, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power down a port.

        This may or may not have a Antenna attached.
        The station has this port:antenna mapping from configuration files.

        :param argin: the logical id of the TPM to power down

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOffPort")
        result_code, message = handler(argin)
        return ([result_code], [message])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def GetSmartBoxInfo(self: MccsFNDH, antenna_id: int) -> tuple[list[Any], list[Any]]:
        """
        Return information about relationship of an antenna to other PaSD components.

        :param antenna_id: antenna id to query.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("GetSmartBoxInfo")
        result_code, unique_id = handler(antenna_id)
        return ([result_code], [unique_id])

    # @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    # def PowerUpAntennas(
    #     self: MccsFNDH,
    # ) -> tuple[list[ResultCode], list[Optional[str]]]:
    #     """
    #     Power up all Antenna LNA's.

    #     :return: A tuple containing a return code and a string message
    #         indicating status. The message is for information purposes
    #         only.
    #     """
    #     handler = self.get_command_object("PowerUpAntennas")
    #     result_code, message = handler()
    #     return ([result_code], [message])

    # @command(dtype_out="DevVarLongStringArray")
    # def PowerDownAntennas(
    #     self: MccsFNDH,
    # ) -> tuple[list[ResultCode], list[Optional[str]]]:
    #     """
    #     Power down all Antanna LNA's.

    #     :return: A tuple containing a return code and a string message
    #         indicating status. The message is for information purposes
    #         only.
    #     """
    #     handler = self.get_command_object("PowerDownAntennas")
    #     result_code, message = handler()
    #     return ([result_code], [message])

    # ----------
    # Attributes
    # ----------

    # TODO: Copy over all FNDH related attributes from the pasdBus
    @attribute(dtype=("DevBoolean",), max_dim_x=28, label="a list of power states")
    def portPowerStates(
        self: MccsFNDH,
    ) -> List[bool]:
        """
        Handle a Tango attribute read of the power state of TPM 4.

        :return: the power state of TPM 4.
        """
        return self.component_manager.is_port_on()

    @attribute(
        dtype=("DevString",),
        max_dim_x=256,
        label="smartboxStatuses",
    )
    def smartboxStatuses(self: MccsFNDH) -> list[str]:
        """
        Return each smartbox's status.

        :return: each smartbox's status.
        """
        return self.component_manager.smartbox_statuses()

    # ----------
    # Callbacks
    # ----------
    def _communication_state_changed(
        self: MccsFNDH, communication_state: CommunicationStatus
    ) -> None:
        self.logger.debug(
            "Device received callback from component manager that communication "
            "with the component is %s.",
            communication_state.name,
        )
        if communication_state != CommunicationStatus.ESTABLISHED:
            self._update_port_power_states([PowerState.UNKNOWN] * self._port_count)

        super()._communication_state_changed(communication_state)

        self._health_model.update_state(communicating=True)

    def _update_port_power_states(
        self: MccsFNDH, port_power_states: list[PowerState]
    ) -> None:
        if self._port_power_states != port_power_states:
            self._port_power_states = port_power_states
            self.push_change_event("portPowerState", port_power_states)

    def _component_state_changed_callback(
        self: MccsFNDH,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        pasdbus_status: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param pasdbus_status: the status of the FNDH
        :param kwargs: additional keyword arguments defining component
            state.
        """
        super()._component_state_changed(fault=fault, power=power)
        self._health_model.update_state(
            fault=fault, power=power, pasdbus_status=pasdbus_status
        )

    def _health_changed_callback(self: MccsFNDH, health: HealthState) -> None:
        """
        Handle change in this device's health state.

        This is a callback hook, called whenever the HealthModel's
        evaluated health state changes. It is responsible for updating
        the tango side of things i.e. making sure the attribute is up to
        date, and events are pushed.

        :param health: the new health value
        """
        if self._health_state != health:
            self._health_state = health
            self.push_change_event("healthState", health)


# ----------
# Run server
# ----------
def main(*args: str, **kwargs: str) -> int:
    """
    Launch an `MccsFNDH` Tango device server instance.

    :param args: positional arguments, passed to the Tango device
    :param kwargs: keyword arguments, passed to the sever

    :return: the Tango server exit code
    """
    return MccsFNDH.run_server(args=args or None, **kwargs)


if __name__ == "__main__":
    main()
