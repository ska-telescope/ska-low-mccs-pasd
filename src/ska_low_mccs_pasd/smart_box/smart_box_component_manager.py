#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
# pylint: disable=too-many-lines
"""This module implements the component management for smartbox."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common import MccsDeviceProxy
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

from ska_low_mccs_pasd.pasd_data import PasdData

__all__ = ["SmartBoxComponentManager"]


class Port:
    """A instance of a Smartbox Port."""

    def __init__(
        self,
        power_on_callback: Callable[..., Any],
        port_id: int,
        logger: logging.Logger,
    ) -> None:
        """
        Initialise a new instance.

        :param port_id: the port id
        :param power_on_callback: a callback hook to turn ON this port.
        :param logger: a logger for this object to use
        """
        self.logger = logger
        self._port_id = port_id
        self._power_on_callback = power_on_callback

        self.desire_on = False
        self._task_callback = None

    def set_desire_on(self, task_callback: Optional[Callable]) -> None:
        """
        Desire the port to be turned on when the smartbox becomes online.

        :param task_callback: the command_tracker callback
            for this command.
        """
        self.logger.info("Port desired on. To be turned on when smartbox is on.")
        self.desire_on = True
        self._task_callback = task_callback  # type: ignore[assignment]

    def turn_on(self, task_callback: Optional[Callable] = None) -> None:
        """
        Turn the port on.

        :param task_callback: the command_tracker callback
            for this command.
        """
        self.logger.info(f"Turning on Power to port {self._port_id}.......")
        assert (
            self._task_callback or task_callback
        ), "We need task callback in order to keep track of command status"

        command_tracker = next(
            item for item in [task_callback, self._task_callback] if item is not None
        )
        self._power_on_callback(  # type: ignore[attr-defined]
            self._port_id, command_tracker
        )

        self.desire_on = False
        self._task_callback = None


class _PasdBusProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus specific to this smartbox."""

    # pylint: disable=too-many-arguments
    def __init__(
        self: _PasdBusProxy,
        fqdn: str,
        smartbox_nr: int,
        logger: logging.Logger,
        max_workers: int,
        smartbox_communication_state_callback: Callable[[CommunicationStatus], None],
        smartbox_component_state_callback: Callable[..., None],
        fndh_port_power_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the Tile device.
        :param smartbox_nr: the smartbox's ID number.
        :param logger: the logger to be used by this object.
        :param max_workers: the maximum worker threads for the slow commands
            associated with this component manager.
        :param smartbox_communication_state_callback: callback to be
            called when the status of the communications change.
        :param smartbox_component_state_callback: callback to be
            called when the component state changes.
        :param fndh_port_power_callback: callback to be called when the
            fndh port power states change.
        :param attribute_change_callback: callback for when a attribute relevant to
            this smartbox changes.
        """
        self._attribute_change_callback = attribute_change_callback
        self._fndh_port_power_callback = fndh_port_power_callback
        self._smartbox_nr = smartbox_nr
        self._power_state = PowerState.UNKNOWN

        super().__init__(
            fqdn,
            logger,
            max_workers,
            smartbox_communication_state_callback,
            smartbox_component_state_callback,
        )

    def subscribe_to_attributes(self: _PasdBusProxy) -> None:
        """Subscribe to attributes relating to this SmartBox."""
        assert self._proxy is not None
        # Ask what attributes to subscribe to and subscribe to them.
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self._smartbox_nr)
        for attribute in subscriptions:
            if attribute not in self._proxy._change_event_subscription_ids.keys():
                self._proxy.add_change_event_callback(
                    attribute, self._on_attribute_change
                )
        # Also subscribe to fndhPortsPowerSensed
        if (
            "fndhPortsPowerSensed"
            not in self._proxy._change_event_subscription_ids.keys()
        ):
            self._proxy.add_change_event_callback(
                "fndhPortsPowerSensed", self._fndh_port_power_callback
            )

    def _on_attribute_change(
        self: _PasdBusProxy,
        attr_name: str,
        attr_value: Any,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle attribute change.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        # TODO: MCCS-1481: Update the MccsDeviceProxy to conserve attribute case.

        try:
            # 'smartbox' followed by 1 or 2 digits, followed by a string.
            smartbox_attribute_pattern = re.compile(r"smartbox(\d{1,2})(.*)")

            # Use the pattern to match the input string
            smartbox_attribute = smartbox_attribute_pattern.match(attr_name)

            # Check if we got a match, this checks it starts with 'smartbox'
            assert smartbox_attribute is not None

            # Check we're looking at the correct smartbox
            assert int(smartbox_attribute.group(1)) == self._smartbox_nr

            # If there's a match, return the string after the number
            tango_attribute_name = smartbox_attribute.group(2).lower()

            if tango_attribute_name == "status":
                tango_attribute_name = "pasdstatus"

            timestamp = datetime.now(timezone.utc).timestamp()
            self._attribute_change_callback(
                tango_attribute_name, attr_value, timestamp, attr_quality
            )
        except AssertionError:
            self.logger.error(
                f"Attribute subscription {attr_name} does not seem to belong "
                f"to this smartbox (smartbox {self._smartbox_nr})"
            )

    def set_smartbox_port_powers(
        self: _PasdBusProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the SetSmartboxPortPowers command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        self._proxy.InitializeSmartbox(self._smartbox_nr)
        argument = json.loads(json_argument)
        argument.update({"smartbox_number": self._smartbox_nr})
        return self._proxy.SetSmartboxPortPowers(json.dumps(argument))

    def set_fndh_port_powers(
        self: _PasdBusProxy, json_argument: str
    ) -> tuple[ResultCode, str]:
        """
        Proxy for the SetFndhPortPowers command.

        :param json_argument: the json formatted string.

        :return: A tuple containing a result code and a
            unique id to identify the command in the queue.
        """
        assert self._proxy
        self._proxy.InitializeFndh()
        return self._proxy.SetFndhPortPowers(json_argument)

    def write_attribute(
        self: _PasdBusProxy, tango_attribute_name: str, value: Any
    ) -> None:
        """
        Proxy for the generic write attribute function.

        :param tango_attribute_name: the name of the Tango attribute.
        :param value: the value to write.
        """
        assert self._proxy
        setattr(
            self._proxy,
            f"smartbox{self._smartbox_nr}{tango_attribute_name}",
            value,
        )


# pylint: disable-next=abstract-method, too-many-instance-attributes
class SmartBoxComponentManager(TaskExecutorComponentManager):
    """
    A component manager for MccsSmartBox.

    This communicates via a proxy to a MccsPasdBus that talks to a simulator
    or the real hardware.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self: SmartBoxComponentManager,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        smartbox_nr: int,
        port_count: int,
        field_station_name: str,
        pasd_fqdn: str,
        _pasd_bus_proxy: Optional[MccsDeviceProxy] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_callback: callback to be
            called when the component state changes
        :param attribute_change_callback: callback to be called when a attribute
            of interest changes.
        :param smartbox_nr: the smartbox's ID number.
        :param port_count: the number of smartbox ports.
        :param field_station_name: the name of the field station.
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
        """
        max_workers = 1
        self._pasd_fqdn = pasd_fqdn
        self.logger = logger
        self.ports = [
            Port(self.turn_on_port, port, logger) for port in range(1, port_count + 1)
        ]
        self._power_state = PowerState.UNKNOWN
        self._desire_standby = False
        self._smartbox_nr = smartbox_nr
        self._fndh_port: Optional[int] = None
        self._port_mask = [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS
        self._attribute_change_callback = attribute_change_callback
        self.fndh_ports_change = threading.Event()
        self.smartbox_ports_change = threading.Event()

        self._fndh_port_powers = [PowerState.UNKNOWN] * PasdData.NUMBER_OF_FNDH_PORTS
        self._smartbox_port_powers = [
            PowerState.UNKNOWN
        ] * PasdData.NUMBER_OF_SMARTBOX_PORTS

        self._field_station_proxy = DeviceComponentManager(
            field_station_name,
            logger,
            max_workers,
            self._field_station_communication_change,
            self._field_station_state_change,
        )

        self._pasd_bus_proxy = _pasd_bus_proxy or _PasdBusProxy(
            pasd_fqdn,
            smartbox_nr,
            logger,
            max_workers,
            self._pasd_bus_communication_state_changed,
            self._pasd_bus_component_state_changed,
            self._on_fndh_ports_power_changed,
            attribute_change_callback,
        )
        self._pasd_communication_state = CommunicationStatus.NOT_ESTABLISHED
        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
            max_workers=max_workers,
            power=None,
            health=None,
            fault=None,
            pasdbus_status=None,
        )

    def _field_station_communication_change(
        self: SmartBoxComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        if communication_state == CommunicationStatus.ESTABLISHED:
            assert self._field_station_proxy._proxy is not None
            self._field_station_proxy._proxy.add_change_event_callback(
                "smartboxMapping", self._on_mapping_change
            )

    def _on_mapping_change(
        self: SmartBoxComponentManager,
        event_name: str,
        event_value: str,
        event_quality: tango.AttrQuality,
    ) -> None:
        self.logger.warning(f"Mapping changed to {event_value}")
        assert event_name.lower() == "smartboxmapping"

        mapping = json.loads(event_value)
        if mapping is None:
            self.logger.warning(
                "Smartbox mapping is not present, "
                "Check FieldStation `smartboxMapping`."
            )
            return
        for smartbox_config in mapping["smartboxMapping"]:
            if "smartboxID" in smartbox_config:
                if smartbox_config["smartboxID"] == self._smartbox_nr:
                    fndh_port = smartbox_config["fndhPort"]
                    if 0 < fndh_port < PasdData.NUMBER_OF_FNDH_PORTS + 1:
                        self.update_fndh_port(fndh_port)
                        self.logger.info(
                            f"Smartbox has been moved to fndh port {fndh_port}"
                        )
                        return
                    self.logger.error(
                        f"Unable to put smartbox on port {fndh_port},"
                        "Out of range 0 - 28"
                    )
                    return

    def start_communicating(self: SmartBoxComponentManager) -> None:
        """Establish communication."""
        self._pasd_bus_proxy.start_communicating()
        self._field_station_proxy.start_communicating()

    def _pasd_bus_communication_state_changed(
        self: SmartBoxComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        self._pasd_communication_state = communication_state
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._pasd_bus_proxy.subscribe_to_attributes()
        # Only update state on change.
        if communication_state != self._communication_state:
            self._update_communication_state(self._pasd_communication_state)

    def _pasd_bus_component_state_changed(
        self: SmartBoxComponentManager,
        power: PowerState | None = None,
        **kwargs: Any,
    ) -> None:
        if power == PowerState.UNKNOWN:
            self.logger.warning(
                "PasdBus power state has become UNKNOWN."
                "This is treated as communication `NOT_ESTABLISHED`"
            )
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
        elif power == PowerState.ON:
            self._update_communication_state(CommunicationStatus.ESTABLISHED)

    def _field_station_state_change(
        self: SmartBoxComponentManager,
        power: PowerState | None = None,
        **kwargs: Any,
    ) -> None:
        # MccsSmartbox does not care about the state of fieldstation!
        return

    def _on_fndh_ports_power_changed(
        self: SmartBoxComponentManager,
        attr_name: str,
        attr_value: list[bool],
        attr_quality: tango.AttrQuality,
    ) -> None:
        assert attr_name.lower() == "fndhportspowersensed", (
            "failed to update the fndh port powers"
            f"{attr_name.lower()} is not fndhportspowersensed"
        )

        for idx, attr in enumerate(attr_value):
            self._fndh_port_powers[idx] = PowerState.ON if attr else PowerState.OFF
        self.fndh_ports_change.set()
        self._evaluate_power()

    def _on_smartbox_ports_power_changed(
        self: SmartBoxComponentManager,
        attr_name: str,
        attr_value: list[bool],
        attr_quality: tango.AttrQuality,
    ) -> None:
        assert attr_name.lower() == "portspowersensed", (
            "failed to update the smartbox port powers "
            f"{attr_name.lower()} is not portspowersensed"
        )

        for idx, attr in enumerate(attr_value):
            self._smartbox_port_powers[idx] = PowerState.ON if attr else PowerState.OFF
        self.smartbox_ports_change.set()
        self._evaluate_power()

    def update_fndh_port(self: SmartBoxComponentManager, fndh_port: int) -> None:
        """
        Update the fndh port this smartbox is on.

        :param fndh_port: The fndh port this smartbox is on.
        """
        if self._fndh_port != fndh_port and fndh_port is not None:
            for port in self.ports:
                port.desire_on = False
            self._fndh_port = fndh_port
            self._evaluate_power()

    def _evaluate_power(self: SmartBoxComponentManager) -> None:
        """
        Evaluate the power state of the smartbox device.

        * If the Smartbox's FNDH port is not known, the smartbox is UNKNOWN.
        * If the Smartbox's FNDH port is OFF, the Smartbox is OFF.
        * If the Smartbox's FNDH port is ON, and one of:
            1. All its ports are OFF, while not being masked,
            2. All its ports are OFF, and masked, and the desired state is STANDBY,

          the Smartbox is STANDBY.
        * If the Smartbox's FNDH port is ON, and one of:
            1. Any of its ports are ON,
            2. All its ports are OFF, and masked, and the desired state is not STANDBY,

          the Smartbox is ON.
        * If the Smartbox is not in any of the states above, it is UNKNOWN.
        """
        timestamp = datetime.now(timezone.utc).timestamp()
        if self._fndh_port is None:
            self.logger.info(
                "The fndh port this smartbox is attached to is unknown,"
                "Therefore smartbox state transitions to UNKNOWN."
            )
            self._update_component_state(power=PowerState.UNKNOWN)
            return

        match self._fndh_port_powers[self._fndh_port - 1]:
            # If the FNDH port is OFF, the Smartbox is OFF
            case PowerState.OFF:
                if self._power_state != PowerState.OFF:
                    self.logger.info("Setting Smartbox to OFF as its FNDH port is OFF.")
                    self._power_state = PowerState.OFF
                    self._attribute_change_callback(
                        "portspowersensed",
                        [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
                        timestamp,
                        tango.AttrQuality.ATTR_VALID,
                    )

            case PowerState.ON:
                for port in self.ports:
                    if port.desire_on:
                        port.turn_on()

                # If the FNDH port is ON, but all smartbox the ports are OFF,
                # and all the ports aren't masked, the smartbox is STANDBY.
                # However if the ports are all masked, and the last command given was
                # Standby(), go to STANDBY.
                if all(
                    power == PowerState.OFF for power in self._smartbox_port_powers
                ) and (
                    not all(masked for masked in self._port_mask)
                    or self._desire_standby
                ):
                    if self._power_state != PowerState.STANDBY:
                        self.logger.info(
                            "Setting Smartbox to STANDBY as its FNDH port is ON. "
                            "And all its ports are OFF, while they aren't all masked."
                        )
                        self._power_state = PowerState.STANDBY

                # If the FNDH port is ON, and (any of the smartbox ports are ON,
                # or all smartbox ports are OFF, but they are all masked),
                # the Smartbox is ON,
                elif any(
                    power == PowerState.ON for power in self._smartbox_port_powers
                ) or all(masked for masked in self._port_mask):
                    if self._power_state != PowerState.ON:
                        self.logger.info(
                            "Setting Smartbox to ON as its FNDH port is ON. "
                            "And at least one of its ports is ON, "
                            "or all of its ports are masked."
                        )
                        self._power_state = PowerState.ON
                        try:
                            port_power = getattr(
                                self._pasd_bus_proxy._proxy,
                                f"smartbox{self._smartbox_nr}portspowersensed",
                            )
                            self._attribute_change_callback(
                                "portspowersensed",
                                port_power,
                                timestamp,
                                tango.AttrQuality.ATTR_VALID,
                            )
                        except Exception:  # pylint: disable=broad-except
                            self.logger.warning(
                                "Unable to read smartbox port powers"
                                "May be attempting read before attribute polled."
                                "port powers will be updated when polled."
                            )

                else:
                    self.logger.warning("No PowerState rules matched, going UNKNOWN")
                    self._power_state = PowerState.UNKNOWN

            case PowerState.UNKNOWN:
                self.logger.warning(
                    f"The FNDH port is known ({self._fndh_port}), "
                    "however its PowerState is UNKNOWN"
                )
                self._power_state = PowerState.UNKNOWN

            case _:
                self.logger.warning("No PowerState rules matched, going UNKNOWN")
                self._power_state = PowerState.UNKNOWN

        self._update_component_state(power=self._power_state)

    def stop_communicating(self: SmartBoxComponentManager) -> None:
        """Stop communication with components under control."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._pasd_bus_proxy.stop_communicating()
        self._update_component_state(power=None, fault=None)

    def _power_fndh_port(
        self: SmartBoxComponentManager,
        power_state: PowerState,
        fndh_port: int,
        timeout: int,
    ) -> int:
        desired_port_powers: list[bool | None] = [None] * PasdData.NUMBER_OF_FNDH_PORTS
        desired_port_powers[fndh_port - 1] = power_state == PowerState.ON
        json_argument = json.dumps(
            {
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )
        self._pasd_bus_proxy.set_fndh_port_powers(json_argument)
        return self._wait_for_fndh_port_state(power_state, fndh_port, timeout)

    def _wait_for_fndh_port_state(
        self: SmartBoxComponentManager,
        power_state: PowerState,
        fndh_port: int,
        timeout: int,
    ) -> int:
        while self._fndh_port_powers[fndh_port - 1] != power_state:
            self.logger.debug(
                f"Waiting for FNDH port {self._fndh_port} to change state."
            )
            t1 = time.time()
            self.fndh_ports_change.wait(3)
            t2 = time.time()
            timeout -= int(t2 - t1)
            self.fndh_ports_change.clear()
            if timeout < 0:
                raise TimeoutError(
                    f"FNDH port {self._fndh_port} didn't "
                    f"change state in {timeout} seconds."
                )
        return timeout

    def _power_smartbox_ports(
        self: SmartBoxComponentManager, power_state: PowerState, timeout: int
    ) -> int:
        desired_port_powers: list[bool] = [
            power_state == PowerState.ON
        ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
        for port, masked in enumerate(self._port_mask):
            if masked:
                desired_port_powers[port] = False
        json_argument = json.dumps(
            {
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )
        self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)
        return self._wait_for_smartbox_ports_state(desired_port_powers, timeout)

    def _wait_for_smartbox_ports_state(
        self: SmartBoxComponentManager, desired_port_powers: list[bool], timeout: int
    ) -> int:
        desired_port_power_states = [
            PowerState.ON if power else PowerState.OFF for power in desired_port_powers
        ]
        while not self._smartbox_port_powers == desired_port_power_states:
            self.logger.debug("Waiting for unmasked smartbox ports to change state")
            t1 = time.time()
            self.smartbox_ports_change.wait(3)
            t2 = time.time()
            timeout -= int(t2 - t1)
            self.smartbox_ports_change.clear()
            if timeout < 0:
                raise TimeoutError(
                    f"Unmasked smartbox ports didn't change state in {timeout} seconds."
                )
        return timeout

    @check_communicating
    def on(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox on.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._on,  # type: ignore[arg-type]
            args=[],
            task_callback=task_callback,
        )

    def _on(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        if self._pasd_bus_proxy is None:
            raise ValueError(f"Power on smartbox '{self._fndh_port} failed'")

        if self._fndh_port is None:
            self.logger.info(
                "Cannot turn on SmartBox, we do not yet know what port it is on"
            )
            raise ValueError("cannot turn on Unknown FNDH port.")

        # So we can differentiate between ON and STANDBY when all ports are masked.
        self._desire_standby = False

        try:
            timeout = 60  # seconds
            if self._fndh_port_powers[self._fndh_port - 1] != PowerState.ON:
                timeout = self._power_fndh_port(PowerState.ON, self._fndh_port, timeout)

            self._power_smartbox_ports(PowerState.ON, timeout)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=(ResultCode.FAILED, f"{ex}"),
                )

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(
                    ResultCode.OK,
                    f"Power on smartbox '{self._fndh_port} success'",
                ),
            )

    @check_communicating
    def standby(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox to standby.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._standby,  # type: ignore[arg-type]
            args=[],
            task_callback=task_callback,
        )

    def _standby(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        if self._pasd_bus_proxy is None:
            raise ValueError(f"Power smartbox '{self._fndh_port} to standby failed'")

        if self._fndh_port is None:
            self.logger.info(
                "Cannot turn SmartBox to standby, we do not yet know what port it is on"
            )
            raise ValueError("cannot turn on Unknown FNDH port.")

        # So we can differentiate between ON and STANDBY when all ports are masked.
        self._desire_standby = True

        try:
            timeout = 60  # seconds
            if self._fndh_port_powers[self._fndh_port - 1] != PowerState.ON:
                timeout = self._power_fndh_port(PowerState.ON, self._fndh_port, timeout)

            self._power_smartbox_ports(PowerState.OFF, timeout)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=(ResultCode.FAILED, f"{ex}"),
                )

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(
                    ResultCode.OK,
                    f"Power smartbox '{self._fndh_port} to standby success'",
                ),
            )

    @check_communicating
    def off(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn the Smartbox off.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,  # type: ignore[arg-type]
            args=[],
            task_callback=task_callback,
        )

    def _off(
        self: SmartBoxComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        if self._pasd_bus_proxy is None:
            raise ValueError(f"Power off smartbox '{self._fndh_port} failed'")

        if self._fndh_port is None:
            self.logger.info(
                "Cannot turn on SmartBox, we do not yet know what port it is on"
            )
            raise ValueError("cannot turn off Unknown FNDH port.")

        try:
            timeout = 60  # seconds
            if self._fndh_port_powers[self._fndh_port - 1] != PowerState.OFF:
                timeout = self._power_fndh_port(
                    PowerState.OFF, self._fndh_port, timeout
                )

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=(ResultCode.FAILED, f"{ex}"),
                )

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(
                    ResultCode.OK,
                    f"Power off smartbox '{self._fndh_port} success'",
                ),
            )

    @check_communicating
    def turn_off_port(
        self: SmartBoxComponentManager,
        port_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a Port off.

        This may or may not have a Antenna attached.

        :param port_number: (one-based) number of the port to turn off.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_off_port,  # type: ignore[arg-type]
            args=[port_number],
            task_callback=task_callback,
        )

    def _turn_off_port(
        self: SmartBoxComponentManager,
        port_number: int,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")
            desired_port_powers: list[bool | None] = [
                None
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            desired_port_powers[port_number - 1] = False
            json_argument = json.dumps(
                {
                    "port_powers": desired_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            (
                result_code,
                return_message,
            ) = self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power off port '{port_number} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power off port '{port_number} success'",
            )
        return result_code, return_message

    @check_communicating
    def turn_on_port(
        self: SmartBoxComponentManager,
        port_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn a port on.

        This may or may not have a Antenna attached.

        :param port_number: (one-based) number of the port to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_on_port,  # type: ignore[arg-type]
            args=[
                port_number,
            ],
            task_callback=task_callback,
        )

    def _turn_on_port(
        self: SmartBoxComponentManager,
        port_number: int,
        task_callback: Optional[Callable],
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        try:
            if self._pasd_bus_proxy is None:
                raise NotImplementedError("pasd_bus_proxy is None")
            port = self.ports[port_number - 1]
            if self._fndh_port is None:
                msg = (
                    "Tried to turn on port of a smartbox, however the smartbox"
                    " cannot be turned on as it does not know its FNDH port."
                )
                self.logger.error(msg)
                return (ResultCode.FAILED, msg)
            # Turn smartbox standby if not already.
            if self._fndh_port_powers[self._fndh_port - 1] != PowerState.ON:
                assert port._port_id == port_number
                port.set_desire_on(task_callback)  # type: ignore[assignment]
                self._power_fndh_port(PowerState.ON, self._fndh_port, 60)
                return (
                    ResultCode.STARTED,
                    "The command will continue when the smartbox turns on.",
                )
            desired_port_powers: list[bool | None] = [
                None
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            desired_port_powers[port_number - 1] = True
            json_argument = json.dumps(
                {
                    "port_powers": desired_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            (
                result_code,
                return_message,
            ) = self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {ex}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result=f"Power on port '{port_number} failed'",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            self.logger.info(f"Port {port_number} turned on!")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=f"Power on port '{port_number} success'",
            )
        return result_code, return_message

    @check_communicating
    def set_port_powers(
        self: SmartBoxComponentManager,
        json_argument: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Set port powers.

        These ports will not have an antenna attached.

        :param json_argument: desired port powers of unmasked ports with
            smartboxes attached in json form.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._set_port_powers,  # type: ignore[arg-type]
            args=[json_argument],
            task_callback=task_callback,
        )

    def _set_port_powers(
        self: SmartBoxComponentManager,
        json_argument: str,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[ResultCode, str]:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        try:
            assert self._pasd_bus_proxy._proxy
            (
                result_code,
                unique_id,
            ) = self._pasd_bus_proxy.set_smartbox_port_powers(json_argument)

        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error(f"error {repr(ex)}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result="Set port powers failed",
                )

            return ResultCode.FAILED, "0"

        if task_callback:
            task_callback(
                status=TaskStatus.COMPLETED,
                result="Set port powers success",
            )
        return result_code, unique_id

    @check_communicating
    def write_attribute(
        self: SmartBoxComponentManager,
        attribute_name: str,
        value: Any,
    ) -> None:
        """
        Request to write an attribute via the proxy.

        :param attribute_name: the name of the Tango attribute.
        :param value: the value to write.
        """
        self._pasd_bus_proxy.write_attribute(attribute_name, value)
