"""Module to test the Pasd Modbus client API."""
from __future__ import annotations

import logging
import pprint
from typing import Any

from ska_low_mccs_pasd.pasd_bus.pasd_bus_modbus_api import PasdBusModbusApiClient


class PasdBusConnectionTest:
    """Class to test the PaSD comms by directly using the Modbus API client."""

    def __init__(self: PasdBusConnectionTest, host: str, port: int) -> None:
        """Initialize a new instance.

        :param host: Host name of the device to connect to
        :param port: Port number
        """
        logging.basicConfig()
        self._pasd_bus_api_client = PasdBusModbusApiClient(host, port, logging.DEBUG)

    def read(self: PasdBusConnectionTest, address: int, *attributes: str) -> None:
        """Read the requested attributes and print out the results.

        :param address: Modbus slave address
        :param attributes: name of the attribute(s) to read
        """
        results = self._pasd_bus_api_client.read_attributes(address, *attributes)
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(results)

    def execute_command(
        self: PasdBusConnectionTest, address: int, command: str, *arguments: Any
    ) -> None:
        """Execute the requested command.

        :param address: Modbus slave address
        :param command: name of the command to send
        :param arguments: optional arguments to be passed with the command
        """
        succeeded = self._pasd_bus_api_client.execute_command(
            address, command, *arguments
        )
        if succeeded:
            print("Command executed successfully")


if __name__ == "__main__":
    conn = PasdBusConnectionTest("127.0.0.1", 5000)

    # conn.execute_command(101, "turn_port_on", 3, True)
    # conn.execute_command(101, "reset_port_breaker", 3)
    # conn.execute_command(1, "set_led_pattern", "OFF")
    # conn.execute_command(1, "turn_port_off", 1)
    # conn.execute_command(1, "turn_port_on")
    # conn.execute_command(1, "turn_port_on", 2, True)

    # Read FNDH polling registers
    conn.read(
        0,
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
        "uptime",
        "sys_address",
        "psu48v_voltages",
        "psu48v_current",
        "psu48v_temperatures",
        "pcb_temperature",
        "fncb_temperature",
        "humidity",
        "status",
        "led_pattern",
    )

    # #Port status:
    # conn.read(
    #     0,
    #     "port_forcings",
    #     "port_breakers_tripped",
    #     "ports_desired_power_when_online",
    #     "ports_desired_power_when_offline",
    #     "ports_power_sensed",
    # )

    # # # Smart box on port 1
    conn.read(
        1,
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
        "uptime",
        "sys_address",
        "input_voltage",
        "power_supply_output_voltage",
        "power_supply_temperature",
        "pcb_temperature",
        "outside_temperature",
        "status",
        "led_pattern",
    )

    # # # Port status:
    # conn.read(
    #     1,
    #     "port_forcings",
    #     "port_breakers_tripped",
    #     "ports_desired_power_when_online",
    #     "ports_desired_power_when_offline",
    #     "ports_power_sensed",
    #     "ports_current_draw",
    # )
