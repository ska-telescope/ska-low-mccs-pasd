# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsFNDH."""

from __future__ import annotations

import gc
from typing import Generator

import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsFNDH, MccsPasdBus

gc.disable()  # TODO: why is this needed?


@pytest.fixture(name="pasd_bus_name", scope="session")
def pasd_bus_name_fixture() -> str:
    """
    Return the name of the pasd_bus Tango device.

    :return: the name of the pasd_bus Tango device.
    """
    return "low-mccs-pasd/pasdbus/001"


@pytest.fixture(name="fndh_name", scope="session")
def fndh_name_fixture() -> str:
    """
    Return the name of the fndh_bus Tango device.

    :return: the name of the fndh_bus Tango device.
    """
    return "low-mccs-pasd/fndh/001"


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    fndh_name: str,
    pasd_bus_name: str,
    pasd_bus_info: dict,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param fndh_name: the name of the fndh_bus Tango device
    :param pasd_bus_name: the fqdn of the pasdbus
    :param pasd_bus_info: the information for pasd setup

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        fndh_name,
        MccsFNDH,
        PasdFQDNs=pasd_bus_name,
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    context_manager.add_device(
        pasd_bus_name,
        MccsPasdBus,
        Host=pasd_bus_info["host"],
        Port=pasd_bus_info["port"],
        Timeout=pasd_bus_info["timeout"],
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    with context_manager as context:
        yield context


@pytest.fixture(name="fndh_device")
def fndh_device_fixture(
    tango_harness: TangoContextProtocol,
    fndh_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the fndh_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param fndh_name: name of the fndh_bus Tango device.

    :yield: the fndh_bus Tango device under test.
    """
    yield tango_harness.get_device(fndh_name)


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the pasd_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: name of the pasd_bus Tango device.

    :yield: the pasd_bus Tango device under test.
    """
    yield tango_harness.get_device(pasd_bus_name)


class TestfndhPasdBusIntegration:  # pylint: disable=too-few-public-methods
    """Test pasdbus and fndh integration."""

    def test_fndh_pasd_integration(
        self: TestfndhPasdBusIntegration,
        fndh_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of fndh with the pasdBus.

        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        assert fndh_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fndh_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fndh_state"],
        )
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.DISABLE)
        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        # ----------------------------------------------------------------
        # Check that the devices enters the correct state after turning adminMode on
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # The fndh should enter UNKNOWN, then it should check with the
        # The fndh that the port this subrack is attached to
        # has power, this is simulated as off.
        fndh_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fndh_state"].assert_change_event(tango.DevState.OFF)


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "fndh_state",
        "pasd_bus_state",
        timeout=2.0,
    )
