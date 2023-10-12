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
from typing import Any, Final, Optional

from ska_control_model import CommunicationStatus, HealthState, PowerState, ResultCode
from ska_tango_base.base import SKABaseDevice
from ska_tango_base.commands import DeviceInitCommand, SubmittedSlowCommand
from tango.server import attribute, command, device_property

from .smart_box_component_manager import SmartBoxComponentManager
from .smartbox_health_model import SmartBoxHealthModel

__all__ = ["MccsSmartBox", "main"]


class MccsSmartBox(SKABaseDevice):
    """An implementation of the SmartBox device for MCCS."""

    PORT_COUNT: Final = 12

    # -----------------
    # Device Properties
    # -----------------
    FndhPort = device_property(dtype=int, mandatory=True)
    PasdFQDN = device_property(dtype=(str), mandatory=True)
    SmartBoxNumber = device_property(dtype=int, mandatory=True)

    # --------------------
    # Forwarded attributes
    # --------------------
    modbusRegisterMapRevisionNumber = attribute(
        name="modbusRegisterMapRevisionNumber",
        label="Modbus register map revision number",
        forwarded=True,
    )
    pcbRevisionNumber = attribute(
        name="pcbRevisionNumber", label="PCB revision number", forwarded=True
    )
    cpuId = attribute(name="cpuId", label="CPU ID", forwarded=True)
    chipId = attribute(name="chipId", label="Chip ID", forwarded=True)
    firmwareVersion = attribute(
        name="firmwareVersion", label="Firmware version", forwarded=True
    )
    uptime = attribute(name="uptime", label="Uptime", forwarded=True)
    smartboxStatus = attribute(
        name="smartboxStatus", label="smartbox status", forwarded=True
    )
    sysAddress = attribute(name="sysAddress", label="System address", forwarded=True)
    ledPattern = attribute(name="ledPattern", label="LED pattern", forwarded=True)
    inputVoltage = attribute(name="inputVoltage", label="Input voltage", forwarded=True)
    powerSupplyOutputVoltage = attribute(
        name="powerSupplyOutputVoltage",
        label="Power supply output voltage",
        forwarded=True,
    )
    powerSupplyTemperature = attribute(
        name="powerSupplyTemperature", label="Power supply temperature", forwarded=True
    )
    pcbTemperature = attribute(
        name="pcbTemperature", label="PCB temperature", forwarded=True
    )
    femAmbientTemperature = attribute(
        name="femAmbientTemperature", label="FEM ambient temperature", forwarded=True
    )
    femCaseTemperatures = attribute(
        name="femCaseTemperatures", label="FEM case temperatures", forwarded=True
    )
    femHeatsinkTemperatures = attribute(
        name="femHeatsinkTemperatures",
        label="FEM heatsink temperatures",
        forwarded=True,
    )
    # TODO: https://gitlab.com/tango-controls/cppTango/-/issues/1018
    # Cannot forward this attribute right now:
    # portForcings = attribute(name="portForcings", label="Port forcings", forwarded=True)
    portBreakersTripped = attribute(
        name="portBreakersTripped", label="Port breakers tripped", forwarded=True
    )
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
        name="portsPowerSensed", label="Ports power sensed", forwarded=True
    )
    portsCurrentDraw = attribute(
        name="portsCurrentDraw", label="Ports current draw", forwarded=True
    )
    inputVoltageThresholds = attribute(
        name="inputVoltageThresholds", label="Input voltage thresholds", forwarded=True
    )
    powerSupplyOutputVoltageThresholds = attribute(
        name="powerSupplyOutputVoltageThresholds",
        label="Power supply output voltage thresholds",
        forwarded=True,
    )
    powerSupplyTemperatureThresholds = attribute(
        name="powerSupplyTemperatureThresholds",
        label="Power supply temperature thresholds",
        forwarded=True,
    )
    pcbTemperatureThresholds = attribute(
        name="pcbTemperatureThresholds",
        label="PCB temperature thresholds",
        forwarded=True,
    )
    femAmbientTemperatureThresholds = attribute(
        name="femAmbientTemperatureThresholds",
        label="FEM ambient temperature thresholds",
        forwarded=True,
    )
    femCaseTemperature1Thresholds = attribute(
        name="femCaseTemperature1Thresholds",
        label="FEM case temperature 1 thresholds",
        forwarded=True,
    )
    femCaseTemperature2Thresholds = attribute(
        name="femCaseTemperature2Thresholds",
        label="FEM case temperature 2 thresholds",
        forwarded=True,
    )
    femHeatsinkTemperature1Thresholds = attribute(
        name="femHeatsinkTemperature1Thresholds",
        label="FEM heatsink temperature 1 thresholds",
        forwarded=True,
    )
    femHeatsinkTemperature2Thresholds = attribute(
        name="femHeatsinkTemperature2Thresholds",
        label="FEM heatsink temperature 2 thresholds",
        forwarded=True,
    )
    fem1CurrentTripThreshold = attribute(
        name="fem1CurrentTripThreshold",
        label="FEM 1 current trip threshold",
        forwarded=True,
    )
    fem2CurrentTripThreshold = attribute(
        name="fem2CurrentTripThreshold",
        label="FEM 2 current trip threshold",
        forwarded=True,
    )
    fem3CurrentTripThreshold = attribute(
        name="fem3CurrentTripThreshold",
        label="FEM 3 current trip threshold",
        forwarded=True,
    )
    fem4CurrentTripThreshold = attribute(
        name="fem4CurrentTripThreshold",
        label="FEM 4 current trip threshold",
        forwarded=True,
    )
    fem5CurrentTripThreshold = attribute(
        name="fem5CurrentTripThreshold",
        label="FEM 5 current trip threshold",
        forwarded=True,
    )
    fem6CurrentTripThreshold = attribute(
        name="fem6CurrentTripThreshold",
        label="FEM 6 current trip threshold",
        forwarded=True,
    )
    fem7CurrentTripThreshold = attribute(
        name="fem7CurrentTripThreshold",
        label="FEM 7 current trip threshold",
        forwarded=True,
    )
    fem8CurrentTripThreshold = attribute(
        name="fem8CurrentTripThreshold",
        label="FEM 8 current trip threshold",
        forwarded=True,
    )
    fem9CurrentTripThreshold = attribute(
        name="fem9CurrentTripThreshold",
        label="FEM 9 current trip threshold",
        forwarded=True,
    )
    fem10CurrentTripThreshold = attribute(
        name="fem10CurrentTripThreshold",
        label="FEM 10 current trip threshold",
        forwarded=True,
    )
    fem11CurrentTripThreshold = attribute(
        name="fem11CurrentTripThreshold",
        label="FEM 11 current trip threshold",
        forwarded=True,
    )
    fem12CurrentTripThreshold = attribute(
        name="fem12CurrentTripThreshold",
        label="FEM 12 current trip threshold",
        forwarded=True,
    )
    warningFlags = attribute(name="warningFlags", label="Warning flags", forwarded=True)
    alarmFlags = attribute(name="alarmFlags", label="Alarm flags", forwarded=True)

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

        self._port_forcings: list[str] = []

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tFndhPort: {self.FndhPort}\n"
            f"\tPasdFQDN: {self.PasdFQDN}\n"
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
    # Attributes
    # ----------
    @attribute(dtype=(str,))
    def portForcings(self) -> list[str]:
        return self._port_forcings

    # --------------
    # Initialization
    # --------------
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
            self._component_state_changed,
            self.PORT_COUNT,
            self.FndhPort,
            self.PasdFQDN,
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

        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_changed(power=self.component_manager._power_state)
        else:
            self._component_state_changed(power=PowerState.UNKNOWN)

        super()._communication_state_changed(communication_state)
        self._health_model.update_state(
            communicating=(communication_state == CommunicationStatus.ESTABLISHED)
        )

    def _component_state_changed(
        self: MccsSmartBox,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        status: Optional[str] = None,
        port_forcings: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param status: the status of the smartbox
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if port_forcings is not None:
            self._port_forcings = port_forcings
            self.push_change_event("portForcings", port_forcings)

        super()._component_state_changed(fault=fault, power=power)
        self._health_model.update_state(fault=fault, power=power, pasdbus_status=status)

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
