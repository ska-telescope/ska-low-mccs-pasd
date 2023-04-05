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
import time
import unittest.mock
from typing import Any

import pytest
from ska_control_model import CommunicationStatus, TaskStatus
from ska_tango_testing.mock import MockCallableGroup
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.fndh import FndhComponentManager


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return MockTangoEventCallbackGroup(
        "adminMode",
        "healthState",
        "longRunningCommandResult",
        "longRunningCommandStatus",
        "state",
    )


@pytest.fixture(name="mocked_pasd_proxy")
def mocked_pasd_proxy_fixture() -> unittest.mock.Mock:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return unittest.mock.Mock()


@pytest.fixture(name="task_callback")
def task_callback_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return unittest.mock.Mock()


@pytest.fixture(name="fndh_component_manager")
def fndh_component_manager_fixture(
    logger: logging.Logger,
    pasd_bus_fndh: str,
    mock_callbacks: MockCallableGroup,
    mocked_pasd_proxy: unittest.mock.Mock,
) -> FndhComponentManager:
    """
    Return an FNDH component manager.

    (This is a pytest fixture.)

    :param logger: a logger for this command to use.
    :param pasd_bus_fndh: the pasd bus fndh
    :param mock_callbacks: mock callables.
    :param mocked_pasd_proxy: a unittest.mock

    :return: an APIU component manager in the specified simulation mode.
    """
    component_manager = FndhComponentManager(
        logger,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        pasd_bus_fndh,
        mocked_pasd_proxy,
    )
    mocked_pasd_proxy._change_event_subscription_ids = {}
    mocked_pasd_proxy.fndhPortsPowerSensed = [True] * 24
    component_manager.start_communicating()

    return component_manager


class TestFndhComponentManager:
    """Tests for the FNDH component manager."""

    def test_communication(
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the start_communicating command.

        WARNING: This can take a considerable amount of time for a timeout.

        :param fndh_component_manager: A FNDH component manager
            with communication established.
        :param mock_callbacks: mock callables.
        :param mocked_pasd_proxy: a unittest.mock
        """
        # The fixture start communicating, check that the communication state
        # transistions as expected.
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        # check that the communication state goes to DISABLED after stop communication.
        fndh_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()

        # Check failed MccsDeviceProxy acts as desired.
        # This will attempt to form a proxy and time out,
        # due to no tango device resolution.
        fndh_component_manager._pasd_bus_proxy = None
        fndh_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        # check that we can for start communication again.
        fndh_component_manager._pasd_bus_proxy = mocked_pasd_proxy
        fndh_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "pasd_proxy_command",
            "component_manager_command_argument",
            "pasd_proxy_response",
            "expected_manager_result",
        ),
        [
            (
                "smartbox_statuses",
                "smartboxStatuses",
                None,
                [False] * 24,
                [False] * 24,
            ),
            (
                "is_port_on",
                "fndhPortsPowerSensed",
                None,
                False,
                False,
            ),
            (
                "get_smartbox_info",
                "GetSmartboxInfo",
                3,
                {"status": "OK"},
                {"status": "OK"},
            ),
        ],
    )
    def test_attributes(  # pylint: disable=too-many-arguments
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        pasd_proxy_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
    ) -> None:
        """
        Test the FNDH object attributes.

        :param fndh_component_manager: A FNDH component manager
            with communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        """
        # set up the proxy responce
        if component_manager_command_argument is None:
            setattr(mocked_pasd_proxy, pasd_proxy_command, pasd_proxy_response)
            assert (
                getattr(fndh_component_manager, component_manager_command)
                == expected_manager_result
            )
        else:
            mock_response = unittest.mock.MagicMock(return_value=pasd_proxy_response)
            setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)
            mocked_pasd_proxy.TurnSmartboxOff = unittest.mock.MagicMock(
                return_value=pasd_proxy_response
            )
            assert (
                getattr(fndh_component_manager, component_manager_command)(
                    component_manager_command_argument
                )
                == expected_manager_result
            )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_command_argument",
            "pasd_proxy_command",
            "pasd_proxy_response",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "power_on_port",
                3,
                "TurnSmartboxOn",
                ([True], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} success'",
            ),
            (
                "power_off_port",
                3,
                "TurnSmartboxOff",
                ([True], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} success'",
            ),
        ],
    )
    def test_command(  # pylint: disable=too-many-arguments
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_command: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        task_callback: unittest.mock.Mock,
    ) -> None:
        """
        Test the FNDH object commands.

        :param fndh_component_manager: A FNDH component manager
            with communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param task_callback: the task_callback.
        """
        # set up the proxy responce
        if component_manager_command_argument is None:
            setattr(mocked_pasd_proxy, pasd_proxy_command, pasd_proxy_response)
            assert (
                getattr(fndh_component_manager, component_manager_command)
                == expected_manager_result
            )

        else:
            mock_response = unittest.mock.MagicMock(return_value=pasd_proxy_response)
            setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)
            mocked_pasd_proxy.TurnSmartboxOff = unittest.mock.MagicMock(
                return_value=pasd_proxy_response
            )
            assert (
                getattr(fndh_component_manager, component_manager_command)(
                    component_manager_command_argument, task_callback
                )
                == expected_manager_result
            )
            task_callback.assert_called_with(
                status=TaskStatus.COMPLETED, result=command_tracked_response
            )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_command_argument",
            "pasd_proxy_command",
            "pasd_proxy_response",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "power_on_port",
                3,
                "TurnSmartboxOn",
                (True, True, "wrong_response"),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} failed'",
            ),
            (
                "power_off_port",
                3,
                "TurnSmartboxOff",
                (True, True, "wrong_response"),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} failed'",
            ),
        ],
    )
    def test_proxy_return_error(  # pylint: disable=too-many-arguments
        self: TestFndhComponentManager,
        fndh_component_manager: FndhComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_command: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        task_callback: unittest.mock.Mock,
    ) -> None:
        """
        Test how the FNDH object handles the incorrect return type.

        This simulates the case where the pasd proxy response changes.
        For example we expect a response from the proxy of ([Any],[Any])
        Here we mock as (Any, Any, Any)

        :param fndh_component_manager: A FNDH component manager with
            communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param task_callback: the task_callback.
        """
        # setup the response from the mocked pasd proxy
        mock_response = unittest.mock.MagicMock(return_value=pasd_proxy_response)
        setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)

        # check component manager can issue a command and it returns as expected
        assert (
            getattr(fndh_component_manager, component_manager_command)(
                component_manager_command_argument, task_callback
            )
            == expected_manager_result
        )

        # check that the task execution is as expected
        time.sleep(0.01)
        task_callback.assert_called_with(
            status=TaskStatus.FAILED, result=command_tracked_response
        )
