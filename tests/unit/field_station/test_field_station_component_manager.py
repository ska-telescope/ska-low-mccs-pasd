# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the field_station component manager."""
from __future__ import annotations

import json
import logging
import time
import unittest.mock
from typing import Any, Iterator
from unittest.mock import ANY, MagicMock, call, patch

import pytest
import tango
from ska_control_model import CommunicationStatus, PowerState, ResultCode, TaskStatus
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.field_station import FieldStationComponentManager
from ska_low_mccs_pasd.pasd_data import PasdData
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_fndh_name,
    get_smartbox_name,
)


@pytest.fixture(name="mock_smartbox")
def mock_smartboxes_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsSmartBox device.

    :return: a mock MccsSmartBox device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_command("On", ([ResultCode.OK], ["Dummy return string"]))
    builder.add_command("Standby", ([ResultCode.OK], ["Dummy return string"]))
    builder.add_result_command("PowerOnPort", ResultCode.OK)
    builder.add_result_command("PowerOffPort", ResultCode.OK)
    builder.add_result_command("SetPortPowers", ResultCode.QUEUED)
    builder.add_attribute("fndhPort", json.dumps(1))
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    builder.add_result_command(
        "PowerOnAntenna", ResultCode.OK, "power on antenna sb18-01 success."
    )
    builder.add_result_command(
        "PowerOffAntenna", ResultCode.OK, "power off antenna sb18-01 success."
    )
    builder.add_attribute("antennaNames", ["sb18-01"])
    return builder()


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture(mocked_outside_temperature: float) -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFndh device.

    :param mocked_outside_temperature: the mocked outside temperature.

    :return: a mock MccsFndh device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.STANDBY)
    builder.add_result_command("PowerOnPort", ResultCode.OK)
    builder.add_result_command("PowerOffPort", ResultCode.OK)
    builder.add_result_command("SetPortPowers", ResultCode.QUEUED)
    builder.add_attribute("OutsideTemperature", mocked_outside_temperature)
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    builder.add_result_command("Standby", ResultCode.OK)
    builder.add_result_command("On", ResultCode.OK)
    return builder()


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_fndh: unittest.mock.Mock, mock_smartbox: unittest.mock.Mock, station_label: str
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing a single mock PaSD bus device.

    :param mock_fndh: A mock FNDH device.
    :param mock_smartbox: A mock Smartbox devices.
    :param station_label: The label of the station under test.

    :yield: the test context
    """
    harness = PasdTangoTestHarness(station_label=station_label)
    harness.set_mock_fndh_device(mock_fndh)
    for smartbox_id in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        harness.set_mock_smartbox_device(mock_smartbox, smartbox_id)
    with harness as context:
        yield context


class TestFieldStationComponentManager:
    """Tests of the FieldStation component manager."""

    @pytest.fixture(name="field_station_component_manager")
    def field_station_component_manager_fixture(
        self: TestFieldStationComponentManager,
        test_context: str,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
        station_label: str,
    ) -> FieldStationComponentManager:
        """
        Return an FieldStation component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param mock_callbacks: mock callables.
        :param station_label: The label of the station under test.

        :return: an FieldStation component manager.
        """
        return FieldStationComponentManager(
            logger,
            "ci-1",
            get_fndh_name(station_label=station_label),
            [
                get_smartbox_name(smartbox_id, station_label=station_label)
                for smartbox_id in range(
                    1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1
                )
            ],
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
        )

    def test_outside_temperature(
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        mock_callbacks: MockCallableGroup,
        mocked_outside_temperature: float,
    ) -> None:
        """
        Test reading the outsideTemperature from the FieldStation.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param mock_callbacks: mock callables.
        :param mocked_outside_temperature: the mocked value for outsideTemperature.
        """
        # Before communication has been started the outsideTemperature should
        # report None
        assert field_station_component_manager.outsideTemperature is None

        field_station_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
        )
        # Lookahead needs to take into account smartbox callbacks
        mock_callbacks["component_state"].assert_call(
            outsidetemperature=mocked_outside_temperature, lookahead=50
        )
        assert (
            field_station_component_manager.outsideTemperature
            == mocked_outside_temperature
        )

    def test_communication(
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the start_communicating command.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param mock_callbacks: mock callables.
        """
        field_station_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
        )

        field_station_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.DISABLED
        )

    @patch(
        "ska_low_mccs_pasd.field_station."
        "field_station_component_manager.MccsCommandProxy"
    )
    @pytest.mark.parametrize(
        (
            "antenna_id",
            "component_manager_command",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            (
                "sb18-01",
                "power_on_antenna",
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    (ResultCode.OK, "power on antenna sb18-01 success."),
                ),
            ),
            (
                "sb18-01",
                "power_off_antenna",
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    (ResultCode.OK, "power off antenna sb18-01 success."),
                ),
            ),
        ],
    )
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_antenna_power_commands(
        self: TestFieldStationComponentManager,
        mock_command_cls: unittest.mock.Mock,
        field_station_component_manager: FieldStationComponentManager,
        antenna_id: str,
        component_manager_command: str,
        expected_manager_result: tuple[TaskStatus, str],
        command_tracked_result: tuple[TaskStatus, str],
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the antenna power on command.

        :param mock_command_cls: a patched MccsCommandProxy
            class for to assert against.
        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param antenna_id: antenna number under test.
        :param component_manager_command: command to call on the component manager.
        :param expected_manager_result: expected response from the call
        :param command_tracked_result: The result of the command.
        :param mock_callbacks: mock callables.
        """
        # Mock composite command
        mock_composite = MagicMock()
        mock_command_cls.return_value = mock_composite
        mock_composite.__iadd__.return_value = mock_composite

        # Mock result of calling the composite command
        mock_composite.return_value = (ResultCode.OK, "Success")

        field_station_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        assert (
            getattr(field_station_component_manager, component_manager_command)(
                antenna_id, mock_callbacks["task"]
            )
            == expected_manager_result
        )
        time.sleep(0.2)

        def _snake_to_pascal_case(snake_string: str) -> str:
            return "".join(word.capitalize() for word in snake_string.split("_"))

        mock_command_cls.assert_has_calls(
            [
                call(
                    device_name=ANY,
                    command_name=_snake_to_pascal_case(component_manager_command),
                    logger=ANY,
                ),
                call()(arg=antenna_id, is_lrc=True, wait_for_result=True),
            ]
        )
        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        if command_tracked_result[0] == TaskStatus.COMPLETED:
            mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)

    @patch(
        "ska_low_mccs_pasd.field_station."
        "field_station_component_manager.MccsCompositeCommandProxy"
    )
    @patch(
        "ska_low_mccs_pasd.field_station."
        "field_station_component_manager.MccsCommandProxy"
    )
    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "command_tracked_result",
        ),
        [
            pytest.param(
                "on",
                (
                    TaskStatus.COMPLETED,
                    (
                        ResultCode.OK,
                        "All unmasked antennas turned on.",
                    ),
                ),
                id="On",
            ),
            pytest.param(
                "off",
                (
                    TaskStatus.COMPLETED,
                    (
                        ResultCode.OK,
                        "All FNDH ports turned off. All Smartbox ports turned off.",
                    ),
                ),
                id="Off",
            ),
        ],
    )
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def test_on_off_commands(
        self: TestFieldStationComponentManager,
        mock_command_cls: unittest.mock.Mock,
        mock_composite_cls: unittest.mock.Mock,
        field_station_component_manager: FieldStationComponentManager,
        component_manager_command: Any,
        command_tracked_result: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the FieldStation object commands.

        :param mock_command_cls: a patched MccsCommandProxy
            class for to assert against.
        :param mock_composite_cls: a patched MccsCompositeCommandProxy
            class for to assert against.
        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param command_tracked_result: The result of the command.
        :param mock_callbacks: mock callables.
        """
        # Mock composite command
        mock_composite = MagicMock()
        mock_command = MagicMock()
        mock_composite_cls.return_value = mock_composite
        mock_command_cls.return_value = mock_command
        mock_composite.__iadd__.return_value = mock_composite

        # Mock result of calling the composite command
        mock_composite.return_value = (ResultCode.OK, "Success")
        mock_command.return_value = (ResultCode.OK, "Success")

        field_station_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        getattr(field_station_component_manager, str("_" + component_manager_command))(
            mock_callbacks["task"],
        )

        expected_state = (
            PowerState.ON if component_manager_command == "on" else PowerState.OFF
        )

        # We only expect to see smartbox commands called when we are turning ON
        if expected_state == PowerState.ON:
            mock_command.assert_called_once_with(
                timeout=FieldStationComponentManager.FIELDSTATION_ON_COMMAND_TIMEOUT,
                is_lrc=True,
                wait_for_result=True,
            )

            expected_calls = [
                call(
                    device_name=field_station_component_manager._fndh_name,
                    command_name="On",
                    logger=ANY,
                ),
            ]

            for smartbox in field_station_component_manager._smartbox_proxys.values():
                expected_calls.append(
                    call(
                        device_name=smartbox._name,
                        command_name="On",
                        logger=ANY,
                    )
                )

            mock_command_cls.assert_has_calls(expected_calls, any_order=True)
        else:
            mock_command_cls.assert_called_once_with(
                device_name=field_station_component_manager._fndh_name,
                command_name="Standby",
                logger=ANY,
            )
            mock_command.assert_called_once_with(
                timeout=FieldStationComponentManager.FIELDSTATION_ON_COMMAND_TIMEOUT,
                is_lrc=True,
                wait_for_result=True,
            )
