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
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Optional, cast

import tango
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
    TaskStatus,
)
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import (
    DeviceInitCommand,
    FastCommand,
    JsonValidator,
    SubmittedSlowCommand,
)
from tango.device_attribute import ExtractAs
from tango.server import attribute, command, device_property

from ska_low_mccs_pasd.pasd_bus.pasd_bus_register_map import DesiredPowerEnum

from ..pasd_controllers_configuration import ControllerDict, PasdControllersConfig
from .fndh_component_manager import FndhComponentManager
from .fndh_health_model import FndhHealthModel

__all__ = ["MccsFNDH", "main"]


DevVarLongStringArrayType = tuple[list[ResultCode], list[str]]


@dataclass
class FNDHAttribute:
    """Class representing the internal state of a FNDH attribute."""

    value: Any
    quality: tango.AttrQuality
    timestamp: float


# pylint: disable=too-many-instance-attributes
class MccsFNDH(SKABaseDevice[FndhComponentManager]):
    """An implementation of the FNDH device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    PasdFQDN: Final = device_property(dtype=(str), mandatory=True)

    # ---------
    # Constants
    # ---------
    CONFIG: Final[ControllerDict] = PasdControllersConfig.get_fndh()
    TYPES: Final[dict[str, type]] = {
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "DesiredPowerEnum": DesiredPowerEnum,
    }

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
        self._port_power_states = [PowerState.UNKNOWN] * self.CONFIG["number_of_ports"]
        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_model: FndhHealthModel
        self._overCurrentThreshold: float
        self._overVoltageThreshold: float
        self._humidityThreshold: float

    def init_device(self: MccsFNDH) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        super().init_device()

        # Setup attributes shared with the MccsPasdBus.
        self._fndh_attributes: dict[str, FNDHAttribute] = {}
        self._setup_fndh_attributes()

        # Attributes for specific ports on the FNDH.
        # These attributes are a breakdown of the portPowerSensed
        # attribute. The reason is to allow smartbox's to subscribe to
        # their power state.
        for port in range(1, self.CONFIG["number_of_ports"] + 1):
            attr_name = f"Port{port}PowerState"
            self._setup_fndh_attribute(
                attr_name, PowerState, tango.AttrWriteType.READ, 1, PowerState.UNKNOWN
            )

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tPasdFQDN: {self.PasdFQDN}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def _init_state_model(self: MccsFNDH) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = FndhHealthModel(self._health_changed_callback)
        self.set_change_event("healthState", True, False)
        self.set_archive_event("healthState", True, False)

    def create_component_manager(self: MccsFNDH) -> FndhComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return FndhComponentManager(
            self.logger,
            self._communication_state_changed,
            self._component_state_changed_callback,
            self._attribute_changed_callback,
            self._update_port_power_states,
            self.PasdFQDN,
        )

    def init_command_objects(self: MccsFNDH) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for command_name, method_name in [
            ("PowerOnPort", "power_on_port"),
            ("PowerOffPort", "power_off_port"),
            ("SetPortPowers", "set_port_powers"),
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
            "PortPowerState",
            self.PortPowerStateCommand(self, self.logger),
        )
        self.register_command_object(
            "Configure",
            self.ConfigureCommand(self, self.logger),
        )

    # ----------
    # Commands
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
            self._device._isAlive = True
            self._device._overCurrentThreshold = 0.0
            self._device._overVoltageThreshold = 0.0
            self._device._humidityThreshold = 0.0
            return (ResultCode.OK, "Init command completed OK")

    class ConfigureCommand(FastCommand):
        """
        Class for handling the Configure() command.

        This command takes as input a JSON string that conforms to the
        following schema:

        .. code-block:: json

           {
               "type": "object",
               "properties": {
                   "overCurrentThreshold": {"type": "number"},
                   "overVoltageThreshold": {"type": "number"},
                   "humidityThreshold": {"type": "number"},
               },
           }

        """

        SCHEMA: Final = {
            "type": "object",
            "properties": {
                "overCurrentThreshold": {"type": "number"},
                "overVoltageThreshold": {"type": "number"},
                "humidityThreshold": {"type": "number"},
            },
        }

        def __init__(
            self: MccsFNDH.ConfigureCommand,
            device: MccsFNDH,
            logger: Optional[logging.Logger] = None,
        ) -> None:
            """
            Initialise a new ConfigureCommand instance.

            :param device: the device that this command acts upon
            :param logger: a logger for this command to use.
            """
            self._device = device
            validator = JsonValidator("Configure", self.SCHEMA, logger)
            super().__init__(logger, validator)

        def do(
            self: MccsFNDH.ConfigureCommand,
            *args: Any,
            **kwargs: Any,
        ) -> tuple[TaskStatus, str]:
            """
            Implement :py:meth:`.MccsFNDH.Configure` command functionality.

            :param args: Positional arguments. This should be empty and
                is provided for type hinting purposes only.
            :param kwargs: keyword arguments unpacked from the JSON
                argument to the command.

            :return: A tuple containing a return code and a string
                message indicating status. The message is for
                information purpose only.
            """
            over_current_threshold = kwargs.get("overCurrentThreshold")
            if over_current_threshold is not None:
                self._device._overCurrentThreshold = over_current_threshold
                self.logger.debug(
                    f"Over-current threshold set to {over_current_threshold}."
                )

            over_voltage_threshold = kwargs.get("overVoltageThreshold")
            if over_voltage_threshold is not None:
                self._device._overVoltageThreshold = over_voltage_threshold
                self.logger.debug(
                    f"Over-voltage threshold set to {over_voltage_threshold}."
                )

            humidity_threshold = kwargs.get("humidityThreshold")
            if humidity_threshold is not None:
                self._device._humidityThreshold = humidity_threshold
                self.logger.debug(f"Humidity threshold set to {humidity_threshold}.")

            return (TaskStatus.COMPLETED, "Configure completed OK")

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def Configure(self: MccsFNDH, argin: str) -> DevVarLongStringArrayType:
        """
        Configure the Fndh device attributes.

        :param argin: the configuration for the device in stringified json format

        :return: A tuple containing a return code and a string
            message indicating status. The message is for
            information purpose only.
        """
        handler = self.get_command_object("Configure")
        (return_code, message) = handler(argin)
        return ([return_code], [message])

    class PortPowerStateCommand(FastCommand):
        """A class for the MccsFndh PortPowerStateCommand() command."""

        def __init__(
            self: MccsFNDH.PortPowerStateCommand,
            device: MccsFNDH,
            logger: Optional[logging.Logger] = None,
        ) -> None:
            """
            Initialise a new instance.

            :param device: the device to which this command belongs.
            :param logger: a logger for this command to use.
            """
            self._device = device
            super().__init__(logger)

        def do(
            self: MccsFNDH.PortPowerStateCommand,
            *args: int,
            **kwargs: Any,
        ) -> bool:
            """
            Stateless hook for device PortPowerStateCommand() command.

            :param args: the port number (1-28)
            :param kwargs: keyword args to the component manager method

            :return: True if the port is on.
            """
            port_id = args[0]
            attr_name = f"Port{port_id}PowerState"
            return self._device._fndh_attributes[attr_name.lower()].value

    @command(dtype_in="DevULong", dtype_out="DevULong")
    def PortPowerState(  # type: ignore[override]
        self: MccsFNDH, argin: int
    ) -> PowerState:
        """
        Check power state of a port.

        :param argin: the port number (1-28)

        :return: The power state of the port.
        """
        handler = self.get_command_object("PortPowerState")
        return handler(argin)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def PowerOnPort(
        self: MccsFNDH, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up a port.

        This may or may not have a Antenna attached.

        :param argin: the port to power up.

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

        :param argin: the port to power down.

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOffPort")
        result_code, message = handler(argin)
        return ([result_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def SetPortPowers(
        self: MccsFNDH,
        json_argument: str,
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Set port powers.

        These ports will not have a smartbox attached.

        :param json_argument: desired port powers of unmasked ports with
            smartboxes attached in json form.

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("SetPortPowers")
        result_code, message = handler(json_argument)
        return ([result_code], [message])

    # -----------
    # Attributes
    # -----------
    def _setup_fndh_attributes(self: MccsFNDH) -> None:
        for register in self.CONFIG["registers"].values():
            data_type = self.TYPES[register["data_type"]]
            self._setup_fndh_attribute(
                register["tango_attr_name"],
                cast(
                    type | tuple[type],
                    (data_type if register["tango_dim_x"] == 1 else (data_type,)),
                ),
                (
                    tango.AttrWriteType.READ_WRITE
                    if register["writable"]
                    else tango.AttrWriteType.READ
                ),
                max_dim_x=register["tango_dim_x"],
            )

    # pylint: disable=too-many-arguments
    def _setup_fndh_attribute(
        self: MccsFNDH,
        attribute_name: str,
        data_type: type | tuple[type],
        access_type: tango.AttrWriteType,
        max_dim_x: Optional[int] = None,
        default_value: Optional[Any] = None,
    ) -> None:
        self._fndh_attributes[attribute_name.lower()] = FNDHAttribute(
            value=default_value, timestamp=0, quality=tango.AttrQuality.ATTR_INVALID
        )
        attr = tango.server.attribute(
            name=attribute_name,
            dtype=data_type,
            access=access_type,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fget=self._read_fndh_attribute,
            fset=self._read_fndh_attribute,
        ).to_attr()
        self.add_attribute(
            attr,
            self._read_fndh_attribute,
            self._write_fndh_attribute,
            None,
        )
        self.set_change_event(attribute_name, True, False)
        self.set_archive_event(attribute_name, True, False)

    def _read_fndh_attribute(self: MccsFNDH, fndh_attribute: tango.Attribute) -> None:
        attribute_name = fndh_attribute.get_name().lower()
        fndh_attribute.set_value_date_quality(
            self._fndh_attributes[attribute_name].value,
            self._fndh_attributes[attribute_name].timestamp,
            self._fndh_attributes[attribute_name].quality,
        )

    def _write_fndh_attribute(self: MccsFNDH, fndh_attribute: tango.Attribute) -> None:
        # Register the request with the component manager
        tango_attr_name = fndh_attribute.get_name()
        value = fndh_attribute.get_write_value(ExtractAs.List)
        self.logger.debug(
            f"Requesting to write FNDH attribute: {tango_attr_name} with value"
            f" {value}"
        )
        self.component_manager.write_attribute(tango_attr_name, value)

    @attribute(dtype="DevDouble", label="Over current threshold", unit="Amp")
    def overCurrentThreshold(self: MccsFNDH) -> float:
        """
        Return the overCurrentThreshold attribute.

        :return: the value of the overCurrentThreshold attribute
        """
        return self._overCurrentThreshold

    @overCurrentThreshold.write  # type: ignore[no-redef]
    def overCurrentThreshold(self: MccsFNDH, value: float) -> None:
        """
        Set the overCurrentThreshold attribute.

        :param value: new value for the overCurrentThreshold attribute
        """
        self._overCurrentThreshold = value

    @attribute(dtype="DevDouble", label="Over Voltage threshold", unit="Volt")
    def overVoltageThreshold(self: MccsFNDH) -> float:
        """
        Return the overVoltageThreshold attribute.

        :return: the value of the overVoltageThreshold attribute
        """
        return self._overVoltageThreshold

    @overVoltageThreshold.write  # type: ignore[no-redef]
    def overVoltageThreshold(self: MccsFNDH, value: float) -> None:
        """
        Set the overVoltageThreshold attribute.

        :param value: new value for the overVoltageThreshold attribute
        """
        self._overVoltageThreshold = value

    @attribute(dtype="DevDouble", label="Humidity threshold", unit="percent")
    def humidityThreshold(self: MccsFNDH) -> float:
        """
        Return the humidity threshold.

        :return: the value of the humidityThreshold attribute
        """
        return self._humidityThreshold

    @humidityThreshold.write  # type: ignore[no-redef]
    def humidityThreshold(self: MccsFNDH, value: float) -> None:
        """
        Set the humidityThreshold attribute.

        :param value: new value for the humidityThreshold attribute
        """
        self._humidityThreshold = value

    # ----------
    # Callbacks
    # ----------
    def _communication_state_changed(
        self: MccsFNDH, communication_state: CommunicationStatus
    ) -> None:
        self.logger.debug(
            (
                "Device received callback from component manager that communication "
                "with the component is %s."
            ),
            communication_state.name,
        )
        if communication_state != CommunicationStatus.ESTABLISHED:
            self._update_port_power_states(
                [PowerState.UNKNOWN] * self.CONFIG["number_of_ports"]
            )
            self._component_state_changed_callback(power=PowerState.UNKNOWN)
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_changed_callback(power=PowerState.ON)
            self._update_port_power_states(self._port_power_states)

        super()._communication_state_changed(communication_state)

        self._health_model.update_state(communicating=True)

    def _update_port_power_states(
        self: MccsFNDH, power_states: list[PowerState]
    ) -> None:
        assert self.CONFIG["number_of_ports"] == len(power_states)
        timestamp = datetime.utcnow().timestamp()
        for port in range(self.CONFIG["number_of_ports"]):
            attr_name = f"Port{port + 1}PowerState"
            if self._fndh_attributes[attr_name.lower()].value != power_states[port]:
                self._fndh_attributes[attr_name.lower()].value = power_states[port]
                # Set Quality to VALID as the UNKNOWN value already captures a
                # faulty communication status
                self._fndh_attributes[
                    attr_name.lower()
                ].quality = tango.AttrQuality.ATTR_VALID
                self._fndh_attributes[attr_name.lower()].timestamp = timestamp
                self.push_change_event(
                    attr_name,
                    self._fndh_attributes[attr_name.lower()].value,
                    timestamp,
                    tango.AttrQuality.ATTR_VALID,
                )
                if power_states[port] != PowerState.UNKNOWN:
                    self._port_power_states[port] = power_states[port]

    def _component_state_changed_callback(
        self: MccsFNDH,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        fqdn: Optional[str] = None,
        pasdbus_status: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param fqdn: the fqdn of the device calling.
        :param pasdbus_status: the status of the pasd_bus
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if fqdn is not None:
            # TODO: The information passed here could factor into the FNDH health
            if power == PowerState.UNKNOWN:
                # If a proxy calls back with a unknown power. As a precaution it is
                # assumed that communication is NOT_ESTABLISHED.
                self._communication_state_changed(CommunicationStatus.NOT_ESTABLISHED)
                return
            if power == PowerState.ON:
                self._update_port_power_states(self._port_power_states)

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
            self.push_archive_event("healthState", health)

    def _attribute_changed_callback(
        self: MccsFNDH,
        attr_name: str,
        attr_value: Any,
        timestamp: float,
        attr_quality: tango.AttrQuality,
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
        :param: timestamp: the timestamp for the current change
        :param: attr_quality: the quality factor for the attribute
        """
        try:
            assert (
                len(
                    [
                        register["tango_attr_name"]
                        for register in self.CONFIG["registers"].values()
                        if register["tango_attr_name"].lower() == attr_name.lower()
                    ]
                )
                > 0
            )
            # TODO: These attributes may factor into the FNDH health.
            # we should notify the health model of any relevant changes.
            if attr_value is None:
                # This happens when the upstream attribute's quality factor has
                # been set to INVALID. Pushing a change event with None
                # triggers an exception so we change it to the last known value here
                attr_value = self._fndh_attributes[attr_name].value
            else:
                self._fndh_attributes[attr_name].value = attr_value
            self._fndh_attributes[attr_name].quality = attr_quality
            self._fndh_attributes[attr_name].timestamp = timestamp
            self.push_change_event(attr_name, attr_value, timestamp, attr_quality)
            self.push_archive_event(attr_name, attr_value, timestamp, attr_quality)

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
    Launch an `MccsFNDH` Tango device server instance.

    :param args: positional arguments, passed to the Tango device
    :param kwargs: keyword arguments, passed to the sever

    :return: the Tango server exit code
    """
    return MccsFNDH.run_server(args=args or None, **kwargs)


if __name__ == "__main__":
    main()
