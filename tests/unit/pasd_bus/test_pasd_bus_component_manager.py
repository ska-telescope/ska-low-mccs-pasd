# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus component manager."""
from __future__ import annotations

import logging
import random
from typing import Any, Iterator

import pytest
from ska_control_model import CommunicationStatus, PowerState
from ska_tango_testing.mock import MockCallableGroup
from ska_tango_testing.mock.placeholders import Anything

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusComponentManager,
    SmartboxSimulator,
)
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import PasdConversionUtility
from tests.harness import PasdTangoTestHarness


@pytest.fixture(name="mock_callbacks")
def mock_callbacks_fixture() -> MockCallableGroup:
    """
    Return a group of callables with asynchrony support.

    These can be used in tests as callbacks. When the production code
    expects to be passed a callback, we pass it a member of this group,
    and we can then assert on the order and timing of calls.

    :return: a group of callables ith asynchrony support.
    """
    smartbox_callback_names = [
        f"pasd_device_state_for_smartbox{i}" for i in range(1, 25)
    ]

    return MockCallableGroup(
        "communication_state",
        "component_state",
        "pasd_device_state_for_fndh",
        *smartbox_callback_names,
        timeout=20.0,
    )


@pytest.fixture(name="pasd_bus_component_manager")
def pasd_bus_component_manager_fixture(
    mock_fndh_simulator: FndhSimulator,
    mock_smartbox_simulators: dict[int, SmartboxSimulator],
    logger: logging.Logger,
    mock_callbacks: MockCallableGroup,
) -> Iterator[PasdBusComponentManager]:
    """
    Return a PaSD bus component manager, running against a PaSD bus simulator.

    :param mock_fndh_simulator:
        the FNDH simulator backend that the TCP server will front,
        wrapped with a mock so that we can assert calls.
    :param mock_smartbox_simulators:
        the smartbox simulator backends that the TCP server will front,
        each wrapped with a mock so that we can assert calls.
    :param logger: the logger to be used by this object.
    :param mock_callbacks: a group of mock callables for the component
        manager under test to use as callbacks

    :yields: a PaSD bus component manager, running against a simulator.
    """

    def _pasd_device_state_splitter(device_id: int, **kwargs: Any) -> None:
        device_name = "fndh" if device_id == 0 else f"smartbox{device_id}"
        mock_callbacks[f"pasd_device_state_for_{device_name}"](**kwargs)

    harness = PasdTangoTestHarness()
    harness.set_pasd_bus_simulator(mock_fndh_simulator, mock_smartbox_simulators)
    with harness as context:
        (host, port) = context.get_pasd_bus_address()

        component_manager = PasdBusComponentManager(
            host,
            port,
            0.1,  # polling_rate very fast for unit testing
            0.2,  # device_polling_rate very fast for unit testing
            3.0,
            logger,
            mock_callbacks["communication_state"],
            mock_callbacks["component_state"],
            _pasd_device_state_splitter,
        )
        yield component_manager

        # Ensure the component manager closes its socket during teardown
        component_manager.stop_communicating()


class TestPasdBusComponentManager:
    """
    Tests of commands common to the PaSDBus simulator and its component manager.

    Because the PaSD bus component manager passes commands down to the
    PaSD bus simulator, many commands are common. Here we test those
    common commands.
    """

    # pylint: disable=too-many-arguments
    def test_attribute_updates(
        self: TestPasdBusComponentManager,
        pasd_config: dict,
        pasd_bus_component_manager: PasdBusComponentManager,
        fndh_simulator: FndhSimulator,
        smartbox_simulator: SmartboxSimulator,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test that the PaSD bus component manager receives updated values.

        :param pasd_config: a dictionary of PaSD configuration data with
            which the PaSD under test was configured.
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test.
        :param fndh_simulator: the FNDH simulator under test.
        :param smartbox_simulator: the smartbox simulator under test.
        :param mock_callbacks: a group of mock callables for the component
            manager under test to use as callbacks
        """
        mock_callbacks.assert_not_called()

        pasd_bus_component_manager.start_communicating()

        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.ESTABLISHED
        )
        mock_callbacks.assert_call("component_state", power=PowerState.ON, fault=False)

        pasd_bus_component_manager.initialize_fndh()
        for smartbox_number in range(1, 25):
            pasd_bus_component_manager.initialize_smartbox(smartbox_number)

        # First we'll receive static info about the FNDH
        mock_callbacks.assert_call(
            "pasd_device_state_for_fndh",
            modbus_register_map_revision=FndhSimulator.MODBUS_REGISTER_MAP_REVISION,
            pcb_revision=FndhSimulator.PCB_REVISION,
            cpu_id=PasdConversionUtility.convert_cpu_id(FndhSimulator.CPU_ID)[0],
            chip_id=PasdConversionUtility.convert_chip_id(FndhSimulator.CHIP_ID)[0],
            firmware_version=PasdConversionUtility.convert_firmware_version(
                [FndhSimulator.DEFAULT_FIRMWARE_VERSION]
            )[0],
            lookahead=25,
        )
        for smartbox_number in range(1, 25):
            mock_callbacks.assert_call(
                f"pasd_device_state_for_smartbox{smartbox_number}",
                modbus_register_map_revision=(
                    SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION
                ),
                pcb_revision=SmartboxSimulator.PCB_REVISION,
                cpu_id=PasdConversionUtility.convert_cpu_id(SmartboxSimulator.CPU_ID)[
                    0
                ],
                chip_id=PasdConversionUtility.convert_chip_id(
                    SmartboxSimulator.CHIP_ID
                )[0],
                firmware_version=PasdConversionUtility.convert_firmware_version(
                    [SmartboxSimulator.DEFAULT_FIRMWARE_VERSION]
                )[0],
                lookahead=25,
            )
        # and then the FNDH sensor thresholds
        mock_callbacks.assert_call(
            "pasd_device_state_for_fndh",
            psu48v_voltage_1_thresholds=PasdConversionUtility.scale_volts(
                fndh_simulator.psu48v_voltage_1_thresholds
            ),
            psu48v_voltage_2_thresholds=PasdConversionUtility.scale_volts(
                fndh_simulator.psu48v_voltage_2_thresholds
            ),
            psu48v_current_thresholds=PasdConversionUtility.scale_48vcurrents(
                fndh_simulator.psu48v_current_thresholds
            ),
            psu48v_temperature_1_thresholds=(
                PasdConversionUtility.scale_signed_16bit(
                    fndh_simulator.psu48v_temperature_1_thresholds
                )
            ),
            psu48v_temperature_2_thresholds=(
                PasdConversionUtility.scale_signed_16bit(
                    fndh_simulator.psu48v_temperature_2_thresholds
                )
            ),
            panel_temperature_thresholds=PasdConversionUtility.scale_signed_16bit(
                fndh_simulator.panel_temperature_thresholds
            ),
            fncb_temperature_thresholds=PasdConversionUtility.scale_signed_16bit(
                fndh_simulator.fncb_temperature_thresholds
            ),
            fncb_humidity_thresholds=fndh_simulator.fncb_humidity_thresholds,
            comms_gateway_temperature_thresholds=(
                PasdConversionUtility.scale_signed_16bit(
                    fndh_simulator.comms_gateway_temperature_thresholds
                )
            ),
            power_module_temperature_thresholds=(
                PasdConversionUtility.scale_signed_16bit(
                    fndh_simulator.power_module_temperature_thresholds
                )
            ),
            outside_temperature_thresholds=(
                PasdConversionUtility.scale_signed_16bit(
                    fndh_simulator.outside_temperature_thresholds
                )
            ),
            internal_ambient_temperature_thresholds=(
                PasdConversionUtility.scale_signed_16bit(
                    fndh_simulator.internal_ambient_temperature_thresholds
                )
            ),
        )
        for smartbox_number in range(1, 25):
            # smartbox sensor thresholds
            mock_callbacks.assert_call(
                f"pasd_device_state_for_smartbox{smartbox_number}",
                input_voltage_thresholds=PasdConversionUtility.scale_volts(
                    smartbox_simulator.input_voltage_thresholds
                ),
                power_supply_output_voltage_thresholds=(
                    PasdConversionUtility.scale_volts(
                        smartbox_simulator.power_supply_output_voltage_thresholds
                    )
                ),
                power_supply_temperature_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.power_supply_temperature_thresholds
                    )
                ),
                pcb_temperature_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.pcb_temperature_thresholds
                    )
                ),
                fem_ambient_temperature_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.fem_ambient_temperature_thresholds
                    )
                ),
                fem_case_temperature_1_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.fem_case_temperature_1_thresholds
                    )
                ),
                fem_case_temperature_2_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.fem_case_temperature_2_thresholds
                    )
                ),
                fem_heatsink_temperature_1_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.fem_heatsink_temperature_1_thresholds
                    )
                ),
                fem_heatsink_temperature_2_thresholds=(
                    PasdConversionUtility.scale_signed_16bit(
                        smartbox_simulator.fem_heatsink_temperature_2_thresholds
                    )
                ),
            )
        # Then FNDH status info
        mock_callbacks["pasd_device_state_for_fndh"].assert_call(
            uptime=Anything,
            sys_address=FndhSimulator.SYS_ADDRESS,
            status="OK",
            led_pattern="service: OFF, status: OFF",
            psu48v_voltages=PasdConversionUtility.scale_volts(
                FndhSimulator.DEFAULT_PSU48V_VOLTAGES
            ),
            psu48v_current=PasdConversionUtility.scale_48vcurrents(
                [FndhSimulator.DEFAULT_PSU48V_CURRENT]
            )[0],
            psu48v_temperatures=PasdConversionUtility.scale_signed_16bit(
                FndhSimulator.DEFAULT_PSU48V_TEMPERATURES
            ),
            panel_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_PANEL_TEMPERATURE]
            )[0],
            fncb_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_FNCB_TEMPERATURE]
            )[0],
            fncb_humidity=FndhSimulator.DEFAULT_FNCB_HUMIDITY,
            comms_gateway_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE]
            )[0],
            power_module_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE]
            )[0],
            outside_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE]
            )[0],
            internal_ambient_temperature=(
                PasdConversionUtility.scale_signed_16bit(
                    [FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE]
                )[0]
            ),
        )

        for smartbox_number in range(1, 25):
            # smartbox ports current trip thresholds
            mock_callbacks.assert_call(
                f"pasd_device_state_for_smartbox{smartbox_number}",
                fem1_current_trip_threshold=(
                    smartbox_simulator.fem1_current_trip_threshold
                ),
                fem2_current_trip_threshold=(
                    smartbox_simulator.fem2_current_trip_threshold
                ),
                fem3_current_trip_threshold=(
                    smartbox_simulator.fem3_current_trip_threshold
                ),
                fem4_current_trip_threshold=(
                    smartbox_simulator.fem4_current_trip_threshold
                ),
                fem5_current_trip_threshold=(
                    smartbox_simulator.fem5_current_trip_threshold
                ),
                fem6_current_trip_threshold=(
                    smartbox_simulator.fem6_current_trip_threshold
                ),
                fem7_current_trip_threshold=(
                    smartbox_simulator.fem7_current_trip_threshold
                ),
                fem8_current_trip_threshold=(
                    smartbox_simulator.fem8_current_trip_threshold
                ),
                fem9_current_trip_threshold=(
                    smartbox_simulator.fem9_current_trip_threshold
                ),
                fem10_current_trip_threshold=(
                    smartbox_simulator.fem10_current_trip_threshold
                ),
                fem11_current_trip_threshold=(
                    smartbox_simulator.fem11_current_trip_threshold
                ),
                fem12_current_trip_threshold=(
                    smartbox_simulator.fem12_current_trip_threshold
                ),
            )

        for smartbox_number in range(1, 25):
            # Then the smartbox status info
            mock_callbacks[
                f"pasd_device_state_for_smartbox{smartbox_number}"
            ].assert_call(
                uptime=Anything,
                sys_address=smartbox_number,
                status="OK",
                led_pattern="service: OFF, status: OFF",
                input_voltage=PasdConversionUtility.scale_volts(
                    [SmartboxSimulator.DEFAULT_INPUT_VOLTAGE]
                )[0],
                power_supply_output_voltage=(
                    PasdConversionUtility.scale_volts(
                        [SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE]
                    )[0]
                ),
                power_supply_temperature=PasdConversionUtility.scale_signed_16bit(
                    [SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE]
                )[0],
                pcb_temperature=PasdConversionUtility.scale_signed_16bit(
                    [SmartboxSimulator.DEFAULT_PCB_TEMPERATURE]
                )[0],
                fem_ambient_temperature=PasdConversionUtility.scale_signed_16bit(
                    [SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE]
                )[0],
                fem_case_temperatures=(
                    PasdConversionUtility.scale_signed_16bit(
                        SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES
                    )
                ),
                fem_heatsink_temperatures=(
                    PasdConversionUtility.scale_signed_16bit(
                        SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
                    )
                ),
                lookahead=25,
            )

        expected_fndh_ports_powered = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_config in pasd_config["pasd"]["smartboxes"].values():
            expected_fndh_ports_powered[smartbox_config["fndh_port"] - 1] = True

        # Then FNDH port status info
        mock_callbacks.assert_call(
            "pasd_device_state_for_fndh",
            port_forcings=["NONE"] * FndhSimulator.NUMBER_OF_PORTS,
            ports_desired_power_when_online=expected_fndh_ports_powered,
            ports_desired_power_when_offline=expected_fndh_ports_powered,
            ports_power_sensed=expected_fndh_ports_powered,
            lookahead=25,
        )
        # and FNDH warning and alarm flags
        mock_callbacks.assert_call(
            "pasd_device_state_for_fndh",
            warning_flags=FndhSimulator.DEFAULT_FLAGS.name,
            lookahead=25,
        )
        mock_callbacks.assert_call(
            "pasd_device_state_for_fndh",
            alarm_flags=FndhSimulator.DEFAULT_FLAGS.name,
            lookahead=25,
        )

        for smartbox_number in range(1, 25):
            mock_callbacks.assert_call(
                f"pasd_device_state_for_smartbox{smartbox_number}",
                port_forcings=["NONE"] * SmartboxSimulator.NUMBER_OF_PORTS,
                port_breakers_tripped=[False] * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_desired_power_when_online=[False]
                * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_desired_power_when_offline=[False]
                * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_power_sensed=[False] * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_current_draw=[0] * SmartboxSimulator.NUMBER_OF_PORTS,
                lookahead=25,
            )
            # and smartbox warning and alarm flags
            mock_callbacks.assert_call(
                f"pasd_device_state_for_smartbox{smartbox_number}",
                warning_flags=SmartboxSimulator.DEFAULT_FLAGS.name,
                lookahead=25,
            )
            mock_callbacks.assert_call(
                f"pasd_device_state_for_smartbox{smartbox_number}",
                alarm_flags=SmartboxSimulator.DEFAULT_FLAGS.name,
                lookahead=50,
            )

        # TODO: Once we have a poller, extend this test to cover spontaneous changes
        # in the simulator

        pasd_bus_component_manager.stop_communicating()

        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["component_state"].assert_call(
            power=PowerState.UNKNOWN, fault=None
        )

    def test_set_fndh_port_powers(
        self: TestPasdBusComponentManager,
        fndh_simulator: FndhSimulator,
        pasd_bus_component_manager: PasdBusComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test that the PaSD bus component manager can turn ports on and off.

        :param fndh_simulator: the FNDH simulator under test
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test.
        :param mock_callbacks: a group of mock callables for the component
            manager under test to use as callbacks
        """
        mock_callbacks.assert_not_called()
        pasd_bus_component_manager.start_communicating()
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.ESTABLISHED
        )
        mock_callbacks.assert_call("component_state", power=PowerState.ON, fault=False)

        # FNDH reads comprise two initial reads, then a cycle of four.
        # Let's wait for six calls before proceeding.
        # These are fully unpacked in test_attribute_updates,
        # so there's no need for us to unpack them again
        for _ in range(6):
            mock_callbacks["pasd_device_state_for_fndh"].assert_against_call()

        pasd_bus_component_manager.initialize_fndh()

        ports_connected = fndh_simulator.ports_connected
        port_forcings = fndh_simulator.port_forcings

        for i in range(1, 5):
            print(f"\nTest iteration {i}")
            ports_desired_power_when_online = (
                fndh_simulator.ports_desired_power_when_online
            )
            ports_desired_power_when_offline = (
                fndh_simulator.ports_desired_power_when_offline
            )

            desired_port_powers: list[bool | None] = random.choices(
                [True, False, None], k=len(ports_connected)
            )
            desired_stay_on_when_offline = random.choice([True, False])

            print(f"{ports_desired_power_when_online=}")
            print(f"{ports_desired_power_when_offline=}")
            print(f"{desired_port_powers=}")
            print(f"{desired_stay_on_when_offline=}")

            expected_desired_power_when_online: list[bool | None] = list(
                ports_desired_power_when_online
            )
            expected_desired_power_when_offline: list[bool | None] = list(
                ports_desired_power_when_offline
            )

            for i, desired in enumerate(desired_port_powers):
                if desired is None:
                    continue
                expected_desired_power_when_online[i] = desired_port_powers[i]
                expected_desired_power_when_offline[i] = (
                    desired_port_powers[i] and desired_stay_on_when_offline
                )
            expected_ports_power_sensed = list(expected_desired_power_when_online)

            pasd_bus_component_manager.set_fndh_port_powers(
                desired_port_powers, desired_stay_on_when_offline
            )

            mock_callbacks["pasd_device_state_for_fndh"].assert_call(
                port_forcings=port_forcings,
                ports_desired_power_when_online=expected_desired_power_when_online,
                ports_desired_power_when_offline=expected_desired_power_when_offline,
                ports_power_sensed=expected_ports_power_sensed,
                lookahead=11,  # Full cycle plus one to cover off on race conditions
            )

    def test_smartbox_port_power_commands(  # pylint: disable=too-many-locals
        self: TestPasdBusComponentManager,
        smartbox_simulator: SmartboxSimulator,
        smartbox_id: int,
        pasd_bus_component_manager: PasdBusComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test that the component manager can turn smartbox ports on and off.

        :param smartbox_simulator: the smartbox simulator under test.
        :param smartbox_id: id of the smartbox being addressed.
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test.
        :param mock_callbacks: a group of mock callables for the component
            manager under test to use as callbacks
        """
        mock_callbacks.assert_not_called()
        pasd_bus_component_manager.start_communicating()
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.ESTABLISHED
        )
        mock_callbacks.assert_call("component_state", power=PowerState.ON, fault=False)

        # Smartbox reads comprise three initial reads, then a cycle of four.
        # Let's wait for seven calls before proceeding.
        # These are fully unpacked in test_attribute_updates,
        # so there's no need for us to unpack them again
        for _ in range(7):
            mock_callbacks[
                f"pasd_device_state_for_smartbox{smartbox_id}"
            ].assert_against_call()

        pasd_bus_component_manager.initialize_smartbox(smartbox_id)

        ports_connected = smartbox_simulator.ports_connected
        port_forcings = smartbox_simulator.port_forcings
        port_breakers_tripped = smartbox_simulator.port_breakers_tripped

        print(f"{ports_connected=}")

        for i in range(1, 5):
            print(f"Test iteration {i}")
            ports_desired_power_when_online = (
                smartbox_simulator.ports_desired_power_when_online
            )
            ports_desired_power_when_offline = (
                smartbox_simulator.ports_desired_power_when_offline
            )

            desired_port_powers: list[bool | None] = random.choices(
                [True, False, None], k=len(ports_connected)
            )
            desired_stay_on_when_offline = random.choice([True, False])

            print(f"{ports_desired_power_when_online=}")
            print(f"{ports_desired_power_when_offline=}")
            print(f"{desired_port_powers=}")
            print(f"{desired_stay_on_when_offline=}")

            expected_desired_power_when_online: list[bool | None] = list(
                ports_desired_power_when_online
            )
            expected_desired_power_when_offline: list[bool | None] = list(
                ports_desired_power_when_offline
            )

            for i, desired in enumerate(desired_port_powers):
                if desired is None:
                    continue
                expected_desired_power_when_online[i] = desired_port_powers[i]
                expected_desired_power_when_offline[i] = (
                    desired_port_powers[i] and desired_stay_on_when_offline
                )
            expected_ports_current_draw = [
                SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW if s and c else 0.0
                for s, c in zip(expected_desired_power_when_online, ports_connected)
            ]

            pasd_bus_component_manager.set_smartbox_port_powers(
                smartbox_id, desired_port_powers, desired_stay_on_when_offline
            )

            mock_callbacks[f"pasd_device_state_for_smartbox{smartbox_id}"].assert_call(
                port_forcings=port_forcings,
                port_breakers_tripped=port_breakers_tripped,
                ports_desired_power_when_online=expected_desired_power_when_online,
                ports_desired_power_when_offline=expected_desired_power_when_offline,
                ports_power_sensed=expected_desired_power_when_online,
                ports_current_draw=expected_ports_current_draw,
                lookahead=11,  # Full cycle plus one to cover off on race conditions
            )

    def test_led_pattern(
        self: TestPasdBusComponentManager,
        pasd_bus_component_manager: PasdBusComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test the component manager can set FNDH and smartbox LED patterns.

        :param pasd_bus_component_manager: the PaSD bus component
            manager under test.
        :param mock_callbacks: a group of mock callables for the component
            manager under test to use as callbacks
        """
        mock_callbacks.assert_not_called()
        pasd_bus_component_manager.start_communicating()
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.NOT_ESTABLISHED
        )
        mock_callbacks.assert_call(
            "communication_state", CommunicationStatus.ESTABLISHED
        )
        mock_callbacks.assert_call("component_state", power=PowerState.ON, fault=False)

        # FNDH reads comprise two initial reads, then a cycle of four.
        # Let's wait for six calls before proceeding.
        # These are fully unpacked in test_attribute_updates,
        # so there's no need for us to unpack them again
        for _ in range(6):
            mock_callbacks["pasd_device_state_for_fndh"].assert_against_call()

        pasd_bus_component_manager.set_fndh_led_pattern("SERVICE")

        mock_callbacks["pasd_device_state_for_fndh"].assert_call(
            uptime=Anything,
            sys_address=FndhSimulator.SYS_ADDRESS,
            status="OK",
            led_pattern="service: ON, status: OFF",
            psu48v_voltages=PasdConversionUtility.scale_volts(
                FndhSimulator.DEFAULT_PSU48V_VOLTAGES
            ),
            psu48v_current=PasdConversionUtility.scale_48vcurrents(
                [FndhSimulator.DEFAULT_PSU48V_CURRENT]
            )[0],
            psu48v_temperatures=PasdConversionUtility.scale_signed_16bit(
                FndhSimulator.DEFAULT_PSU48V_TEMPERATURES
            ),
            panel_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_PANEL_TEMPERATURE]
            )[0],
            fncb_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_FNCB_TEMPERATURE]
            )[0],
            fncb_humidity=FndhSimulator.DEFAULT_FNCB_HUMIDITY,
            comms_gateway_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE]
            )[0],
            power_module_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE]
            )[0],
            outside_temperature=PasdConversionUtility.scale_signed_16bit(
                [FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE]
            )[0],
            internal_ambient_temperature=(
                PasdConversionUtility.scale_signed_16bit(
                    [FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE]
                )[0]
            ),
            lookahead=5,  # Full cycle plus one to cover off on race conditions
        )

        smartbox_number = 4

        # Smartbox reads comprise three initial reads, then a cycle of four.
        # Let's wait for seven calls before proceeding.
        # These are fully unpacked in test_attribute_updates,
        # so there's no need for us to unpack them again
        for _ in range(7):
            mock_callbacks[
                f"pasd_device_state_for_smartbox{smartbox_number}"
            ].assert_against_call()

        pasd_bus_component_manager.set_smartbox_led_pattern(smartbox_number, "SERVICE")

        mock_callbacks[f"pasd_device_state_for_smartbox{smartbox_number}"].assert_call(
            uptime=Anything,
            sys_address=smartbox_number,
            status=SmartboxSimulator.DEFAULT_STATUS.name,
            led_pattern="service: ON, status: OFF",
            input_voltage=PasdConversionUtility.scale_volts(
                [SmartboxSimulator.DEFAULT_INPUT_VOLTAGE]
            )[0],
            power_supply_output_voltage=(
                PasdConversionUtility.scale_volts(
                    [SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE]
                )[0]
            ),
            power_supply_temperature=PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE]
            )[0],
            pcb_temperature=PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_PCB_TEMPERATURE]
            )[0],
            fem_ambient_temperature=PasdConversionUtility.scale_signed_16bit(
                [SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE]
            )[0],
            fem_case_temperatures=(
                PasdConversionUtility.scale_signed_16bit(
                    SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES
                )
            ),
            fem_heatsink_temperatures=(
                PasdConversionUtility.scale_signed_16bit(
                    SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
                )
            ),
            lookahead=5,  # Full cycle plus one to cover off on race conditions
        )
