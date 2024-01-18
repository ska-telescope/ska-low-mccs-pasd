# -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Tests of the PasdBusModbusApi."""
from __future__ import annotations

import logging
from typing import Any, Generator
from unittest import mock

import pytest
from pymodbus.exceptions import ModbusIOException
from pymodbus.factory import ClientDecoder
from pymodbus.framer.ascii_framer import ModbusAsciiFramer
from pymodbus.pdu import ExceptionResponse, ModbusExceptions
from pymodbus.register_read_message import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
)
from pymodbus.register_write_message import (
    WriteMultipleRegistersRequest,
    WriteMultipleRegistersResponse,
)

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusModbusApi,
    PasdBusModbusApiClient,
    PasdHardwareSimulator,
    SmartboxSimulator,
)
from ska_low_mccs_pasd.pasd_bus.pasd_bus_conversions import (
    FndhStatusMap,
    LedServiceMap,
    LedStatusMap,
)
from ska_low_mccs_pasd.pasd_bus.pasd_bus_modbus_api import MODBUS_EXCEPTIONS
from ska_low_mccs_pasd.pasd_bus.pasd_bus_register_map import PasdCommandStrings
from tests.harness import PasdTangoTestHarness


class TestPasdBusModbusApi:
    """Tests of the PaSD bus Modbus server API."""

    @pytest.fixture(name="backend_fndh")
    def backend_fndh_fixture(
        self: TestPasdBusModbusApi, fndh_simulator: FndhSimulator
    ) -> mock.Mock:
        """
        Return a mock backend FNDH to test the API against.

        :param fndh_simulator: a FndhSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock
            with the same interface as its FNDH.
        :return: a mock backend to test the API against.
        """
        backend_fndh = mock.create_autospec(
            fndh_simulator,
            spec_set=True,
            instance=True,
            chip_id=[1, 2, 3, 4, 5, 6, 7, 8],
            psu48v_voltages=[47, 48],
            fncb_temperature=50,
        )
        # backend_fndh.set_led_pattern.return_value = True
        # backend_fndh.initialize.side_effect = ValueError("Mock error")
        return backend_fndh

    @pytest.fixture(name="backend_smartbox")
    def backend_smartbox_fixture(
        self: TestPasdBusModbusApi, smartbox_simulator: SmartboxSimulator
    ) -> mock.Mock:
        """
        Return a mock backend smartbox to test the API against.

        :param smartbox_simulator: a SmartboxSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock
            with the same interface as a Smartbox.
        :return: mock backends to test the API against.
        """
        backend_smartbox = mock.create_autospec(
            smartbox_simulator,
            spec_set=True,
            instance=True,
            chip_id=[8, 7, 6, 5, 4, 3, 2, 1],
            input_voltage=48,
            fem_case_temperatures=[40, 41],
        )
        return backend_smartbox

    @pytest.fixture(name="api")
    def api_fixture(
        self: TestPasdBusModbusApi,
        backend_fndh: mock.Mock,
        backend_smartbox: mock.Mock,
    ) -> PasdBusModbusApi:
        """
        Return an API instance against which to test.

        :param backend_fndh: a mock backend FNDH for the API to front.
        :param backend_smartbox: a mock backend smartboxes for the API to front.
        :return: an API instance against which to test
        """
        backend_mocks: dict[int, FndhSimulator | SmartboxSimulator] = {
            0: backend_fndh,
            1: backend_smartbox,
        }
        return PasdBusModbusApi(backend_mocks, logging.getLogger())

    # pylint: disable=too-many-arguments
    @pytest.mark.parametrize(
        ("backend", "slave", "attribute", "address", "count"),
        [
            ("backend_fndh", 0, "chip_id", 4, 8),
            ("backend_fndh", 0, "psu48v_voltages", 16, 2),
            ("backend_fndh", 0, "fncb_temperature", 22, 1),
            ("backend_smartbox", 1, "chip_id", 4, 8),
            ("backend_smartbox", 1, "input_voltage", 16, 1),
            ("backend_smartbox", 1, "fem_case_temperatures", 23, 2),
        ],
    )
    def test_read_attribute(
        self: TestPasdBusModbusApi,
        api: PasdBusModbusApi,
        backend: str,
        slave: int,
        attribute: str,
        address: int,
        count: int,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        Test handling of an attribute read request for an existing attribute.

        :param api: the API under test
        :param backend: a mock backend FNDH/Smartbox for this command to execute
            against.
        :param slave: id of modbus slave
        :param attribute: to read
        :param address: of register
        :param count: number of registers to read
        :param request: pytest FixtureRequest
        """
        framer = ModbusAsciiFramer(None)
        read_request = ReadHoldingRegistersRequest(address, count, slave)
        request_bytes = framer.buildPacket(read_request)
        response_bytes = api(request_bytes)
        reply_handled = False

        def _handle_reply(message: Any) -> None:
            nonlocal reply_handled
            reply_handled = True
            assert isinstance(message, ReadHoldingRegistersResponse)
            if isinstance(message, ReadHoldingRegistersResponse):
                assert message.slave_id == slave
                assert len(message.registers) == count
                expected = getattr(request.getfixturevalue(backend), attribute)
                if len(message.registers) == 1:
                    assert message.registers[0] == pytest.approx(expected)
                else:
                    assert message.registers == pytest.approx(expected)

        decoder = ModbusAsciiFramer(ClientDecoder())
        decoder.processIncomingPacket(response_bytes, _handle_reply, slave)
        assert reply_handled

    @pytest.mark.parametrize(
        ("slave", "address", "count"),
        [
            (0, 64, 1),  # nonexistent FNDH attribute
            (1, 60, 1),  # nonexistent smartbox attribute
            (0, 1100, 4),  # dummy FNDH attribute in register map, but not in simulator
        ],
    )
    def test_read_nonexistent_attribute(
        self: TestPasdBusModbusApi,
        api: PasdBusModbusApi,
        slave: int,
        address: int,
        count: int,
    ) -> None:
        """
        Test handling of an attribute read request for a nonexistent attribute.

        :param api: the API under test
        :param slave: id of modbus slave
        :param address: of register
        :param count: number of registers to read
        """
        framer = ModbusAsciiFramer(None)
        read_request = ReadHoldingRegistersRequest(address, count, slave)
        request_bytes = framer.buildPacket(read_request)
        response_bytes = api(request_bytes)
        reply_handled = False

        def _handle_reply(message: Any) -> None:
            nonlocal reply_handled
            reply_handled = True
            assert isinstance(message, ExceptionResponse)
            if isinstance(message, ExceptionResponse):
                assert message.slave_id == slave
                assert message.registers == []
                assert (
                    message.function_code
                    == 0x80 | ReadHoldingRegistersRequest.function_code
                )
                assert message.exception_code == ModbusExceptions.IllegalAddress

        decoder = ModbusAsciiFramer(ClientDecoder())
        decoder.processIncomingPacket(response_bytes, _handle_reply, slave)
        assert reply_handled

    @pytest.mark.parametrize(
        ("slave", "address", "count"),
        [
            (2, 16, 1),
            (3, 60, 1),
        ],
    )
    def test_read_unresponsive_device(
        self: TestPasdBusModbusApi,
        api: PasdBusModbusApi,
        slave: int,
        address: int,
        count: int,
    ) -> None:
        """
        Test handling of an attribute read request from an unresponsive device.

        :param api: the API under test
        :param slave: id of modbus slave
        :param address: of register
        :param count: number of registers to read
        """
        framer = ModbusAsciiFramer(None)
        read_request = ReadHoldingRegistersRequest(address, count, slave)
        request_bytes = framer.buildPacket(read_request)
        response_bytes = api(request_bytes)
        reply_handled = False

        def _handle_reply(message: Any) -> None:
            nonlocal reply_handled
            reply_handled = True
            assert isinstance(message, ExceptionResponse)
            if isinstance(message, ExceptionResponse):
                assert message.slave_id == slave
                assert message.registers == []
                assert (
                    message.function_code
                    == 0x80 | ReadHoldingRegistersRequest.function_code
                )
                assert message.exception_code == ModbusExceptions.GatewayNoResponse

        decoder = ModbusAsciiFramer(ClientDecoder())
        decoder.processIncomingPacket(response_bytes, _handle_reply, slave)
        assert reply_handled

    @pytest.mark.parametrize(
        ("slave", "address", "values"),
        [
            (0, 1000, [1, 2]),
            (1, 1000, [1, 2, 3, 4]),
        ],
    )
    def test_write_attribute(
        self: TestPasdBusModbusApi,
        api: PasdBusModbusApi,
        slave: int,
        address: int,
        values: Any,
    ) -> None:
        """
        Test handling of an attribute write request for an existing attribute.

        :param api: the API under test
        :param slave: id of modbus slave
        :param address: of register
        :param values: to write
        """
        framer = ModbusAsciiFramer(None)
        write_request = WriteMultipleRegistersRequest(address, values, slave)
        request_bytes = framer.buildPacket(write_request)
        response_bytes = api(request_bytes)
        reply_handled = False

        def _handle_reply(message: Any) -> None:
            nonlocal reply_handled
            reply_handled = True
            assert isinstance(message, WriteMultipleRegistersResponse)
            if isinstance(message, WriteMultipleRegistersResponse):
                assert message.slave_id == slave
                assert message.address == address
                assert message.count == len(values)

        decoder = ModbusAsciiFramer(ClientDecoder())
        decoder.processIncomingPacket(response_bytes, _handle_reply, slave)
        assert reply_handled

    @pytest.mark.parametrize(
        ("slave", "address", "values"),
        [
            (0, 1048, [1, 2]),  # nonexistent FNDH attribute
            (1, 1036, [1, 2, 3, 4]),  # nonexistent smartbox attribute
            (0, 1100, 1),  # dummy FNDH attribute in register map, but not in simulator
        ],
    )
    def test_write_nonexistent_attribute(
        self: TestPasdBusModbusApi,
        api: PasdBusModbusApi,
        slave: int,
        address: int,
        values: Any,
    ) -> None:
        """
        Test handling of an attribute write request for an existing attribute.

        :param api: the API under test
        :param slave: id of modbus slave
        :param address: of register
        :param values: to write
        """
        framer = ModbusAsciiFramer(None)
        write_request = WriteMultipleRegistersRequest(address, values, slave)
        request_bytes = framer.buildPacket(write_request)
        response_bytes = api(request_bytes)
        reply_handled = False

        def _handle_reply(message: Any) -> None:
            nonlocal reply_handled
            reply_handled = True
            assert isinstance(message, ExceptionResponse)
            if isinstance(message, ExceptionResponse):
                assert message.slave_id == slave
                assert message.registers == []
                assert (
                    message.function_code
                    == 0x80 | WriteMultipleRegistersRequest.function_code
                )
                assert message.exception_code == ModbusExceptions.IllegalAddress

        decoder = ModbusAsciiFramer(ClientDecoder())
        decoder.processIncomingPacket(response_bytes, _handle_reply, slave)
        assert reply_handled


class TestPasdBusModbusApiClient:
    """Tests of the PaSD bus Modbus client API."""

    @pytest.fixture(name="api")
    def api_fixture(
        self: TestPasdBusModbusApiClient,
        pasd_hw_simulators: dict[int, PasdHardwareSimulator],
        logger: logging.Logger,
    ) -> Generator:
        """
        Return an API instance against which to test.

        :param pasd_hw_simulators:
            the FNDH and smartbox simulator backends that the TCP server will front.
        :param logger: the logger to be used by this object.
        :yields: an API instance against which to test
        """
        harness = PasdTangoTestHarness()
        harness.set_pasd_bus_simulator(pasd_hw_simulators)
        with harness as context:
            (host, port) = context.get_pasd_bus_address()
            api = PasdBusModbusApiClient(host, port, logger, 3.0)
            api.connect()
            yield api
            api.close()

    @pytest.mark.parametrize(
        ("slave", "attribute", "expected"),
        [
            (
                0,
                "modbus_register_map_revision",
                FndhSimulator.MODBUS_REGISTER_MAP_REVISION,
            ),
            (1, "input_voltage", SmartboxSimulator.DEFAULT_INPUT_VOLTAGE / 100),
        ],
    )
    def test_read_attribute(
        self: TestPasdBusModbusApiClient,
        api: PasdBusModbusApiClient,
        slave: int,
        attribute: str,
        expected: Any,
    ) -> None:
        """
        Test handling of an attribute read request for an existing attribute.

        :param api: the API under test
        :param slave: id of modbus slave
        :param attribute: to read
        :param expected: values returned from simulator
        """
        response = api.read_attributes(slave, attribute)
        assert response[attribute] == expected

    # pylint: disable=too-many-arguments
    @pytest.mark.parametrize(
        ("backend", "slave", "attribute", "values", "expected"),
        [
            (
                "fndh_simulator",
                0,
                "fncb_temperature_thresholds",
                (100.0, 90.0, 50.0, 40.0),
                [10000, 9000, 5000, 4000],
            ),
            (
                "smartbox_simulator",
                1,
                "input_voltage_thresholds",
                (60.0, 55.0, 35.0, 30.0),
                [6000, 5500, 3500, 3000],
            ),
        ],
    )
    def test_write_attribute(
        self: TestPasdBusModbusApiClient,
        api: PasdBusModbusApiClient,
        backend: str,
        slave: int,
        attribute: str,
        values: Any,
        expected: Any,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        Test handling of an attribute write request for an existing attribute.

        :param backend: a mock backend FNDH/Smartbox for this command to execute
            against.
        :param api: the API under test
        :param slave: id of modbus slave
        :param attribute: to write
        :param values: to write
        :param expected: values returned from simulator
        :param request: pytest FixtureRequest
        """
        response = api.write_attribute(slave, attribute, *values)
        assert response[attribute] == values
        simulator_values = getattr(request.getfixturevalue(backend), attribute)
        assert simulator_values == expected

    # pylint: disable=too-many-arguments
    @pytest.mark.parametrize(
        ("backend", "slave", "command", "arguments", "attribute", "expected"),
        [
            (
                "smartbox_simulator",
                1,
                PasdCommandStrings.TURN_PORT_ON,
                2,
                "ports_desired_power_when_online",
                True,
            ),
            (
                "fndh_simulator",
                0,
                PasdCommandStrings.TURN_PORT_OFF,
                1,
                "ports_desired_power_when_online",
                False,
            ),
            (
                "smartbox_simulator",
                1,
                PasdCommandStrings.RESET_PORT_BREAKER,
                3,
                "port_breakers_tripped",
                False,
            ),
            (
                "fndh_simulator",
                0,
                PasdCommandStrings.SET_LED_PATTERN,
                LedServiceMap.ON.name,
                "led_pattern",
                LedServiceMap.ON ^ LedStatusMap.GREENSLOW,
            ),
            (
                "smartbox_simulator",
                1,
                PasdCommandStrings.INITIALIZE,
                10,
                "status",
                FndhStatusMap.OK,
            ),
        ],
    )
    def test_execute_command(
        self: TestPasdBusModbusApiClient,
        api: PasdBusModbusApiClient,
        backend: str,
        slave: int,
        command: str,
        arguments: Any,
        attribute: str,
        expected: Any,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        Test handling of an execute command request.

        :param backend: a mock backend FNDH/Smartbox for this command to execute
            against.
        :param api: the API under test
        :param slave: id of modbus slave
        :param command: to execute
        :param arguments: for command
        :param attribute: to check
        :param expected: values returned from simulator
        :param request: pytest FixtureRequest
        """
        if isinstance(arguments, tuple):
            response = api.execute_command(slave, command, *arguments)
        else:
            response = api.execute_command(slave, command, arguments)
        assert response is True
        simulator_values = getattr(request.getfixturevalue(backend), attribute)
        if isinstance(simulator_values, list) and not isinstance(expected, list):
            assert simulator_values[arguments - 1] == expected
        else:
            assert simulator_values == expected

    def test_execute_command_error(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test handling of an invalid execute command request.

        :param api: the API under test
        """
        response = api.execute_command(0, "DummyCommand", 0)
        assert response["error"]["code"] == "request"
        assert "Invalid command request" in response["error"]["detail"]
        print("\n" + response["error"]["detail"])

    def test_read_nonexistent_attribute(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test handling of an attribute read request for a nonexistent attribute.

        :param api: the API under test
        """
        response = api.read_attributes(0, "nonexistent attribute")
        assert response == {}

    def test_read_exception(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test reading attribute that exists in the register map, but not in simulator.

        :param api: the API under test
        """
        # TODO: Do we expect this exception from the HW?
        with pytest.raises(ModbusIOException) as exception:
            api.read_attributes(0, "dummy_for_test")
        assert (
            "Modbus Error: [Input/Output] No Response received from the remote slave/"
            "Unable to decode response" in str(exception.value)
        )
        print("\n" + str(exception.value))

    def test_read_non_contiguous_error(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test exception handling of reading multiple non-contiguous attributes.

        :param api: the API under test
        """
        response = api.read_attributes(25, "input_voltage", "pcb_temperature")
        assert response["error"]["code"] == "request"
        assert "Non-contiguous registers requested" in response["error"]["detail"]
        print("\n" + response["error"]["detail"])

    def test_read_unresponsive_device(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test handling of an attribute read request from an unresponsive device.

        :param api: the API under test
        """
        response = api.read_attributes(25, "input_voltage")
        assert response["error"]["code"] == "read"
        assert (
            MODBUS_EXCEPTIONS[ModbusExceptions.GatewayNoResponse]
            in response["error"]["detail"]
        )
        print("\n" + response["error"]["detail"])

    def test_write_nonexistent_attribute(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test handling of an attribute write request for a nonexistent attribute.

        :param api: the API under test
        """
        # TODO: Do we expect this exception from the HW?
        with pytest.raises(ModbusIOException) as exception:
            api.write_attribute(0, "dummy_for_test", 1, 2)
        assert (
            "Modbus Error: [Input/Output] No Response received from the remote slave/"
            "Unable to decode response" in str(exception.value)
        )
        print("\n" + str(exception.value))

    def test_write_read_only_attribute(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test handling of an attribute write request for a read-only attribute.

        :param api: the API under test
        """
        response = api.write_attribute(1, "input_voltage", 20.0)
        assert response["error"]["code"] == "request"
        assert (
            "Non-writeable register requested for write" in response["error"]["detail"]
        )
        print("\n" + response["error"]["detail"])

    def test_write_unresponsive_device(
        self: TestPasdBusModbusApiClient, api: PasdBusModbusApiClient
    ) -> None:
        """
        Test handling of an attribute write request to an unresponsive device.

        :param api: the API under test
        """
        response = api.write_attribute(25, "input_voltage_thresholds", 4, 3, 2, 1)
        assert response["error"]["code"] == "write"
        assert (
            MODBUS_EXCEPTIONS[ModbusExceptions.GatewayNoResponse]
            in response["error"]["detail"]
        )
        print("\n" + response["error"]["detail"])
