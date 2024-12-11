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
from dataclasses import dataclass
from datetime import datetime, timezone
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
from tango import AttrQuality
from tango.device_attribute import ExtractAs
from tango.server import command

from ska_low_mccs_pasd.pasd_data import PasdData

from ..pasd_controllers_configuration import ControllerDict
from .pasd_bus_component_manager import PasdBusComponentManager
from .pasd_bus_conversions import FndhStatusMap, SmartboxStatusMap
from .pasd_bus_health_model import PasdBusHealthModel
from .pasd_bus_register_map import DesiredPowerEnum

__all__ = ["MccsPasdBus", "main"]


DevVarLongStringArrayType = tuple[list[ResultCode], list[Optional[str]]]


@dataclass
class PasdAttribute:
    """Class representing the internal state of a PaSD attribute."""

    value: Any
    quality: AttrQuality
    timestamp: float


# pylint: disable=too-many-lines, too-many-instance-attributes
class MccsPasdBus(SKABaseDevice[PasdBusComponentManager]):
    """An implementation of a PaSD bus Tango device for MCCS."""

    # pylint: disable=attribute-defined-outside-init
    # Because Tango devices define attributes in init_device.

    # ----------
    # Properties
    # ----------
    Host: Final = tango.server.device_property(dtype=str)
    Port: Final = tango.server.device_property(dtype=int)
    PollingRate: Final = tango.server.device_property(dtype=float, default_value=0.5)
    DevicePollingRate: Final = tango.server.device_property(
        dtype=float, default_value=15.0
    )
    Timeout: Final = tango.server.device_property(dtype=float)
    # Default low-pass filtering cut-off frequency for sensor readings.
    # It is automatically written to all sensor registers of the FNDH and smartboxes
    # after MccsPasdBus is initialised and set ONLINE, and after any of them are powered
    # on or reset later.
    LowPassFilterCutoff: int = tango.server.device_property(
        dtype=float, default_value=10.0, update_db=True
    )
    # Current trip threshold, used for all FEMs (optional).
    # If set, it is automatically written to all smartboxes on power up / reset.
    FEMCurrentTripThreshold: int = tango.server.device_property(dtype=int)
    SimulationConfig: Final = tango.server.device_property(
        dtype=int, default_value=SimulationMode.FALSE
    )
    AvailableSmartboxes: Final[list[int]] = tango.server.device_property(
        dtype="DevVarShortArray",
        default_value=list(range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1)),
    )

    # ---------
    # Constants
    # ---------
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
    def init_device(self: MccsPasdBus) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        super().init_device()
        self._init_pasd_devices = True

        self._simulation_mode = self.SimulationConfig

        self._build_state: str = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id: str = sys.modules["ska_low_mccs_pasd"].__version__

        self._pasd_state: dict[str, PasdAttribute] = {}
        for key, controller in PasdData.CONTROLLERS_CONFIG.items():
            if key == "FNSC":
                for smartbox_number in self.AvailableSmartboxes:
                    self._setup_controller_attributes(controller, str(smartbox_number))
            else:
                self._setup_controller_attributes(controller)

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
            f"\tLowPassFilterCutoff: {self.LowPassFilterCutoff}\n"
            f"\tFEMCurrentTripThreshold: {self.FEMCurrentTripThreshold}\n"
            f"\tSimulationConfig: {self.SimulationConfig}\n"
            f"\tAvailableSmartboxes: {self.AvailableSmartboxes}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def _setup_controller_attributes(
        self: MccsPasdBus, controller_config: ControllerDict, id_no: str = ""
    ) -> None:
        for register in controller_config["registers"].values():
            data_type = self.TYPES[register["data_type"]]
            if register["tango_attr_name"] == "PasdStatus":
                register["tango_attr_name"] = "Status"
            self._setup_pasd_attribute(
                controller_config["prefix"] + id_no + register["tango_attr_name"],
                cast(
                    type | tuple[type],
                    (data_type if register["tango_dim_x"] == 1 else (data_type,)),
                ),
                max_dim_x=register["tango_dim_x"],
                access=(
                    tango.AttrWriteType.READ_WRITE
                    if register["writable"]
                    else tango.AttrWriteType.READ
                ),
            )

    def _read_pasd_attribute(self, pasd_attribute: tango.Attribute) -> None:
        attr_name = pasd_attribute.get_name()
        attr_value = self._pasd_state[attr_name].value
        if attr_value is None:
            msg = f"Attempted read of {attr_name} before it has been polled."
            self.logger.warning(msg)
            raise tango.Except.throw_exception(
                f"Error: {attr_name} is None", msg, "".join(traceback.format_stack())
            )
        pasd_attribute.set_value_date_quality(
            attr_value,
            self._pasd_state[attr_name].timestamp,
            self._pasd_state[attr_name].quality,
        )

    def _write_pasd_attribute(self, pasd_attribute: tango.Attribute) -> None:
        # Register the request with the component manager
        tango_attr_name: str = pasd_attribute.get_name()
        if tango_attr_name.startswith("fndh"):
            tango_attr_name = tango_attr_name.removeprefix("fndh")
            device_id = PasdData.FNDH_DEVICE_ID
            controller_config = PasdData.CONTROLLERS_CONFIG["FNPC"]
        elif tango_attr_name.startswith("fncc"):
            tango_attr_name = tango_attr_name.removeprefix("fncc")
            device_id = PasdData.FNCC_DEVICE_ID
            controller_config = PasdData.CONTROLLERS_CONFIG["FNCC"]
        else:
            # Obtain smartbox number after 'smartbox' prefix
            # This could be 1 or 2 digits
            tango_attr_name = tango_attr_name.removeprefix("smartbox")
            device_id = (
                int(tango_attr_name[0:2])
                if tango_attr_name[0:2].isdigit()
                else int(tango_attr_name[0])
            )
            tango_attr_name = tango_attr_name.lstrip("0123456789")
            controller_config = PasdData.CONTROLLERS_CONFIG["FNSC"]

        self.logger.debug(
            f"Requesting to write attribute: {pasd_attribute.get_name()} with value"
            f" {pasd_attribute.get_write_value()} for device {device_id}"
        )
        # Get the name of the attribute (dict key) as understood by the Modbus API
        for key, register in controller_config["registers"].items():
            if register["tango_attr_name"] == tango_attr_name:
                self.component_manager.write_attribute(
                    device_id,
                    key,
                    pasd_attribute.get_write_value(ExtractAs.List),
                )
                break

    def _setup_pasd_attribute(
        self: MccsPasdBus,
        attribute_name: str,
        data_type: type | tuple[type],
        max_dim_x: Optional[int] = None,
        access: tango.AttrWriteType = tango.AttrWriteType.READ,
    ) -> None:
        # Initialize all attributes as INVALID until read from the h/w
        self._pasd_state[attribute_name] = PasdAttribute(
            value=None, timestamp=0, quality=AttrQuality.ATTR_INVALID
        )
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

    def _init_state_model(self: MccsPasdBus) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = PasdBusHealthModel(self._health_changed)
        self.set_change_event("healthState", True, False)

    def _set_all_low_pass_filters_of_device(
        self: MccsPasdBus, pasd_device_number: int
    ) -> None:
        """
        Set all the low-pass filter constants of a given PaSD device.

        :param pasd_device_number: the number of the PaSD device to set.
            0 refers to the FNDH, otherwise the device number is the
            smartbox number.
        """
        if pasd_device_number == 0:
            self.component_manager.set_fndh_low_pass_filters(self.LowPassFilterCutoff)
            self.component_manager.set_fndh_low_pass_filters(
                self.LowPassFilterCutoff, True
            )
        else:
            self.component_manager.set_smartbox_low_pass_filters(
                pasd_device_number, self.LowPassFilterCutoff
            )
            self.component_manager.set_smartbox_low_pass_filters(
                pasd_device_number, self.LowPassFilterCutoff, True
            )

    def _set_fem_current_trip_thresholds(self: MccsPasdBus, smartbox_id: int) -> None:
        """
        Set all the FEM current trip thresholds on the given smartbox device.

        :param smartbox_id: the smartbox number to write to.
        """
        if self.FEMCurrentTripThreshold is not None:
            self.component_manager.write_attribute(
                smartbox_id,
                "fem_current_trip_thresholds",
                [self.FEMCurrentTripThreshold] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            )

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
            self.AvailableSmartboxes,
        )

    def init_command_objects(self: MccsPasdBus) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for command_name, command_class in [
            ("InitializeFndh", MccsPasdBus._InitializeFndhCommand),
            ("ResetFnccStatus", MccsPasdBus._ResetFnccStatusCommand),
            ("SetFndhPortPowers", MccsPasdBus._SetFndhPortPowersCommand),
            ("SetFndhLedPattern", MccsPasdBus._SetFndhLedPatternCommand),
            ("SetFndhLowPassFilters", MccsPasdBus._SetFndhLowPassFiltersCommand),
            ("ResetFndhAlarms", MccsPasdBus._ResetFndhAlarmsCommand),
            ("ResetFndhWarnings", MccsPasdBus._ResetFndhWarningsCommand),
            ("SetSmartboxPortPowers", MccsPasdBus._SetSmartboxPortPowersCommand),
            (
                "SetSmartboxLedPattern",
                MccsPasdBus._SetSmartboxLedPatternCommand,
            ),
            (
                "SetSmartboxLowPassFilters",
                MccsPasdBus._SetSmartboxLowPassFiltersCommand,
            ),
            (
                "ResetSmartboxPortBreaker",
                MccsPasdBus._ResetSmartboxPortBreakerCommand,
            ),
            ("ResetSmartboxAlarms", MccsPasdBus._ResetSmartboxAlarmsCommand),
            ("ResetSmartboxWarnings", MccsPasdBus._ResetSmartboxWarningsCommand),
        ]:
            self.register_command_object(
                command_name,
                command_class(self.component_manager, self.logger),
            )
        self.register_command_object(
            "InitializeSmartbox",
            MccsPasdBus._InitializeSmartboxCommand(
                self.component_manager, self.logger, self.FEMCurrentTripThreshold
            ),
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

        if communication_state is CommunicationStatus.ESTABLISHED:
            self._health_model.update_state(communicating=True)
        else:
            self._health_model.update_state(communicating=False)

        if (
            self._init_pasd_devices
            and self._simulation_mode == SimulationMode.FALSE
            and communication_state == CommunicationStatus.ESTABLISHED
        ):
            self._init_pasd_devices = False
            for device_number in self.AvailableSmartboxes + [PasdData.FNDH_DEVICE_ID]:
                self._set_all_low_pass_filters_of_device(device_number)
            for device_number in self.AvailableSmartboxes:
                self._set_fem_current_trip_thresholds(device_number)

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

        Note that this "component" is the PaSD bus itself,
        and the PaSD bus has no monitoring points.
        All we can do is infer that it is powered on and not in fault,
        from the fact that we receive responses to our requests.

        The responses themselves deliver information about
        the state of the devices attached to the bus.
        This payload is handled by a different callback.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param kwargs: additional keyword arguments defining component
            state.
        """
        super()._component_state_changed(fault=fault, power=power)
        self._health_model.update_state(fault=fault, power=power)

    def _pasd_device_state_callback(  # noqa: C901
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
        timestamp = datetime.now(timezone.utc).timestamp()
        if (
            pasd_device_number
            not in [PasdData.FNCC_DEVICE_ID, PasdData.FNDH_DEVICE_ID]
            + self.AvailableSmartboxes
        ):
            self.logger.error(
                f"Received update for unknown PaSD device number {pasd_device_number}."
            )
            return

        def _get_tango_attribute_name(
            pasd_device_number: int, pasd_attribute_name: str
        ) -> str:
            for controller in PasdData.CONTROLLERS_CONFIG.values():
                if controller.get("pasd_number") == pasd_device_number:
                    for key, register in controller["registers"].items():
                        if key == pasd_attribute_name:
                            return controller["prefix"] + register["tango_attr_name"]
            for key, register in PasdData.CONTROLLERS_CONFIG["FNSC"][
                "registers"
            ].items():
                if key == pasd_attribute_name:
                    return (
                        PasdData.CONTROLLERS_CONFIG["FNSC"]["prefix"]
                        + str(pasd_device_number)
                        + register["tango_attr_name"]
                    )
            return ""

        if "error" in kwargs:
            # Mark the quality factor for the attribute(s) as INVALID
            for pasd_attribute_name in kwargs["attributes"]:
                tango_attribute_name = _get_tango_attribute_name(
                    pasd_device_number, pasd_attribute_name
                )
                self.logger.debug(f"Tango attribute name: {tango_attribute_name}.")
                self._pasd_state[tango_attribute_name].timestamp = timestamp
                # Only push out a change event if the attribute was previously valid
                if (
                    self._pasd_state[tango_attribute_name].quality
                    != AttrQuality.ATTR_INVALID
                ):
                    self._pasd_state[
                        tango_attribute_name
                    ].quality = AttrQuality.ATTR_INVALID
                    self.push_change_event(
                        tango_attribute_name,
                        self._pasd_state[tango_attribute_name].value,
                        timestamp,
                        AttrQuality.ATTR_INVALID,
                    )
            return

        for pasd_attribute_name, pasd_attribute_value in kwargs.items():
            tango_attribute_name = _get_tango_attribute_name(
                pasd_device_number, pasd_attribute_name
            )
            self.logger.debug(
                f"Tango attribute name: {tango_attribute_name}, "
                f"value: {pasd_attribute_value}"
            )
            if tango_attribute_name == "":
                self.logger.error(
                    f"Received update for unknown PaSD attribute {pasd_attribute_name} "
                    f"(for PaSD device {pasd_device_number})."
                )
                # Continue on to allow other attributes to be updated

            # Update the timestamp
            self._pasd_state[tango_attribute_name].timestamp = timestamp

            if pasd_attribute_name == "status":
                # Determine if the device has been reset or powered on since
                # MCCS was started by checking if its status changed to UNINITIALISED
                previous_status = self._pasd_state[tango_attribute_name].value
                if (
                    pasd_attribute_value != previous_status
                    and pasd_attribute_value
                    in (
                        FndhStatusMap.UNINITIALISED.name,
                        SmartboxStatusMap.UNINITIALISED.name,
                    )
                ):
                    # Register a request to read the static info and thresholds
                    self.component_manager.request_startup_info(pasd_device_number)
                    # Set the device's low-pass filter constants
                    if self._simulation_mode == SimulationMode.FALSE:
                        self._set_all_low_pass_filters_of_device(pasd_device_number)
                    # Set the FEM current trip thresholds
                    if pasd_device_number in self.AvailableSmartboxes:
                        self._set_fem_current_trip_thresholds(pasd_device_number)

            self._pasd_state[tango_attribute_name].value = pasd_attribute_value
            self._pasd_state[tango_attribute_name].quality = AttrQuality.ATTR_VALID
            self.push_change_event(
                tango_attribute_name,
                pasd_attribute_value,
                timestamp,
                AttrQuality.ATTR_VALID,
            )

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
        ) -> None:
            """Initialize an FNDH."""
            self._component_manager.initialize_fndh()

    @command(dtype_out="DevVarLongStringArray")
    def InitializeFndh(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Initialize an FNDH.

        :return: A tuple containing a result code and a human-readable status message.
        """
        handler = self.get_command_object("InitializeFndh")
        handler()
        return ([ResultCode.OK], ["InitializeFndh command requested."])

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
        ) -> None:
            """
            Turn on an FNDH port.

            :param port_powers: desired power of each port.
                False means off, True means on, None means no desired change.
            :param stay_on_when_offline: whether any ports being turned on
                should remain on if communication with the MCCS is lost.
            """
            self._component_manager.set_fndh_port_powers(
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
        handler(argin)
        return ([ResultCode.OK], ["SetFndhPortPowers command requested."])

    class _SetFndhLedPatternCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_SetFndhLedPattern.json",
            )
        )

        def __init__(
            self: MccsPasdBus._SetFndhLedPatternCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("SetFndhLedPattern", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetFndhLedPatternCommand,
            pattern: str,
        ) -> None:
            """
            Set the FNDH service LED pattern.

            :param pattern: name of the service LED pattern.
            """
            self._component_manager.set_fndh_led_pattern(pattern)

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetFndhLedPattern(self: MccsPasdBus, argin: str) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set the FNDH service LED pattern.

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetFndhLedPattern.json
           :language: json

        :param argin: a JSON string specifying the request.

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        handler = self.get_command_object("SetFndhLedPattern")
        handler(argin)
        return ([ResultCode.OK], ["SetFndhLedPattern command requested."])

    class _SetFndhLowPassFiltersCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_SetFndhLowPassFilters.json",
            )
        )

        def __init__(
            self: MccsPasdBus._SetFndhLowPassFiltersCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("SetFndhLowPassFilters", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetFndhLowPassFiltersCommand,
            cutoff: int,
            extra_sensors: bool = False,
        ) -> None:
            """
            Set the FNDH's sensors' low pass filter constants.

            :param cutoff: frequency of LPF to set.
            :param extra_sensors: write the constant to the extra sensors' registers
                after the LED status register.
            """
            self._component_manager.set_fndh_low_pass_filters(cutoff, extra_sensors)

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetFndhLowPassFilters(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set the FNDH's sensors' low pass filter constants.

        The given cut-off frequency is stored as the LowPassFilterCutoff property in the
        tango database. It is automatically written to all sensor registers of the FNDH
        and smartboxes after MccsPasdBus is initialised and set ONLINE, and after any of
        them are powered on or reset later.

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetFndhLowPassFilters.json
           :language: json

        :param argin: a JSON string specifying the request.

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        if self._simulation_mode == SimulationMode.TRUE:
            return (
                [ResultCode.NOT_ALLOWED],
                ["SetFndhLowPassFilters is not supported by the simulator"],
            )
        handler = self.get_command_object("SetFndhLowPassFilters")
        handler(argin)
        return ([ResultCode.OK], ["SetFndhLowPassFilters command requested."])

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
        ) -> None:
            """Reset the FNDH alarms register."""
            self._component_manager.reset_fndh_alarms()

    @command(dtype_out="DevVarLongStringArray")
    def ResetFndhAlarms(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Reset the FNDH alarms register.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetFndhAlarms")
        handler()
        return ([ResultCode.OK], ["ResetFndhAlarms command requested."])

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
        ) -> None:
            """Reset the FNDH warnings register."""
            self._component_manager.reset_fndh_warnings()

    @command(dtype_out="DevVarLongStringArray")
    def ResetFndhWarnings(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Reset the FNDH warnings register.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetFndhWarnings")
        handler()
        return ([ResultCode.OK], ["ResetFndhwarnings command requested."])

    class _InitializeSmartboxCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._InitializeSmartboxCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
            fem_current_trip_threshold: int,
        ):
            self._component_manager = component_manager
            self._fem_current_trip_threshold = fem_current_trip_threshold
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._InitializeSmartboxCommand, smartbox_id: int
        ) -> None:
            """
            Initialize a Smartbox.

            :param smartbox_id: id of the smartbox being addressed.
            """
            # We set the current trip thresholds here just in case
            # it hasn't been done yet
            self._component_manager.initialize_fem_current_trip_thresholds(
                smartbox_id, self._fem_current_trip_threshold
            )
            self._component_manager.initialize_smartbox(smartbox_id)

    @command(dtype_in=int, dtype_out="DevVarLongStringArray")
    def InitializeSmartbox(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Initialize a smartbox.

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a human-readable status message.
        """
        handler = self.get_command_object("InitializeSmartbox")
        handler(argin)
        return ([ResultCode.OK], ["InitializeSmartbox command requested."])

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
        ) -> None:
            """
            Set a Smartbox's port powers.

            :param smartbox_number: number of the smartbox to be addressed.
            :param port_powers: the desired power for each port.
                True means powered on, False means off,
                None means no desired change
            :param stay_on_when_offline: whether any ports being turned on
                should remain on if communication with the MCCS is lost.
            """
            self._component_manager.set_smartbox_port_powers(
                smartbox_number, port_powers, stay_on_when_offline
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetSmartboxPortPowers(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set a Smartbox's port powers.

        This command takes as input a JSON string that conforms to the
        following schema:

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetSmartboxPortPowers.json
           :language: json

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        handler = self.get_command_object("SetSmartboxPortPowers")
        handler(argin)
        return ([ResultCode.OK], ["SetSmartboxPortPowers command requested."])

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
        ) -> None:
            self._component_manager.set_smartbox_led_pattern(smartbox_number, pattern)

    class _SetSmartboxLowPassFiltersCommand(FastCommand):
        SCHEMA: Final = json.loads(
            importlib.resources.read_text(
                "ska_low_mccs_pasd.pasd_bus.schemas",
                "MccsPasdBus_SetSmartboxLowPassFilters.json",
            )
        )

        def __init__(
            self: MccsPasdBus._SetSmartboxLowPassFiltersCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager

            validator = JsonValidator("SetSmartboxLowPassFilters", self.SCHEMA, logger)
            super().__init__(logger, validator)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._SetSmartboxLowPassFiltersCommand,
            smartbox_number: int,
            cutoff: int,
            extra_sensors: bool = False,
        ) -> None:
            """
            Set a Smartbox's sensors' low pass filter constants.

            :param smartbox_number: number of the smartbox to be addressed.
            :param cutoff: frequency of LPF to set.
            :param extra_sensors: write the constant to the extra sensors' registers
                after the LED status register.
            """
            self._component_manager.set_smartbox_low_pass_filters(
                smartbox_number, cutoff, extra_sensors
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def SetSmartboxLowPassFilters(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set a Smartbox's sensors' low pass filter constants.

        The given cut-off frequency is stored as the LowPassFilterCutoff property in the
        tango database. It is automatically written to all sensor registers of the FNDH
        and smartboxes after MccsPasdBus is initialised and set ONLINE, and after any of
        them are powered on or reset later.

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetSmartboxLowPassFilters.json
           :language: json

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        if self._simulation_mode == SimulationMode.TRUE:
            return (
                [ResultCode.NOT_ALLOWED],
                ["SetSmartboxLowPassFilters is not supported by the simulator"],
            )
        handler = self.get_command_object("SetSmartboxLowPassFilters")
        handler(argin)
        self.LowPassFilterCutoff = json.loads(argin)["cutoff"]
        return ([ResultCode.OK], ["SetSmartboxLowPassFilters command requested."])

    @command(dtype_in="str", dtype_out="DevVarLongStringArray")
    def SetSmartboxLedPattern(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Set a Smartbox's service LED pattern.

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_SetSmartboxLedPattern.json
           :language: json

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        handler = self.get_command_object("SetSmartboxLedPattern")
        handler(argin)
        return ([ResultCode.OK], ["SetSmartboxLedPattern command requested."])

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
        ) -> None:
            """
            Reset a Smartbox's port breaker.

            :param smartbox_number: number of the smartbox to be addressed.
            :param port_number: the number of the port whose breaker is
                to be reset.
            """
            self._component_manager.reset_smartbox_port_breaker(
                smartbox_number, port_number
            )

    @command(dtype_in=str, dtype_out="DevVarLongStringArray")
    def ResetSmartboxPortBreaker(
        self: MccsPasdBus, argin: str
    ) -> DevVarLongStringArrayType:
        # pylint: disable=line-too-long
        """
        Reset a Smartbox's port's breaker.

        .. literalinclude:: /../../src/ska_low_mccs_pasd/pasd_bus/schemas/MccsPasdBus_ResetSmartboxPortBreaker.json
           :language: json

        :param argin: arguments encoded as a JSON string

        :return: A tuple containing a result code and a human-readable status message.
        """  # noqa: E501
        handler = self.get_command_object("ResetSmartboxPortBreaker")
        handler(argin)
        return ([ResultCode.OK], ["ResetSmartboxPortBreaker command requested."])

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
        ) -> None:
            """
            Reset a Smartbox's alarms register.

            :param smartbox_number: number of the smartbox to be addressed.
            """
            self._component_manager.reset_smartbox_alarms(smartbox_number)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def ResetSmartboxAlarms(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Reset a Smartbox alarms register.

        :param argin: Smartbox number

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetSmartboxAlarms")
        handler(argin)
        return ([ResultCode.OK], ["ResetSmartboxAlarms command requested."])

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
        ) -> None:
            """
            Reset a Smartbox's warnings register.

            :param smartbox_number: number of the smartbox to be addressed
            """
            self._component_manager.reset_smartbox_warnings(smartbox_number)

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
        handler(argin)
        return ([ResultCode.OK], ["ResetSmartboxWarnings command requested."])

    @command(dtype_out="DevVarLongStringArray")
    def ResetFnccStatus(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Reset the FNCC status register.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetFnccStatus")
        handler()
        return ([ResultCode.OK], ["ResetFnccStatus command requested."])

    class _ResetFnccStatusCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._ResetFnccStatusCommand,
            component_manager: PasdBusComponentManager,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._ResetFnccStatusCommand,
        ) -> None:
            """Reset the FNCC status register."""
            self._component_manager.reset_fncc_status()

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
            for controller in PasdData.CONTROLLERS_CONFIG.values():
                if controller.get("pasd_number") == pasd_device_number:
                    return [
                        controller["prefix"] + register["tango_attr_name"]
                        for register in controller["registers"].values()
                    ]
            if pasd_device_number in self._device.AvailableSmartboxes:
                return [
                    PasdData.CONTROLLERS_CONFIG["FNSC"]["prefix"]
                    + str(pasd_device_number)
                    + register["tango_attr_name"]
                    for register in PasdData.CONTROLLERS_CONFIG["FNSC"][
                        "registers"
                    ].values()
                ]
            return []

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
