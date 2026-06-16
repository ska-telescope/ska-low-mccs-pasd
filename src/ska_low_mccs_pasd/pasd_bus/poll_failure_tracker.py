# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Track poll failures for the PaSD bus and report them as a snapshot."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from ska_low_mccs_pasd.pasd_data import PasdData


@dataclass(frozen=True)
class PollFailureSnapshot:
    """
    Immutable snapshot of poll-failure state.

    Carries both cumulative counts (since the tracker was created) and
    the number of failures observed within the most recent sliding
    window.
    """

    fndh_total: int
    fncc_total: int
    smartbox_totals: tuple[int, ...]
    fndh_in_window: int
    fncc_in_window: int
    smartbox_in_window: tuple[int, ...]


# pylint: disable=too-many-instance-attributes
class PollFailureTracker:
    """Track and report poll failures for the PaSD bus.

    Whenever state changes (a new failure is recorded or a sliding
    window value is re-calculated), a single `PollFailureSnapshot`
    is delivered to the ``on_changed`` callback.
    """

    def __init__(
        self: PollFailureTracker,
        window: float,
        prune_interval: float,
        logger: logging.Logger,
        on_changed: Callable[[PollFailureSnapshot], None],
    ):
        """
        Initialise a new instance.

        :param window: sliding-window length in seconds.
        :param prune_interval: how often (seconds) to prune expired
            timestamps.
        :param logger: logger for this object to use.
        :param on_changed: callable invoked with a fresh snapshot whenever
            the cumulative or windowed counts change.
        """
        self._logger = logger
        self._window = window
        self._prune_interval = prune_interval
        self._on_changed = on_changed

        self._lock = threading.Lock()
        self._stopped = False

        self._fndh_total = 0
        self._fncc_total = 0
        self._smartbox_totals: list[int] = [
            0
        ] * PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION
        self._fndh_timestamps: deque[float] = deque()
        self._fncc_timestamps: deque[float] = deque()
        self._smartbox_timestamps: list[deque[float]] = [
            deque() for _ in range(PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION)
        ]
        # Keep hold of the last snapshot to prevent duplicate callbacks
        self._last_snapshot: Optional[PollFailureSnapshot] = None

        self._prune_timer: Optional[threading.Timer] = None
        self._schedule_prune()

    def record_poll_failure(self: PollFailureTracker, device_id: int) -> None:
        """
        Record a failed poll for a PaSD device.

        Increments the cumulative counter for the device, appends a
        timestamp to its sliding window, and emits a snapshot if the
        resulting state differs from the previous one.

        :param device_id: id of the PaSD device whose poll just failed.
        """
        now = time.monotonic()
        with self._lock:
            if device_id == PasdData.FNDH_DEVICE_ID:
                self._fndh_total += 1
                self._fndh_timestamps.append(now)
            elif device_id == PasdData.FNCC_DEVICE_ID:
                self._fncc_total += 1
                self._fncc_timestamps.append(now)
            elif 1 <= device_id <= PasdData.MAX_NUMBER_OF_SMARTBOXES_PER_STATION:
                sb_id = device_id - 1
                self._smartbox_totals[sb_id] += 1
                self._smartbox_timestamps[sb_id].append(now)
            else:
                self._logger.warning(
                    f"Ignoring poll failure for unknown device id {device_id}"
                )
                return
            self._emit_snapshot()

    def _emit_snapshot(self: PollFailureTracker) -> None:
        """
        Prune expired timestamps and emit a snapshot if it changed.

        Caller must hold ``self._lock``.
        """
        cutoff = time.monotonic() - self._window

        def _prune(dq: deque[float]) -> int:
            while dq and dq[0] < cutoff:
                dq.popleft()
            return len(dq)

        snapshot = PollFailureSnapshot(
            fndh_total=self._fndh_total,
            fncc_total=self._fncc_total,
            smartbox_totals=tuple(self._smartbox_totals),
            fndh_in_window=_prune(self._fndh_timestamps),
            fncc_in_window=_prune(self._fncc_timestamps),
            smartbox_in_window=tuple(_prune(dq) for dq in self._smartbox_timestamps),
        )
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        try:
            self._on_changed(snapshot)
        except Exception:  # pylint: disable=broad-except
            self._logger.exception(
                "Poll-failure on_changed callback raised; state still updated."
            )

    def _schedule_prune(self: PollFailureTracker) -> None:
        """Schedule the next prune of the sliding window."""
        if self._stopped:
            return
        timer = threading.Timer(self._prune_interval, self._prune_tick)
        timer.daemon = True
        self._prune_timer = timer
        timer.start()

    def _prune_tick(self: PollFailureTracker) -> None:
        """Run one prune of the sliding window and reschedule itself."""
        try:
            with self._lock:
                if self._stopped:
                    return
                self._emit_snapshot()
        except Exception:  # pylint: disable=broad-except
            self._logger.exception("Failed to prune failed-poll timestamps.")
        finally:
            self._schedule_prune()

    def cleanup(self: PollFailureTracker) -> None:
        """Stop the prune timer and prevent further rescheduling."""
        with self._lock:
            self._stopped = True
            timer = self._prune_timer
            self._prune_timer = None
        if timer is not None:
            timer.cancel()
