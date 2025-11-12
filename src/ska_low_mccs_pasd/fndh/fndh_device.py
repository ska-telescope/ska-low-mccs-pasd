# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
# pylint: disable=too-many-lines
"""This module implements the MCCS FNDH device."""

from __future__ import annotations

import importlib.resources
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Any, Callable, Final, Optional, cast

import tango
from jsonschema import validate
from ska_control_model import (
    AdminMode,
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
)
from ska_low_mccs_common import HealthRecorder, MccsBaseDevice
from ska_tango_base.commands import (
    DeviceInitCommand,
    FastCommand,
    JsonValidator,
    SubmittedSlowCommand,
)
from tango import DevFailed
from tango.device_attribute import ExtractAs
from tango.server import attribute, command, device_property

from ska_low_mccs_pasd.pasd_bus.pasd_bus_register_map import DesiredPowerEnum
from ska_low_mccs_pasd.pasd_data import PasdData

from ..pasd_bus.pasd_bus_conversions import FndhStatusMap
from ..pasd_controllers_configuration import ControllerDict, PasdControllersConfig
from ..pasd_utils import PasdDatabase, PasdThresholds
from .fndh_component_manager import FndhComponentManager
from .fndh_health_model import FndhHealthModel

__all__ = ["MccsFNDH"]


DevVarLongStringArrayType = tuple[list[ResultCode], list[str]]


@dataclass
class FNDHAttribute:
    """Class representing the internal state of a FNDH attribute."""

    value: Any
    quality: tango.AttrQuality
    timestamp: float


# pylint: disable=too-many-instance-attributes
class MccsFNDH(MccsBaseDevice[FndhComponentManager]):
    """An implementation of the FNDH device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    PasdFQDN: Final = device_property(dtype=(str), mandatory=True)
    PortsWithSmartbox: Final = device_property(dtype=(int,), mandatory=True)
    UseAttributesForHealth: Final = device_property(
        doc="Use the attribute quality factor in health. ADR-115.",
        dtype=bool,
        default_value=True,
    )

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
    UPDATE_HEALTH_PARAMS_SCHEMA: Final = json.loads(
        importlib.resources.read_text(
            "ska_low_mccs_pasd.schemas.fndh", "MccsFndh_UpdateHealthParams.json"
        )
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
        self._fndh_attributes: dict[str, FNDHAttribute] = {}
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
        self._health_model: Optional[FndhHealthModel]
        self._health_recorder: Optional[HealthRecorder]
        self._health_report: str = ""
        self._stopping: bool = False
        self._healthful_attributes: dict[str, Callable]
        self._overCurrentThreshold: float
        self._overVoltageThreshold: float
        self._humidityThreshold: float
        self.component_manager: FndhComponentManager
        self._nof_stuck_on_smartbox_ports: Optional[int] = None
        self._nof_stuck_off_smartbox_ports: Optional[int] = None
        self._db_connection: PasdDatabase

        # Health monitor points contains a cache of monitoring points as they
        # are updated in a poll. When communication is lost this cache is
        # reset to empty again.
        self._health_monitor_points: dict[str, list[float]] = {}
        self._ports_with_smartbox: list[int] = self.PortsWithSmartbox

    def init_device(self: MccsFNDH) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        super().init_device()

        # Setup attributes shared with the MccsPasdBus.
        self._setup_fndh_attributes()

        # Attributes for specific ports on the FNDH.
        # These attributes are a breakdown of the portPowerSensed
        # attribute. The reason is to allow smartbox's to subscribe to
        # their power state.
        for port in range(1, self.CONFIG["number_of_ports"] + 1):
            attr_name = f"Port{port}PowerState"
            self._setup_fndh_attribute(
                attr_name,
                PowerState,
                tango.AttrWriteType.READ,
                f"Port {port} power state",
                1,
                PowerState.UNKNOWN,
            )
        self._db_connection = PasdDatabase()

        self._thresholds_tango = PasdThresholds(self.CONFIG)
        self._thresholds_pasd = PasdThresholds(self.CONFIG)

        self.update_threshold_cache()

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tPasdFQDN: {self.PasdFQDN}\n"
            f"\tPortsWithSmartbox: {self.PortsWithSmartbox}\n"
            f"\tUseAttributesForHealth: {self.UseAttributesForHealth}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def delete_device(self: MccsFNDH) -> None:
        """Delete the device."""
        self.component_manager._pasd_bus_proxy.cleanup()
        self.component_manager._task_executor._executor.shutdown()
        self._stopping = True
        if self._health_recorder is not None:
            self._health_recorder.cleanup()
            self._health_recorder = None
        super().delete_device()

    def _init_state_model(self: MccsFNDH) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._healthful_attributes = {
            "pasdStatus": partial(self._fndh_attributes.get, "pasdstatus"),
            "numberOfStuckOnSmartboxPorts": lambda: self._nof_stuck_on_smartbox_ports,
            "numberOfStuckOffSmartboxPorts": lambda: self._nof_stuck_off_smartbox_ports,
        }
        for register in self.CONFIG["registers"].values():
            attr = register["tango_attr_name"]
            if attr.endswith("Thresholds"):
                health_attr = attr.removesuffix("Thresholds")
                self._healthful_attributes[health_attr] = partial(
                    self._fndh_attributes.get, health_attr.lower()
                )
        self.set_change_event("numberOfStuckOnSmartboxPorts", True, False)
        self.set_archive_event("numberOfStuckOnSmartboxPorts", True, False)
        self.set_change_event("numberOfStuckOffSmartboxPorts", True, False)
        self.set_archive_event("numberOfStuckOffSmartboxPorts", True, False)
        if not self.UseAttributesForHealth:
            self._health_model = FndhHealthModel(
                self._health_changed_callback, self.logger
            )
            self._health_model.update_state(ports_with_smartbox=self.PortsWithSmartbox)
            self._health_recorder = None
        else:
            self._health_recorder = HealthRecorder(
                self.get_name(),
                self.logger,
                attributes=list(self._healthful_attributes.keys()),
                health_callback=self._health_changed,
                attr_conf_callback=self._attr_conf_changed,
            )
            self._health_model = None
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
            self.PortsWithSmartbox,
            event_serialiser=self._event_serialiser,
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
    @command(dtype_out="DevVarLongStringArray")
    def UpdateThresholdCache(
        self: MccsFNDH,
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Update the threshold caches.

        :return: A tuple containing a return code and a string message
            indicating status.
        """
        self.update_threshold_cache()
        diff = self._threshold_differences()
        if diff:
            message = f"Thresholds do not match: {diff}"
            return ([ResultCode.FAILED], [message])

        return ([ResultCode.OK], ["UpdateThresholdCache completed"])

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
                description=register["description"],
                max_dim_x=register["tango_dim_x"],
                unit=register["unit"],
                format_string=register["format_string"],
                min_value=register["min_value"],
                max_value=register["max_value"],
            )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def _setup_fndh_attribute(
        self: MccsFNDH,
        attribute_name: str,
        data_type: type | tuple[type],
        access_type: tango.AttrWriteType,
        description: str,
        max_dim_x: Optional[int] = None,
        default_value: Optional[Any] = None,
        unit: Optional[str] = None,
        format_string: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
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
            unit=unit,
            description=description,
            format=format_string,
        ).to_attr()
        self.add_attribute(
            attr,
            self._read_fndh_attribute,
            self._write_fndh_attribute,
            None,
        )
        if min_value is not None or max_value is not None:
            if access_type != tango.AttrWriteType.READ_WRITE:
                self.logger.warning(
                    "Can't set min and max values on read-only "
                    f"attribute {attribute_name}"
                )
            else:
                writeable_attribute = self.get_device_attr().get_w_attr_by_name(
                    attribute_name
                )
                if min_value is not None:
                    writeable_attribute.set_min_value(min_value)
                if max_value is not None:
                    writeable_attribute.set_max_value(max_value)
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
        attr_name = fndh_attribute.get_name().lower()
        if attr_name.endswith("thresholds"):
            if self._admin_mode == AdminMode.ENGINEERING:
                values = fndh_attribute.get_write_value(ExtractAs.List)
                self.component_manager.write_attribute(attr_name, values)
                self._db_connection.put_value(self.get_name(), attr_name, values)
                self._thresholds_tango.update({attr_name: values})
            else:
                self.logger.warning(
                    f"Cannot write attributes {attr_name} unless in engineering mode"
                )
                # raise AttributeError(
                #     f"Cannot write attribute {attr_name} unless in engineering mode"
                # )
        else:
            value = fndh_attribute.get_write_value(ExtractAs.List)
            self.component_manager.write_attribute(attr_name, value)

    def update_threshold_cache(self: MccsFNDH) -> None:
        """Update fndh thresholds cache from database and firmware."""
        for name in self._thresholds_tango.all_thresholds:
            value = self._db_connection.get_value(self.get_name(), name)
            self._thresholds_tango.update(value)

        for name in self._thresholds_pasd.all_thresholds:
            string_vals = []
            for value in self._fndh_attributes[name].value:
                string_vals.append(str(value))
            self._thresholds_pasd.update({name: string_vals})

    def _threshold_differences(self: MccsFNDH) -> dict:
        """
        Compare the tango and firmware thresholds.

        :return: The differences between thresholds.
        """
        differences = {}

        for (
            name,
            thresholds_tango,
        ) in self._thresholds_tango.all_thresholds.items():
            thresholds_pasd = self._thresholds_pasd.all_thresholds[name]
            if isinstance(thresholds_pasd, numpy.ndarray):
                assert isinstance(thresholds_pasd, numpy.ndarray)
                thresholds_pasd = thresholds_pasd.tolist()
            if isinstance(thresholds_tango, numpy.ndarray):
                assert isinstance(thresholds_tango, numpy.ndarray)
                thresholds_tango = thresholds_tango.tolist()
            if thresholds_pasd is None:
                self.logger.debug("Not yet retrieved value from firmware, skipping..")
                continue
            for i, value in enumerate(thresholds_tango):
                if thresholds_tango[i] != thresholds_pasd[i]:
                    differences[
                        name
                    ] = f"tango:{thresholds_tango} != pasd:{thresholds_pasd}"
                    break

        return differences

    @attribute(dtype="DevString", label="ThresholdDifferences")
    def threshold_differences(self: MccsFNDH) -> str:
        """
        Return the differences between threshold values.

        :return: Return the differences between threshold values.
        """
        return json.dumps(self._threshold_differences())

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

    @attribute(
        dtype="DevString",
        label="return the version of healthRules in use. Only v0 and v1 available.",
    )
    def healthRuleVersion(self: MccsFNDH) -> str:
        """
        Return the HealthRuleVersion in use.

        :return: the HealthRuleVersion is use.
        """
        if self._health_model.health_rule_active:
            return "v1"
        return "v0"

    @healthRuleVersion.write  # type: ignore[no-redef]
    def healthRuleVersion(self: MccsFNDH, value: str) -> None:
        """
        Set the HealthRuleVersion to use.

        :param value: new version to use. Currenly support v0 or v1

        :raises ValueError: when attempting to set a version not
            supported.
        """
        version = value.lower()
        if version not in ["v0", "v1"]:
            raise ValueError("We only support versions v0 and v1")
        if version == "v0":
            self._health_model.health_rule_active = False
            self.logger.info("De-activated the new healthRules.")
            return
        self._health_model.health_rule_active = True
        self.logger.info("Activated the new healthRules.")

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

    @attribute(dtype=("DevShort",), label="portsWithSmartbox", max_dim_x=24)
    def portsWithSmartbox(self: MccsFNDH) -> list[bool]:
        """
        Return the ports with a smartbox attached.

        :return: the ports with smartbox attached.
        """
        return self._ports_with_smartbox

    @portsWithSmartbox.write  # type: ignore[no-redef]
    def portsWithSmartbox(self: MccsFNDH, port_numbers: list[int]) -> None:
        """
        Set the ports with smartbox attached.

        :param port_numbers: the port numbers with a smartbox attached.

        :raises ValueError: if the number of smartbox exceeds the maximum allowed for
            a station.
        """
        if len(port_numbers) > PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION:
            self.logger.error(
                "The number of ports with smartbox is over the "
                f"maximum for a station: {len(port_numbers)}."
            )
            raise ValueError(
                "The number of ports with smartbox is over the "
                f"maximum for a station: {len(port_numbers)}."
            )
        self._ports_with_smartbox = port_numbers
        self.component_manager._ports_with_smartbox = port_numbers
        if self._health_model is not None:
            self._health_model.update_state(
                ports_with_smartbox=self._ports_with_smartbox
            )

    @attribute(dtype="DevShort", max_alarm=5, max_warning=1)
    def numberOfStuckOnSmartboxPorts(self: MccsFNDH) -> Optional[int]:
        """
        Return the total number of stuck on smartbox ports.

        This is used for alarm configuration.

        :return: the total number of stuck on smartbox ports.
        """
        return self._nof_stuck_on_smartbox_ports

    @attribute(dtype="DevShort", max_alarm=5, max_warning=1)
    def numberOfStuckOffSmartboxPorts(self: MccsFNDH) -> Optional[int]:
        """
        Return the total number of stuck off smartbox ports.

        This is used for alarm configuration.

        :return: the total number of stuck off smartbox ports.
        """
        return self._nof_stuck_off_smartbox_ports

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
            # Clear the cached monitoring points due to loss of communication.
            self._health_monitor_points = {}
            if self._health_recorder is not None:
                self._health_recorder.clear_attribute_state()

            self._component_state_changed(power=PowerState.UNKNOWN)
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._update_port_power_states(self._port_power_states)
            self._component_state_changed(power=self.component_manager._power_state)

        super()._communication_state_changed(communication_state)
        if self._health_model is not None:
            self._health_model.update_state(
                communicating=(communication_state == CommunicationStatus.ESTABLISHED),
                monitoring_points=self._health_monitor_points,
            )

    def _update_port_power_states(
        self: MccsFNDH, power_states: list[PowerState]
    ) -> None:
        assert self.CONFIG["number_of_ports"] == len(power_states)
        timestamp = datetime.now(timezone.utc).timestamp()
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
        self.component_manager._fndh_port_powers = self._port_power_states
        self.component_manager.fndh_ports_change.set()
        self.component_manager._evaluate_power()

    def _component_state_changed_callback(
        self: MccsFNDH,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        fqdn: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param fqdn: the fqdn of the device calling.
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if fqdn is not None and self._health_model is not None:
            if "health" in kwargs:
                # NOTE: If the health is updated with None it means
                # we do not roll up the power.
                if kwargs.get("health", "") is None:
                    self._health_model.update_state(ignore_pasd_power=True)
                else:
                    self._health_model.update_state(ignore_pasd_power=False)
            self._health_model.update_state(pasd_power=power)
            return
        super()._component_state_changed(fault=fault, power=power)
        if fault is not None and self._health_model is not None:
            self._health_model.update_state(fault=fault)
        if power is not None and self._health_model is not None:
            self._health_model.update_state(power=power)

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

    def _health_changed(
        self: MccsFNDH, health: HealthState, health_report: str
    ) -> None:
        """
        Handle change in this device's health state.

        This is a callback hook, called whenever the HealthModel's
        evaluated health state changes. It is responsible for updating
        the tango side of things i.e. making sure the attribute is up to
        date, and events are pushed.

        :param health: the new health value
        :param health_report: the health report
        """
        if self._stopping:
            return
        self._health_report = health_report
        if self._health_state != health:
            self._health_state = health
            self.push_change_event("healthState", health)
            self.push_archive_event("healthState", health)

    def _attr_conf_changed(self: MccsFNDH, attribute_name: str) -> None:
        """
        Handle change in configuration of an attribute.

        This is a workaround as if you configure an attribute
        which is not alarming to have alarm/warning thresholds
        such that it would be alarming, Tango does not push an event
        until the attribute value changes.

        :param attribute_name: the name of the attribute whose
            configuration has changed.
        """
        if (
            attribute_name in self._healthful_attributes
            and self._healthful_attributes[attribute_name]() is not None
        ):
            attr = self._healthful_attributes[attribute_name]()
            value = attr.value if isinstance(attr, FNDHAttribute) else attr
            if value is not None:
                self.push_change_event(attribute_name, value)

    def _attribute_changed_callback(  # noqa: C901
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
            if attr_value is None:
                # This happens when the upstream attribute's quality factor has
                # been set to INVALID. Pushing a change event with None
                # triggers an exception so we change it to the last known value here
                attr_value = self._fndh_attributes[attr_name].value
            else:
                self._fndh_attributes[attr_name].value = attr_value
            # Status register mapping to quality to health:
            # UNINITIALISED -> ATTR_VALID -> OK
            # OK -> ATTR_VALID -> OK
            # WARNING -> ATTR_WARNING -> DEGRADED
            # ALARM -> ATTR_ALARM -> FAILED
            # RECOVERY -> ATTR_ALARM -> FAILED
            # POWERDOWN -> ATTR_INVALID -> UNKNOWN (shouldn't be seen in operation)
            if "pasdstatus" in attr_name.lower():
                pasd_status_quality = self._convert_status_to_quality(attr_value)
                if pasd_status_quality in [
                    tango.AttrQuality.ATTR_ALARM,
                    tango.AttrQuality.ATTR_WARNING,
                ]:
                    self.set_state(tango.DevState.ALARM)
                attr_quality = pasd_status_quality
            self._fndh_attributes[attr_name].quality = attr_quality
            self._fndh_attributes[attr_name].timestamp = timestamp

            self.push_change_event(attr_name, attr_value, timestamp, attr_quality)
            self.push_archive_event(attr_name, attr_value, timestamp, attr_quality)

            # If we are reading alarm thresholds, update the alarm configuration
            # for the corresponding Tango attribute
            if self._health_model is not None:
                if attr_name.endswith("thresholds"):
                    try:
                        threshold_attribute_name = attr_name.removesuffix("thresholds")
                        self._health_model.update_monitoring_point_threshold(
                            threshold_attribute_name, attr_value
                        )
                        self._thresholds_pasd.update({attr_name: attr_value})
                        diff = self._threshold_differences()
                        if diff:
                            self.logger.error(
                                f"Mismatch between firmware and tango thresholds: {diff}"
                            )
                            self._component_state_changed(fault=True)
                    except DevFailed:
                        # No corresponding attribute to update, continue
                        pass
                elif attr_name.endswith("status"):
                    self._health_model.update_state(status=attr_value)
                else:
                    self._health_monitor_points[attr_name] = attr_value
                    self._health_model.update_state(
                        monitoring_points=self._health_monitor_points
                    )
            if attr_name in ("portspowersensed", "portspowercontrol"):
                self._evaluate_faulty_ports()
        except AssertionError:
            self.logger.error(
                f"""The attribute {attr_name} pushed from MccsPasdBus
                device does not exist in MccsFNDH"""
            )

    def _evaluate_faulty_ports(self: MccsFNDH) -> None:
        port_power_control = self._fndh_attributes.get("portspowercontrol")
        port_power_sensed = self._fndh_attributes.get("portspowersensed")
        if (
            port_power_control is not None
            and port_power_control.value is not None
            and port_power_sensed is not None
            and port_power_sensed.value is not None
        ):
            nof_stuck_off_smartbox_ports = sum(
                not powered and controlled
                for i, (powered, controlled) in enumerate(
                    zip(port_power_sensed.value, port_power_control.value),
                    start=1,
                )
                if i in self._ports_with_smartbox
            )
            nof_stuck_on_smartbox_ports = sum(
                powered and not controlled
                for i, (powered, controlled) in enumerate(
                    zip(port_power_sensed.value, port_power_control.value),
                    start=1,
                )
                if i in self._ports_with_smartbox
            )
            if nof_stuck_off_smartbox_ports != self._nof_stuck_off_smartbox_ports:
                self._nof_stuck_off_smartbox_ports = nof_stuck_off_smartbox_ports
                self.push_change_event(
                    "numberOfStuckOffSmartboxPorts",
                    self._nof_stuck_off_smartbox_ports,
                )
                self.push_archive_event(
                    "numberOfStuckOffSmartboxPorts",
                    self._nof_stuck_off_smartbox_ports,
                )
            if nof_stuck_on_smartbox_ports != self._nof_stuck_on_smartbox_ports:
                self._nof_stuck_on_smartbox_ports = nof_stuck_on_smartbox_ports
                self.push_change_event(
                    "numberOfStuckOnSmartboxPorts",
                    self._nof_stuck_on_smartbox_ports,
                )
                self.push_archive_event(
                    "numberOfStuckOnSmartboxPorts",
                    self._nof_stuck_on_smartbox_ports,
                )

    @staticmethod
    def _convert_status_to_quality(pasd_status: Optional[str]) -> tango.AttrQuality:
        match pasd_status:
            case None | FndhStatusMap.POWERUP.name:
                return tango.AttrQuality.ATTR_INVALID
            case FndhStatusMap.UNINITIALISED.name | FndhStatusMap.OK.name:
                return tango.AttrQuality.ATTR_VALID
            case FndhStatusMap.WARNING.name:
                return tango.AttrQuality.ATTR_WARNING
            case FndhStatusMap.ALARM.name | FndhStatusMap.RECOVERY.name:
                return tango.AttrQuality.ATTR_ALARM
            case _:
                return tango.AttrQuality.ATTR_INVALID

    @attribute(
        dtype="DevString",
        format="%s",
    )
    def healthModelParams(self: MccsFNDH) -> str:
        """
        Get the health params from the health model.

        Monitoring points will have a thresholds defined by a list
        ``[max_alm, max_warn, min_warn, min_alm]`` this is specified by
        the polling of the hardware. It is suggested not to
        modify these defaults but not enforced.
        See:
        https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html
        for extra information.

        :return: the health params
        """
        return json.dumps(self._health_model.health_params)

    @healthModelParams.write  # type: ignore[no-redef]
    def healthModelParams(self: MccsFNDH, argin: str) -> None:
        """
        Set the params for health transition rules.

        :param argin: JSON-string of dictionary of health states
        """
        validate(json.loads(argin), self.UPDATE_HEALTH_PARAMS_SCHEMA)
        self._health_model.health_params = json.loads(argin)
        self._health_model.update_health()

    @attribute(dtype="DevString")
    def healthReport(self: MccsFNDH) -> str:
        """
        Get the health report.

        :return: the health report.
        """
        if self._health_model is not None:
            return self._health_model.health_report
        return self._health_report
