# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the SmartBox component manager."""
from __future__ import annotations

import logging
import unittest.mock
from typing import Any

import pytest
from ska_control_model import (
    CommunicationStatus,
    PowerState,
    ResultCode,
    TaskStatus,
)
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.pasd_bus import MccsPasdBus
from ska_low_mccs_pasd.smart_box import SmartBoxComponentManager


@pytest.fixture(name="callbacks")
def callbacks_fixture() -> MockCallableGroup:
    """
    Return a dictionary of callables to be used as callbacks.

    :return: a dictionary of callables to be used as callbacks.
    """
    return MockCallableGroup(
        "communication_status",
        "component_state",
        "task_callback",
        timeout=2.0,
    )


@pytest.fixture(name="mocked_pasd_proxy")
def mocked_pasd_proxy_fixture(smartbox_number: int) -> unittest.mock.Mock:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :param smartbox_number: the smartbox number used
        to get the subscription list.
    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    mock = unittest.mock.Mock()
    mock.GetPasdDeviceSubscriptions = unittest.mock.Mock(
        return_value=MccsPasdBus._ATTRIBUTE_MAP[int(smartbox_number)].values()
    )
    return mock


@pytest.fixture(name="mocked_fndh_proxy")
def mocked_fndh_proxy_fixture() -> unittest.mock.Mock:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return unittest.mock.Mock()


@pytest.fixture(name="fndh_port")
def fndh_port_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 5


@pytest.fixture(name="smartbox_number")
def smartbox_number_fixture() -> int:
    """
    Return the id of the station whose configuration will be used in testing.

    :return: the id of the station whose configuration will be used in
        testing.
    """
    return 1


@pytest.fixture(name="smartbox_component_manager")
def smartbox_component_manager_fixture(  # pylint: disable=too-many-arguments
    logger: logging.Logger,
    pasd_bus_fndh: str,
    fndh_bus_fndh: str,
    mock_callbacks: MockCallableGroup,
    mocked_pasd_proxy: unittest.mock.Mock,
    mocked_fndh_proxy: unittest.mock.Mock,
    smartbox_number: int,
) -> SmartBoxComponentManager:
    """
    Return an SmartBox component manager.

    (This is a pytest fixture.)

    :param logger: a logger for this command to use.
    :param pasd_bus_fndh: the pasd bus smartbox
    :param fndh_bus_fndh: the fndh smartbox
    :param mock_callbacks: mock callables.
    :param mocked_pasd_proxy: a unittest.mock
    :param mocked_fndh_proxy: a unittest.mock
    :param smartbox_number: the number assigned to this smartbox.

    :return: an APIU component manager in the specified simulation mode.
    """
    component_manager = SmartBoxComponentManager(
        logger,
        mock_callbacks["communication_state"],
        mock_callbacks["component_state"],
        mock_callbacks["attribute_update"],
        pasd_bus_fndh,
        fndh_bus_fndh,
        smartbox_number,
        mocked_pasd_proxy,
        mocked_fndh_proxy,
    )
    mocked_pasd_proxy._change_event_subscription_ids = {}
    mocked_pasd_proxy.fndhPortsPowerSensed = [False] * 24

    component_manager.start_communicating()

    return component_manager


class TestSmartBoxComponentManager:
    """Tests for the SmartBox component manager."""

    def test_communication(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the start_communicating command.

        WARNING: This can take a considerable amount of time for a timeout.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_callbacks: mock callables.
        :param mocked_pasd_proxy: a unittest.mock
        """
        # The fixture starts communicating.
        # We should transition from NOT_ESTABLISHED to ESTABLISHED.
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        # check that the communication state goes to DISABLED after stop communication.
        smartbox_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()

        # Check failed MccsDeviceProxy acts as desired.
        # This will attempt to form a proxy and time out,
        # due to no tango device resolution.
        smartbox_component_manager._pasd_bus_proxy = None
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        # ------------------------------
        # CHECK START STOP COMMUNICATION
        # ------------------------------
        smartbox_component_manager._pasd_bus_proxy = mocked_pasd_proxy
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        smartbox_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()

        # ----------------------------
        # MOCK FAILURE IN UPDATE STATE
        # ----------------------------
        mock_error = unittest.mock.Mock(
            side_effect=Exception("attribute mocked to fail")
        )
        smartbox_component_manager._pasd_bus_proxy.ping = unittest.mock.MagicMock(
            side_effect=mock_error
        )  # type: ignore[assignment]
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        # ------------------------------
        # STOP COMMUNICATION
        # ------------------------------
        smartbox_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()

        # -------------------------
        # MOCK FAILURE IN SUBSCRIBE
        # -------------------------
        mock_error = unittest.mock.Mock(
            side_effect=Exception("attribute mocked to fail")
        )
        smartbox_component_manager._pasd_bus_proxy.add_change_event_callback = (
            unittest.mock.MagicMock(side_effect=mock_error)  # type: ignore[assignment]
        )
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

    def test_component_state(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_callbacks: MockCallableGroup,
        mocked_fndh_proxy: unittest.mock.Mock,
    ) -> None:
        """
        Test the start_communicating command.

        WARNING: This can take a considerable amount of time for a timeout.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_callbacks: mock callables.
        :param mocked_fndh_proxy: The mocked fndh proxy.
        """
        # The fixture starts communicating.
        # We should transition from NOT_ESTABLISHED to ESTABLISHED.
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        # state transitions
        mock_callbacks["component_state"].assert_call(power=PowerState.UNKNOWN)

        # check that the communication state goes to DISABLED after stop communication.
        smartbox_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["communication_state"].assert_not_called()

        # Now mock start_communicating with a known fndh_port:
        mocked_fndh_proxy.Port2PowerState = False
        smartbox_component_manager._fndh_port = 2

        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_not_called()

        mock_callbacks["component_state"].assert_call(power=PowerState.OFF)

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "pasd_proxy_command",
            "pasd_proxy_response",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "on",
                "TurnFndhPortOn",
                ([ResultCode.OK], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.FAILED,
                    "cannot turn on Unknown FNDH port.",
                ),
            ),
            (
                "off",
                "TurnFndhPortOff",
                ([ResultCode.OK], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.FAILED,
                    "cannot turn off Unknown FNDH port.",
                ),
            ),
        ],
    )
    def test_on_off_without_port_knowledge(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        pasd_proxy_command: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the SmartBox On/Off Commands.

        The Smartbox will be instructed by the station of its FNDH port number.
        This is determined dynamically by the startup_sequence.

        The station will turn on each FNDH port in 5 second intervals
        and then loop round the smartboxes reading the Uptime,
        correlate to find what smartbox is attached to what port when
        write to the smartbox telling it its port.

        Here we are simulating trying to turn On/Off a smartbox
        when it has no knowledge of the port it is attached to.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param callbacks: the callbacks.
        """
        # set up the proxy responce
        mock_response = unittest.mock.MagicMock(return_value=pasd_proxy_response)
        setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)

        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                callbacks["task_callback"]
            )
            == expected_manager_result
        )
        callbacks["task_callback"].assert_call(status=TaskStatus.QUEUED)
        callbacks["task_callback"].assert_call(status=TaskStatus.IN_PROGRESS)
        callbacks["task_callback"].assert_call(
            status=command_tracked_response[0], result=command_tracked_response[1]
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "pasd_proxy_command",
            "pasd_proxy_response",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "on",
                "TurnFndhPortOn",
                ([ResultCode.OK], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    f"Power on smartbox '{2}  success'",
                ),
            ),
            (
                "off",
                "TurnFndhPortOff",
                ([ResultCode.OK], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    f"Power off smartbox '{2}  success'",
                ),
            ),
        ],
    )
    def test_on_off_with_port_knowledge(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        pasd_proxy_command: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the SmartBox On/Off Commands.

        The Smartbox will be instructed by the station of its FNDH port number.
        This is determined dynamically by the startup_sequence.

        The station will turn on each FNDH port in 5 second intervals
        and then loop round the smartboxes reading the Uptime,
        correlate to find what smartbox is attached to what port when
        write to the smartbox telling it its port.

        Here we are simulating trying to turn On/Off a smartbox
        when it has knowledge of the port it is attached to.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param callbacks: the callbacks.
        """
        # Simulate the Station telling the smartbox its port its fndh port is 2.
        smartbox_component_manager._fndh_port = 2

        # set up the proxy responce
        mock_response = unittest.mock.MagicMock(return_value=pasd_proxy_response)
        setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)

        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                callbacks["task_callback"]
            )
            == expected_manager_result
        )
        callbacks["task_callback"].assert_call(status=TaskStatus.QUEUED)
        callbacks["task_callback"].assert_call(status=TaskStatus.IN_PROGRESS)
        callbacks["task_callback"].assert_call(
            status=command_tracked_response[0], result=command_tracked_response[1]
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
                "turn_on_port",
                3,
                "TurnSmartboxPortOn",
                ([True], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} success'",
            ),
            (
                "turn_off_port",
                3,
                "TurnSmartboxPortOff",
                ([True], [True]),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} success'",
            ),
        ],
    )
    def test_command(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_command: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the SmartBox object commands.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param callbacks: the callbacks.
        """
        # set up the proxy responce
        if component_manager_command_argument is None:
            setattr(mocked_pasd_proxy, pasd_proxy_command, pasd_proxy_response)
            assert (
                getattr(smartbox_component_manager, component_manager_command)
                == expected_manager_result
            )

        else:
            mock_response = unittest.mock.Mock(return_value=pasd_proxy_response)
            setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)
            mocked_pasd_proxy.TurnSmartboxOff = unittest.mock.Mock(
                return_value=pasd_proxy_response
            )
            assert (
                getattr(smartbox_component_manager, component_manager_command)(
                    component_manager_command_argument, callbacks["task_callback"]
                )
                == expected_manager_result
            )
            callbacks["task_callback"].assert_call(status=TaskStatus.QUEUED)
            callbacks["task_callback"].assert_call(status=TaskStatus.IN_PROGRESS)
            callbacks["task_callback"].assert_call(
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
                "turn_on_port",
                3,
                "TurnAntennaOn",
                (True, True, "wrong_response"),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} failed'",
            ),
            (
                "turn_off_port",
                3,
                "TurnAntennaOff",
                (True, True, "wrong_response"),
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} failed'",
            ),
        ],
    )
    def test_proxy_return_error(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mocked_pasd_proxy: unittest.mock.Mock,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_command: Any,
        pasd_proxy_response: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        callbacks: MockCallableGroup,
    ) -> None:
        """
        Test how the SmartBox object handles the incorrect return type.

        This simulates the case where the pasd proxy response changes.
        For example we expect a response from the proxy of ([Any],[Any])
        Here we mock as (Any, Any, Any)

        :param smartbox_component_manager: A SmartBox component manager with
            communication established.
        :param mocked_pasd_proxy: a unittest.mock
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param pasd_proxy_response: mocked response
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param callbacks: the callbacks.
        """
        # setup the response from the mocked pasd proxy
        mock_response = unittest.mock.MagicMock(return_value=pasd_proxy_response)
        setattr(mocked_pasd_proxy, pasd_proxy_command, mock_response)

        # check component manager can issue a command and it returns as expected
        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                component_manager_command_argument, callbacks["task_callback"]
            )
            == expected_manager_result
        )

        callbacks["task_callback"].assert_call(status=TaskStatus.QUEUED)
        callbacks["task_callback"].assert_call(status=TaskStatus.IN_PROGRESS)
        callbacks["task_callback"].assert_call(
            status=TaskStatus.FAILED, result=command_tracked_response
        )
