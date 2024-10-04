# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the SmartBox component manager."""
from __future__ import annotations

import json
import logging
import time
import unittest.mock
from datetime import datetime, timezone
from typing import Any, Iterator

import pytest
import tango
from ska_control_model import CommunicationStatus, PowerState, ResultCode, TaskStatus
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd import PasdData
from ska_low_mccs_pasd.smart_box import SmartBoxComponentManager, _PasdBusProxy
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_field_station_name,
    get_pasd_bus_name,
)

SMARTBOX_PORTS = 12


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_pasdbus: unittest.mock.Mock,
    mock_field_station: unittest.mock.Mock,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing mock PaSD bus and FNDH devices.

    :param mock_pasdbus: A mock PaSD bus device.
    :param mock_field_station: A mock FieldStation device.

    :yield: the test context
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_field_station_device(mock_field_station)
    harness.set_mock_pasd_bus_device(mock_pasdbus)
    with harness as context:
        yield context


class TestPasdBusProxy:
    """Tests of the PaSD bus proxy used by the smartbox component manager."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    @pytest.fixture(name="pasd_bus_proxy")
    def pasd_bus_proxy_fixture(
        self: TestPasdBusProxy,
        test_context: str,
        smartbox_number: int,
        fndh_port: int,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
    ) -> _PasdBusProxy:
        """
        Return the PaSD bus proxy used by the smartbox component manager.

        :param test_context: a test context containing the Tango devices.
        :param smartbox_number: number of the smartbox under test.
        :param fndh_port: the fndh port this smartbox is attached to.
        :param logger: a logger for the PaSD bus proxy to use
        :param mock_callbacks: A group of callables.

        :return: a proxy to the PaSD bus device.
        """
        return _PasdBusProxy(
            get_pasd_bus_name(),
            smartbox_number,
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["smartbox_power_state"],
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

    def test_attribute_change_events(
        self: TestPasdBusProxy,
        pasd_bus_proxy: _PasdBusProxy,
        smartbox_number: int,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the attribute change event callback produces correct attribute names.

        :param pasd_bus_proxy: A proxy to the pasd_bus device.
        :param smartbox_number: number of the smartbox under test.
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

        # Choose an example attribute to send event for
        attribute = f"smartbox{smartbox_number}PcbTemperature"
        smartbox_attribute = "PcbTemperature".lower()

        # Pretend to receive a change event
        pasd_bus_proxy._on_attribute_change(
            attr_name=attribute,
            attr_value=50,
            attr_quality=tango.AttrQuality.ATTR_VALID,
        )
        mock_callbacks["attribute_update"].assert_call(
            smartbox_attribute,
            50,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

    def test_invalid_attribute_change_events(
        self: TestPasdBusProxy,
        pasd_bus_proxy: _PasdBusProxy,
        smartbox_number: int,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the callback produces INVALID attributes when device is unavailable.

        :param pasd_bus_proxy: A proxy to the pasd_bus device.
        :param smartbox_number: number of the smartbox under test.
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

        # Choose an example attribute to send event for
        attribute = f"smartbox{smartbox_number}PcbTemperature"
        smartbox_attribute = "PcbTemperature".lower()

        # Pretend to receive a change event
        pasd_bus_proxy._on_attribute_change(
            attr_name=attribute,
            attr_value=50,
            attr_quality=tango.AttrQuality.ATTR_INVALID,
        )
        mock_callbacks["attribute_update"].assert_call(
            smartbox_attribute,
            50,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_INVALID,
        )


class TestSmartBoxComponentManager:
    """Tests for the SmartBox component manager."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    @pytest.fixture(name="smartbox_component_manager")
    def smartbox_component_manager_fixture(
        self: TestSmartBoxComponentManager,
        test_context: str,
        logger: logging.Logger,
        smartbox_number: int,
        fndh_port: int,
        mock_callbacks: MockCallableGroup,
    ) -> SmartBoxComponentManager:
        """
        Return an SmartBox component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param smartbox_number: number of the smartbox under test.
        :param fndh_port: the fndh port this smartbox is attached to.
        :param mock_callbacks: mock callables.

        :return: an SmartBox component manager.
        """
        component_manager = SmartBoxComponentManager(
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["attribute_update"],
            smartbox_number,
            f"sb{smartbox_number:02d}",
            SMARTBOX_PORTS,
            get_field_station_name(),
            get_pasd_bus_name(),
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
        # check that the communication state goes to DISABLED after stop communication.
        smartbox_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)

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

        mock_callbacks["attribute_update"].assert_call(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        # To transition to a state we need to know what fndh port we are on.
        # Lookahead 2 is needed incase this information is not initially known
        # We first transtion to UNKNOWN,
        # then when we know the state we transition to ON/OFF
        mock_callbacks["component_state"].assert_call(power=PowerState.ON, lookahead=2)

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
                    (ResultCode.OK, "Power on smartbox '{fndh_port} OK'"),
                ),
            ),
            (
                "off",
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    (ResultCode.OK, "Power off smartbox '{fndh_port} OK'"),
                ),
            ),
        ],
    )
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_on_off(
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
        mock_callbacks["component_state"].assert_call(power=PowerState.UNKNOWN)

        mock_callbacks["attribute_update"].assert_call(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        mock_callbacks["component_state"].assert_call(power=PowerState.ON)
        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                mock_callbacks["task"]
            )
            == expected_manager_result
        )
        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)

        # Once the command has started, smartbox waits for fndh ports to change state.
        # Let's pretend that happened.
        smartbox_component_manager._on_fndh_ports_power_changed(
            "fndhportspowersensed",
            [component_manager_command == "on"] * PasdData.NUMBER_OF_FNDH_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        mock_callbacks["task"].assert_call(
            status=command_tracked_response[0],
            result=(
                command_tracked_response[1][0],
                command_tracked_response[1][1].format(fndh_port=fndh_port),
            ),
        )

    @pytest.mark.parametrize(
        ("initial_state"),
        ["on", "off"],
    )
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_standby(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_pasdbus: unittest.mock.Mock,
        fndh_port: int,
        smartbox_number: int,
        mock_callbacks: MockCallableGroup,
        initial_state: str,
    ) -> None:
        """
        Test the SmartBox Standby Command.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_pasdbus: the mock PaSD bus that is set in the test harness
        :param fndh_port: the fndh port the smartbox is attached to.
        :param smartbox_number: the number of the smartbox under test.
        :param mock_callbacks: the mock_callbacks.
        :param initial_state: the state before we call Standby().
        """
        # make all other ports the opposite.
        mock_setup = [initial_state == "off"] * 28
        mock_setup[fndh_port - 1] = not mock_setup[fndh_port - 1]
        mock_pasdbus.configure_mock(fndhPortsPowerSensed=mock_setup)
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        mock_callbacks["component_state"].assert_call(power=PowerState.UNKNOWN)

        mock_callbacks["attribute_update"].assert_call(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )
        match initial_state:
            case "off":
                mock_callbacks["component_state"].assert_call(power=PowerState.OFF)
            case "on":
                mock_callbacks["component_state"].assert_call(power=PowerState.ON)
            case _:
                pytest.fail("Unknown initial state.")

        smartbox_component_manager.standby(task_callback=mock_callbacks["task"])

        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)

        # Once the task has started, the smartbox will expect to receive change events
        # on FNDH port powers and its own Smartbox port powers, so we will pretend to
        # receive them.

        # If we start in the OFF state, we expect that the FNDH port will be powered on
        if initial_state == "off":
            fndh_port_powers: list[bool | None] = [None] * PasdData.NUMBER_OF_FNDH_PORTS
            fndh_port_powers[fndh_port - 1] = True
            expected_fndh_powers = json.dumps(
                {
                    "port_powers": fndh_port_powers,
                    "stay_on_when_offline": True,
                }
            )
            mock_pasdbus.SetFndhPortPowers.assert_next_call(expected_fndh_powers)

            # We have checked the PasdBus is sent the correct command, lets now assume
            # it did the correct thing and we get the correct change event.
            smartbox_component_manager._on_fndh_ports_power_changed(
                "fndhportspowersensed",
                [fndh_port_power is not None for fndh_port_power in fndh_port_powers],
                tango.AttrQuality.ATTR_VALID,
            )

        # We expect all smartbox ports to be turned OFF.
        expected_smartbox_powers = json.dumps(
            {
                "port_powers": [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
                "stay_on_when_offline": True,
                "smartbox_number": smartbox_number,
            }
        )

        # We have checked the PasdBus is sent the correct command, lets now assume
        # it did the correct thing and we get the correct change event.
        mock_pasdbus.SetSmartboxPortPowers.assert_next_call(expected_smartbox_powers)

        # We've sent the command, lets now pretend it worked and we got a
        # change event from PasdBus.
        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [False] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        # Now that our ports have all changed to the correct state, the command should
        # now finish.
        mock_callbacks["task"].assert_call(
            status=TaskStatus.COMPLETED,
            result=(
                ResultCode.OK,
                f"Power smartbox '{fndh_port} to standby OK'",
            ),
        )

        # And after all is said and done, the component manager should be in STANDBY.
        assert smartbox_component_manager._power_state == PowerState.STANDBY

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "masked_ports",
            "expected_manager_result",
            "command_tracked_response",
        ),
        [
            (
                "set_port_powers",
                [1, 4, 5],
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "Set port powers success",
                ),
            ),
        ],
    )
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_all_port_commands(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        component_manager_command: Any,
        masked_ports: list,
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
        :param masked_ports: the ports to mask in this test.
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

        desired_port_powers: list[bool | None]

        desired_port_powers = [True] * SMARTBOX_PORTS
        for masked_port in masked_ports:
            desired_port_powers[masked_port - 1] = None

        json_argument = json.dumps(
            {
                "smartbox_number": smartbox_component_manager._smartbox_nr,
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )

        assert (
            getattr(smartbox_component_manager, component_manager_command)(
                json_argument,
                task_callback=mock_callbacks["task"],
            )
            == expected_manager_result
        )

        pasd_bus_proxy = smartbox_component_manager._pasd_bus_proxy._proxy
        assert pasd_bus_proxy
        pasd_bus_proxy.SetSmartboxPortPowers.assert_next_call(json_argument)

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
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_command(
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
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        mock_callbacks["attribute_update"].assert_call(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        # To turn off on a smartbox the smartbox itself must be on and communicating.
        timeout = 10
        start_time = time.time()
        while time.time() < start_time + timeout:
            if smartbox_component_manager._power_state == PowerState.ON:
                break
            time.sleep(0.1)

        assert smartbox_component_manager._power_state == PowerState.ON

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
                "SetSmartboxPortPowers",
                (TaskStatus.QUEUED, "Task queued"),
                f"Power on port '{3} failed'",
            ),
            (
                "turn_off_port",
                3,
                "SetSmartboxPortPowers",
                (TaskStatus.QUEUED, "Task queued"),
                f"Power off port '{3} failed'",
            ),
        ],
    )
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_command_fail(
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
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        mock_callbacks["attribute_update"].assert_call(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        # To turn off on a smartbox the smartbox itself must be on and communicating.
        timeout = 10
        start_time = time.time()
        while time.time() < start_time + timeout:
            if smartbox_component_manager._power_state == PowerState.ON:
                break
            time.sleep(0.1)

        assert smartbox_component_manager._power_state == PowerState.ON

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

    def test_configuration_change(
        self: TestSmartBoxComponentManager,
        smartbox_component_manager: SmartBoxComponentManager,
        mock_callbacks: MockCallableGroup,
        mock_pasdbus: unittest.mock.Mock,
        alternate_input_smartbox_mapping: str,
        changed_fndh_port: int,
    ) -> None:
        """
        Test that a change in fieldstation configuration is noticed.

        :param smartbox_component_manager: A SmartBox component manager
            with communication established.
        :param mock_callbacks: A group of callables.
        :param mock_pasdbus: A mock pasdBus
        :param alternate_input_smartbox_mapping: an alternate smartbox mapping to use.
        :param changed_fndh_port: the new port for this smartbox.
        """
        smartbox_component_manager.start_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        mock_callbacks["component_state"].assert_call(power=PowerState.UNKNOWN)

        mock_callbacks["attribute_update"].assert_call(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            pytest.approx(datetime.now(timezone.utc).timestamp()),
            tango.AttrQuality.ATTR_VALID,
        )

        smartbox_component_manager._on_smartbox_ports_power_changed(
            "portspowersensed",
            [True] * PasdData.NUMBER_OF_SMARTBOX_PORTS,
            tango.AttrQuality.ATTR_VALID,
        )

        mock_callbacks["component_state"].assert_call(power=PowerState.ON)

        # mock a callback from the fieldstation when it changes state.
        # We are placing the smartbox on a new port that is OFF.
        smartbox_component_manager._on_mapping_change(
            "smartboxmapping",
            alternate_input_smartbox_mapping,
            tango.AttrQuality.ATTR_VALID,
        )
        mock_callbacks["component_state"].assert_call(power=PowerState.OFF, lookahead=2)

        mock_pasdbus.set_fndh_port_powers = unittest.mock.Mock()

        # Check that when we turn on the correct port for this new configuration.
        smartbox_component_manager.on()
        desired_port_powers: list[bool | None] = [None] * PasdData.NUMBER_OF_FNDH_PORTS
        desired_port_powers[changed_fndh_port - 1] = True
        json_argument = json.dumps(
            {
                "port_powers": desired_port_powers,
                "stay_on_when_offline": True,
            }
        )
        mock_pasdbus.SetFndhPortPowers.assert_next_call(json_argument)


@pytest.fixture(name="alternate_input_smartbox_mapping")
def alternate_input_smartbox_mapping_fixture(
    input_smartbox_mapping: dict[str, Any],
    smartbox_number: int,
    changed_fndh_port: int,
) -> str:
    """
    Alternate configuration to use in smartbox.

    This is to simulate a change in the fieldstations configuration.

    :param input_smartbox_mapping: A mocked fieldstation smartboxMapping
        attribute value.
    :param smartbox_number: the id of this smartbox
    :param changed_fndh_port: the new port to place this smartbox.

    :return: a string representing the smartbox mapping reported by fieldstation.
    """
    smartbox_mapping = input_smartbox_mapping["smartboxMapping"]

    # The smartbox under test is attached to the port
    # given by fixture changed_fndh_port!!
    smartbox_mapping[f"sb{(smartbox_number):02d}"] = changed_fndh_port

    return json.dumps({"smartboxMapping": smartbox_mapping})
