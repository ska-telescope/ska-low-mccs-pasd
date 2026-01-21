# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the FNCC component manager."""
from __future__ import annotations

import logging
import unittest.mock
from typing import Iterator

import pytest
import tango
from ska_control_model import CommunicationStatus
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.fncc import FnccComponentManager, _PasdBusProxy
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_pasd_bus_name,
)


@pytest.fixture(name="mock_pasdbus")
def mock_pasdbus_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsPaSDBus device.

    :return: a mock MccsPaSDBus device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_command("GetPasdDeviceSubscriptions", {})
    return builder()


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_pasdbus: unittest.mock.Mock,
    station_label: str,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing a single mock PaSD bus device.

    :param mock_pasdbus: A mock PaSD bus device.
    :param station_label: The label of the station under test.

    :yield: the test context
    """
    harness = PasdTangoTestHarness(station_label=station_label)
    harness.set_mock_pasd_bus_device(mock_pasdbus)
    with harness as context:
        yield context


class TestPasdBusProxy:
    """Tests of the PaSD bus proxy used by the FNCC component manager."""

    @pytest.fixture(name="pasd_bus_proxy")
    def pasd_bus_proxy_fixture(
        self: TestPasdBusProxy,
        test_context: str,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
        station_label: str,
    ) -> _PasdBusProxy:
        """
        Return a proxy to the PasdBus for testing.

        This is a pytest fixture.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for the PaSD bus proxy to use
        :param mock_callbacks: A group of callables.
        :param station_label: The label of the station under test.

        :return: a proxy to the PaSD bus device.
        """
        return _PasdBusProxy(
            get_pasd_bus_name(station_label=station_label),
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["attribute_update"],
        )

    def test_pasd_proxy_communication(
        self: TestPasdBusProxy,
        pasd_bus_proxy: _PasdBusProxy,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test pasd proxy used by the FNCC component manager.

        :param pasd_bus_proxy: A proxy to the pasd_bus device.
        :param mock_callbacks: A group of callables.
        """
        assert pasd_bus_proxy.communication_state == CommunicationStatus.DISABLED

        pasd_bus_proxy.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        assert pasd_bus_proxy.communication_state == CommunicationStatus.ESTABLISHED

        pasd_bus_proxy.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)


class TestFnccComponentManager:
    """Tests of the FNCC component manager."""

    @pytest.fixture(name="fncc_component_manager")
    def fncc_component_manager_fixture(
        self: TestFnccComponentManager,
        test_context: str,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
        station_label: str,
    ) -> FnccComponentManager:
        """
        Return an FNCC component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param mock_callbacks: mock callables.
        :param station_label: The label of the station under test.

        :return: an FNCC component manager.
        """
        return FnccComponentManager(
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["attribute_update"],
            get_pasd_bus_name(station_label=station_label),
        )

    def test_communication(
        self: TestFnccComponentManager,
        fncc_component_manager: FnccComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the start_communicating command.

        :param fncc_component_manager: A FNCC component manager
            with communication established.
        :param mock_callbacks: mock callables.
        """
        fncc_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()
        assert (
            fncc_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
        )

        # check that the communication state goes to DISABLED after stop communication.
        fncc_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()
