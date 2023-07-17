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

import importlib.resources
import logging
from datetime import datetime
from typing import Final, Optional, Sequence
import yaml
from .pasd_bus_conversions import FndhStatusMap, SmartBoxStatusMap

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

    DEFAULT_LED_PATTERN = "OFF"
    DEFAULT_STATUS = "UNINITIALISED"

    # Temporary
    DEFAULT_UPTIME: Final = 1000

    def __init__(
        self: PasdHardwareSimulator,
        number_of_ports: int,
    ) -> None:
        """
        Initialise a new instance.

        :param number_of_ports: number of ports managed by this hardware
        """
        self._ports = [_PasdPortSimulator() for _ in range(number_of_ports)]
        self._led_pattern = str(self.DEFAULT_LED_PATTERN)
        self._status = self.DEFAULT_STATUS
        self._power_on_time = None

    def _load_thresholds(self: PasdHardwareSimulator, file_path: str) -> bool:
        """
        Load PaSD sensor thresholds from a file into this simulator.

        :param file_path: path to sensor thresholds YAML file

        :return: whether successful

        :raises yaml.YAMLError: if the config file cannot be parsed.
        """
        config_data = importlib.resources.read_text(
            "ska_low_mccs_pasd.pasd_bus",
            file_path,
        )

        assert config_data is not None  # for the type-checker

        try:
            sensor_thresholds = yaml.safe_load(config_data)
        except yaml.YAMLError as exception:
            logger.error(
                f"PaSD hardware simulator could not load thresholds: {exception}."
            )
            raise

        for entry in sensor_thresholds["thresholds"]:
            name = list(entry)[0]
            thresholds = entry[name][0]
            try:
                sensor = getattr(self, name)
                setattr(sensor, "high_alarm", thresholds.get("high_alarm"))
                setattr(sensor, "high_warning", thresholds.get("high_warning"))
                setattr(sensor, "low_warning", thresholds.get("low_warning"))
                setattr(sensor, "low_alarm", thresholds.get("low_alarm"))
            except AttributeError:
                pass
        return True

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
        for port, is_connected in zip(self._ports, ports_connected):
            port.connected = is_connected

    @property
    def ports_connected(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return whether each port is connected.

        :return: whether each port is connected.
        """
        return [port.connected for port in self._ports]

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
        turned_on = self._ports[port_number - 1].simulate_forcing(forcing)
        if turned_on:
            self._power_on_time = datetime.now()
        return turned_on

    @property
    def port_forcings(self: PasdHardwareSimulator) -> list[str]:
        """
        Return the forcing statuses of all ports.

        :return: the forcing statuses of each port.
            "ON" means the port has been forced on.
            "OFF" means it has been forced off.
            "NONE" means it has not been forced.
        """
        forcing_map = {
            True: "ON",
            False: "OFF",
            None: "NONE",
        }
        return [forcing_map[port.forcing] for port in self._ports]

    @property
    def port_breakers_tripped(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return whether each port has had its breaker tripped.

        :return: whether each port has had its breaker tripped
        """
        return [port.breaker_tripped for port in self._ports]

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
        turned_on = self._ports[port_number - 1].turn_on(
            stay_on_when_offline=stay_on_when_offline
        )
        if turned_on:
            self._power_on_time = datetime.now()
        return turned_on

    def turn_port_off(
        self: PasdHardwareSimulator,
        port_number: int,
    ) -> Optional[bool]:
        """
        Turn off a specified port.

        :param port_number: number of the port to turn off

        :return: whether successful, or None if there was nothing to do
        """
        turned_off = self._ports[port_number - 1].turn_off()
        if turned_off:
            self._power_on_time = None
        return turned_off

    @property
    def ports_desired_power_when_online(
        self: PasdHardwareSimulator,
    ) -> list[bool]:
        """
        Return the desired power of each port when the device is online.

        That is, for each port, should it be powered if the control
        system is online?

        :return: the desired power of each port when the device is
            online
        """
        return [port.desired_power_when_online for port in self._ports]

    @property
    def ports_desired_power_when_offline(
        self: PasdHardwareSimulator,
    ) -> list[bool]:
        """
        Return the desired power of each port when the device is offline.

        That is, for each port, should it remain powered if the control
        system goes offline?

        :return: the desired power of each port when the device is
            offline
        """
        return [port.desired_power_when_offline for port in self._ports]

    @property
    def ports_power_sensed(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return the actual sensed power state of each port.

        :return: the actual sensed power state of each port.
        """
        return [port.power_sensed for port in self._ports]

    @property
    def led_pattern(self: PasdHardwareSimulator) -> str:
        """
        Return the LED pattern name.

        :return: the name of the LED pattern.
        """
        return self._led_pattern

    def set_led_pattern(
        self: PasdHardwareSimulator,
        led_pattern: str,
    ) -> bool | None:
        """
        Set the LED pattern.

        :param led_pattern: the LED pattern to be set.
            Options are "OFF" and "SERVICE".

        :return: whether successful, or None if there was nothing to do.
        """
        if self._led_pattern == led_pattern:
            return None
        self._led_pattern = led_pattern
        return True


class Sensor:
    """Single sensor's attributes of a FNDH/Smartbox."""

    def __init__(self: Sensor, value: float) -> None:
        """
        Initialise a new instance.

        :param value: value to simulate
        """
        self.value = value
        self.status = "UNINITIALISED"
        self.high_alarm = None
        self.high_warning = None
        self.low_warning = None
        self.low_alarm = None

    def __getattr__(self: Sensor, name: str):
        """
        Get attribute.

        :param name: name
        :return: value
        :raises AttributeError: if it does not exist in object dict
        """
        try:
            return self.__dict__[f"_{name}"]
        except KeyError as exc:
            raise AttributeError from exc

    def __setattr__(self: Sensor, name: str, value: float):
        """
        Set attribute.

        :param name: name
        :param value: value
        """
        self.__dict__[f"_{name}"] = value
        if name != "status":
            self._update_status()

    def _update_status(self: Sensor) -> None:
        """Update the sensor status based on the thresholds."""
        try:
            if self.high_alarm is not None and self.value > self.high_alarm:
                self.status = "ALARM"
            elif self.low_alarm is not None and self.value < self.low_alarm:
                self.status = "ALARM"
            elif self.high_warning is not None and self.value > self.high_warning:
                self.status = "WARNING"
            elif self.low_warning is not None and self.value < self.low_warning:
                self.status = "WARNING"
            else:
                self.status = "OK"
        except AttributeError:
            return


class FndhSimulator(PasdHardwareSimulator):
    """
    A simple simulator of a Field Node Distribution Hub.

    This FNDH simulator will never be used as a standalone simulator. It
    will only be used as a component of a PaSD bus simulator.
    """

    NUMBER_OF_PORTS: Final = 28

    CPU_ID: Final = 22
    CHIP_ID: Final = 23
    MODBUS_REGISTER_MAP_REVISION: Final = 20
    PCB_REVISION: Final = 21

    DEFAULT_FIRMWARE_VERSION: Final = "1.2.3-fake"
    DEFAULT_PSU48V_VOLTAGES: Final = [47.9, 48.1]
    DEFAULT_PSU5V_VOLTAGE: Final = 5.1
    DEFAULT_PSU48V_CURRENT: Final = 20.1
    DEFAULT_PSU48V_TEMPERATURE: Final = 41.2
    DEFAULT_PSU5V_TEMPERATURE: Final = 41.3
    DEFAULT_PCB_TEMPERATURE: Final = 41.4
    DEFAULT_OUTSIDE_TEMPERATURE: Final = 41.5

    # Thresholds with over- and under-value alarm and warning
    THRESHOLDS_PATH = "simulator_fndh_thresholds.yaml"

    def __init__(self: FndhSimulator) -> None:
        """Initialise a new instance."""
        super().__init__(self.NUMBER_OF_PORTS)
        # self._load_thresholds(self.THRESHOLDS_PATH)

    @property
    def sys_address(self: FndhSimulator) -> int:
        """
        Return the sys address.

        :return: the system address.
        """
        return self.SYS_ADDRESS

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
    def modbus_register_map_revision(self: FndhSimulator) -> int:
        """
        Return the Modbus register map revision number.

        :return: the Modbus register map revision number.
        """
        return self.MODBUS_REGISTER_MAP_REVISION

    @property
    def pcb_revision(self: FndhSimulator) -> int:
        """
        Return the PCB revision number.

        :return: the PCB revision number.
        """
        return self.PCB_REVISION

    @property
    def cpu_id(self: FndhSimulator) -> int:
        """
        Return the ID of the CPU.

        :return: the ID of the CPU.
        """
        return self.CPU_ID

    @property
    def chip_id(self: FndhSimulator) -> int:
        """
        Return the ID of the chip.

        :return: the ID of the chip.
        """
        return self.CHIP_ID

    @property
    def firmware_version(self: FndhSimulator) -> str:
        """
        Return the firmware version.

        :return: the firmware version.
        """
        return self.DEFAULT_FIRMWARE_VERSION

    @property
    def uptime(self: FndhSimulator) -> int:
        """
        Return the uptime, as an integer.

        :return: the uptime.
        """
        return self.DEFAULT_UPTIME

    @property
    def status(self: FndhSimulator) -> str:
        """
        Return the FNDH status string.

        :return: the FNDH status string.
        """
        return self.DEFAULT_STATUS


class SmartboxSimulator(PasdHardwareSimulator):
    """A simulator for a PaSD smartbox."""

    NUMBER_OF_PORTS: Final = 12

    MODBUS_REGISTER_MAP_REVISION: Final = 20
    PCB_REVISION: Final = 21
    CPU_ID: Final = 24
    CHIP_ID: Final = 25

    DEFAULT_FIRMWARE_VERSION = "0.1.2-fake"
    # Address
    DEFAULT_INPUT_VOLTAGE: Final = 48.0
    DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE: Final = 5.0
    DEFAULT_POWER_SUPPLY_TEMPERATURE: Final = 42.1
    DEFAULT_PCB_TEMPERATURE: Final = 38.6  # Not currently implemented in hardware
    DEFAULT_OUTSIDE_TEMPERATURE: Final = 44.4

    DEFAULT_PORT_CURRENT_DRAW: Final = 20.5

    # Thresholds with over- and under-value alarm and warning
    THRESHOLDS_PATH = "simulator_smartbox_thresholds.yaml"

    def __init__(self: SmartboxSimulator) -> None:
        """Initialise a new instance."""
        super().__init__(self.NUMBER_OF_PORTS)
        self._port_breaker_tripped = [False] * self.NUMBER_OF_PORTS
        # Sensors
        self.input_voltage = Sensor(self.DEFAULT_INPUT_VOLTAGE)
        self.power_supply_output_voltage = Sensor(
            self.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        )
        self.power_supply_temperature = Sensor(self.DEFAULT_POWER_SUPPLY_TEMPERATURE)
        self.pcb_temperature = Sensor(self.DEFAULT_PCB_TEMPERATURE)
        self.outside_temperature = Sensor(self.DEFAULT_OUTSIDE_TEMPERATURE)
        self._load_thresholds(self.THRESHOLDS_PATH)

    @property
    def status(self: SmartboxSimulator) -> str:
        """
        Return the status of the smartbox.

        :return: a string status.
        """
        # Status is not updated until attribute is initialised
        if self._status is not SmartBoxStatusMap.UNINITIALISED.name:
            # Gather all sensors' statuses in a list
            sensors_status = [
                self.input_voltage.status,
                self.power_supply_output_voltage.status,
                self.power_supply_temperature.status,
                self.pcb_temperature.status,
                self.outside_temperature.status,
            ]
            # Set the smartbox status to the highest priority status of any sensor
            if SmartBoxStatusMap.RECOVERY.name in sensors_status:
                self._status = SmartBoxStatusMap.RECOVERY.name
            elif SmartBoxStatusMap.ALARM.name in sensors_status:
                self._status = SmartBoxStatusMap.ALARM.name
            elif SmartBoxStatusMap.WARNING.name in sensors_status:
                self._status = SmartBoxStatusMap.WARNING.name
            else:
                self._status = SmartBoxStatusMap.OK.name
        return self._status

    @status.setter
    def status(self: SmartboxSimulator, value: any) -> None:
        """
        Initiliaze the smartbox status.

        :param value: ignored
        """
        # Temporarily set status to undefined and read the status
        self._status = SmartBoxStatusMap.UNDEFINED.name
        self._status = self.status

    @property
    def ports_current_draw(
        self: SmartboxSimulator,
    ) -> list[float]:
        """
        Return the current being drawn from each smartbox port.

        :return: the current being drawn from each smartbox port.
        """
        return [
            self.DEFAULT_PORT_CURRENT_DRAW if connected else 0.0
            for connected in self.ports_connected
        ]

    @property
    def modbus_register_map_revision(self: SmartboxSimulator) -> int:
        """
        Return the Modbus register map revision number.

        :return: the Modbus register map revision number.
        """
        return self.MODBUS_REGISTER_MAP_REVISION

    @property
    def pcb_revision(self: SmartboxSimulator) -> int:
        """
        Return the PCB revision number.

        :return: the PCB revision number.
        """
        return self.PCB_REVISION

    @property
    def cpu_id(self: SmartboxSimulator) -> int:
        """
        Return the CPU ID.

        :return: the CPU ID.
        """
        return self.CPU_ID

    @property
    def chip_id(self: SmartboxSimulator) -> int:
        """
        Return the chip ID.

        :return: the chip ID.
        """
        return self.CHIP_ID

    @property
    def firmware_version(self: SmartboxSimulator) -> str:
        """
        Return the firmware version.

        :return: the firmware version.
        """
        return self.DEFAULT_FIRMWARE_VERSION

    @property
    def uptime(self: SmartboxSimulator) -> int:
        """
        Return the uptime in seconds.

        :return: the uptime
        """
        return self.DEFAULT_UPTIME


class PasdBusSimulator:
    """
    A stub class that provides similar functionality to a PaSD bus.

    Many attributes are stubbed out:

    * The antennas are always online.
    * Voltages, currents and temperatures never change.
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

        logger.info(
            f"Logger level set to {logging.getLevelName(logger.getEffectiveLevel())}."
        )

        self._fndh_simulator = FndhSimulator()
        logger.info(f"Initialised FNDH simulator for station {station_id}.")
        self._smartbox_simulators = [
            SmartboxSimulator() for _ in range(self.NUMBER_OF_SMARTBOXES)
        ]
        logger.info(
            f"Initialised {self.NUMBER_OF_SMARTBOXES} Smartbox"
            f" simulators for station {station_id}."
        )

        self._smartbox_fndh_ports: list[int] = [0] * self.NUMBER_OF_SMARTBOXES

        self._load_config()
        logger.info(
            f"PaSD configuration data loaded into simulator for station {station_id}."
        )
        logger.info(f"Initialised PaSD bus simulator for station {station_id}.")

    def get_fndh(self: PasdBusSimulator) -> FndhSimulator:
        """
        Return the FNDH simulator.

        :return: the FNDH simulator.
        """
        return self._fndh_simulator

    def get_smartboxes(self: PasdBusSimulator) -> Sequence[SmartboxSimulator]:
        """
        Return a sequence of smartboxes.

        :return: a sequence of smartboxes.
        """
        return list(self._smartbox_simulators)

    def _load_config(self: PasdBusSimulator) -> bool:
        """
        Load PaSD configuration data from a file into this simulator.

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
            for _ in range(self.NUMBER_OF_SMARTBOXES)
        ]
        for antenna_config in my_config["antennas"]:
            smartbox_id = antenna_config["smartbox_id"]
            smartbox_port = antenna_config["smartbox_port"]
            smartbox_ports_connected[smartbox_id - 1][smartbox_port - 1] = True

        for smartbox_index, ports_connected in enumerate(smartbox_ports_connected):
            self._smartbox_simulators[smartbox_index].configure(ports_connected)

        return True
