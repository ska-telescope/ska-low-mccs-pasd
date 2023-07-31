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

    DEFAULT_LED_PATTERN: Final = "OFF"
    DEFAULT_STATUS: Final = "UNINITIALISED"
    DEFAULT_UPTIME: Final = 0
    DEFAULT_THRESHOLDS_PATH = "pasd_default_thresholds.yaml"

    def __init__(
        self: PasdHardwareSimulator,
        number_of_ports: int,
    ) -> None:
        """
        Initialise a new instance.

        :param number_of_ports: number of ports managed by this hardware
        """
        self._power_on_time = None
        self._ports = [_PasdPortSimulator() for _ in range(number_of_ports)]
        self._sensors_status: dict = {}
        self._status = self.DEFAULT_STATUS
        self._led_pattern = str(self.DEFAULT_LED_PATTERN)

    def _load_thresholds(
        self: PasdHardwareSimulator, file_path: str, device: str
    ) -> bool:
        """
        Load PaSD sensor thresholds from a file into this simulator.

        :param file_path: path to sensor thresholds YAML file
        :param device: device thresholds to load - fndh/smartbox
        :return: whether successful
        :raises yaml.YAMLError: if the config file cannot be parsed.
        """
        config_data = importlib.resources.read_text(
            "ska_low_mccs_pasd.pasd_bus",
            file_path,
        )

        assert config_data is not None  # for the type-checker

        try:
            loaded_data = yaml.safe_load(config_data)
        except yaml.YAMLError as exception:
            logger.error(
                f"PaSD hardware simulator could not load thresholds: {exception}."
            )
            raise

        try:
            sensor_thresholds = loaded_data[device]["default_thresholds"]
            for sensor, thresholds in sensor_thresholds.items():
                thresholds_list = [
                    thresholds.get("high_alarm", None),
                    thresholds.get("high_warning", None),
                    thresholds.get("low_warning", None),
                    thresholds.get("low_alarm", None),
                ]
                setattr(self, sensor + "_thresholds", Sensor())
                setattr(self, sensor + "_thresholds", thresholds_list)
        except KeyError as exception:
            logger.error(
                f"PaSD hardware simulator could not load thresholds: {exception}."
            )
        return True

    def _update_sensor_status(self: PasdHardwareSimulator, sensor_name: str) -> None:
        """
        Update the sensor status based on the thresholds.

        :param sensor_name: Base name string of the sensor's attributes
        """
        try:
            thresholds = getattr(self, sensor_name + "_thresholds")
            high_alarm = thresholds[0]
            high_warning = thresholds[1]
            low_warning = thresholds[2]
            low_alarm = thresholds[3]
            value_list = getattr(self, sensor_name)
            if not isinstance(value_list, list):
                value_list = [value_list]
            for i, value in enumerate(value_list, 1):
                if high_alarm is not None and value >= high_alarm:
                    self._sensors_status[sensor_name + str(i)] = "ALARM"
                elif low_alarm is not None and value <= low_alarm:
                    self._sensors_status[sensor_name + str(i)] = "ALARM"
                elif high_warning is not None and value >= high_warning:
                    self._sensors_status[sensor_name + str(i)] = "WARNING"
                elif low_warning is not None and value <= low_warning:
                    self._sensors_status[sensor_name + str(i)] = "WARNING"
                else:
                    self._sensors_status[sensor_name + str(i)] = "OK"
        except AttributeError:
            # TODO: log
            return

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
        return self._ports[port_number - 1].simulate_forcing(forcing)

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
    def uptime(self: PasdHardwareSimulator) -> int:
        """
        Return the uptime, as an integer.

        :return: the uptime.
        """
        if self._power_on_time is None:
            return self.DEFAULT_UPTIME
        return datetime.now().timestamp() - self._power_on_time.timestamp()

    @property
    def status(self: PasdHardwareSimulator) -> str:
        """
        Return the status of the FNDH/smartbox.

        :return: an overall status.
            "OK" means all sensors are within thresholds.
            "WARNING" means one or more sensors are over/under warning thresholds.
            "ALARM" means one or more sensors are over/under alarm thresholds.
            "RECOVERY" means all sensors are back within alarm thresholds after
            being in alarm state previously. "OK" status must be requested.
        """
        if self._status == "ALARM" and "ALARM" not in self._sensors_status.values():
            self._status = "RECOVERY"
        elif self._status is not self.DEFAULT_STATUS:
            if "ALARM" in self._sensors_status.values():
                self._status = "ALARM"
            elif self._status != "RECOVERY":
                if "WARNING" in self._sensors_status.values():
                    self._status = "WARNING"
                else:
                    self._status = "OK"
        return self._status

    def set_status(self: PasdHardwareSimulator, request: str) -> bool | None:
        """
        Set the smartbox status.

        :param request: the only valid request is "OK", otherwise do nothing.
        :return: whether successful, or None if there was nothing to do.
        """
        # Temporarily set status to undefined and then get the status
        if request == "OK":
            self._status = "UNDEFINED"
            self._status = self.status
            if self._status == "OK":
                return True
            logger.warning(
                f"PaSD Bus simulator status was not set to OK, status is {self._status}"
            )
            return False
        return None

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
    """
    Descriptor for sensor attributes of a FNDH/Smartbox.

    This descriptor allows for handling sensor attributes and their status
    within the context of a FNDH/Smartbox simulator class.
    """

    # pylint: disable=attribute-defined-outside-init

    def __set_name__(self: Sensor, owner: PasdHardwareSimulator, name: str) -> None:
        """
        Set the name of the sensor attribute.

        :param owner: The owner object.
        :param name: The name of the object created in the instance.
        """
        self.name = name

    def __get__(
        self: Sensor, obj: PasdHardwareSimulator, objtype: type
    ) -> None | int | list[int]:
        """
        Get the value of the sensor attribute from the instance.

        :param obj: The instance of the class where the descriptor is being used.
        :param objtype: The type of the instance (usually the class).
        :returns: Sensor value stored in the instance's __dict__.
        """
        return obj.__dict__.get(self.name)

    def __set__(
        self: Sensor, obj: PasdHardwareSimulator, value: int | list[int]
    ) -> None:
        """
        Set the value of the sensor attribute for the instance.

        :param obj: The instance of the class where the descriptor is being used.
        :param value: The value to be set for the sensor attribute.
        """
        if isinstance(value, list):
            obj.__dict__[self.name] = [int(val) for val in value]
        else:
            obj.__dict__[self.name] = int(value)
        obj._update_sensor_status(f"{self.name}")


class FndhSimulator(PasdHardwareSimulator):
    """
    A simple simulator of a Field Node Distribution Hub.

    This FNDH simulator will never be used as a standalone simulator. It
    will only be used as a component of a PaSD bus simulator.
    """

    # pylint: disable=too-many-instance-attributes

    NUMBER_OF_PORTS: Final = 28

    CPU_ID: Final = 22
    CHIP_ID: Final = 23
    MODBUS_REGISTER_MAP_REVISION: Final = 20
    PCB_REVISION: Final = 21
    SYS_ADDRESS: Final = 101

    DEFAULT_FIRMWARE_VERSION: Final = "1.2.3-fake"
    DEFAULT_PSU48V_VOLTAGES: Final = [4790, 4810]
    DEFAULT_PSU48V_CURRENT: Final = 1510
    DEFAULT_PSU48V_TEMPERATURES: Final = [4120, 4290]
    DEFAULT_PANEL_TEMPERATURE: Final = 3720
    DEFAULT_FNCB_TEMPERATURE: Final = 4150
    DEFAULT_FNCB_HUMIDITY: Final = 5020
    DEFAULT_COMMS_GATEWAY_TEMPERATURE: Final = 3930
    DEFAULT_POWER_MODULE_TEMPERATURE: Final = 4580
    DEFAULT_OUTSIDE_TEMPERATURE: Final = 3250
    DEFAULT_INTERNAL_AMBIENT_TEMPERATURE: Final = 3600

    # Instantiate sensor data descriptors
    psu48v_voltages = Sensor()
    psu48v_current = Sensor()
    psu48v_temperatures = Sensor()
    panel_temperature = Sensor()  # Not implemented in hardware?
    fncb_temperature = Sensor()
    fncb_humidity = Sensor()
    comms_gateway_temperature = Sensor()
    power_module_temperature = Sensor()
    outside_temperature = Sensor()
    internal_ambient_temperature = Sensor()

    def __init__(self: FndhSimulator) -> None:
        """Initialise a new instance."""
        super().__init__(self.NUMBER_OF_PORTS)
        # self._power_on_time = datetime.now()
        # Sensors
        self._load_thresholds(self.DEFAULT_THRESHOLDS_PATH, "fndh")
        self.psu48v_voltages = self.DEFAULT_PSU48V_VOLTAGES
        self.psu48v_current = self.DEFAULT_PSU48V_CURRENT
        self.psu48v_temperatures = self.DEFAULT_PSU48V_TEMPERATURES
        self.panel_temperature = self.DEFAULT_PANEL_TEMPERATURE
        self.fncb_temperature = self.DEFAULT_FNCB_TEMPERATURE
        self.fncb_humidity = self.DEFAULT_FNCB_HUMIDITY
        self.comms_gateway_temperature = self.DEFAULT_COMMS_GATEWAY_TEMPERATURE
        self.power_module_temperature = self.DEFAULT_POWER_MODULE_TEMPERATURE
        self.outside_temperature = self.DEFAULT_OUTSIDE_TEMPERATURE
        self.internal_ambient_temperature = self.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE

    @property
    def sys_address(self: FndhSimulator) -> int:
        """
        Return the system address.

        :return: the system address.
        """
        return self.SYS_ADDRESS

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


class SmartboxSimulator(PasdHardwareSimulator):
    """A simulator for a PaSD smartbox."""

    # pylint: disable=too-many-instance-attributes

    NUMBER_OF_PORTS: Final = 12

    MODBUS_REGISTER_MAP_REVISION: Final = 20
    PCB_REVISION: Final = 21
    CPU_ID: Final = 24
    CHIP_ID: Final = 25

    DEFAULT_SYS_ADDRESS: Final = 1
    DEFAULT_FIRMWARE_VERSION = "0.1.2-fake"
    # Address
    DEFAULT_INPUT_VOLTAGE: Final = 4800
    DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE: Final = 480
    DEFAULT_POWER_SUPPLY_TEMPERATURE: Final = 4210
    DEFAULT_PCB_TEMPERATURE: Final = 3860  # Not implemented in hardware?
    DEFAULT_FEM_AMBIENT_TEMPERATURE: Final = 4010
    DEFAULT_FEM_CASE_TEMPERATURES: Final = [4440, 4460]
    DEFAULT_FEM_HEATSINK_TEMPERATURES: Final = [4280, 4250]
    DEFAULT_PORT_CURRENT_DRAW: Final = 421

    # Instantiate sensor data descriptors
    input_voltage = Sensor()
    power_supply_output_voltage = Sensor()
    power_supply_temperature = Sensor()
    pcb_temperature = Sensor()
    fem_ambient_temperature = Sensor()
    fem_case_temperatures = Sensor()
    fem_heatsink_temperatures = Sensor()

    def __init__(self: SmartboxSimulator) -> None:
        """Initialise a new instance."""
        super().__init__(self.NUMBER_OF_PORTS)
        self._port_breaker_tripped = [False] * self.NUMBER_OF_PORTS
        self._sys_address = self.DEFAULT_SYS_ADDRESS
        # Sensors
        self._load_thresholds(self.DEFAULT_THRESHOLDS_PATH, "smartbox")
        self.input_voltage = self.DEFAULT_INPUT_VOLTAGE
        self.power_supply_output_voltage = self.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        self.power_supply_temperature = self.DEFAULT_POWER_SUPPLY_TEMPERATURE
        self.pcb_temperature = self.DEFAULT_PCB_TEMPERATURE
        self.fem_ambient_temperature = self.DEFAULT_FEM_AMBIENT_TEMPERATURE
        self.fem_case_temperatures = self.DEFAULT_FEM_CASE_TEMPERATURES
        self.fem_heatsink_temperatures = self.DEFAULT_FEM_HEATSINK_TEMPERATURES

    @property
    def sys_address(self: SmartboxSimulator) -> int:
        """
        Return the system address.

        :return: the system address.
        """
        return self._sys_address

    def set_sys_address(self: SmartboxSimulator, address: int) -> bool | None:
        """
        Set the system address.

        :param address: the system address to be set - must be in range from 1 to 99.

        :return: whether successful, or None if there was nothing to do.
        """
        if 1 <= address <= 99:
            if self._sys_address == address:
                return None
            self._sys_address = address
            return True
        logger.warning(
            "PaSD Bus simulator smartbox address must be in range from 1 to 99."
        )
        return False

    @property
    def ports_current_draw(
        self: SmartboxSimulator,
    ) -> list[int]:
        """
        Return the current being drawn from each smartbox port.

        :return: the current being drawn from each smartbox port.
        """
        return [
            self.DEFAULT_PORT_CURRENT_DRAW if connected else 0
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
