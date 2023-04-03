# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS SmartBox device."""

from __future__ import annotations

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
from ska_tango_base.commands import DeviceInitCommand, SubmittedSlowCommand
from tango.server import attribute, command, device_property

from .smart_box_component_manager import SmartBoxComponentManager
from .smartbox_health_model import SmartBoxHealthModel

__all__ = ["MccsSmartBox", "main"]  # TODO: Should we include main in __all__?


class MccsSmartBox(SKABaseDevice):
    """An implementation of the SmartBox device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    FndhPort = device_property(dtype=int, default_value=0)
    PasdFQDNs = device_property(dtype=(str,), default_value=[])

    PORT_COUNT = 12

    # ---------------
    # Initialisation
    # ---------------
    def __init__(self: MccsSmartBox, *args: Any, **kwargs: Any) -> None:
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
        self._health_model: SmartBoxHealthModel
        self._hardware_attributes: dict[str, Any] = {}

    def init_device(self: MccsSmartBox) -> None:
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
            "Initialised MccsSmartBox device with properties:\n"
            f"\tFndhPort: {self.FndhPort}\n"
            f"\tPasdFQDNs: {self.PasdFQDNs}\n"
        )
        self.logger.info(message)

    def _init_state_model(self: MccsSmartBox) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = SmartBoxHealthModel(self._health_changed_callback)
        self.set_change_event("healthState", True, False)

    # ----------
    # Properties
    # ----------

    class InitCommand(DeviceInitCommand):
        """Initialisation command class for this base device."""

        def do(
            self: MccsSmartBox.InitCommand, *args: Any, **kwargs: Any
        ) -> tuple[ResultCode, str]:
            """
            Initialise the attributes of this MccsSmartBox.

            :param args: additional positional arguments; unused here
            :param kwargs: additional keyword arguments; unused here

            :return: a resultcode, message tuple
            """
            # self._device.set_change_event("antennasTripped", True, False)
            self._completed()
            return (ResultCode.OK, "Init command completed OK")

    # --------------
    # Initialization
    # --------------
    def create_component_manager(self: MccsSmartBox) -> SmartBoxComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return SmartBoxComponentManager(
            self.logger,
            self._communication_state_changed,
            self._component_state_changed_callback,
            "low-mccs-pasd/pasdbus/001",  # TODO: get fqdn from property
            self.FndhPort,
            self.PasdFQDNs,
        )

    def init_command_objects(self: MccsSmartBox) -> None:
        """Initialise the command handlers for this device."""
        super().init_command_objects()

        for (command_name, method_name) in [
            ("PowerOnPort", "turn_on_port"),
            ("PowerOffPort", "turn_off_port"),
            ("GetAntennaInfo", "get_antenna_info"),
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
    # Commands
    # ----------
    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def PowerOnPort(
        self: MccsSmartBox, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up a Antenna's LNA.

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
        self: MccsSmartBox, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power down a Antenna's LNA.

        :param argin: the logical id of the TPM to power down

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOffPort")
        result_code, message = handler(argin)
        return ([result_code], [message])

    # @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    # def PowerUpAntennas(
    #     self: MccsSmartBox,
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
    #     self: MccsSmartBox,
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

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def GetAntennaInfo(self: MccsSmartBox, argin: int) -> tuple[list[Any], list[Any]]:
        """
        Return information about relationship of an antenna to other PaSD components.

        :param argin: antenna to get info from

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("GetAntennaInfo")
        result_code, unique_id = handler(argin)
        return ([result_code], [unique_id])

    # ----------
    # Attributes
    # ----------

    # TODO: Copy over all SmartBox related attributes from the pasdBus
    @attribute(dtype=PowerState, label="a list of power states")
    def portPowerStates(
        self: MccsSmartBox,
    ) -> List[PowerState]:
        """
        Handle a Tango attribute read of the power state of TPM 4.

        :return: the power state of TPM 4.
        """
        return self._port_power_states

    # ----------
    # Callbacks
    # ----------
    def _communication_state_changed(
        self: MccsSmartBox, communication_state: CommunicationStatus
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
        self: MccsSmartBox, port_power_states: list[PowerState]
    ) -> None:
        if self._port_power_states != port_power_states:
            self._port_power_states = port_power_states
            self.push_change_event("portPowerState", port_power_states)

    def _component_state_changed_callback(
        self: MccsSmartBox,
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

    def _health_changed_callback(self: MccsSmartBox, health: HealthState) -> None:
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
    Launch an `MccsSmartBox` Tango device server instance.

    :param args: positional arguments, passed to the Tango device
    :param kwargs: keyword arguments, passed to the sever

    :return: the Tango server exit code
    """
    return MccsSmartBox.run_server(args=args or None, **kwargs)


if __name__ == "__main__":
    main()
