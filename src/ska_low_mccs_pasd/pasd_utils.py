# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides common code for all PaSD devices."""


def join_health_reports(messages: list[str]) -> str:
    """
    Join the messages removing duplicates and empty strings.

    :param messages: a list of messages.

    :returns: a string with result.
    """
    seen = set()
    unique_messages = []

    for message in messages:
        # Ignore empty strings and duplicates
        if message and message not in seen:
            seen.add(message)
            unique_messages.append(message)

    return "\n".join(unique_messages)
