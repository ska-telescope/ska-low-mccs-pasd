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
from typing import Any, Final, Optional

import tango
from ska_control_model import CommunicationStatus, HealthState, PowerState, ResultCode
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import (
    DeviceInitCommand,
    FastCommand,
    JsonValidator,
    SubmittedSlowCommand,
)
from tango.server import attribute, command, device_property

from .fndh_component_manager import FndhComponentManager
from .fndh_health_model import FndhHealthModel

__all__ = ["MccsFNDH", "main"]


DevVarLongStringArrayType = tuple[list[ResultCode], list[str]]


# pylint: disable-next=too-many-instance-attributes
class MccsFNDH(SKABaseDevice[FndhComponentManager]):
    """An implementation of the FNDH device for MCCS."""

    PORT_COUNT: Final = 28

    # -----------------
    # Device Properties
    # -----------------
    PasdFQDN = device_property(dtype=(str), mandatory=True)

    # --------------------
    # Forwarded attributes
    # --------------------
    modbusRegisterMapRevisionNumber = attribute(
        name="modbusRegisterMapRevisionNumber",
        label="Modbus register map revision number",
        forwarded=True,
    )
    pcbRevisionNumber = attribute(
        name="pcbRevisionNumber",
        label="PCB revision number",
        forwarded=True,
    )
    cpuId = attribute(
        name="cpuId",
        label="CPU id",
        forwarded=True,
    )
    chipId = attribute(
        name="chipId",
        label="Chip ID",
        forwarded=True,
    )
    firmwareVersion = attribute(
        name="firmwareVersion",
        label="Firmware version",
        forwarded=True,
    )
    uptime = attribute(
        name="uptime",
        label="Update",
        forwarded=True,
    )
    sysAddress = attribute(
        name="sysAddress",
        label="System address",
        forwarded=True,
    )
    fndhStatus = attribute(
        name="fndhStatus",
        label="FNDH status",
        forwarded=True,
    )
    ledPattern = attribute(
        name="ledPattern",
        label="LED pattern",
        forwarded=True,
    )
    psu48vVoltages = attribute(
        name="psu48vVoltages",
        label="PSU 48v voltages",
        forwarded=True,
    )
    psu48vCurrent = attribute(
        name="psu48vCurrent",
        label="PSU 48v current",
        forwarded=True,
    )
    psu48vTemperatures = attribute(
        name="psu48vTemperatures",
        label="PSU 48v temperatures",
        forwarded=True,
    )
    panelTemperature = attribute(
        name="panelTemperature",
        label="Panel temperature",
        forwarded=True,
    )
    fncbTemperature = attribute(
        name="fncbTemperature",
        label="FNCB temperature",
        forwarded=True,
    )
    fncbHumidity = attribute(
        name="fncbHumidity",
        label="FNCB humidity",
        forwarded=True,
    )
    commsGatewayTemperature = attribute(
        name="commsGatewayTemperature",
        label="Communications gateway temperature",
        forwarded=True,
    )
    powerModuleTemperature = attribute(
        name="powerModuleTemperature",
        label="Power module temperature",
        forwarded=True,
    )
    outsideTemperature = attribute(
        name="outsideTemperature",
        label="Outside temperature",
        forwarded=True,
    )
    internalAmbientTemperature = attribute(
        name="internalAmbientTemperature",
        label="Internal ambient temperature",
        forwarded=True,
    )
    # TODO: https://gitlab.com/tango-controls/cppTango/-/issues/1018
    # Cannot forward this attribute right now:
    # portForcings = attribute(
    #     name="portForcings",
    #     label="Port forcings",
    #     forwarded=True,
    # )
    portsDesiredPowerOnline = attribute(
        name="portsDesiredPowerOnline",
        label="Ports desired power when online",
        forwarded=True,
    )
    portsDesiredPowerOffline = attribute(
        name="portsDesiredPowerOffline",
        label="Ports desired power when offline",
        forwarded=True,
    )
    portsPowerSensed = attribute(
        name="portsPowerSensed",
        label="Ports power sensed",
        forwarded=True,
    )
    warningFlags = attribute(
        name="warningFlags",
        label="Warning flags",
        forwarded=True,
    )
    alarmFlags = attribute(
        name="alarmFlags",
        label="Alarm flags",
        forwarded=True,
    )
    psu48vVoltage1Thresholds = attribute(
        name="psu48vVoltage1Thresholds",
        label="PSU 48v voltage 1 thresholds",
        forwarded=True,
    )
    psu48vVoltage2Thresholds = attribute(
        name="psu48vVoltage2Thresholds",
        label="PSU 48v voltage 2 thresholds",
        forwarded=True,
    )
    psu48vCurrentThresholds = attribute(
        name="psu48vCurrentThresholds",
        label="PSU 48v current thresholds",
        forwarded=True,
    )
    psu48vTemperature1Thresholds = attribute(
        name="psu48vTemperature1Thresholds",
        label="PSU 48v temperature 1 thresholds",
        forwarded=True,
    )
    psu48vTemperature2Thresholds = attribute(
        name="psu48vTemperature2Thresholds",
        label="PSU 48v temperature 2 thresholds",
        forwarded=True,
    )
    panelTemperatureThresholds = attribute(
        name="panelTemperatureThresholds",
        label="Panel temperature thresholds",
        forwarded=True,
    )
    fncbTemperatureThresholds = attribute(
        name="fncbTemperatureThresholds",
        label="FNCB temperature thresholds",
        forwarded=True,
    )
    humidityThresholds = attribute(
        name="humidityThresholds",
        label="Humidity thresholds",
        forwarded=True,
    )
    outsideTemperatureThresholds = attribute(
        name="outsideTemperatureThresholds",
        label="Outside temperature thresholds",
        forwarded=True,
    )
    commsGatewayTemperatureThresholds = attribute(
        name="commsGatewayTemperatureThresholds",
        label="Communications gateway temperature thresholds",
        forwarded=True,
    )
    powerModuleTemperatureThresholds = attribute(
        name="powerModuleTemperatureThresholds",
        label="Power module temperature thresholds",
        forwarded=True,
    )
    internalAmbientTemperatureThresholds = attribute(
        name="internalAmbientTemperatureThresholds",
        label="Internal ambient temperature thresholds",
        forwarded=True,
    )

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
        self._fndh_attributes: dict[str, Any] = {}

        # Attributes for specific ports on the FNDH.
        # These attributes are a breakdown of the portPowerSensed
        # attribute. The reason is to allow smartboxes to subscribe to
        # their power state.
        for port in range(1, self.PORT_COUNT + 1):
            attr_name = f"Port{port}PowerState"
            self._setup_fndh_attribute(attr_name, PowerState, 1, PowerState.UNKNOWN)

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
            self._device._isAlive = True
            self._device._overCurrentThreshold = 0.0
            self._device._overVoltageThreshold = 0.0
            self._device._humidityThreshold = 0.0
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
            self._update_port_power_states,
            self.PasdFQDN,
        )

    def init_command_objects(self: MccsFNDH) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for command_name, method_name in [
            ("PowerOnPort", "power_on_port"),
            ("PowerOffPort", "power_off_port"),
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
        ) -> tuple[ResultCode, str]:
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

            return (ResultCode.OK, "Configure completed OK")

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
            return self._device._fndh_attributes[attr_name.lower()]

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

    def _setup_fndh_attribute(
        self: MccsFNDH,
        attribute_name: str,
        data_type: type | tuple[type],
        max_dim_x: Optional[int] = None,
        default_value: Optional[Any] = None,
    ) -> None:
        self._fndh_attributes[attribute_name.lower()] = default_value
        attr = attribute(
            name=attribute_name,
            dtype=data_type,
            access=tango.AttrWriteType.READ,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fread="_read_fndh_attribute",
        ).to_attr()
        self.add_attribute(attr, self._read_fndh_attribute, None, None)
        self.set_change_event(attribute_name, True, False)
        self.set_archive_event(attribute_name, True, False)

    def _read_fndh_attribute(self: MccsFNDH, fndh_attribute: tango.Attribute) -> None:
        fndh_attribute.set_value(
            self._fndh_attributes[fndh_attribute.get_name().lower()]
        )

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
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_changed_callback(power=PowerState.ON)
            self._update_port_power_states(self._port_power_states)
        else:
            self._update_port_power_states([PowerState.UNKNOWN] * self.PORT_COUNT)
            self._component_state_changed_callback(power=PowerState.UNKNOWN)

        super()._communication_state_changed(communication_state)
        self._health_model.update_state(
            communicating=(communication_state == CommunicationStatus.ESTABLISHED)
        )

    def _update_port_power_states(
        self: MccsFNDH, power_states: list[PowerState]
    ) -> None:
        assert self.PORT_COUNT == len(power_states)
        for port in range(self.PORT_COUNT):
            attr_name = f"Port{port + 1}PowerState"
            if self._fndh_attributes[attr_name.lower()] != power_states[port]:
                self._fndh_attributes[attr_name.lower()] = power_states[port]
                self.push_change_event(
                    attr_name, self._fndh_attributes[attr_name.lower()]
                )
                if power_states[port] != PowerState.UNKNOWN:
                    self._port_power_states[port] = power_states[port]

    def _component_state_changed_callback(
        self: MccsFNDH,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        status: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param status: the status of the FNDH
        :param kwargs: additional keyword arguments defining component
            state.
        """
        super()._component_state_changed(fault=fault, power=power)
        self._health_model.update_state(fault=fault, power=power, pasdbus_status=status)

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
