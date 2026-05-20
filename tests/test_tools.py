# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module provides a set of useful methods for testing."""
from __future__ import annotations

import json
import time
from typing import Any

import tango


def get_lrc_finished(
    device_proxy: tango.DeviceProxy,
    uid: str,
) -> dict[str, Any]:
    """
    Return the finished LRC entry matching the given UID.

    Returns an empty dict if no entry with the given UID is found in
    ``lrcfinished``.  The returned dict can be used to make further
    field-level assertions.

    :param device_proxy: device proxy for use in the test.
    :param uid: the UID of the LRC to look up.
    :return: the parsed LRC finished entry, or ``{}`` if not present.
    """
    for completed_task in device_proxy.lrcfinished:
        task_dict = json.loads(completed_task)
        if task_dict["uid"] == uid:
            return task_dict
    return {}


def assert_against_lrc_finished(
    device: tango.DeviceProxy, command_id: str, status: str, timeout: float = 10.0
) -> None:
    """
    Wait for command to finish and assert against the status.

    :param device: the tango device to monitor.
    :param command_id: The command_id to look for in the queue.
    :param status: The expected status of the command in the queue.
    :param timeout: An optional time to wait in seconds.

    :raises TimeoutError: When the command failed to enter the queue in time.
    """
    completed_task = get_lrc_finished(device, command_id)
    start_time = time.time()
    while not completed_task:
        if time.time() - start_time > timeout:
            raise TimeoutError(
                f"LRC '{command_id}' not found in completed after {timeout} seconds"
            )
        time.sleep(0.1)
        completed_task = get_lrc_finished(device, command_id)
    assert completed_task["status"] == status
