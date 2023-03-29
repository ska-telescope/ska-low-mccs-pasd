# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS PaSD bus device."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Optional

import tango
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
    SimulationMode,
)
from ska_low_mccs_common import release
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import DeviceInitCommand, FastCommand
from tango.server import attribute, command

from .pasd_bus_component_manager import PasdBusComponentManager
from .pasd_bus_health_model import PasdBusHealthModel

__all__ = ["MccsPasdBus", "main"]


NUMBER_OF_ANTENNAS_PER_STATION = 256
NUMBER_OF_SMARTBOXES_PER_STATION = 24
NUMBER_OF_FNDH_PORTS = 28

DevVarLongStringArrayType = tuple[list[ResultCode], list[Optional[str]]]


class MccsPasdBus(SKABaseDevice):  # pylint: disable=too-many-public-methods
    """An implementation of a PaSD bus Tango device for MCCS."""

    # ----------
    # Properties
    # ----------
    Host = tango.server.device_property(dtype=str)
    Port = tango.server.device_property(dtype=int)
    Timeout = tango.server.device_property(dtype=float)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_model: PasdBusHealthModel

    # ---------------
    # Initialisation
    # ---------------
    def init_device(self: MccsPasdBus) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        self._build_state: str = release.get_release_info()
        self._version_id: str = release.version

        self._max_workers = 1
        self._power_state_lock = threading.RLock()
        super().init_device()

        message = (
            "Initialised MccsPasdBus device with properties:\n"
            f"\tHost: {self.Host}\n"
            f"\tPort: {self.Port}\n"
            f"\tTimeout: {self.Timeout}\n"
        )
        self.logger.info(message)

    def _init_state_model(self: MccsPasdBus) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = PasdBusHealthModel(self._health_changed_callback)
        self.set_change_event("healthState", True, False)

    def create_component_manager(  # type: ignore[override]
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
            self._max_workers,
            self._communication_state_changed_callback,
            self._component_state_changed_callback,
        )

    def init_command_objects(self: MccsPasdBus) -> None:
        """Initialise the command handlers for commands supported by this device."""
        super().init_command_objects()

        for (command_name, method_name) in [
            ("ReloadDatabase", "reload_database"),
            ("GetFndhInfo", "get_fndh_info"),
            ("GetSmartboxInfo", "get_smartbox_info"),
            ("TurnSmartboxOn", "turn_smartbox_on"),
            ("TurnSmartboxOff", "turn_smartbox_off"),
            ("GetAntennaInfo", "get_antenna_info"),
            ("ResetAntennaBreaker", "reset_antenna_breaker"),
            ("TurnAntennaOn", "turn_antenna_on"),
            ("TurnAntennaOff", "turn_antenna_off"),
        ]:
            self.register_command_object(
                command_name,
                MccsPasdBus._SubmittedFastCommand(
                    getattr(self.component_manager, method_name),
                    logger=self.logger,
                ),
            )

        for (command_name, command_class, is_on) in [
            ("TurnFndhServiceLedOn", MccsPasdBus._TurnFndhServiceLedOnOffCommand, True),
            (
                "TurnFndhServiceLedOff",
                MccsPasdBus._TurnFndhServiceLedOnOffCommand,
                False,
            ),
            (
                "TurnSmartboxServiceLedOn",
                MccsPasdBus._TurnSmartboxServiceLedOnOffCommand,
                True,
            ),
            (
                "TurnSmartboxServiceLedOff",
                MccsPasdBus._TurnSmartboxServiceLedOnOffCommand,
                False,
            ),
        ]:
            self.register_command_object(
                command_name,
                command_class(self.component_manager, is_on, logger=self.logger),
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
    def _communication_state_changed_callback(
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

    def _component_state_changed_callback(
        self: MccsPasdBus,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        fndh_status: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param fndh_status: the status of the FNDH
        :param kwargs: additional keyword arguments defining component
            state.
        """
        super()._component_state_changed(fault=fault, power=power)
        self._health_model.update_state(
            fault=fault, power=power, fndh_status=fndh_status
        )

    def _health_changed_callback(self, health: HealthState) -> None:
        if self._health_state != health:
            self._health_state = health
            self.push_change_event("healthState", health)

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

    @attribute(dtype=("float",), max_dim_x=2, label="fndhPsu48vVoltages")
    def fndhPsu48vVoltages(self: MccsPasdBus) -> list[float]:
        """
        Return the output voltages on the two 48V DC power supplies, in voltes.

        :return: the output voltages on the two 48V DC power supplies,
             in volts.
        """
        return self.component_manager.fndh_psu48v_voltages

    @attribute(dtype=float, label="fndhPsu5vVoltage")
    def fndhPsu5vVoltage(self: MccsPasdBus) -> float:
        """
        Return the output voltage on the 5V power supply, in volts.

        :return: the output voltage on the 5V power supply, in volts.
        """
        return self.component_manager.fndh_psu5v_voltage

    @attribute(dtype=float, label="fndhPsu48vCurrent")
    def fndhPsu48vCurrent(self: MccsPasdBus) -> float:
        """
        Return the total current on the 48V DC bus, in amperes.

        :return: the total current on the 48V DC bus, in amperes.
        """
        return self.component_manager.fndh_psu48v_current

    @attribute(dtype=float, label="fndhPsu48vTemperature")
    def fndhPsu48vTemperature(self: MccsPasdBus) -> float:
        """
        Return the common temperature for both 48V power supplies, in celcius.

        :return: the common temperature for both 48V power supplies, in celcius.
        """
        return self.component_manager.fndh_psu48v_temperature

    @attribute(dtype=float, label="fndhPsu5vTemperature")
    def fndhPsu5vTemperature(self: MccsPasdBus) -> float:
        """
        Return the temperature of the 5V power supply, in celcius.

        :return: the temperature of the 5V power supply, in celcius.
        """
        return self.component_manager.fndh_psu5v_temperature

    @attribute(dtype=float, label="fndhPcbTemperature")
    def fndhPcbTemperature(self: MccsPasdBus) -> float:
        """
        Return the temperature of the FNDH's PCB, in celcius.

        :return: the temperature of the FNDH's PCB, in celcius.
        """
        return self.component_manager.fndh_pcb_temperature

    @attribute(dtype=float, label="fndhOutsideTemperature")
    def fndhOutsideTemperature(self: MccsPasdBus) -> float:
        """
        Return the temperature outside the FNDH, in celcius.

        :return: the temperature outside the FNDH, in celcius.
        """
        return self.component_manager.fndh_pcb_temperature

    @attribute(dtype=str, label="fndhStatus")
    def fndhStatus(self: MccsPasdBus) -> str:
        """
        Return the status of the FNDH.

        :return: the status of the FNDH
        """
        return self.component_manager.fndh_status

    @attribute(dtype=bool, label="fndhServiceLedOn")
    def fndhServiceLedOn(self: MccsPasdBus) -> bool:
        """
        Whether the FNDH's blue service indicator LED is on.

        :return: whether the FNDH's blue service indicator LED is on.
        """
        return self.component_manager.fndh_service_led_on

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_FNDH_PORTS,
        label="fndhPortsPowerSensed",
    )
    def fndhPortsPowerSensed(self: MccsPasdBus) -> list[bool]:
        """
        Return the actual power state of each FNDH port.

        :return: the actual power state of each FNDH port.
        """
        return self.component_manager.fndh_ports_power_sensed

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_FNDH_PORTS,
        label="fndhPortsConnected",
    )
    def fndhPortsConnected(self: MccsPasdBus) -> list[bool]:
        """
        Return whether there is a smartbox connected to each FNDH port.

        :return: whether there is a smartbox connected to each FNDH
            port.
        """
        return self.component_manager.fndh_ports_connected

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_FNDH_PORTS,
        label="fndhPortsForced",
    )
    def fndhPortsForced(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each FNDH port has had its power locally forced.

        :return: whether each FNDH port has had its power locally
            forced.
        """
        return [
            forcing is not None for forcing in self.component_manager.fndh_port_forcings
        ]

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_FNDH_PORTS,
        label="fndhPortsDesiredPowerOnline",
    )
    def fndhPortsDesiredPowerOnline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each FNDH port is desired to be powered when controlled by MCCS.

        :return: whether each FNDH port is desired to be powered when
            controlled by MCCS
        """
        return self.component_manager.fndh_ports_desired_power_online

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_FNDH_PORTS,
        label="fndhPortsDesiredPowerOffline",
    )
    def fndhPortsDesiredPowerOffline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each FNDH port should be powered when MCCS control has been lost.

        :return: whether each FNDH port is desired to be powered when
            MCCS control has been lost
        """
        return self.component_manager.fndh_ports_desired_power_offline

    @attribute(
        dtype=("float",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxInputVoltages",
    )
    def smartboxInputVoltages(self: MccsPasdBus) -> list[float]:
        """
        Return each smartbox's power input voltage, in volts.

        :return: each smartbox's power input voltage, in volts.
        """
        return self.component_manager.smartbox_input_voltages

    @attribute(
        dtype=("float",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxPowerSupplyOutputVoltages",
    )
    def smartboxPowerSupplyOutputVoltages(self: MccsPasdBus) -> list[float]:
        """
        Return each smartbox's power supply output voltage, in volts.

        :return: each smartbox's power supply output voltage, in volts.
        """
        return self.component_manager.smartbox_power_supply_output_voltages

    @attribute(
        dtype=("DevString",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxStatuses",
    )
    def smartboxStatuses(self: MccsPasdBus) -> list[str]:
        """
        Return each smartbox's status.

        :return: each smartbox's status.
        """
        return self.component_manager.smartbox_statuses

    @attribute(
        dtype=("float",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxPowerSupplyTemperatures",
    )
    def smartboxPowerSupplyTemperatures(self: MccsPasdBus) -> list[float]:
        """
        Return each smartbox's power supply temperature.

        :return: each smartbox's power supply temperature.
        """
        return self.component_manager.smartbox_power_supply_temperatures

    @attribute(
        dtype=("float",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxOutsideTemperatures",
    )
    def smartboxOutsideTemperatures(self: MccsPasdBus) -> list[float]:
        """
        Return each smartbox's outside temperature.

        :return: each smartbox's outside temperature.
        """
        return self.component_manager.smartbox_outside_temperatures

    @attribute(
        dtype=("float",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxPcbTemperatures",
    )
    def smartboxPcbTemperatures(self: MccsPasdBus) -> list[float]:
        """
        Return each smartbox's PCB temperature.

        :return: each smartbox's PCB temperature.
        """
        return self.component_manager.smartbox_pcb_temperatures

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxServiceLedsOn",
    )
    def smartboxServiceLedsOn(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each smartbox's blue service LED is on.

        :return: a list of booleans indicating whether each smartbox's
            blue service LED is on.
        """
        return self.component_manager.smartbox_service_leds_on

    @attribute(
        dtype=("int",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxFndhPorts",
    )
    def smartboxFndhPorts(self: MccsPasdBus) -> list[int]:
        """
        Return each smartbox's FNDH port.

        :return: each smartbox's FNDH port.
        """
        return self.component_manager.smartbox_fndh_ports

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxesDesiredPowerOnline",
    )
    def smartboxesDesiredPowerOnline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each smartbox should be on when the PaSD is under MCCS control.

        :return: whether each smartbox should be on when the PaSD is
            under MCCS control.
        """
        return self.component_manager.smartboxes_desired_power_online

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_SMARTBOXES_PER_STATION,
        label="smartboxesDesiredPowerOffline",
    )
    def smartboxesDesiredPowerOffline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each smartbox should be on when MCCS control of the PaSD is lost.

        :return: whether each smartbox should be on when MCCS control of
            the PaSD is lost.
        """
        return self.component_manager.smartboxes_desired_power_offline

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennasOnline",
    )
    def antennasOnline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each antenna is online.

        :return: a list of booleans indicating whether each antenna is
            online
        """
        return self.component_manager.antennas_online

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennasForced",
    )
    def antennasForced(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each antenna is forced.

        :return: a list of booleans indicating whether each antenna is
            forces
        """
        return [
            forcing is not None for forcing in self.component_manager.antenna_forcings
        ]

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennasTripped",
    )
    def antennasTripped(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each antenna has had its breaker tripped.

        :return: a list of booleans indicating whether each antenna has
            had its breaker tripped
        """
        return self.component_manager.antennas_tripped

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennaPowerStates",
    )
    def antennasPowerSensed(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each antenna is currently powered on.

        :return: a list of booleans indicating whether each antenna is
            currently powered on
        """
        return self.component_manager.antennas_power_sensed

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennasDesiredPowerOnline",
    )
    def antennasDesiredPowerOnline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each antenna is desired to be on when it is online.

        :return: a list of booleans indicating whether each antenna is
            desired to be on when it is online.
        """
        return self.component_manager.antennas_desired_power_online

    @attribute(
        dtype=("DevBoolean",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennasDesiredPowerOffline",
    )
    def antennasDesiredPowerOffline(self: MccsPasdBus) -> list[bool]:
        """
        Return whether each antenna is desired to be on when it is offline.

        :return: a list of booleans indicating whether each antenna is
            desired to be on when it is offline.
        """
        return self.component_manager.antennas_desired_power_offline

    @attribute(
        dtype=("float",),
        max_dim_x=NUMBER_OF_ANTENNAS_PER_STATION,
        label="antennaCurrents",
    )
    def antennaCurrents(self: MccsPasdBus) -> list[float]:
        """
        Return the current at each antenna's power port, in amps.

        :return: the current at each antenna's power port, in amps
        """
        return self.component_manager.antenna_currents

    # ----------
    # Commands
    # ----------
    class _SubmittedFastCommand(FastCommand):
        """
        Boilerplate for a FastCommand.

        This is a temporary class,
        just until we can turn these commands into proper SlowCommands.
        """

        def __init__(
            self: MccsPasdBus._SubmittedFastCommand,
            component_manager_method: Callable,
            logger: logging.Logger,
        ) -> None:
            """
            Initialise a new instance.

            :param component_manager_method: the method to invoke.
            :param logger: a logger for this command to use.
            """
            self._component_manager_method = component_manager_method
            super().__init__(logger)

        def do(
            self: MccsPasdBus._SubmittedFastCommand, *args: Any, **kwargs: Any
        ) -> Any:
            """
            Execute the user-specified code for this command.

            :param args: positional arguments to this do-method.
            :param kwargs: keyword arguments to this do-method.

            :return: result of executing the command.
            """
            return self._component_manager_method(*args, **kwargs)

    @command(dtype_out="DevVarLongStringArray")
    def ReloadDatabase(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Reload PaSD configuration from the configuration database.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ReloadDatabase")
        success = handler()
        if success:
            return ([ResultCode.OK], ["ReloadDatabase succeeded"])
        return ([ResultCode.FAILED], ["ReloadDatabase failed"])

    @command(dtype_out="str")
    def GetFndhInfo(self: MccsPasdBus) -> str:
        """
        Return information about the FNDH.

        :return: A dictionary of information about the FNDH.
        """
        handler = self.get_command_object("GetFndhInfo")
        fndh_info = handler()
        return json.dumps(fndh_info)

    class _TurnFndhServiceLedOnOffCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._TurnFndhServiceLedOnOffCommand,
            component_manager: PasdBusComponentManager,
            is_on: bool,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            self._is_on = is_on
            super().__init__(logger)

        # pylint: disable-next=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._TurnFndhServiceLedOnOffCommand,
        ) -> Optional[bool]:
            """
            Turn the FNDH service led on/off.

            :return: whether successful, or None if there was nothing to
                do.
            """
            return self._component_manager.set_fndh_service_led_on(self._is_on)

    @command(dtype_out="DevVarLongStringArray")
    def TurnFndhServiceLedOn(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Turn on the FNDH's blue service LED.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnFndhServiceLedOn")
        success = handler()
        if success:
            return ([ResultCode.OK], ["TurnFndhServiceLedOn succeeded"])
        if success is None:
            return ([ResultCode.OK], ["TurnFndhServiceLedOn succeeded: nothing to do"])
        return ([ResultCode.FAILED], ["TurnFndhServiceLedOn failed"])

    @command(dtype_out="DevVarLongStringArray")
    def TurnFndhServiceLedOff(self: MccsPasdBus) -> DevVarLongStringArrayType:
        """
        Turn off the FNDH's blue service LED.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnFndhServiceLedOff")
        success = handler()
        if success:
            return ([ResultCode.OK], ["TurnFndhServiceLedOff succeeded"])
        if success is None:
            return ([ResultCode.OK], ["TurnFndhServiceLedOff succeeded: nothing to do"])
        return ([ResultCode.FAILED], ["TurnFndhServiceLedOff failed"])

    @command(dtype_in="DevULong", dtype_out=str)
    def GetSmartboxInfo(self: MccsPasdBus, argin: int) -> str:
        """
        Return information about a smartbox.

        :param argin: smartbox to get info from

        :return: A dictionary of information about the smartbox.
        """
        handler = self.get_command_object("GetSmartboxInfo")
        smartbox_info = handler(argin)
        return json.dumps(smartbox_info)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnSmartboxOn(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Turn on a smartbox.

        :param argin: smartbox to turn on

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnSmartboxOn")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnSmartboxOn {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnSmartboxOn {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnSmartboxOn {argin} failed"])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnSmartboxOff(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Turn off a smartbox.

        :param argin: smartbox to turn off

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnSmartboxOff")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnSmartboxOff {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnSmartboxOff {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnSmartboxOff {argin} failed"])

    class _TurnSmartboxServiceLedOnOffCommand(FastCommand):
        def __init__(
            self: MccsPasdBus._TurnSmartboxServiceLedOnOffCommand,
            component_manager: PasdBusComponentManager,
            is_on: bool,
            logger: logging.Logger,
        ):
            self._component_manager = component_manager
            self._is_on = is_on
            super().__init__(logger)

        # pylint: disable=arguments-differ
        def do(  # type: ignore[override]
            self: MccsPasdBus._TurnSmartboxServiceLedOnOffCommand,
            smartbox_id: int,
        ) -> Optional[bool]:
            return self._component_manager.set_smartbox_service_led_on(
                smartbox_id, self._is_on
            )

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnSmartboxServiceLedOn(
        self: MccsPasdBus, argin: int
    ) -> DevVarLongStringArrayType:
        """
        Turn on a smartbox's blue service LED.

        :param argin: smartbox service led to turn on

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnSmartboxServiceLedOn")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnSmartboxServiceLedOn {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnSmartboxServiceLedOn {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnSmartboxServiceLedOn {argin} failed"])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnSmartboxServiceLedOff(
        self: MccsPasdBus, argin: int
    ) -> DevVarLongStringArrayType:
        """
        Turn off a smartbox's blue service LED.

        :param argin: smartbox service led to turn off

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnSmartboxServiceLedOff")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnSmartboxServiceLedOff {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnSmartboxServiceLedOff {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnSmartboxServiceLedOff {argin} failed"])

    @command(dtype_in="DevULong", dtype_out=str)
    def GetAntennaInfo(self: MccsPasdBus, argin: int) -> str:
        """
        Return information about relationship of an antenna to other PaSD components.

        :param argin: antenna to get info from

        :return: A dictionary of information about the antenna.
        """
        handler = self.get_command_object("GetAntennaInfo")
        antenna_info = handler(argin)
        return json.dumps(antenna_info)

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def ResetAntennaBreaker(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Reset a tripped antenna breaker.

        :param argin: antenna breaker to reset

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("ResetAntennaBreaker")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"ResetAntennaBreaker {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"ResetAntennaBreaker {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"ResetAntennaBreaker {argin} failed"])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnAntennaOn(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Turn on an antenna.

        :param argin: antenna to turn on

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnAntennaOn")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnAntennaOn {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnAntennaOn {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnAntennaOn {argin} failed"])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def TurnAntennaOff(self: MccsPasdBus, argin: int) -> DevVarLongStringArrayType:
        """
        Turn off an antenna.

        :param argin: antenna to turn off

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("TurnAntennaOff")
        success = handler(argin)
        if success:
            return ([ResultCode.OK], [f"TurnAntennaOff {argin} succeeded"])
        if success is None:
            return (
                [ResultCode.OK],
                [f"TurnAntennaOff {argin} succeeded: nothing to do"],
            )
        return ([ResultCode.FAILED], [f"TurnAntennaOff {argin} failed"])


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
