# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains pytest-specific test harness for PaSD functional tests."""
import os
from typing import Generator, Union, cast

import _pytest
import pytest
from ska_control_model import LoggingLevel
from ska_tango_testing.context import (
    TangoContextProtocol,
    ThreadedTestTangoContextManager,
    TrueTangoContextManager,
)


# TODO: https://github.com/pytest-dev/pytest-forked/issues/67
# We're stuck on pytest 6.2 until this gets fixed,
# and this version of pytest is not fully typehinted
def pytest_addoption(
    parser: _pytest.config.argparsing.Parser,  # type: ignore[name-defined]
) -> None:
    """
    Add a command line option to pytest.

    This is a pytest hook, here implemented to add the `--true-context`
    option, used to indicate that a true Tango subsystem is available,
    so there is no need for the test harness to spin up a Tango test
    context.

    :param parser: the command line options parser
    """
    parser.addoption(
        "--true-context",
        action="store_true",
        default=False,
        help=(
            "Tell pytest that you have a true Tango context and don't "
            "need to spin up a Tango test context"
        ),
    )


@pytest.fixture(name="true_context", scope="session")
def true_context_fixture(request: pytest.FixtureRequest) -> bool:
    """
    Return whether to test against an existing Tango deployment.

    If True, then Tango is already deployed, and the tests will be run
    against that deployment.

    If False, then Tango is not deployed, so the test harness will stand
    up a test context and run the tests against that.

    :param request: A pytest object giving access to the requesting test
        context.

    :return: whether to test against an existing Tango deployment
    """
    if request.config.getoption("--true-context"):
        return True
    if os.getenv("TRUE_TANGO_CONTEXT", None):
        return True
    return False


@pytest.fixture(name="tango_harness", scope="module")
def tango_harness_fixture(
    pasd_bus_name: str,
    true_context: bool,
) -> Generator[TangoContextProtocol, None, None]:
    """
    Yield a Tango context containing the device/s under test.

    :param pasd_bus_name: name of the PaSD bus Tango device.
    :param true_context: whether to test against an existing Tango
        deployment

    :yields: a Tango context containing the devices under test
    """
    tango_context_manager: Union[
        TrueTangoContextManager, ThreadedTestTangoContextManager
    ]  # for the type checker
    if true_context:
        tango_context_manager = TrueTangoContextManager()
        with tango_context_manager as context:
            yield context
    else:
        tango_context_manager = ThreadedTestTangoContextManager()
        cast(ThreadedTestTangoContextManager, tango_context_manager).add_device(
            pasd_bus_name,
            "ska_low_mccs_pasd.MccsPasdBus",
            LoggingLevelDefault=int(LoggingLevel.DEBUG),
        )
        with tango_context_manager as context:
            yield context
