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

        mock_callbacks["communication_state"].assert_not_called()
        mock_callbacks["component_state"].assert_not_called()

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

        # Then FNDH status info
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            uptime=FndhSimulator.DEFAULT_UPTIME,
            status=FndhSimulator.DEFAULT_STATUS,
            led_pattern=FndhSimulator.DEFAULT_LED_PATTERN,
            psu48v_voltages=FndhSimulator.DEFAULT_PSU48V_VOLTAGES,
            psu5v_voltage=FndhSimulator.DEFAULT_PSU5V_VOLTAGE,
            psu48v_current=FndhSimulator.DEFAULT_PSU48V_CURRENT,
            psu48v_temperature=FndhSimulator.DEFAULT_PSU48V_TEMPERATURE,
            psu5v_temperature=FndhSimulator.DEFAULT_PSU5V_TEMPERATURE,
            pcb_temperature=FndhSimulator.DEFAULT_PCB_TEMPERATURE,
            outside_temperature=FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE,
        )

        expected_fndh_ports_connected = [False] * FndhSimulator.NUMBER_OF_PORTS
        for smartbox_config in pasd_config["smartboxes"]:
            expected_fndh_ports_connected[smartbox_config["fndh_port"] - 1] = True

        # Then FNDH port status info
        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            ports_connected=expected_fndh_ports_connected,
            port_forcings=["NONE"] * FndhSimulator.NUMBER_OF_PORTS,
            port_breakers_tripped=[False] * FndhSimulator.NUMBER_OF_PORTS,
            ports_desired_power_when_online=[False] * FndhSimulator.NUMBER_OF_PORTS,
            ports_desired_power_when_offline=[False] * FndhSimulator.NUMBER_OF_PORTS,
            ports_power_sensed=[False] * FndhSimulator.NUMBER_OF_PORTS,
        )

        for smartbox_number in range(1, 25):
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
            mock_callbacks.assert_call(
                "pasd_device_state",
                smartbox_number,
                uptime=SmartboxSimulator.DEFAULT_UPTIME,
                status=SmartboxSimulator.DEFAULT_STATUS,
                led_pattern=SmartboxSimulator.DEFAULT_LED_PATTERN,
                input_voltage=SmartboxSimulator.DEFAULT_INPUT_VOLTAGE,
                power_supply_output_voltage=(
                    SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
                ),
                power_supply_temperature=(
                    SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE
                ),
                outside_temperature=SmartboxSimulator.DEFAULT_OUTSIDE_TEMPERATURE,
                pcb_temperature=SmartboxSimulator.DEFAULT_PCB_TEMPERATURE,
            )

            expected_smartbox_ports_connected = [
                False
            ] * SmartboxSimulator.NUMBER_OF_PORTS
            for antenna_config in pasd_config["antennas"]:
                if antenna_config["smartbox_id"] != smartbox_number:
                    continue
                smartbox_port = antenna_config["smartbox_port"]
                expected_smartbox_ports_connected[smartbox_port - 1] = True

            mock_callbacks.assert_call(
                "pasd_device_state",
                smartbox_number,
                ports_connected=expected_smartbox_ports_connected,
                port_forcings=["NONE"] * SmartboxSimulator.NUMBER_OF_PORTS,
                port_breakers_tripped=[False] * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_desired_power_when_online=[False]
                * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_desired_power_when_offline=[False]
                * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_power_sensed=[False] * SmartboxSimulator.NUMBER_OF_PORTS,
                ports_current_draw=[
                    SmartboxSimulator.DEFAULT_PORT_CURRENT_DRAW if connected else 0.0
                    for connected in expected_smartbox_ports_connected
                ],
            )

        # TODO: Once we have a poller, extend this test to cover spontaneous changes
        # in the simulator

        mock_callbacks.assert_not_called()

        pasd_bus_component_manager.stop_communicating()

        mock_callbacks.assert_call("communication_state", CommunicationStatus.DISABLED)
        mock_callbacks.assert_call("component_state", power=None, fault=None)
        mock_callbacks.assert_not_called()

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
        mock_callbacks.assert_not_called()

        ports_connected = fndh_simulator.ports_connected
        expected_port_forcings = fndh_simulator.port_forcings
        expected_port_breakers_tripped = fndh_simulator.port_breakers_tripped
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
            ports_connected=ports_connected,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
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
            ports_connected=ports_connected,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
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
        mock_callbacks.assert_not_called()

        ports_current_draw = smartbox_simulator.ports_current_draw
        ports_connected = smartbox_simulator.ports_connected
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

        mock_callbacks.assert_call(
            "pasd_device_state",
            smartbox_id,
            ports_connected=ports_connected,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
            ports_current_draw=ports_current_draw,
        )

        # TODO: Once we have a poller, we can simulate port forcing,
        # and breaker tripping and resetting here.

        pasd_bus_component_manager.turn_smartbox_port_off(smartbox_id, connected_port)
        expected_ports_desired_power_when_online[connected_port - 1] = False
        expected_ports_desired_power_when_offline[connected_port - 1] = False
        expected_ports_power_sensed[connected_port - 1] = False

        mock_callbacks.assert_call(
            "pasd_device_state",
            smartbox_id,
            ports_connected=ports_connected,
            port_forcings=expected_port_forcings,
            port_breakers_tripped=expected_port_breakers_tripped,
            ports_desired_power_when_online=expected_ports_desired_power_when_online,
            ports_desired_power_when_offline=expected_ports_desired_power_when_offline,
            ports_power_sensed=expected_ports_power_sensed,
            ports_current_draw=ports_current_draw,
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
        mock_callbacks.assert_not_called()

        pasd_bus_component_manager.set_fndh_led_pattern("SERVICE")

        mock_callbacks.assert_call(
            "pasd_device_state",
            0,  # FNDH
            uptime=FndhSimulator.DEFAULT_UPTIME,
            status=FndhSimulator.DEFAULT_STATUS,
            led_pattern="SERVICE",
            psu48v_voltages=FndhSimulator.DEFAULT_PSU48V_VOLTAGES,
            psu5v_voltage=FndhSimulator.DEFAULT_PSU5V_VOLTAGE,
            psu48v_current=FndhSimulator.DEFAULT_PSU48V_CURRENT,
            psu48v_temperature=FndhSimulator.DEFAULT_PSU48V_TEMPERATURE,
            psu5v_temperature=FndhSimulator.DEFAULT_PSU5V_TEMPERATURE,
            pcb_temperature=FndhSimulator.DEFAULT_PCB_TEMPERATURE,
            outside_temperature=FndhSimulator.DEFAULT_OUTSIDE_TEMPERATURE,
        )

        pasd_bus_component_manager.set_smartbox_led_pattern(4, "SERVICE")

        mock_callbacks.assert_call(
            "pasd_device_state",
            4,
            uptime=SmartboxSimulator.DEFAULT_UPTIME,
            status=SmartboxSimulator.DEFAULT_STATUS,
            led_pattern="SERVICE",
            input_voltage=SmartboxSimulator.DEFAULT_INPUT_VOLTAGE,
            power_supply_output_voltage=(
                SmartboxSimulator.DEFAULT_POWER_SUPPLY_OUTPUT_VOLTAGE
            ),
            power_supply_temperature=SmartboxSimulator.DEFAULT_POWER_SUPPLY_TEMPERATURE,
            outside_temperature=SmartboxSimulator.DEFAULT_OUTSIDE_TEMPERATURE,
            pcb_temperature=SmartboxSimulator.DEFAULT_PCB_TEMPERATURE,
        )
