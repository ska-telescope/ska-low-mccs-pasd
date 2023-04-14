# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsSmartBox."""

from __future__ import annotations

import gc
import json
import time
from typing import Generator

import numpy as np
import pytest
import tango
from ska_control_model import AdminMode, LoggingLevel
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup
from tango.server import command

from ska_low_mccs_pasd import MccsPasdBus, MccsSmartBox
from ska_low_mccs_pasd.pasd_bus import SmartboxSimulator

gc.disable()  # TODO: why is this needed?


@pytest.fixture(name="pasd_bus_name", scope="session")
def pasd_bus_name_fixture() -> str:
    """
    Return the name of the pasd_bus Tango device.

    :return: the name of the pasd_bus Tango device.
    """
    return "low-mccs-pasd/pasdbus/001"


@pytest.fixture(name="smartbox_name", scope="session")
def smartbox_name_fixture() -> str:
    """
    Return the name of the smartbox_bus Tango device.

    :return: the name of the smartbox_bus Tango device.
    """
    return "low-mccs-smartbox/smartbox/00001"


@pytest.fixture(name="patched_pasd_device_class")
def patched_pasd_device_class_fixture() -> type[MccsSmartBox]:
    """
    Return a pasd bus device that is patched with a mock push change event.

    :return: a pasd bus device that is patched with a mock push change event
    """

    class PatchedMccsPasdBus(MccsPasdBus):
        """This patched device allows us to push_change_events."""

        @command(dtype_in="DevString")
        def mocked_push_change_event(self: PatchedMccsPasdBus, argin: str) -> None:
            """
            Turn on the FNDH's blue service LED.

            :param argin: a json encoded dictionary.
            """
            arg = json.loads(argin)

            for key, value in arg.items():
                self.push_change_event(key, np.array([value]))

    return PatchedMccsPasdBus


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    smartbox_name: str,
    pasd_bus_name: str,
    pasd_bus_info: dict,
    patched_pasd_device_class: MccsSmartBox,
    smartbox_number: int,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param smartbox_name: the name of the smartbox_bus Tango device
    :param pasd_bus_name: the fqdn of the pasdbus
    :param pasd_bus_info: the information for pasd setup
    :param patched_pasd_device_class: a pasdbus with a mocked command to
        push change events.
    :param smartbox_number: the number assigned to the smartbox of interest.

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        smartbox_name,
        MccsSmartBox,
        FndhPort=0,
        PasdFQDNs=pasd_bus_name,
        SmartBoxNumber=smartbox_number,
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    context_manager.add_device(
        pasd_bus_name,
        patched_pasd_device_class,
        Host=pasd_bus_info["host"],
        Port=pasd_bus_info["port"],
        Timeout=pasd_bus_info["timeout"],
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    with context_manager as context:
        yield context


@pytest.fixture(name="smartbox_device")
def smartbox_device_fixture(
    tango_harness: TangoContextProtocol,
    smartbox_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the smartbox_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param smartbox_name: name of the smartbox_bus Tango device.

    :yield: the smartbox_bus Tango device under test.
    """
    yield tango_harness.get_device(smartbox_name)


@pytest.fixture(name="pasd_bus_device")
def pasd_bus_device_fixture(
    tango_harness: TangoContextProtocol,
    pasd_bus_name: str,
) -> tango.DeviceProxy:
    """
    Fixture that returns the pasd_bus Tango device under test.

    :param tango_harness: a test harness for Tango devices.
    :param pasd_bus_name: name of the pasd_bus Tango device.

    :yield: the pasd_bus Tango device under test.
    """
    yield tango_harness.get_device(pasd_bus_name)


class TestSmartBoxPasdBusIntegration:  # pylint: disable=too-few-public-methods
    """Test pasdbus and smartbox integration."""

    def test_smartbox_pasd_integration(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of smartbox with the pasdBus.

        This tests basic communications:
        - Does the state transition as expected when adminMode put online
        with the MccsPasdBus
        - Can MccsSmartBox handle a changing attribute event pushed from the
        MccsPasdBus.

        :param smartbox_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchrony support
        """
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        assert smartbox_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        smartbox_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["smartbox_state"],
        )
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.DISABLE
        )
        change_event_callbacks["pasd_bus_state"].assert_not_called()
        # ----------------------------------------------------------------
        # Check that the devices enters the correct state after turning adminMode on
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # The smartbox should enter UNKNOWN, then it should check with the
        # The fndh that the port this subrack is attached to
        # has power, this is simulated as off.

        # Check that we get a DevFailed for accessing non initialied attributes.
        for i in [
            "ModbusRegisterMapRevisionNumber",
            "PcbRevisionNumber",
            "CpuId",
            "ChipId",
            "FirmwareVersion",
            "Uptime",
            "InputVoltage",
            "PowerSupplyOutputVoltage",
            "PowerSupplyTemperature",
            "OutsideTemperature",
            "PcbTemperature",
        ]:
            with pytest.raises(tango.DevFailed):
                getattr(smartbox_device, i)

        smartbox_device.adminMode = AdminMode.ONLINE

        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        change_event_callbacks["smartbox_state"].assert_change_event(tango.DevState.OFF)
        change_event_callbacks["smartbox_state"].assert_not_called()
        # Check that the smartbox has updated its values from the smartbox simulator.
        assert (
            smartbox_device.ModbusRegisterMapRevisionNumber
            == SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION
        )
        assert smartbox_device.PcbRevisionNumber == SmartboxSimulator.PCB_REVISION
        assert smartbox_device.CpuId == SmartboxSimulator.CPU_ID
        assert smartbox_device.ChipId == SmartboxSimulator.CHIP_ID
        assert (
            smartbox_device.FirmwareVersion
            == SmartboxSimulator.DEFAULT_FIRMWARE_VERSION
        )
        assert smartbox_device.Uptime == SmartboxSimulator.DEFAULT_UPTIME
        assert smartbox_device.InputVoltage == SmartboxSimulator.DEFAULT_INPUT_VOLTAGE
        assert (
            smartbox_device.PowerSupplyOutputVoltage
            == SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
        )
        assert (
            smartbox_device.PowerSupplyTemperature
            == SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
        )
        assert (
            smartbox_device.OutsideTemperature
            == SmartboxSimulator.DEFAULT_OUTSIDE_TEMPERATURE
        )
        assert (
            smartbox_device.PcbTemperature == SmartboxSimulator.DEFAULT_PCB_TEMPERATURE
        )

        # TODO: Add the polling mechanism to the MccsPasdBus,
        # We will then be able to mock a change in attributes at the Simulator level.
        # The MccsPasdBus will then poll this and fire a event we can catch.

        # Below is a bit of a hack just to test the functionality:
        # The patched MccsPasdBus has a mock_push_change_event
        # allowing us to manually fire change events.
        initial_input_voltage = smartbox_device.InputVoltage
        mock_input_voltage = '{"smartbox1InputVoltage": 4}'
        pasd_bus_device.mocked_push_change_event(mock_input_voltage)
        time.sleep(0.1)
        assert smartbox_device.InputVoltage != initial_input_voltage
        assert smartbox_device.InputVoltage == 4


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "smartbox_state",
        "pasd_bus_state",
        timeout=2.0,
    )
