from __future__ import annotations

import gc
import time
import unittest.mock
from typing import Any, Generator

import pytest
import tango
from ska_control_model import AdminMode, HealthState, LoggingLevel
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
)
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd import MccsPasdBus, MccsSmartBox

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


@pytest.fixture(name="tango_harness")
def tango_harness_fixture(
    smartbox_name: str,
    pasd_bus_name: str,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Return a Tango harness against which to run tests of the deployment.

    :param smartbox_name: the name of the smartbox_bus Tango device
    :param patched_smartbox_device_class: a subclass of MccsSmartBox that
        has been patched with extra commands that mock system under
        control behaviours.

    :yields: a tango context.
    """
    context_manager = ThreadedTestTangoContextManager()
    context_manager.add_device(
        smartbox_name,
        MccsSmartBox,
        LoggingLevelDefault=int(LoggingLevel.DEBUG),
    )
    context_manager.add_device(
        pasd_bus_name,
        MccsPasdBus,
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
    @pytest.mark.xfail()
    def test_subrack_tile_integration(
        self: TestSmartBoxPasdBusIntegration,
        smartbox_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Test the integration of smartbox with the pasdBus.

        TODO: this is a incomplete test.
        # This may be checking for incorrect state transitions.
        # This is technical debt!!
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
        # The station whether the port on the fndh that this subrack is attached to
        # has a subrack attached in the configuration files.
        smartbox_device.adminMode = AdminMode.ONLINE

        # This should not happen?
        change_event_callbacks["smartbox_state"].assert_change_event(
            tango.DevState.UNKNOWN
        )


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
