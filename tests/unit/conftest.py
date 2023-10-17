# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains pytest-specific test harness for MCCS unit tests."""

import pytest
from ska_tango_testing.mock import MockCallableGroup


@pytest.fixture(name="mock_callbacks")
def mock_callbacks_fixture() -> MockCallableGroup:
    """
    Return a group of callables with asynchrony support.

    These can be used in tests as callbacks. When the production code
    expects to be passed a callback, we pass it a member of this group,
    and we can then assert on the order and timing of calls.

    :return: a group of callables ith asynchrony support.
    """
    return MockCallableGroup(
        "communication_state",
        "component_state",
        "pasd_device_state",
        "attribute_update",
        "port_power_state",
        "task",
        timeout=10.0,
    )
