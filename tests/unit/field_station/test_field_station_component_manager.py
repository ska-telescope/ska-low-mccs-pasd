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
def on_antenna_number_fixture() -> str:
    """
    Return a fixture for the number of an antenna which is on.

    :returns: a fixture for the number of an antenna which is on.
    """
    return "sb18-01"


@pytest.fixture(name="on_smartbox_id")
def on_smartbox_id_fixture(
    on_antenna_number: str, mock_antenna_mapping: dict[str, list]
) -> str:
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
    on_smartbox_id: str, mock_smartbox_mapping: dict[str, int]
) -> int:
    """
    Return a FNDH port which is on.

    :param on_smartbox_id: the id of a smartbox which is on.
    :param mock_smartbox_mapping: a default set of fndh port mappings.

    :returns: a FNDH port which is on.
    """
    return mock_smartbox_mapping[on_smartbox_id]


def _input_antenna_mask() -> dict:
    antenna_mask: dict = {}

    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
            antenna_mask[f"sb{smartbox_no:02d}-{smartbox_port:02d}"] = False
    # Mask the first 12 antennas
    # The 94th element in this list will have antennaID = 95
    antenna_mask["sb22-01"] = True
    return {"antennaMask": antenna_mask}


def _output_antenna_mask() -> dict:
    antenna_mask: dict = {}
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
            antenna_mask[f"sb{smartbox_no:02d}-{smartbox_port:02d}"] = False
    antenna_mask["sb22-01"] = True
    return {"antennaMask": antenna_mask}


def _input_antenna_mapping() -> dict:
    antenna_mapping: dict = {}
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION - 3):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
            antenna_id = f"sb{smartbox_no:02d}-{smartbox_port:02d}"
            antenna_mapping[antenna_id] = {}
            antenna_mapping[antenna_id]["smartboxID"] = smartbox_no
            antenna_mapping[antenna_id]["smartboxPort"] = smartbox_port

    # Swap two antennas
    tmp_antenna = antenna_mapping["sb01-01"]
    antenna_mapping["sb01-01"] = antenna_mapping["sb01-02"]
    antenna_mapping["sb01-02"] = tmp_antenna

    return {"antennaMapping": antenna_mapping}


def _output_antenna_mapping() -> dict:
    antenna_mapping: dict = {}
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION - 3):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1):
            antenna_id = f"sb{smartbox_no:02d}-{smartbox_port:02d}"
            antenna_mapping[antenna_id] = (smartbox_no, smartbox_port)

    antenna_mapping["sb21-01"] = (f"sb{21}", 1)
    antenna_mapping["sb21-02"] = (f"sb{21}", 2)
    antenna_mapping["sb21-03"] = (f"sb{21}", 3)
    # Swap two antennas
    tmp_antenna = antenna_mapping["sb01-01"]
    antenna_mapping["sb01-01"] = antenna_mapping["sb01-02"]
    antenna_mapping["sb01-02"] = tmp_antenna

    return {"antennaMapping": antenna_mapping}


def _input_smartbox_mapping() -> dict:
    smartbox_mapping = {}
    for fndh_port in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        smartbox_mapping[f"sb{fndh_port:02d}"] = fndh_port

    # Swap two smartboxes

    smartbox_mapping["sb01"] = 2
    smartbox_mapping["sb02"] = 1

    return {"smartboxMapping": smartbox_mapping}


def _output_smartbox_mapping() -> dict:
    smartbox_mapping: dict = {}
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        smartbox_name = f"sb{smartbox_no:02d}"
        smartbox_mapping[smartbox_name] = smartbox_no

    # Swap two smartboxes
    smartbox_mapping["sb01"] = 2
    smartbox_mapping["sb02"] = 1
    return {"smartboxMapping": smartbox_mapping}


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
    for i in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
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
def mock_antenna_mapping_fixture() -> dict[str, list]:
    """
    Generate a default set of antenna mappings for testing.

    Antennas are assigned in ascending order of smartbox port and smartbox id.

    :returns: a default set of antenna mappings for testing.
    """
    return {
        f"sb{smartbox_no:02d}-{smartbox_port:02d}": [
            f"sb{smartbox_no:02d}",
            smartbox_port,
        ]
        for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1)
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS + 1)
        if smartbox_no * PasdData.NUMBER_OF_SMARTBOX_PORTS + smartbox_port + 1 < 257
        # For sanity's sake we assign all ports antennas, this is not realistic
        # however the calls on the smartboxes become complex to predict, and these
        # unit tests are already quite complex.
        # if smartbox_no * NUMBER_OF_SMARTBOX_PORTS + smartbox_port < 256
    }


@pytest.fixture(name="mock_smartbox_mapping")
def mock_smartbox_mapping_fixture() -> dict[str, int]:
    """
    Generate a default set of fndh port mappings.

    It is assumed smartbox id is the same as FNDH port no.

    :returns: a default set of fndh port mappings
    """
    return {
        "sb" + str(port): port
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

    for i in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        smartboxes[f"sb{i:02d}"] = {"fndh_port": i, "modbus_id": i}

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
        mock_antenna_mapping: dict[str, list],
        mock_smartbox_mapping: dict[str, int],
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
        for smartbox_id in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
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
            "antenna_id",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            (
                "sb18-01",
                True,  # antenna is masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Antenna number sb18-01 is masked, call with"
                        " ignore_mask=True to ignore"
                    ),
                ),
            ),
            (
                "sb18-01",
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (TaskStatus.COMPLETED, "turn on antenna sb18-01 success."),
            ),
        ],
    )
    def test_antenna_power_on(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        antenna_id: str,
        antenna_masking_state: bool,
        expected_manager_result: tuple[TaskStatus, str],
        command_tracked_result: tuple[TaskStatus, str],
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the antenna power on command.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param antenna_id: antenna number under test.
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

        field_station_component_manager._antenna_mask["antennaMask"][
            antenna_id
        ] = antenna_masking_state
        assert field_station_component_manager._antenna_mapping is not None
        smartbox_id = field_station_component_manager._antenna_mapping[
            "antennaMapping"
        ][antenna_id][0]
        smartbox_port = field_station_component_manager._antenna_mapping[
            "antennaMapping"
        ][antenna_id][1]

        fndh_port = field_station_component_manager._smartbox_mapping[
            "smartboxMapping"
        ][smartbox_id]

        assert (
            field_station_component_manager.turn_on_antenna(
                antenna_id, mock_callbacks["task"]
            )
            == expected_manager_result
        )

        if antenna_masking_state is False:
            assert field_station_component_manager._fndh_proxy._proxy is not None
            fndh_proxy_command = (
                field_station_component_manager._fndh_proxy._proxy.PowerOnPort
            )

            smartbox_proxy = field_station_component_manager._smartbox_proxys[
                smartbox_id
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
            "antenna_id",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            (
                "sb18-01",
                True,  # antenna is masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    "Antenna number sb18-01 is masked, "
                    "call with ignore_mask=True to ignore",
                ),
            ),
            (
                "sb18-11",
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (TaskStatus.COMPLETED, "turn off antenna sb18-11 success."),
            ),
            (
                "sb10-12",
                False,  # antenna is not masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.REJECTED,
                    (
                        "Tried to turn off antenna sb10-12, this is mapped to "
                        "smartbox sb10, which is on fndh port 10."
                        " However this port is not powered on."
                    ),
                ),
            ),
        ],
    )
    def test_antenna_power_off(  # pylint: disable=too-many-arguments
        self: TestFieldStationComponentManager,
        field_station_component_manager: FieldStationComponentManager,
        antenna_id: str,
        antenna_masking_state: bool,
        expected_manager_result: tuple[TaskStatus, str],
        command_tracked_result: tuple[TaskStatus, str],
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the antenna power off command.

        :param field_station_component_manager: A FieldStation component manager
            with communication established.
        :param antenna_id: antenna number under test.
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

        field_station_component_manager._antenna_mask["antennaMask"][
            antenna_id
        ] = antenna_masking_state
        assert field_station_component_manager._antenna_mapping is not None
        smartbox_id = field_station_component_manager._antenna_mapping[
            "antennaMapping"
        ][antenna_id][0]
        smartbox_port = field_station_component_manager._antenna_mapping[
            "antennaMapping"
        ][antenna_id][1]

        assert (
            field_station_component_manager.turn_off_antenna(
                antenna_id, mock_callbacks["task"]
            )
            == expected_manager_result
        )

        if command_tracked_result[0] == TaskStatus.COMPLETED:
            assert field_station_component_manager._fndh_proxy._proxy is not None
            fndh_proxy_command = (
                field_station_component_manager._fndh_proxy._proxy.PowerOffPort
            )

            smartbox_proxy = field_station_component_manager._smartbox_proxys[
                smartbox_id
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
            "antenna_id",
            "antenna_masking_state",
            "expected_manager_result",
            "command_tracked_result",
        ),
        [
            pytest.param(
                "on",
                "sb18-11",
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
                0,
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
                "sb18-11",
                False,  # antenna(s) are masked
                (TaskStatus.QUEUED, "Task queued"),
                (
                    TaskStatus.COMPLETED,
                    "All unmasked antennas turned on.",
                ),
                id="Turn on all antennas when one masked",
            ),
            pytest.param(
                "off",
                0,
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
                0,
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
                "sb18-11",
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
        antenna_id: Any,
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
        :param antenna_id: antenna to mask (if any).
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

        if antenna_id == 0:
            field_station_component_manager._all_masked = True
        else:
            field_station_component_manager._antenna_mask["antennaMask"][
                antenna_id
            ] = antenna_masking_state

            # If working with all antennas, no specific smartbox will get a call with a
            # masked port

        assert (
            getattr(field_station_component_manager, component_manager_command)(
                mock_callbacks["task"],
            )
            == expected_manager_result
        )
        assert field_station_component_manager._antenna_mapping is not None
        # If we are working with a specific antenna, rather than all antennas,
        # get the smartbox_id and smartbox_port that the antenna is connected to.

        expected_state = component_manager_command == "on"

        desired_fndh_port_powers: list[bool | None] = [
            expected_state
        ] * PasdData.NUMBER_OF_FNDH_PORTS

        # There are 4 surplus ports plus 2 smartbox have no antenna.
        for unused_fndh_port in range(21, 28):
            desired_fndh_port_powers[unused_fndh_port] = None

        fndh_json_arg = json.dumps(
            {
                "port_powers": desired_fndh_port_powers,
                "stay_on_when_offline": True,
            }
        )

        # If we are not working with a fully masked station.
        if not antenna_masking_state:
            fndh_proxy_command = getattr(
                field_station_component_manager._fndh_proxy._proxy, "SetPortPowers"
            )
            fndh_proxy_command.assert_next_call(fndh_json_arg)

            # Mock a change event in the power of fndh ports
            field_station_component_manager._on_fndh_port_change(
                "portspowersensed",
                desired_fndh_port_powers,
                tango.AttrQuality.ATTR_VALID,
            )
            for (
                smartbox_name,
                smartbox_proxy,
            ) in field_station_component_manager._smartbox_proxys.items():
                fndh_port = field_station_component_manager._smartbox_mapping[
                    "smartboxMapping"
                ][smartbox_name]
                if desired_fndh_port_powers[fndh_port - 1]:
                    mocked_smartbox_power = PowerState.ON
                else:
                    mocked_smartbox_power = PowerState.OFF

                smartbox_trl = field_station_component_manager._smartbox_name_trl_map[
                    smartbox_name
                ]
                field_station_component_manager.smartbox_state_change(
                    smartbox_trl, power=mocked_smartbox_power
                )

                smartbox_mask_map = (
                    field_station_component_manager._get_masked_smartbox_ports()
                )
                ports_to_change = [expected_state] * 12
                for smartbox_identity, masked_ports in smartbox_mask_map.items():
                    if smartbox_name == smartbox_identity:
                        for masked_port in masked_ports:
                            ports_to_change[masked_port - 1] = None
                field_station_component_manager._on_port_power_change(
                    smartbox_proxy._name,
                    "portspowersensed",
                    ports_to_change,
                    tango.AttrQuality.ATTR_VALID,
                )

            for (
                smartbox_no,
                smartbox,
            ) in field_station_component_manager._smartbox_proxys.items():
                smartbox_proxy_command = getattr(smartbox._proxy, "SetPortPowers")

                desired_smartbox_port_powers: list[bool | None] = [
                    expected_state
                ] * PasdData.NUMBER_OF_SMARTBOX_PORTS

                if smartbox_no == "sb21":
                    # The last smartbox only has 3 antenna
                    desired_smartbox_port_powers = [expected_state] * 3 + [None] * 9
                if smartbox_no in ["sb22", "sb23", "sb24"]:
                    # The configuration did not put any antenna on the
                    # last 3 smartbox
                    desired_smartbox_port_powers = [
                        None
                    ] * PasdData.NUMBER_OF_SMARTBOX_PORTS
                # if smartbox_no == smartbox_id:
                #     desired_smartbox_port_powers[smartbox_port - 1] = None

                smartbox_json_arg = json.dumps(
                    {
                        "port_powers": desired_smartbox_port_powers,
                        "stay_on_when_offline": True,
                    }
                )

                print(f"smartbox_json_arg == {smartbox_json_arg}")

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
