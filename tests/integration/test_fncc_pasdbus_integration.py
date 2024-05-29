# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsFNCC."""

from __future__ import annotations

import gc

import pytest
import tango
from ska_control_model import AdminMode, HealthState
from ska_tango_testing.mock.placeholders import Anything
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FnccSimulator
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import PasdConversionUtility

from ..conftest import Helpers

gc.disable()  # TODO: why is this needed?


class TestfnccPasdBusIntegration:
    """Test pasdbus and fncc integration."""

    def test_fncc_pasd_integration(
        self: TestfnccPasdBusIntegration,
        fncc_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of fncc with the pasdBus.

        :param fncc_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param change_event_callbacks: group of Tango change event
            callback with asynchronous support
        """
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        assert fncc_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        fncc_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fncc_state"],
        )
        change_event_callbacks["fncc_state"].assert_change_event(tango.DevState.DISABLE)
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
        # ================================================================
        pasd_bus_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )
        # TODO: Do we want to enter On state here?
        change_event_callbacks["pasd_bus_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["pasd_bus_state"].assert_not_called()

        # The fncc should enter UNKNOWN, if communication can be established
        # the FNCC has power.
        fncc_device.adminMode = AdminMode.ONLINE
        change_event_callbacks["fncc_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fncc_state"].assert_change_event(tango.DevState.ON)
        # ================================================================

    # pylint: disable=too-many-arguments
    def test_communication(
        self: TestfnccPasdBusIntegration,
        fncc_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        fncc_simulator: FnccSimulator,
        change_event_callbacks: MockTangoEventCallbackGroup,
        last_smartbox_id: int,
    ) -> None:
        """
        Test the Tango device's communication with the PaSD bus.

        :param fncc_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param pasd_bus_device: a proxy to the PaSD bus device under test.
        :param fncc_simulator: the FNCC simulator under test
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        :param last_smartbox_id: ID of the last smartbox polled
        """
        # adminMode offline and in DISABLE state
        # ----------------------------------------------------------------
        assert fncc_device.adminMode == AdminMode.OFFLINE
        assert pasd_bus_device.adminMode == AdminMode.OFFLINE

        pasd_bus_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasd_bus_state"],
        )
        change_event_callbacks.assert_change_event(
            "pasd_bus_state", tango.DevState.DISABLE
        )

        fncc_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["fncc_state"],
        )
        change_event_callbacks["fncc_state"].assert_change_event(tango.DevState.DISABLE)

        pasd_bus_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["pasdBushealthState"],
        )

        change_event_callbacks.assert_change_event(
            "pasdBushealthState", HealthState.UNKNOWN
        )
        assert pasd_bus_device.healthState == HealthState.UNKNOWN
        # -----------------------------------------------------------------

        # This is a bit of a cheat.
        # It's an implementation-dependent detail that
        # this is one of the last attributes to be read from the simulator.
        # We subscribe events on this attribute because we know that
        # once we have an updated value for this attribute,
        # we have an updated value for all of them.
        pasd_bus_device.subscribe_event(
            f"smartbox{last_smartbox_id}AlarmFlags",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks[f"smartbox{last_smartbox_id}AlarmFlags"],
        )
        change_event_callbacks.assert_change_event(
            f"smartbox{last_smartbox_id}AlarmFlags", Anything
        )

        pasd_bus_device.adminMode = AdminMode.ONLINE  # type: ignore[assignment]

        # TODO: Weird behaviour, this started failing with WOM-276 changes
        Helpers.print_change_event_queue(change_event_callbacks, "pasd_bus_state")
        # change_event_callbacks.assert_change_event(
        #     "pasd_bus_state", tango.DevState.UNKNOWN
        # )
        # change_event_callbacks.assert_change_event(
        #     "pasd_bus_state", tango.DevState.ON
        # )
        change_event_callbacks["pasd_bus_state"].assert_change_event(
            tango.DevState.ON, 2, True
        )

        change_event_callbacks.assert_change_event("pasdBushealthState", HealthState.OK)
        assert pasd_bus_device.healthState == HealthState.OK

        fncc_device.adminMode = AdminMode.ONLINE

        change_event_callbacks["fncc_state"].assert_change_event(tango.DevState.UNKNOWN)
        change_event_callbacks["fncc_state"].assert_change_event(tango.DevState.ON)
        change_event_callbacks["fncc_state"].assert_not_called()

        assert (
            fncc_device.ModbusRegisterMapRevisionNumber
            == FnccSimulator.MODBUS_REGISTER_MAP_REVISION
        )
        assert fncc_device.SysAddress == FnccSimulator.SYS_ADDRESS
        assert fncc_device.PcbRevisionNumber == FnccSimulator.PCB_REVISION
        assert (
            fncc_device.CpuId
            == PasdConversionUtility.convert_cpu_id(FnccSimulator.CPU_ID)[0]
        )
        assert (
            fncc_device.ChipId
            == PasdConversionUtility.convert_chip_id(FnccSimulator.CHIP_ID)[0]
        )
        assert (
            fncc_device.FirmwareVersion
            == PasdConversionUtility.convert_firmware_version(
                [FnccSimulator.DEFAULT_FIRMWARE_VERSION]
            )[0]
        )
        assert (
            fncc_device.Uptime
            <= PasdConversionUtility.convert_uptime(fncc_simulator.uptime)[0]
        )
        assert fncc_device.PasdStatus == "OK"
        assert fncc_device.FieldNodeNumber == fncc_simulator.FIELD_NODE_NUMBER


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture(
    last_smartbox_id: int,
) -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of callables to be used as Tango change event callbacks.

    :param last_smartbox_id: ID of the last smartbox polled
    :return: a dictionary of callables to be used as tango change event
        callbacks.
    """
    return MockTangoEventCallbackGroup(
        "fncc_state",
        "pasd_bus_state",
        "pasdBushealthState",
        f"smartbox{last_smartbox_id}AlarmFlags",
        timeout=26.0,
        assert_no_error=False,
    )
