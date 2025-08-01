# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS SmartBox device."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Final, Optional, cast

import numpy
import tango
from ska_control_model import CommunicationStatus, HealthState, PowerState, ResultCode
from ska_low_mccs_common import MccsBaseDevice
from ska_tango_base.commands import DeviceInitCommand, SubmittedSlowCommand
from tango import DevFailed
from tango.device_attribute import ExtractAs
from tango.server import attribute, command, device_property

from ska_low_mccs_pasd.pasd_bus.pasd_bus_register_map import DesiredPowerEnum
from ska_low_mccs_pasd.pasd_data import PasdData

from ..pasd_controllers_configuration import ControllerDict, PasdControllersConfig
from ..pasd_utils import configure_alarms
from .smart_box_component_manager import SmartBoxComponentManager
from .smartbox_health_model import SmartBoxHealthModel

__all__ = ["MccsSmartBox"]


class JsonSerialize(json.JSONEncoder):
    """Allows numpy arrays to be dumped to json."""

    def default(self, o: Any) -> Any:
        """
        Return json serializable values.

        :param o: object to be made json consumable.

        :return: value that can be consumed by json.
        """
        if isinstance(o, numpy.integer):
            return int(o)
        if isinstance(o, numpy.floating):
            return float(o)
        if isinstance(o, numpy.ndarray):
            return o.tolist()
        return json.JSONEncoder.default(self, o)


@dataclass
class SmartboxAttribute:
    """Class representing the internal state of a Smartbox attribute."""

    value: Any
    quality: tango.AttrQuality
    timestamp: float


# pylint: disable=too-many-instance-attributes
class MccsSmartBox(MccsBaseDevice):
    """An implementation of the SmartBox device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    FieldStationName: Final = device_property(dtype=(str), mandatory=True)
    PasdFQDN: Final = device_property(dtype=(str), mandatory=True)
    SmartBoxNumber: Final = device_property(dtype=int, mandatory=True)
    PortsWithAntennas: Final = device_property(dtype=(int,), default_value=[])
    AntennaNames: Final = device_property(dtype=(str,), default_value=[])
    FndhPort: Final = device_property(dtype=int, mandatory=True)

    CONFIG: Final[ControllerDict] = PasdControllersConfig.get_smartbox()
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
        self.component_manager: SmartBoxComponentManager
        self._health_monitor_points: dict[str, list[float]] = {}

    def init_device(self: MccsSmartBox) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        self._readable_name = re.findall("sb[0-9]+", self.get_name())[0]
        super().init_device()
        self._smartbox_state: dict[str, SmartboxAttribute] = {}
        self._setup_smartbox_attributes()

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tFieldStationName: {self.FieldStationName}\n"
            f"\tPasdFQDN: {self.PasdFQDN}\n"
            f"\tSmartBoxNumber: {self.SmartBoxNumber}\n"
            f"\tPortsWithAntennas: {self.PortsWithAntennas}\n"
            f"\tAntennaNames: {self.AntennaNames}\n"
            f"\tFndhPort: {self.FndhPort}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def delete_device(self: MccsSmartBox) -> None:
        """Delete the device."""
        self.component_manager._pasd_bus_proxy.cleanup()
        self.component_manager._task_executor._executor.shutdown()
        super().delete_device()

    def _init_state_model(self: MccsSmartBox) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = SmartBoxHealthModel(
            self._health_changed_callback, self.logger
        )
        self.set_change_event("healthState", True, False)
        self.set_archive_event("healthState", True, False)
        self.set_change_event("antennaPowers", True, False)
        self.set_archive_event("antennaPowers", True, False)

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
            self.SmartBoxNumber,
            self._readable_name,
            self.CONFIG["number_of_ports"],
            self.PasdFQDN,
            self.PortsWithAntennas,
            self.AntennaNames,
            self.FndhPort,
            event_serialiser=self._event_serialiser,
        )

    def init_command_objects(self: MccsSmartBox) -> None:
        """Initialise the command handlers for this device."""
        super().init_command_objects()

        for command_name, method_name in [
            ("PowerOnPort", "turn_on_port"),
            ("PowerOffPort", "turn_off_port"),
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

    # ----------
    # Commands
    # ----------
    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def PowerOnAntenna(
        self: MccsSmartBox, antenna_name: str
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up an antenna.

        :param antenna_name: the antenna to power up

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        if antenna_name not in self.AntennaNames:
            msg = f"{antenna_name} not on this smartbox: {self.AntennaNames}"
            self.logger.error(msg)
            return ([ResultCode.REJECTED], [msg])
        port_number = self.component_manager._port_to_antenna_map.inverse.get(
            antenna_name
        )
        handler = self.get_command_object("PowerOnPort")
        result_code, message = handler(port_number)
        return ([result_code], [message])

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def PowerOffAntenna(
        self: MccsSmartBox, antenna_name: str
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power off an antenna.

        :param antenna_name: the antenna to power down

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        if antenna_name not in self.AntennaNames:
            msg = f"{antenna_name} not on this smartbox: {self.AntennaNames}"
            self.logger.error(msg)
            return ([ResultCode.REJECTED], [msg])
        port_number = self.component_manager._port_to_antenna_map.inverse.get(
            antenna_name
        )
        handler = self.get_command_object("PowerOffPort")
        result_code, message = handler(port_number)
        return ([result_code], [message])

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

    @command(dtype_in="DevString", dtype_out="DevVarLongStringArray")
    def SetPortPowers(
        self: MccsSmartBox,
        json_argument: str,
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Set port powers.

        These ports may not have an antenna attached.

        :param json_argument: desired port powers of unmasked ports with
            smartboxes attached in json form.
        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("SetPortPowers")
        result_code, message = handler(json_argument)
        return ([result_code], [message])

    # ----------
    # Attributes
    # ----------
    def _setup_smartbox_attributes(self: MccsSmartBox) -> None:
        for register in self.CONFIG["registers"].values():
            data_type = self.TYPES[register["data_type"]]
            self._setup_smartbox_attribute(
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
                description=register["description"],
                unit=register["unit"],
                format_string=register["format_string"],
                min_value=register["min_value"],
                max_value=register["max_value"],
            )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def _setup_smartbox_attribute(
        self: MccsSmartBox,
        attribute_name: str,
        data_type: type | tuple[type],
        access_type: tango.AttrWriteType,
        description: str,
        max_dim_x: Optional[int] = None,
        unit: Optional[str] = None,
        format_string: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> None:
        self._smartbox_state[attribute_name.lower()] = SmartboxAttribute(
            value=None, timestamp=0, quality=tango.AttrQuality.ATTR_INVALID
        )
        attr = tango.server.attribute(
            name=attribute_name,
            dtype=data_type,
            access=access_type,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fget=self._read_smartbox_attribute,
            fset=self._write_smartbox_attribute,
            unit=unit,
            description=description,
            format=format_string,
        ).to_attr()
        self.add_attribute(
            attr, self._read_smartbox_attribute, self._write_smartbox_attribute, None
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

    def _read_smartbox_attribute(self, smartbox_attribute: tango.Attribute) -> None:
        attribute_name = smartbox_attribute.get_name().lower()
        smartbox_attribute.set_value_date_quality(
            self._smartbox_state[attribute_name].value,
            self._smartbox_state[attribute_name].timestamp,
            self._smartbox_state[attribute_name].quality,
        )

    def _write_smartbox_attribute(self, smartbox_attribute: tango.Attribute) -> None:
        # Register the request with the component manager
        tango_attr_name = smartbox_attribute.get_name()
        value = smartbox_attribute.get_write_value(ExtractAs.List)
        self.component_manager.write_attribute(tango_attr_name, value)

    # ----------
    # Callbacks
    # ----------
    def _communication_state_changed(
        self: MccsSmartBox, communication_state: CommunicationStatus
    ) -> None:
        self.logger.debug(
            (
                "Device received callback from component manager that communication "
                "with the component is %s."
            ),
            communication_state.name,
        )

        if communication_state != CommunicationStatus.ESTABLISHED:
            self._component_state_callback(power=PowerState.UNKNOWN)
            self._health_monitor_points = {}
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_callback(power=self.component_manager._power_state)

        super()._communication_state_changed(communication_state)

        self._health_model.update_state(
            communicating=True,
            monitoring_points=self._health_monitor_points,
        )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def _component_state_callback(
        self: MccsSmartBox,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        pasdbus_status: Optional[str] = None,
        fqdn: Optional[str] = None,
        power_state: Optional[PowerState] = None,
        antenna_powers: Optional[str] = None,
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
        :param antenna_powers: the antenna powers.
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
        if fault is not None:
            self._health_model.update_state(fault=fault)
        if power is not None:
            self._health_model.update_state(power=power)
        if pasdbus_status is not None:
            self._health_model.update_state(pasdbus_status=pasdbus_status)
        if antenna_powers is not None:
            self.push_change_event("antennaPowers", antenna_powers)

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
                attr_value = self._smartbox_state[attr_name].value
            else:
                self._smartbox_state[attr_name].value = attr_value
            if "portspowersensed" in attr_name.lower():
                self.component_manager._on_smartbox_ports_power_changed(
                    attr_name, attr_value, attr_quality
                )
            self._smartbox_state[attr_name].quality = attr_quality
            self._smartbox_state[attr_name].timestamp = timestamp

            self.push_change_event(attr_name, attr_value, timestamp, attr_quality)
            self.push_archive_event(attr_name, attr_value, timestamp, attr_quality)

            # If we are reading alarm thresholds, update the alarm configuration
            # for the corresponding Tango attribute
            if attr_name.endswith("thresholds"):
                try:
                    attr_true = attr_name.removesuffix("thresholds")
                    configure_alarms(
                        self.get_device_attr().get_attr_by_name(attr_true),
                        attr_value,
                        self.logger,
                    )
                    self._health_model.health_params = {attr_true: attr_value}
                except DevFailed:
                    # No corresponding attribute to update, continue
                    pass
            elif attr_name.endswith("status"):
                self._health_model.update_state(status=attr_value)
            elif "portbreakerstripped" in attr_name.lower():
                self._health_model.update_state(port_breakers_tripped=attr_value)
            else:
                self._health_monitor_points[attr_name] = attr_value
                self._health_model.update_state(
                    monitoring_points=self._health_monitor_points
                )

        except AssertionError as e:
            self.logger.debug(
                f"""The attribute {attr_name} pushed from MccsPasdBus
                device does not exist in MccsSmartBox"""
            )
            self.logger.error(repr(e))

    @attribute(dtype="DevString", label="FndhPort")
    def fndhPort(self: MccsSmartBox) -> str:
        """
        Return the fndh port the smartbox is attached to.

        :return: the fndh port that the smartbox is attached to.
        """
        return json.dumps(self.component_manager._fndh_port)

    @attribute(dtype="DevString", label="ReadableName")
    def ReadableName(self: MccsSmartBox) -> str:
        """
        Return the name of the smartbox in a readable format.

        :return: the name of the smartbox
        """
        return self._readable_name

    @attribute(dtype=(bool,), label="PortMask", max_dim_x=12)
    def portMask(self: MccsSmartBox) -> list[bool]:
        """
        Return the port mask for this smartbox's ports.

        :return: the port mask for this smartbox's ports.
        """
        return self.component_manager.port_mask

    @portMask.write  # type: ignore[no-redef]
    def portMask(self: MccsSmartBox, port_mask: list[bool]) -> None:
        """
        Set the port mask for this smartbox's ports.

        :param port_mask: the port mask, it must be the correct length (12).

        :raises ValueError: if the length of supplied port mask is incorrect.
        """
        if not len(port_mask) == PasdData.NUMBER_OF_SMARTBOX_PORTS:
            self.logger.error(
                f"Can't set port mask with wrong number of values: {len(port_mask)}."
            )
            raise ValueError(
                f"Can't set port mask with wrong number of values: {len(port_mask)}."
            )
        self.component_manager.port_mask = port_mask

    @attribute(
        dtype="DevString",
        label="AntennaPowers",
    )
    def antennaPowers(self: MccsSmartBox) -> str:
        """
        Get the antenna powers.

        :return: the antenna powers.
        """
        return json.dumps(self.component_manager._antenna_powers)

    @attribute(
        dtype=("str",),
        label="AntennaNames",
        max_dim_x=12,
    )
    def antennaNames(self: MccsSmartBox) -> str:
        """
        Get the names of antennas on this smartbox.

        :return: the names of antennas on this smartbox.
        """
        return self.AntennaNames

    @attribute(
        dtype="DevString",
        format="%s",
    )
    def healthModelParams(self: MccsSmartBox) -> str:
        """
        Get the health params from the health model.

        :return: the health params
        """
        return json.dumps(self._health_model.health_params, cls=JsonSerialize)

    @healthModelParams.write  # type: ignore[no-redef]
    def healthModelParams(self: MccsSmartBox, argin: str) -> None:
        """
        Set the params for health transition rules.

        :param argin: JSON-string of dictionary of health states
        """
        self._health_model.health_params = json.loads(argin)
        self._health_model.update_health()

    @attribute(dtype="DevString")
    def healthReport(self: MccsSmartBox) -> str:
        """
        Get the health report.

        :return: the health report.
        """
        return self._health_model.health_report

    @attribute(dtype="DevBoolean", label="useNewHealthRules")
    def useNewHealthRules(self: MccsSmartBox) -> bool:
        """
        Get whether to use new health rules.

        :return: whether to use new health rules.
        """
        return self._health_model._use_new_health_rules

    @useNewHealthRules.write  # type: ignore[no-redef]
    def useNewHealthRules(self: MccsSmartBox, use_new_rules: bool) -> None:
        """
        Set whether to use new health rules.

        :param use_new_rules: whether to use new rules
        """
        self._health_model.use_new_health_rules = use_new_rules
        self._health_model.update_health()
