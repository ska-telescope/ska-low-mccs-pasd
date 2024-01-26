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
the PaSD bus using MODBUS-over-TCP.

The Pasd bus simulator class is provided below. To help manage
complexity, it is composed of a separate FNDH simulator and a number of
smartbox simulators, which in turn make use of port simulators. Only the
PasdBusSimulator class should be considered public.
"""
# pylint: disable=too-many-lines

from __future__ import annotations

import importlib.resources
import logging
from abc import ABC
from datetime import datetime
from typing import Callable, Final, Optional, Sequence

import yaml

from ska_low_mccs_pasd.pasd_data import PasdData

from .pasd_bus_conversions import (
    FndhAlarmFlags,
    FndhStatusMap,
    LedServiceMap,
    LedStatusMap,
    PasdConversionUtility,
    SmartboxAlarmFlags,
    SmartboxStatusMap,
)
from .pasd_bus_modbus_api import FNDH_MODBUS_ADDRESS
from .pasd_bus_register_map import DesiredPowerEnum

logger = logging.getLogger()


class _PasdPortSimulator(ABC):
    """
    A private abstract base class of a single FNDH/smartbox simulated port.

    It supports:

    * Local forcing: a technician in the field can manually force the
      power state of a port. If forced off, a port will not deliver
      power regardless of other settings.

    * Online and offline delivery of power. When we tell a port to turn
      on, we can also indicate whether we want it to remain on if the
      control system goes offline. This simulator remembers that
      information, but there's no way to tell the simulator that the
      control system is offline because the whole point of these
      simulators is to simulate the PaSD from the point of view of the
      control system. By definition, the control system cannot observe
      the behaviour of PaSD when the control system is offline, so there
      is no need to implement this behaviour.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(
        self: _PasdPortSimulator,
        number: int | None = None,
    ):
        """
        Initialise a new instance.

        :param number: optional port number of FNDH/smartbox.
        """
        self._number = number
        # Internal to simulator port states
        self._connected: bool = False
        self._on: bool = False
        self._over_current: bool = False
        # Simulated PDoC/FEM state registers
        self._enabled: bool = False
        self._online: bool = True  # Redundant, as desribed above
        self._desired_on_when_online: DesiredPowerEnum = DesiredPowerEnum.DEFAULT
        self._desired_on_when_offline: DesiredPowerEnum = (
            DesiredPowerEnum.DEFAULT
        )  # Redundant, as desribed above
        self._forcing: Optional[bool] = None

    def _update_port_power(self: _PasdPortSimulator) -> None:
        """
        Update the port power.

        Turn the port ON or OFF depending on the desired power, forcing and
        over current states.
        """
        if self._forcing is False:
            self._on = False
        elif (self._forcing or self._enabled) and not self._over_current:
            if (
                self._desired_on_when_online == DesiredPowerEnum.ON and self._online
            ) or (
                self._desired_on_when_offline == DesiredPowerEnum.ON
                and not self._online
            ):
                self._on = True
            else:
                self._on = False
        elif not self._enabled or self._over_current:  # forcing has priority
            self._on = False

    @property
    def breaker_tripped(self: _PasdPortSimulator) -> bool:
        """
        Return whether the port breaker has been tripped.

        :raises NotImplementedError: raised if not implemented in subclass
        """
        raise NotImplementedError

    def simulate_over_current(
        self: _PasdPortSimulator, state: bool = True
    ) -> Optional[bool]:
        """
        Simulate port over-current condition.

        :param state: of simulating condition.
        :return: whether successful, or None if there was nothing to do.
        """
        if self._over_current == state:
            return None
        self._over_current = state
        self._update_port_power()
        return True

    def simulate_stuck_on(
        self: _PasdPortSimulator, state: bool = True
    ) -> Optional[bool]:
        """
        Simulate port stuck on fault condition.

        :param state: of simulating condition.
        :raises NotImplementedError: raised if not implemented in subclass
        """
        raise NotImplementedError

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

    @property
    def enabled(self: _PasdPortSimulator) -> bool:
        """
        Return whether this port is enabled.

        :return: whether this port is enabled.
        """
        return self._enabled

    @enabled.setter
    def enabled(self: _PasdPortSimulator, is_enabled: bool) -> None:
        """
        Set whether this port is enabled.

        :param is_enabled: whether this port is enabled.
        """
        self._enabled = is_enabled
        self._update_port_power()

    def desired_on(
        self: _PasdPortSimulator, stay_on_when_offline: bool = True
    ) -> Optional[bool]:
        """
        Turn the port on.

        :param stay_on_when_offline: whether the port should stay on if
            the control system goes offline.

        :return: whether successful, or None if there was nothing to do.
        """
        if (
            self._desired_on_when_online == DesiredPowerEnum.ON
            and (self._desired_on_when_offline == DesiredPowerEnum.ON)
            == stay_on_when_offline
        ):
            return None

        self._desired_on_when_online = DesiredPowerEnum.ON
        self._desired_on_when_offline = (
            DesiredPowerEnum.ON if stay_on_when_offline else DesiredPowerEnum.OFF
        )
        self._update_port_power()
        return True

    def desired_off(self: _PasdPortSimulator) -> Optional[bool]:
        """
        Turn the port off.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._desired_on_when_online == DesiredPowerEnum.OFF:
            return None

        self._desired_on_when_online = DesiredPowerEnum.OFF
        self._desired_on_when_offline = DesiredPowerEnum.OFF
        self._update_port_power()
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
        self._update_port_power()
        return True

    @property
    def desired_power_when_online(self: _PasdPortSimulator) -> DesiredPowerEnum:
        """
        Return the desired power mode of the port when the control system is online.

        :return: the desired power mode of the port when the control
            system is online.
        """
        return self._desired_on_when_online

    @desired_power_when_online.setter
    def desired_power_when_online(
        self: _PasdPortSimulator, power_on: DesiredPowerEnum
    ) -> None:
        """
        Set the desired power mode of the port when the control system is online.

        :param power_on: whether power is on
        """
        self._desired_on_when_online = power_on

    @property
    def desired_power_when_offline(self: _PasdPortSimulator) -> DesiredPowerEnum:
        """
        Return the desired power mode of the port when the control system is offline.

        :return: the desired power mode of the port when the control
            system is offline.
        """
        return self._desired_on_when_offline

    @desired_power_when_offline.setter
    def desired_power_when_offline(
        self: _PasdPortSimulator, power_on: DesiredPowerEnum
    ) -> None:
        """
        Set the desired power mode of the port when the control system is offline.

        :param power_on: whether power is on
        """
        self._desired_on_when_offline = power_on

    @property
    def power_sensed(self: _PasdPortSimulator) -> bool:
        """
        Return whether power is sensed on the port.

        :return: whether power is sensed on the port.
        """
        return self._on


class _FndhPortSimulator(_PasdPortSimulator):
    """
    A private class that manages a single simulated port of a FNDH.

    It adds:

    * Update port power: Controls the state of a FNDH simulator port, with the optional
      capability of instantiating or deleting the attached smartbox simulator in the
      top public PasdBusSimulator instance when the port is turned on or off.
    """

    def __init__(
        self: _FndhPortSimulator,
        number: int | None = None,
        instantiate_smartbox: Callable[[int], Optional[bool]] | None = None,
        delete_smartbox: Callable[[int], Optional[bool]] | None = None,
    ):
        super().__init__(number)
        self._instantiate_smartbox = instantiate_smartbox
        self._delete_smartbox = delete_smartbox
        self._stuck_on = False

    def _update_port_power(self: _FndhPortSimulator) -> None:
        """
        Update the port power.

        Turn the port ON or OFF depending on the desired power, forcing and
        over current states.
        """
        previous = self._on
        super()._update_port_power()
        if self._stuck_on:
            self._on = True
        # Instantiate or delete smartbox if port state has changed
        if (
            previous != self._on
            and self._instantiate_smartbox is not None
            and self._delete_smartbox is not None
            and self._number is not None
        ):
            if self._on:
                self._instantiate_smartbox(self._number)
            else:
                self._delete_smartbox(self._number)

    def simulate_stuck_on(
        self: _FndhPortSimulator, state: bool = True
    ) -> Optional[bool]:
        """
        Simulate port stuck on fault condition.

        :param state: of simulating condition.
        :return: whether successful, or None if there was nothing to do.
        """
        if self._stuck_on == state:
            return None
        self._stuck_on = state
        self._update_port_power()
        return True


class _SmartboxPortSimulator(_PasdPortSimulator):
    """
    A private class that manages a single simulated port of a Smartbox.

    It adds:

    * Update port power: Controls the state of a Smartbox simulator port.

    * Breaker tripping: In the real hardware, a port breaker might trip,
      for example as a result of an overcurrent condition. This
      simulator provides for simulating a breaker trip. Once tripped,
      the port will not deliver any power until the breaker has been
      reset.
    """

    def __init__(
        self: _SmartboxPortSimulator,
        number: int | None = None,
    ):
        super().__init__(number)

    @property
    def breaker_tripped(self: _SmartboxPortSimulator) -> bool:
        """
        Return whether the port breaker has been tripped.

        :return: whether the breaker has been tripped
        """
        return self._over_current


class PasdHardwareSimulator:
    """
    A class that captures commonality between FNDH and smartbox simulators.

    Both have a status that must be initialized and manage a set of ports -
    which can be switched on and off, locally forced, etc.
    """

    # pylint: disable=too-many-instance-attributes

    DEFAULT_LED_PATTERN: int = LedServiceMap.OFF | LedStatusMap.YELLOWFAST
    DEFAULT_STATUS: FndhStatusMap | SmartboxStatusMap = FndhStatusMap.UNINITIALISED
    DEFAULT_UPTIME: Final = [0, 1]
    DEFAULT_FLAGS: int = 0x0
    DEFAULT_THRESHOLDS_PATH = "pasd_default_thresholds.yaml"

    ALARM_MAPPING: dict[str, FndhAlarmFlags | SmartboxAlarmFlags] = {}

    def __init__(
        self: PasdHardwareSimulator,
        ports: Sequence[_FndhPortSimulator | _SmartboxPortSimulator],
        time_multiplier: int,
    ) -> None:
        """
        Initialise a new instance.

        :param ports: instantiated ports for the simulator.
        :param time_multiplier: to differentiate uptime in test context without delays.
        """
        self._ports = ports
        self._boot_on_time: datetime | None = datetime.now()
        self._time_multiplier: int = time_multiplier
        self._sensors_status: dict = {}
        self._warning_flags: int = self.DEFAULT_FLAGS
        self._alarm_flags: int = self.DEFAULT_FLAGS
        self._status: int = self.DEFAULT_STATUS
        self._service_led: int = LedServiceMap.OFF
        self._status_led: int = LedStatusMap.YELLOWFAST

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
                setattr(self, sensor + "_thresholds", thresholds_list)
        except KeyError as exception:
            logger.error(
                f"PaSD hardware simulator missing thresholds for {sensor}: {exception}."
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
        except TypeError:
            logger.error(
                f"PaSD bus simulator: {sensor_name} has no thresholds defined!"
            )
            return
        sensor_value = getattr(self, sensor_name)
        # Return if default value has not been set yet in instance's __init__()
        if sensor_value is None:
            return

        def _check_thresholds_and_set_status(sensor: str, value: int) -> None:
            if value >= high_alarm or value <= low_alarm:
                self._set_sensor_alarm(sensor)
            elif value >= high_warning or value <= low_warning:
                self._set_sensor_warning(sensor)
            else:
                self._sensors_status[sensor] = "OK"

        # Check single sensor value or
        if not isinstance(sensor_value, list):
            _check_thresholds_and_set_status(sensor_name, sensor_value)
            return
        # loop through multiple sensor values
        for i, value in enumerate(sensor_value, 1):
            numbered_name = sensor_name[:-1] + "_" + str(i)
            _check_thresholds_and_set_status(numbered_name, value)

    def _set_sensor_alarm(self: PasdHardwareSimulator, sensor_name: str) -> None:
        """
        Set alarm flag and status of sensor.

        :param sensor_name: to use as the dict key and flag description.
        """
        self._sensors_status[sensor_name] = "ALARM"
        self._alarm_flags ^= self.ALARM_MAPPING[sensor_name].value

    def _set_sensor_warning(self: PasdHardwareSimulator, sensor_name: str) -> None:
        """
        Set warning flag and status of sensor.

        :param sensor_name: to use as the dict key and flag description.
        """
        self._sensors_status[sensor_name] = "WARNING"
        self._warning_flags ^= self.ALARM_MAPPING[sensor_name].value

    def _update_system_status(
        self: PasdHardwareSimulator, request_ok: bool = False
    ) -> None:
        """
        Update the system status.

        :param request_ok: optional request to transition to "OK"
        """
        if (
            request_ok is False
            and self._status in {FndhStatusMap.ALARM, FndhStatusMap.RECOVERY}
            and "ALARM" not in self._sensors_status.values()
        ):
            self._status = FndhStatusMap.RECOVERY
        elif request_ok or (
            request_ok is False and self._status is not self.DEFAULT_STATUS
        ):
            if "ALARM" in self._sensors_status.values():
                self._status = FndhStatusMap.ALARM
                self._status_led = LedStatusMap.REDSLOW
            elif "WARNING" in self._sensors_status.values():
                self._status = FndhStatusMap.WARNING
                self._status_led = LedStatusMap.YELLOWSLOW
            else:
                self._status = FndhStatusMap.OK
                self._status_led = LedStatusMap.GREENSLOW

    def _update_ports_state(self: PasdHardwareSimulator) -> None:
        """
        Update the ports state.

        Enable or disable all the ports based on the system status.
        """
        if (
            self._status in {FndhStatusMap.OK, FndhStatusMap.WARNING}
            and not self._ports[0].enabled
        ):
            for port in self._ports:
                port.enabled = True
        elif self._ports[0].enabled:
            for port in self._ports:
                port.enabled = False

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
    def warning_flags(self: PasdHardwareSimulator) -> int:
        """
        Return the sensor warning flags.

        :return: the sensor warning flags.
        """
        return self._warning_flags

    def reset_warnings(self: PasdHardwareSimulator) -> bool | None:
        """
        Reset the sensor warning flags.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._warning_flags != self.DEFAULT_FLAGS:
            self._warning_flags = self.DEFAULT_FLAGS
            return True
        return None

    @property
    def alarm_flags(self: PasdHardwareSimulator) -> int:
        """
        Return the sensor alarm flags.

        :return: the sensor alarm flags.
        """
        return self._alarm_flags

    def reset_alarms(self: PasdHardwareSimulator) -> bool | None:
        """
        Reset the sensor alarm flags.

        :return: whether successful, or None if there was nothing to do.
        """
        if self._alarm_flags != self.DEFAULT_FLAGS:
            self._alarm_flags = self.DEFAULT_FLAGS
            return True
        return None

    @property
    def ports_connected(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return whether each port is connected.

        :return: whether each port is connected.
        """
        return [port.connected for port in self._ports]

    def simulate_port_forcing(
        self: PasdHardwareSimulator, forcing: Optional[bool]
    ) -> list[Optional[bool]]:
        """
        Simulate local forcing of a port.

        :param forcing: the new forcing status of the port. True means
            the port has been forced on. False means it has been forced
            off. None means it has not been forced.

        :return: whether successful, or None if there was nothing to do.
        """
        # Per port overriding is not possible in the hardware
        results = []
        for port in self._ports:
            results.append(port.simulate_forcing(forcing))
        return results

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

    @port_forcings.setter
    def port_forcings(self: PasdHardwareSimulator, forcing: tuple[str, int]) -> None:
        """
        Set the forcing status of a port.

        :param forcing: tuple of (forcing, port)
        """
        forcing_map = {
            "ON": True,
            "OFF": False,
            "NONE": None,
        }
        self._ports[forcing[1]].simulate_forcing(forcing_map[forcing[0]])

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
        return self._ports[port_number - 1].desired_on(
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
        return self._ports[port_number - 1].desired_off()

    def simulate_port_over_current(
        self: PasdHardwareSimulator, port_number: int, state: bool = True
    ) -> Optional[bool]:
        """
        Simulate a port breaker trip.

        :param port_number: number of the port for which a breaker trip
            will be simulated.
        :param state: of simulating condition.
        :return: whether successful, or None if there was nothing to do.
        """
        return self._ports[port_number - 1].simulate_over_current(state)

    @property
    def ports_desired_power_when_online(
        self: PasdHardwareSimulator,
    ) -> list[DesiredPowerEnum]:
        """
        Return the desired power of each port when the device is online.

        That is, for each port, should it be powered if the control
        system is online?

        :return: the desired power of each port when the device is
            online
        """
        return [port.desired_power_when_online for port in self._ports]

    @ports_desired_power_when_online.setter
    def ports_desired_power_when_online(
        self: PasdHardwareSimulator,
        desire: tuple[DesiredPowerEnum, int],
    ) -> None:
        """
        Set the desired power of a port when the device is online.

        :param desire: tuple of (desire power when online, port)
        """
        if desire[0] != DesiredPowerEnum.DEFAULT:
            self._ports[desire[1]].desired_power_when_online = desire[0]
            self._ports[desire[1]]._update_port_power()

    @property
    def ports_desired_power_when_offline(
        self: PasdHardwareSimulator,
    ) -> list[DesiredPowerEnum]:
        """
        Return the desired power of each port when the device is offline.

        That is, for each port, should it remain powered if the control
        system goes offline?

        :return: the desired power of each port when the device is
            offline
        """
        return [port.desired_power_when_offline for port in self._ports]

    @ports_desired_power_when_offline.setter
    def ports_desired_power_when_offline(
        self: PasdHardwareSimulator,
        desire: tuple[DesiredPowerEnum, int],
    ) -> None:
        """
        Set the desired power of a port when the device is offline.

        :param desire: tuple of (desire power when offline, port)
        """
        if desire[0] != DesiredPowerEnum.DEFAULT:
            self._ports[desire[1]].desired_power_when_offline = desire[0]
            self._ports[desire[1]]._update_port_power()

    @property
    def ports_power_sensed(self: PasdHardwareSimulator) -> list[bool]:
        """
        Return the actual sensed power state of each port.

        :return: the actual sensed power state of each port.
        """
        return [port.power_sensed for port in self._ports]

    @property
    def uptime(self: PasdHardwareSimulator) -> list[int]:
        """
        Return the uptime as an integer in seconds, or fractions of a second for tests.

        :return: the uptime.
        """
        if self._boot_on_time is None:
            return self.DEFAULT_UPTIME
        uptime_val = int(
            (datetime.now().timestamp() - self._boot_on_time.timestamp())
            * self._time_multiplier
        )
        return PasdConversionUtility.convert_uptime([uptime_val], inverse=True)

    @property
    def status(self: PasdHardwareSimulator) -> int:
        """
        Return the status of the FNDH/smartbox.

        :return: an overall status.
            "OK" means all sensors are within thresholds.
            "WARNING" means one or more sensors are over/under warning thresholds.
            "ALARM" means one or more sensors are over/under alarm thresholds.
            "RECOVERY" means all sensors are back within alarm thresholds after
            being in alarm state previously. "OK" status must be requested.
        """
        return self._status

    @status.setter
    def status(self: PasdHardwareSimulator, _: int) -> None:
        """
        Set the status of the FNDH/smartbox.

        This indicates the smartbox should be initialised, no matter the input value.
        """
        self.initialize()

    def initialize(self: PasdHardwareSimulator) -> bool | None:
        """
        Initialize a FNDH/smartbox.

        Request to transition the FNDH/smartbox's status to "OK".

        :return: whether successful, or None if there was nothing to do.
        """
        if self._status != FndhStatusMap.OK:
            self._update_system_status(request_ok=True)
            self._update_ports_state()
            if self._status == FndhStatusMap.OK:
                return True
            logger.debug(
                f"PaSD Bus simulator status was not set to OK, status is {self._status}"
            )
            return False
        return None

    @property
    def led_pattern(self: PasdHardwareSimulator) -> int:
        """
        Return the LED pattern name.

        :return: the name of the LED pattern.
        """
        return self._service_led | self._status_led

    @led_pattern.setter
    def led_pattern(self: PasdHardwareSimulator, service_pattern: int) -> None:
        """
        Set the LED pattern.

        :param service_pattern: the LED pattern to be set.
        """
        self.set_led_pattern(service_pattern)

    def set_led_pattern(
        self: PasdHardwareSimulator,
        service_pattern: int,
    ) -> bool | None:
        """
        Set the LED pattern.

        :param service_pattern: the LED pattern to be set.
        :return: whether successful, or None if there was nothing to do.
        """
        if (
            service_pattern in LedServiceMap.__members__.values()
            and self._service_led != service_pattern
        ):
            self._service_led = LedServiceMap(service_pattern)
            return True
        return None


class _Sensor:
    """
    Data descriptor for sensor attributes of a FNDH/Smartbox.

    This descriptor allows for handling sensor attributes and their status
    within the context of a FNDH/Smartbox simulator class.
    """

    # pylint: disable=attribute-defined-outside-init

    def __set_name__(self: _Sensor, owner: PasdHardwareSimulator, name: str) -> None:
        """
        Set the name of the sensor attribute.

        :param owner: The owner object.
        :param name: The name of the object created in the instance.
        """
        self.name = name

    def __get__(
        self: _Sensor, obj: PasdHardwareSimulator, objtype: type
    ) -> None | int | list[int]:
        """
        Get the value of the sensor attribute from the instance.

        :param obj: The instance of the class where the descriptor is being used.
        :param objtype: The type of the instance (usually the class).
        :returns: Sensor value stored in the instance's __dict__.
        """
        return obj.__dict__.get(self.name)

    def __set__(
        self: _Sensor, obj: PasdHardwareSimulator, value: int | list[int]
    ) -> None:
        """
        Set the value of the sensor attribute for the instance.

        Then update the system and ports status.

        :param obj: The instance of the class where the descriptor is being used.
        :param value: The value to be set for the sensor attribute.
        """
        obj.__dict__[self.name] = value
        obj._update_sensor_status(self.name.removesuffix("_thresholds"))
        obj._update_system_status()
        obj._update_ports_state()


class FndhSimulator(PasdHardwareSimulator):
    """
    A simple simulator of a Field Node Distribution Hub.

    This FNDH simulator will never be used as a standalone simulator. It
    will only be used as a component of a PaSD bus simulator.
    """

    # pylint: disable=too-many-instance-attributes

    NUMBER_OF_PORTS: Final = 28

    MODBUS_REGISTER_MAP_REVISION: Final = 1
    PCB_REVISION: Final = 21
    CPU_ID: Final = [1, 2]
    CHIP_ID: Final = [1, 2, 3, 4, 5, 6, 7, 8]
    SYS_ADDRESS: Final = FNDH_MODBUS_ADDRESS

    DEFAULT_FIRMWARE_VERSION: Final = 257
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

    ALARM_MAPPING = {
        "psu48v_voltage_1": FndhAlarmFlags.SYS_48V1_V,
        "psu48v_voltage_2": FndhAlarmFlags.SYS_48V2_V,
        "psu48v_current": FndhAlarmFlags.SYS_48V_I,
        "psu48v_temperature_1": FndhAlarmFlags.SYS_48V1_TEMP,
        "psu48v_temperature_2": FndhAlarmFlags.SYS_48V2_TEMP,
        "panel_temperature": FndhAlarmFlags.SYS_PANELTEMP,
        "fncb_temperature": FndhAlarmFlags.SYS_FNCBTEMP,
        "fncb_humidity": FndhAlarmFlags.SYS_HUMIDITY,
        "comms_gateway_temperature": FndhAlarmFlags.SYS_SENSE01_COMMS_GATEWAY,
        "power_module_temperature": FndhAlarmFlags.SYS_SENSE02_POWER_MODULE_TEMP,
        "outside_temperature": FndhAlarmFlags.SYS_SENSE03_OUTSIDE_TEMP,
        "internal_ambient_temperature": FndhAlarmFlags.SYS_SENSE04_INTERNAL_TEMP,
    }

    # Instantiate sensor data descriptors
    psu48v_voltages = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    psu48v_voltages_thresholds = _Sensor()
    psu48v_current = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    psu48v_current_thresholds = _Sensor()
    psu48v_temperatures = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    psu48v_temperatures_thresholds = _Sensor()
    panel_temperature = _Sensor()  # Not implemented in hardware?
    """Public attribute as _Sensor() data descriptor: *int*"""
    panel_temperature_thresholds = _Sensor()
    fncb_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    fncb_temperature_thresholds = _Sensor()
    fncb_humidity = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    fncb_humidity_thresholds = _Sensor()
    comms_gateway_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    comms_gateway_temperature_thresholds = _Sensor()
    power_module_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    power_module_temperature_thresholds = _Sensor()
    outside_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    outside_temperature_thresholds = _Sensor()
    internal_ambient_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    internal_ambient_temperature_thresholds = _Sensor()

    def __init__(
        self: FndhSimulator,
        time_multiplier: int,
        instantiate_smartbox: Callable[[int], Optional[bool]] | None = None,
        delete_smartbox: Callable[[int], Optional[bool]] | None = None,
    ) -> None:
        """
        Initialise a new instance.

        :param time_multiplier: to differentiate uptime in test context without delays.
        :param instantiate_smartbox: optional reference to PasdBusSimulator function.
        :param delete_smartbox: optional reference to PasdBusSimulator function.
        """
        ports: Sequence[_FndhPortSimulator] = [
            _FndhPortSimulator(port_index, instantiate_smartbox, delete_smartbox)
            for port_index in range(1, self.NUMBER_OF_PORTS + 1)
        ]
        super().__init__(ports, time_multiplier)
        # Sensors
        super()._load_thresholds(self.DEFAULT_THRESHOLDS_PATH, "fndh")
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
        # Aliases for some thresholds, which are separate sets in HW
        self.psu48v_voltage_1_thresholds = self.psu48v_voltages_thresholds
        self.psu48v_voltage_2_thresholds = self.psu48v_voltages_thresholds
        self.psu48v_temperature_1_thresholds = self.psu48v_temperatures_thresholds
        self.psu48v_temperature_2_thresholds = self.psu48v_temperatures_thresholds

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
    def cpu_id(self: FndhSimulator) -> list[int]:
        """
        Return the ID of the CPU.

        :return: the ID of the CPU.
        """
        return self.CPU_ID

    @property
    def chip_id(self: FndhSimulator) -> list[int]:
        """
        Return the ID of the chip.

        :return: the ID of the chip.
        """
        return self.CHIP_ID

    @property
    def firmware_version(self: FndhSimulator) -> int:
        """
        Return the firmware version.

        :return: the firmware version.
        """
        return self.DEFAULT_FIRMWARE_VERSION

    @property
    def ports_power_control(
        self: FndhSimulator,
    ) -> list[bool]:
        """
        Return the power control line state of each FNDH port.

        :return: the power control line state of each FNDH port.
        """
        return [
            port.enabled if port.forcing is not False else False for port in self._ports
        ]

    def simulate_port_stuck_on(
        self: FndhSimulator, port_number: int, state: bool = True
    ) -> Optional[bool]:
        """
        Simulate port stuck on fault condition.

        :param port_number: number of the port for which a breaker trip
            will be simulated.
        :param state: of simulating condition.
        :return: whether successful, or None if there was nothing to do.
        """
        return self._ports[port_number - 1].simulate_stuck_on(state)


class SmartboxSimulator(PasdHardwareSimulator):
    """A simulator for a PaSD smartbox."""

    # pylint: disable=too-many-instance-attributes

    NUMBER_OF_PORTS: Final = 12

    MODBUS_REGISTER_MAP_REVISION: Final = 1
    PCB_REVISION: Final = 21
    CPU_ID: Final = [2, 4]
    CHIP_ID: Final = [8, 7, 6, 5, 4, 3, 2, 1]

    DEFAULT_STATUS: SmartboxStatusMap = SmartboxStatusMap.UNINITIALISED
    DEFAULT_SYS_ADDRESS: Final = 1
    DEFAULT_FIRMWARE_VERSION: Final = 258
    # Address
    DEFAULT_INPUT_VOLTAGE: Final = 4800
    DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE: Final = 480
    DEFAULT_POWER_SUPPLY_TEMPERATURE: Final = 4210
    DEFAULT_PCB_TEMPERATURE: Final = 3860  # Not implemented in hardware?
    DEFAULT_FEM_AMBIENT_TEMPERATURE: Final = 4010
    DEFAULT_FEM_CASE_TEMPERATURES: Final = [4440, 4460]
    DEFAULT_FEM_HEATSINK_TEMPERATURES: Final = [4280, 4250]
    DEFAULT_PORT_CURRENT_DRAW: Final = 421
    DEFAULT_PORT_CURRENT_THRESHOLD: Final = 496

    ALARM_MAPPING = {
        "input_voltage": SmartboxAlarmFlags.SYS_48V_V,
        "power_supply_output_voltage": SmartboxAlarmFlags.SYS_PSU_V,
        "power_supply_temperature": SmartboxAlarmFlags.SYS_PSU_TEMP,
        "pcb_temperature": SmartboxAlarmFlags.SYS_PCB_TEMP,
        "fem_ambient_temperature": SmartboxAlarmFlags.SYS_AMB_TEMP,
        "fem_case_temperature_1": SmartboxAlarmFlags.SYS_SENSE01_FEM_CASE1_TEMP,
        "fem_case_temperature_2": SmartboxAlarmFlags.SYS_SENSE02_FEM_CASE2_TEMP,
        "fem_heatsink_temperature_1": SmartboxAlarmFlags.SYS_SENSE03_FEM_HEATSINK_TEMP1,
        "fem_heatsink_temperature_2": SmartboxAlarmFlags.SYS_SENSE04_FEM_HEATSINK_TEMP2,
    }

    # Instantiate sensor data descriptors
    input_voltage = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    input_voltage_thresholds = _Sensor()
    power_supply_output_voltage = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    power_supply_output_voltage_thresholds = _Sensor()
    power_supply_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    power_supply_temperature_thresholds = _Sensor()
    pcb_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    pcb_temperature_thresholds = _Sensor()
    fem_ambient_temperature = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    fem_ambient_temperature_thresholds = _Sensor()
    fem_case_temperatures = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    fem_case_temperatures_thresholds = _Sensor()
    fem_heatsink_temperatures = _Sensor()
    """Public attribute as _Sensor() data descriptor: *int*"""
    fem_heatsink_temperatures_thresholds = _Sensor()

    def __init__(
        self: SmartboxSimulator,
        time_multiplier: int,
        address: int = DEFAULT_SYS_ADDRESS,
    ) -> None:
        """
        Initialise a new instance.

        :param time_multiplier: to differentiate uptime in test context without delays.
        :param address: to set as default system address.
        """
        ports: Sequence[_SmartboxPortSimulator] = [
            _SmartboxPortSimulator(port_index + 1)
            for port_index in range(self.NUMBER_OF_PORTS)
        ]
        super().__init__(ports, time_multiplier)
        self._status = SmartboxStatusMap.UNINITIALISED
        self._sys_address = address
        # Sensors
        super()._load_thresholds(self.DEFAULT_THRESHOLDS_PATH, "smartbox")
        self.input_voltage = self.DEFAULT_INPUT_VOLTAGE
        self.power_supply_output_voltage = self.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        self.power_supply_temperature = self.DEFAULT_POWER_SUPPLY_TEMPERATURE
        self.pcb_temperature = self.DEFAULT_PCB_TEMPERATURE
        self.fem_ambient_temperature = self.DEFAULT_FEM_AMBIENT_TEMPERATURE
        self.fem_case_temperatures = self.DEFAULT_FEM_CASE_TEMPERATURES
        self.fem_heatsink_temperatures = self.DEFAULT_FEM_HEATSINK_TEMPERATURES
        # Aliases for some thresholds, which are separate sets in HW
        self.fem_case_temperature_1_thresholds = self.fem_case_temperatures_thresholds
        self.fem_case_temperature_2_thresholds = self.fem_case_temperatures_thresholds
        self.fem_heatsink_temperature_1_thresholds = (
            self.fem_heatsink_temperatures_thresholds
        )
        self.fem_heatsink_temperature_2_thresholds = (
            self.fem_heatsink_temperatures_thresholds
        )
        # TODO: Make each current trip threshold separate R/W property?
        self.fem1_current_trip_threshold = self.ports_current_trip_threshold
        self.fem2_current_trip_threshold = self.ports_current_trip_threshold
        self.fem3_current_trip_threshold = self.ports_current_trip_threshold
        self.fem4_current_trip_threshold = self.ports_current_trip_threshold
        self.fem5_current_trip_threshold = self.ports_current_trip_threshold
        self.fem6_current_trip_threshold = self.ports_current_trip_threshold
        self.fem7_current_trip_threshold = self.ports_current_trip_threshold
        self.fem8_current_trip_threshold = self.ports_current_trip_threshold
        self.fem9_current_trip_threshold = self.ports_current_trip_threshold
        self.fem10_current_trip_threshold = self.ports_current_trip_threshold
        self.fem11_current_trip_threshold = self.ports_current_trip_threshold
        self.fem12_current_trip_threshold = self.ports_current_trip_threshold

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
        logger.info(
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
            self.DEFAULT_PORT_CURRENT_DRAW if connected and powered else 0
            for connected, powered in zip(self.ports_connected, self.ports_power_sensed)
        ]

    @property
    def ports_current_trip_threshold(
        self: SmartboxSimulator,
    ) -> int:
        """
        Return the current trip threshold for each smartbox port.

        :return: the current trip threshold for each smartbox port.
        """
        return self.DEFAULT_PORT_CURRENT_THRESHOLD

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
    def cpu_id(self: SmartboxSimulator) -> list[int]:
        """
        Return the CPU ID.

        :return: the CPU ID.
        """
        return self.CPU_ID

    @property
    def chip_id(self: SmartboxSimulator) -> list[int]:
        """
        Return the chip ID.

        :return: the chip ID.
        """
        return self.CHIP_ID

    @property
    def firmware_version(self: SmartboxSimulator) -> int:
        """
        Return the firmware version.

        :return: the firmware version.
        """
        return self.DEFAULT_FIRMWARE_VERSION

    @property
    def port_breakers_tripped(self: SmartboxSimulator) -> list[bool]:
        """
        Return whether each port has had its breaker tripped.

        :return: whether each port has had its breaker tripped
        """
        return [port.breaker_tripped for port in self._ports]

    @port_breakers_tripped.setter
    def port_breakers_tripped(self: SmartboxSimulator, reset: tuple[bool, int]) -> None:
        """
        Set a port breaker's status.

        This can only be used to reset a port breaker, it cannot simulate a port
        breaker trip.

        :param reset: tuple of (breaker status (True to reset breaker), port)
        """
        if reset[0]:
            self.reset_port_breaker(reset[1] + 1)

    def reset_port_breaker(
        self: SmartboxSimulator,
        port_number: int,
    ) -> Optional[bool]:
        """
        Reset a tripped port breaker.

        :param port_number: number of the port whose breaker should be reset.
        :return: whether successful, or None if there was nothing to do.
        """
        return self._ports[port_number - 1].simulate_over_current(False)


class PasdBusSimulator:
    """
    A stub class that provides similar functionality to a PaSD bus.

    Many attributes are stubbed out:

    * The antennas are always online.
    * Voltages, currents and temperatures never change.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self: PasdBusSimulator,
        pasd_configuration_path: str,
        station_label: str,
        logging_level: int = logging.INFO,
        smartboxes_depend_on_attached_ports: bool = False,
        time_multiplier: int = 1000,  # ms
    ) -> None:
        """
        Initialise a new instance.

        :param pasd_configuration_path: path to a PaSD configuration file.
        :param station_label: name of the station to which this PaSD belongs.
        :param logging_level: the level to log at.
        :param smartboxes_depend_on_attached_ports: enable instantiation/deleting
            of smartboxes when FNDH ports are turned on and off.
        :param time_multiplier: to differentiate uptime in test context without delays.
        """
        self._station_label = station_label
        logger.setLevel(logging_level)
        logger.info(
            f"Logger level set to {logging.getLevelName(logger.getEffectiveLevel())}."
        )

        self._hw_simulators: dict[int, PasdHardwareSimulator] = {}
        self._smartboxes_ports_connected: list[list[bool]] = []
        self._smartbox_attached_ports: list[int] = [0] * PasdData.NUMBER_OF_SMARTBOXES
        self._time_multiplier: int = time_multiplier

        if smartboxes_depend_on_attached_ports:
            self._hw_simulators[0] = FndhSimulator(
                time_multiplier, self._instantiate_smartbox, self._delete_smartbox
            )
        else:
            self._hw_simulators[0] = FndhSimulator(time_multiplier)
        logger.info(f"Initialised FNDH simulator for station {station_label}.")

        self._load_config(pasd_configuration_path)
        logger.info(
            "PaSD configuration data loaded into simulator "
            f"for station {station_label}."
        )

        if not smartboxes_depend_on_attached_ports:
            for port_number in self._smartbox_attached_ports:
                self._instantiate_smartbox(port_number)
        logger.info(f"Initialised PaSD bus simulator for station {station_label}.")

    def get_fndh(self: PasdBusSimulator) -> PasdHardwareSimulator:
        """
        Return only the FNDH simulator.

        :return: the FNDH simulator.
        """
        return self._hw_simulators[0]

    def get_fndh_and_smartboxes(
        self: PasdBusSimulator,
    ) -> dict[int, PasdHardwareSimulator]:
        """
        Return a dictionary of the FNDH and Smartbox simulators.

        :return: a dictionary of simulators.
        """
        return self._hw_simulators

    def get_smartbox_attached_ports(self: PasdBusSimulator) -> list[int]:
        """
        Return a list of FNDH port numbers each smartbox is attached to.

        :return: a list of FNDH port numbers each smartbox is attached to.
        """
        return self._smartbox_attached_ports

    def _instantiate_smartbox(
        self: PasdBusSimulator, port_number: int
    ) -> Optional[bool]:
        """
        Try to instantiate a smartbox.

        :param port_number: of FNDH.
        :return: whether successful, or None if there was nothing to do.
        """
        try:
            smartbox_id = self._smartbox_attached_ports.index(port_number) + 1
            self._hw_simulators[smartbox_id] = SmartboxSimulator(
                self._time_multiplier, smartbox_id
            )
            self._hw_simulators[smartbox_id].configure(
                self._smartboxes_ports_connected[smartbox_id - 1]
            )
            logger.debug(f"Initialised Smartbox simulator {smartbox_id}.")
            return True
        except ValueError:
            return None

    def _delete_smartbox(self: PasdBusSimulator, port_number: int) -> Optional[bool]:
        """
        Try to delete an existing smartbox instance.

        :param port_number: of FNDH.
        :return: whether successful, or None if there was nothing to do.
        """
        try:
            smartbox_id = self._smartbox_attached_ports.index(port_number) + 1
            del self._hw_simulators[smartbox_id]
            logger.debug(f"Deleted Smartbox simulator {smartbox_id}.")
            return True
        except ValueError:
            return None

    def _load_config(self: PasdBusSimulator, path: str) -> bool:
        """
        Load PaSD configuration data from a file into this simulator.

        :param path: path to a file from which to load configuration.

        :return: whether successful

        :raises yaml.YAMLError: if the config file cannot be parsed.
        """
        with open(path, "r", encoding="utf-8") as config_file:
            try:
                config = yaml.safe_load(config_file)
            except yaml.YAMLError as exception:
                logger.error(
                    f"PaSD Bus simulator could not load configuration: {exception}."
                )
                raise

        pasd_config = config["pasd"]

        fndh_ports_is_connected = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_id, smartbox_config in pasd_config["smartboxes"].items():
            smartbox_id = int(smartbox_id)
            fndh_port = smartbox_config["fndh_port"]
            self._smartbox_attached_ports[smartbox_id - 1] = fndh_port
            fndh_ports_is_connected[fndh_port - 1] = True
        self._hw_simulators[0].configure(fndh_ports_is_connected)

        self._smartboxes_ports_connected = [
            [False] * SmartboxSimulator.NUMBER_OF_PORTS
            for _ in range(PasdData.NUMBER_OF_SMARTBOXES)
        ]
        for antenna_config in config["antennas"].values():
            smartbox_id = int(antenna_config["smartbox"])
            smartbox_port = antenna_config["smartbox_port"]
            self._smartboxes_ports_connected[smartbox_id - 1][smartbox_port - 1] = True

        return True
