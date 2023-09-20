# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus component manager."""
from __future__ import annotations

from ska_control_model import CommunicationStatus, PowerState
from ska_tango_testing.mock import MockCallableGroup
from ska_tango_testing.mock.placeholders import Anything

from ska_low_mccs_pasd.pasd_bus import PasdBusComponentManager
from ska_low_mccs_pasd.pasd_bus.pasd_bus_simulator import (
    FndhSimulator,
    SmartboxSimulator,
)


class TestPasdBusComponentManager:
    """
    Tests of commands common to the PaSDBus simulator and its component manager.

    Because the PaSD bus component manager passes commands down to the
    PaSD bus simulator, many commands are common. Here we test those
    common commands.
    """

    def test_attribute_updates(
        self: TestPasdBusComponentManager,
        pasd_config: dict,
        pasd_bus_component_manager: PasdBusComponentManager,
        mock_callbacks: MockCallableGroup,
    ) -> None:
        """
        Test that the PaSD bus component manager receives updated values.

        :param pasd_config: a dictionary of PaSD configuration data with
            which the PaSD under test was configured.
        :param pasd_bus_component_manager: the PaSD bus component
            manager under test.
        :param mock_callbacks: dictionary of driver callbacks.
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
        # First we'll receive static info about the FNDH
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            modbus_register_map_revision=FndhSimulator.MODBUS_REGISTER_MAP_REVISION,
            pcb_revision=FndhSimulator.PCB_REVISION,
            cpu_id=FndhSimulator.CPU_ID,
            chip_id=FndhSimulator.CHIP_ID,
            firmware_version=FndhSimulator.DEFAULT_FIRMWARE_VERSION,
        )

        # Then static info about each of the smartboxes
        for smartbox_number in range(1, 25):
            pasd_bus_component_manager.initialize_smartbox(smartbox_number)
            mock_callbacks.assert_call(
                "pasd_device_state",
                smartbox_number,
                modbus_register_map_revision=(
                    SmartboxSimulator.MODBUS_REGISTER_MAP_REVISION
                ),
                pcb_revision=SmartboxSimulator.PCB_REVISION,
                cpu_id=SmartboxSimulator.CPU_ID,
                chip_id=SmartboxSimulator.CHIP_ID,
                firmware_version=SmartboxSimulator.DEFAULT_FIRMWARE_VERSION,
            )

        # Then FNDH status info
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            uptime=Anything,
            sys_address=FndhSimulator.SYS_ADDRESS,
            status="OK",
            led_pattern=FndhSimulator.DEFAULT_LED_PATTERN,
            psu48v_voltages=FndhSimulator.DEFAULT_PSU48V_VOLTAGES,
            psu48v_current=FndhSimulator.DEFAULT_PSU48V_CURRENT,
            psu48v_temperatures=FndhSimulator.DEFAULT_PSU48V_TEMPERATURES,
            panel_temperature=FndhSimulator.DEFAULT_PANEL_TEMPERATURE,
            fncb_temperature=FndhSimulator.DEFAULT_FNCB_TEMPERATURE,
            fncb_humidity=FndhSimulator.DEFAULT_FNCB_HUMIDITY,
            comms_gateway_temperature=FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE,
            power_module_temperature=FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE,
            outside_temperature=FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE,
            internal_ambient_temperature=(
                FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE
            ),
        )

        expected_fndh_ports_powered = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_config in pasd_config["pasd"]["smartboxes"].values():
            expected_fndh_ports_powered[smartbox_config["fndh_port"] - 1] = True

        # Then FNDH port status info
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            port_forcings=["NONE"] * FndhSimulator.NUMBER_OF_PORTS,
            ports_desired_power_when_online=expected_fndh_ports_powered,
            ports_desired_power_when_offline=expected_fndh_ports_powered,
            ports_power_sensed=expected_fndh_ports_powered,
        )

        for smartbox_number in range(1, 25):
            mock_callbacks.assert_call(
                "pasd_device_state",
                smartbox_number,
                uptime=Anything,
                sys_address=SmartboxSimulator.DEFAULT_SYS_ADDRESS,
                status="OK",
                led_pattern=SmartboxSimulator.DEFAULT_LED_PATTERN,
                input_voltage=SmartboxSimulator.DEFAULT_INPUT_VOLTAGE,
                power_supply_output_voltage=(
                    SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
                ),
                power_supply_temperature=(
                    SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
                ),
                pcb_temperature=SmartboxSimulator.DEFAULT_PCB_TEMPERATURE,
                fem_ambient_temperature=(
                    SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE
                ),
                fem_case_temperatures=(SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES),
                fem_heatsink_temperatures=(
                    SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
                ),
            )

            mock_callbacks.assert_call(
                "pasd_device_state",
                smartbox_number,
                port_forcings=["NONE"] * SmartboxSimulator.NUMBER_OF_PORTS,
                port_breakers_tripped=[False] * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_desired_power_when_online=[False]
                * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_desired_power_when_offline=[False]
                * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_power_sensed=[False] * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_current_draw=[0] * SmartboxSimulator.NUMBER_OF_PORTS,
            )

        # TODO: Once we have a poller, extend this test to cover spontaneous changes
        # in the simulator

        pasd_bus_component_manager.stop_communicating()

        mock_callbacks["communication_state"].assert_call(CommunicationStatus.DISABLED)
        mock_callbacks["component_state"].assert_call(
            power=PowerState.UNKNOWN, fault=None
        )

    def test_fndh_port_power_commands(
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
        :param mock_callbacks: dictionary of driver callbacks.
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

        # Three calls per device (1 FNDH and 24 subracks).
        # These are fully unpacked in the above test.
        # There's no need for us to unpack them again
        for _ in range(75):
            mock_callbacks.assert_against_call("pasd_device_state")

        pasd_bus_component_manager.initialize_fndh()
        ports_connected = fndh_simulator.ports_connected
        expected_port_forcings = fndh_simulator.port_forcings
        expected_ports_desired_power_when_online = (
            fndh_simulator.ports_desired_power_when_online
        )
        expected_ports_desired_power_when_offline = (
            fndh_simulator.ports_desired_power_when_offline
        )
        expected_ports_power_sensed = fndh_simulator.ports_power_sensed

        connected_port = ports_connected.index(True) + 1

        pasd_bus_component_manager.turn_fndh_port_on(connected_port, True)
        expected_ports_desired_power_when_online[connected_port - 1] = True
        expected_ports_desired_power_when_offline[connected_port - 1] = True
        expected_ports_power_sensed[connected_port - 1] = True

        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            port_forcings=expected_port_forcings,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
            lookahead=75,
        )

        # TODO: Once we have a poller, we can simulate port forcing,
        # and breaker tripping and resetting here.

        pasd_bus_component_manager.turn_fndh_port_off(connected_port)
        expected_ports_desired_power_when_online[connected_port - 1] = False
        expected_ports_desired_power_when_offline[connected_port - 1] = False
        expected_ports_power_sensed[connected_port - 1] = False

        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            port_forcings=expected_port_forcings,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
            lookahead=75,
        )

        pasd_bus_component_manager.turn_all_fndh_ports_on(True)
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            port_forcings=expected_port_forcings,
            ports_desired_power_when_online=[True] * 28,
            ports_desired_power_when_offline=[True] * 28,
            ports_power_sensed=[True] * 28,
            lookahead=100,
        )

        pasd_bus_component_manager.turn_all_fndh_ports_off()
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            port_forcings=expected_port_forcings,
            ports_desired_power_when_online=[False] * 28,
            ports_desired_power_when_offline=[False] * 28,
            ports_power_sensed=[False] * 28,
            lookahead=150,
        )

    def test_smartbox_port_power_commands(
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
        :param mock_callbacks: dictionary of driver callbacks.
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

        # Three calls per device (1 FNDH and 24 subracks).
        # These are fully unpacked in the above test.
        # There's no need for us to unpack them again
        for _ in range(75):
            mock_callbacks.assert_against_call("pasd_device_state")

        pasd_bus_component_manager.initialize_smartbox(smartbox_id)
        ports_connected = smartbox_simulator.ports_connected
        expected_ports_current_draw = smartbox_simulator.ports_current_draw
        expected_port_forcings = smartbox_simulator.port_forcings
        expected_port_breakers_tripped = smartbox_simulator.port_breakers_tripped
        expected_ports_desired_power_when_online = (
            smartbox_simulator.ports_desired_power_when_online
        )
        expected_ports_desired_power_when_offline = (
            smartbox_simulator.ports_desired_power_when_offline
        )
        expected_ports_power_sensed = smartbox_simulator.ports_power_sensed

        connected_port = ports_connected.index(True) + 1

        pasd_bus_component_manager.turn_smartbox_port_on(
            smartbox_id, connected_port, True
        )
        expected_ports_desired_power_when_online[connected_port - 1] = True
        expected_ports_desired_power_when_offline[connected_port - 1] = True
        expected_ports_power_sensed[connected_port - 1] = True
        expected_ports_current_draw[
            connected_port - 1
        ] = SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW

        mock_callbacks.assert_call(
            "pasd_device_state",
            smartbox_id,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
            ports_current_draw=expected_ports_current_draw,
            lookahead=75,
        )

        # TODO: Once we have a poller, we can simulate port forcing,
        # and breaker tripping and resetting here.

        pasd_bus_component_manager.turn_smartbox_port_off(smartbox_id, connected_port)
        expected_ports_desired_power_when_online[connected_port - 1] = False
        expected_ports_desired_power_when_offline[connected_port - 1] = False
        expected_ports_power_sensed[connected_port - 1] = False
        expected_ports_current_draw[connected_port - 1] = 0

        mock_callbacks.assert_call(
            "pasd_device_state",
            smartbox_id,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
            ports_current_draw=expected_ports_current_draw,
            lookahead=75,
        )

        pasd_bus_component_manager.turn_all_smartbox_ports_on(smartbox_id, True)

        expected_ports_current_draw = [
            SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW * p for p in ports_connected
        ]

        mock_callbacks.assert_call(
            "pasd_device_state",
            smartbox_id,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=[True] * 12,
            ports_desired_power_when_offline=[True] * 12,
            ports_power_sensed=[True] * 12,
            ports_current_draw=expected_ports_current_draw,
            lookahead=125,
        )

        pasd_bus_component_manager.turn_all_smartbox_ports_off(smartbox_id)
        mock_callbacks.assert_call(
            "pasd_device_state",
            smartbox_id,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=[False] * 12,
            ports_desired_power_when_offline=[False] * 12,
            ports_power_sensed=[False] * 12,
            ports_current_draw=[0.0] * 12,
            lookahead=175,
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
        :param mock_callbacks: dictionary of driver callbacks.
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

        # Three calls per device (1 FNDH and 24 subracks).
        # These are fully unpacked in the above test.
        # There's no need for us to unpack them again
        for _ in range(75):
            mock_callbacks.assert_against_call("pasd_device_state")

        pasd_bus_component_manager.set_fndh_led_pattern("SERVICE")

        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            uptime=Anything,
            sys_address=FndhSimulator.SYS_ADDRESS,
            status="OK",
            led_pattern="SERVICE",
            psu48v_voltages=FndhSimulator.DEFAULT_PSU48V_VOLTAGES,
            psu48v_current=FndhSimulator.DEFAULT_PSU48V_CURRENT,
            psu48v_temperatures=FndhSimulator.DEFAULT_PSU48V_TEMPERATURES,
            panel_temperature=FndhSimulator.DEFAULT_PANEL_TEMPERATURE,
            fncb_temperature=FndhSimulator.DEFAULT_FNCB_TEMPERATURE,
            fncb_humidity=FndhSimulator.DEFAULT_FNCB_HUMIDITY,
            comms_gateway_temperature=FndhSimulator.DEFAULT_COMMS_GATEWAY_TEMPERATURE,
            power_module_temperature=FndhSimulator.DEFAULT_POWER_MODULE_TEMPERATURE,
            outside_temperature=FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE,
            internal_ambient_temperature=(
                FndhSimulator.DEFAULT_INTERNAL_AMBIENT_TEMPERATURE
            ),
            lookahead=75,
        )

        pasd_bus_component_manager.set_smartbox_led_pattern(4, "SERVICE")

        mock_callbacks.assert_call(
            "pasd_device_state",
            4,
            uptime=Anything,
            sys_address=SmartboxSimulator.DEFAULT_SYS_ADDRESS,
            status=SmartboxSimulator.DEFAULT_STATUS,
            led_pattern="SERVICE",
            input_voltage=SmartboxSimulator.DEFAULT_INPUT_VOLTAGE,
            power_supply_output_voltage=(
                SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
            ),
            power_supply_temperature=SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE,
            pcb_temperature=SmartboxSimulator.DEFAULT_PCB_TEMPERATURE,
            fem_ambient_temperature=SmartboxSimulator.DEFAULT_FEM_AMBIENT_TEMPERATURE,
            fem_case_temperatures=(SmartboxSimulator.DEFAULT_FEM_CASE_TEMPERATURES),
            fem_heatsink_temperatures=(
                SmartboxSimulator.DEFAULT_FEM_HEATSINK_TEMPERATURES
            ),
            lookahead=75,
        )
