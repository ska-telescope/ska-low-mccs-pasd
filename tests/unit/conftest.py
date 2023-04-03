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


def pytest_itemcollected(item: pytest.Item) -> None:
    """
    Modify a test after it has been collected by pytest.

    This pytest hook implementation adds the "forked" custom mark to all
    tests that use the ``tango_harness`` fixture, causing them to be
    sandboxed in their own process.

    :param item: the collected test for which this hook is called
    """
    if "tango_harness" in item.listnames():
        item.add_marker("forked")


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
        "task",
    )
