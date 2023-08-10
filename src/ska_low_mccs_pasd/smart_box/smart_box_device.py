# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS SmartBox device."""

from __future__ import annotations

import sys
from typing import Any, Final, Optional, cast

import tango
from ska_control_model import CommunicationStatus, HealthState, PowerState, ResultCode
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import DeviceInitCommand, SubmittedSlowCommand
from tango.server import command, device_property

from .smart_box_component_manager import SmartBoxComponentManager
from .smartbox_health_model import SmartBoxHealthModel

__all__ = ["MccsSmartBox", "main"]


class MccsSmartBox(SKABaseDevice):
    """An implementation of the SmartBox device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    FndhPort = device_property(dtype=int, mandatory=True)
    PasdFQDN = device_property(dtype=(str), mandatory=True)
    FndhFQDN = device_property(dtype=(str), mandatory=True)
    SmartBoxNumber = device_property(dtype=int, mandatory=True)

    PORT_COUNT: Final = 12

    # TODO: MCCS-1480: create a yaml file containing
    # coupled MccsSmartBox MccsPasdBus attributes.
    ATTRIBUTES = [
        ("ModbusRegisterMapRevisionNumber", int, None),
        ("PcbRevisionNumber", int, None),
        ("CpuId", str, None),
        ("ChipId", str, None),
        ("FirmwareVersion", str, None),
        ("Uptime", int, None),
        ("PasdStatus", str, None),
        ("SysAddress", int, None),
        ("LedPattern", str, None),
        ("InputVoltage", float, None),
        ("PowerSupplyOutputVoltage", float, None),
        ("PowerSupplyTemperature", float, None),
        ("PcbTemperature", float, None),
        ("FemAmbientTemperature", float, None),
        ("FemCaseTemperatures", (float,), 2),
        ("FemHeatsinkTemperatures", (float,), 2),
        ("PortsConnected", (bool,), PORT_COUNT),
        ("PortForcings", (str,), PORT_COUNT),
        ("PortBreakersTripped", (bool,), PORT_COUNT),
        ("PortsDesiredPowerOnline", (bool,), PORT_COUNT),
        ("PortsDesiredPowerOffline", (bool,), PORT_COUNT),
        ("PortsPowerSensed", (bool,), PORT_COUNT),
        ("PortsCurrentDraw", (float,), PORT_COUNT),
    ]

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
        super().init_device()
        self._smartbox_state: dict[str, Any] = {}
        self._setup_smartbox_attributes()

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tFndhPort: {self.FndhPort}\n"
            f"\tPasdFQDN: {self.PasdFQDN}\n"
            f"\tFndhFQDN: {self.FndhFQDN}\n"
            f"\tSmartBoxNumber: {self.SmartBoxNumber}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

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
    def create_component_manager(
        self: MccsSmartBox,
    ) -> SmartBoxComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return SmartBoxComponentManager(
            self.logger,
            self._communication_state_changed,
            self._component_state_callback,
            self._attribute_changed_callback,
            self.PORT_COUNT,
            self.FndhPort,
            self.PasdFQDN,
            self.FndhFQDN,
            self.SmartBoxNumber,
        )

    def init_command_objects(self: MccsSmartBox) -> None:
        """Initialise the command handlers for this device."""
        super().init_command_objects()

        for command_name, method_name in [
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
        self: MccsSmartBox, port_number: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up a port.

        This may or may not have a Antenna attached.

        :param port_number: the smartbox port to power up

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOnPort")

        result_code, message = handler(port_number)
        return ([result_code], [message])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def PowerOffPort(
        self: MccsSmartBox, port_number: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power down a port.

        This may or may not have a Antenna attached.

        :param port_number: the smartbox port to power down

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOffPort")
        result_code, message = handler(port_number)
        return ([result_code], [message])

    # ----------
    # Attributes
    # ----------
    def _setup_smartbox_attributes(self: MccsSmartBox) -> None:
        for slug, data_type, length in self.ATTRIBUTES:
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
        self._smartbox_state[attribute_name.lower()] = None
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
        smartbox_attribute.set_value(
            self._smartbox_state[smartbox_attribute.get_name().lower()]
        )

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
            self._component_state_callback(power=PowerState.UNKNOWN)
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_callback(power=self.component_manager._power_state)

        super()._communication_state_changed(communication_state)

        self._health_model.update_state(communicating=True)

    def _component_state_callback(  # pylint: disable=too-many-arguments
        self: MccsSmartBox,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        pasdbus_status: Optional[str] = None,
        fqdn: Optional[str] = None,
        power_state: Optional[PowerState] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param pasdbus_status: the status of the pasd_bus
        :param fqdn: the fqdn of the device passing calling.
        :param power_state: the power_state change.
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if fqdn is not None:
            # TODO: use this in the health model.
            if power == PowerState.UNKNOWN:
                # If a proxy calls back with a unknown power. As a precaution it is
                # assumed that communication is NOT_ESTABLISHED.
                self._communication_state_changed(CommunicationStatus.NOT_ESTABLISHED)
            return
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
        self: MccsSmartBox, attr_name: str, attr_value: HealthState
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
        try:
            assert (
                len(
                    [
                        attr
                        for (attr, _, _) in self.ATTRIBUTES
                        if attr == attr_name or attr.lower() == attr_name
                    ]
                )
                > 0
            )

            self._smartbox_state[attr_name] = attr_value
            self.push_change_event(attr_name, attr_value)
            self.push_archive_event(attr_name, attr_value)

        except AssertionError:
            self.logger.debug(
                f"""The attribute {attr_name} pushed from MccsPasdBus
                device does not exist in MccsSmartBox"""
            )


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
