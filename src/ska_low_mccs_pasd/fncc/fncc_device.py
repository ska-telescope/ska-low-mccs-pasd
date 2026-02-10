# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FNCC device."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Final, Optional, cast

import tango
from ska_control_model import CommunicationStatus, HealthState, PowerState
from ska_low_mccs_common import MccsBaseDevice
from tango.server import device_property

from ..pasd_controllers_configuration import ControllerDict, PasdControllersConfig
from .fncc_component_manager import FnccComponentManager
from .fncc_health_model import FnccHealthModel

__all__ = ["MccsFNCC"]


@dataclass
class FNCCAttribute:
    """Class representing the internal state of a FNCC attribute."""

    value: Any
    quality: tango.AttrQuality
    timestamp: float


class MccsFNCC(MccsBaseDevice[FnccComponentManager]):
    """An implementation of the FNCC device for MCCS."""

    # -----------------
    # Device Properties
    # -----------------
    PasdFQDN: Final = device_property(dtype=(str), mandatory=True)

    # ---------
    # Constants
    # ---------
    CONFIG: Final[ControllerDict] = PasdControllersConfig.get_fncc()
    TYPES: Final[dict[str, type]] = {"int": int, "str": str}

    # ---------------
    # Initialisation
    # ---------------
    def __init__(self: MccsFNCC, *args: Any, **kwargs: Any) -> None:
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
        self.component_manager: FnccComponentManager
        # Initialise with unknown.
        self._health_state: HealthState = HealthState.UNKNOWN
        self._health_model: FnccHealthModel

    def init_device(self: MccsFNCC) -> None:
        """
        Initialise the device.

        This is overridden here to change the Tango serialisation model.
        """
        super().init_device()

        # Setup attributes shared with the MccsPasdBus.
        self._fncc_attributes: dict[str, FNCCAttribute] = {}
        self._setup_fncc_attributes()

        self._build_state = sys.modules["ska_low_mccs_pasd"].__version_info__
        self._version_id = sys.modules["ska_low_mccs_pasd"].__version__
        device_name = f'{str(self.__class__).rsplit(".", maxsplit=1)[-1][0:-2]}'
        version = f"{device_name} Software Version: {self._version_id}"
        properties = (
            f"Initialised {device_name} device with properties:\n"
            f"\tPasdFQDN: {self.PasdFQDN}\n"
        )
        self.logger.info(
            "\n%s\n%s\n%s", str(self.GetVersionInfo()), version, properties
        )

    def delete_device(self: MccsFNCC) -> None:
        """Delete the device."""
        self.component_manager.cleanup()
        super().delete_device()

    def _init_state_model(self: MccsFNCC) -> None:
        super()._init_state_model()
        self._health_state = HealthState.UNKNOWN
        self._health_model = FnccHealthModel(self._health_changed_callback, self.logger)
        self.set_change_event("healthState", True, False)
        self.set_archive_event("healthState", True, False)

    def create_component_manager(self: MccsFNCC) -> FnccComponentManager:
        """
        Create and return a component manager for this device.

        :return: a component manager for this device.
        """
        return FnccComponentManager(
            self.logger,
            self._communication_state_changed,
            self._component_state_changed_callback,
            self._attribute_changed_callback,
            self.PasdFQDN,
            event_serialiser=self._event_serialiser,
        )

    # ----------
    # Attributes
    # ----------
    def _setup_fncc_attributes(self: MccsFNCC) -> None:
        for register in self.CONFIG["registers"].values():
            data_type = self.TYPES[register["data_type"]]
            self._setup_fncc_attribute(
                register["tango_attr_name"],
                cast(
                    type | tuple[type],
                    (data_type if register["tango_dim_x"] == 1 else (data_type,)),
                ),
                (
                    tango.AttrWriteType.READ_WRITE
                    if register["writable"]
                    else tango.AttrWriteType.READ
                ),
                description=register["description"],
                max_dim_x=register["tango_dim_x"],
                unit=register["unit"],
                format_string=register["format_string"],
            )

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def _setup_fncc_attribute(
        self: MccsFNCC,
        attribute_name: str,
        data_type: type | tuple[type],
        access_type: tango.AttrWriteType,
        description: str,
        max_dim_x: Optional[int] = None,
        default_value: Optional[Any] = None,
        unit: Optional[str] = None,
        format_string: Optional[str] = None,
    ) -> None:
        self._fncc_attributes[attribute_name.lower()] = FNCCAttribute(
            value=default_value, timestamp=0, quality=tango.AttrQuality.ATTR_INVALID
        )
        attr = tango.server.attribute(
            name=attribute_name,
            dtype=data_type,
            access=access_type,
            label=attribute_name,
            max_dim_x=max_dim_x,
            fget=self._read_fncc_attribute,
            unit=unit,
            description=description,
            format=format_string,
        ).to_attr()
        self.add_attribute(
            attr,
            self._read_fncc_attribute,
            None,
            None,
        )
        self.set_change_event(attribute_name, True, False)
        self.set_archive_event(attribute_name, True, False)

    def _read_fncc_attribute(self: MccsFNCC, fncc_attribute: tango.Attribute) -> None:
        attribute_name = fncc_attribute.get_name().lower()
        if self._fncc_attributes[attribute_name].value is not None:
            fncc_attribute.set_value_date_quality(
                self._fncc_attributes[attribute_name].value,
                self._fncc_attributes[attribute_name].timestamp,
                self._fncc_attributes[attribute_name].quality,
            )

    # ----------
    # Callbacks
    # ----------
    def _communication_state_changed(
        self: MccsFNCC, communication_state: CommunicationStatus
    ) -> None:
        self.logger.debug(
            (
                "Device received callback from component manager that communication "
                "with the component is %s."
            ),
            communication_state.name,
        )
        if communication_state != CommunicationStatus.ESTABLISHED:
            self._component_state_changed_callback(power=PowerState.UNKNOWN)
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._component_state_changed_callback(power=PowerState.ON)

        super()._communication_state_changed(communication_state)

        if self._health_model is not None:
            self._health_model.update_state(
                communicating=(communication_state == CommunicationStatus.ESTABLISHED),
            )

    def _component_state_changed_callback(
        self: MccsFNCC,
        fault: Optional[bool] = None,
        power: Optional[PowerState] = None,
        fqdn: Optional[str] = None,
        pasdbus_status: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Handle change in the state of the component.

        This is a callback hook, called by the component manager when
        the state of the component changes.

        :param fault: whether the component is in fault.
        :param power: the power state of the component
        :param fqdn: the fqdn of the device calling.
        :param pasdbus_status: the status of the pasd_bus
        :param kwargs: additional keyword arguments defining component
            state.
        """
        if fqdn is not None:
            # TODO: The information passed here could factor into the FNCC health
            if power == PowerState.UNKNOWN:
                # If a proxy calls back with a unknown power. As a precaution it is
                # assumed that communication is NOT_ESTABLISHED.
                self._communication_state_changed(CommunicationStatus.NOT_ESTABLISHED)
                return

        super()._component_state_changed(fault=fault, power=power)
        if fault is not None:
            self._health_model.update_state(fault=fault)
        if power is not None:
            self._health_model.update_state(power=power)
        if pasdbus_status is not None:
            self._health_model.update_state(pasdbus_status=pasdbus_status)

    def _health_changed_callback(self: MccsFNCC, health: HealthState) -> None:
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

    def _attribute_changed_callback(
        self: MccsFNCC,
        attr_name: str,
        attr_value: Any,
        timestamp: float,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle changes to subscribed attributes.

        This is a callback hook we pass to the component manager,
        It is called when a subscribed attribute changes.
        It is responsible for:
        - updating this device attribute
        - pushing a change event to any listeners.

        :param attr_name: the name of the attribute that needs updating
        :param attr_value: the value to update with.
        :param: timestamp: the timestamp for the current change
        :param: attr_quality: the quality factor for the attribute
        """
        try:
            assert (
                len(
                    [
                        register["tango_attr_name"]
                        for register in self.CONFIG["registers"].values()
                        if register["tango_attr_name"].lower() == attr_name.lower()
                    ]
                )
                > 0
            )
            if attr_value is None:
                # This happens when the upstream attribute's quality factor has
                # been set to INVALID. Pushing a change event with None
                # triggers an exception so we change it to the last known value here
                attr_value = self._fncc_attributes[attr_name].value
            else:
                self._fncc_attributes[attr_name].value = attr_value
            self._fncc_attributes[attr_name].quality = attr_quality
            self._fncc_attributes[attr_name].timestamp = timestamp
            self.push_change_event(attr_name, attr_value, timestamp, attr_quality)
            self.push_archive_event(attr_name, attr_value, timestamp, attr_quality)

            # Update the health model with the value of the status register
            if self._health_model is not None and attr_name.endswith("status"):
                self._health_model.update_state(status=attr_value)

        except AssertionError:
            self.logger.debug(
                f"""The attribute {attr_name} pushed from MccsPasdBus
                device does not exist in MccsFNCC"""
            )
