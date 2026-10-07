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
the resets that cleared the fault. The MccsPasdBus pushes a change event for the
status on every poll (not only when it changes), so a fault that persists across
several polls is reported to the device several times. These tests drive the
device's real ``_attribute_changed_callback`` with such a sequence of reports.

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
    MccsFNCC, so the code under test is the device's own. Device properties
    have their default values, unless they are set.
    """

    ResetRetryTimeout: float

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
        self._fncc_reset_requested_at = 0.0

    def __getattr__(self, name: str) -> Any:
        member = inspect.getattr_static(MccsFNCC, name)
        if isinstance(member, staticmethod):
            return member.__func__
        if inspect.isfunction(member):
            return types.MethodType(member, self)
        if hasattr(member, "default_value"):
            # A device property, which has not been set in the database.
            return member.default_value
        return member

    def report_status(self, status: str, at: float = 0.0) -> None:
        """
        Report an FNCC status to the device, as the MccsPasdBus does on a poll.

        :param status: the status of the FNCC.
        :param at: the time of the report, in seconds.
        """
        self._attribute_changed_callback(
            "pasdstatus", status, at, tango.AttrQuality.ATTR_VALID
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
    Test that a fault is reset.

    :param fncc: the device under test.
    """
    fncc.report_status(FRAME_ERROR)

    assert fncc.resets_requested == 1


def test_reset_is_counted_when_the_status_clears(fncc: _FnccStandIn) -> None:
    """
    Test that a reset is counted when the fault is seen to have cleared, once.

    Requesting a reset only queues it. It can still fail when it is written to
    the hardware, so it is only counted when the status is seen to have cleared.

    :param fncc: the device under test.
    """
    fncc.report_status(FRAME_ERROR)
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(RESET)
    assert fncc.fncc_reset_count_signal == 1

    for status in (RESET, OK, OK):
        fncc.report_status(status)
    assert fncc.fncc_reset_count_signal == 1


def test_healthy_status_is_not_reset(fncc: _FnccStandIn) -> None:
    """
    Test that neither OK nor RESET statuses cause a reset, or are counted.

    :param fncc: the device under test.
    """
    for status in (OK, RESET, OK):
        fncc.report_status(status)

    assert fncc.resets_requested == 0
    assert fncc.fncc_reset_count_signal == 0


def test_persisting_fault_is_reset_once(fncc: _FnccStandIn) -> None:
    """
    Test that a fault reported on every poll is reset once, and counted once.

    :param fncc: the device under test.
    """
    for _ in range(5):
        fncc.report_status(FRAME_ERROR)
    assert fncc.resets_requested == 1
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(RESET)
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
    assert fncc.fncc_reset_count_signal == 1

    fncc.report_status(RESET)
    assert fncc.fncc_reset_count_signal == 2


def test_different_fault_is_reset(fncc: _FnccStandIn) -> None:
    """
    Test that a change from one fault to another is reset, but not counted.

    The first fault did not clear: it was replaced. Only the reset that is seen
    to have cleared a fault is counted.

    :param fncc: the device under test.
    """
    for status in (FRAME_ERROR, FRAME_ERROR, MODBUS_STUCK, MODBUS_STUCK):
        fncc.report_status(status)
    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(RESET)
    assert fncc.fncc_reset_count_signal == 1


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
    fncc.report_status(FRAME_ERROR)
    fncc.report_status(FRAME_ERROR)
    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(RESET)
    assert fncc.fncc_reset_count_signal == 1


def test_status_that_clears_by_itself_is_not_counted(fncc: _FnccStandIn) -> None:
    """
    Test that a fault that clears when no reset was requested is not counted.

    :param fncc: the device under test.
    """
    fncc.component_manager.reset_fncc_status.side_effect = ConnectionError(
        "PasdBus not communicating"
    )

    fncc.report_status(FRAME_ERROR)
    fncc.report_status(OK)

    assert fncc.fncc_reset_count_signal == 0


def test_fault_is_not_reset_again_before_the_timeout(fncc: _FnccStandIn) -> None:
    """
    Test that a fault still reported just before the timeout is not reset again.

    :param fncc: the device under test.
    """
    for time in (0.0, 10.0, 29.9):
        fncc.report_status(FRAME_ERROR, at=time)

    assert fncc.resets_requested == 1


def test_fault_is_reset_again_after_the_timeout(fncc: _FnccStandIn) -> None:
    """
    Test that a fault still reported when the timeout expires is reset again.

    The reset may have been queued but have failed when it was written to the
    hardware, so it is retried. The fault is counted once, when it clears.

    :param fncc: the device under test.
    """
    for time in (0.0, 10.0, 30.0):
        fncc.report_status(FRAME_ERROR, at=time)
    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(RESET, at=31.0)
    assert fncc.fncc_reset_count_signal == 1


def test_retries_repeat_every_timeout(fncc: _FnccStandIn) -> None:
    """
    Test that the timeout is measured from the latest attempt.

    :param fncc: the device under test.
    """
    for time in (0.0, 30.0, 45.0, 59.9):
        fncc.report_status(FRAME_ERROR, at=time)
    assert fncc.resets_requested == 2

    for time in (60.0, 75.0, 90.0):
        fncc.report_status(FRAME_ERROR, at=time)
    assert fncc.resets_requested == 4
    assert fncc.fncc_reset_count_signal == 0

    fncc.report_status(OK, at=91.0)
    assert fncc.fncc_reset_count_signal == 1


def test_timeout_is_measured_from_the_last_successful_request(
    fncc: _FnccStandIn,
) -> None:
    """
    Test that a request that could not be made does not start the timeout.

    :param fncc: the device under test.
    """
    fncc.component_manager.reset_fncc_status.side_effect = [
        ConnectionError("PasdBus not communicating"),
        None,
        None,
    ]

    fncc.report_status(FRAME_ERROR, at=100.0)  # Fails.
    fncc.report_status(FRAME_ERROR, at=101.0)  # Retried at once, and succeeds.
    fncc.report_status(FRAME_ERROR, at=130.9)  # 29.9 s after the last attempt.
    assert fncc.resets_requested == 2

    fncc.report_status(FRAME_ERROR, at=131.0)  # 30 s after the last attempt.

    assert fncc.resets_requested == 3


def test_recovery_ends_the_wait(fncc: _FnccStandIn) -> None:
    """
    Test that a fault that returns is reset at once, not after the timeout.

    :param fncc: the device under test.
    """
    fncc.report_status(FRAME_ERROR, at=0.0)
    fncc.report_status(RESET, at=1.0)
    fncc.report_status(FRAME_ERROR, at=2.0)

    assert fncc.resets_requested == 2
    assert fncc.fncc_reset_count_signal == 1


def test_retry_timeout_is_configurable(fncc: _FnccStandIn) -> None:
    """
    Test that the timeout can be changed with the ResetRetryTimeout property.

    :param fncc: the device under test.
    """
    fncc.ResetRetryTimeout = 5.0

    fncc.report_status(FRAME_ERROR, at=0.0)
    fncc.report_status(FRAME_ERROR, at=4.9)
    assert fncc.resets_requested == 1

    fncc.report_status(FRAME_ERROR, at=5.0)

    assert fncc.resets_requested == 2
