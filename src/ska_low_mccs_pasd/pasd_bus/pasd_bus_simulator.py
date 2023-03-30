# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""
This module provides a simulated component manager for the PaSD bus.

The components of a PaSD system all share the same multi-drop serial
bus, and monitoring and control of those component is necessarily via
that bus:

* MccsAntenna instances use the bus to monitor and control their
  antennas;
* MccsSmartbox instances use the bus to monitor and control their
  smartboxes;
* The MccsFndh instance uses the bus to monitor and control the FNDH

To arbitrate access and prevent collisions/congestion, the MccsPasdBus
device is given exclusive use of the PaSD bus. All other devices can
only communicate on the PaSD bus by proxying through MccsPasdBus.

To that end, MccsPasdBus needs a PasdBusComponentManager that talks to
the PaSD bus using MODBUS-over-TCP. This class is not yet written; but
meanwhile, a PasdBusJsonApi class takes its place, providing access to
the PaSD bus simulator, but talking JSON instead of MODBUS.

The Pasd bus simulator class is provided below. To help manage
complexity, it is composed of a separate FNDH simulator and a number of
smartbox simulators, which in turn make use of port simulators. Only the
PasdBusSimulator class should be considered public.
"""
from __future__ import annotations

import importlib
import logging
from datetime import datetime
from typing import Final, Optional, TypedDict

import yaml

_AntennaConfigType = TypedDict(
    "_AntennaConfigType",
    {
        "antenna_id": int,
        "smartbox_id": int,
        "smartbox_port": int,
        "tpm_id": int,
        "tpm_input": int,
    },
)


_SmartboxConfigType = TypedDict(
    "_SmartboxConfigType",
    {
        "smartbox_id": int,
        "fndh_port": int,
    },
)


AntennaInfoType = TypedDict(
    "AntennaInfoType",
    {
        "smartbox_id": int,
        "port_number": int,
        "tpm_number": int,
        "tpm_input_number": int,
    },
)


SmartboxInfoType = TypedDict(
    "SmartboxInfoType",
    {
        "modbus_register_map_revision_number": int,
        "pcb_revision_number": int,
        "cpu_id": int,
        "chip_id": int,
        "firmware_version": str,
        "uptime_integer": int,
        "status": str,
        "led_status_pattern": str,
        "read_time": str,
    },
)


FndhInfoType = TypedDict(
    "FndhInfoType",
    {
        "modbus_register_map_revision_number": int,
        "pcb_revision_number": int,
        "cpu_id": int,
        "chip_id": int,
        "firmware_version": str,
        "uptime_integer": int,
        "status": str,
        "led_status_pattern": str,
        "read_time": str,
    },
)


logger = logging.getLogger()


class _PasdPortSimulator:
    """
    A private class that manages a single simulated port of a PaSD device.

    It supports:

    * breaker tripping: in the real hardware, a port breaker might trip,
      for example as a result of an overcurrent condition. This
      simulator provides for simulating a breaker trip. Once tripped,
      the port will not deliver any power until the breaker has been
      reset.

    * local forcing: a technician in the field can manually force the
      power state of a port. If forced off, a port will not deliver
      power regardless of other settings. If forced on, an (untripped)
      port will deliver power regardless of other settings.

    * online and offline delivery of power. When we tell a port to turn
      on, we can also indicate whether we want it to remain on if the
      control system goes offline. This simulator remembers that
      information, but there's no way to tell the simulator that the
      control system is offline because the whole point of these
      simulators is to simulate the PaSD from the point of view of the
      control system. By definition, the control system cannot observe
      the behaviour of PaSD when the control system is offline, so there
      is no need to implement this behaviour.
    """

    def __init__(self: _PasdPortSimulator):
        """Initialise a new instance."""
        self._connected = False
        self._breaker_tripped = False
        self._forcing: Optional[bool] = None
        self._desired_on_when_online = False
        self._desired_on_when_offline = False

    @property
    def connected(self: _PasdPortSimulator) -> bool:
        """
        Return whether anything is connected to this port.

        :return: whether anything is connected to this port.
        """
        return self._connected

    @connected.setter
    def connected(self: _PasdPortSimulator, is_connected: bool) -> None:
        """
        Set whether anything is connected to this port.

        :param is_connected: whether anything is connected to the port.
        """
        self._connected = is_connected

    def turn_on(
        self: _PasdPortSimulator, stay_on_when_offline: bool = True
    ) -> Optional[bool]:
        """
        Turn the port on.

        :param stay_on_when_offline: whether the port should stay on if
            the control system goes offline.

        :return: whether successful, or None if there was nothing to do.
        """
        if not self._connected:
            return False  # Can't turn a port on if nothing is connected to it
        if self._forcing is False:
            return False  # Can't turn a port on if it is locally forced off

        if self._desired_on_when_online and (
            self._desired_on_when_offline == stay_on_when_offline
        ):
            return None

        self._desired_on_when_online = True
        self._desired_on_when_offline = stay_on_when_offline
        return True

    def turn_off(self: _PasdPortSimulator) -> Optional[bool]:
        """
        Turn the port off.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._forcing:
            return False  # Can't turn a port off if it is locally forced on
        if not self._desired_on_when_online:
            return None

        self._desired_on_when_online = False
        self._desired_on_when_offline = False
        return True

    @property
    def forcing(self: _PasdPortSimulator) -> Optional[bool]:
        """
        Return the forcing status of this port.

        :return: the forcing status of this port. True means the port
            has been forced on. False means it has been forced off. None
            means it has not be forced.
        """
        return self._forcing

    def simulate_forcing(
        self: _PasdPortSimulator, forcing: Optional[bool]
    ) -> Optional[bool]:
        """
        Simulate locally forcing this port.

        :param forcing: the new forcing status. True means the port has
            been forced on. False means it has been forced off. None
            means it has not be forced.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._forcing == forcing:
            return None
        self._forcing = forcing
        return True

    @property
    def breaker_tripped(self: _PasdPortSimulator) -> bool:
        """
        Return whether the port breaker has been tripped.

        :return: whether the breaker has been tripped
        """
        return self._breaker_tripped

    def simulate_breaker_trip(self: _PasdPortSimulator) -> Optional[bool]:
        """
        Simulate a breaker trip.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._breaker_tripped:
            return None
        self._breaker_tripped = True
        return True

    def reset_breaker(self: _PasdPortSimulator) -> Optional[bool]:
        """
        Reset the breaker.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._breaker_tripped:
            self._breaker_tripped = False
            return True
        return None

    @property
    def desired_power_when_online(self: _PasdPortSimulator) -> bool:
        """
        Return the desired power mode of the port when the control system is online.

        :return: the desired power mode of the port when the control
            system is online.
        """
        return self._desired_on_when_online

    @property
    def desired_power_when_offline(self: _PasdPortSimulator) -> bool:
        """
        Return the desired power mode of the port when the control system is offline.

        :return: the desired power mode of the port when the control
            system is offline.
        """
        return self._desired_on_when_offline

    @property
    def power_sensed(self: _PasdPortSimulator) -> bool:
        """
        Return whether power is sensed on the port.

        :return: whether power is sensed on the port.
        """
        if self._breaker_tripped:
            return False
        if self._forcing is not None:
            return self._forcing
        return self._desired_on_when_online


class PasdHardwareSimulator:
    """
    A class that captures commonality between FNDH and smartbox simulators.

    Both things manage a set of ports, which can be switched on and off,
    locally forced, experience a breaker trip, etc.
    """

    def __init__(
        self: PasdHardwareSimulator,
        number_of_ports: int,
    ) -> None:
        """
        Initialise a new instance.

        :param number_of_ports: number of ports managed by this hardware
        """
        self._service_led_on = False

        self._ports = [_PasdPortSimulator() for _ in range(number_of_ports)]

    def configure(
        self: PasdHardwareSimulator,
        ports_connected: list[bool],
    ) -> None:
        """
        Configure the hardware.

        :param ports_connected: whether each port has something
            connected to it.

        :raises ValueError: if the configuration doesn't match the
            number of ports.
        """
        if len(ports_connected) != len(self._ports):
            raise ValueError("Configuration must match the number of ports.")
        for (port, is_connected) in zip(self._ports, ports_connected):
            port.connected = is_connected

    @property
    def are_ports_connected(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return whether each port is connected.

        :return: whether each port is connected.
        """
        return [port.connected for port in self._ports]

    def is_port_connected(self: PasdHardwareSimulator, port_number: int) -> bool:
        """
        Return whether a specified port is connected.

        :param port_number: number of the port to be queried.

        :return: whether the port is connected
        """
        return self._ports[port_number - 1].connected

    def simulate_port_forcing(
        self: PasdHardwareSimulator, port_number: int, forcing: Optional[bool]
    ) -> Optional[bool]:
        """
        Simulate local forcing of a port.

        :param port_number: the port number for which local forcing will
            be simulated.
        :param forcing: the new forcing status of the port. True means
            the port has been forced on. False means it has been forced
            off. None means it has not be forced.

        :return: whether successful, or None if there was nothing to do.
        """
        return self._ports[port_number - 1].simulate_forcing(forcing)

    @property
    def port_forcings(self: PasdHardwareSimulator) -> list[Optional[bool]]:
        """
        Return the forcing statuses of all ports.

        :return: the forcing statuses of each port. True means the port
            has been forced on. False means it has been forced off. None
            means it has not be forced.
        """
        return [port.forcing for port in self._ports]

    def get_port_forcing(
        self: PasdHardwareSimulator, port_number: int
    ) -> Optional[bool]:
        """
        Return the forcing status of a specified port.

        :param port_number: number of the port to be queried

        :return: the forcing status of the port. True means the port has
            been forced on. False means it has been forced off. None
            means it has not be forced.
        """
        return self._ports[port_number - 1].forcing

    def is_port_breaker_tripped(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> bool:
        """
        Return whether a specified port has had its breaker tripped.

        :param port_number: number of the port to be queried

        :return: whether the port has had its breaker tripped
        """
        return self._ports[port_number - 1].breaker_tripped

    def simulate_port_breaker_trip(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> Optional[bool]:
        """
        Simulate a port breaker trip.

        :param port_number: number of the port for which a breaker trip
            will be simulated

        :return: whether successful, or None if there was nothing to do
        """
        return self._ports[port_number - 1].simulate_breaker_trip()

    def reset_port_breaker(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> Optional[bool]:
        """
        Reset a tripped port breaker.

        :param port_number: number of the port whose breaker should be
            reset

        :return: whether successful, or None if there was nothing to do
        """
        return self._ports[port_number - 1].reset_breaker()

    def turn_port_on(
        self: PasdHardwareSimulator,
        port_number: int,
        stay_on_when_offline: bool = True,
    ) -> Optional[bool]:
        """
        Turn on a specified port.

        :param port_number: number of the port to turn off
        :param stay_on_when_offline: whether to remain on if the control
            system goes offline

        :return: whether successful, or None if there was nothing to do
        """
        return self._ports[port_number - 1].turn_on(
            stay_on_when_offline=stay_on_when_offline
        )

    def turn_port_off(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> Optional[bool]:
        """
        Turn off a specified port.

        :param port_number: number of the port to turn off

        :return: whether successful, or None if there was nothing to do
        """
        return self._ports[port_number - 1].turn_off()

    def get_port_desired_power_online(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> bool:
        """
        Return the desired power of a specified port when the device is online.

        That is, should the port be powered if the control system is
        online?

        :param port_number: number of the port to be queried

        :return: the desired power of the port when the device is
            online
        """
        return self._ports[port_number - 1].desired_power_when_online

    @property
    def ports_desired_power_online(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return the desired power of each port when the device is online.

        That is, for each port, should it be powered if the control
        system is online?

        :return: the desired power of each port when the device is
            online
        """
        return [port.desired_power_when_online for port in self._ports]

    def get_port_desired_power_offline(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> bool:
        """
        Return the desired power of a specified port when the device is offline.

        That is, should the port remain powered if the control system
        goes offline?

        :param port_number: number of the port to be queried

        :return: the desired power of the port when the device is
            offline
        """
        return self._ports[port_number - 1].desired_power_when_offline

    @property
    def ports_desired_power_offline(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return the desired power of each port when the device is offline.

        That is, for each port, should it remain powered if the control
        system goes offline?

        :return: the desired power of each port when the device is
            offline
        """
        return [port.desired_power_when_offline for port in self._ports]

    def is_port_commanded_powered(
        self: PasdHardwareSimulator, port_number: int
    ) -> bool:
        """
        Return whether a given port is commanded powered.

        A port might be commanded powered on, yet power may not be
        sensed: it might have been locally forced off, or a breaker
        might has tripped.

        :param port_number: number of the port to be queried

        :return: whether the port is commanded powered.
        """
        return self._ports[port_number - 1].desired_power_when_online

    @property
    def ports_power_sensed(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return the actual sensed power state of each port.

        :return: the actual sensed power state of each port.
        """
        return [port.power_sensed for port in self._ports]

    def is_port_power_sensed(self: PasdHardwareSimulator, port_number: int) -> bool:
        """
        Return whether power is sensed on a specified port.

        :param port_number: number of the port for which to check if
            power is sensed.

        :return: whether power is sensed on the port
        """
        return self._ports[port_number - 1].power_sensed

    @property
    def service_led_on(self: PasdHardwareSimulator) -> bool:
        """
        Whether the blue service indicator LED is on.

        :return: whether the blue service indicator LED is on.
        """
        return self._service_led_on

    @service_led_on.setter
    def service_led_on(
        self: PasdHardwareSimulator,
        led_on: bool,
    ) -> None:
        """
        Turn on/off the blue service indicator LED.

        :param led_on: whether the blue service indicator LED should be
            on.
        """
        self._service_led_on = led_on


class FndhSimulator(PasdHardwareSimulator):
    """
    A simple simulator of a Field Node Distribution Hub.

    This FNDH simulator will never be used as a standalone simulator. It
    will only be used as a component of a PaSD bus simulator.
    """

    NUMBER_OF_PORTS = 28

    CPU_ID = 22
    CHIP_ID = 23
    MODBUS_REGISTER_MAP_REVISION_NUMBER = 20
    PCB_REVISION_NUMBER = 21

    DEFAULT_FIRMWARE_VERSION = "1.2.3-fake"
    DEFAULT_STATUS = "OK"
    DEFAULT_LED_PATTERN = "OK"
    DEFAULT_UPTIME = 2000
    DEFAULT_PSU48V_VOLTAGES = [47.9, 48.1]
    DEFAULT_PSU5V_VOLTAGE = 5.1
    DEFAULT_PSU48V_CURRENT = 20.1
    DEFAULT_PSU48V_TEMPERATURE = 41.2
    DEFAULT_PSU5V_TEMPERATURE = 41.3
    DEFAULT_PCB_TEMPERATURE = 41.4
    DEFAULT_OUTSIDE_TEMPERATURE = 41.5

    def __init__(self: FndhSimulator) -> None:
        """Initialise a new instance."""
        self._update_time = datetime.now().isoformat()
        super().__init__(self.NUMBER_OF_PORTS)

    @property
    def psu48v_voltages(self: FndhSimulator) -> list[float]:
        """
        Return the output voltages on the two 48V DC power supplies, in volts.

        :return: the output voltages on the two 48V DC power supplies,
             in volts.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PSU48V_VOLTAGES

    @property
    def psu5v_voltage(self: FndhSimulator) -> float:
        """
        Return the output voltage on the 5V power supply, in volts.

        :return: the output voltage on the 5V power supply, in volts.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PSU5V_VOLTAGE

    @property
    def psu48v_current(self: FndhSimulator) -> float:
        """
        Return the total current on the 48V DC bus, in amperes.

        :return: the total current on the 48V DC bus, in amperes.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PSU48V_CURRENT

    @property
    def psu48v_temperature(self: FndhSimulator) -> float:
        """
        Return the common temperature for both 48V power supplies, in celcius.

        :return: the common temperature for both 48V power supplies, in celcius.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PSU48V_TEMPERATURE

    @property
    def psu5v_temperature(self: FndhSimulator) -> float:
        """
        Return the temperature of the 5V power supply, in celcius.

        :return: the temperature of the 5V power supply, in celcius.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PSU5V_TEMPERATURE

    @property
    def pcb_temperature(self: FndhSimulator) -> float:
        """
        Return the temperature of the FNDH's PCB, in celcius.

        :return: the temperature of the FNDH's PCB, in celcius.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PCB_TEMPERATURE

    @property
    def outside_temperature(self: FndhSimulator) -> float:
        """
        Return the temperature outside the FNDH, in celcius.

        :return: the temperature outside the FNDH, in celcius.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_OUTSIDE_TEMPERATURE

    @property
    def status(self: FndhSimulator) -> str:
        """
        Return the status of the FNDH.

        :return: the status of the FNDH
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_STATUS

    def update_status(self: FndhSimulator) -> None:
        """
        Update the FNDH status.

        This will usually be called on a polling loop, and will be the
        primary mechanism by which attributes are updated. But for now
        we don't poll, so there's not much for this method to do.
        """
        self._update_time = datetime.now().isoformat()

    def get_info(self: FndhSimulator) -> FndhInfoType:
        """
        Return information about an FNDH controller.

        :return: a dictionary containing information about the FNDH
            controller.
        """
        # TODO: We're currently returning canned results.
        revision = self.MODBUS_REGISTER_MAP_REVISION_NUMBER
        return {
            "modbus_register_map_revision_number": revision,
            "pcb_revision_number": self.PCB_REVISION_NUMBER,
            "cpu_id": self.CPU_ID,
            "chip_id": self.CHIP_ID,
            "firmware_version": self.DEFAULT_FIRMWARE_VERSION,
            "uptime_integer": self.DEFAULT_UPTIME,
            "status": self.DEFAULT_STATUS,
            "led_status_pattern": self.DEFAULT_LED_PATTERN,
            "read_time": self._update_time,
        }


class SmartboxSimulator(PasdHardwareSimulator):
    """A simulator for a PaSD smartbox."""

    NUMBER_OF_PORTS: Final = 12

    CPU_ID: Final = 24
    CHIP_ID: Final = 25
    MODBUS_REGISTER_MAP_REVISION_NUMBER: Final = 20
    PCB_REVISION_NUMBER: Final = 21

    DEFAULT_FIRMWARE_VERSION = "0.1.2-fake"
    DEFAULT_INPUT_VOLTAGE: Final = 48.0
    DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE: Final = 5.0
    DEFAULT_POWER_SUPPLY_TEMPERATURE: Final = 42.1
    DEFAULT_OUTSIDE_TEMPERATURE: Final = 44.4
    DEFAULT_PCB_TEMPERATURE: Final = 38.6
    DEFAULT_STATUS: Final = "OK"
    DEFAULT_LED_PATTERN: Final = "OK"
    DEFAULT_UPTIME: Final = 1000

    DEFAULT_PORT_CURRENT_DRAW: Final = 20.5

    def __init__(self: SmartboxSimulator) -> None:
        """Initialise a new instance."""
        super().__init__(self.NUMBER_OF_PORTS)
        self._port_breaker_tripped = [False] * self.NUMBER_OF_PORTS
        self._update_time = datetime.now().isoformat()

    def get_port_current_draw(
        self: SmartboxSimulator,
        port_number: int,
    ) -> float:
        """
        Return the current being drawn from a given smartbox port.

        :param port_number: number of the port for which the current
            draw is sought

        :return: the current being drawn from the port.
        """
        if self.is_port_connected(port_number):
            # TODO: We're currently returning canned results.
            return self.DEFAULT_PORT_CURRENT_DRAW
        return 0.0

    @property
    def input_voltage(self: SmartboxSimulator) -> float:
        """
        Return the input voltage, in volts.

        :return: the input voltage.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_INPUT_VOLTAGE

    @property
    def power_supply_output_voltage(self: SmartboxSimulator) -> float:
        """
        Return the power supply output voltage, in volts.

        :return: the power supply output voltage
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE

    @property
    def status(self: SmartboxSimulator) -> str:
        """
        Return the status of the smartbox.

        :return: a string statuses.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_STATUS

    @property
    def power_supply_temperature(self: SmartboxSimulator) -> float:
        """
        Return the smartbox's power supply temperature, in celcius.

        :return: the power supply temperature.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_POWER_SUPPLY_TEMPERATURE

    @property
    def outside_temperature(self: SmartboxSimulator) -> float:
        """
        Return the smartbox's outside temperature, in celcius.

        :return: the outside temperature.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_OUTSIDE_TEMPERATURE

    @property
    def pcb_temperature(self: SmartboxSimulator) -> float:
        """
        Return the smartbox's PCB temperature, in celcius.

        :return: the PCB temperatures.
        """
        # TODO: We're currently returning canned results.
        return self.DEFAULT_PCB_TEMPERATURE

    def update_status(self: SmartboxSimulator) -> None:
        """
        Update the smartbox status.

        This will usually be called on a polling loop, and will be the
        primary mechanism by which attributes are updated. But for now
        we don't poll, so there's not much for this method to do.
        """
        self._update_time = datetime.now().isoformat()

    def get_info(self: SmartboxSimulator) -> SmartboxInfoType:
        """
        Return information about this smartbox.

        :return: a dictionary containing information about the smartbox.
        """
        # TODO: We're currently returning canned results.
        revision = self.MODBUS_REGISTER_MAP_REVISION_NUMBER
        return {
            "modbus_register_map_revision_number": revision,
            "pcb_revision_number": self.PCB_REVISION_NUMBER,
            "cpu_id": self.CPU_ID,
            "chip_id": self.CHIP_ID,
            "firmware_version": self.DEFAULT_FIRMWARE_VERSION,
            "uptime_integer": self.DEFAULT_UPTIME,
            "status": self.DEFAULT_STATUS,
            "led_status_pattern": self.DEFAULT_LED_PATTERN,
            "read_time": self._update_time,
        }


# pylint: disable-next=too-many-public-methods, too-many-instance-attributes
class PasdBusSimulator:
    """
    A stub class that provides similar functionality to a PaSD bus.

    Many attributes are stubbed out:

    * The antennas are always online.
    * Antenna status cannot be forced.
    * Voltages, currents and temperatures never change.

    You can, however:

    * simulate tripping an antenna breaker, and reset a breaker;
    * turn antennas off and on;
    """

    CONFIG_PATH = "pasd_configuration.yaml"

    NUMBER_OF_SMARTBOXES = 24
    NUMBER_OF_ANTENNAS = 256

    def __init__(
        self: PasdBusSimulator,
        station_id: int,
        logging_level: int = logging.INFO,
    ) -> None:
        """
        Initialise a new instance.

        :param station_id: id of the station to which this PaSD belongs.
        :param logging_level: the level to log at.
        """
        self._station_id = station_id
        logger.setLevel(logging_level)

        self._fndh_simulator = FndhSimulator()
        self._smartbox_simulators = [
            SmartboxSimulator() for _ in range(self.NUMBER_OF_SMARTBOXES)
        ]

        self._smartbox_fndh_ports: list[int] = [0] * self.NUMBER_OF_SMARTBOXES
        self._antenna_smartbox_ports: list[tuple[int, int]] = [
            (0, 0)
        ] * self.NUMBER_OF_ANTENNAS

        self._antenna_configs: list[_AntennaConfigType] = []
        self.reload_database()

        # ANTENNAS
        self._antennas_desired_power_online = [False] * len(self._antenna_configs)
        self._antennas_desired_power_offline = [False] * len(self._antenna_configs)

        logger.info(f"Initialised PaSD bus simulator for station {station_id}.")

    def reload_database(self: PasdBusSimulator) -> bool:
        """
        Load PaSD configuration data from a database into this simulator.

        :return: whether successful

        :raises yaml.YAMLError: if the config file cannot be parsed.
        """
        config_data = importlib.resources.read_text(
            "ska_low_mccs_pasd.pasd_bus",
            self.CONFIG_PATH,
        )

        assert config_data is not None  # for the type-checker

        try:
            config = yaml.safe_load(config_data)
        except yaml.YAMLError as exception:
            logger.error(
                f"PaSD Bus simulator could not load configuration: {exception}."
            )
            raise

        my_config = config["stations"][self._station_id - 1]

        fndh_port_is_connected = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_config in my_config["smartboxes"]:
            smartbox_id = smartbox_config["smartbox_id"]
            fndh_port = smartbox_config["fndh_port"]
            self._smartbox_fndh_ports[smartbox_id - 1] = fndh_port
            fndh_port_is_connected[fndh_port - 1] = True
        self._fndh_simulator.configure(fndh_port_is_connected)

        smartbox_ports_connected = [
            [False] * SmartboxSimulator.NUMBER_OF_PORTS
        ] * self.NUMBER_OF_SMARTBOXES
        for antenna_config in my_config["antennas"]:
            antenna_id = antenna_config["antenna_id"]
            smartbox_id = antenna_config["smartbox_id"]
            smartbox_port = antenna_config["smartbox_port"]
            self._antenna_smartbox_ports[antenna_id - 1] = (
                smartbox_id,
                smartbox_port,
            )
            smartbox_ports_connected[smartbox_id - 1][smartbox_port - 1] = True

        for (smartbox_index, ports_connected) in enumerate(smartbox_ports_connected):
            self._smartbox_simulators[smartbox_index].configure(ports_connected)

        # hoping to get rid of this eventually
        self._antenna_configs = config["stations"][self._station_id - 1]["antennas"]

        return True

    def get_fndh_info(self: PasdBusSimulator) -> FndhInfoType:
        """
        Return information about an FNDH controller.

        :return: a dictionary containing information about the FNDH
            controller.
        """
        return self._fndh_simulator.get_info()

    @property
    def fndh_psu48v_voltages(self: PasdBusSimulator) -> list[float]:
        """
        Return the output voltages on the two 48V DC power supplies, in volts.

        :return: the output voltages on the two 48V DC power supplies,
             in volts.
        """
        return self._fndh_simulator.psu48v_voltages

    @property
    def fndh_psu5v_voltage(self: PasdBusSimulator) -> float:
        """
        Return the output voltage on the 5V power supply, in volts.

        :return: the output voltage on the 5V power supply, in volts.
        """
        return self._fndh_simulator.psu5v_voltage

    @property
    def fndh_psu48v_current(self: PasdBusSimulator) -> float:
        """
        Return the total current on the 48V DC bus, in amperes.

        :return: the total current on the 48V DC bus, in amperes.
        """
        return self._fndh_simulator.psu48v_current

    @property
    def fndh_psu48v_temperature(self: PasdBusSimulator) -> float:
        """
        Return the common temperature for both 48V power supplies, in celcius.

        :return: the common temperature for both 48V power supplies, in celcius.
        """
        return self._fndh_simulator.psu48v_temperature

    @property
    def fndh_psu5v_temperature(self: PasdBusSimulator) -> float:
        """
        Return the temperature of the 5V power supply, in celcius.

        :return: the temperature of the 5V power supply, in celcius.
        """
        return self._fndh_simulator.psu5v_temperature

    @property
    def fndh_pcb_temperature(self: PasdBusSimulator) -> float:
        """
        Return the temperature of the FNDH's PCB, in celcius.

        :return: the temperature of the FNDH's PCB, in celcius.
        """
        return self._fndh_simulator.pcb_temperature

    @property
    def fndh_outside_temperature(self: PasdBusSimulator) -> float:
        """
        Return the temperature outside the FNDH, in celcius.

        :return: the temperature outside the FNDH, in celcius.
        """
        return self._fndh_simulator.outside_temperature

    @property
    def fndh_status(self: PasdBusSimulator) -> str:
        """
        Return the status of the FNDH.

        :return: the status of the FNDH
        """
        return self._fndh_simulator.status

    @property
    def fndh_service_led_on(self: PasdBusSimulator) -> bool:
        """
        Whether the FNDH's blue service indicator LED is on.

        :return: whether the FNDH's blue service indicator LED is on.
        """
        return self._fndh_simulator.service_led_on

    def set_fndh_service_led(
        self: PasdBusSimulator,
        led_on: bool,
    ) -> Optional[bool]:
        """
        Turn on/off the FNDH's blue service indicator LED.

        :param led_on: whether the LED should be on.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._fndh_simulator.service_led_on == led_on:
            return None
        self._fndh_simulator.service_led_on = led_on
        return True

    @property
    def fndh_ports_power_sensed(self: PasdBusSimulator) -> list[bool]:
        """
        Return the actual sensed power state of each FNDH port.

        :return: the actual sensed power state of each FNDH port.
        """
        return list(self._fndh_simulator.ports_power_sensed)

    def is_fndh_port_power_sensed(
        self: PasdBusSimulator,
        port_number: int,
    ) -> bool:
        """
        Return whether power is sensed on a specified FNDH port.

        :param port_number: number of the FNDH port for which to check
            if power is sensed.

        :return: whether power is sensed on the port
        """
        return self._fndh_simulator.is_port_power_sensed(port_number)

    @property
    def fndh_ports_connected(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether there is a smartbox connected to each FNDH port.

        :return: whether there is a smartbox connected to each FNDH
            port.
        """
        return list(self._fndh_simulator.are_ports_connected)

    @property
    def fndh_port_forcings(self: PasdBusSimulator) -> list[Optional[bool]]:
        """
        Return whether each FNDH port has had its power locally forced.

        :return: a list of values, one for each port. True means the
            port has been locally forced on. False means the port has
            been locally forced off. None means the port has not been
            locally forced.
        """
        return list(self._fndh_simulator.port_forcings)

    def get_fndh_port_forcing(
        self: PasdBusSimulator, port_number: int
    ) -> Optional[bool]:
        """
        Return the forcing status of a specified FNDH port.

        :param port_number: number of the FNDH port for which the
            forcing status is sought

        :return: the forcing status of a specified FNDH port. True means
            the port has been locally forced on. False means the port
            has been locally forced off. None means the port has not
            been locally forced.
        """
        return self._fndh_simulator.get_port_forcing(port_number)

    def simulate_fndh_port_forcing(
        self: PasdBusSimulator, port_number: int, forcing: Optional[bool]
    ) -> None:
        """
        Simulate local forcing of the power of a specified FNDH port.

        :param port_number: number of the FNDH port for which forcing is
            to be simulated.
        :param forcing: the simulated forcing status of the port. True
            means the port has been locally forced on. False means the
            port has been locally forced off. None means the port has
            not been locally forced.
        """
        self._fndh_simulator.simulate_port_forcing(port_number, forcing)

    @property
    def fndh_ports_desired_power_online(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each FNDH port is desired to be powered when controlled by MCCS.

        :return: whether each FNDH port is desired to be powered when
            controlled by MCCS
        """
        return list(self._fndh_simulator.ports_desired_power_online)

    @property
    def fndh_ports_desired_power_offline(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each FNDH port should be powered when MCCS control has been lost.

        :return: whether each FNDH port is desired to be powered when
            MCCS control has been lost
        """
        return list(self._fndh_simulator.ports_desired_power_online)

    def get_smartbox_info(self: PasdBusSimulator, smartbox_id: int) -> SmartboxInfoType:
        """
        Return information about a smartbox.

        :param smartbox_id: the smartbox number

        :return: a dictionary containing information about the smartbox.
        """
        return self._smartbox_simulators[smartbox_id - 1].get_info()

    def turn_smartbox_on(
        self: PasdBusSimulator,
        smartbox_id: int,
        desired_on_if_offline: bool = True,
    ) -> Optional[bool]:
        """
        Turn on a smartbox.

        :param smartbox_id: the (one-based) number of the smartbox to be
            turned on.
        :param desired_on_if_offline: whether the smartbox should stay
            on if the control system goes offline.

        :return: Whether successful, or None if there was nothing to do
        """
        fndh_port = self._smartbox_fndh_ports[smartbox_id - 1]
        return self._fndh_simulator.turn_port_on(fndh_port, desired_on_if_offline)

    def turn_smartbox_off(self: PasdBusSimulator, smartbox_id: int) -> Optional[bool]:
        """
        Turn off a smartbox.

        :param smartbox_id: the (one-based) number of the smartbox to be
            turned off.

        :return: Whether successful, or None if there was nothing to do
        """
        fndh_port = self._smartbox_fndh_ports[smartbox_id - 1]
        return self._fndh_simulator.turn_port_off(fndh_port)

    def is_smartbox_port_power_sensed(
        self: PasdBusSimulator,
        smartbox_id: int,
        smartbox_port_number: int,
    ) -> bool:
        """
        Return whether power is sensed at a given smartbox port.

        :param smartbox_id: id of the smartbox to check
        :param smartbox_port_number: number of the port to check

        :return: whether power is sensed that the specified port.
        """
        fndh_port = self._smartbox_fndh_ports[smartbox_id - 1]
        return self._fndh_simulator.is_port_power_sensed(
            fndh_port
        ) and self._smartbox_simulators[smartbox_id - 1].is_port_power_sensed(
            smartbox_port_number
        )

    @property
    def smartbox_input_voltages(self: PasdBusSimulator) -> list[float]:
        """
        Return each smartbox's power input voltage, in volts.

        :return: a list of voltages.
        """
        return [smartbox.input_voltage for smartbox in self._smartbox_simulators]

    @property
    def smartbox_power_supply_output_voltages(
        self: PasdBusSimulator,
    ) -> list[float]:
        """
        Return each smartbox's power supply output voltage, in volts.

        :return: a list of voltages.
        """
        return [
            smartbox.power_supply_output_voltage
            for smartbox in self._smartbox_simulators
        ]

    @property
    def smartbox_statuses(self: PasdBusSimulator) -> list[str]:
        """
        Return the status of each smartbox.

        :return: a list of string statuses.
        """
        return [smartbox.status for smartbox in self._smartbox_simulators]

    @property
    def smartbox_power_supply_temperatures(
        self: PasdBusSimulator,
    ) -> list[float]:
        """
        Return each smartbox's power supply temperature, in celcius.

        :return: a list of temperatures.
        """
        return [
            smartbox.power_supply_temperature for smartbox in self._smartbox_simulators
        ]

    @property
    def smartbox_outside_temperatures(self: PasdBusSimulator) -> list[float]:
        """
        Return each smartbox's outside temperature, in celcius.

        :return: a list of temperatures.
        """
        return [smartbox.outside_temperature for smartbox in self._smartbox_simulators]

    @property
    def smartbox_pcb_temperatures(self: PasdBusSimulator) -> list[float]:
        """
        Return each smartbox's PCB temperature, in celcius.

        :return: a list of temperatures.
        """
        return [smartbox.pcb_temperature for smartbox in self._smartbox_simulators]

    @property
    def smartbox_service_leds_on(self: PasdBusSimulator) -> list[bool]:
        """
        Whether each smartbox's blue service indicator LED is on.

        :return: whether each smartbox's blue service indicator LED is
            on.
        """
        return [smartbox.service_led_on for smartbox in self._smartbox_simulators]

    def set_smartbox_service_led(
        self: PasdBusSimulator,
        smartbox_id: int,
        led_on: bool,
    ) -> Optional[bool]:
        """
        Turn on the blue service indicator LED for a smartbox.

        :param smartbox_id: the smartbox to have its LED switched
        :param led_on: whether the LED should be on.

        :return: whether successful, or None if there was nothing to do
        """
        if self._smartbox_simulators[smartbox_id - 1].service_led_on == led_on:
            return None

        self._smartbox_simulators[smartbox_id - 1].service_led_on = led_on
        return True

    @property
    def smartbox_fndh_ports(self: PasdBusSimulator) -> list[int]:
        """
        Return the physical port in the FNDH into which each smartbox is plugged.

        :return: the physical port in the FNDH into which each smartbox
            is plugged.
        """
        return list(self._smartbox_fndh_ports)

    @property
    def smartboxes_desired_power_online(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each smartbox should be on when the PaSD is under MCCS control.

        :return: whether each smartbox should be on when the PaSD is
            under MCCS control.
        """
        return [
            self._fndh_simulator.get_port_desired_power_online(fndh_port)
            for fndh_port in self._smartbox_fndh_ports
        ]

    @property
    def smartboxes_desired_power_offline(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each smartbox should be on when MCCS control of the PaSD is lost.

        :return: whether each smartbox should be on when MCCS control of
            the PaSD is lost.
        """
        return [
            self._fndh_simulator.get_port_desired_power_offline(fndh_port)
            for fndh_port in self._smartbox_fndh_ports
        ]

    def get_smartbox_ports_power_sensed(
        self: PasdBusSimulator, smartbox_id: int
    ) -> list[bool]:
        """
        Return whether power is sensed at each port of a smartbox.

        :param smartbox_id: id of the smartbox for which we want to know
            if power is sensed.

        :return: whether each smartbox should be on when MCCS control of
            the PaSD is lost.
        """
        return list(self._smartbox_simulators[smartbox_id - 1].ports_power_sensed)

    def get_antenna_info(self: PasdBusSimulator, antenna_id: int) -> AntennaInfoType:
        """
        Return information about relationship of an antenna to other PaSD components.

        :param antenna_id: the antenna number

        :return: a dictionary containing the antenna's smartbox number,
            port number, TPM number and TPM input number.
        """
        antenna_config = self._antenna_configs[antenna_id - 1]
        return {
            "smartbox_id": antenna_config["smartbox_id"],
            "port_number": antenna_config["smartbox_port"],
            "tpm_number": antenna_config["tpm_id"],
            "tpm_input_number": antenna_config["tpm_input"],
        }

    @property
    def antennas_online(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each antenna is online.

        :return: a list of booleans indicating whether each antenna is
            online.
        """
        fndh_ports = [
            self._smartbox_fndh_ports[smartbox_id - 1]
            for (smartbox_id, _) in self._antenna_smartbox_ports
        ]
        return [
            self._fndh_simulator.is_port_power_sensed(fndh_port)
            for fndh_port in fndh_ports
        ]

    @property
    def antenna_forcings(self: PasdBusSimulator) -> list[Optional[bool]]:
        """
        Return whether each antenna has had its status forced locally.

        :return: a list of booleans indicating the forcing status of
            each antenna. True means the antenna has been locally forced
            on. False means the antenna has been locally forced off.
            None means the antenna has not been locally forced.
        """
        return [
            self._smartbox_simulators[smartbox_id - 1].get_port_forcing(smartbox_port)
            for (smartbox_id, smartbox_port) in self._antenna_smartbox_ports
        ]

    def get_antenna_forcing(self: PasdBusSimulator, antenna_id: int) -> Optional[bool]:
        """
        Return the forcing status of a specified antenna.

        :param antenna_id: the id of the antenna for which the forcing
            status is required.

        :return: the forcing status of the antenna. True means the
            antenna is forced on. False means it is forced off. None
            means it is not forced.
        """
        (smartbox_id, smartbox_port) = self._antenna_smartbox_ports[antenna_id - 1]
        return self._smartbox_simulators[smartbox_id - 1].get_port_forcing(
            smartbox_port
        )

    def simulate_antenna_forcing(
        self: PasdBusSimulator, antenna_id: int, forcing: Optional[bool]
    ) -> Optional[bool]:
        """
        Simulate forcing an antenna on or off.

        :param antenna_id: id of the antenna to be forced
        :param forcing: the new forcing state of the antenna. True means
            the antenna is forced on. False means it is forced off. None
            means it is not forced.

        :return: whether successful, or None if there was nothing to do
        """
        (smartbox_id, smartbox_port) = self._antenna_smartbox_ports[antenna_id - 1]
        return self._smartbox_simulators[smartbox_id - 1].simulate_port_forcing(
            smartbox_port, forcing
        )

    def simulate_antenna_breaker_trip(
        self: PasdBusSimulator, antenna_id: int
    ) -> Optional[bool]:
        """
        Simulate an antenna breaker trip.

        :param antenna_id: the (one-based) number of the antenna for
            which a breaker trip is to be simulated.

        :return: whether successful, or None if there was nothing to do
        """
        (smartbox_id, smartbox_port) = self._antenna_smartbox_ports[antenna_id - 1]
        return self._smartbox_simulators[smartbox_id - 1].simulate_port_breaker_trip(
            smartbox_port
        )

    def reset_antenna_breaker(
        self: PasdBusSimulator, antenna_id: int
    ) -> Optional[bool]:
        """
        Reset a tripped antenna breaker.

        :param antenna_id: the (one-based) number of the antenna for
            which a breaker trip is to be reset.

        :return: Whether successful, or None if there was nothing to do
        """
        (smartbox_id, smartbox_port) = self._antenna_smartbox_ports[antenna_id - 1]
        return self._smartbox_simulators[smartbox_id - 1].reset_port_breaker(
            smartbox_port
        )

    @property
    def antennas_tripped(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each antenna has had its breaker tripped.

        :return: a list of booleans indicating whether each antenna has
            had its breaker tripped.
        """
        return [
            self._smartbox_simulators[smartbox_id - 1].is_port_breaker_tripped(
                smartbox_port
            )
            for (smartbox_id, smartbox_port) in self._antenna_smartbox_ports
        ]

    def turn_antenna_on(
        self: PasdBusSimulator,
        antenna_id: int,
        desired_on_if_offline: bool = True,
    ) -> Optional[bool]:
        """
        Turn on an antenna.

        :param antenna_id: the (one-based) number of the antenna to
            be turned on.
        :param desired_on_if_offline: whether the antenna should remain
            on if the control system goes offline.

        :return: Whether successful, or None if there was nothing to do
        """
        (smartbox_id, smartbox_port) = self._antenna_smartbox_ports[antenna_id - 1]

        # TODO: Better handling of desired_on_if_online
        if self.turn_smartbox_on(smartbox_id, desired_on_if_offline) is False:
            return False

        return self._smartbox_simulators[smartbox_id - 1].turn_port_on(
            smartbox_port, desired_on_if_offline
        )

    def turn_antenna_off(self: PasdBusSimulator, antenna_id: int) -> Optional[bool]:
        """
        Turn off an antenna.

        :param antenna_id: the (one-based) number of the antenna to
            be turned off.

        :return: Whether successful, or None if there was nothing to do
        """
        (smartbox_id, smartbox_port) = self._antenna_smartbox_ports[antenna_id - 1]
        result = self._smartbox_simulators[smartbox_id - 1].turn_port_off(smartbox_port)
        if result and not any(
            self._smartbox_simulators[smartbox_id - 1].ports_desired_power_online
        ):
            _ = self.turn_smartbox_off(smartbox_id)
        return result

    @property
    def antennas_power_sensed(self: PasdBusSimulator) -> list[bool]:
        """
        Return whether each antenna is currently powered on.

        :return: a list of booleans indicating whether each antenna is
            powered on.
        """
        return [
            self._smartbox_simulators[smartbox_id - 1].is_port_power_sensed(
                smartbox_port
            )
            for (smartbox_id, smartbox_port) in self._antenna_smartbox_ports
        ]

    @property
    def antennas_desired_power_online(self: PasdBusSimulator) -> list[bool]:
        """
        Return the desired power state of each antenna when it is online.

        :return: the desired power state of each antenna when it is
            online.
        """
        return [
            self._smartbox_simulators[smartbox_id - 1].get_port_desired_power_online(
                smartbox_port
            )
            for (smartbox_id, smartbox_port) in self._antenna_smartbox_ports
        ]

    @property
    def antennas_desired_power_offline(self: PasdBusSimulator) -> list[bool]:
        """
        Return the desired power state of each antenna when it is offline.

        :return: the desired power state of each antenna when it is
            offline.
        """
        return [
            self._smartbox_simulators[smartbox_id - 1].get_port_desired_power_offline(
                smartbox_port
            )
            for (smartbox_id, smartbox_port) in self._antenna_smartbox_ports
        ]

    @property
    def antenna_currents(self: PasdBusSimulator) -> list[float]:
        """
        Return the current at each antenna's power port, in amps.

        :return: a list of currents.
        """
        return [
            self._smartbox_simulators[smartbox_id - 1].get_port_current_draw(
                smartbox_port
            )
            for (smartbox_id, smartbox_port) in self._antenna_smartbox_ports
        ]

    def update_status(
        self: PasdBusSimulator,
    ) -> None:
        """
        Update the status of devices accessible through this bus.

        At present this does nothing except update a timestamp
        """
        self._fndh_simulator.update_status()
        for smartbox in self._smartbox_simulators:
            smartbox.update_status()
