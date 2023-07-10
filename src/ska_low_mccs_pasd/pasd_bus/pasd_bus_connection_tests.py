"""Module to test the Pasd Modbus client API."""
from __future__ import annotations

import logging
import pprint

from ska_low_mccs_pasd.pasd_bus.pasd_bus_modbus_api import PasdBusModbusApiClient


# pylint: disable=too-few-public-methods
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


if __name__ == "__main__":
    conn = PasdBusConnectionTest("127.0.0.1", 5000)

    # conn.read(101, "status")

    # Read FNDH polling registers
    conn.read(
        101,
        "modbus_register_map_revision",
        "pcb_revision",
        "cpu_id",
        "chip_id",
        "firmware_version",
        "uptime",
        "sys_address",
        "psu48v_voltages",
        "psu48v_current",
        "psu48v_temperature",
        "pcb_temperature",
        "fncb_temperature",
        "humidity",
        "status",
        "led_pattern",
    )

    # # Port status:
    # conn.read(
    #     101,
    #     "port_forcings",
    #     "port_breakers_tripped",
    #     "ports_desired_power_when_online",
    #     "ports_desired_power_when_offline",
    #     "ports_power_sensed",
    # )

    # # Smart box on port 1
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
        "psu_temperature",
        "pcb_temperature",
        "outside_temperature",
        "status",
        "led_pattern",
    )

    # Port status:
    # conn.read(
    #     1,
    #     "port_forcings",
    #     "port_breakers_tripped",
    #     "ports_desired_power_when_online",
    #     "ports_desired_power_when_offline",
    #     "ports_power_sensed",
    #     "ports_current_draw",
    # )
