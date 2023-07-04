# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the FNDH component manager."""
from __future__ import annotations

import unittest.mock
from typing import Any

import pytest
from ska_control_model import CommunicationStatus, TaskStatus
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.fndh import FndhComponentManager, _PasdBusProxy


class TestFndhComponentManager:
    """Tests for the FNDH component manager."""

    def test_pasd_proxy_communication(
        self: TestFndhComponentManager,
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
        assert (
            getattr(fndh_component_manager, component_manager_command)(
                component_manager_command_argument,
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
        pasd_bus_proxy: _PasdBusProxy,
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
        :param pasd_bus_proxy: a proxy to the PaSDBusdevice.
        """
        fndh_component_manager._update_communication_state(
            CommunicationStatus.ESTABLISHED
        )
        # setup to raise exception.
        mock_response = unittest.mock.MagicMock(
            side_effect=Exception("Mocked exception")
        )
        setattr(pasd_bus_proxy, pasd_proxy_command, mock_response)
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
