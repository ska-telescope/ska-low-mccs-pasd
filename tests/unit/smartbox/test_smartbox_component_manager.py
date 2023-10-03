# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the SmartBox component manager."""
from __future__ import annotations

import functools
import logging
import unittest.mock
from typing import Any, Iterator

import pytest
from ska_control_model import CommunicationStatus, PowerState, TaskStatus
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.smart_box import SmartBoxComponentManager, _PasdBusProxy
from ska_low_mccs_pasd.smart_box.smart_box_component_manager import _FndhProxy
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_fndh_name,
    get_pasd_bus_name,
)


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_pasdbus: unittest.mock.Mock,
    mock_fndh: unittest.mock.Mock,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing mock PaSD bus and FNDH devices.

    :param mock_pasdbus: A mock PaSD bus device.
    :param mock_fndh: A mock FNDH device.

    :yield: the test context
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_fndh_device(mock_fndh)
    harness.set_mock_pasd_bus_device(mock_pasdbus)
    with harness as context:
        yield context


class TestPasdBusProxy:
    """Tests of the PaSD bus proxy used by the smartbox component manager."""

    @pytest.fixture(name="pasd_bus_proxy")
    def pasd_bus_proxy_fixture(
        self: TestPasdBusProxy,
        test_context: str,
        smartbox_number: int,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
    ) -> _PasdBusProxy:
        """
        Return the PaSD bus proxy used by the smartbox component manager.

        :param test_context: a test context containing the Tango devices.
        :param smartbox_number: number of the smartbox under test
        :param logger: a logger for the PaSD bus proxy to use
        :param mock_callbacks: A group of callables.

        :return: a proxy to the PaSD bus device.
        """
        return _PasdBusProxy(
            get_pasd_bus_name(),
            smartbox_number,
            logger,
            1,
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
        Test the PaSD bus proxy used by the smartbox component manager.

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

        pasd_bus_proxy.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)


class TestFndhProxy:
    """Tests of the FNDH proxy used by the smartbox component manager."""

    @pytest.fixture(name="fndh_proxy")
    def fndh_proxy_fixture(
        self: TestFndhProxy,
        test_context: str,
        fndh_port: int,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
    ) -> _FndhProxy:
        """
        Return the FNDH proxy used by the smartbox component manager.

        :param test_context: a test context containing the Tango devices.
        :param fndh_port: the FNDH port into which the smartbox is plugged
        :param logger: a logger for the PaSD bus proxy to use
        :param mock_callbacks: A group of callables.

        :return: a proxy to the PaSD bus device.
        """
        return _FndhProxy(
            get_fndh_name(),
            fndh_port,
            logger,
            1,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["port_power_state"],
        )

    def test_fndh_proxy_communication(
        self: TestFndhProxy,
        fndh_proxy: _PasdBusProxy,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test fndh proxy used by the smartbox component manager.

        :param fndh_proxy: the smartbox fndh_proxy
        :param mock_callbacks: A group of callables.
        """
        assert fndh_proxy.communication_state == CommunicationStatus.DISABLED
        fndh_proxy.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        fndh_proxy.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)


class TestSmartBoxComponentManager:
    """Tests for the SmartBox component manager."""

    @pytest.fixture(name="smartbox_component_manager")
    def smartbox_component_manager_fixture(
        self: TestSmartBoxComponentManager,
        test_context: str,
        logger: logging.Logger,
        fndh_port: int,
        mock_callbacks: MockCallableGroup,
    ) -> SmartBoxComponentManager:
        """
        Return an SmartBox component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param fndh_port: the fndh port this smartbox is attached.
        :param mock_callbacks: mock callables.

        :return: an SmartBox component manager.
        """
        component_manager = SmartBoxComponentManager(
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["attribute_update"],
            12,
            fndh_port,
            get_pasd_bus_name(),
            get_fndh_name(),
        )
        component_manager._pasd_bus_proxy._communication_state_callback = (
            component_manager._smartbox_communication_state_changed
        )
        component_manager._pasd_bus_proxy._component_state_callback = functools.partial(
            mock_callbacks["component_state"], fqdn=get_pasd_bus_name()
        )
        component_manager._fndh_proxy._communication_state_callback = (
            component_manager._fndh_communication_state_changed
        )
        component_manager._fndh_proxy._component_state_callback = functools.partial(
            mock_callbacks["component_state"], fqdn=get_fndh_name()
        )
        return component_manager

    def test_communication(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test start_communicating and stop_communicating functions.

        Check that the smartbox component manager calls the callbacks
        with the correct values.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_callbacks: A group of callables.
        """
        smartbox_component_manager.start_communicating()
        # This will call start_communicating on the proxies.
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

    def test_communication_with_proxy_none(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test that communication state does not change if proxy is None.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_callbacks: A group of callables.
        """
        smartbox_component_manager._pasd_bus_proxy = None  # type: ignore[assignment]
        with pytest.raises(AttributeError):
            smartbox_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_not_called()

    def test_component_state(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the state change callbacks upon start_communicating.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_callbacks: A group of callables.
        """
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        # Lookahead 2 needed since we do not know what callback will be called first.
        mock_callbacks["component_state"].assert_call(
            fqdn=get_pasd_bus_name(), power=PowerState.ON, lookahead=3
        )
        mock_callbacks["component_state"].assert_call(
            fqdn=get_fndh_name(), power=PowerState.ON, lookahead=3
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "on",
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "Power on smartbox '{fndh_port}  success'",
                ),
            ),
            (
                "off",
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "Power off smartbox '{fndh_port}  success'",
                ),
            ),
        ],
    )
    def test_on_off(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        component_manager_command: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        fndh_port: int,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the SmartBox On/Off Commands.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param fndh_port: the fndh port the smartbox is attached to.
        :param mock_callbacks: the mock_callbacks.
        """
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                mock_callbacks["task"]
            )
            == expected_manager_result
        )
        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=command_tracked_response[0],
            result=command_tracked_response[1].format(fndh_port=fndh_port),
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_command_argument",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "turn_on_port",
                3,
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} success'",
            ),
            (
                "turn_off_port",
                3,
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} success'",
            ),
        ],
    )
    def test_command(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the SmartBox commands.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param component_manager_command_argument: argument to call on component manager
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param mock_callbacks: A group of callables.
        """
        smartbox_component_manager._power_state = PowerState.ON
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        assert (
            getattr(smartbox_component_manager, component_manager_command)(
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
                "turn_on_port",
                3,
                "TurnAntennaOn",
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} failed'",
            ),
            (
                "turn_off_port",
                3,
                "TurnAntennaOff",
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} failed'",
            ),
        ],
    )
    def test_command_fail(  # pylint: disable=too-many-arguments
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_pasdbus: unittest.mock.Mock,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        pasd_proxy_command: Any,
        expected_manager_result: Any,
        command_tracked_response: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test how the SmartBoxComponentManager object handles a failed command.

        :param smartbox_component_manager: A SmartBox component manager with
            communication established.
        :param mock_pasdbus: the mock PaSD bus that is set in the test harness
        :param component_manager_command: command to issue to the component manager
        :param pasd_proxy_command: component to mock on proxy
        :param component_manager_command_argument: argument to call on component manager
        :param expected_manager_result: expected response from the call
        :param command_tracked_response: The result of the command.
        :param mock_callbacks: the mock_callbacks.
        """
        # To turn off on a smartbox the smartbox itself must be on and communicating.
        smartbox_component_manager._power_state = PowerState.ON
        smartbox_component_manager._update_communication_state(
            CommunicationStatus.ESTABLISHED
        )
        # setup to raise exception.
        mock_response = unittest.mock.MagicMock(
            side_effect=Exception("Mocked exception")
        )
        setattr(mock_pasdbus, pasd_proxy_command, mock_response)

        # check component manager can issue a command and it returns failed command.
        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                component_manager_command_argument, mock_callbacks["task"]
            )
            == expected_manager_result
        )

        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=TaskStatus.FAILED, result=command_tracked_response
        )
