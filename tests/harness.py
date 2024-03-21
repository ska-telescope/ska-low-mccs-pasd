# -*- coding: utf-8 -*-
"""This module provides a flexible test harness for testing PaSD Tango devices."""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Iterator

import tango
from ska_control_model import LoggingLevel
from ska_tango_testing.harness import TangoTestHarness, TangoTestHarnessContext
from tango.server import Device

if TYPE_CHECKING:
    from ska_low_mccs_pasd.pasd_bus import PasdHardwareSimulator

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


def get_fncc_name(station_label: str | None = None) -> str:
    """
    Return the FNCC Tango device name.

    :param station_label: name of the station under test.
        Defaults to None, in which case the module default is used.

    :return: the FNCC Tango device name
    """
    return f"low-mccs/fncc/{station_label or DEFAULT_STATION_LABEL}"


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

    def get_fncc_device(self: PasdTangoTestHarnessContext) -> tango.DeviceProxy:
        """
        Get a proxy to the FNCC Tango device.

        :returns: a proxy to the FNCC Tango device.
        """
        return self._tango_context.get_device(get_fncc_name(self._station_label))

    def get_pasd_bus_address(self: PasdTangoTestHarnessContext) -> tuple[str, int]:
        """
        Get the address of the PaSD.

        :returns: the address (hostname and port) of the PaSD.
        """
        return self._tango_context.get_context("pasd_bus")

    def get_pasd_configuration_server_address(
        self: PasdTangoTestHarnessContext,
    ) -> tuple[str, int]:
        """
        Get the address of the PaSD configuration server.

        :returns: the address (hostname and port) of the PaSD configuration server.
        """
        return self._tango_context.get_context("configuration_manager")

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
        pasd_hw_simulators: dict[int, PasdHardwareSimulator],
    ) -> None:
        """
        Set the PaSD bus simulator server for the test harness.

        :param pasd_hw_simulators: FNDH and smartbox simulators to be used in testing.
        """
        # Defer importing from ska_low_mccs_pasd
        # until we know we need to launch a PaSD simulator to test against.
        # This ensures that we can use this harness to run tests against a real cluster,
        # from within a pod that does not have ska_low_mccs_pasd installed.
        # pylint: disable-next=import-outside-toplevel
        from ska_low_mccs_pasd.pasd_bus import PasdBusSimulatorModbusServer

        pasd_bus_simulator_server = PasdBusSimulatorModbusServer(pasd_hw_simulators)

        self._tango_test_harness.add_context_manager(
            "pasd_bus",
            server_context_manager_factory(pasd_bus_simulator_server),
        )

    def set_configuration_server(
        self: PasdTangoTestHarness,
        config_manager: Any,
    ) -> None:
        """
        Set the FieldStation configuration server for the test harness.

        :param config_manager: a configuration manager to manage
            configuration resource.
        """
        # Defer importing from ska_low_mccs_pasd
        # until we know we need to launch a PaSD simulator to test against.
        # This ensures that we can use this harness to run tests against a real cluster,
        # from within a pod that does not have ska_low_mccs_pasd installed.
        # pylint: disable-next=import-outside-toplevel
        from ska_low_mccs_pasd.reference_data_store import PasdConfigurationJsonServer

        logger: logging.Logger = logging.getLogger()
        configuration_server = PasdConfigurationJsonServer(
            logger, self._station_label, "ska-low-mccs", config_manager
        )

        self._tango_test_harness.add_context_manager(
            "configuration_manager",
            server_context_manager_factory(configuration_server),
        )

    def set_pasd_bus_device(  # pylint: disable=too-many-arguments
        self: PasdTangoTestHarness,
        address: tuple[str, int] | None = None,
        polling_rate: float = 0.5,
        device_polling_rate: float = 15.0,
        low_pass_filter_cutoff: float = 10.0,
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
        :param low_pass_filter_cutoff: the default cut-off frequency to set for
            the devices' sensors' low-pass filtering.
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
            LowPassFilterCutoff=low_pass_filter_cutoff,
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

        def port(context: dict[str, Any]) -> int:
            return context["configuration_manager"][1]

        smartbox_names = [get_smartbox_name(number) for number in smartbox_numbers]

        self._tango_test_harness.add_device(
            get_field_station_name(self._station_label),
            device_class,
            StationName=self._station_label,
            ConfigurationHost="localhost",
            ConfigurationPort=port,
            ConfigurationTimeout=5,
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

    def set_fncc_device(
        self: PasdTangoTestHarness,
        logging_level: int = int(LoggingLevel.DEBUG),
        device_class: type[Device] | str = "ska_low_mccs_pasd.MccsFNCC",
    ) -> None:
        """
        Set the FNCC Tango device in the test harness.

        This test harness currently only permits one FNCC device.

        :param logging_level: the Tango device's default logging level.
        :param device_class: The device class to use.
            This may be used to override the usual device class,
            for example with a patched subclass.
        """
        self._tango_test_harness.add_device(
            get_fncc_name(self._station_label),
            device_class,
            PasdFQDN=get_pasd_bus_name(),
            LoggingLevelDefault=logging_level,
        )

    def set_mock_field_station_device(
        self: PasdTangoTestHarness,
        mock: tango.DeviceProxy,
    ) -> None:
        """
        Add a mock Field Station Tango device to this test harness.

        :param mock: the proxy or mock to be used as a mock FieldStation device.
        """
        self._tango_test_harness.add_mock_device(
            get_field_station_name(self._station_label), mock
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
        logging_level: int = int(LoggingLevel.DEBUG),
        device_class: type[Device] | str = "ska_low_mccs_pasd.MccsSmartBox",
    ) -> None:
        """
        Add a smartbox Tango device to the test harness.

        :param smartbox_id: ID number of the smartbox.
        :param logging_level: the Tango device's default logging level.
        :param device_class: The device class to use.
            This may be used to override the usual device class,
            for example with a patched subclass.
        """
        self._tango_test_harness.add_device(
            get_smartbox_name(smartbox_id, station_label=self._station_label),
            device_class,
            FieldStationName=get_field_station_name(),
            PasdFQDN=get_pasd_bus_name(),
            SmartBoxNumber=smartbox_id,
            LoggingLevelDefault=logging_level,
        )

    def __enter__(
        self: PasdTangoTestHarness,
    ) -> PasdTangoTestHarnessContext:
        """
        Enter the context.

        :return: the entered context.
        """
        with self._cleanup_on_error():
            return PasdTangoTestHarnessContext(
                self._tango_test_harness.__enter__(), self._station_label
            )

    @contextmanager
    def _cleanup_on_error(self: PasdTangoTestHarness) -> Iterator[None]:
        with self._tango_test_harness._exit_stack as stack:
            stack.push(self)
            yield
            stack.pop_all()

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
