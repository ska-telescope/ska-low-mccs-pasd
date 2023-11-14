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
from typing import Any, Callable, Final, Optional

import jsonschema
import tango
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_low_mccs_common.component import DeviceComponentManager
from ska_ser_devices.client_server import (
    ApplicationClient,
    SentinelBytesMarshaller,
    TcpClient,
)
from ska_tango_base.base import check_communicating
from ska_tango_base.commands import ResultCode
from ska_tango_base.executor import TaskExecutorComponentManager

from ska_low_mccs_pasd.pasd_data import PasdData

from ..command_proxy import MccsCommandProxy
from ..reference_data_store.pasd_configmap_interface import (
    PasdConfigurationJsonApiClient,
)

__all__ = ["FieldStationComponentManager"]


# pylint: disable=too-many-instance-attributes,  too-many-lines, abstract-method
class FieldStationComponentManager(TaskExecutorComponentManager):
    """A component manager for MccsFieldStation."""

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
        communication_state_callback: Callable[..., None],
        component_state_changed: Callable[..., None],
        antenna_power_changed: Callable[..., None],
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
        :param communication_state_callback: callback to be
            called when the status of the communications channel between
            the component manager and its component changes
        :param component_state_changed: callback to be
            called when the component state changes
        :param antenna_power_changed: callback to be
            called when power state of a antenna changes
        :param _fndh_proxy: a injected fndh proxy for purposes of testing only.
        :param _smartbox_proxys: injected smartbox proxys for purposes of testing only.

        :raises NotImplementedError: configuration in TelModel not yet implemented
        """
        self._on_antenna_power_change = antenna_power_changed
        self._communication_state_callback: Callable[..., None]
        self._component_state_callback: Callable[..., None]
        self.outsideTemperature: Optional[float] = None
        max_workers = 1
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

        self._smartbox_proxys = []
        smartbox_count = 0
        self._smartbox_name_number_map: dict[str, int] = {}
        if _smartbox_proxys:
            self._smartbox_proxys = _smartbox_proxys
        else:
            for smartbox_name in smartbox_names:
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

        # TODO add configurability.
        # This could be as simple as ...
        # "if i am given a ip / port i am in simulation mode"
        simulation_mode = True

        try:
            # Configuration read from the API_CLIENT when in simulation mode
            # TelModel when interfacing with hardware.
            if simulation_mode:
                tcp_client = TcpClient(
                    (configuration_host, configuration_port), configuration_timeout
                )

                self.logger.debug(r"Creating marshaller with sentinel '\n'...")
                marshaller = SentinelBytesMarshaller(b"\n")
                application_client = ApplicationClient[bytes, bytes](
                    tcp_client, marshaller.marshall, marshaller.unmarshall
                )
                self._field_station_configuration_api_client = (
                    PasdConfigurationJsonApiClient(application_client)
                )
                self._field_station_configuration_api_client.connect()

                configuration = (
                    self._field_station_configuration_api_client.read_attributes(
                        self.station_name
                    )
                )
            else:
                # TODO: ask for data from TelModel
                self.logger.error(
                    "Attempted read from TelModel when functionality not implemented."
                )
                raise NotImplementedError(
                    "Attempted read from TelModel when functionality not implemented."
                )

            # Validate configuration before updating.
            jsonschema.validate(configuration, self.CONFIGURATION_SCHEMA)

            self._update_mappings(configuration)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error(f"Failed to update configuration {e}.")

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
        smartbox_mapping_pretty: list[dict] = [{}] * PasdData.NUMBER_OF_SMARTBOXES

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

        # TODO: Contact every MccsSmartbox under this FieldStations control
        # informing them of the fndh port they are on?

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
        event_value: list[bool],
        event_quality: tango.AttrQuality,
    ) -> None:
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

        self._on_antenna_power_change(self.antenna_powers)

    def _update_antenna_power_map(
        self: FieldStationComponentManager,
        antenna_power_map: dict[str, PowerState],
        antenna_mapping: dict[int, list[int]],
        smartbox_under_change: int,
        port_powers: list[PowerState],
    ) -> None:
        for antenna_id, antenna_config in antenna_mapping.items():
            antennas_smartbox = antenna_config[0]
            smartbox_port = antenna_config[1]
            if antennas_smartbox == smartbox_under_change:
                if str(antenna_id) in antenna_power_map.keys():
                    antenna_power_map[str(antenna_id)] = port_powers[smartbox_port - 1]
                else:
                    raise KeyError(f"Unexpected key {str(antenna_id)}")

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
        )

    def _on(  # pylint: disable=too-many-locals
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

        desired_fndh_port_powers: list[bool | None] = [
            True
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
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys):
            assert smartbox._proxy
            desired_smartbox_port_powers: list[bool | None] = [
                True
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            masked_ports = masked_smartbox_ports.get(smartbox_no + 1, [])
            for masked_port in masked_ports:
                desired_smartbox_port_powers[masked_port - 1] = None
            json_argument = json.dumps(
                {
                    "smartbox_number": smartbox_no + 1,
                    "port_powers": desired_smartbox_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            result, _ = smartbox._proxy.SetPortPowers(json_argument)
            results += result
        if all(result == ResultCode.OK for result in results):
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result="All unmasked antennas turned on.",
                )
            return
        if task_callback:
            task_callback(
                status=TaskStatus.FAILED, result="Didn't turn on all unmasked antennas."
            )

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
        for smartbox_no, smartbox in enumerate(self._smartbox_proxys):
            assert smartbox._proxy
            desired_smartbox_port_powers: list[int | None] = [
                False
            ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
            masked_ports = masked_smartbox_ports.get(smartbox_no + 1, [])
            for masked_port in masked_ports:
                desired_smartbox_port_powers[masked_port - 1] = None
            json_argument = json.dumps(
                {
                    "smartbox_number": self._smartbox_mapping[str(smartbox_no + 1)],
                    "port_powers": desired_smartbox_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            result, _ = smartbox._proxy.SetPortPowers(json_argument)
            results += result

        if all(result == ResultCode.OK for result in results):
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
        masked_fndh_ports = []
        for smartbox_id in list(masked_smartbox_ports.keys()):
            if (
                len(masked_smartbox_ports[smartbox_id])
                == PasdData.NUMBER_OF_SMARTBOX_PORTS
            ):
                fndh_port = self._smartbox_mapping[str(smartbox_id)]
                masked_fndh_ports.append(fndh_port)
        for fndh_port, fndh_port_state in enumerate(
            self._get_fndh_ports_with_smartboxes()
        ):
            if fndh_port_state is False:
                masked_fndh_ports.append(fndh_port + 1)

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

        for smartbox_id in range(1, PasdData.NUMBER_OF_SMARTBOXES + 1):
            for smartbox_port, smartbox_state in enumerate(
                self._get_smartbox_ports_with_antennas(smartbox_id)
            ):
                if smartbox_state is False:
                    try:
                        masked_smartbox_ports[smartbox_id]
                    except KeyError:
                        masked_smartbox_ports[smartbox_id] = []
                    masked_smartbox_ports[smartbox_id].append(smartbox_port + 1)

        return masked_smartbox_ports

    def _get_smartbox_ports_with_antennas(
        self: FieldStationComponentManager, smartbox_id: int
    ) -> list:
        smartbox_ports = [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS
        for smartbox in list(self._antenna_mapping.values()):
            if smartbox[0] == smartbox_id:
                smartbox_ports[smartbox[1] - 1] = True
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
        except KeyError:
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

        if not self._fndh_proxy._proxy.PortPowerState(fndh_port):
            result, _ = self._fndh_proxy._proxy.PowerOnPort(fndh_port)

        assert smartbox_proxy._proxy is not None

        if not smartbox_proxy._proxy.PortsPowerSensed[smartbox_port]:
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
        )

    # All the if(task_callbacks) artificially extend the complexity.
    def _turn_off_antenna(  # noqa: C901, pylint: disable=too-many-branches
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
        except KeyError:
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

        result = None
        if task_callback:
            task_callback(status=TaskStatus.IN_PROGRESS)

        if self._fndh_proxy._proxy.PortPowerState(fndh_port):
            result, _ = self._fndh_proxy._proxy.PowerOffPort(fndh_port)
        assert smartbox_proxy._proxy is not None
        if smartbox_proxy._proxy.PortsPowerSensed[smartbox_port]:
            if result is None or result[0] in [
                ResultCode.OK,
                ResultCode.STARTED,
                ResultCode.QUEUED,
            ]:
                result, _ = smartbox_proxy._proxy.PowerOffPort(smartbox_port)
        if result is None:
            if task_callback:
                task_callback(
                    status=TaskStatus.COMPLETED,
                    result=f"antenna {antenna_number} was already off.",
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

        antenna_mask = kwargs["antennaMask"]
        for antenna in antenna_mask:
            antenna_id = antenna["antennaID"]
            masking_state = antenna["maskingState"]

            self._antenna_mask[antenna_id] = masking_state
            if not masking_state:
                all_masked = False
        self._antenna_mask[0] = all_masked
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
        for antenna in antenna_mapping:
            antenna_id = antenna["antennaID"]
            smartbox_id = antenna["smartboxID"]
            smartbox_port = antenna["smartboxPort"]
            if str(antenna_id) in self._antenna_mapping:
                self._antenna_mapping[str(antenna_id)] = [smartbox_id, smartbox_port]
            else:
                self.logger.info(f"antenna {str(antenna_id)} not in antenna mapping")
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
        for smartbox in smartbox_mapping:
            smartbox_id = smartbox["smartboxID"]
            fndh_port = smartbox["fndhPort"]
            self._smartbox_mapping[str(smartbox_id)] = fndh_port
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

    def _load_configuration(
        self: FieldStationComponentManager,
        task_callback: Optional[Callable] = None,
        task_abort_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Get the configuration from the configuration server.

        :param task_callback: Update task state, defaults to None
        :param task_abort_event: Check for abort, defaults to None

        :raises NotImplementedError: configuration in TelModel not yet implemented
        """
        try:
            self.logger.info("Attempting to load data from configmap.....")

            simulation_mode = True
            if simulation_mode:
                configuration = (
                    self._field_station_configuration_api_client.read_attributes(
                        self.station_name
                    )
                )
            else:
                # TODO: Add data to TelModel
                self.logger.error(
                    "Attempted read from TelModel when functionality not implemented."
                )
                raise NotImplementedError(
                    "Attempted read from TelModel when functionality not implemented."
                )

            # Validate configuration before updating.
            jsonschema.validate(configuration, self.CONFIGURATION_SCHEMA)

            self._update_mappings(configuration)
            self.logger.info("Configuration has been successfully updated.")

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error(f"Failed to update configuration: {e}")
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
