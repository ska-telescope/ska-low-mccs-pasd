# -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
# This information is all copied from online. I have put it here to help with writing the device.
# The SmartBox:
#     This gets power from a FNDH and communicates with the FNDH communication gateway.
#     Each antenna is connected to the SMARTBOX via a coaxial cable.
#         - This provides DC power to the LNA (low noise amplifier)

#     The SmartBox converts the electrical RF signals into a Optical RF signals.
#     Each station has 24 smart boxes.
#     Each smartBox has 12 antenna ports.

#     - FEM package
#         Purpose:
#             -manage and supports the optical interconnection between individual FEM ("front end module": converts electrical to optical)
#             fibre optic pigtails and the 12 core field node breakout cable (FNBC)
#             -Dissapation of the electronic heat generated by the FEMs to minimise the obove-ambient operating temperature.
#         contents:
#             - 24 coax connectors
#             - 2 Fibre optic cables glands
#             - 2 indicators
#             - 2 DB-25 D-sub connectors
#             - 2 heat sinks
#             - 12 FEMs mounted directly onto 2 heat sinks.
#             - 2 heat sinks
#             - 1 custum sensor circuit board
#             - 1 Fuse circuit board
#             - Power distribution board
#             - 1 COTS Molex Power cable
#             - 1 2-pin polarised DC power connector
#             - 1 Single mode, dual-wavelength fibre-optic pigtail
#             - 2 MCX connectors

#     - Electronics Package:
#         Purpose:
#             -Converts the incoming 48Vdc power to 4.7Vdc to power the FEMs
#             -Monitor health of the system, Voltage, Current, Temperature
#             -Providing individual on/off control and overcurrent protection of FEMs.
#         contents:
#             - 2 DB-25 D-Sub connectors (interface to SMARTBOX FEM package)
#                 - 1 connector for power
#                 - 1 connector carries signals for the analog temperature sensors, the technician interface I/O and the SMART BOX address/location switches
#             - 1 F-type connector (for the PDoC RG6 Quad shield coaxial cable from the NDH EP)
#             - 1 MCU circuit board.
#             - 1 COTS in-line D-sub emmision filters.
#             - 1 PDoC circuit board.
#             - 1 PSU Circuit board.

# MCCSSmartBox:
#     A Tango device that monitors and controls a single PaSD smartbox. It communicates with its smartbox by proxying through a PaSD bus LMC Tango device.
#     This MccsSmartBox device is the only device that can speak Modbus.

#     - Monitoring
#         - IP address.
#         - 12x LNA power status
#         - Voltages
#         - Current
#         - Temperatures (5x Thermistors)
#         - Get Antenna IP.

#     - Commands:
#         - PowerOnPort(int)
#         - PowerOffPort(int)
#         - CircuitBoardTemperature
#         - FEMHeatSinkTemperature
#         - ThermistorReadings
#         - GetLNAPorts
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.

# pylint: disable-next


from __future__ import annotations

import threading
from typing import Any, Optional

import tango
from ska_control_model import (
    CommunicationStatus,
    HealthState,
    PowerState,
    ResultCode,
)
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import DeviceInitCommand, SubmittedSlowCommand
from tango.server import attribute, command

from .smart_box_component_manager import SmartBoxComponentManager
from .smartbox_health_model import SmartBoxHealthModel

__all__ = ["MccsSmartBox", "main"]

# TODO: do we want dangling globals

"""The number of Antenna attached (some bays may be empty)"""


class MccsSmartBox(SKABaseDevice):
    """An implementation of the SmartBox device for MCCS."""

    # All 12 ports may not be connected to a antenna at any point
    # 24 smartboxes x 12 ports.
    PORT_COUNT = 12

    # these are the attributes avaliable.
    # Most are commented out to be implemented at a later date.
    # This is simply a dictionary that we update

    _ATTRIBUTE_MAP = {
        # "mb_address": "ModbusAddress",
        # "mb_register_revision": "ModbusRegisterRevision",
        # "pcb_revision": "PCBRevision",
        # "register_map": "RegisterMap", #TODO: does TANGO care?
        "sensor_temps": "SensorTemps",
        # "cpuid": "CPUId",
        # "chipid": "ChipId",
        # "firmware_version": "FirmwareVersion",
        # "uptime": "Uptime",
        # "station_value": "StationValue",
        "incoming_voltage": "IncomingVoltage",
        "psu_voltage": "PowerSupplyVoltage",
        "psu_temp": "PowerSupplyTemp",
        "pcb_temp": "PCBTemp",
        # "outside_temp": "OutsideTemp",
        # "statuscode": "StatusCode",
        # "status": "Status",
        # "service_led": "ServiceLED",
        # "indicator_code": "IndicatorCode",
        # "indicator_state": "IndicatorState",
        # "readtime": "ReadTime", # last poll time in UTC
        # "pdoc_number": "PDoCNumber",
        # "thresholds": "Threshold",
        # "portconfig": "PortConfig",
        # #FEM values
        "fem_port_power_state": "FEMPortPowerStates",  # from the PortStatus
        # "fem_port_number":"FEMPortNumber",
        # "fem_modbus_address": "FEMModbusAddress",
        # "fem_current_timestamp": "FEMCurrentTimeStamp",
        # "fem_current_raw": "FEMCurrentRaw",
        "fem_current": "FEMCurrents",  # from teh PortStatus
        # "fem_status_timestamp": "FEMStatusTimestamps", #from teh PortStatus
    }

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

        # This lists the ports with antenna attached [0,1,0,1,1,1,1,1,0,1,1,1]
        # Do we need to check a antenna is attached before executing a command?
        # Or do we just send the command and let it hit a wall (empty port).
        self._antenna_present: list[bool] = []

        # Initialise with unknown.
        self._antenna_power_states = [PowerState.UNKNOWN] * self.PORT_COUNT
        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_model: SmartBoxHealthModel
        self._hardware_attributes: dict[str, Any] = {}

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

    def _init_state_model(self: MccsSmartBox) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN  # InitCommand.do() does this too late.
        self._health_model = SmartBoxHealthModel(self._component_state_changed_callback)
        self.set_change_event("healthState", True, False)

    # ----------
    # Properties
    # ----------

    # pylint: disable-next=too-few-public-methods
    class InitCommand(DeviceInitCommand):
        """Initialisation command class for this base device."""

        # pylint: disable=protected-access
        def do(
            self: MccsSmartBox.InitCommand, *args: Any, **kwargs: Any
        ) -> tuple[ResultCode, str]:
            """
            Initialise the attributes of this MccsSmartBox.

            :param args: additional positional arguments; unused here
            :param kwargs: additional keyword arguments; unused here

            :return: a resultcode, message tuple
            """
            # self._device.set_change_event("antennasTripped", True, False)
            self._device.set_change_event("antennasTripped", True)
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
            self._component_state_changed,
            "low-mccs-pasd/pasdbus/001",
        )

    def init_command_objects(self: MccsSmartBox) -> None:
        """Initialise the command handlers for this device."""
        super().init_command_objects()

        for (command_name, method_name) in [
            ("PowerOnPort", "turn_on_port"),
            ("PowerOffPort", "turn_off_port"),
            ("GetAntennaInfo", "get_antenna_info"),
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
    def PowerOnPort(  # pylint: disable=invalid-name
        self: MccsSmartBox, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up a Antenna's LNA.

        :param argin: the logical id of the Antenna (LNA) to power up

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        self.logger.info("called the turn on")
        handler = self.get_command_object("PowerOnPort")
        self.logger.info("called the turn on")
        result_code, message = handler(argin)
        return ([result_code], [message])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def PowerOffPort(  # pylint: disable=invalid-name
        self: MccsSmartBox, argin: int
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power down a Antenna's LNA.

        :param argin: the logical id of the TPM to power down

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerOffPort")
        result_code, message = handler(argin)
        return ([result_code], [message])

    @command(dtype_out="DevVarLongStringArray")
    def PowerUpAntennas(  # pylint: disable=invalid-name
        self: MccsSmartBox,
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power up all Antenna LNA's.

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerUpAntennas")
        result_code, message = handler()
        return ([result_code], [message])

    @command(dtype_out="DevVarLongStringArray")
    def PowerDownAntennas(  # pylint: disable=invalid-name
        self: MccsSmartBox,
    ) -> tuple[list[ResultCode], list[Optional[str]]]:
        """
        Power down all Antanna LNA's.

        :return: A tuple containing a return code and a string message
            indicating status. The message is for information purposes
            only.
        """
        handler = self.get_command_object("PowerDownAntennas")
        result_code, message = handler()
        return ([result_code], [message])

    @command(dtype_in="DevULong", dtype_out="DevVarLongStringArray")
    def GetAntennaInfo(self: MccsSmartBox, argin: int) -> tuple[list[Any], list[Any]]:
        """
        Return information about relationship of an antenna to other PaSD components.

        :param argin: antenna to get info from

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        handler = self.get_command_object("GetAntennaInfo")
        result_code, unique_id = handler(argin)
        return ([result_code], [unique_id])

    # ----------
    # Attributes
    # ----------

    # TODO: Copy over all SmartBox related attributes from the pasdBus
    @attribute(
        dtype=(bool,),
        max_dim_x=256,
        label="antennas Tripped",
    )
    def antennasTripped(self: MccsSmartBox) -> list[bool]:
        """
        Return whether each antenna has had its breaker tripped.

        :return: a list of booleans indicating whether each antenna has
            had its breaker tripped
        """
        # TODO: this is just proof of concept:
        # Havnt given thought if we actually want this attribute in
        # this device.
        return self.component_manager.antennas_tripped

    # ----------
    # Callbacks
    # ----------
    def _communication_state_changed(
        self: MccsSmartBox, communication_state: CommunicationStatus
    ) -> None:
        self.logger.debug(
            "Device received notification from component manager that communication "
            "with the component is %s.",
            communication_state.name,
        )
        if communication_state != CommunicationStatus.ESTABLISHED:
            self._update_port_power_states([PowerState.UNKNOWN] * self._port_count)

        super()._communication_state_changed(communication_state)

    def _component_state_changed(
        self: MccsSmartBox,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        **kwargs: Any,
    ) -> None:
        """
        This will be called from the component manager with
        long running command reponses from the pasd_device_proxy
        key must be:
        "antenna_present" # this will be notified on a database reload.
        """

        super()._component_state_changed(fault=fault, power=power)
        self.logger.info("ijssssn")
        for key, value in kwargs.items():
            special_update_method = getattr(self, f"_update_{key}", None)
            if special_update_method is None:
                tango_attribute_name = self._ATTRIBUTE_MAP[key]
                self._hardware_attributes[tango_attribute_name] = value
                self.push_change_event(tango_attribute_name, value)
            else:
                special_update_method(value)

        antenna_power_state = None
        if power == PowerState.OFF:
            antenna_power_state = PowerState.NO_SUPPLY
        elif power == PowerState.UNKNOWN:
            antenna_power_state = PowerState.UNKNOWN
        if antenna_power_state is not None:
            self._update_antanna_power_states([antenna_power_state] * self._port_count)

    def _update_board_current(self: MccsSmartBox, board_current: float) -> None:
        if board_current is None:
            self._hardware_attributes["boardCurrent"] = None
            self.push_change_event("boardCurrent", [])
        else:
            self._hardware_attributes["boardCurrent"] = [board_current]
            self.push_change_event("boardCurrent", [board_current])

    def _update_antennas_tripped(
        self: MccsSmartBox, antennas_tripped: Optional[list[bool]]
    ) -> None:
        if antennas_tripped is None:
            antennas_tripped = []
        # if self._antennas_tripped == antennas_tripped:
        #     return
        # self._antennas_tripped = antennas_tripped
        self.push_change_event("antennasTripped", antennas_tripped)

    def _update_antenna_on_off(
        self: MccsSmartBox, antenna_on_off: Optional[list[bool]]
    ) -> None:
        if antenna_on_off is None:
            power_states = [PowerState.UNKNOWN] * self._port_count
        else:
            power_states = [
                PowerState.ON if is_on else PowerState.OFF for is_on in antenna_on_off
            ]
        self._update_port_power_states(power_states)

    def _update_port_power_states(
        self: MccsSmartBox, antenna_power_states: list[PowerState]
    ) -> None:
        for index, power_state in enumerate(antenna_power_states):
            if self._antenna_power_states[index] != power_state:
                self._antenna_power_states[index] = power_state
                self.push_change_event(f"antenna{index+1}PowerState", power_state)

    def _component_state_changed_callback(
        self: MccsSmartBox, state_change: dict[str, Any]
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param state_change: the state change parameter.
        """
        self.logger.info("ijn")
        action_map = {
            PowerState.OFF: "component_off",
            PowerState.STANDBY: "component_standby",
            PowerState.ON: "component_on",
            PowerState.UNKNOWN: "component_unknown",
        }

        with self._power_state_lock:
            if "power_state" in state_change.keys():
                power_state = state_change.get("power_state")
                self.component_manager.power_state = power_state
                if power_state:
                    self.op_state_model.perform_action(action_map[power_state])

        if "fault" in state_change.keys():
            is_fault = state_change.get("fault")
            if is_fault:
                self.op_state_model.perform_action("component_fault")
                self._health_model.component_fault(True)
            else:
                self.op_state_model.perform_action(
                    action_map[self.component_manager.power_state]
                )
                self._health_model.component_fault(False)

        if "health_state" in state_change.keys():
            health = state_change["health_state"]
            if self._health_state != health:
                self._health_state = health
                self.push_change_event("healthState", health)


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
