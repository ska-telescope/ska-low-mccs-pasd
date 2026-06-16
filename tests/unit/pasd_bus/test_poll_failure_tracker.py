# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests of the PaSD bus poll failure tracker."""

from __future__ import annotations

import logging
import time
from typing import Final, Iterator

import numpy as np
import pytest
from ska_tango_testing.mock import MockCallable

from ska_low_mccs_pasd import PasdData
from ska_low_mccs_pasd.pasd_bus.poll_failure_tracker import (
    PollFailureSnapshot,
    PollFailureTracker,
)

N_SMARTBOXES: Final = PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION


@pytest.fixture(name="on_changed_callback")
def on_changed_callback_fixture() -> MockCallable:
    """
    Return a mock callback.

    :return: a Mock Callable object.
    """
    return MockCallable()


@pytest.fixture(name="poll_failure_tracker")
def poll_failure_tracker_fixture(
    on_changed_callback: MockCallable,
    logger: logging.Logger,
) -> Iterator[PollFailureTracker]:
    """
    Instantiate a PollFailureTracker.

    :param on_changed_callback: Callable to pass as the on_changed function
    :param logger: Logging object to use
    :yields: a PollFailureTracker object

    """
    # Use a window of 1 second for speedy testing, and a
    # short prune interval to ensure the window is updated promptly
    poll_failure_tracker = PollFailureTracker(
        1,
        0.1,
        logger,
        on_changed_callback,
    )
    yield poll_failure_tracker
    poll_failure_tracker.cleanup()


@pytest.mark.parametrize(
    ["fndh_failures", "fncc_failures", "smartbox_failures"],
    [
        pytest.param(
            np.random.randint(1, 10),
            0,
            tuple([0] * N_SMARTBOXES),
            id="fndh_failures",
        ),
        pytest.param(
            0,
            np.random.randint(1, 10),
            tuple([0] * N_SMARTBOXES),
            id="fncc_failures",
        ),
        pytest.param(
            0,
            0,
            tuple(np.random.randint(0, 3) for _ in range(N_SMARTBOXES)),
            id="sb_failures",
        ),
    ],
)
def test_record_failure(
    poll_failure_tracker: PollFailureTracker,
    on_changed_callback: MockCallable,
    fndh_failures: int,
    fncc_failures: int,
    smartbox_failures: tuple[int, ...],
) -> None:
    """
    Test recording a poll failure for each type of device.

    :param poll_failure_tracker: The PollFailureTracker object under test.
    :param on_changed_callback: The mocked Callable called when a poll fails.
    :param fndh_failures: The number of FNDH poll failures to trigger.
    :param fncc_failures: The number of FNCC poll failures to trigger.
    :param smartbox_failures: A tuple of smartbox failures to trigger.
    """
    initial_snapshot = PollFailureSnapshot(
        fndh_total=0,
        fncc_total=0,
        smartbox_totals=tuple([0] * N_SMARTBOXES),
        fndh_in_window=0,
        fncc_in_window=0,
        smartbox_in_window=tuple([0] * N_SMARTBOXES),
    )
    on_changed_callback.assert_call(initial_snapshot)
    on_changed_callback.assert_not_called()

    n_failures = max(fndh_failures, fncc_failures, sum(list(smartbox_failures)))

    for _ in range(fndh_failures):
        poll_failure_tracker.record_poll_failure(PasdData.FNDH_DEVICE_ID)

    for _ in range(fncc_failures):
        poll_failure_tracker.record_poll_failure(PasdData.FNCC_DEVICE_ID)

    for sb_index, sb_failures in enumerate(smartbox_failures):
        for _ in range(sb_failures):
            poll_failure_tracker.record_poll_failure(sb_index + 1)

    expected_snapshot = PollFailureSnapshot(
        fndh_total=fndh_failures,
        fncc_total=fncc_failures,
        smartbox_totals=smartbox_failures,
        fndh_in_window=fndh_failures,
        fncc_in_window=fncc_failures,
        smartbox_in_window=smartbox_failures,
    )
    # Add some lookahead buffer for the sliding window updates, as the prune
    # timer may have already removed some timestamps
    on_changed_callback.assert_call(expected_snapshot, lookahead=n_failures + 50)


def test_sliding_window_updates(
    poll_failure_tracker: PollFailureTracker, on_changed_callback: MockCallable
) -> None:
    """
    Test the sliding window values update as expected.

    :param poll_failure_tracker: The PollFailureTracker object being tested
    :param on_changed_callback: A mocked callback
    """
    n_failures: Final = 10
    # Record an FNDH poll failure every 0.1 seconds
    for _ in range(n_failures):
        poll_failure_tracker.record_poll_failure(PasdData.FNDH_DEVICE_ID)
        time.sleep(0.1)

    # Initially get N_FAILURES callbacks, each incrementing
    # both the total and window counters
    for total in range(1, n_failures + 1):
        expected_snapshot = PollFailureSnapshot(
            fndh_total=total,
            fncc_total=0,
            smartbox_totals=tuple([0] * N_SMARTBOXES),
            fndh_in_window=total,
            fncc_in_window=0,
            smartbox_in_window=tuple([0] * N_SMARTBOXES),
        )
        on_changed_callback.assert_call(expected_snapshot, consume_nonmatches=True)

    # After some time has passed, the window counters will decrease one by one
    time.sleep(1)
    for window in range(n_failures - 1, 0, -1):
        updated_snapshot = PollFailureSnapshot(
            fndh_total=n_failures,
            fncc_total=0,
            smartbox_totals=tuple([0] * N_SMARTBOXES),
            fndh_in_window=window,
            fncc_in_window=0,
            smartbox_in_window=tuple([0] * N_SMARTBOXES),
        )
        on_changed_callback.assert_call(updated_snapshot, consume_nonmatches=True)
