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
import threading
import time
from typing import Any, Callable, Final, Optional

import jsonschema
import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager
from ska_telmodel.data import TMData  # type: ignore

from ska_low_mccs_pasd.pasd_data import PasdData

from ..command_proxy import MccsCommandProxy
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

    # pylint: disable=too-many-arguments, too-many-locals
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
        _smartbox_proxys: Optional[list[DeviceComponentManager]] = None,
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
        self._antenna_mapping: dict[str, list[int]] = {}
        self._all_masked = False
        self._antenna_mask: list[bool] = []
        self._antenna_mask_telmodel: dict = {}
        self._smartbox_mapping: dict[str, int] = {}

        max_workers = 1
        self.fndh_port_states: list[Optional[bool]] = [
            None
        ] * PasdData.NUMBER_OF_FNDH_PORTS
        self._configuration_client = PasdConfigurationClient(
            configuration_host,
            configuration_port,
            station_name,
        )
        self._antenna_mask_pretty: Optional[dict[str, Any]] = None
        self._antenna_mapping_pretty: Optional[dict[str, Any]] = None
        self._smartbox_mapping_pretty: Optional[dict[str, Any]] = None
        self.fndh_port_change = threading.Event()
        self.antenna_powers_changed = threading.Event()
        self.smartbox_power_change = threading.Event()

        self.has_antenna = False
        super().__init__(
            logger,
            communication_state_callback,
            component_state_changed,
            max_workers=max_workers,
        )
        self._communication_states = {
            fqdn: CommunicationStatus.DISABLED
            for fqdn in [fndh_name] + list(smartbox_names)
        }

        self._fndh_name = fndh_name
        self._fndh_proxy = _fndh_proxy or DeviceComponentManager(
            fndh_name,
            logger,
            max_workers,
            functools.partial(self._device_communication_state_changed, fndh_name),
            functools.partial(self._component_state_callback, device_name=fndh_name),
        )
        self._smartbox_power_state = []
        self._smartbox_proxys = []
        smartbox_count = 0
        self._smartbox_name_number_map: dict[str, int] = {}
        if _smartbox_proxys:
            self._smartbox_proxys = _smartbox_proxys
        else:
            for smartbox_name in smartbox_names:
                self._smartbox_power_state.append(PowerState.UNKNOWN)
                self._smartbox_proxys.append(
                    DeviceComponentManager(
                        smartbox_name,
                        logger,
                        max_workers,
                        functools.partial(
                            self._device_communication_state_changed, smartbox_name
                        ),
                        functools.partial(
                            self._component_state_callback, device_name=smartbox_name
                        ),
                    )
                )
                self._smartbox_name_number_map.update({smartbox_name: smartbox_count})
                smartbox_count += 1

        # initialise the power
        self.antenna_powers: dict[str, PowerState] = {}
        for antenna_id in range(1, PasdData.NUMBER_OF_ANTENNAS + 1):
            self.antenna_powers[str(antenna_id)] = PowerState.UNKNOWN

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
        antenna_masks_pretty: list[dict] = [{}] * PasdData.NUMBER_OF_ANTENNAS
        antenna_mapping_pretty: list[dict] = [{}] * PasdData.NUMBER_OF_ANTENNAS
        smartbox_mapping_pretty: list[dict] = [
            {}
        ] * PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION

        antenna_masks_logical: list[bool] = [False] * (PasdData.NUMBER_OF_ANTENNAS + 1)
        antenna_mapping_logical: dict[str, list[int]] = {}
        smartbox_mappings_logical: dict[str, int] = {}

        all_masked = True

        for antenna_id, antenna_config in reference_data["antennas"].items():
            smartbox_id = int(antenna_config["smartbox"])
            smartbox_port = int(antenna_config["smartbox_port"])
            masked_state = bool(antenna_config["masked"])

            antenna_mapping_pretty[int(antenna_id) - 1] = {
                "antennaID": int(antenna_id),
                "smartboxID": smartbox_id,
                "smartboxPort": smartbox_port,
            }
            antenna_mapping_logical[str(antenna_id)] = [smartbox_id, smartbox_port]

            antenna_masks_pretty[int(antenna_id) - 1] = {
                "antennaID": int(antenna_id),
                "maskingState": masked_state,
            }
            if not masked_state:
                all_masked = False

            antenna_masks_logical[int(antenna_id)] = masked_state

        for smartbox_id, smartbox_config in reference_data["pasd"][
            "smartboxes"
        ].items():
            smartbox_mapping_pretty[int(smartbox_id) - 1] = {
                "smartboxID": int(smartbox_id),
                "fndhPort": smartbox_config["fndh_port"],
            }
            smartbox_mappings_logical[str(smartbox_id)] = smartbox_config["fndh_port"]

        antenna_masks_logical[0] = all_masked

        self._antenna_mask_pretty = {"antennaMask": antenna_masks_pretty}
        self._smartbox_mapping_pretty = {"smartboxMapping": smartbox_mapping_pretty}
        self._antenna_mapping_pretty = {"antennaMapping": antenna_mapping_pretty}

        self._antenna_mask = antenna_masks_logical
        self._smartbox_mapping = smartbox_mappings_logical
        self._antenna_mapping = antenna_mapping_logical

        self.logger.info("Configuration has been successfully updated.")
        self._on_configuration_change(self._smartbox_mapping_pretty)

        if self._antenna_mapping:
            self.has_antenna = True

    def start_communicating(self: FieldStationComponentManager) -> None:
        """Establish communication."""
        if self._communication_state == CommunicationStatus.ESTABLISHED:
            return

        if self._communication_state == CommunicationStatus.DISABLED:
            self._update_communication_state(CommunicationStatus.NOT_ESTABLISHED)

        self._fndh_proxy.start_communicating()
        for proxy in self._smartbox_proxys:
            proxy.start_communicating()

    def stop_communicating(self: FieldStationComponentManager) -> None:
        """Break off communication with the PasdData."""
        self._fndh_proxy.stop_communicating()
        for proxy in self._smartbox_proxys:
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
        elif fqdn in self._smartbox_name_number_map:
            smartbox_no = self._smartbox_name_number_map[fqdn]
            proxy_object = self._smartbox_proxys[smartbox_no]

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
        smartbox_name: str,
        event_name: str,
        event_value: list[bool] | None,
        event_quality: tango.AttrQuality,
    ) -> None:
        if event_value is None:
            self.logger.info(
                "Discarding empty port power changed event for smartbox {smartbox_name}"
            )
            return
        if smartbox_name not in self._smartbox_name_number_map:
            self.logger.error(
                f"An unrecognised smartbox {smartbox_name}"
                "had a change in its port powers"
            )
            return
        smartbox_number = self._smartbox_name_number_map[smartbox_name] + 1
        assert event_name.lower() == "portspowersensed"
        port_powers = [PowerState.UNKNOWN] * PasdData.NUMBER_OF_SMARTBOX_PORTS

        for i, value in enumerate(event_value):
            if value:
                port_powers[i] = PowerState.ON
            else:
                port_powers[i] = PowerState.OFF

        number_of_antenna_powers_updated = 0
        for antenna_id, (
            antennas_smartbox,
            smartbox_port,
        ) in self._antenna_mapping.items():
            if antennas_smartbox == smartbox_number:
                str_antenna_id = str(antenna_id)
                if str_antenna_id in self.antenna_powers:
                    port_index = smartbox_port - 1
                    if 0 <= port_index < len(port_powers):
                        self.antenna_powers[str_antenna_id] = port_powers[port_index]
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
                            f"for antenna {str_antenna_id}"
                        )
                else:
                    self.logger.warning(
                        f"Warning: Antenna {str_antenna_id} not "
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
        self: FieldStationComponentManager, smartbox_name: str, power: PowerState
    ) -> None:
        """
        Register a state change for a smartbox.

        :param smartbox_name: the name of the smartbox with a state change
        :param power: the power state of the smartbox.
        """
        smartbox_id = self._smartbox_name_number_map[smartbox_name]
        self._smartbox_power_state[smartbox_id] = power
        self.smartbox_power_change.set()

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
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        if not ignore_mask and self._antenna_mask[0]:
            msg = (
                "Antennas in this station are masked, "
                "call with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        try:
            # Wait for the smartbox to change state
            timeout = self.FIELDSTATION_ON_COMMAND_TIMEOUT
            failure_log = self._turn_on_station(timeout)

        except TimeoutError as e:
            failure_log = f"Timeout when turning station on {e}, "

        except Exception as e:  # pylint: disable=broad-exception-caught
            failure_log = f"Unhandled error when turning station on {e}, "

        if failure_log:
            self.logger.error(f"Failure in the `ON` command -> {failure_log}")
            if task_callback:
                task_callback(
                    status=TaskStatus.FAILED,
                    result="Didn't turn on all unmasked antennas.",
                )
            return

        if task_callback:
            self.logger.info("All unmasked antennas turned on.")
            task_callback(
                status=TaskStatus.COMPLETED,
                result="All unmasked antennas turned on.",
            )

    def _get_desired_smartbox_powers(
        self: FieldStationComponentManager,
        desired_fndh_port_powers: list[bool | None],
    ) -> list[bool | None]:
        desired_smartbox_power: list[bool | None] = [None] * len(self._smartbox_proxys)
        for smartbox_idx, smartbox_proxy in enumerate(self._smartbox_proxys):
            assert smartbox_proxy._proxy is not None
            fndh_port = json.loads(smartbox_proxy._proxy.fndhPort)
            if fndh_port is None:
                self.logger.error(
                    "Unable to determine the smartbox desired power! "
                    f"smartbox {smartbox_proxy._name} does not know its fndh port"
                )
                raise ValueError("Smartbox attribute fndhPort has non integer value.")
            desired_smartbox_power[smartbox_idx] = desired_fndh_port_powers[
                fndh_port - 1
            ]
        return desired_smartbox_power

    def turn_on_unmasked_smartbox_ports(
        self: FieldStationComponentManager, masked_smartbox_ports: dict[int, list]
    ) -> list[ResultCode]:
        """
        Turn on all smartbox ports that are not masked.

        :param masked_smartbox_ports: a map containing the masked ports for a
            specified logical smartbox.

        :returns: a list containing the Resultcode of each `ON` command.
        """
        results = []
        masked_ports = []
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys, start=1):
            assert smartbox._proxy
            desired_smartbox_port_powers: list[bool | None] = [
                True
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            masked_ports = masked_smartbox_ports.get(smartbox_no, [])
            for masked_port in masked_ports:
                desired_smartbox_port_powers[masked_port - 1] = None
            json_argument = json.dumps(
                {
                    "port_powers": desired_smartbox_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            result, _ = smartbox._proxy.SetPortPowers(json_argument)
            results += result
        return results

    def _turn_on_station(  # noqa: C901
        self: FieldStationComponentManager,
        timeout: int,
    ) -> str:
        """
        Turn on this stations unmasked antenna.

        :param timeout: the maximum time to wait in seconds (s)

        :return: A string containing a failure message, empty when no failure.
        """
        failure_log = ""
        assert self._fndh_proxy._proxy
        masked_smartbox_ports: dict[int, list] = self._get_masked_smartbox_ports()
        masked_fndh_ports: list = self._get_masked_fndh_ports(masked_smartbox_ports)

        desired_fndh_port_powers: list[bool | None] = [
            True
        ] * PasdData.NUMBER_OF_FNDH_PORTS
        for masked_port in masked_fndh_ports:
            desired_fndh_port_powers[masked_port - 1] = None

        desired_smartbox_power: list = self._get_desired_smartbox_powers(
            desired_fndh_port_powers
        )
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
            self.wait_for_fndh_port(desired_fndh_port_powers, timeout)

            t2 = time.time()
            time_taken = int(t2 - t1)
            timeout -= time_taken

            self.logger.info(
                f"waiting on smartboxes to change state in {timeout} seconds ..."
            )

            self.wait_for_smartbox_device_state(desired_smartbox_power, timeout)
            t3 = time.time()
            time_taken = int(t3 - t2)
            timeout -= time_taken

            # Now the smartbox are all on we can turn on the ports
            # with unmasked antenna
            results = self.turn_on_unmasked_smartbox_ports(masked_smartbox_ports)
            if all(result == ResultCode.QUEUED for result in results):
                self.logger.info(
                    f"waiting on antenna to change state in {timeout} seconds ..."
                )
                desired_antenna_powers = self._calculate_desired_antenna_powers(
                    masked_smartbox_ports, PowerState.ON
                )
                self.wait_for_antenna_powers(desired_antenna_powers, timeout)
                t4 = time.time()
                time_taken = int(t4 - t3)
                timeout -= time_taken
                self.logger.info(
                    "All unmasked antenna have been turned on with"
                    f" {timeout} seconds left till timeout"
                )
            else:
                failure_log = "Failed to execute `ON` command for smartbox ports, "
        else:
            failure_log = (
                "Turning on all antenna in the station Failed, "
                "Command `fndh_proxy.SetPortPowers` failed, "
            )

        return failure_log

    def _calculate_desired_antenna_powers(
        self: FieldStationComponentManager,
        masked_smartbox_ports: dict[int, list],
        desired_power_state: PowerState,
    ) -> list[PowerState | None]:
        desired_power: list[PowerState | None] = [None] * PasdData.NUMBER_OF_ANTENNAS
        # Set the desired power states for unmasked antenna with a mapping.
        for antenna_id, (smartbox_id, smartbox_port) in self._antenna_mapping.items():
            for masked_smartbox_id, masked_ports in masked_smartbox_ports.items():
                if int(masked_smartbox_id) == int(smartbox_id):
                    if int(smartbox_port) not in masked_ports:
                        desired_power[int(antenna_id) - 1] = desired_power_state
        return desired_power

    def wait_for_fndh_port(  # noqa: C901
        self: FieldStationComponentManager, desired: list[Optional[bool]], timeout: int
    ) -> ResultCode:
        """
        Wait for the fndh ports to change state to a desired state.

        :param desired: the desired port powers looks like `[False]*28`
        :param timeout: the maximum time to wait in seconds (s)

        :raises TimeoutError: If the fndh port powers did not match the desired state
            after the timout period
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
            self.logger.error(
                "On command failed to complete successfully, "
                "Timeout waiting for fndh ports to change state."
            )
            raise TimeoutError("The FndhPorts did not change in time")

        self.logger.info("All FNDH turned ON successfully")
        return ResultCode.OK

    def wait_for_smartbox_device_state(  # noqa: C901
        self: FieldStationComponentManager, desired: list[Optional[bool]], timeout: int
    ) -> ResultCode:
        """
        Wait for the smartbox devices to change state.

        :param desired: the desired port powers looks like `[False]*24`
        :param timeout: the maximum time to wait in seconds (s)

        :raises TimeoutError: If the smartboxes did not match the desired state
            after the timout period
        :return: A ResultCode and a string.
        """

        def _smartbox_power_as_desired(
            current_state: list[PowerState], desired_state: list[Optional[bool]]
        ) -> bool:
            for port_idx, port_state in enumerate(desired_state):
                if port_state is not None:
                    port_power = PowerState.ON if port_state else PowerState.OFF
                    if current_state[port_idx] != port_power:
                        return False
            return True

        # Wait for smartboxes to match the desired state, else report failure
        if not _smartbox_power_as_desired(self._smartbox_power_state, desired):
            # Wait for a callback.
            t1 = time.time()
            self.smartbox_power_change.wait(timeout)
            t2 = time.time()
            time_waited = t2 - t1
            if (
                self.smartbox_power_change.is_set()
                and timeout > 0
                and time_waited <= timeout
            ):
                self.smartbox_power_change.clear()
                remaining_time = timeout - int(time_waited)
                return self.wait_for_smartbox_device_state(desired, remaining_time)
            raise TimeoutError(
                "The subservient smartbox devices failed to reach state in time"
            )
        self.logger.info("All smartboxes turned ON successfully")
        return ResultCode.OK

    def wait_for_antenna_powers(  # noqa: C901
        self: FieldStationComponentManager,
        desired_antenna_powers: list[Optional[PowerState]],
        timeout: int,
    ) -> ResultCode:
        """
        Wait for the antennas powers to match the desired states.

        :param desired_antenna_powers: A list containing the desired
            antenna power states. Power state None if antenna is masked.
        :param timeout: the maximum time to wait in seconds (s)

        :raises TimeoutError: If the smartboxes did not match the desired state
            after the timout period.
        :return: A ResultCode and a string.
        """

        def antenna_power_as_desired(
            current_state: dict[str, PowerState],
            desired_antenna_powers: list[Optional[PowerState]],
        ) -> bool:
            for antenna_id, desired_power in enumerate(desired_antenna_powers, start=1):
                if desired_power is not None:
                    if current_state[str(antenna_id)] != desired_power:
                        return False
            return True

        # Check the antenna power is as desired.
        if not antenna_power_as_desired(self.antenna_powers, desired_antenna_powers):
            # Wait for a callback.
            t1 = time.time()
            self.antenna_powers_changed.wait(timeout)
            t2 = time.time()
            time_waited = t2 - t1
            if (
                self.antenna_powers_changed.is_set()
                and timeout > 0
                and time_waited <= timeout
            ):
                self.antenna_powers_changed.clear()
                remaining_time = int(timeout - time_waited)
                return self.wait_for_antenna_powers(
                    desired_antenna_powers, remaining_time
                )
            raise TimeoutError("The antenna did not reach the desired states in time")
        self.logger.info("All Antenna turned ON successfully")
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

    def _off(  # pylint: disable=too-many-locals
        self: FieldStationComponentManager,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        if not ignore_mask and self._antenna_mask[0]:
            msg = (
                "Antennas in this station are masked, "
                "call with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = self._get_masked_smartbox_ports()
        results = []
        assert self._fndh_proxy._proxy
        masked_fndh_ports: list = self._get_masked_fndh_ports(masked_smartbox_ports)
        desired_fndh_port_powers: list[int | None] = [
            False
        ] * PasdData.NUMBER_OF_FNDH_PORTS
        for masked_port in masked_fndh_ports:
            desired_fndh_port_powers[masked_port - 1] = None

        json_argument = json.dumps(
            {
                "port_powers": desired_fndh_port_powers,
                "stay_on_when_offline": True,
            }
        )
        result, _ = self._fndh_proxy._proxy.SetPortPowers(json_argument)
        results += result
        masked_ports = []
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys, start=1):
            assert smartbox._proxy
            desired_smartbox_port_powers: list[int | None] = [
                False
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            masked_ports = masked_smartbox_ports.get(smartbox_no, [])
            for masked_port in masked_ports:
                desired_smartbox_port_powers[masked_port - 1] = None
            json_argument = json.dumps(
                {
                    "port_powers": desired_smartbox_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            result, _ = smartbox._proxy.SetPortPowers(json_argument)
            results += result
        if all(result == ResultCode.QUEUED for result in results):
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result="All unmasked antennas turned off.",
                )
            return
        if task_callback:
            task_callback(
                status=TaskStatus.FAILED,
                result="Didn't turn off all unmasked antennas.",
            )

    def _get_masked_fndh_ports(
        self: FieldStationComponentManager, masked_smartbox_ports: dict
    ) -> list:
        # A FNDH port will be masked if either there is no smartbox
        # attached to the port or the smartbox attached to the port is
        # masked
        fndh_ports_masking_state: list[Optional[bool]] = [
            None
        ] * PasdData.NUMBER_OF_FNDH_PORTS
        for smartbox_id in list(masked_smartbox_ports.keys()):
            if (
                len(masked_smartbox_ports[smartbox_id])
                == PasdData.NUMBER_OF_SMARTBOX_PORTS
            ):
                if str(smartbox_id) in self._smartbox_mapping:
                    fndh_port = self._smartbox_mapping[str(smartbox_id)]
                    fndh_ports_masking_state[fndh_port - 1] = True
                else:
                    self.logger.info(
                        f"No mapping found for {str(smartbox_id)} smartbox"
                        "leaving smartbox masking state unknown"
                    )
                    continue
        for fndh_port, fndh_port_state in enumerate(
            self._get_fndh_ports_with_smartboxes()
        ):
            if fndh_port_state is False:
                fndh_ports_masking_state[fndh_port] = True

        masked_fndh_ports = []
        for fndh_port_idx, masking_state in enumerate(
            fndh_ports_masking_state, start=1
        ):
            if masking_state:
                masked_fndh_ports.append(fndh_port_idx)

        return masked_fndh_ports

    def _get_masked_smartbox_ports(
        self: FieldStationComponentManager,
    ) -> dict[int, list]:
        # A smartbox port will be masked if either there is no antenna
        # attached to the port or the antenna attached to the port is
        # masked
        # Smartbox_id : [List of masked ports on that smartbox]
        masked_smartbox_ports: dict[int, list] = {}
        for antenna_id, antenna_masked in enumerate(self._antenna_mask):
            # Checking antenna_id > 0 as 0 corresponds to all antennas
            if antenna_masked and antenna_id > 0:
                smartbox_id, smartbox_port = self._antenna_mapping[str(antenna_id)]
                try:
                    masked_smartbox_ports[smartbox_id]
                except KeyError:
                    masked_smartbox_ports[smartbox_id] = []
                masked_smartbox_ports[smartbox_id].append(smartbox_port)

        # mask all smartbox ports with no antenna attached.
        for smartbox_id in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
            for smartbox_port, port_has_antenna in enumerate(
                self._get_smartbox_ports_with_antennas(smartbox_id), start=1
            ):
                if not port_has_antenna:
                    try:
                        masked_smartbox_ports[smartbox_id]
                    except KeyError:
                        masked_smartbox_ports[smartbox_id] = []
                    masked_smartbox_ports[smartbox_id].append(smartbox_port)

        return masked_smartbox_ports

    def _get_smartbox_ports_with_antennas(
        self: FieldStationComponentManager, smartbox_id: int
    ) -> list:
        smartbox_ports = [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS
        for antenna_smartbox_id, antennas_smartbox_port in list(
            self._antenna_mapping.values()
        ):
            if antenna_smartbox_id == smartbox_id:
                smartbox_ports[antennas_smartbox_port - 1] = True
        return smartbox_ports

    def _get_fndh_ports_with_smartboxes(self: FieldStationComponentManager) -> list:
        fndh_ports = [False] * PasdData.NUMBER_OF_FNDH_PORTS
        for fndh_port in list(self._smartbox_mapping.values()):
            fndh_ports[fndh_port - 1] = True
        return fndh_ports

    @check_communicating
    def turn_on_antenna(
        self: FieldStationComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn on an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        :param antenna_number: (one-based) number of the Antenna to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_on_antenna,  # type: ignore[arg-type]
            args=[
                antenna_number,
            ],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(
                self._field_station_mapping_loaded, "PowerOnAntenna"
            ),
        )

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_on_antenna(  # noqa: C901, pylint: disable=too-many-branches
        self: FieldStationComponentManager,
        antenna_number: int,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
        assert self._fndh_proxy._proxy is not None
        if not ignore_mask and (self._antenna_mask[antenna_number]):
            msg = (
                f"Antenna number {antenna_number} is masked, call "
                "with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if ignore_mask:
            self.logger.warning("Turning on masked antenna")
        smartbox_id, smartbox_port = self._antenna_mapping[str(antenna_number)]
        try:
            smartbox_proxy = self._smartbox_proxys[smartbox_id - 1]
        except IndexError:
            msg = (
                f"Tried to turn on antenna {antenna_number}, this is mapped to "
                f"smartbox {smartbox_id}, port {smartbox_port}. However this smartbox"
                " device is not deployed"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED
        fndh_port = self._smartbox_mapping[str(smartbox_id)]

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        if not self._fndh_proxy._proxy.PortsPowerSensed[fndh_port - 1]:
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
                    result=f"antenna {antenna_number} was already on.",
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
                    result=f"turn on antenna {antenna_number} success.",
                )
            return TaskStatus.COMPLETED
        if task_callback:
            task_callback(status=TaskStatus.FAILED)

        return TaskStatus.FAILED

    @check_communicating
    def turn_off_antenna(
        self: FieldStationComponentManager,
        antenna_number: int,
        task_callback: Optional[Callable] = None,
    ) -> tuple[TaskStatus, str]:
        """
        Turn off an antenna.

        The Field station knows what ports need to be
        turned on and what fndh and smartboxes it is connected to.

        :param antenna_number: (one-based) number of the TPM to turn on.
        :param task_callback: callback to be called when the status of
            the command changes

        :return: the task status and a human-readable status message
        """
        return self.submit_task(
            self._turn_off_antenna,  # type: ignore[arg-type]
            args=[
                antenna_number,
            ],
            task_callback=task_callback,
            is_cmd_allowed=functools.partial(
                self._field_station_mapping_loaded, "PowerOffAntenna"
            ),
        )

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_off_antenna(  # noqa: C901
        self: FieldStationComponentManager,
        antenna_number: int,
        ignore_mask: bool = False,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> TaskStatus:
        assert self._fndh_proxy._proxy is not None
        if not ignore_mask and self._antenna_mask[antenna_number]:
            msg = (
                f"Antenna number {antenna_number} is masked, call "
                "with ignore_mask=True to ignore"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED

        if ignore_mask:
            self.logger.warning("Turning off masked antenna")

        smartbox_id, smartbox_port = self._antenna_mapping[str(antenna_number)]
        try:
            smartbox_proxy = self._smartbox_proxys[smartbox_id - 1]
        except IndexError:
            msg = (
                f"Tried to turn off antenna {antenna_number}, this is mapped to "
                f"smartbox {smartbox_id}, port {smartbox_port}. However this smartbox"
                " device is not deployed"
            )
            self.logger.error(msg)
            if task_callback:
                task_callback(status=TaskStatus.REJECTED, result=msg)
            return TaskStatus.REJECTED
        fndh_port = self._smartbox_mapping[str(smartbox_id)]

        try:
            assert self._fndh_proxy._proxy.PortsPowerSensed[fndh_port - 1]
        except AssertionError:
            msg = (
                f"Tried to turn off antenna {antenna_number}, this is mapped to "
                f"smartbox {smartbox_id}, which is on fndh port {fndh_port}."
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
                    result=f"turn off antenna {antenna_number} success.",
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
        all_masked = True

        antenna_masks_pretty: list[dict] = [{}] * PasdData.NUMBER_OF_ANTENNAS

        antenna_mask = kwargs["antennaMask"]
        for antenna in antenna_mask:
            antenna_id = antenna.get("antennaID")
            masking_state = antenna.get("maskingState")

            if antenna_id is not None and masking_state is not None:
                antenna_masks_pretty[int(antenna_id) - 1] = {
                    "antennaID": int(antenna_id),
                    "maskingState": masking_state,
                }

                self._antenna_mask[antenna_id] = masking_state
                if not masking_state:
                    all_masked = False
        self._antenna_mask[0] = all_masked
        self._antenna_mask_pretty = {"antennaMask": antenna_masks_pretty}
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

        antenna_mapping_pretty: list[dict] = [{}] * PasdData.NUMBER_OF_ANTENNAS
        antenna_mapping = kwargs["antennaMapping"]
        for antenna in antenna_mapping:
            antenna_id = antenna.get("antennaID")
            smartbox_id = antenna.get("smartboxID")
            smartbox_port = antenna.get("smartboxPort")
            if (
                antenna_id is not None
                and smartbox_id is not None
                and smartbox_port is not None
            ):
                if str(antenna_id) in self._antenna_mapping:
                    self._antenna_mapping[str(antenna_id)] = [
                        smartbox_id,
                        smartbox_port,
                    ]
                else:
                    self.logger.info(
                        f"antenna {str(antenna_id)} not in antenna mapping"
                    )

                antenna_mapping_pretty[int(antenna_id) - 1] = {
                    "antennaID": int(antenna_id),
                    "smartboxID": smartbox_id,
                    "smartboxPort": smartbox_port,
                }

        self._antenna_mapping_pretty = {"antennaMapping": antenna_mapping_pretty}
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

        smartbox_mapping_pretty: list[dict] = [
            {}
        ] * PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION
        smartbox_mapping = kwargs["smartboxMapping"]
        for smartbox in smartbox_mapping:
            smartbox_id = smartbox.get("smartboxID")
            fndh_port = smartbox.get("fndhPort")
            if smartbox_id is not None and fndh_port is not None:
                self._smartbox_mapping[str(smartbox_id)] = fndh_port
                smartbox_mapping_pretty[int(smartbox_id) - 1] = {
                    "smartboxID": int(smartbox_id),
                    "fndhPort": int(fndh_port),
                }

        self._smartbox_mapping_pretty = {"smartboxMapping": smartbox_mapping_pretty}
        self._on_configuration_change(self._smartbox_mapping_pretty)
        if task_callback:
            task_callback(status=TaskStatus.COMPLETED)

    def configure(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> tuple[TaskStatus, str]:
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
            jsonschema.validate(configuration, self.CONFIGURATION_SCHEMA)

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

            config_converted = self._convert_config(configuration)

            # Validate configuration before updating.
            jsonschema.validate(config_converted, self.CONFIGURATION_SCHEMA)

            self._update_mappings(config_converted)

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

    def _convert_config(
        self: FieldStationComponentManager, telmodel_config: dict
    ) -> dict:
        """
        Convert telmodel mapping into compatible mapping.

        :param telmodel_config: config from telmodel.

        :return: Converted config that matches old format.
        """
        # TODO: MCCS-2115 This convert function is only required until we
        # rewrite the antenna mappings. This will make the antenna mappings
        # reference from a dict of antenna ids, rather than index of a list
        # In this work it will also rewrite the .yaml.gotmpl file to convert
        # the old format into the new format
        new_config: dict = {}
        new_config["antennas"] = {}

        for i, antenna_id in enumerate(telmodel_config["antennas"]):
            new_config["antennas"][str(i + 1)] = {}
            new_config["antennas"][str(i + 1)]["smartbox"] = telmodel_config[
                "antennas"
            ][antenna_id]["smartbox"][-2:]
            new_config["antennas"][str(i + 1)]["smartbox_port"] = telmodel_config[
                "antennas"
            ][antenna_id]["smartbox_port"]

            new_config["antennas"][str(i + 1)]["masked"] = (
                telmodel_config["antennas"][antenna_id].get("masked") or False
            )

        new_config["pasd"] = {}

        pasd = telmodel_config["pasd"]
        converted_smart_boxes: dict = {}
        for i, smartbox_id in enumerate(pasd["smartboxes"]):
            converted_smart_boxes[str(i)] = {}
            converted_smart_boxes[str(i)]["fndh_port"] = pasd["smartboxes"][
                smartbox_id
            ]["fndh_port"]

        new_config["pasd"]["smartboxes"] = converted_smart_boxes

        return new_config

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
