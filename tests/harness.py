# -*- coding: utf-8 -*-
"""This module provides a flexible test harness for testing PaSD Tango devices."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Iterator

import tango
from ska_control_model import LoggingLevel
from ska_tango_testing.harness import TangoTestHarness, TangoTestHarnessContext
from tango.server import Device

if TYPE_CHECKING:
    from ska_low_mccs_pasd.pasd_bus import FndhSimulator, SmartboxSimulator

DEFAULT_STATION_LABEL = "ci-1"  # station 1 of cluster "ci"


def get_pasd_bus_name(station_label: str | None = None) -> str:
    """
    Return the PaSD bus Tango device name.

    :param station_label: name of the station under test.
        Defaults to None, in which case the module default is used.

    :return: the PaSD bus Tango device name
    """
    return f"low-mccs/pasdbus/{station_label or DEFAULT_STATION_LABEL}"


def get_field_station_name(station_label: str | None = None) -> str:
    """
    Return the field_station Tango device name.

    :param station_label: name of the station under test.
        Defaults to None, in which case the module default is used.

    :return: the field station Tango device name
    """
    return f"low-mccs/fieldstation/{station_label or DEFAULT_STATION_LABEL}"


def get_fndh_name(station_label: str | None = None) -> str:
    """
    Return the FNDH Tango device name.

    :param station_label: name of the station under test.
        Defaults to None, in which case the module default is used.

    :return: the FNDH Tango device name
    """
    return f"low-mccs/fndh/{station_label or DEFAULT_STATION_LABEL}"


def get_smartbox_name(smartbox_id: int, station_label: str | None = None) -> str:
    """
    Return a smartbox's  Tango device name.

    :param smartbox_id: ID of the smartbox under test.
    :param station_label: name of the station under test.
        Defaults to None, in which case the module default is used.

    :return: the smartbox's Tango device name
    """
    slug = f"{station_label or DEFAULT_STATION_LABEL}-{smartbox_id:02}"
    return f"low-mccs/smartbox/{slug}"


class PasdTangoTestHarnessContext:
    """Handle for the PaSD test harness context."""

    def __init__(
        self: PasdTangoTestHarnessContext,
        tango_context: TangoTestHarnessContext,
        station_label: str,
    ) -> None:
        """
        Initialise a new instance.

        :param tango_context: handle for the underlying test harness
            context.
        :param station_label: name of the station under test.
        """
        self._station_label = station_label
        self._tango_context = tango_context

    def get_pasd_bus_device(self: PasdTangoTestHarnessContext) -> tango.DeviceProxy:
        """
        Get a proxy to the PaSD bus Tango device.

        :returns: a proxy to the PaSD bus Tango device.
        """
        return self._tango_context.get_device(get_pasd_bus_name(self._station_label))

    def get_field_station_device(
        self: PasdTangoTestHarnessContext,
    ) -> tango.DeviceProxy:
        """
        Get a proxy to the field station Tango device.

        :returns: a proxy to the field station Tango device.
        """
        return self._tango_context.get_device(
            get_field_station_name(self._station_label)
        )

    def get_fndh_device(self: PasdTangoTestHarnessContext) -> tango.DeviceProxy:
        """
        Get a proxy to the FNDH Tango device.

        :returns: a proxy to the FNDH Tango device.
        """
        return self._tango_context.get_device(get_fndh_name(self._station_label))

    def get_pasd_bus_address(self: PasdTangoTestHarnessContext) -> tuple[str, int]:
        """
        Get the address of the PaSD.

        :returns: the address (hostname and port) of the PaSD.
        """
        return self._tango_context.get_context("pasd_bus")

    def get_smartbox_device(
        self: PasdTangoTestHarnessContext, smartbox_id: int
    ) -> tango.DeviceProxy:
        """
        Get a smartbox Tango device by its ID number.

        :param smartbox_id: the ID number of the smartbox.

        :returns: a proxy to the smartbox Tango device.
        """
        return self._tango_context.get_device(
            get_smartbox_name(smartbox_id, station_label=self._station_label)
        )


@contextmanager
def server_context_manager_factory(
    backend: Callable[[Iterator[bytes]], bytes | None],
) -> Iterator[tuple[str | bytes | bytearray, int]]:
    """
    Return a context manager factory for a server.

    That is, a callable that, when called,
    returns a context manager that spins up a server for the provided backend,
    yields it for use in testing,
    and then shuts its down afterwards.

    :param backend: the backend for the TCP server

    :yields: a server context manager factory.
    """
    # pylint: disable-next=import-outside-toplevel
    from ska_ser_devices.client_server import TcpServer

    server = TcpServer("localhost", 0, backend)
    with server:
        server_thread = threading.Thread(
            name="TCP server thread",
            target=server.serve_forever,
        )
        server_thread.daemon = True  # don't hang on exit
        server_thread.start()
        yield server.server_address
        server.shutdown()


class PasdTangoTestHarness:
    """A test harness for testing monitoring and control of PaSD hardware."""

    def __init__(self: PasdTangoTestHarness, station_label: str | None = None) -> None:
        """
        Initialise a new test harness instance.

        :param station_label: name of the station under test.
            Defaults to None, in which case "ci-1" is used.
        """
        self._station_label = station_label or DEFAULT_STATION_LABEL
        self._tango_test_harness = TangoTestHarness()

    def set_pasd_bus_simulator(
        self: PasdTangoTestHarness,
        fndh_simulator: FndhSimulator,
        smartbox_simulators: dict[int, SmartboxSimulator],
    ) -> None:
        """
        Set the PaSD bus simulator server for the test harness.

        :param fndh_simulator: the FNDH simulator to be used in testing.
        :param smartbox_simulators: the smartbox simulators to be used in testing.
        """
        # Defer importing from ska_low_mccs_pasd
        # until we know we need to launch a PaSD simulator to test against.
        # This ensures that we can use this harness to run tests against a real cluster,
        # from within a pod that does not have ska_low_mccs_pasd installed.
        # pylint: disable-next=import-outside-toplevel
        from ska_low_mccs_pasd.pasd_bus import PasdBusSimulatorJsonServer

        pasd_bus_simulator_server = PasdBusSimulatorJsonServer(
            fndh_simulator, smartbox_simulators
        )

        self._tango_test_harness.add_context_manager(
            "pasd_bus",
            server_context_manager_factory(pasd_bus_simulator_server),
        )

    def set_pasd_bus_device(  # pylint: disable=too-many-arguments
        self: PasdTangoTestHarness,
        address: tuple[str, int] | None = None,
        polling_rate: float = 0.5,
        device_polling_rate: float = 15.0,
        timeout: float = 1.0,
        logging_level: int = int(LoggingLevel.DEBUG),
        device_class: type[Device] | str = "ska_low_mccs_pasd.MccsPasdBus",
    ) -> None:
        """
        Set the PaSD bus Tango device in the test harness.

        This test harness currently only permits one PaSD bus device.

        :param address: address of the PaSD
            to be monitored and controlled by this Tango device.
            It is a tuple of hostname or IP address, and port.
        :param polling_rate: minimum amount of time between communications
            on the PaSD bus
        :param device_polling_rate: minimum amount of time between communications
            with the same device.
        :param timeout: timeout to use when interacting with the PaSD
        :param logging_level: the Tango device's default logging level.
        :param device_class: The device class to use.
            This may be used to override the usual device class,
            for example with a patched subclass.
        """
        port: Callable[[dict[str, Any]], int] | int  # for the type checker

        if address is None:
            host = "localhost"

            def port(context: dict[str, Any]) -> int:
                return context["pasd_bus"][1]

        else:
            (host, port) = address

        self._tango_test_harness.add_device(
            get_pasd_bus_name(self._station_label),
            device_class,
            Host=host,
            Port=port,
            PollingRate=polling_rate,
            DevicePollingRate=device_polling_rate,
            Timeout=timeout,
            LoggingLevelDefault=logging_level,
        )

    def set_mock_pasd_bus_device(
        self: PasdTangoTestHarness,
        mock: tango.DeviceProxy,
    ) -> None:
        """
        Add a mock pasd bus Tango device to this test harness.

        :param mock: the proxy or mock to be used as a mock pasd bus device.
        """
        self._tango_test_harness.add_mock_device(
            get_pasd_bus_name(self._station_label), mock
        )

    def set_field_station_device(
        self: PasdTangoTestHarness,
        smartbox_numbers: list[int] | None = None,
        logging_level: int = int(LoggingLevel.DEBUG),
        device_class: type[Device] | str = "ska_low_mccs_pasd.MccsFieldStation",
    ) -> None:
        """
        Set the Field Station Tango device in the test harness.

        This test harness currently only permits one Field Station device.

        :param smartbox_numbers: numbers of the smartboxes
        :param logging_level: the Tango device's default logging level.
        :param device_class: The device class to use.
            This may be used to override the usual device class,
            for example with a patched subclass.
        """
        if smartbox_numbers is None:
            smartbox_numbers = list(range(1, 25))

        smartbox_names = [get_smartbox_name(number) for number in smartbox_numbers]

        self._tango_test_harness.add_device(
            get_field_station_name(self._station_label),
            device_class,
            FndhFQDN=get_fndh_name(),
            SmartBoxFQDNs=smartbox_names,
            LoggingLevelDefault=logging_level,
        )

    def set_fndh_device(
        self: PasdTangoTestHarness,
        logging_level: int = int(LoggingLevel.DEBUG),
        device_class: type[Device] | str = "ska_low_mccs_pasd.MccsFNDH",
    ) -> None:
        """
        Set the FNDH Tango device in the test harness.

        This test harness currently only permits one FNDH device.

        :param logging_level: the Tango device's default logging level.
        :param device_class: The device class to use.
            This may be used to override the usual device class,
            for example with a patched subclass.
        """
        self._tango_test_harness.add_device(
            get_fndh_name(self._station_label),
            device_class,
            PasdFQDN=get_pasd_bus_name(),
            LoggingLevelDefault=logging_level,
        )

    def set_mock_fndh_device(
        self: PasdTangoTestHarness,
        mock: tango.DeviceProxy,
    ) -> None:
        """
        Add a mock FNDH Tango device to this test harness.

        :param mock: the proxy or mock to be used as a mock FNDH device.
        """
        self._tango_test_harness.add_mock_device(
            get_fndh_name(self._station_label), mock
        )

    def set_mock_smartbox_device(
        self: PasdTangoTestHarness,
        mock: tango.DeviceProxy,
        smartbox_id: int,
    ) -> None:
        """
        Add a mock FNDH Tango device to this test harness.

        :param mock: the proxy or mock to be used as a mock FNDH device.
        :param smartbox_id: the id of the smartbox.
        """
        self._tango_test_harness.add_mock_device(
            get_smartbox_name(smartbox_id, self._station_label), mock
        )

    def add_smartbox_device(
        self: PasdTangoTestHarness,
        smartbox_id: int,
        fndh_port: int = 0,
        logging_level: int = int(LoggingLevel.DEBUG),
        device_class: type[Device] | str = "ska_low_mccs_pasd.MccsSmartBox",
    ) -> None:
        """
        Add a smartbox Tango device to the test harness.

        :param smartbox_id: ID number of the smartbox.
        :param fndh_port: FNDH port in which this smartbox is plugged.
            If omitted or set to zero, the port will be the same as the smartbox id.
        :param logging_level: the Tango device's default logging level.
        :param device_class: The device class to use.
            This may be used to override the usual device class,
            for example with a patched subclass.
        """
        self._tango_test_harness.add_device(
            get_smartbox_name(smartbox_id, station_label=self._station_label),
            device_class,
            FndhPort=fndh_port or smartbox_id,
            PasdFQDN=get_pasd_bus_name(),
            FndhFQDN=get_fndh_name(),
            LoggingLevelDefault=logging_level,
        )

    def __enter__(
        self: PasdTangoTestHarness,
    ) -> PasdTangoTestHarnessContext:
        """
        Enter the context.

        :return: the entered context.
        """
        return PasdTangoTestHarnessContext(
            self._tango_test_harness.__enter__(), self._station_label
        )

    def __exit__(
        self: PasdTangoTestHarness,
        exc_type: type[BaseException] | None,
        exception: BaseException | None,
        trace: TracebackType | None,
    ) -> bool | None:
        """
        Exit the context.

        :param exc_type: the type of exception thrown in the with block,
            if any.
        :param exception: the exception thrown in the with block, if
            any.
        :param trace: the exception traceback, if any,

        :return: whether the exception (if any) has been fully handled
            by this method and should be swallowed i.e. not re-
            raised
        """
        return self._tango_test_harness.__exit__(exc_type, exception, trace)
