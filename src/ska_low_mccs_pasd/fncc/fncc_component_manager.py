#  -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the component management for fncc."""
from __future__ import annotations

import functools
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import tango
from ska_control_model import CommunicationStatus
from ska_low_mccs_common import EventSerialiser, MccsDeviceProxy
from ska_low_mccs_common.component import DeviceComponentManager
from ska_tango_base.executor import TaskExecutorComponentManager

from ska_low_mccs_pasd.pasd_data import PasdData

__all__ = ["FnccComponentManager", "_PasdBusProxy"]


class _PasdBusProxy(DeviceComponentManager):
    """This is a proxy to the pasdbus bus."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self: _PasdBusProxy,
        fqdn: str,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        state_change_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        event_serialiser: Optional[EventSerialiser] = None,
    ) -> None:
        """
        Initialise a new instance.

        :param fqdn: the FQDN of the MccsPaSDBus device
        :param logger: the logger to be used by this object.
        :param communication_state_callback: callback to be
            called when communication state changes.
        :param state_change_callback: callback to be called when the
            component state changes
        :param attribute_change_callback: callback for when a subscribed attribute
            on the pasdbus changes.
        :param event_serialiser: the event serialiser to be used by this object.
        """
        self._attribute_change_callback = attribute_change_callback
        self._pasd_device = PasdData.FNCC_DEVICE_ID

        super().__init__(
            fqdn,
            logger,
            communication_state_callback,
            state_change_callback,
            event_serialiser=event_serialiser,
        )

    def subscribe_to_attributes(self: _PasdBusProxy) -> None:
        """Subscribe to attributes relating to this FNCC."""
        assert self._proxy is not None
        subscriptions = self._proxy.GetPasdDeviceSubscriptions(self._pasd_device)
        for attribute in subscriptions:
            if attribute not in self._proxy._change_event_subscription_ids.keys():
                self.logger.info(f"subscribing to attribute {attribute}.....")
                self._proxy.add_change_event_callback(
                    attribute, self._on_attribute_change
                )

    def _on_attribute_change(
        self: _PasdBusProxy,
        attr_name: str,
        attr_value: Any,
        attr_quality: tango.AttrQuality,
    ) -> None:
        """
        Handle attribute change event.

        :param attr_name: The name of the attribute that is firing a change event.
        :param attr_value: The value of the attribute that is changing.
        :param attr_quality: The quality of the attribute.
        """
        is_a_fncc = re.search("^fncc", attr_name)

        if is_a_fncc:
            tango_attribute_name = attr_name[is_a_fncc.end() :].lower()

            # Status is a bad name since it conflicts with TANGO status.
            if tango_attribute_name.lower() == "status":
                tango_attribute_name = "pasdstatus"

            timestamp = datetime.now(timezone.utc).timestamp()
            self._attribute_change_callback(
                tango_attribute_name, attr_value, timestamp, attr_quality
            )
            return

        self.logger.info(
            f"Attribute subscription {attr_name} does not seem to begin"
            "with 'fncc' string so it is assumed it is a incorrect subscription"
        )


# pylint: disable-next=abstract-method
class FnccComponentManager(TaskExecutorComponentManager):
    """
    A component manager for an fncc.

    This communicates via a proxy to a MccsPasdBus that talks to a simulator
    or the real hardware.
    """

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self: FnccComponentManager,
        logger: logging.Logger,
        communication_state_callback: Callable[[CommunicationStatus], None],
        component_state_callback: Callable[..., None],
        attribute_change_callback: Callable[..., None],
        pasd_fqdn: str,
        event_serialiser: Optional[EventSerialiser] = None,
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
        :param attribute_change_callback: callback to be
            called when a attribute changes
        :param pasd_fqdn: the fqdn of the pasdbus to connect to.
        :param event_serialiser: the event serialiser to be used by this object.
        :param _pasd_bus_proxy: a optional injected device proxy for testing
            purposes only. defaults to None
        """
        self._event_serialiser = event_serialiser
        self._component_state_callback = component_state_callback
        self._attribute_change_callback = attribute_change_callback
        self._pasd_fqdn = pasd_fqdn

        self._pasd_bus_proxy = _pasd_bus_proxy or _PasdBusProxy(
            pasd_fqdn,
            logger,
            self._pasdbus_communication_state_changed,
            functools.partial(component_state_callback, fqdn=self._pasd_fqdn),
            attribute_change_callback,
            event_serialiser=self._event_serialiser,
        )
        self.logger = logger
        super().__init__(
            logger,
            communication_state_callback,
            component_state_callback,
            power=None,
            fault=None,
            pasdbus_status=None,
        )

    def _pasdbus_communication_state_changed(
        self: FnccComponentManager,
        communication_state: CommunicationStatus,
    ) -> None:
        if communication_state == CommunicationStatus.ESTABLISHED:
            self._pasd_bus_proxy.subscribe_to_attributes()

        self._update_communication_state(communication_state)

    def start_communicating(self: FnccComponentManager) -> None:  # noqa: C901
        """Establish communication with the pasdBus via a proxy."""
        self._pasd_bus_proxy.start_communicating()

    def stop_communicating(self: FnccComponentManager) -> None:
        """Break off communication with the pasdBus."""
        if self.communication_state == CommunicationStatus.DISABLED:
            return
        self._pasd_bus_proxy.stop_communicating()
        self._update_component_state(power=None, fault=None)
