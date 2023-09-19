# -*- coding: utf-8 -*
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Tests of the PasdBusModbusApi."""
from __future__ import annotations

from typing import Any, Dict
from unittest import mock

import pytest
from pymodbus.factory import ClientDecoder
from pymodbus.framer.ascii_framer import ModbusAsciiFramer
from pymodbus.register_read_message import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
)

from ska_low_mccs_pasd.pasd_bus import (
    FndhSimulator,
    PasdBusModbusApi,
    PasdBusSimulator,
    SmartboxSimulator,
)


class TestPasdBusModbusApi:
    """Tests of the PaSD bus Modbus-based API."""

    @pytest.fixture(name="backend_pasd_bus")
    def backend_pasd_bus_fixture(
        self: TestPasdBusModbusApi,
        pasd_bus_simulator: PasdBusSimulator,
    ) -> mock.Mock:
        """
        Return a mock backend to test the API against.

        :param pasd_bus_simulator: a PasdBusSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock with the same interface.

        :return: a mock backend to test the API against.
        """
        backend_pasd_bus = mock.create_autospec(
            pasd_bus_simulator,
            spec_set=True,
            instance=True,
        )
        return backend_pasd_bus

    @pytest.fixture(name="backend_fndh")
    def backend_fndh_fixture(
        self: TestPasdBusModbusApi, pasd_bus_simulator: PasdBusSimulator
    ) -> mock.Mock:
        """
        Return a mock backend FNDH to test the API against.

        :param pasd_bus_simulator: a PasdBusSimulator.
            This backend fixture doesn't actually use the simulator,
            other than to autospec a mock
            with the same interface as its FNDH.

        :return: a mock backend to test the API against.
        """
        backend_fndh = mock.create_autospec(
            pasd_bus_simulator.get_fndh(),
            spec_set=True,
            instance=True,
            fncb_temperature=40,
        )
        backend_fndh.set_led_pattern.return_value = True
        backend_fndh.initialize.side_effect = ValueError("Mock error")
        return backend_fndh

    @pytest.fixture(name="backend_smartboxes")
    def backend_smartboxes_fixture(
        self: TestPasdBusModbusApi,
    ) -> Dict[int, mock.Mock]:
        """
        Return a dictionary of mock backend smartboxes to test the API against.

        :return: mock backends to test the API against.
        """
        return {i: mock.Mock() for i in range(1, 25)}

    @pytest.fixture(name="encoding")
    def encoding_fixture(
        self: TestPasdBusModbusApi,
    ) -> str:
        """
        Return the encoding to use when converting between string and bytes.

        :return: the encoding to use when converting between string and
            bytes.
        """
        return "utf-8"

    @pytest.fixture(name="api")
    def api_fixture(
        self: TestPasdBusModbusApi,
        backend_fndh: mock.Mock,
        backend_smartboxes: Dict[int, mock.Mock],
    ) -> PasdBusModbusApi:
        """
        Return an API instance against which to test.

        :param backend_fndh: a mock backend FNDH for the API to front.
        :param backend_smartboxes: dictionary of mock backend smartboxes for
            the API to front.

        :return: an API instance against which to test
        """
        backend_mocks: Dict[int, FndhSimulator | SmartboxSimulator] = {101: backend_fndh}
        backend_mocks.update(backend_smartboxes)
        return PasdBusModbusApi(backend_mocks)

    def test_read_attribute(
        self: TestPasdBusModbusApi,
        api: PasdBusModbusApi,
        backend_fndh: mock.Mock,
    ) -> None:
        """
        Test handling of an attribute read request for an existing attribute.

        :param api: the API under test
        :param backend_fndh: a mock backend FNDH for this command to execute
            against.
        """
        framer = ModbusAsciiFramer(None)
        request = ReadHoldingRegistersRequest(address=23, slave=0, count=1)
        request_bytes = framer.buildPacket(request)
        response_bytes = api(request_bytes)
        reply_handled = False

        def _handle_reply(message: Any) -> None:
            nonlocal reply_handled
            reply_handled = True
            assert isinstance(message, ReadHoldingRegistersResponse)
            if isinstance(message, ReadHoldingRegistersResponse):
                assert message.slave_id == 0
                assert len(message.registers) == 1
                assert message.registers[0] == pytest.approx(
                    backend_fndh.fncb_temperature
                )

        decoder = ModbusAsciiFramer(ClientDecoder())
        decoder.processIncomingPacket(response_bytes, _handle_reply, slave=0)
        assert reply_handled
