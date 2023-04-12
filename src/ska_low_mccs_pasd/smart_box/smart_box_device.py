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
from typing import Any, List, Optional, cast

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

__all__ = ["MccsSmartBox", "main"]


class MccsSmartBox(SKABaseDevice):
    """An implementation of the SmartBox device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    FndhPort = device_property(dtype=int, default_value=0)
    PasdFQDNs = device_property(dtype=(str,), default_value=[])
    #TODO: do we want both fndhPort and SmartBoxNumber?
    SmartBoxNumber = device_property(dtype=int, default_value=1)

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
        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_model: SmartBoxHealthModel

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
        
        # setup all attributes.
        self._smartbox_state: dict[str, Any] = {}
        self._setup_smartbox_attributes()

        message = (
            "Initialised MccsSmartBox device with properties:\n"
            f"\tFndhPort: {self.FndhPort}\n"
            f"\tPasdFQDNs: {self.PasdFQDNs}\n"
            f"\tSmartBoxNumber: {self.SmartBoxNumber}\n"
        )
        self.logger.info(message)

    def _init_state_model(self: MccsSmartBox) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = SmartBoxHealthModel(self._health_changed_callback)
        self.set_change_event("healthState", True, False)
        self.set_archive_event("healthState", True, False)
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
            self._attribute_changed_callback,
            self.PasdFQDNs,
            self.FndhPort,
            self.SmartBoxNumber,
        )

    def init_command_objects(self: MccsSmartBox) -> None:
        """Initialise the command handlers for this device."""
        super().init_command_objects()

        for (command_name, method_name) in [
            ("PowerOnPort", "turn_on_port"),
            ("PowerOffPort", "turn_off_port"),
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
        self: MccsSmartBox, argin: int
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

    # ----------
    # Attributes
    # ----------
    def _setup_smartbox_attributes(self: MccsSmartBox) -> None:
        for (slug, data_type, length) in [
            ("ModbusRegisterMapRevisionNumber", int, None),
            ("PcbRevisionNumber", int, None),
            ("CpuId", int, None),
            ("ChipId", int, None),
            ("FirmwareVersion", str, None),
            ("Uptime", int, None),
            ("Status", str, None),
            ("LedPattern", str, None),
            ("InputVoltage", float, None),
            ("PowerSupplyOutputVoltage", float, None),
            ("PowerSupplyTemperature", float, None),
            ("OutsideTemperature", float, None),
            ("PcbTemperature", float, None),
            ("PortsConnected", (bool,), self.PORT_COUNT),
            ("PortForcings", (str,), self.PORT_COUNT),
            ("PortBreakersTripped", (bool,), self.PORT_COUNT),
            ("PortsDesiredPowerOnline", (bool,), self.PORT_COUNT),
            ("PortsDesiredPowerOffline", (bool,), self.PORT_COUNT),
            ("PortsPowerSensed", (bool,), self.PORT_COUNT),
            ("PortsCurrentDraw", (float,), self.PORT_COUNT),
        ]:
            self._setup_smartbox_attribute(
                f"{slug}",
                cast(type | tuple[type], data_type),
                max_dim_x=length,
            )

    def _setup_smartbox_attribute(
        self: MccsSmartBox,
        attribute_name: str,
        data_type: type | tuple[type],
        max_dim_x: Optional[int] = None,
    ) -> None:
        self._smartbox_state[attribute_name] = None
        attr = tango.server.attribute(
            name=attribute_name,
            dtype=data_type,
            access=tango.AttrWriteType.READ,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fread="_read_smartbox_attribute",
        ).to_attr()
        self.add_attribute(attr, self._read_smartbox_attribute, None, None)
        self.set_change_event(attribute_name, True, False)
        self.set_archive_event(attribute_name, True, False)

    def _read_smartbox_attribute(self, smartbox_attribute: tango.Attribute) -> None:
        smartbox_attribute.set_value(self._smartbox_state[smartbox_attribute.get_name()])

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
            self._component_state_changed_callback(power = PowerState.UNKNOWN)

        super()._communication_state_changed(communication_state)

        self._health_model.update_state(communicating=True)

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
            self.push_archive_event("healthState", health)

    def _attribute_changed_callback(
        self: MccsSmartBox,
        attr_name: str,
        attr_value: HealthState
    ) -> None:
        """
        Handle changes to subscribed attributes. 

        This is a callback hook we pass to the component manager, 
        It is called when a subscribed attribute changes. 
        It is responsible for:
        - updating this device attribute
        - pushing a change event to any listeners.

        :param attr_name: the name of the attribute that needs updating
        :param attr_value: the value to update with.
        """
        self._smartbox_state[attr_name] = attr_value
        self.push_change_event(attr_name, attr_value)
        self.push_archive_event(attr_name, attr_value)
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
