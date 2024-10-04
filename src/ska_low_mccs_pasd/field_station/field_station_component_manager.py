#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for FieldStation."""
from __future__ import annotations

import functools
import importlib.resources
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Final, Optional

import jsonschema
import tango
from bidict import bidict
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common.component import DeviceComponentManager
from ska_low_mccs_common.component.command_proxy import MccsCommandProxy
from ska_low_mccs_common.component.composite_command_proxy import (
    CompositeCommandResultEvaluator,
    MccsCompositeCommandProxy,
)
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager
from ska_telmodel.data import TMData  # type: ignore

from ska_low_mccs_pasd.pasd_data import PasdData

from ..reference_data_store.pasd_config_client_server import PasdConfigurationClient

__all__ = ["FieldStationComponentManager"]


# pylint: disable=too-many-instance-attributes,  too-many-lines, abstract-method
class FieldStationComponentManager(TaskExecutorComponentManager):
    """A component manager for MccsFieldStation."""

    FIELDSTATION_ON_COMMAND_TIMEOUT = 600  # seconds
    CONFIGURATION_SCHEMA: Final = json.loads(
        importlib.resources.read_text(
            "ska_low_mccs_pasd.field_station.schemas",
            "MccsFieldStation_Updateconfiguration.json",
        )
    )
    CONFIGURATION_SCHEMA_TELMODEL: Final = json.loads(
        importlib.resources.read_text(
            "ska_low_mccs_pasd.field_station.schemas",
            "MccsFieldStation_UpdateConfiguration_Telmodel.json",
        )
    )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self: FieldStationComponentManager,
        logger: logging.Logger,
        configuration_host: str,
        configuration_port: int,
        configuration_timeout: int,
        station_name: str,
        fndh_name: str,
        smartbox_names: list[str],
        tm_config_details: Optional[list[str]],
        communication_state_callback: Callable[..., None],
        component_state_changed: Callable[..., None],
        configuration_change_callback: Callable[..., None],
        _fndh_proxy: Optional[DeviceComponentManager] = None,
        _smartbox_proxys: Optional[dict[str, DeviceComponentManager]] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param logger: a logger for this object to use
        :param configuration_host: the name of the service used to connect
            to the configuration host.
        :param configuration_port: the port to connect to the configuration
            host.
        :param configuration_timeout: the max time to wait before
            giving up on a connection.
        :param station_name: the station name.
        :param fndh_name: the name of the fndh this field station
            encompasses
        :param smartbox_names: the names of the smartboxes this field station
            encompasses
        :param tm_config_details: default location and filepath of the
            config in telmodel
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed: callback to be
            called when the component state changes
        :param configuration_change_callback: callback to be
            called when configuration changes.
        :param _fndh_proxy: a injected fndh proxy for purposes of testing only.
        :param _smartbox_proxys: injected smartbox proxys for purposes of testing only.
        """
        self._on_configuration_change = configuration_change_callback
        self._communication_state_callback: Callable[..., None]
        self._component_state_callback: Callable[..., None]
        self.outsideTemperature: Optional[float] = None
        self._antenna_mapping: dict = {}
        self._antenna_mask: dict = {}
        self._smartbox_mapping: dict = {}
        self._power_state: Optional[PowerState] = None
        self._power_state_lock = threading.RLock()

        self.fndh_port_states: list[Optional[bool]] = [
            None
        ] * PasdData.NUMBER_OF_FNDH_PORTS
        self._configuration_client = PasdConfigurationClient(
            configuration_host,
            configuration_port,
            station_name,
        )
        self.fndh_port_change = threading.Event()
        self.antenna_powers_changed = threading.Event()
        self.smartbox_power_change = threading.Event()

        self.has_antenna = False
        super().__init__(
            logger,
            communication_state_callback,
            component_state_changed,
        )
        self._communication_states = {
            fqdn: CommunicationStatus.DISABLED
            for fqdn in [fndh_name] + list(smartbox_names)
        }

        self._fndh_name = fndh_name
        self._fndh_proxy = _fndh_proxy or DeviceComponentManager(
            fndh_name,
            logger,
            functools.partial(self._device_communication_state_changed, fndh_name),
            functools.partial(self._component_state_callback, device_name=fndh_name),
        )
        self._smartbox_power_state = {}
        self._smartbox_proxys = {}
        self._smartbox_trl_name_map: bidict = bidict()
        if _smartbox_proxys:
            self._smartbox_proxys = _smartbox_proxys
        else:
            for smartbox_trl in smartbox_names:
                self._smartbox_power_state[smartbox_trl] = PowerState.UNKNOWN
                self._smartbox_proxys[smartbox_trl] = DeviceComponentManager(
                    smartbox_trl,
                    logger,
                    functools.partial(
                        self._device_communication_state_changed, smartbox_trl
                    ),
                    functools.partial(
                        self._component_state_callback, device_name=smartbox_trl
                    ),
                )

        # initialise the power
        self.antenna_powers: dict[str, PowerState] = {}

        self.logger = logger
        self.station_name = station_name

        if tm_config_details:
            self._load_configuration_uri(tm_config_details)
        else:
            self._load_configuration()

    def _update_mappings(
        self: FieldStationComponentManager,
        reference_data: dict[str, Any],
    ) -> None:
        """
        Update the internal maps from the reference data.

        This method is used to load validated data from the reference source
        and update the internal mappings.

        :param reference_data: the single source of truth for the
            field station port mapping information.
        """
        antenna_masks: dict = {}
        antenna_mapping: dict[str, tuple[str, int]] = {}
        smartbox_mappings: dict = {}

        for antenna_name, antenna_config in reference_data["antennas"].items():
            smartbox_name = antenna_config["smartbox"]
            smartbox_port = antenna_config["smartbox_port"]
            masked_state = antenna_config.get("masked") or False
            self.antenna_powers[antenna_name] = PowerState.UNKNOWN

            antenna_mapping[antenna_name] = (smartbox_name, smartbox_port)
            antenna_masks[antenna_name] = masked_state

        for smartbox_name, smartbox_config in reference_data["pasd"][
            "smartboxes"
        ].items():
            smartbox_mappings[smartbox_name] = smartbox_config["fndh_port"]

        self._antenna_mask = {"antennaMask": antenna_masks}
        self._smartbox_mapping = {"smartboxMapping": smartbox_mappings}
        self._antenna_mapping = {"antennaMapping": antenna_mapping}

        self.logger.info("Configuration has been successfully updated.")
        self._on_configuration_change(self._smartbox_mapping)

        if self._antenna_mapping:
            self.has_antenna = True

        self._update_smartbox_mask()

    def _update_smartbox_mask(self: FieldStationComponentManager) -> None:
        """Update the mask on the smartboxe for their ports."""
        try:
            for smartbox_trl, smartbox_proxy in self._smartbox_proxys.items():
                assert smartbox_proxy._proxy is not None
                smartbox_name = self._smartbox_trl_name_map[smartbox_trl]
                port_mask = self._get_smartbox_port_mask(smartbox_name)
                smartbox_proxy._proxy.portMask = port_mask
        except Exception:  # pylint: disable=broad-exception-caught
            self.logger.warning(
                "Tried to update smartbox port mask on smartboxes, "
                "however connection is not established. "
                "Will try again when connection established."
            )

    def start_communicating(self: FieldStationComponentManager) -> None:
        """Establish communication."""
        if self._communication_state == CommunicationStatus.ESTABLISHED:
            return

        if self._communication_state == CommunicationStatus.DISABLED:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

        self._fndh_proxy.start_communicating()
        for smartbox_trl, proxy in self._smartbox_proxys.items():
            proxy.start_communicating()
            smartbox_name = re.findall("sb[0-9]+", smartbox_trl)[0]
            self._smartbox_trl_name_map[smartbox_trl] = smartbox_name

    def stop_communicating(self: FieldStationComponentManager) -> None:
        """Break off communication with the PasdData."""
        self._fndh_proxy.stop_communicating()
        for proxy in self._smartbox_proxys.values():
            proxy.stop_communicating()

        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._update_communication_state(CommunicationStatus.DISABLED)

    def subscribe_to_attribute(
        self: FieldStationComponentManager,
        fqdn: str,
        attribute_name: str,
        callback: Callable,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Subscribe to an attribute on a device.

        :param fqdn: The device to subscribe too.
        :param attribute_name: the name of the attribute to subscribe to.
        :param callback: a callback to call on change.
        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._subscribe_to_attribute,  # type: ignore[arg-type]
            args=[fqdn, attribute_name, callback],
            task_callback=task_callback,
        )

    def _subscribe_to_attribute(
        self: FieldStationComponentManager,
        fqdn: str,
        attribute_name: str,
        callback: Callable,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        proxy_object = None
        if fqdn == self._fndh_name:
            proxy_object = self._fndh_proxy
        elif fqdn in self._smartbox_proxys:
            proxy_object = self._smartbox_proxys[fqdn]

        if (
            proxy_object is not None
            and proxy_object._proxy is not None
            and attribute_name.lower()
            not in proxy_object._proxy._change_event_callbacks.keys()
        ):
            try:
                proxy_object._proxy.add_change_event_callback(
                    attribute_name,
                    callback,
                    stateless=True,
                )
                self.logger.info(f"subscribed to {fqdn} {attribute_name}")

            except Exception:  # pylint: disable=broad-except
                self.logger.error(
                    f"Failed to make subscription to {fqdn} {attribute_name}"
                )

    def _on_field_conditions_change(
        self: FieldStationComponentManager,
        event_name: str,
        event_value: Any,
        event_quality: tango.AttrQuality,
    ) -> None:
        match event_name.lower():
            case "outsidetemperature":
                if event_quality == tango.AttrQuality.ATTR_VALID:
                    assert isinstance(event_value, float)
                    self.outsideTemperature = event_value
                    self._component_state_callback(
                        outsidetemperature=self.outsideTemperature
                    )
            case _:
                self.logger.error(f"Attribute name {event_name} Unknown")

    def _on_port_power_change(
        self: FieldStationComponentManager,
        smartbox_trl: str,
        event_name: str,
        event_value: list[bool] | None,
        event_quality: tango.AttrQuality,
    ) -> None:
        if event_value is None:
            self.logger.info(
                "Discarding empty port power changed event for smartbox {smartbox_name}"
            )
            return
        if smartbox_trl not in self._smartbox_trl_name_map.keys():
            self.logger.error(
                f"An unrecognised smartbox {smartbox_trl} "
                "had a change in its port powers"
            )
            return
        assert event_name.lower() == "portspowersensed"
        port_powers = [PowerState.UNKNOWN] * PasdData.NUMBER_OF_SMARTBOX_PORTS

        for i, value in enumerate(event_value):
            if value:
                port_powers[i] = PowerState.ON
            else:
                port_powers[i] = PowerState.OFF

        number_of_antenna_powers_updated = 0
        smartbox_name = self._smartbox_trl_name_map[smartbox_trl]
        for antenna_name, (
            antennas_smartbox_name,
            smartbox_port,
        ) in self._antenna_mapping["antennaMapping"].items():
            if antennas_smartbox_name == smartbox_name:
                if antenna_name in self.antenna_powers:
                    port_index = smartbox_port - 1
                    if 0 <= port_index < len(port_powers):
                        self.antenna_powers[antenna_name] = port_powers[port_index]
                        number_of_antenna_powers_updated += 1
                        if (
                            number_of_antenna_powers_updated
                            == PasdData.NUMBER_OF_SMARTBOX_PORTS
                        ):
                            # Max 12 antenna per smartbox. Therefore break.
                            break
                    else:
                        self.logger.warning(
                            "Warning: Invalid smartbox port index"
                            f"for antenna {antenna_name}"
                        )
                else:
                    self.logger.warning(
                        f"Warning: Antenna {antenna_name} not "
                        "found in antenna powers"
                    )
        self.antenna_powers_changed.set()
        self._component_state_callback(antenna_powers=self.antenna_powers)

    def _on_fndh_port_change(
        self: FieldStationComponentManager,
        event_name: str,
        event_value: list[Optional[bool]],
        event_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle change in fndh port powers.

        :param event_name: name of the event; will always be
            "portspowersensed" for this callback
        :param event_value: the new attribute value
        :param event_quality: the quality of the change event
        """
        assert event_name.lower() == "portspowersensed"
        self.fndh_port_states = event_value
        self.fndh_port_change.set()

    def smartbox_state_change(
        self: FieldStationComponentManager, smartbox_trl: str, power: PowerState
    ) -> None:
        """
        Register a state change for a smartbox.

        :param smartbox_trl: the name of the smartbox with a state change
        :param power: the power state of the smartbox.
        """
        self._smartbox_power_state[smartbox_trl] = power
        self.smartbox_power_change.set()
        self._evaluate_power_state()

    def _device_communication_state_changed(
        self: FieldStationComponentManager,
        fqdn: str,
        communication_state: CommunicationStatus,
    ) -> None:
        if communication_state == CommunicationStatus.ESTABLISHED:
            try:
                match fqdn:
                    case self._fndh_name:
                        self.subscribe_to_attribute(
                            fqdn, "OutsideTemperature", self._on_field_conditions_change
                        )
                        self.subscribe_to_attribute(
                            fqdn, "PortsPowerSensed", self._on_fndh_port_change
                        )
                    case _:
                        self.subscribe_to_attribute(
                            fqdn,
                            "PortsPowerSensed",
                            functools.partial(self._on_port_power_change, fqdn),
                        )

            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.error(f"failed to subscribe to {fqdn}: {e}")
        self._communication_states[fqdn] = communication_state
        self.logger.debug(
            f"device {fqdn} changed communcation state to {communication_state.name}"
        )
        if not self.has_antenna:
            self.logger.info("FieldStation has no antenna, Transitioning to `ON` ...")
            self._component_state_callback(power=PowerState.ON)

        if CommunicationStatus.DISABLED in self._communication_states.values():
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
        elif CommunicationStatus.NOT_ESTABLISHED in self._communication_states.values():
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)
        else:
            self._update_communication_state(CommunicationStatus.ESTABLISHED)
            self._update_smartbox_mask()

    def on(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn on the FieldStation.

        Turning on the FieldStation will distribute power
        to all antennas that make up that FieldStation.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._on,
            args=[],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(self._field_station_mapping_loaded, "On"),
        )

    def _on(  # noqa: C901
        self: FieldStationComponentManager,
        task_callback: Callable,
        ignore_mask: bool = False,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)
        failure_log = ""

        try:
            # Wait for the smartbox to change state
            timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
            fndh_result, time_left = self._power_fndh_ports(PowerState.ON, timeout)
            if fndh_result == ResultCode.OK:
                smartbox_on_commands = MccsCompositeCommandProxy(self.logger)
                for smartbox_trl in self._smartbox_proxys:
                    smartbox_on_commands += MccsCommandProxy(
                        smartbox_trl, "On", self.logger
                    )
                result, message = smartbox_on_commands(
                    command_evaluator=CompositeCommandResultEvaluator(),
                    timeout=time_left,
                )
                if result != ResultCode.OK:
                    loaded_composite_message = json.loads(message)
                    failure_log += (
                        f"MccsCompositeCommandProxy was not happy {result=}"
                        f" {json.dumps(loaded_composite_message, indent=4)}"
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            failure_log = f"Unhandled error when turning station on {e}, "

        if failure_log:
            self.logger.error(f"Failure in the `ON` command -> {failure_log}")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(result, message),
            )
            return

        self.logger.info("All unmasked antennas turned on.")
        task_callback(
            status=TaskStatus.COMPLETED,
            result=(ResultCode.OK, "All unmasked antennas turned on."),
        )

    def standby(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn the FieldStation to Standby.

        Turning the FieldStation to Standby will turn on all smartboxes,
        but leave their ports turned off.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._standby,
            args=[],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(
                self._field_station_mapping_loaded, "Standby"
            ),
        )

    def _standby(  # noqa: C901
        self: FieldStationComponentManager,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)

        failure_log = ""

        try:
            # Wait for the smartbox to change state
            timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
            fndh_result, time_left = self._power_fndh_ports(PowerState.ON, timeout)
            if fndh_result == ResultCode.OK:
                smartbox_standby_commands = MccsCompositeCommandProxy(self.logger)
                for smartbox_trl in self._smartbox_proxys:
                    smartbox_standby_commands += MccsCommandProxy(
                        smartbox_trl, "Standby", self.logger
                    )
                result, message = smartbox_standby_commands(
                    command_evaluator=CompositeCommandResultEvaluator(),
                    timeout=time_left,
                )
                if result != ResultCode.OK:
                    loaded_composite_message = json.loads(message)
                    failure_log += (
                        f"MccsCompositeCommandProxy was not happy {result=}"
                        f" {json.dumps(loaded_composite_message, indent=4)}"
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            failure_log = f"Unhandled error when turning station standby {e}, "

        if failure_log:
            self.logger.error(f"Failure in the `STANDBY` command -> {failure_log}")
            task_callback(
                status=TaskStatus.COMPLETED,
                result=(result, message),
            )
            return

        self.logger.info("All FNDH ports turned on. All Smartbox ports turn off.")
        task_callback(
            status=TaskStatus.COMPLETED,
            result=(
                ResultCode.OK,
                "All FNDH ports turned on. All Smartbox ports turn off.",
            ),
        )

    def _power_fndh_ports(
        self: FieldStationComponentManager,
        power: PowerState,
        timeout: int,
    ) -> tuple[ResultCode, int]:
        assert self._fndh_proxy._proxy
        result = ResultCode.FAILED

        desired_fndh_port_powers: list[bool | None] = [
            power == PowerState.ON
        ] * PasdData.NUMBER_OF_FNDH_PORTS

        # We only want to turn ON ports with smartboxes, but we do want to turn OFF
        # ports without smartboxes.
        for fndh_port, fndh_port_state in enumerate(
            self._get_fndh_ports_with_smartboxes()
        ):
            if fndh_port_state is False:
                desired_fndh_port_powers[fndh_port] = False
        json_argument = json.dumps(
            {
                "port_powers": desired_fndh_port_powers,
                "stay_on_when_offline": True,
            }
        )
        [set_fndh_port_powers_result], _ = self._fndh_proxy._proxy.SetPortPowers(
            json_argument
        )
        if set_fndh_port_powers_result == ResultCode.QUEUED:
            t1 = time.time()
            self.logger.info(
                f"waiting on fndh ports to change in {timeout} seconds ..."
            )
            result = self.wait_for_fndh_port(desired_fndh_port_powers, timeout)

            t2 = time.time()
            time_taken = int(t2 - t1)
            timeout -= time_taken

        return result, timeout

    def wait_for_fndh_port(  # noqa: C901
        self: FieldStationComponentManager, desired: list[Optional[bool]], timeout: int
    ) -> ResultCode:
        """
        Wait for the fndh ports to change state to a desired state.

        :param desired: the desired port powers looks like `[False]*28`
        :param timeout: the maximum time to wait in seconds (s)

        :return: A ResultCode and a string.
        """

        def _fndh_ports_match_desired(
            current_state: list[Optional[bool]], desired_state: list[Optional[bool]]
        ) -> bool:
            for port_idx, port_state in enumerate(desired_state):
                if port_state is not None:
                    if current_state[port_idx] != port_state:
                        return False
            return True

        # Wait for port to match the desired state, raise Timeout error if
        # not completed in time.
        if not _fndh_ports_match_desired(self.fndh_port_states, desired):
            # Wait for a callback.
            t1 = time.time()
            self.fndh_port_change.wait(timeout)
            t2 = time.time()
            time_waited = t2 - t1
            if (
                self.fndh_port_change.is_set()
                and timeout > 0
                and time_waited <= timeout
            ):
                self.fndh_port_change.clear()
                remaining_time = timeout - int(time_waited)
                return self.wait_for_fndh_port(desired, remaining_time)
            self.logger.error("Timeout waiting for fndh ports to change state.")
            return ResultCode.FAILED

        self.logger.info("All FNDH ports reached desired state.")
        return ResultCode.OK

    def off(
        self: FieldStationComponentManager, task_callback: Optional[Callable] = None
    ) -> tuple[TaskStatus, str]:
        """
        Turn off the FieldStation.

        Turning off the FieldStation will cut off power
        to all antennas that make up that FieldStation.

        :param task_callback: Update task state, defaults to None

        :return: a result code and a unique_id or message.
        """
        return self.submit_task(
            self._off,
            args=[],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(self._field_station_mapping_loaded, "Off"),
        )

    def _off(
        self: FieldStationComponentManager,
        task_callback: Callable,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        task_callback(status=TaskStatus.IN_PROGRESS)

        failure_log = ""

        try:
            # Wait for the smartbox to change state
            timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
            self._power_fndh_ports(PowerState.OFF, timeout)

        except Exception as e:  # pylint: disable=broad-exception-caught
            failure_log = f"Unhandled error when turning station off {e}, "

        if failure_log:
            self.logger.error(f"Failure in the `OFF` command -> {failure_log}")
            task_callback(
                status=TaskStatus.FAILED,
                result=(ResultCode.FAILED, "Didn't turn off all FNDH ports."),
            )
            return

        self.logger.info("All FNDH ports turned off. All Smartbox ports turned off.")
        task_callback(
            status=TaskStatus.COMPLETED,
            result=(
                ResultCode.OK,
                "All FNDH ports turned off. All Smartbox ports turned off.",
            ),
        )

    def _get_masked_smartbox_ports(
        self: FieldStationComponentManager,
    ) -> dict[str, list]:
        """
        Get which ports are masked on each smartbox.

        This will return a dictionary, containing keys for each smartbox,
        and values which are lists containing which port is masked.

        e.g {sb01 : [4,5]}. Smartbox 1 has ports 4 and 5 masked.

        :returns: which ports are masked on each smartbox.
        """
        # A smartbox port will be masked if either there is no antenna
        # attached to the port or the antenna attached to the port is
        # masked
        # smartbox_name : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[str, list] = {}
        for antenna_name, antenna_masked in self._antenna_mask["antennaMask"].items():
            if antenna_masked:
                smartbox_name, smartbox_port = self._antenna_mapping["antennaMapping"][
                    antenna_name
                ]
                try:
                    masked_smartbox_ports[smartbox_name]
                except KeyError:
                    masked_smartbox_ports[smartbox_name] = []
                masked_smartbox_ports[smartbox_name].append(smartbox_port)

        # mask all smartbox ports with no antenna attached.
        for smartbox_name in self._smartbox_trl_name_map.values():
            for smartbox_port, port_has_antenna in enumerate(
                self._get_smartbox_ports_with_antennas(smartbox_name), start=1
            ):
                if not port_has_antenna:
                    try:
                        masked_smartbox_ports[smartbox_name]
                    except KeyError:
                        masked_smartbox_ports[smartbox_name] = []
                    masked_smartbox_ports[smartbox_name].append(smartbox_port)

        return masked_smartbox_ports

    def _get_smartbox_port_mask(
        self: FieldStationComponentManager, smartbox_name: str
    ) -> list[bool]:
        """
        Get the port mask for a given (0-indexed) smartbox no.

        This will return an array of 12 bools, one for each smartbox port.

        :param smartbox_name: which smartbox to get the port mask of.

        :returns: the port mask for the given smartbox.
        """
        all_smartbox_masked_ports = self._get_masked_smartbox_ports()
        port_mask = [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS
        masked_ports = all_smartbox_masked_ports.get(smartbox_name, [])
        for masked_port in masked_ports:
            port_mask[masked_port - 1] = True
        return port_mask

    def _get_smartbox_ports_with_antennas(
        self: FieldStationComponentManager, smartbox_name: str
    ) -> list:
        smartbox_ports = [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS
        for antenna_smartbox_name, antennas_smartbox_port in list(
            self._antenna_mapping["antennaMapping"].values()
        ):
            if antenna_smartbox_name == smartbox_name:
                smartbox_ports[antennas_smartbox_port - 1] = True
        return smartbox_ports

    def _get_fndh_ports_with_smartboxes(self: FieldStationComponentManager) -> list:
        fndh_ports = [False] * PasdData.NUMBER_OF_FNDH_PORTS
        for fndh_port in list(self._smartbox_mapping["smartboxMapping"].values()):
            fndh_ports[fndh_port - 1] = True

        return fndh_ports

    @check_communicating
    def turn_on_antenna(
        self: FieldStationComponentManager,
        antenna_name: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn on an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        :param antenna_name: (one-based) number of the Antenna to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_on_antenna,  # type: ignore[arg-type]
            args=[
                antenna_name,
            ],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(
                self._field_station_mapping_loaded, "PowerOnAntenna"
            ),
        )

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_on_antenna(  # noqa: C901, pylint: disable=too-many-branches
        self: FieldStationComponentManager,
        antenna_name: str,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
        assert self._fndh_proxy._proxy is not None
        if not ignore_mask and (self._antenna_mask["antennaMask"][antenna_name]):
            msg = (
                f"Antenna number {antenna_name} is masked, call "
                "with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if ignore_mask:
            self.logger.warning("Turning on masked antenna")
        smartbox_name, smartbox_port = self._antenna_mapping["antennaMapping"][
            antenna_name
        ]
        try:
            smartbox_trl = self._smartbox_trl_name_map.inverse[smartbox_name]
            smartbox_proxy = self._smartbox_proxys[smartbox_trl]
        except IndexError:
            msg = (
                f"Tried to turn on antenna {antenna_name}, this is mapped to "
                f"smartbox {smartbox_name}, port {smartbox_port}. However this smartbox"
                " device is not deployed"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED
        fndh_port = self._smartbox_mapping["smartboxMapping"][smartbox_name]

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        if not self._fndh_proxy._proxy.PortsPowerSensed[fndh_port]:
            result, _ = self._fndh_proxy._proxy.PowerOnPort(fndh_port)

        assert smartbox_proxy._proxy is not None

        if not smartbox_proxy._proxy.PortsPowerSensed[smartbox_port - 1]:
            if result is None or result[0] in [
                ResultCode.OK,
                ResultCode.STARTED,
                ResultCode.QUEUED,
            ]:
                result, _ = smartbox_proxy._proxy.PowerOnPort(smartbox_port)
        if result is None:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"antenna {antenna_name} was already on.",
                )
            return TaskStatus.COMPLETED
        if result[0] in [
            ResultCode.OK,
            ResultCode.STARTED,
            ResultCode.QUEUED,
        ]:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"turn on antenna {antenna_name} success.",
                )
            return TaskStatus.COMPLETED
        if task_callback:
            task_callback(status=TaskStatus.FAILED)

        return TaskStatus.FAILED

    @check_communicating
    def turn_off_antenna(
        self: FieldStationComponentManager,
        antenna_name: str,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn off an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        :param antenna_name: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_off_antenna,  # type: ignore[arg-type]
            args=[
                antenna_name,
            ],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(
                self._field_station_mapping_loaded, "PowerOffAntenna"
            ),
        )

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_off_antenna(  # noqa: C901
        self: FieldStationComponentManager,
        antenna_name: str,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
        assert self._fndh_proxy._proxy is not None
        if not ignore_mask and self._antenna_mask["antennaMask"][antenna_name]:
            msg = (
                f"Antenna number {antenna_name} is masked, call "
                "with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if ignore_mask:
            self.logger.warning("Turning off masked antenna")

        smartbox_name, smartbox_port = self._antenna_mapping["antennaMapping"][
            antenna_name
        ]
        try:
            smartbox_trl = self._smartbox_trl_name_map.inverse[smartbox_name]
            smartbox_proxy = self._smartbox_proxys[smartbox_trl]
        except IndexError:
            msg = (
                f"Tried to turn off antenna {antenna_name}, this is mapped to "
                f"smartbox {smartbox_name}, port {smartbox_port}. However this smartbox"
                " device is not deployed"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED
        fndh_port = self._smartbox_mapping["smartboxMapping"][smartbox_name]

        try:
            assert self._fndh_proxy._proxy.PortsPowerSensed[fndh_port - 1]
        except AssertionError:
            msg = (
                f"Tried to turn off antenna {antenna_name}, this is mapped to "
                f"smartbox {smartbox_name}, which is on fndh port {fndh_port}."
                " However this port is not powered on."
            )
            self.logger.warning(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        assert smartbox_proxy._proxy is not None
        result, _ = smartbox_proxy._proxy.PowerOffPort(smartbox_port)

        if result[0] in [
            ResultCode.OK,
            ResultCode.STARTED,
            ResultCode.QUEUED,
        ]:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"turn off antenna {antenna_name} success.",
                )
            return TaskStatus.COMPLETED
        if task_callback:
            task_callback(status=TaskStatus.FAILED)
        return TaskStatus.FAILED

    def update_antenna_mask(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus, str]:
        """
        Manually update the antenna mask.

        :param task_callback: callback to be called when the status of
            the command changes
        :param kwargs: dict containing masking state for all antennas.

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._update_antenna_mask,  # type: ignore[arg-type]
            kwargs=kwargs,
            task_callback=task_callback,
        )

    def _update_antenna_mask(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        antenna_mask = kwargs["antennaMask"]
        for antenna_name, masking_state in antenna_mask.items():
            if antenna_name is not None and masking_state is not None:
                self._antenna_mask["antennaMask"][antenna_name] = masking_state
        if task_callback:
            task_callback(status=TaskStatus.COMPLETED)

    def update_antenna_mapping(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus, str]:
        """
        Manually update the antenna mapping.

        :param task_callback: callback to be called when the status of
            the command changes
        :param kwargs: dict containing mapping for all antennas.

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._update_antenna_mapping,  # type: ignore[arg-type]
            kwargs=kwargs,
            task_callback=task_callback,
        )

    def _update_antenna_mapping(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        antenna_mapping = kwargs["antennaMapping"]
        for (
            antenna_name,
            values,
        ) in antenna_mapping.items():
            smartbox_name = values["smartboxID"]
            smartbox_port = values["smartboxPort"]
            if (
                antenna_name is not None
                and smartbox_name is not None
                and smartbox_port is not None
            ):
                if antenna_name in self._antenna_mapping["antennaMapping"]:
                    self._antenna_mapping["antennaMapping"][antenna_name] = (
                        smartbox_name,
                        smartbox_port,
                    )
                else:
                    self.logger.info(f"antenna {antenna_name} not in antenna mapping")

        if task_callback:
            task_callback(status=TaskStatus.COMPLETED)

    def update_smartbox_mapping(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus, str]:
        """
        Manually update the smartbox mapping.

        :param task_callback: callback to be called when the status of
            the command changes
        :param kwargs: dict containing mapping for all smartboxes.

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._update_smartbox_mapping,  # type: ignore[arg-type]
            kwargs=kwargs,
            task_callback=task_callback,
        )

    def _update_smartbox_mapping(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> None:
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        smartbox_mapping = kwargs["smartboxMapping"]
        mapping_new = {}
        for smartbox_name, fndh_port in smartbox_mapping.items():
            if smartbox_name is not None and fndh_port is not None:
                mapping_new[smartbox_name] = fndh_port

        self._smartbox_mapping["smartboxMapping"] = mapping_new

        self._on_configuration_change({"smartboxMapping": mapping_new})
        if task_callback:
            task_callback(status=TaskStatus.COMPLETED)

    def configure(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus | ResultCode, str]:
        """
        Configure the field station.

        Currently this only supports configuring FNDH alarm thresholds.

        :param task_callback: callback to be called when the status of
            the command changes
        :param kwargs: keyword arguments extracted from the JSON string.

        :return: the task status and a human-readable status message
        """
        command_proxy = MccsCommandProxy(self._fndh_name, "Configure", self.logger)
        return command_proxy(json.dumps(kwargs), task_callback=task_callback)

    def load_configuration(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the LoadConfiguration slow command.

        This method returns immediately after it is submitted for
        execution.

        :param task_callback: Update task state, defaults to None
        :param task_abort_event: Check for abort, defaults to None
        :return: Task status and response message
        """
        return self.submit_task(
            self._load_configuration,
            args=[],
            task_callback=task_callback,
        )

    def load_configuration_uri(
        self: FieldStationComponentManager,
        tm_config_details: Optional[list[str]],
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Submit the LoadConfigurationUri slow command.

        This method returns immediately after it is submitted for
        execution.

        :param tm_config_details: Location of the config in telmodel
        :param task_callback: Update task state, defaults to None
        :param task_abort_event: Check for abort, defaults to None
        :return: Task status and response message
        """
        return self.submit_task(
            self._load_configuration_uri,
            args=[tm_config_details],
            task_callback=task_callback,
        )

    def _load_configuration(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Get the configuration from the configuration server.

        :param task_callback: Update task state, defaults to None
        :param task_abort_event: Check for abort, defaults to None
        """
        try:
            self.logger.info("Attempting to load data from configuration server.....")
            configuration = self._configuration_client.get_config()
            self.logger.info("Configuration loaded from configuration server")

            # Validate configuration before updating.
            jsonschema.validate(configuration, self.CONFIGURATION_SCHEMA_TELMODEL)

            self._update_mappings(configuration)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error(f"Failed to update configuration {repr(e)}.")
            if task_callback is not None:
                task_callback(
                    TaskStatus.FAILED,
                    result="Failed to load configuration.",
                )
        if task_callback is not None:
            task_callback(
                TaskStatus.COMPLETED,
                result="Configuration has been retreived successfully.",
            )

    def _find_by_key(
        self: FieldStationComponentManager, data: dict, target: str
    ) -> Optional[dict]:
        """
        Traverse nested dictionary, yield next value for given target.

        :param data: generic nested dictionary to traverse through.
        :param target: key to find the next value of.

        :return: the value for given key.
        """
        for key, value in data.items():
            if key == target:
                return value
            if isinstance(value, dict):
                item = self._find_by_key(value, target)
                if item is not None:
                    return item
        return None

    def _load_configuration_uri(
        self: FieldStationComponentManager,
        tm_config_details: list[str],
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Get the configuration from the configuration server.

        :param tm_config_details: Location of the config in telmodel
        :param task_callback: Update task state, defaults to None
        :param task_abort_event: Check for abort, defaults to None

        :raises ValueError: If the station name key cant be found.
        """
        try:
            config_uri = tm_config_details[0]
            config_filepath = tm_config_details[1]
            station_name = tm_config_details[2]

            tmdata = TMData([config_uri])
            full_dict = tmdata[config_filepath].get_dict()

            configuration = self._find_by_key(full_dict, str(station_name))

            if configuration is None:
                raise ValueError("Key not found in config")

            # Validate configuration before updating.
            jsonschema.validate(configuration, self.CONFIGURATION_SCHEMA_TELMODEL)

            self._update_mappings(configuration)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error(f"Failed to update configuration from URI {repr(e)}.")
            if task_callback is not None:
                task_callback(
                    TaskStatus.FAILED,
                    result="Failed to load configuration from URI.",
                )
        if task_callback is not None:
            task_callback(
                TaskStatus.COMPLETED,
                result="Configuration has been retreived successfully.",
            )

    def _field_station_mapping_loaded(
        self: FieldStationComponentManager, command_name: str
    ) -> bool:
        """
        Return true if fieldstation has loaded mapping.

        :param command_name: the name of the command that requires this check
            for logging purposes only.

        :return: True if complete fieldStation mapping is loaded
        """
        if not all(
            [
                self._antenna_mapping,
                self._antenna_mask,
                self._smartbox_mapping,
            ]
        ):
            self.logger.warning(
                f"Incomplete mapping present, unable to execute command {command_name}"
            )
            return False
        return True

    def _evaluate_power_state(self: FieldStationComponentManager) -> None:  # noqa: C901
        """
        Evaluate the power state of the FieldStation.

        * FieldStation is ON if any smartboxes are ON.
        * FieldStation is STANDBY if any smartboxes are STANDBY.
        * FieldStation is OFF if all smartboxes are OFF.
        * FieldStation is UNKNOWN if none of these were matched.
        """
        # We don't want to take into account UNKNOWN smartboxes here, that's taken care
        # in the healthState.
        trimmed_smartbox_power_states = [
            smartbox_power_state
            for smartbox_power_state in self._smartbox_power_state.values()
            if smartbox_power_state != PowerState.UNKNOWN
        ]

        def transition_to(power_state: PowerState, msg: str | None = None) -> None:
            if self._power_state != power_state:
                self.logger.info(
                    msg
                    or f"At least one Smartbox is {power_state.name}, "
                    f"FieldStation transitioning to {power_state.name} state ...."
                )
                self._power_state = power_state
                self._component_state_callback(power=power_state)

        if trimmed_smartbox_power_states:
            with self._power_state_lock:
                match self._smartbox_power_state:
                    case _ if PowerState.ON in trimmed_smartbox_power_states:
                        transition_to(PowerState.ON)
                    case _ if PowerState.STANDBY in trimmed_smartbox_power_states:
                        transition_to(PowerState.STANDBY)
                    case _ if all(
                        power == PowerState.OFF
                        for power in trimmed_smartbox_power_states
                    ):
                        transition_to(
                            PowerState.OFF,
                            msg=(
                                "All smartboxes are `OFF`, "
                                "FieldStation transitioning to `OFF` state ...."
                            ),
                        )
                    case _:
                        transition_to(
                            PowerState.UNKNOWN,
                            msg=(
                                "No PowerState rules matched, "
                                "FieldStation transitioning to `UNKNOWN` state ...."
                            ),
                        )
