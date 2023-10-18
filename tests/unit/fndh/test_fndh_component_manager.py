# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the FNDH component manager."""
from __future__ import annotations

import logging
import unittest.mock
from typing import Any, Iterator

import pytest
import tango
from ska_control_model import CommunicationStatus, ResultCode, TaskStatus
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.fndh import FndhComponentManager, _PasdBusProxy
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
    builder.add_result_command("SetSmartboxPortPowers", ResultCode.OK)
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    return builder()


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_pasdbus: unittest.mock.Mock,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing a single mock PaSD bus device.

    :param mock_pasdbus: A mock PaSD bus device.

    :yield: the test context
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_pasd_bus_device(mock_pasdbus)
    with harness as context:
        yield context


class TestPasdBusProxy:
    """Tests of the PaSD bus proxy used by the FNDH component manager."""

    @pytest.fixture(name="pasd_bus_proxy")
    def pasd_bus_proxy_fixture(
        self: TestPasdBusProxy,
        test_context: str,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
    ) -> _PasdBusProxy:
        """
        Return a proxy to the PasdBus for testing.

        This is a pytest fixture.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for the PaSD bus proxy to use
        :param mock_callbacks: A group of callables.

        :return: a proxy to the PaSD bus device.
        """
        return _PasdBusProxy(
            get_pasd_bus_name(),
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["attribute_update"],
            mock_callbacks["port_power_state"],
        )

    def test_pasd_proxy_communication(
        self: TestPasdBusProxy,
        pasd_bus_proxy: _PasdBusProxy,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test pasd proxy used by the FNDH component manager.

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


class TestFndhComponentManager:
    """Tests of the FNDH component manager."""

    @pytest.fixture(name="fndh_component_manager")
    def fndh_component_manager_fixture(
        self: TestFndhComponentManager,
        test_context: str,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
    ) -> FndhComponentManager:
        """
        Return an FNDH component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param mock_callbacks: mock callables.

        :return: an FNDH component manager.
        """
        return FndhComponentManager(
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["attribute_update"],
            mock_callbacks["port_power_state"],
            get_pasd_bus_name(),
        )

    def test_communication(
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the start_communicating command.

        :param fndh_component_manager: A FNDH component manager
            with communication established.
        :param mock_callbacks: mock callables.
        """
        fndh_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()
        assert (
            fndh_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
        )

        # check that the communication state goes to DISABLED after stop communication.
        fndh_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_command_argument",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "power_on_port",
                3,
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} success'",
            ),
            (
                "power_off_port",
                3,
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} success'",
            ),
            (
                "power_on_all_ports",
                None,
                (TaskStatus.QUEUED, "Task queued"),
                "Power on all ports success",
            ),
            (
                "power_off_all_ports",
                None,
                (TaskStatus.QUEUED, "Task queued"),
                "Power off all ports success",
            ),
        ],
    )
    def test_command(  # pylint: disable=too-many-arguments
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the FNDH object commands.

        :param fndh_component_manager: A FNDH component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param component_manager_command_argument: argument to call on component manager
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param mock_callbacks: mock callables.
        """
        fndh_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        if component_manager_command_argument:
            assert (
                getattr(fndh_component_manager, component_manager_command)(
                    component_manager_command_argument,
                    mock_callbacks["task"],
                )
                == expected_manager_result
            )
        else:
            assert (
                getattr(fndh_component_manager, component_manager_command)(
                    mock_callbacks["task"],
                )
                == expected_manager_result
            )
        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=TaskStatus.COMPLETED, result=command_tracked_response
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_command_argument",
            "pasd_proxy_command",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "power_on_port",
                0,
                "TurnSmartboxOn",
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{0} failed'",
            ),
            (
                "power_off_port",
                0,
                "TurnSmartboxOff",
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{0} failed'",
            ),
        ],
    )
    def test_proxy_return_error(  # pylint: disable=too-many-arguments
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_command: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        mock_callbacks: MockCallableGroup,
        mock_pasdbus: unittest.mock.Mock,
    ) -> None:
        """
        Test how the FNDH object handles the incorrect return type.

        This simulates the case where the pasd proxy response changes.
        For example we expect a response from the proxy of ([Any],[Any])
        Here we mock as (Any, Any, Any)

        :param fndh_component_manager: A FNDH component manager with
            communication established.
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param mock_callbacks: mock callables.
        :param mock_pasdbus: the mock PaSD bus in the test harness.
        """
        fndh_component_manager._update_communication_state(
            CommunicationStatus.ESTABLISHED
        )
        # setup to raise exception.
        mock_response = unittest.mock.MagicMock(
            side_effect=Exception("Mocked exception")
        )
        setattr(mock_pasdbus, pasd_proxy_command, mock_response)
        # check component manager can issue a command and it returns as expected
        assert (
            getattr(fndh_component_manager, component_manager_command)(
                component_manager_command_argument, mock_callbacks["task"]
            )
            == expected_manager_result
        )

        # check that the task execution is as expected
        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=TaskStatus.FAILED, result=command_tracked_response
        )
