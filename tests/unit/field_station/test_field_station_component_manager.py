# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the field_station component manager."""
from __future__ import annotations

import logging
import unittest.mock
from typing import Any, Iterator

import pytest
import tango
from ska_control_model import CommunicationStatus, ResultCode, TaskStatus
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.mock import MockCallableGroup

from ska_low_mccs_pasd.field_station import FieldStationComponentManager
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_fndh_name,
    get_smartbox_name,
)

SMARTBOX_NUMBER = 24
SMARTBOX_PORTS = 12


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFndh device.

    :return: a mock MccsFndh device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_result_command("PowerOnPort", ResultCode.OK)
    builder.add_result_command("PowerOnAllPorts", ResultCode.OK)
    builder.add_result_command("PowerOffAllPorts", ResultCode.OK)
    builder.add_command("PortPowerState", False)
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    return builder()


@pytest.fixture(name="mock_smartbox")
def mock_smartbox_fixture() -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsSmartBox device.

    :return: a mock MccsSmartBox device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_result_command("PowerOnPort", ResultCode.OK)
    builder.add_result_command("PowerOnAllPorts", ResultCode.OK)
    builder.add_result_command("PowerOffAllPorts", ResultCode.OK)
    builder.add_attribute("PortsPowerSensed", [False for _ in range(256)])
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    return builder()


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_fndh: unittest.mock.Mock,
    mock_smartbox: unittest.mock.Mock,
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing a single mock PaSD bus device.

    :param mock_fndh: A mock FNDH device.
    :param mock_smartbox: A mock Smartbox device.

    :yield: the test context
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_fndh_device(mock_fndh)
    for smartbox_id in range(1, SMARTBOX_NUMBER + 1):
        harness.set_mock_smartbox_device(mock_smartbox, smartbox_id)
    with harness as context:
        yield context


@pytest.fixture(name="mock_antenna_mask")
def mock_antenna_mask_fixture() -> list[bool]:
    """
    Generate a default set of maskings for testing, all unmasked.

    :returns: a default set of maskings for testing, all unmasked.
    """
    return [False for _ in range(256 + 1)]


@pytest.fixture(name="mock_antenna_mapping")
def mock_antenna_mapping_fixture() -> dict[int, list]:
    """
    Generate a default set of antenna mappings for testing.

    Antennas are assigned in ascending order of smartbox port and smartbox id.

    :returns: a default set of antenna mappings for testing.
    """
    return {
        smartbox_no * SMARTBOX_PORTS
        + smartbox_port
        + 1: [smartbox_no + 1, smartbox_port + 1]
        for smartbox_no in range(0, SMARTBOX_NUMBER)
        for smartbox_port in range(0, SMARTBOX_PORTS)
        if smartbox_no * SMARTBOX_PORTS + smartbox_port < 256
    }


@pytest.fixture(name="mock_smartbox_mapping")
def mock_smartbox_mapping_fixture() -> dict[int, int]:
    """
    Generate a default set of fndh port mappings.

    It is assumed smartbox id is the same as FNDH port no.

    :returns: a default set of fndh port mappings
    """
    return {port: port for port in range(1, SMARTBOX_NUMBER + 1)}


class TestFieldStationComponentManager:
    """Tests of the FieldStation component manager."""

    @pytest.fixture(name="field_station_component_manager")
    def field_station_component_manager_fixture(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        test_context: str,
        logger: logging.Logger,
        mock_callbacks: MockCallableGroup,
        mock_antenna_mask: list[bool],
        mock_antenna_mapping: dict[int, list],
        mock_smartbox_mapping: dict[int, int],
    ) -> FieldStationComponentManager:
        """
        Return an FieldStation component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param mock_callbacks: mock callables.
        :param mock_antenna_mask: a default set of maskings for testing, all unmasked.
        :param mock_antenna_mapping: a default set of antenna mappings for testing.
        :param mock_smartbox_mapping: a default set of fndh port mappings

        :return: an FieldStation component manager.
        """
        return FieldStationComponentManager(
            logger,
            get_fndh_name(),
            [
                get_smartbox_name(smartbox_id)
                for smartbox_id in range(1, SMARTBOX_NUMBER + 1)
            ],
            mock_antenna_mask,
            mock_antenna_mapping,
            mock_smartbox_mapping,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
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
        mock_callbacks["communication_state"].assert_not_called()
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
        )

        # check that the communication state goes to DISABLED after stop communication.
        field_station_component_manager.stop_communicating()
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.DISABLED, lookahead=10
        )
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.DISABLED
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_command_argument",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            (
                "turn_on_antenna",
                255,
                True,  # antenna is masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Antenna number 255 is masked, call with"
                        " ignore_mask=True to ignore"
                    ),
                ),
            ),
            (
                "turn_on_antenna",
                256,
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (TaskStatus.COMPLETED, "turn on antenna 256 success."),
            ),
            (
                "turn_off_antenna",
                1,
                True,  # antenna is masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    "Antenna number 1 is masked, call with ignore_mask=True to ignore",
                ),
            ),
            (
                "turn_off_antenna",
                255,
                True,  # antenna is masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Antenna number 255 is masked, call with "
                        "ignore_mask=True to ignore"
                    ),
                ),
            ),
        ],
    )
    def test_antenna_power_commands(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        component_manager_command: Any,
        component_manager_command_argument: Any,
        antenna_masking_state: bool,
        expected_manager_result: Any,
        command_tracked_result: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the FieldStation object commands.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param component_manager_command_argument: argument to call on component manager
        :param antenna_masking_state: whether the antenna is masked.
        :param expected_manager_result: expected response from the call
        :param command_tracked_result: The result of the command.
        :param mock_callbacks: mock callables.
        """
        field_station_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        field_station_component_manager._antenna_mask[
            component_manager_command_argument
        ] = antenna_masking_state

        assert (
            getattr(field_station_component_manager, component_manager_command)(
                component_manager_command_argument,
                mock_callbacks["task"],
            )
            == expected_manager_result
        )
        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        if command_tracked_result[0] == TaskStatus.COMPLETED:
            mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=command_tracked_result[0], result=command_tracked_result[1]
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "proxy_command",
            "antenna_no",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            pytest.param(
                "on",
                "PowerOnAllPorts",
                0,  # 0 for all antennas
                False,  # antenna(s) are not masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "All unmasked antennas turned on.",
                ),
                id="Turn on all antennas when all unmasked",
            ),
            pytest.param(
                "on",
                "PowerOnAllPorts",
                0,  # 0 for all antennas
                True,  # antenna(s) are masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Antennas in this station are masked, call with"
                        " ignore_mask=True to ignore"
                    ),
                ),
                id="Try to turn on all antennas when they are all masked",
            ),
            pytest.param(
                "on",
                "PowerOnAllPorts",
                123,
                True,  # antenna(s) are masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "All unmasked antennas turned on.",
                ),
                id="Turn on all antennas when one masked",
            ),
            pytest.param(
                "off",
                "PowerOffAllPorts",
                0,  # 0 for all antennas
                False,  # antenna(s) are not masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "All unmasked antennas turned off.",
                ),
                id="Turn off all antennas when all unmasked",
            ),
            pytest.param(
                "off",
                "PowerOffAllPorts",
                0,  # 0 for all antennas
                True,  # antenna(s) are masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Antennas in this station are masked, call with"
                        " ignore_mask=True to ignore"
                    ),
                ),
                id="Try to turn off all antennas when they are all masked",
            ),
            pytest.param(
                "off",
                "PowerOffAllPorts",
                123,
                True,  # antenna(s) are masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "All unmasked antennas turned off.",
                ),
                id="Turn off all antennas when one masked",
            ),
        ],
    )
    def test_on_off_commands(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        component_manager_command: Any,
        proxy_command: str,
        antenna_no: Any,
        antenna_masking_state: bool,
        expected_manager_result: Any,
        command_tracked_result: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the FieldStation object commands.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param proxy_command: command we expect to be called on the proxies.
        :param antenna_no: antenna to mask (if any).
        :param antenna_masking_state: masking state of antenna.
        :param expected_manager_result: expected response from the call
        :param command_tracked_result: The result of the command.
        :param mock_callbacks: mock callables.
        """
        field_station_component_manager.start_communicating()

        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks["communication_state"].assert_call(
            CommunicationStatus.ESTABLISHED
        )

        field_station_component_manager._antenna_mask[
            antenna_no
        ] = antenna_masking_state

        assert (
            getattr(field_station_component_manager, component_manager_command)(
                mock_callbacks["task"],
            )
            == expected_manager_result
        )

        # If we are working with a specific antenna, rather than all antennas,
        # get the smartbox_id and smartbox_port that the antenna is connected to.
        if antenna_no > 0:
            (
                smartbox_id,
                smartbox_port,
            ) = field_station_component_manager._antenna_mapping[antenna_no]
        else:
            # If working with all antennas, no specific smartbox will get a call with a
            # masked port
            smartbox_id = 0
            smartbox_port = 0

        # Here we check that for a given antenna, the mapped smartbox
        # power command is called with the correct port.

        # If we are not working with a fully masked station.
        if antenna_no != 0 or not antenna_masking_state:
            fndh_proxy_command = getattr(
                field_station_component_manager._fndh_proxy._proxy, proxy_command
            )
            fndh_proxy_command.assert_next_call([])
            for smartbox_no, smartbox in enumerate(
                field_station_component_manager._smartbox_proxys
            ):
                smartbox_proxy_command = getattr(smartbox._proxy, proxy_command)
                if smartbox_no == smartbox_id - 1:
                    smartbox_proxy_command.assert_next_call([smartbox_port])
                else:
                    smartbox_proxy_command.assert_next_call([])

        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        if command_tracked_result[0] in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=command_tracked_result[0], result=command_tracked_result[1]
        )
