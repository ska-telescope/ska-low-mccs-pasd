# pylint: disable-all
# flake8: noqa
""" Module to test the Pasd Modbus client"""
from __future__ import annotations

import logging
import pprint

from ska_ser_devices.client_server import (
    ApplicationClient,
    SentinelBytesMarshaller,
    TcpClient,
)

from ska_low_mccs_pasd.pasd_bus.pasd_bus_modbus_api import PasdBusModbusApiClient


class PasdBusConnectionTest:
    """Class to test the PaSD comms by directly using the Modbus API client"""

    def __init__(
        self: PasdBusConnectionTest, host: str, port: int, timeout: int
    ) -> None:
        tcp_client = TcpClient(host, port, timeout)
        marshaller = SentinelBytesMarshaller(b"\n")
        application_client = ApplicationClient(
            tcp_client, marshaller.marshall, marshaller.unmarshall
        )
        logging.basicConfig()
        self._pasd_bus_api_client = PasdBusModbusApiClient(
            application_client, logging.DEBUG
        )

    def read(self: PasdBusConnectionTest, address: int, *attributes: str) -> None:
        results = self._pasd_bus_api_client.read_attributes(address, *attributes)
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(results)


if __name__ == "__main__":
    conn = PasdBusConnectionTest("127.0.0.1", 5000, 5)

    # Read FNDH polling registers
    # conn.read(101, "modbus_register_map_revision", "pcb_revision", "cpu_id", "chip_id", "firmware_version", "uptime", "sys_address", "psu48v_voltages", "psu48v_current", "psu48v_temperature", "pcb_temperature", "outside_temperature", "humidity", "status", "led_pattern")
    conn.read(101, "cpu_id")

    # Smart box on port 1
    # conn.read(1, "modbus_register_map_revision", "pcb_revision", "cpu_id", "chip_id", "firmware_version", "uptime", "sys_address", "input_voltage", "power_supply_output_voltage", "psu_temperature", "pcb_temperature", "outside_temperature", "status", "led_pattern")

    # Smart box on port 2
    # conn.read(2, "modbus_register_map_revision", "pcb_revision", "cpu_id", "chip_id", "firmware_version", "uptime", "sys_address", "input_voltage", "power_supply_output_voltage", "psu_temperature", "pcb_temperature", "outside_temperature", "status", "led_pattern")
