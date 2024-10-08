# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for MccsFieldStation."""

from __future__ import annotations

import gc
import json
import unittest.mock
from typing import Any

import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel, ResultCode
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsFieldStation
from ska_low_mccs_pasd.pasd_data import PasdData
from tests.harness import PasdTangoTestHarness

# TODO: Weird hang-at-garbage-collection bug
gc.disable()


def _antenna_mask_arg() -> str:
    antenna_mask: dict = {}
    for antenna_no in range(PasdData.NUMBER_OF_ANTENNAS):
        antenna_mask[f"sb-{antenna_no:02d}"] = False
    # Mask the first 12 antennas
    for antenna_no in range(PasdData.NUMBER_OF_SMARTBOX_PORTS):
        antenna_mask[f"sb-{antenna_no:02d}"] = True
    # The 94th element in this list will have antennaID = 95
    antenna_mask["sb-94"] = True

    return json.dumps({"antennaMask": antenna_mask})


def _bad_antenna_mask_arg() -> str:
    good_antenna_mask_arg = _antenna_mask_arg()

    # Take a good argument, and mess it up
    bad_antenna_mask = json.loads(good_antenna_mask_arg)

    # Non-boolean state? Can't have that
    bad_antenna_mask["antennaMask"]["sb-123"] = "Something horrible"

    return json.dumps(bad_antenna_mask)


def _antenna_mapping_arg() -> str:
    antenna_mapping: dict = {}
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS):
            try:
                antenna_no = f"sb{smartbox_no:02d}-{smartbox_port}"
                antenna_mapping[antenna_no] = {}
                antenna_mapping[antenna_no]["smartboxID"] = f"sb{smartbox_no}"
                antenna_mapping[antenna_no]["smartboxPort"] = smartbox_port
            except IndexError:
                break

    # Swap two antennas
    antenna_mapping["sb01-1"]["smartboxID"] = "sb01-2"
    antenna_mapping["sb01-1"]["smartboxPort"] = 2

    antenna_mapping["sb01-2"]["smartboxID"] = "sb01-1"
    antenna_mapping["sb01-2"]["smartboxPort"] = 1

    return json.dumps({"antennaMapping": antenna_mapping})


def _bad_antenna_mapping_arg() -> str:
    good_antenna_mapping_arg = _antenna_mapping_arg()

    # Take a good argument, and mess it up
    bad_antenna_mapping = json.loads(good_antenna_mapping_arg)

    # 257 antennas? Don't like that
    extra_antenna = {
        "smartboxID": 123,
        "smartboxPort": 3,
    }

    bad_antenna_mapping["antennaMapping"]["257"] = extra_antenna

    return json.dumps(bad_antenna_mapping)


def _smartbox_mapping_arg() -> str:
    smartbox_mapping: dict = {}
    for smartbox_no in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION):
        for smartbox_port in range(1, PasdData.NUMBER_OF_SMARTBOX_PORTS):
            smartbox_mapping[f"sb{smartbox_no:02d}"] = smartbox_port

    # Swap two smartboxes
    smartbox_mapping["sb01"] = 2

    smartbox_mapping["sb02"] = 1

    return json.dumps({"smartboxMapping": smartbox_mapping})


def _bad_smartbox_mapping_arg() -> str:
    good_smartbox_mapping_arg = _smartbox_mapping_arg()

    # Take a good argument, and mess it up
    bad_smartbox_mapping = json.loads(good_smartbox_mapping_arg)

    # 25 smartboxes? Don't like that

    bad_smartbox_mapping["smartboxMapping"]["sb100"] = [100]

    return json.dumps(bad_smartbox_mapping)


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
        timeout=2.0,
        assert_no_error=False,
    )


@pytest.fixture(name="mock_component_manager")
def mock_component_manager_fixture() -> unittest.mock.Mock:
    """
    Return a mock to be used as a component manager for the field station bus device.

    :return: a mock to be used as a component manager for the
        field station bus device.
    """
    component_manager = unittest.mock.Mock()
    component_manager.max_queued_tasks = 0
    component_manager.max_executing_tasks = 1
    return component_manager


@pytest.fixture(name="patched_field_station_device_class")
def patched_field_station_device_class_fixture(
    mock_component_manager: unittest.mock.Mock,
) -> type[MccsFieldStation]:
    """
    Return a field station bus device that is patched with a mock component manager.

    :param mock_component_manager: the mock component manager with
        which to patch the device

    :return: a field station bus device that is patched with a mock component
        manager.
    """

    class PatchedMccsFieldStation(MccsFieldStation):
        """A field station bus device patched with a mock component manager."""

        def create_component_manager(
            self: PatchedMccsFieldStation,
        ) -> unittest.mock.Mock:
            """
            Return a mock component manager instead of the usual one.

            :return: a mock component manager
            """
            mock_component_manager._component_state_callback = (
                self._component_state_callback
            )

            return mock_component_manager

    return PatchedMccsFieldStation


@pytest.fixture(name="simulated_configuration", scope="module")
def simulated_configuration_fixture() -> dict[Any, Any]:
    """
    Return a configuration for the fieldstation.

    :return: a configuration for representing the antenna port mapping information.
    """
    number_of_antenna = 256
    antennas = {}
    smartboxes = {}
    for i in range(1, number_of_antenna + 1):
        antennas[str(i)] = {"smartbox": str(i % 13 + 1), "smartbox_port": i % 11}
    for i in range(1, PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION + 1):
        smartboxes[str(i)] = {"fndh_port": i}

    configuration = {"antennas": antennas, "pasd": {"smartboxes": smartboxes}}
    return configuration


@pytest.fixture(name="configuration_manager", scope="module")
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


@pytest.fixture(name="field_station_device")
def field_station_device_fixture(
    patched_field_station_device_class: type[MccsFieldStation],
    mock_fndh: unittest.mock.Mock,
    mock_smartbox: unittest.mock.Mock,
    configuration_manager: unittest.mock.Mock,
) -> tango.DeviceProxy:
    """
    Fixture that returns a proxy to the FieldStation Tango device under test.

    :param patched_field_station_device_class: a patches class for use in testing.
    :param mock_fndh: a mock FNDH for use in testing.
    :param mock_smartbox: a mock Smartbox for use in testing.
    :param configuration_manager: the configuration manager to manage configuration
        for field station.

    :yield: a proxy to the FieldStation Tango device under test.
    """
    harness = PasdTangoTestHarness()
    harness.set_mock_fndh_device(mock_fndh)
    for smarbox_no in range(1, 24 + 1):
        harness.set_mock_smartbox_device(mock_smartbox, smarbox_no)
    harness.set_configuration_server(configuration_manager)
    harness.set_field_station_device(
        logging_level=int(LoggingLevel.DEBUG),
        device_class=patched_field_station_device_class,
    )

    with harness as context:
        yield context.get_field_station_device()


def test_outside_temperature(
    field_station_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    mocked_outside_temperature: float,
) -> None:
    """
    Test reading the outsideTemperature from the FieldStation.

    :param field_station_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched field station bus device.
    :param mocked_outside_temperature: the mocked outsideTemperature.
    """
    # Before a value is set it will be None.
    mock_component_manager.outsideTemperature = None
    with pytest.raises(tango.DevFailed):
        field_station_device.outsideTemperature  # pylint: disable=pointless-statement

    # Check wrong type.
    mock_component_manager.outsideTemperature = "36.5"
    with pytest.raises(tango.DevFailed):
        field_station_device.outsideTemperature  # pylint: disable=pointless-statement

    # check happy case with a
    mock_component_manager.outsideTemperature = mocked_outside_temperature
    assert field_station_device.outsideTemperature == mocked_outside_temperature


@pytest.mark.parametrize(
    (
        "device_command",
        "component_manager_method",
        "device_command_argin",
        "component_manager_method_return",
    ),
    [
        pytest.param(
            "PowerOnAntenna",
            "turn_on_antenna",
            "4",
            [True, True],
            id="Power on an antenna",
        ),
        pytest.param(
            "PowerOffAntenna",
            "turn_off_antenna",
            "4",
            [True, True],
            id="Power off an antenna",
        ),
        pytest.param(
            "UpdateAntennaMask",
            "update_antenna_mask",
            _antenna_mask_arg(),
            [True, True],
            id="Manually update antenna mask",
        ),
        pytest.param(
            "UpdateAntennaMapping",
            "update_antenna_mapping",
            _antenna_mapping_arg(),
            [True, True],
            id="Manually update antenna mapping",
        ),
        pytest.param(
            "UpdateSmartboxMapping",
            "update_smartbox_mapping",
            _smartbox_mapping_arg(),
            [True, True],
            id="Manually update smartbox mapping",
        ),
    ],
)
def test_command(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    field_station_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
) -> None:
    """
    Test tango command with mocked response from component manager.

    :param field_station_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched field station bus device.
    :param device_command: name of the device command under test.
    :param component_manager_method: name of the component manager
        method that is expected to be called when the device
        command is called.
    :param device_command_argin: argument to the device command
    :param component_manager_method_return: return value of the
        component manager method
    """
    method_mock = unittest.mock.Mock(return_value=component_manager_method_return)
    setattr(mock_component_manager, component_manager_method, method_mock)
    method_mock.assert_not_called()

    command = getattr(field_station_device, device_command)
    field_station_device.adminMode = AdminMode.ONLINE
    if device_command_argin is None:
        command_return = command()
    else:
        command_return = command(device_command_argin)

    method_mock.assert_called()

    assert command_return[0] == ResultCode.QUEUED
    assert command_return[1][0].split("_")[-1] == device_command


@pytest.mark.parametrize(
    (
        "device_command",
        "component_manager_method",
        "device_command_argin",
        "component_manager_method_return",
    ),
    [
        pytest.param(
            "UpdateAntennaMask",
            "update_antenna_mask",
            _bad_antenna_mask_arg(),
            [True, True],
            id="Manually update antenna mask with invalid schema",
        ),
        pytest.param(
            "UpdateAntennaMapping",
            "update_antenna_mapping",
            _bad_antenna_mapping_arg(),
            [True, True],
            id="Manually update antenna mapping with invalid schema",
        ),
        pytest.param(
            "UpdateSmartboxMapping",
            "update_smartbox_mapping",
            _bad_smartbox_mapping_arg(),
            [True, True],
            id="Manually update smartbox mapping with invalid schema",
        ),
    ],
)
# pylint: disable=too-many-arguments, too-many-positional-arguments
def test_invalid_json_commands(
    field_station_device: tango.DeviceProxy,
    mock_component_manager: unittest.mock.Mock,
    device_command: str,
    component_manager_method: str,
    device_command_argin: Any,
    component_manager_method_return: Any,
) -> None:
    """
    Test we get Json validation errors when we attempt commands with invalid schema.

    :param field_station_device: fixture that provides a
        :py:class:`tango.DeviceProxy` to the device under test, in a
        :py:class:`tango.test_context.DeviceTestContext`.
    :param mock_component_manager: the mock component manager being
        used by the patched field station bus device.
    :param device_command: name of the device command under test.
    :param component_manager_method: name of the component manager
        method that is expected to be called when the device
        command is called.
    :param device_command_argin: argument to the device command
    :param component_manager_method_return: return value of the
        component manager method
    """
    method_mock = unittest.mock.Mock(return_value=component_manager_method_return)
    setattr(mock_component_manager, component_manager_method, method_mock)
    method_mock.assert_not_called()

    command = getattr(field_station_device, device_command)
    field_station_device.adminMode = AdminMode.ONLINE

    with pytest.raises(tango.DevFailed) as err:
        command(device_command_argin)

    assert "jsonschema.exceptions.ValidationError" in str(err.value)
    method_mock.assert_not_called()
