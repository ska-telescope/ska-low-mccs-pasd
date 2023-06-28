# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS SmartBox module."""
from __future__ import annotations

import functools
import logging
import unittest
from typing import Generator

import pytest
import tango
from ska_control_model import PowerState, ResultCode
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.smart_box import (
    SmartBoxComponentManager,
    _FndhProxy,
    _SmartBoxProxy,
)


@pytest.fixture(name="mocked_initial_port_power_state")
def mocked_initial_port_power_state_fixture() -> PowerState:
    """
    Return the initial power state of the FNDH port.

    :return: the initial power state.
    """
    return PowerState.ON


@pytest.fixture(name="pasdbus_fqdn", scope="session")
def pasdbus_fqdn_fixture() -> str:
    """
    Return the name of the PaSDBus Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs/pasdbus/001"


@pytest.fixture(name="fndh_fqdn", scope="session")
def fndh_fqdn_fixture() -> str:
    """
    Return the name of the fndh Tango device.

    :return: the name of the fndh Tango device.
    """
    return "low-mccs/fndh/001"


def fndh_port_value() -> int:
    """
    Return the fndh port the smartbox is attached to.

    This is purely to use in pytest paramaters.

    :return: the fndh port this smartbox is attached.
    """
    return 2


@pytest.fixture(name="fndh_port")
def fndh_port_fixture() -> int:
    """
    Return the fndh port the smartbox is attached to.

    :return: the fndh port this smartbox is attached.
    """
    return fndh_port_value()


@pytest.fixture(name="smartbox_number")
def smartbox_number_fixture() -> int:
    """
    Return the logical number assigned to this smartbox.

    :return: the logical number of the smartbox under test.
    """
    return 1


@pytest.fixture(name="mock_pasdbus")
def mock_pasdbus_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsPaSDBus device.

    :return: a mock MccsPaSDBus device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_command("GetPasdDeviceSubscriptions", {})
    builder.add_result_command("TurnSmartboxPortOn", ResultCode.OK)
    builder.add_result_command("TurnSmartboxPortOff", ResultCode.OK)
    builder.add_result_command("TurnFndhPortOff", ResultCode.OK)
    builder.add_result_command("TurnFndhPortOn", ResultCode.OK)
    return builder()


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture(
    fndh_port: int, mocked_initial_port_power_state: PowerState
) -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFNDH device.

    :param fndh_port: the port that this smartbox is attached to
    :param mocked_initial_port_power_state: the initial power state of
        the port the smartbox is attached to.

    :return: a mock MccsFNDH device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_attribute(f"Port{fndh_port}PowerState", mocked_initial_port_power_state)
    return builder()


@pytest.fixture(name="pasd_bus_proxy")
def pasd_bus_proxy_fixture(
    test_context: TangoContextProtocol,
    pasdbus_fqdn: str,
    smartbox_number: int,
    logger: logging.Logger,
    mock_callbacks: MockCallableGroup,
) -> _SmartBoxProxy:
    """
    Return a proxy to the PasdBus for testing.

    This is a pytest fixture.

    :param test_context: a test context hosting the mocked devices for the
        component manager
    :param pasdbus_fqdn: FQDN of pasdbus device.
    :param smartbox_number: the logical number of the smartbox.
    :param logger: a loger for the antenna component manager to use
    :param mock_callbacks: A group of callables.

    :return: a _SmartBoxProxy to the PaSDBus device.
    """
    return _SmartBoxProxy(
        pasdbus_fqdn,
        smartbox_number,
        logger,
        1,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["attribute_update"],
    )


@pytest.fixture(name="fndh_proxy")
def fndh_proxy_fixture(
    test_context: TangoContextProtocol,
    fndh_fqdn: str,
    fndh_port: int,
    logger: logging.Logger,
    mock_callbacks: MockCallableGroup,
) -> _FndhProxy:
    """
    Return a proxy to the FNDH for testing.

    This is a pytest fixture.

    :param test_context: a test context hosting the mocked devices for the
        component manager
    :param fndh_fqdn: FQDN of FNDH device.
    :param fndh_port: the port of interest to the smartbox_component manager.
    :param logger: a loger for the antenna component manager to use
    :param mock_callbacks: A group of callables.

    :return: a _FndhProxy proxy to the FNDH device.
    """
    return _FndhProxy(
        fndh_fqdn,
        fndh_port,
        logger,
        1,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["port_power_state"],
    )


@pytest.fixture(name="smartbox_component_manager")
def smartbox_component_manager_fixture(  # pylint: disable=too-many-arguments
    logger: logging.Logger,
    fndh_port: int,
    pasdbus_fqdn: str,
    fndh_fqdn: str,
    mock_callbacks: MockCallableGroup,
    fndh_proxy: tango.DeviceProxy,
    smartbox_number: int,
    pasd_bus_proxy: tango.DeviceProxy,
) -> SmartBoxComponentManager:
    """
    Return an SmartBox component manager.

    :param logger: a logger for this command to use.
    :param fndh_port: the fndh port this smartbox is attached.
    :param pasdbus_fqdn: the pasd bus smartbox
    :param fndh_fqdn: the fndh smartbox
    :param mock_callbacks: mock callables.
    :param fndh_proxy: the smartbox's fndh proxy.
    :param pasd_bus_proxy: the smartbox's pasd_bus proxy.
    :param smartbox_number: the number assigned to this smartbox.

    :return: an SmartBox component manager.
    """
    component_manager = SmartBoxComponentManager(
        logger,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["attribute_update"],
        12,
        fndh_port,
        pasdbus_fqdn,
        fndh_fqdn,
        smartbox_number,
        pasd_bus_proxy,
        fndh_proxy,
    )
    component_manager._smartbox_proxy._communication_state_callback = (
        component_manager._smartbox_communication_state_changed
    )
    component_manager._smartbox_proxy._component_state_callback = functools.partial(
        mock_callbacks["component_state"], fqdn=pasdbus_fqdn
    )
    component_manager._fndh_proxy._communication_state_callback = (
        component_manager._fndh_communication_state_changed
    )
    component_manager._fndh_proxy._component_state_callback = functools.partial(
        mock_callbacks["component_state"], fqdn=fndh_fqdn
    )
    return component_manager


@pytest.fixture(name="test_context")
def test_context_fixture(
    fndh_fqdn: str,
    mock_fndh: unittest.mock.Mock,
    mock_pasdbus: unittest.mock.Mock,
    pasdbus_fqdn: str,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Create a test context standing up the devices under test.

    :param fndh_fqdn: the name of the FNDH.
    :param mock_fndh: A mock FNDH device.
    :param mock_pasdbus: A mock PaSDBus device.
    :param pasdbus_fqdn: The name of the PaSDBus.
    :yield: A tango context with devices to test.
    """
    context_manager = ThreadedTestTangoContextManager()
    # Add SmartBox and Tile mock devices.
    context_manager.add_mock_device(fndh_fqdn, mock_fndh)
    context_manager.add_mock_device(pasdbus_fqdn, mock_pasdbus)
    with context_manager as context:
        yield context
