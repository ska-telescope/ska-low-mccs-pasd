# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""
This module contains tests of when MccsFNCC resets the FNCC status register.

MccsFNCC resets the status register when the FNCC reports a fault, and counts
the resets. The MccsPasdBus pushes a change event for the status on every poll
(not only when it changes), so a fault that persists across several polls is
reported to the device several times. These tests drive the device's real
``_attribute_changed_callback`` with such a sequence of reports.

They do not need a Tango device server: the device is stood in for by an object
that has the real MccsFNCC methods but mocks the Tango machinery around them.
"""
from __future__ import annotations

import inspect
import types
from typing import Any
from unittest import mock

import pytest
import tango
from ska_low_pasd_driver.pasd_bus_conversions import FnccStatusMap

from ska_low_mccs_pasd.fncc.fncc_device import MccsFNCC

OK = FnccStatusMap.OK.name
RESET = FnccStatusMap.RESET.name
FRAME_ERROR = FnccStatusMap.FRAME_ERROR.name
MODBUS_STUCK = FnccStatusMap.MODBUS_STUCK.name


class _FnccStandIn:  # pylint: disable=too-many-instance-attributes
    """
    A stand-in for an initialised MccsFNCC, without Tango.

    Methods and constants that the stand-in does not define are taken from
    MccsFNCC, so the code under test is the device's own.
    """

    def __init__(self) -> None:
        self.logger = mock.Mock()
        self.component_manager = mock.Mock()
        self.push_change_event = mock.Mock()
        self.push_archive_event = mock.Mock()
        self.set_state = mock.Mock()
        self.fncc_reset_count_signal = 0
        self._fncc_attributes = {
            "pasdstatus": types.SimpleNamespace(
                value=None, quality=tango.AttrQuality.ATTR_INVALID, timestamp=0.0
            )
        }
        # State that MccsFNCC sets up when it is initialised.
        self._fncc_reset_requested_for = None

    def __getattr__(self, name: str) -> Any:
        member = inspect.getattr_static(MccsFNCC, name)
        if isinstance(member, staticmethod):
            return member.__func__
        if inspect.isfunction(member):
            return types.MethodType(member, self)
        return member

    def report_status(self, status: str) -> None:
        """
        Report an FNCC status to the device, as the MccsPasdBus does on a poll.

        :param status: the status of the FNCC.
        """
        self._attribute_changed_callback(
            "pasdstatus", status, 0.0, tango.AttrQuality.ATTR_VALID
        )

    @property
    def resets_requested(self) -> int:
        """
        Return the number of resets of the FNCC status register requested.

        :returns: the number of times a reset has been requested.
        """
        return self.component_manager.reset_fncc_status.call_count


@pytest.fixture(name="fncc")
def fncc_fixture() -> _FnccStandIn:
    """
    Return a stand-in for an initialised MccsFNCC.

    :returns: a stand-in for an initialised MccsFNCC.
    """
    return _FnccStandIn()


def test_fault_is_reset(fncc: _FnccStandIn) -> None:
    """
    Test that a fault is reset, and the reset counted.

    :param fncc: the device under test.
    """
    fncc.report_status(FRAME_ERROR)

    assert fncc.resets_requested == 1
    assert fncc.fncc_reset_count_signal == 1


def test_healthy_status_is_not_reset(fncc: _FnccStandIn) -> None:
    """
    Test that neither OK nor RESET statuses cause a reset.

    :param fncc: the device under test.
    """
    for status in (OK, RESET, OK):
        fncc.report_status(status)

    assert fncc.resets_requested == 0
    assert fncc.fncc_reset_count_signal == 0


def test_persisting_fault_is_reset_once(fncc: _FnccStandIn) -> None:
    """
    Test that a fault reported on every poll is reset and counted only once.

    :param fncc: the device under test.
    """
    for _ in range(5):
        fncc.report_status(FRAME_ERROR)

    assert fncc.resets_requested == 1
    assert fncc.fncc_reset_count_signal == 1


def test_fault_that_returns_is_reset_again(fncc: _FnccStandIn) -> None:
    """
    Test that a fault is reset each time it occurs, after the status recovers.

    :param fncc: the device under test.
    """
    for status in (FRAME_ERROR, FRAME_ERROR, RESET, OK, OK):
        fncc.report_status(status)
    for _ in range(3):
        fncc.report_status(FRAME_ERROR)

    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 2


def test_different_fault_is_reset(fncc: _FnccStandIn) -> None:
    """
    Test that a change from one fault to another is reset.

    :param fncc: the device under test.
    """
    for status in (FRAME_ERROR, FRAME_ERROR, MODBUS_STUCK, MODBUS_STUCK):
        fncc.report_status(status)

    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 2


def test_failed_reset_is_retried_and_not_counted(fncc: _FnccStandIn) -> None:
    """
    Test that a reset that could not be requested is not counted, and is retried.

    :param fncc: the device under test.
    """
    fncc.component_manager.reset_fncc_status.side_effect = [
        ConnectionError("PasdBus not communicating"),
        None,
        None,
    ]

    fncc.report_status(FRAME_ERROR)
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(FRAME_ERROR)
    fncc.report_status(FRAME_ERROR)

    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 1
