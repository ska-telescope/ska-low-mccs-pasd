# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS PaSD bus device."""

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
from tango.device_attribute import ExtractAs
from tango.server import attribute, command

from .pasd_bus_component_manager import PasdBusComponentManager
from .pasd_bus_health_model import PasdBusHealthModel

__all__ = ["MccsPasdBus", "main"]


NUMBER_OF_FNDH_PORTS = 28
NUMBER_OF_SMARTBOX_PORTS = 12

DevVarLongStringArrayType = tuple[list[ResultCode], list[Optional[str]]]


# pylint: disable=too-many-lines
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
            "port_forcings": "fndhPortForcings",
            "ports_desired_power_when_online": "fndhPortsDesiredPowerOnline",
            "ports_desired_power_when_offline": "fndhPortsDesiredPowerOffline",
            "ports_power_sensed": "fndhPortsPowerSensed",
            "psu48v_voltage_1_thresholds": "fndhPsu48vVoltage1Thresholds",
            "psu48v_voltage_2_thresholds": "fndhPsu48vVoltage2Thresholds",
            "psu48v_current_thresholds": "fndhPsu48vCurrentThresholds",
            "psu48v_temperature_1_thresholds": "fndhPsu48vTemperature1Thresholds",
            "psu48v_temperature_2_thresholds": "fndhPsu48vTemperature2Thresholds",
            "panel_temperature_thresholds": "fndhPanelTemperatureThresholds",
            "fncb_temperature_thresholds": "fndhFncbTemperatureThresholds",
            "fncb_humidity_thresholds": "fndhHumidityThresholds",
            "comms_gateway_temperature_thresholds": (
                "fndhCommsGatewayTemperatureThresholds"
            ),
            "power_module_temperature_thresholds": (
                "fndhPowerModuleTemperatureThresholds"
            ),
            "outside_temperature_thresholds": "fndhOutsideTemperatureThresholds",
            "internal_ambient_temperature_thresholds": (
                "fndhInternalAmbientTemperatureThresholds"
            ),
            "warning_flags": "fndhWarningFlags",
            "alarm_flags": "fndhAlarmFlags",
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
                "input_voltage_thresholds": (
                    f"smartbox{smartbox_number}InputVoltageThresholds"
                ),
                "power_supply_output_voltage_thresholds": (
                    f"smartbox{smartbox_number}PowerSupplyOutputVoltageThresholds"
                ),
                "power_supply_temperature_thresholds": (
                    f"smartbox{smartbox_number}PowerSupplyTemperatureThresholds"
                ),
                "pcb_temperature_thresholds": (
                    f"smartbox{smartbox_number}PcbTemperatureThresholds"
                ),
                "fem_ambient_temperature_thresholds": (
                    f"smartbox{smartbox_number}FemAmbientTemperatureThresholds"
                ),
                "fem_case_temperature_1_thresholds": (
                    f"smartbox{smartbox_number}FemCaseTemperature1Thresholds"
                ),
                "fem_case_temperature_2_thresholds": (
                    f"smartbox{smartbox_number}FemCaseTemperature2Thresholds"
                ),
                "fem_heatsink_temperature_1_thresholds": (
                    f"smartbox{smartbox_number}FemHeatsinkTemperature1Thresholds"
                ),
                "fem_heatsink_temperature_2_thresholds": (
                    f"smartbox{smartbox_number}FemHeatsinkTemperature2Thresholds"
                ),
                "fem1_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem1CurrentTripThreshold"
                ),
                "fem2_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem2CurrentTripThreshold"
                ),
                "fem3_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem3CurrentTripThreshold"
                ),
                "fem4_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem4CurrentTripThreshold"
                ),
                "fem5_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem5CurrentTripThreshold"
                ),
                "fem6_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem6CurrentTripThreshold"
                ),
                "fem7_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem7CurrentTripThreshold"
                ),
                "fem8_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem8CurrentTripThreshold"
                ),
                "fem9_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem9CurrentTripThreshold"
                ),
                "fem10_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem10CurrentTripThreshold"
                ),
                "fem11_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem11CurrentTripThreshold"
                ),
                "fem12_current_trip_threshold": (
                    f"smartbox{smartbox_number}Fem12CurrentTripThreshold"
                ),
                "warning_flags": f"smartbox{smartbox_number}WarningFlags",
                "alarm_flags": f"smartbox{smartbox_number}AlarmFlags",
            }
            for smartbox_number in range(1, 25)
        },
    }
    # ----------
    # Properties
    # ----------
    Host = tango.server.device_property(dtype=str)
    Port = tango.server.device_property(dtype=int)
    PollingRate = tango.server.device_property(dtype=float, default_value=0.5 / 10)
    DevicePollingRate = tango.server.device_property(
        dtype=float, default_value=15.0 / 10
    )
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
            f"\tPollingRate: {self.PollingRate}\n"
            f"\tDevicePollingRate: {self.DevicePollingRate}\n"
            f"\tTimeout: {self.Timeout}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def _setup_fndh_attributes(self: MccsPasdBus) -> None:
        for slug, data_type, length, access in [
            ("ModbusRegisterMapRevisionNumber", int, None, tango.AttrWriteType.READ),
            ("PcbRevisionNumber", int, None, tango.AttrWriteType.READ),
            ("CpuId", str, None, tango.AttrWriteType.READ),
            ("ChipId", str, None, tango.AttrWriteType.READ),
            ("FirmwareVersion", str, None, tango.AttrWriteType.READ),
            ("Uptime", int, None, tango.AttrWriteType.READ),
            ("SysAddress", int, None, tango.AttrWriteType.READ),
            ("Psu48vVoltages", (float,), 2, tango.AttrWriteType.READ),
            ("Psu48vCurrent", float, None, tango.AttrWriteType.READ),
            ("Psu48vTemperatures", (float,), 2, tango.AttrWriteType.READ),
            ("PanelTemperature", float, None, tango.AttrWriteType.READ),
            ("FncbTemperature", float, None, tango.AttrWriteType.READ),
            ("FncbHumidity", int, None, tango.AttrWriteType.READ),
            ("CommsGatewayTemperature", float, None, tango.AttrWriteType.READ),
            ("PowerModuleTemperature", float, None, tango.AttrWriteType.READ),
            ("OutsideTemperature", float, None, tango.AttrWriteType.READ),
            ("InternalAmbientTemperature", float, None, tango.AttrWriteType.READ),
            ("Status", str, None, tango.AttrWriteType.READ),
            ("LedPattern", str, None, tango.AttrWriteType.READ),
            ("PortForcings", (str,), NUMBER_OF_FNDH_PORTS, tango.AttrWriteType.READ),
            ("WarningFlags", str, None, tango.AttrWriteType.READ),
            ("AlarmFlags", str, None, tango.AttrWriteType.READ),
            (
                "PortsDesiredPowerOnline",
                (bool,),
                NUMBER_OF_FNDH_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortsDesiredPowerOffline",
                (bool,),
                NUMBER_OF_FNDH_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortsPowerSensed",
                (bool,),
                NUMBER_OF_FNDH_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "Psu48vVoltage1Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "Psu48vVoltage2Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "Psu48vCurrentThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "Psu48vTemperature1Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "Psu48vTemperature2Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "PanelTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "FncbTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            ("HumidityThresholds", (float,), 4, tango.AttrWriteType.READ_WRITE),
            (
                "CommsGatewayTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "PowerModuleTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "OutsideTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "InternalAmbientTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
        ]:
            self._setup_pasd_attribute(
                f"fndh{slug}",
                cast(type | tuple[type], data_type),
                max_dim_x=length,
                access=access,
            )

    def _setup_smartbox_attributes(self: MccsPasdBus, smartbox_number: int) -> None:
        for slug, data_type, length, access in [
            ("ModbusRegisterMapRevisionNumber", int, None, tango.AttrWriteType.READ),
            ("PcbRevisionNumber", int, None, tango.AttrWriteType.READ),
            ("CpuId", str, None, tango.AttrWriteType.READ),
            ("ChipId", str, None, tango.AttrWriteType.READ),
            ("FirmwareVersion", str, None, tango.AttrWriteType.READ),
            ("Uptime", int, None, tango.AttrWriteType.READ),
            ("Status", str, None, tango.AttrWriteType.READ),
            ("SysAddress", int, None, tango.AttrWriteType.READ),
            ("LedPattern", str, None, tango.AttrWriteType.READ),
            ("InputVoltage", float, None, tango.AttrWriteType.READ),
            ("PowerSupplyOutputVoltage", float, None, tango.AttrWriteType.READ),
            ("PowerSupplyTemperature", float, None, tango.AttrWriteType.READ),
            ("PcbTemperature", float, None, tango.AttrWriteType.READ),
            ("FemAmbientTemperature", float, None, tango.AttrWriteType.READ),
            ("FemCaseTemperatures", (float,), 2, tango.AttrWriteType.READ),
            ("FemHeatsinkTemperatures", (float,), 2, tango.AttrWriteType.READ),
            ("WarningFlags", str, None, tango.AttrWriteType.READ),
            ("AlarmFlags", str, None, tango.AttrWriteType.READ),
            (
                "PortForcings",
                (str,),
                NUMBER_OF_SMARTBOX_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortBreakersTripped",
                (bool,),
                NUMBER_OF_SMARTBOX_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortsDesiredPowerOnline",
                (bool,),
                NUMBER_OF_SMARTBOX_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortsDesiredPowerOffline",
                (bool,),
                NUMBER_OF_SMARTBOX_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortsPowerSensed",
                (bool,),
                NUMBER_OF_SMARTBOX_PORTS,
                tango.AttrWriteType.READ,
            ),
            (
                "PortsCurrentDraw",
                (float,),
                NUMBER_OF_SMARTBOX_PORTS,
                tango.AttrWriteType.READ,
            ),
            ("InputVoltageThresholds", (float,), 4, tango.AttrWriteType.READ_WRITE),
            (
                "PowerSupplyOutputVoltageThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "PowerSupplyTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            ("PcbTemperatureThresholds", (float,), 4, tango.AttrWriteType.READ_WRITE),
            (
                "FemAmbientTemperatureThresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "FemCaseTemperature1Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "FemCaseTemperature2Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "FemHeatsinkTemperature1Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            (
                "FemHeatsinkTemperature2Thresholds",
                (float,),
                4,
                tango.AttrWriteType.READ_WRITE,
            ),
            ("Fem1CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem2CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem3CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem4CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem5CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem6CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem7CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem8CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem9CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem10CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem11CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
            ("Fem12CurrentTripThreshold", int, None, tango.AttrWriteType.READ_WRITE),
        ]:
            self._setup_pasd_attribute(
                f"smartbox{smartbox_number}{slug}",
                cast(type | tuple[type], data_type),
                max_dim_x=length,
                access=access,
            )

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

    def _write_pasd_attribute(self, pasd_attribute: tango.Attribute) -> None:
        # Register the request with the component manager
        tango_attr_name = pasd_attribute.get_name()
        if tango_attr_name.startswith("fndh"):
            device_id = 0
        else:
            # Obtain smartbox number after 'smartbox' prefix
            # This could be 1 or 2 digits
            tango_attr_name = tango_attr_name.removeprefix("smartbox")
            device_id = (
                int(tango_attr_name[0:2])
                if tango_attr_name[0:2].isdigit()
                else int(tango_attr_name[0])
            )
        logging.debug(
            f"Requesting to write attribute: {pasd_attribute.get_name()} with value"
            f" {pasd_attribute.get_write_value()} for device {device_id}"
        )
        # Get the name of the attribute as understood by the Modbus API
        attribute_dict = self._ATTRIBUTE_MAP[device_id]
        attribute_name = [
            key
            for key, value in attribute_dict.items()
            if value == pasd_attribute.get_name()
        ][0]

        self.component_manager.write_attribute(
            device_id, attribute_name, pasd_attribute.get_write_value(ExtractAs.List)
        )

    def _setup_pasd_attribute(
        self: MccsPasdBus,
        attribute_name: str,
        data_type: type | tuple[type],
        max_dim_x: Optional[int] = None,
        access: tango.AttrWriteType = tango.AttrWriteType.READ,
    ) -> None:
        self._pasd_state[attribute_name] = None
        attr = tango.server.attribute(
            name=attribute_name,
            dtype=data_type,
            access=access,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fget=self._read_pasd_attribute,
            fset=self._write_pasd_attribute,
        ).to_attr()
        self.add_attribute(
            attr, self._read_pasd_attribute, self._write_pasd_attribute, None
        )
        self.set_change_event(attribute_name, True, False)
        self.set_archive_event(attribute_name, True, False)

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
            self.PollingRate,
            self.DevicePollingRate,
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
            ("SetFndhPortPowers", MccsPasdBus._SetFndhPortPowersCommand),
            ("SetFndhLedPattern", MccsPasdBus._SetFndhLedPatternCommand),
            ("ResetFndhPortBreaker", MccsPasdBus._ResetFndhPortBreakerCommand),
            ("SetSmartboxPortPowers", MccsPasdBus._SetSmartboxPortPowersCommand),
            (
                "SetSmartboxLedPattern",
                MccsPasdBus._SetSmartboxLedPatternCommand,
            ),
            (
                "ResetSmartboxPortBreaker",
                MccsPasdBus._ResetSmartboxPortBreakerCommand,
            ),
            ("ResetFndhAlarms", MccsPasdBus._ResetFndhAlarmsCommand),
            ("ResetFndhWarnings", MccsPasdBus._ResetFndhWarningsCommand),
            ("ResetSmartboxAlarms", MccsPasdBus._ResetSmartboxAlarmsCommand),
            ("ResetSmartboxWarnings", MccsPasdBus._ResetSmartboxWarningsCommand),
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

    def delete_device(self) -> None:
        """
        Prepare to delete the device.

        Make sure the component manager doesn't have a socket open.
        (The socket should be closed when it is deleted,
        but it is good practice to close it explicitly anyhow.)
        """
        self.component_manager.stop_communicating()

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

        if "error" in kwargs:
            # TODO: handle error response from API for known device
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

        :return: A tuple containing a result code and a human-readable status message.
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

    class _SetFndhPortPowersCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_SetFndhPortPowers.json",
            )
        )

        def __init__(
            self: MccsPasdBus._SetFndhPortPowersCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("SetFndhPortPowers", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetFndhPortPowersCommand,
            port_powers: list[bool | None],
            stay_on_when_offline: bool,
        ) -> Optional[bool]:
            """
            Turn on an FNDH port.

            :param port_powers: desired power of each port.
                False means off, True means on, None means no desired change.
            :param stay_on_when_offline: whether any ports being turned on
                should remain on if communication with the MCCS is lost.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.set_fndh_port_powers(
                port_powers, stay_on_when_offline
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetFndhPortPowers(self: MccsPasdBus, argin: str) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set FNDH port powers.

        This command takes as input a JSON string that conforms to the
        following schema:

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetFndhPortPowers.json
           :language: json

        :param argin: a JSON string specifying the request.

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        handler = self.get_command_object("SetFndhPortPowers")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["SetFndhPortPowers succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["SetFndhPortPowers succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["SetFndhPortPowers failed"])

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

        :return: A tuple containing a result code and a human-readable status message.
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

        :return: A tuple containing a result code and a human-readable status message.
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

        :return: A tuple containing a result code and a human-readable status message.
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

    class _SetSmartboxPortPowersCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_SetSmartboxPortPowers.json",
            )
        )

        def __init__(
            self: MccsPasdBus._SetSmartboxPortPowersCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("SetSmartboxPortPowers", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetSmartboxPortPowersCommand,
            smartbox_number: int,
            port_powers: list[bool | None],
            stay_on_when_offline: bool,
        ) -> Optional[bool]:
            """
            Set a smartbox's port powers.

            :param smartbox_number: number of the smartbox to be
                addressed
            :param port_powers: the desired power for each port.
                True means powered on, False means off,
                None means no desired change
            :param stay_on_when_offline: whether any ports being turned on
                should remain on if communication with the MCCS is lost.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.set_smartbox_port_powers(
                smartbox_number, port_powers, stay_on_when_offline
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetSmartboxPortPowers(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set a smartbox's port powers.

        This command takes as input a JSON string that conforms to the
        following schema:

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetSmartboxPortPowers.json
           :language: json

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        handler = self.get_command_object("SetSmartboxPortPowers")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["SetSmartboxPortPowers succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["SetSmartboxPortPowers succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["SetSmartboxPortPowers failed"])

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

        :return: A tuple containing a result code and a human-readable status message.
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

        :return: A tuple containing a result code and a human-readable status message.
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

    class _ResetFndhAlarmsCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._ResetFndhAlarmsCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetFndhAlarmsCommand,
        ) -> Optional[bool]:
            """
            Reset the FNDH alarms register.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.reset_fndh_alarms()

    @command(dtype_out="DevVarLongStringArray")
    def ResetFndhAlarms(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Reset the FNDH alarms register.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetFndhAlarms")
        success = handler()
        if success:
            return ([ResultCode.OK], ["ResetFndhAlarms succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["ResetFndhAlarms succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["ResetFndhAlarms failed"])

    class _ResetFndhWarningsCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._ResetFndhWarningsCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetFndhWarningsCommand,
        ) -> Optional[bool]:
            """
            Reset the FNDH warnings register.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.reset_fndh_warnings()

    @command(dtype_out="DevVarLongStringArray")
    def ResetFndhWarnings(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Reset the FNDH warnings register.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetFndhWarnings")
        success = handler()
        if success:
            return ([ResultCode.OK], ["ResetFndhwarnings succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["ResetFndhWarnings succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["ResetFndhWarnings failed"])

    class _ResetSmartboxAlarmsCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._ResetSmartboxAlarmsCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetSmartboxAlarmsCommand,
            smartbox_number: int,
        ) -> Optional[bool]:
            """
            Reset a Smartbox's alarms register.

            :param smartbox_number: number of the smartbox to be
                addressed
            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.reset_smartbox_alarms(smartbox_number)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def ResetSmartboxAlarms(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Reset a Smartbox alarms register.

        :param argin: Smartbox number

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetSmartboxAlarms")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["ResetSmartboxAlarms succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["ResetSmartboxAlarms succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["ResetSmartboxAlarms failed"])

    class _ResetSmartboxWarningsCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._ResetSmartboxWarningsCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetSmartboxWarningsCommand,
            smartbox_number: int,
        ) -> Optional[bool]:
            """
            Reset a Smartbox's warnings register.

            :param smartbox_number: number of the smartbox to be
                addressed
            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.reset_smartbox_warnings(smartbox_number)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def ResetSmartboxWarnings(
        self: MccsPasdBus, argin: int
    ) -> DevVarLongStringArrayType:
        """
        Reset a Smartbox warnings register.

        :param argin: Smartbox number

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetSmartboxWarnings")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], ["ResetSmartboxWarnings succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                ["ResetSmartboxWarnings succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], ["ResetSmartboxWarnings failed"])


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
