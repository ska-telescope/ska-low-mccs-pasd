# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS PaSD bus device."""
# pylint: disable=too-many-lines

from __future__ import annotations

import importlib.resources
import json
import logging
import sys
import traceback
from typing import Any, Final, Optional, cast

import tango.server
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
    SimulationMode,
)
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import DeviceInitCommand, FastCommand, JsonValidator
from tango.server import attribute, command

from .pasd_bus_component_manager import PasdBusComponentManager
from .pasd_bus_health_model import PasdBusHealthModel

__all__ = ["MccsPasdBus", "main"]


NUMBER_OF_FNDH_PORTS = 28
NUMBER_OF_SMARTBOX_PORTS = 12

DevVarLongStringArrayType = tuple[list[ResultCode], list[Optional[str]]]


class MccsPasdBus(SKABaseDevice[PasdBusComponentManager]):
    """An implementation of a PaSD bus Tango device for MCCS."""

    # pylint: disable=attribute-defined-outside-init
    # Because Tango devices define attributes in init_device.

    _ATTRIBUTE_MAP: dict[int, dict[str, str]] = {
        0: {
            "modbus_register_map_revision": "fndhModbusRegisterMapRevisionNumber",
            "pcb_revision": "fndhPcbRevisionNumber",
            "cpu_id": "fndhCpuId",
            "chip_id": "fndhChipId",
            "firmware_version": "fndhFirmwareVersion",
            "uptime": "fndhUptime",
            "status": "fndhStatus",
            "sys_address": "fndhSysAddress",
            "led_pattern": "fndhLedPattern",
            "psu48v_voltages": "fndhPsu48vVoltages",
            "psu48v_current": "fndhPsu48vCurrent",
            "psu48v_temperatures": "fndhPsu48vTemperatures",
            "panel_temperature": "fndhPanelTemperature",
            "fncb_temperature": "fndhFncbTemperature",
            "fncb_humidity": "fndhFncbHumidity",
            "comms_gateway_temperature": "fndhCommsGatewayTemperature",
            "power_module_temperature": "fndhPowerModuleTemperature",
            "outside_temperature": "fndhOutsideTemperature",
            "internal_ambient_temperature": "fndhInternalAmbientTemperature",
            "ports_connected": "fndhPortsConnected",
            "port_forcings": "fndhPortForcings",
            "ports_desired_power_when_online": "fndhPortsDesiredPowerOnline",
            "ports_desired_power_when_offline": "fndhPortsDesiredPowerOffline",
            "ports_power_sensed": "fndhPortsPowerSensed",
        },
        **{
            smartbox_number: {
                "modbus_register_map_revision": (
                    f"smartbox{smartbox_number}ModbusRegisterMapRevisionNumber"
                ),
                "pcb_revision": f"smartbox{smartbox_number}PcbRevisionNumber",
                "cpu_id": f"smartbox{smartbox_number}CpuId",
                "chip_id": f"smartbox{smartbox_number}ChipId",
                "firmware_version": f"smartbox{smartbox_number}FirmwareVersion",
                "uptime": f"smartbox{smartbox_number}Uptime",
                "status": f"smartbox{smartbox_number}Status",
                "sys_address": f"smartbox{smartbox_number}SysAddress",
                "led_pattern": f"smartbox{smartbox_number}LedPattern",
                "input_voltage": f"smartbox{smartbox_number}InputVoltage",
                "power_supply_output_voltage": (
                    f"smartbox{smartbox_number}PowerSupplyOutputVoltage"
                ),
                "power_supply_temperature": (
                    f"smartbox{smartbox_number}PowerSupplyTemperature"
                ),
                "pcb_temperature": f"smartbox{smartbox_number}PcbTemperature",
                "fem_ambient_temperature": (
                    f"smartbox{smartbox_number}FemAmbientTemperature"
                ),
                "fem_case_temperatures": (
                    f"smartbox{smartbox_number}FemCaseTemperatures"
                ),
                "fem_heatsink_temperatures": (
                    f"smartbox{smartbox_number}FemHeatsinkTemperatures"
                ),
                "ports_connected": f"smartbox{smartbox_number}PortsConnected",
                "port_forcings": f"smartbox{smartbox_number}PortForcings",
                "port_breakers_tripped": (
                    f"smartbox{smartbox_number}PortBreakersTripped"
                ),
                "ports_desired_power_when_online": (
                    f"smartbox{smartbox_number}PortsDesiredPowerOnline"
                ),
                "ports_desired_power_when_offline": (
                    f"smartbox{smartbox_number}PortsDesiredPowerOffline"
                ),
                "ports_power_sensed": f"smartbox{smartbox_number}PortsPowerSensed",
                "ports_current_draw": f"smartbox{smartbox_number}PortsCurrentDraw",
            }
            for smartbox_number in range(1, 25)
        },
    }
    # ----------
    # Properties
    # ----------
    Host = tango.server.device_property(dtype=str)
    Port = tango.server.device_property(dtype=int)
    Timeout = tango.server.device_property(dtype=float)

    # ---------------
    # Initialisation
    # ---------------
    def init_device(self: MccsPasdBus) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        super().init_device()

        self._build_state: str = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id: str = sys.modules["ska_low_mccs_pasd"].__version__

        self._pasd_state: dict[str, Any] = {}
        self._setup_fndh_attributes()
        for smartbox_number in range(1, 25):
            self._setup_smartbox_attributes(smartbox_number)

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tHost: {self.Host}\n"
            f"\tPort: {self.Port}\n"
            f"\tTimeout: {self.Timeout}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def _setup_fndh_attributes(self: MccsPasdBus) -> None:
        for slug, data_type, length in [
            ("ModbusRegisterMapRevisionNumber", int, None),
            ("PcbRevisionNumber", int, None),
            ("CpuId", int, None),
            ("ChipId", int, None),
            ("FirmwareVersion", str, None),
            ("Uptime", int, None),
            ("SysAddress", int, None),
            ("Psu48vVoltages", (float,), 2),
            ("Psu48vCurrent", float, None),
            ("Psu48vTemperatures", (float,), 2),
            ("PanelTemperature", float, None),
            ("FncbTemperature", float, None),
            ("FncbHumidity", float, None),
            ("CommsGatewayTemperature", float, None),
            ("PowerModuleTemperature", float, None),
            ("OutsideTemperature", float, None),
            ("InternalAmbientTemperature", float, None),
            ("Status", str, None),
            ("LedPattern", str, None),
            ("PortsConnected", (bool,), NUMBER_OF_FNDH_PORTS),
            ("PortForcings", (str,), NUMBER_OF_FNDH_PORTS),
            ("PortsDesiredPowerOnline", (bool,), NUMBER_OF_FNDH_PORTS),
            ("PortsDesiredPowerOffline", (bool,), NUMBER_OF_FNDH_PORTS),
            ("PortsPowerSensed", (bool,), NUMBER_OF_FNDH_PORTS),
        ]:
            self._setup_pasd_attribute(
                f"fndh{slug}",
                cast(type | tuple[type], data_type),
                max_dim_x=length,
            )

    def _setup_smartbox_attributes(self: MccsPasdBus, smartbox_number: int) -> None:
        for slug, data_type, length in [
            ("ModbusRegisterMapRevisionNumber", int, None),
            ("PcbRevisionNumber", int, None),
            ("CpuId", int, None),
            ("ChipId", int, None),
            ("FirmwareVersion", str, None),
            ("Uptime", int, None),
            ("Status", str, None),
            ("SysAddress", int, None),
            ("LedPattern", str, None),
            ("InputVoltage", float, None),
            ("PowerSupplyOutputVoltage", float, None),
            ("PowerSupplyTemperature", float, None),
            ("PcbTemperature", float, None),
            ("FemAmbientTemperature", float, None),
            ("FemCaseTemperatures", (float,), 2),
            ("FemHeatsinkTemperatures", (float,), 2),
            ("PortsConnected", (bool,), NUMBER_OF_SMARTBOX_PORTS),
            ("PortForcings", (str,), NUMBER_OF_SMARTBOX_PORTS),
            ("PortBreakersTripped", (bool,), NUMBER_OF_SMARTBOX_PORTS),
            ("PortsDesiredPowerOnline", (bool,), NUMBER_OF_SMARTBOX_PORTS),
            ("PortsDesiredPowerOffline", (bool,), NUMBER_OF_SMARTBOX_PORTS),
            ("PortsPowerSensed", (bool,), NUMBER_OF_SMARTBOX_PORTS),
            ("PortsCurrentDraw", (float,), NUMBER_OF_SMARTBOX_PORTS),
        ]:
            self._setup_pasd_attribute(
                f"smartbox{smartbox_number}{slug}",
                cast(type | tuple[type], data_type),
                max_dim_x=length,
            )

    def _setup_pasd_attribute(
        self: MccsPasdBus,
        attribute_name: str,
        data_type: type | tuple[type],
        max_dim_x: Optional[int] = None,
    ) -> None:
        self._pasd_state[attribute_name] = None
        attr = tango.server.attribute(
            name=attribute_name,
            dtype=data_type,
            access=tango.AttrWriteType.READ,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fread="_read_pasd_attribute",
        ).to_attr()
        self.add_attribute(attr, self._read_pasd_attribute, None, None)
        self.set_change_event(attribute_name, True, False)
        self.set_archive_event(attribute_name, True, False)

    def _read_pasd_attribute(self, pasd_attribute: tango.Attribute) -> None:
        attr_name = pasd_attribute.get_name()
        attr_value = self._pasd_state[attr_name]
        if attr_value is None:
            msg = f"Attempted read of {attr_name} before it has been polled."
            self.logger.warning(msg)
            raise tango.Except.throw_exception(
                f"Error: {attr_name} is None", msg, "".join(traceback.format_stack())
            )
        pasd_attribute.set_value(attr_value)

    def _init_state_model(self: MccsPasdBus) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = PasdBusHealthModel(self._health_changed)
        self.set_change_event("healthState", True, False)

    def create_component_manager(
        self: MccsPasdBus,
    ) -> PasdBusComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return PasdBusComponentManager(
            self.Host,
            self.Port,
            self.Timeout,
            self.logger,
            self._communication_state_callback,
            self._component_state_callback,
            self._pasd_device_state_callback,
        )

    def init_command_objects(self: MccsPasdBus) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for command_name, command_class in [
            ("InitializeFndh", MccsPasdBus._InitializeFndhCommand),
            ("InitializeSmartbox", MccsPasdBus._InitializeSmartboxCommand),
            ("TurnFndhPortOn", MccsPasdBus._TurnFndhPortOnCommand),
            ("TurnFndhPortOff", MccsPasdBus._TurnFndhPortOffCommand),
            ("SetFndhLedPattern", MccsPasdBus._SetFndhLedPatternCommand),
            ("ResetFndhPortBreaker", MccsPasdBus._ResetFndhPortBreakerCommand),
            ("TurnSmartboxPortOn", MccsPasdBus._TurnSmartboxPortOnCommand),
            ("TurnSmartboxPortOff", MccsPasdBus._TurnSmartboxPortOffCommand),
            (
                "SetSmartboxLedPattern",
                MccsPasdBus._SetSmartboxLedPatternCommand,
            ),
            (
                "ResetSmartboxPortBreaker",
                MccsPasdBus._ResetSmartboxPortBreakerCommand,
            ),
        ]:
            self.register_command_object(
                command_name,
                command_class(self.component_manager, self.logger),
            )

        self.register_command_object(
            "GetPasdDeviceSubscriptions",
            MccsPasdBus._GetPasdDeviceSubscriptions(self, self.logger),
        )

    class InitCommand(DeviceInitCommand):
        """
        A class for :py:class:`~.MccsPasdBus`'s Init command.

        The :py:meth:`~.MccsPasdBus.InitCommand.do` method below is
        called upon :py:class:`~.MccsPasdBus`'s initialisation.
        """

        def do(  # type: ignore[override]
            self: MccsPasdBus.InitCommand,
            *args: Any,
            **kwargs: Any,
        ) -> tuple[ResultCode, str]:
            """
            Initialise the attributes and properties of the MccsPasdBus.

            :param args: positional args to the component manager method
            :param kwargs: keyword args to the component manager method

            :return: A tuple containing a return code and a string
                message indicating status. The message is for
                information purpose only.
            """
            return (ResultCode.OK, "Init command completed OK")

    # ----------
    # Callbacks
    # ----------
    def _communication_state_callback(
        self: MccsPasdBus,
        communication_state: CommunicationStatus,
    ) -> None:
        """
        Handle change in communications status between component manager and component.

        This is a callback hook, called by the component manager when
        the communications status changes. It is implemented here to
        drive the op_state.

        :param communication_state: the status of communications
            between the component manager and its component.
        """
        action_map = {
            CommunicationStatus.DISABLED: "component_disconnected",
            CommunicationStatus.NOT_ESTABLISHED: "component_unknown",
            CommunicationStatus.ESTABLISHED: "component_on",
        }

        action = action_map[communication_state]
        if action is not None:
            self.op_state_model.perform_action(action)

        self._health_model.update_state(communicating=True)

    def _component_state_callback(
        self: MccsPasdBus,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        Note this the "component" is the PaSD bus itself,
        and the PaSD bus has no monitoring points.
        All we can do is infer that it is powered on and not in fault,
        from the fact that we receive responses to our requests.

        The responses themselves deliver information about
        the state of the devices attached the bus.
        This payload is handled by a different callback.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param kwargs: additional keyword arguments defining component
            state.
        """
        super()._component_state_changed(fault=fault, power=power)
        self._health_model.update_state(fault=fault, power=power)

    def _pasd_device_state_callback(
        self: MccsPasdBus,
        pasd_device_number: int,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of a PaSD device.

        This is a callback hook, called by the component manager when
        the state of a PaSD device changes.

        :param pasd_device_number: the number of the PaSD device to
            which this state update applies.
            0 refers to the FNDH, otherwise the device number is the
            smartbox number.
        :param kwargs: keyword arguments defining PaSD device state.
        """
        try:
            attribute_map = self._ATTRIBUTE_MAP[pasd_device_number]
        except KeyError:
            self.logger.error(
                f"Received update for unknown PaSD device number {pasd_device_number}."
            )
            return

        for pasd_attribute_name, pasd_attribute_value in kwargs.items():
            try:
                tango_attribute_name = attribute_map[pasd_attribute_name]
            except KeyError:
                self.logger.error(
                    f"Received update for unknown PaSD attribute {pasd_attribute_name} "
                    f"(for PaSD device {pasd_device_number})."
                )
                return

            if self._pasd_state[tango_attribute_name] != pasd_attribute_value:
                self._pasd_state[tango_attribute_name] = pasd_attribute_value
                self.push_change_event(tango_attribute_name, pasd_attribute_value)
                self.push_archive_event(tango_attribute_name, pasd_attribute_value)

    def _health_changed(
        self: MccsPasdBus,
        health: HealthState,
    ) -> None:
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
    # Attributes
    # ----------
    @attribute(dtype=SimulationMode, memorized=True, hw_memorized=True)
    def simulationMode(self: MccsPasdBus) -> int:
        """
        Report the simulation mode of the device.

        :return: Return the current simulation mode
        """
        return SimulationMode.FALSE

    @simulationMode.write  # type: ignore[no-redef]
    def simulationMode(  # pylint: disable=arguments-differ
        self: MccsPasdBus, value: SimulationMode
    ) -> None:
        """
        Set the simulation mode.

        Writing this attribute is deliberately unimplemented.
        To run this device against a simulator,
        stand up a PaSD bus simulator,
        then configure this device
        with the simulator's IP address and port.

        :param value: The simulation mode, as a SimulationMode value
        """
        self.logger.warning(
            "MccsPasdBus's simulationMode attribute is unimplemented. "
            "To run this device against a simulator, "
            "stand up an external PaSD bus simulator, "
            "then configure this device with the simulator's IP address and port."
        )

    # ----------
    # Commands
    # ----------
    class _InitializeFndhCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._InitializeFndhCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._InitializeFndhCommand,
        ) -> Optional[bool]:
            """
            Initialize an FNDH.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.initialize_fndh()

    @command(dtype_out="DevVarLongStringArray")
    def InitializeFndh(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Initialize an FNDH.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("InitializeFndh")
        success = handler()
        if success:
            return ([ResultCode.OK], ["InitializeFndh succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["InitializeFndh succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["InitializeFndh failed"])

    class _TurnFndhPortOnCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_TurnFndhPortOn.json",
            )
        )

        def __init__(
            self: MccsPasdBus._TurnFndhPortOnCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("TurnFndhPortOn", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._TurnFndhPortOnCommand,
            port_number: int,
            stay_on_when_offline: bool,
        ) -> Optional[bool]:
            """
            Turn on an FNDH port.

            :param port_number: number of the port to turn on.
            :param stay_on_when_offline: whether the port should remain
                on if communication with the MCCS is lost.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.turn_fndh_port_on(
                port_number, stay_on_when_offline
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def TurnFndhPortOn(self: MccsPasdBus, argin: str) -> DevVarLongStringArrayType:
        """
        Turn on an FNDH port.

        :param argin: the FNDH port to turn on

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnFndhPortOn")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["TurnFndhPortOn succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["TurnFndhPortOn succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["TurnFndhPortOn failed"])

    class _TurnFndhPortOffCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._TurnFndhPortOffCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._TurnFndhPortOffCommand,
            port_number: int,
        ) -> Optional[bool]:
            """
            Turn off an FNDH port.

            :param port_number: number of the port to turn off.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.turn_fndh_port_off(port_number)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnFndhPortOff(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Turn off an FNDH port.

        :param argin: the FNDH port to turn off

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnFndhPortOff")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnFndhPortOff {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnFndhPortOff {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnFndhPortOff {argin} failed"])

    class _SetFndhLedPatternCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._SetFndhLedPatternCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetFndhLedPatternCommand,
            pattern: str,
        ) -> Optional[bool]:
            """
            Set the FNDH LED pattern.

            :param pattern: name of the new LED pattern

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.set_fndh_led_pattern(pattern)

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetFndhLedPattern(self: MccsPasdBus, pattern: str) -> DevVarLongStringArrayType:
        """
        Set the FNDH's LED pattern.

        :param pattern: name of the new LED pattern.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("SetFndhLedPattern")
        success = handler(pattern)
        if success:
            return ([ResultCode.OK], ["SetFndhLedPattern succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["SetFndhLedPattern succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["SetFndhLedPattern failed"])

    class _ResetFndhPortBreakerCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._ResetFndhPortBreakerCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetFndhPortBreakerCommand,
            port_number: int,
        ) -> Optional[bool]:
            """
            Reset an FNDH port breaker.

            :param port_number: the number of the port whose breaker is
                to be reset.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.reset_fndh_port_breaker(port_number)

    @command(dtype_in=int, dtype_out="DevVarLongStringArray")
    def ResetFndhPortBreaker(
        self: MccsPasdBus, port_number: int
    ) -> DevVarLongStringArrayType:
        """
        Reset an FNDH port's breaker.

        :param port_number: number of the port whose breaker is to be
            reset.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetFndhPortBreaker")
        success = handler(port_number)
        if success:
            return ([ResultCode.OK], ["ResetFndhPortBreaker succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["ResetFndhPortBreaker succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["ResetFndhPortBreaker failed"])

    class _InitializeSmartboxCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._InitializeSmartboxCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._InitializeSmartboxCommand, smartbox_id: int
        ) -> Optional[bool]:
            """
            Initialize a Smartbox.

            :param smartbox_id: id of the smartbox being addressed.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.initialize_smartbox(smartbox_id)

    @command(dtype_in=int, dtype_out="DevVarLongStringArray")
    def InitializeSmartbox(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Initialize a smartbox.

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("InitializeSmartbox")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["InitializeSmartbox succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["InitializeSmartbox succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["InitializeSmartbox failed"])

    class _TurnSmartboxPortOnCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_TurnSmartboxPortOn.json",
            )
        )

        def __init__(
            self: MccsPasdBus._TurnSmartboxPortOnCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("TurnSmartboxPortOn", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._TurnSmartboxPortOnCommand,
            smartbox_number: int,
            port_number: int,
            stay_on_when_offline: bool,
        ) -> Optional[bool]:
            """
            Turn on a smartbox port.

            :param smartbox_number: number of the smartbox to be
                addressed
            :param port_number: name of the port to be turned on.
            :param stay_on_when_offline: whether the port should remain
                on if communication with the MCCS is lost.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.turn_smartbox_port_on(
                smartbox_number, port_number, stay_on_when_offline
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def TurnSmartboxPortOn(self: MccsPasdBus, argin: str) -> DevVarLongStringArrayType:
        """
        Turn on a smartbox port.

        :param argin: arguments encodes as a JSON string

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnSmartboxPortOn")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["TurnSmartboxPortOn succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["TurnSmartboxPortOn succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["TurnSmartboxPortOn failed"])

    class _TurnSmartboxPortOffCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_TurnSmartboxPortOff.json",
            )
        )

        def __init__(
            self: MccsPasdBus._TurnSmartboxPortOffCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("TurnSmartboxPortOff", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._TurnSmartboxPortOffCommand,
            smartbox_number: int,
            port_number: int,
        ) -> Optional[bool]:
            """
            Turn off a smartbox port.

            :param smartbox_number: number of the smartbox to be
                addressed
            :param port_number: name of the port to be turned off.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.turn_smartbox_port_off(
                smartbox_number, port_number
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def TurnSmartboxPortOff(self: MccsPasdBus, argin: str) -> DevVarLongStringArrayType:
        """
        Turn off a smartbox port.

        :param argin: arguments in JSON format

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnSmartboxPortOff")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["TurnSmartboxPortOff succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["TurnSmartboxPortOff succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["TurnSmartboxPortOff failed"])

    class _SetSmartboxLedPatternCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_SetSmartboxLedPattern.json",
            )
        )

        def __init__(
            self: MccsPasdBus._SetSmartboxLedPatternCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("SetSmartboxLedPattern", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetSmartboxLedPatternCommand,
            smartbox_number: int,
            pattern: str,
        ) -> Optional[bool]:
            return self._component_manager.set_smartbox_led_pattern(
                smartbox_number, pattern
            )

    @command(dtype_in="str", dtype_out="DevVarLongStringArray")
    def SetSmartboxLedPattern(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        """
        Set a smartbox's LED pattern.

        :param argin: JSON encoded dictionary of arguments.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("SetSmartboxLedPattern")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["SetSmartboxLedPattern succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["SetSmartboxLedPattern succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["SetSmartboxLedPattern failed"])

    class _ResetSmartboxPortBreakerCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_ResetSmartboxPortBreaker.json",
            )
        )

        def __init__(
            self: MccsPasdBus._ResetSmartboxPortBreakerCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("ResetSmartboxPortBreaker", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetSmartboxPortBreakerCommand,
            smartbox_number: int,
            port_number: int,
        ) -> Optional[bool]:
            """
            Reset an FNDH port breaker.

            :param smartbox_number: number of the smartbox to be
                addressed.
            :param port_number: the number of the port whose breaker is
                to be reset.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.reset_smartbox_port_breaker(
                smartbox_number, port_number
            )

    class _GetPasdDeviceSubscriptions(FastCommand):
        """Class for handling the GetRegisterList() command."""

        def __init__(
            self: MccsPasdBus._GetPasdDeviceSubscriptions,
            device: MccsPasdBus,
            logger: Optional[logging.Logger] = None,
        ) -> None:
            """
            Initialise a new _GetPasdDeviceSubscriptions instance.

            :param device: the device to which this command belongs.
            :param logger: a logger for this command to use.
            """
            self._device = device
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._GetPasdDeviceSubscriptions,
            pasd_device_number: int,
        ) -> list[str]:
            """
            Implement :py:meth:`.MccsTile.GetRegisterList` command functionality.

            :param pasd_device_number: the pasd_device_number
                we want to get subscriptions for.

            :return: a list of the subscriptions for this device.
            """
            return list(self._device._ATTRIBUTE_MAP[pasd_device_number].values())

    @command(dtype_in="DevShort", dtype_out="DevVarStringArray")
    def GetPasdDeviceSubscriptions(self: MccsPasdBus, device_number: int) -> list[str]:
        """
        Get subscriptions for a particular pasd device.

        :param device_number: the pasd_device_number
            we want to get subscriptions for.

        :return: The subscriptions for a particular device.
        """
        handler = self.get_command_object("GetPasdDeviceSubscriptions")
        return handler(device_number)

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def ResetSmartboxPortBreaker(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        """
        Reset a smartbox's port's breaker.

        :param argin: arguments to the command in JSON format.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetSmartboxPortBreaker")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["ResetSmartboxPortBreaker succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["ResetSmartboxPortBreaker succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["ResetSmartboxPortBreaker failed"])


# ----------
# Run server
# ----------
def main(*args: str, **kwargs: str) -> int:  # pragma: no cover
    """
    Entry point for module.

    :param args: positional arguments
    :param kwargs: named arguments

    :return: exit code
    """
    return MccsPasdBus.run_server(args=args or None, **kwargs)


if __name__ == "__main__":
    main()
