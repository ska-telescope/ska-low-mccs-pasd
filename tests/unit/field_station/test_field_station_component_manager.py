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
import unittest.mock
from typing import Any, Iterator

import pytest
import tango
from ska_control_model import CommunicationStatus, PowerState, ResultCode, TaskStatus
from ska_low_mccs_common.testing.mock import MockDeviceBuilder
from ska_tango_testing.mock import MockCallableGroup
from ska_tango_testing.mock.placeholders import Anything

from ska_low_mccs_pasd.field_station import FieldStationComponentManager
from ska_low_mccs_pasd.pasd_data import PasdData
from tests.harness import (
    PasdTangoTestHarness,
    PasdTangoTestHarnessContext,
    get_fndh_name,
    get_smartbox_name,
)

# pylint: disable=too-many-lines


@pytest.fixture(name="on_antenna_number")
def on_antenna_number_fixture() -> int:
    """
    Return a fixture for the number of an antenna which is on.

    :returns: a fixture for the number of an antenna which is on.
    """
    return 123


@pytest.fixture(name="on_smartbox_id")
def on_smartbox_id_fixture(
    on_antenna_number: int, mock_antenna_mapping: dict[int, list]
) -> int:
    """
    Return the id of a smartbox which is on.

    :param on_antenna_number: the number of an antenna which is on.
    :param mock_antenna_mapping: a default set of antenna mappings for testing.

    :returns: the id of a smartbox which is on.
    """
    smartbox_id, smartbox_port = mock_antenna_mapping[on_antenna_number]
    return smartbox_id


@pytest.fixture(name="on_smartbox_port")
def on_smartbox_port_fixture(
    on_antenna_number: int, mock_antenna_mapping: dict[int, list]
) -> int:
    """
    Return the port of a smartbox which is on.

    :param on_antenna_number: the number of an antenna which is on.
    :param mock_antenna_mapping: a default set of antenna mappings for testing.

    :returns: the port of a smartbox which is on.
    """
    smartbox_id, smartbox_port = mock_antenna_mapping[on_antenna_number]
    return smartbox_port


@pytest.fixture(name="on_fndh_port")
def on_fndh_port_fixture(
    on_smartbox_id: int, mock_smartbox_mapping: dict[int, int]
) -> int:
    """
    Return a FNDH port which is on.

    :param on_smartbox_id: the id of a smartbox which is on.
    :param mock_smartbox_mapping: a default set of fndh port mappings.

    :returns: a FNDH port which is on.
    """
    return mock_smartbox_mapping[on_smartbox_id]


def _input_antenna_mask() -> dict:
    antenna_mask: list[dict] = [{} for _ in range(PasdData.NUMBER_OF_ANTENNAS)]
    for antenna_no in range(PasdData.NUMBER_OF_ANTENNAS):
        antenna_mask[antenna_no]["antennaID"] = antenna_no + 1
        antenna_mask[antenna_no]["maskingState"] = False
    # Mask the first 12 antennas
    for antenna_no in range(PasdData.NUMBER_OF_SMARTBOX_PORTS):
        antenna_mask[antenna_no]["maskingState"] = True
    # The 94th element in this list will have antennaID = 95
    antenna_mask[94]["maskingState"] = True
    return {"antennaMask": antenna_mask}


def _output_antenna_mask() -> list:
    antenna_mask: list = [False for _ in range(PasdData.NUMBER_OF_ANTENNAS + 1)]
    for antenna_id in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
        antenna_mask[antenna_id] = True
    antenna_mask[95] = True
    return antenna_mask


def _input_antenna_mapping() -> dict:
    antenna_mapping: list[dict] = [{} for _ in range(PasdData.NUMBER_OF_ANTENNAS)]
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
            try:
                antenna_no = (
                    smartbox_no - 1
                ) * PasdData.NUMBER_OF_SMARTBOX_PORTS + smartbox_port
                antenna_mapping[antenna_no - 1]["antennaID"] = antenna_no
                antenna_mapping[antenna_no - 1]["smartboxID"] = smartbox_no
                antenna_mapping[antenna_no - 1]["smartboxPort"] = smartbox_port
            except IndexError:
                break

    # Swap two antennas
    antenna_mapping[0]["antennaID"] = 1
    antenna_mapping[0]["smartboxID"] = 1
    antenna_mapping[0]["smartboxPort"] = 2

    antenna_mapping[1]["antennaID"] = 2
    antenna_mapping[1]["smartboxID"] = 1
    antenna_mapping[1]["smartboxPort"] = 1

    return {"antennaMapping": antenna_mapping}


def _output_antenna_mapping() -> dict:
    antenna_mapping: dict[str, list] = {
        str(antenna_id): [0, 0]
        for antenna_id in range(1, PasdData.NUMBER_OF_ANTENNAS + 1)
    }
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
            try:
                antenna_no = (
                    smartbox_no - 1
                ) * PasdData.NUMBER_OF_SMARTBOX_PORTS + smartbox_port
                if str(antenna_no) in antenna_mapping.keys():
                    antenna_mapping[str(antenna_no)] = [smartbox_no, smartbox_port]
            except KeyError:
                break

    # Swap two antennas
    antenna_mapping["1"] = [1, 2]
    antenna_mapping["2"] = [1, 1]

    return antenna_mapping


def _input_smartbox_mapping() -> dict:
    smartbox_mapping: list[dict] = [
        {} for _ in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
    ]
    for fndh_port in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION):
        smartbox_mapping[fndh_port]["fndhPort"] = fndh_port + 1
        smartbox_mapping[fndh_port]["smartboxID"] = fndh_port + 1

    # Swap two smartboxes
    smartbox_mapping[0]["fndhPort"] = 1
    smartbox_mapping[0]["smartboxID"] = 2

    smartbox_mapping[1]["fndhPort"] = 2
    smartbox_mapping[1]["smartboxID"] = 1

    return {"smartboxMapping": smartbox_mapping}


def _output_smartbox_mapping() -> dict:
    smartbox_mapping: dict = {
        str(fndh_port): fndh_port
        for fndh_port in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1)
    }

    # Swap two smartboxes
    smartbox_mapping["1"] = 2
    smartbox_mapping["2"] = 1
    return smartbox_mapping


@pytest.fixture(name="mock_smartboxes")
def mock_smartboxes_fixture(
    on_smartbox_id: int, on_smartbox_port: int
) -> list[unittest.mock.Mock]:
    """
    Fixture that provides a mock MccsSmartBox device.

    :param on_smartbox_id: the id of a smartbox which is on.
    :param on_smartbox_port: the port of a smartbox which is on.

    :return: a mock MccsSmartBox device.
    """
    smartboxes = []
    for i in range(1, 25):
        builder = MockDeviceBuilder()
        builder.set_state(tango.DevState.ON)
        builder.add_result_command("PowerOnPort", ResultCode.OK)
        builder.add_result_command("PowerOffPort", ResultCode.OK)
        builder.add_result_command("SetPortPowers", ResultCode.QUEUED)
        port_powers = [False for _ in range(12)]
        if i == on_smartbox_id:
            port_powers[on_smartbox_port - 1] = True
        builder.add_attribute("PortsPowerSensed", port_powers)
        builder.add_attribute("fndhPort", json.dumps(i))
        builder.add_command("dev_name", f"low-mccs/smartbox/ci-1-sb{i:02d}")
        builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
        smartboxes.append(builder())
    return smartboxes


@pytest.fixture(name="mock_fndh")
def mock_fndh_fixture(
    mocked_outside_temperature: float, on_fndh_port: int
) -> unittest.mock.Mock:
    """
    Fixture that provides a mock MccsFndh device.

    :param mocked_outside_temperature: the mocked outside temperature.
    :param on_fndh_port: an fndh port which is powered on.

    :return: a mock MccsFndh device.
    """
    builder = MockDeviceBuilder()
    builder.set_state(tango.DevState.ON)
    builder.add_result_command("PowerOnPort", ResultCode.OK)
    builder.add_result_command("PowerOffPort", ResultCode.OK)
    builder.add_result_command("SetPortPowers", ResultCode.QUEUED)
    builder.add_attribute("OutsideTemperature", mocked_outside_temperature)
    port_powers = [False for _ in range(28)]
    port_powers[on_fndh_port - 1] = True
    builder.add_attribute("PortsPowerSensed", port_powers)
    builder.add_command("dev_name", "low-mccs/fndh/ci-1")
    builder.add_result_command("SetFndhPortPowers", ResultCode.OK)
    return builder()


@pytest.fixture(name="test_context")
def test_context_fixture(
    mock_fndh: unittest.mock.Mock,
    mock_smartboxes: list[unittest.mock.Mock],
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Create a test context containing a single mock PaSD bus device.

    :param mock_fndh: A mock FNDH device.
    :param mock_smartboxes: A list of mock Smartbox devices.

    :yield: the test context
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_fndh_device(mock_fndh)
    for smartbox_id in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        harness.set_mock_smartbox_device(mock_smartboxes[smartbox_id - 1], smartbox_id)
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
        smartbox_no * PasdData.NUMBER_OF_SMARTBOX_PORTS
        + smartbox_port
        + 1: [smartbox_no + 1, smartbox_port + 1]
        for smartbox_no in range(0, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
        for smartbox_port in range(0, PasdData.NUMBER_OF_SMARTBOX_PORTS)
        if smartbox_no * PasdData.NUMBER_OF_SMARTBOX_PORTS + smartbox_port + 1 < 257
        # For sanity's sake we assign all ports antennas, this is not realistic
        # however the calls on the smartboxes become complex to predict, and these
        # unit tests are already quite complex.
        # if smartbox_no * NUMBER_OF_SMARTBOX_PORTS + smartbox_port < 256
    }


@pytest.fixture(name="mock_smartbox_mapping")
def mock_smartbox_mapping_fixture() -> dict[int, int]:
    """
    Generate a default set of fndh port mappings.

    It is assumed smartbox id is the same as FNDH port no.

    :returns: a default set of fndh port mappings
    """
    return {
        port: port
        for port in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1)
    }


@pytest.fixture(name="simulated_configuration")
def simulated_configuration_fixture(mock_antenna_mapping: Any) -> dict[Any, Any]:
    """
     Return a configuration for the fieldstation.

    :param mock_antenna_mapping: a default set of antenna mappings for testing.

     :return: a configuration for representing the antenna port mapping information.
    """
    antennas = {}
    smartboxes = {}

    for antenna_id, config in mock_antenna_mapping.items():
        antennas[str(antenna_id)] = {
            "smartbox": str(config[0]),
            "smartbox_port": config[1],
            "masked": False,
        }

    for i in range(1, 25):
        smartboxes[str(i)] = {"fndh_port": i}

    configuration = {
        "antennas": antennas,
        "pasd": {"smartboxes": smartboxes},
    }
    return configuration


@pytest.fixture(name="configuration_manager")
def configuration_manager_fixture(
    simulated_configuration: dict[Any, Any]
) -> unittest.mock.Mock:
    """
    Return a mock configuration_manager.

    :param simulated_configuration: a fixture containing the
        simulated configuration.

    :return: a mock configuration_manager.
    """
    manager = unittest.mock.Mock()
    manager.connect = unittest.mock.Mock(return_value=True)
    manager.read_data = unittest.mock.Mock(return_value=simulated_configuration)
    return manager


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
        configuration_manager: Any,
        mock_smartboxes: Any,
        mock_fndh: Any,
    ) -> FieldStationComponentManager:
        """
        Return an FieldStation component manager.

        :param test_context: a test context containing the Tango devices.
        :param logger: a logger for this command to use.
        :param mock_callbacks: mock callables.
        :param mock_antenna_mask: a default set of maskings for testing, all unmasked.
        :param mock_antenna_mapping: a default set of antenna mappings for testing.
        :param mock_smartbox_mapping: a default set of fndh port mappings
        :param configuration_manager: a mock configuration manager to manage a
            configuration for the field station
        :param mock_smartboxes: A list of mock Smartbox devices.
        :param mock_fndh: A mock FNDH device.

        :return: an FieldStation component manager.
        """
        harness = PasdTangoTestHarness()
        harness.set_mock_fndh_device(mock_fndh)
        for smartbox_id in range(1, 25):
            harness.set_mock_smartbox_device(
                mock_smartboxes[smartbox_id - 1], smartbox_id
            )
        harness.set_configuration_server(configuration_manager)
        with harness as context:
            (host, port) = context.get_pasd_configuration_server_address()

        return FieldStationComponentManager(
            logger,
            host,
            port,
            2,
            "ci-1",
            get_fndh_name(),
            [
                get_smartbox_name(smartbox_id)
                for smartbox_id in range(
                    1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1
                )
            ],
            [],
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            mock_callbacks["configuration_change_callback"],
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
        mock_callbacks["communication_state"].assert_not_called()
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
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
        mock_callbacks["communication_state"].assert_not_called()
        assert (
            field_station_component_manager.communication_state
            == CommunicationStatus.ESTABLISHED
        )
        # two smartboxes have no antenna attached. Therefore a update in the
        # the port powers has no antenna callback.
        for i in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION):
            mock_callbacks["component_state"].assert_call(
                antenna_powers=Anything, lookahead=30
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
            "antenna_no",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            (
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
                256,
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (TaskStatus.COMPLETED, "turn on antenna 256 success."),
            ),
        ],
    )
    def test_antenna_power_on(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        antenna_no: int,
        antenna_masking_state: bool,
        expected_manager_result: tuple[TaskStatus, str],
        command_tracked_result: tuple[TaskStatus, str],
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the antenna power on command.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param antenna_no: antenna number under test.
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
            antenna_no
        ] = antenna_masking_state
        assert field_station_component_manager._antenna_mapping_pretty is not None
        smartbox_id = field_station_component_manager._antenna_mapping_pretty[
            "antennaMapping"
        ][antenna_no - 1]["smartboxID"]
        smartbox_port = field_station_component_manager._antenna_mapping_pretty[
            "antennaMapping"
        ][antenna_no - 1]["smartboxPort"]

        fndh_port = field_station_component_manager._smartbox_mapping[str(smartbox_id)]

        assert (
            field_station_component_manager.turn_on_antenna(
                antenna_no, mock_callbacks["task"]
            )
            == expected_manager_result
        )

        if antenna_masking_state is False:
            assert field_station_component_manager._fndh_proxy._proxy is not None
            fndh_proxy_command = (
                field_station_component_manager._fndh_proxy._proxy.PowerOnPort
            )

            smartbox_proxy = field_station_component_manager._smartbox_proxys[
                int(smartbox_id) - 1
            ]

            assert smartbox_proxy._proxy is not None
            smartbox_proxy_command = smartbox_proxy._proxy.PowerOnPort

            fndh_proxy_command.assert_next_call(int(fndh_port))
            smartbox_proxy_command.assert_next_call(int(smartbox_port))

        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        if command_tracked_result[0] == TaskStatus.COMPLETED:
            mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=command_tracked_result[0], result=command_tracked_result[1]
        )

    @pytest.mark.parametrize(
        (
            "antenna_no",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            (
                1,
                True,  # antenna is masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    "Antenna number 1 is masked, call with ignore_mask=True to ignore",
                ),
            ),
            (
                123,
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (TaskStatus.COMPLETED, "turn off antenna 123 success."),
            ),
            (
                255,
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Tried to turn off antenna 255, this is mapped to smartbox 22, "
                        "which is on fndh port 22. However this port is "
                        "not powered on."
                    ),
                ),
            ),
        ],
    )
    def test_antenna_power_off(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        antenna_no: int,
        antenna_masking_state: bool,
        expected_manager_result: tuple[TaskStatus, str],
        command_tracked_result: tuple[TaskStatus, str],
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the antenna power off command.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param antenna_no: antenna number under test.
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
            antenna_no
        ] = antenna_masking_state
        assert field_station_component_manager._antenna_mapping_pretty is not None
        smartbox_id = field_station_component_manager._antenna_mapping_pretty[
            "antennaMapping"
        ][antenna_no - 1]["smartboxID"]
        smartbox_port = field_station_component_manager._antenna_mapping_pretty[
            "antennaMapping"
        ][antenna_no - 1]["smartboxPort"]

        assert (
            field_station_component_manager.turn_off_antenna(
                antenna_no, mock_callbacks["task"]
            )
            == expected_manager_result
        )

        if command_tracked_result == TaskStatus.COMPLETED:
            assert field_station_component_manager._fndh_proxy._proxy is not None
            fndh_proxy_command = (
                field_station_component_manager._fndh_proxy._proxy.PowerOffPort
            )

            smartbox_proxy = field_station_component_manager._smartbox_proxys[
                int(smartbox_id) - 1
            ]

            assert smartbox_proxy._proxy is not None
            smartbox_proxy_command = smartbox_proxy._proxy.PowerOffPort

            fndh_proxy_command.assert_not_called()
            smartbox_proxy_command.assert_next_call(smartbox_port)

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
                "SetPortPowers",
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
                "SetPortPowers",
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
                "SetPortPowers",
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
                "SetPortPowers",
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
                "SetPortPowers",
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
                "SetPortPowers",
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
    def test_on_off_commands(  # noqa: C901
        # pylint: disable=too-many-arguments, too-many-locals, too-many-branches
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
        assert field_station_component_manager._antenna_mapping_pretty is not None
        # If we are working with a specific antenna, rather than all antennas,
        # get the smartbox_id and smartbox_port that the antenna is connected to.
        if antenna_no > 0:
            smartbox_id = field_station_component_manager._antenna_mapping_pretty[
                "antennaMapping"
            ][antenna_no - 1]["smartboxID"]
            smartbox_port = field_station_component_manager._antenna_mapping_pretty[
                "antennaMapping"
            ][antenna_no - 1]["smartboxPort"]
        else:
            # If working with all antennas, no specific smartbox will get a call with a
            # masked port
            smartbox_id = 0
            smartbox_port = 0

        expected_state = component_manager_command == "on"

        desired_fndh_port_powers: list[bool | None] = [
            expected_state
        ] * PasdData.NUMBER_OF_FNDH_PORTS

        # There are 4 surplus ports plus 2 smartbox have no antenna.
        for unused_fndh_port in range(22, 28):
            desired_fndh_port_powers[unused_fndh_port] = None

        fndh_json_arg = json.dumps(
            {
                "port_powers": desired_fndh_port_powers,
                "stay_on_when_offline": True,
            }
        )

        # If we are not working with a fully masked station.
        if antenna_no != 0 or not antenna_masking_state:
            fndh_proxy_command = getattr(
                field_station_component_manager._fndh_proxy._proxy, proxy_command
            )
            fndh_proxy_command.assert_next_call(fndh_json_arg)

            # Mock a change event in the power of fndh ports
            field_station_component_manager._on_fndh_port_change(
                "portspowersensed",
                desired_fndh_port_powers,
                tango.AttrQuality.ATTR_VALID,
            )
            for smartbox_proxy in field_station_component_manager._smartbox_proxys:
                smartbox_name = smartbox_proxy._name

                smartbox_no = (
                    field_station_component_manager._smartbox_name_number_map[
                        smartbox_name
                    ]
                    + 1
                )
                fndh_port = field_station_component_manager._smartbox_mapping[
                    str(smartbox_no)
                ]
                if desired_fndh_port_powers[fndh_port - 1]:
                    mocked_smartbox_power = PowerState.ON
                else:
                    mocked_smartbox_power = PowerState.OFF

                field_station_component_manager.smartbox_state_change(
                    smartbox_name, power=mocked_smartbox_power
                )

                smartbox_mask_map = (
                    field_station_component_manager._get_masked_smartbox_ports()
                )
                ports_to_change = [expected_state] * 12
                for smartbox_identity, masked_ports in smartbox_mask_map.items():
                    if smartbox_no == smartbox_identity:
                        for masked_port in masked_ports:
                            ports_to_change[masked_port - 1] = None
                field_station_component_manager._on_port_power_change(
                    smartbox_name,
                    "portspowersensed",
                    ports_to_change,
                    tango.AttrQuality.ATTR_VALID,
                )

            for smartbox_no, smartbox in enumerate(
                field_station_component_manager._smartbox_proxys
            ):
                smartbox_proxy_command = getattr(smartbox._proxy, proxy_command)

                desired_smartbox_port_powers: list[bool | None] = [
                    expected_state
                ] * PasdData.NUMBER_OF_SMARTBOX_PORTS

                if smartbox_no == 21:
                    # The last smartbox only has 4 antenna
                    desired_smartbox_port_powers = [expected_state] * 4 + [None] * 8
                if smartbox_no > 21:
                    # The configuration did not put any antenna on the
                    # last 2 smartbox
                    desired_smartbox_port_powers = [
                        None
                    ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
                if smartbox_no == smartbox_id - 1:
                    desired_smartbox_port_powers[smartbox_port - 1] = None

                smartbox_json_arg = json.dumps(
                    {
                        "port_powers": desired_smartbox_port_powers,
                        "stay_on_when_offline": True,
                    }
                )

                smartbox_proxy_command.assert_next_call(smartbox_json_arg)

        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        if command_tracked_result[0] in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(
            status=command_tracked_result[0], result=command_tracked_result[1]
        )

    @pytest.mark.parametrize(
        (
            "component_manager_command",
            "component_manager_argument",
            "component_manager_attribute",
            "expected_config_output",
            "expected_manager_result",
        ),
        [
            pytest.param(
                "update_antenna_mask",
                _input_antenna_mask(),
                "_antenna_mask",
                _output_antenna_mask(),
                (TaskStatus.QUEUED, "Task queued"),
                id="Manually update antenna mask",
            ),
            pytest.param(
                "update_antenna_mapping",
                _input_antenna_mapping(),
                "_antenna_mapping",
                _output_antenna_mapping(),
                (TaskStatus.QUEUED, "Task queued"),
                id="Manually update antenna mapping",
            ),
            pytest.param(
                "update_smartbox_mapping",
                _input_smartbox_mapping(),
                "_smartbox_mapping",
                _output_smartbox_mapping(),
                (TaskStatus.QUEUED, "Task queued"),
                id="Manually update smartbox mapping",
            ),
        ],
    )
    def test_manual_config_commands(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        component_manager_command: Any,
        component_manager_argument: Any,
        component_manager_attribute: Any,
        expected_config_output: Any,
        expected_manager_result: Any,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the FieldStation manual config update commands.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param component_manager_command: command to issue to the component manager
        :param component_manager_argument: configuration to pass to configuration
            function.
        :param component_manager_attribute: configuration attribute to read from.
        :param expected_config_output: expected attribute result after config.
        :param expected_manager_result: expected response from the call
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
            getattr(field_station_component_manager, component_manager_command)(
                mock_callbacks["task"],
                **component_manager_argument,
            )
            == expected_manager_result
        )

        mock_callbacks["task"].assert_call(status=TaskStatus.QUEUED)
        mock_callbacks["task"].assert_call(status=TaskStatus.IN_PROGRESS)
        mock_callbacks["task"].assert_call(status=TaskStatus.COMPLETED)

        assert (
            getattr(field_station_component_manager, component_manager_attribute)
            == expected_config_output
        )
