# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module defines a pytest harness for testing the MCCS FNDH module."""


from __future__ import annotations

import functools
import logging
import unittest
from typing import Generator

import pytest
import tango
from ska_control_model import ResultCode
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.fndh import FndhComponentManager, _PasdBusProxy


@pytest.fixture(name="pasdbus_fqdn", scope="session")
def pasdbus_fqdn_fixture() -> str:
    """
    Return the name of the pasdbus Tango device.

    :return: the name of the pasdbus Tango device.
    """
    return "low-mccs/pasdbus/001"


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


@pytest.fixture(name="pasd_bus_proxy")
def pasd_bus_proxy_fixture(
    test_context: TangoContextProtocol,
    pasdbus_fqdn: str,
    logger: logging.Logger,
    mock_callbacks: MockCallableGroup,
) -> _PasdBusProxy:
    """
    Return a proxy to the PasdBus for testing.

    This is a pytest fixture.

    :param test_context: a test context hosting the mocked devices for the
        component manager
    :param pasdbus_fqdn: FQDN of pasdbus device.
    :param logger: a loger for the antenna component manager to use
    :param mock_callbacks: A group of callables.

    :return: a _PasdBusProxy to the PaSDBus device.
    """
    return _PasdBusProxy(
        pasdbus_fqdn,
        logger,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["attribute_update"],
        mock_callbacks["port_power_state"],
    )


@pytest.fixture(name="fndh_component_manager")
def fndh_component_manager_fixture(
    logger: logging.Logger,
    pasdbus_fqdn: str,
    mock_callbacks: MockCallableGroup,
    pasd_bus_proxy: unittest.mock.Mock,
) -> FndhComponentManager:
    """
    Return an FNDH component manager.

    (This is a pytest fixture.)

    :param logger: a logger for this command to use.
    :param pasdbus_fqdn: the pasd bus fndh
    :param mock_callbacks: mock callables.
    :param pasd_bus_proxy: a proxy to the PasdBus device.

    :return: an FNDH component manager.
    """
    component_manager = FndhComponentManager(
        logger,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["attribute_update"],
        mock_callbacks["port_power_state"],
        pasdbus_fqdn,
        pasd_bus_proxy,
    )
    component_manager._pasd_bus_proxy._communication_state_callback = (
        component_manager._pasdbus_communication_state_changed
    )
    component_manager._pasd_bus_proxy._component_state_callback = functools.partial(
        mock_callbacks["component_state"], fqdn=pasdbus_fqdn
    )

    return component_manager


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_pasdbus: unittest.mock.Mock,
    pasdbus_fqdn: str,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Create a test context standing up the devices under test.

    :param mock_pasdbus: A mock PaSDBus device.
    :param pasdbus_fqdn: The name of the PaSDBus.
    :yield: A tango context with devices to test.
    """
    context_manager = ThreadedTestTangoContextManager()
    # Add PaSDBus device mock.
    context_manager.add_mock_device(pasdbus_fqdn, mock_pasdbus)
    with context_manager as context:
        yield context
