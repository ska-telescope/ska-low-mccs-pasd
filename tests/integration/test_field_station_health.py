# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the integration tests for MccsPasdBus with MccsFNDH."""

from __future__ import annotations

import gc
import json
from time import sleep
from typing import Callable, Iterator

import pytest
import tango
from ska_control_model import AdminMode, HealthState, LoggingLevel
from ska_tango_testing.mock.tango import MockTangoEventCallbackGroup

from ska_low_mccs_pasd.pasd_bus import FnccSimulator, FndhSimulator, SmartboxSimulator
from tests.harness import PasdTangoTestHarness, PasdTangoTestHarnessContext

gc.disable()  # Bug in garbage collection causes tests to hang.
TIMEOUT = 30


@pytest.fixture(name="change_event_callbacks")
def change_event_callbacks_fixture() -> MockTangoEventCallbackGroup:
    """
    Return a dictionary of change event callbacks with asynchrony support.

    :return: a collections.defaultdict that returns change event
        callbacks by name.
    """
    return MockTangoEventCallbackGroup(
        "field_station_state",
        "field_station_healthstate",
        "fndh_state",
        "fndh_healthstate",
        "smartbox_state",
        "smartbox_healthstate",
        "smartbox_adminMode",
        timeout=TIMEOUT,
    )


@pytest.fixture(name="smartbox_simulators")
def smartbox_simulator_fixture(
    pasd_hw_simulators: dict[int, FndhSimulator | FnccSimulator | SmartboxSimulator],
    smartbox_ids_to_test: list[int],
) -> list[FndhSimulator | FnccSimulator | SmartboxSimulator]:
    """
    Return a smartbox simulator for testing.

    :param pasd_hw_simulators:
        the FNDH and smartbox simulator backends that the TCP server will front.
    :param smartbox_ids_to_test: id list of the smartboxes being addressed.

    :return: a list of smartbox simulators, wrapped in a mock.
    """
    return [pasd_hw_simulators[smartbox_id] for smartbox_id in smartbox_ids_to_test]


@pytest.fixture(name="smartbox_ids_to_test", scope="session")
def smartbox_ids_to_test_fixture() -> list[int]:
    """
    Return a list of smartbox IDs to use in a test.

    :return: a list of smartbox IDs to use in a test
    """
    return list(range(1, 24 + 1))


@pytest.fixture(name="wait_for_lrcs_to_finish")
def wait_for_lrcs_to_finish_fixture() -> Callable:
    """
    Wait for Long Running Commands on devices under test to finish.

    We are sending quite a few LRCs in some of these tests, we must ensure
    they are complete before moving onto the next step, or before trying to
    read attributes.


    :returns: a callable checking status of LRCs on all devices.
    """

    def _wait_for_lrcs_to_finish(
        all_devices: list[tango.DeviceProxy], timeout: int = TIMEOUT
    ) -> None:
        count = 0

        for device in all_devices:
            count = 0
            while device.lrcQueue != () or device.lrcExecuting != ():
                sleep(1)
                count += 1
                if count == timeout:
                    pytest.fail(
                        f"LRCs still running after {timeout} seconds: "
                        f"{device.dev_name()} : {device.lrcQueue=} "
                        f"{device.lrcExecuting=}"
                    )

    return _wait_for_lrcs_to_finish


@pytest.fixture(name="test_context")
def test_context_fixture(
    pasd_hw_simulators: dict[int, FndhSimulator | FnccSimulator | SmartboxSimulator],
    smartbox_ids_to_test: list[int],
    smartbox_attached_ports: list[int],
    smartbox_attached_antennas: list[list[bool]],
    smartbox_attached_antenna_names: list[list[str]],
) -> Iterator[PasdTangoTestHarnessContext]:
    """
    Fixture that returns a proxy to the PaSD bus Tango device under test.

    Here we use 1 pasd bus, 1 fndh, 1 field station, 1 fncc and 24 smartboxes.

    :param pasd_hw_simulators: the FNDH and smartbox simulators against which to test
    :param smartbox_ids_to_test: a list of the smartbox ids used in this test.
    :param smartbox_attached_ports: a list of FNDH port numbers each smartbox
        is connected to.
    :param smartbox_attached_antennas: smartbox port numbers each antenna is
        connected to for each smartbox.
    :param smartbox_attached_antenna_names: names of each antenna connected to
        each smartbox.
    :yield: a test context in which to run the integration tests.
    """
    harness = PasdTangoTestHarness()
    # Set up pasdbus
    harness.set_pasd_bus_simulator(pasd_hw_simulators)
    harness.set_pasd_bus_device(
        polling_rate=0.1,
        device_polling_rate=0.1,
        available_smartboxes=smartbox_ids_to_test,
        logging_level=int(LoggingLevel.FATAL),
    )
    # Set up FNDH
    harness.set_fndh_device(
        int(LoggingLevel.ERROR), ports_with_smartbox=smartbox_attached_ports
    )
    # Set up fncc
    harness.set_fncc_device(int(LoggingLevel.ERROR))

    # set up smartboxes
    for smartbox_id in smartbox_ids_to_test:
        harness.add_smartbox_device(
            smartbox_id,
            int(LoggingLevel.ERROR),
            fndh_port=smartbox_attached_ports[smartbox_id - 1],
            ports_with_antennas=[
                idx + 1
                for idx, attached in enumerate(
                    smartbox_attached_antennas[smartbox_id - 1]
                )
                if attached
            ],
            antenna_names=smartbox_attached_antenna_names[smartbox_id - 1],
        )
    # Set up field station
    harness.set_field_station_device(smartbox_ids_to_test, int(LoggingLevel.ERROR))

    with harness as context:
        yield context


# pylint: disable=too-few-public-methods
class TestFieldStationHealth:
    """Class to test Field Station health."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def _get_devices_on_and_healthy(
        self: TestFieldStationHealth,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        fndh_simulator: FndhSimulator,
        fncc_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        smartbox_proxys: list[tango.DeviceProxy],
        change_event_callbacks: MockTangoEventCallbackGroup,
    ) -> None:
        """
        Get all devices ON and HEALTHY.

        Sets adminMode and turns all devices on. Makes sure all fndh ports are ON

        :param field_station_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fndh_device: Proxy to the FNDH device under test.
        :param fndh_simulator: the FNDH simulator under test
        :param fncc_device: Proxy to the FNCC device under test.
        :param pasd_bus_device: a proxy to the PaSD bus device under test.
        :param smartbox_proxys: list of smartbox proxies to test
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        """
        devices = [
            field_station_device,
            fndh_device,
            pasd_bus_device,
            fncc_device,
        ] + smartbox_proxys
        # Turn on all FNDH Ports so we can control smartboxes
        for port_no in list(range(24)):
            fndh_simulator.turn_port_on(port_no)

        # Bring devices online
        for device in devices:
            device.adminMode = AdminMode.ONLINE
            assert device.adminMode == AdminMode.ONLINE

        change_event_callbacks["field_station_state"].assert_change_event(
            tango.DevState.STANDBY, lookahead=10, consume_nonmatches=True
        )
        for smartbox in smartbox_proxys:
            if smartbox.state() != tango.DevState.ON:
                smartbox.On()

        if field_station_device.state() != tango.DevState.ON:
            field_station_device.On()
            change_event_callbacks["field_station_state"].assert_change_event(
                tango.DevState.ON, lookahead=10
            )

        # Everything should be ON now
        if field_station_device.healthState != HealthState.OK:
            change_event_callbacks["field_station_healthstate"].assert_change_event(
                HealthState.OK, lookahead=10
            )

    def _check_devices_on_and_healthy(
        self: TestFieldStationHealth,
        devices: list[tango.DeviceProxy],
    ) -> None:
        """
        Check that all devices are ON and HEALTHY.

        :param devices: list of devices to check
        """
        # Check we got devices to the right starting state.
        bad_devices = []
        for device in devices:
            if (
                device.state() != tango.DevState.ON
                or device.healthState != HealthState.OK
            ):
                bad_devices.append(device)
        if bad_devices:
            pytest.fail(
                "Some devices are not ON and healthy: "
                f"{[(d.name(), d.state(), d.healthState) for d in bad_devices]}"
            )

    # pylint: disable = too-many-locals
    # flake8: noqa
    def test_health_aggregation(
        self: TestFieldStationHealth,
        field_station_device: tango.DeviceProxy,
        fndh_device: tango.DeviceProxy,
        fncc_device: tango.DeviceProxy,
        pasd_bus_device: tango.DeviceProxy,
        change_event_callbacks: MockTangoEventCallbackGroup,
        fndh_simulator: FndhSimulator,
        smartbox_proxys: list[tango.DeviceProxy],
        wait_for_lrcs_to_finish: Callable,
    ) -> (
        None
    ):  # pylint: disable=too-many-statements, too-many-arguments, too-many-positional-arguments
        """
        Test the health aggregation of the Field Station device.

        :param field_station_device: Proxy to the Field Station device.
        :param fndh_device: fixture that provides a
            :py:class:`tango.DeviceProxy` to the device under test, in a
            :py:class:`tango.test_context.DeviceTestContext`.
        :param fncc_device: Proxy to the FNCC device under test.
        :param pasd_bus_device: a proxy to the PaSD bus device under test.
        :param fndh_simulator: the FNDH simulator under test
        :param change_event_callbacks: dictionary of mock change event
            callbacks with asynchrony support
        :param smartbox_proxys: list of smartbox proxies to test
        :param wait_for_lrcs_to_finish: a callable that waits for all LRCs to finish
        """
        # Change events come in thick and fast so we need to allow some time
        # between us seeing them here and the code under test actually finishing
        # everything it has to do with it.
        event_processing_time = 0.2
        field_station_device.subscribe_event(
            "healthState",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_healthstate"],
        )
        field_station_device.subscribe_event(
            "state",
            tango.EventType.CHANGE_EVENT,
            change_event_callbacks["field_station_state"],
        )
        devices = [
            field_station_device,
            fndh_device,
            pasd_bus_device,
            fncc_device,
        ] + smartbox_proxys
        for device in devices:
            assert device.adminMode == AdminMode.OFFLINE

        # Get devices to a starting state.
        self._get_devices_on_and_healthy(
            field_station_device=field_station_device,
            fndh_device=fndh_device,
            fndh_simulator=fndh_simulator,
            fncc_device=fncc_device,
            pasd_bus_device=pasd_bus_device,
            smartbox_proxys=smartbox_proxys,
            change_event_callbacks=change_event_callbacks,
        )
        wait_for_lrcs_to_finish(devices)
        sleep(1)
        self._check_devices_on_and_healthy(devices)

        assert json.loads(field_station_device.healthThresholds)["smartboxes"] == [
            0,  # All failed = failed
            1,  # Any failed = degraded
            1,  # Any degraded = degraded
        ]
        # Health and thresholds are as expected. Real test begins.

        # Test that as Smartboxes are degraded one by one the health of the
        # Field station goes to and stays degraded.
        failed_thresholds = {
            "inputvoltage": [47.0, 46.0, 9.8, 10.1],
        }
        degraded_thresholds = {
            "inputvoltage": [48.5, 47.0, 9.8, 10.1],
        }
        healthy_thresholds = {
            "inputvoltage": [50.0, 49.0, 45.0, 40.0],
        }
        for smartbox in smartbox_proxys:
            assert smartbox.healthState == HealthState.OK
            smartbox.healthModelParams = json.dumps(degraded_thresholds)
            assert smartbox.healthState == HealthState.DEGRADED

            # FieldStation health should degrade when the first smartbox is degraded.
            if smartbox == smartbox_proxys[0]:
                change_event_callbacks["field_station_healthstate"].assert_change_event(
                    HealthState.DEGRADED, lookahead=10, consume_nonmatches=True
                )
                sleep(event_processing_time)
            assert field_station_device.healthState == HealthState.DEGRADED

        # Reset thresholds to get devices back to healthy state
        for smartbox in smartbox_proxys:
            assert smartbox.healthState == HealthState.DEGRADED
            smartbox.healthModelParams = json.dumps(healthy_thresholds)
            assert smartbox.healthState == HealthState.OK

        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.OK, lookahead=10, consume_nonmatches=True
        )

        # Cause smartboxes to fail one by one.
        # Should be degraded when one fails, and failed when all fail.
        for smartbox in smartbox_proxys:
            assert smartbox.healthState == HealthState.OK
            smartbox.healthModelParams = json.dumps(failed_thresholds)
            assert smartbox.healthState == HealthState.FAILED

            # FieldStation health should degrade when the first smartbox fails.
            if smartbox == smartbox_proxys[0]:
                change_event_callbacks["field_station_healthstate"].assert_change_event(
                    HealthState.DEGRADED, lookahead=10, consume_nonmatches=True
                )
            # Should be degraded until the last smartbox fails.
            if smartbox != smartbox_proxys[-1]:
                sleep(event_processing_time)
                assert field_station_device.healthState == HealthState.DEGRADED

        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.FAILED, lookahead=10, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.FAILED

        # Get back to healthy.
        for smartbox in smartbox_proxys:
            smartbox.healthModelParams = json.dumps(healthy_thresholds)
            assert smartbox.healthState == HealthState.OK
        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.OK, lookahead=10, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.OK

        # Change thresholds and repeat the above test.
        # 2 Failed = Failed
        # 1 Failed = Degraded
        # 3 Degraded = Degraded
        field_station_device.healthThresholds = json.dumps(
            {
                "smartboxes": [2, 1, 3],
            }
        )
        assert json.loads(field_station_device.healthThresholds)["smartboxes"] == [
            2,
            1,
            3,
        ]

        # Check d2d threshold.
        for smartbox in smartbox_proxys[:3]:
            assert field_station_device.healthState == HealthState.OK
            assert smartbox.healthState == HealthState.OK
            smartbox.healthModelParams = json.dumps(degraded_thresholds)
            assert smartbox.healthState == HealthState.DEGRADED

        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.DEGRADED, lookahead=10, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.DEGRADED

        # Reset
        for smartbox in smartbox_proxys[:3]:
            smartbox.healthModelParams = json.dumps(healthy_thresholds)
            assert smartbox.healthState == HealthState.OK

        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.OK, lookahead=10, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.OK

        # Check f2d threshold.
        assert smartbox_proxys[0].healthState == HealthState.OK
        smartbox_proxys[0].healthModelParams = json.dumps(failed_thresholds)
        assert smartbox_proxys[0].healthState == HealthState.FAILED
        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.DEGRADED, lookahead=10, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.DEGRADED

        # Check f2f threshold.
        assert smartbox_proxys[1].healthState == HealthState.OK
        smartbox_proxys[1].healthModelParams = json.dumps(failed_thresholds)
        assert smartbox_proxys[1].healthState == HealthState.FAILED
        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.FAILED, lookahead=10, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.FAILED

        # Reset
        for smartbox in smartbox_proxys[:2]:
            smartbox.healthModelParams = json.dumps(healthy_thresholds)
            assert smartbox.healthState == HealthState.OK
        field_station_device.healthThresholds = json.dumps(
            {
                "smartboxes": [0, 1, 1],
            }
        )
        change_event_callbacks["field_station_healthstate"].assert_change_event(
            HealthState.OK, lookahead=15, consume_nonmatches=True
        )
        sleep(event_processing_time)
        assert field_station_device.healthState == HealthState.OK
