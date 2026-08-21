# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for pasd_utils."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tango import DevFailed

from ska_low_mccs_pasd.pasd_utils import PasdDatabase


class TestPasdDatabase:
    """
    Tests for PasdDatabase.

    tango.Database() always dials the real Tango database, bypassing
    the file-database mechanism used when a device is run standalone
    (e.g. by tangodocgen). These tests assert that PasdDatabase
    degrades gracefully instead of taking the whole device down when
    that database is unreachable.
    """

    def test_construction_does_not_raise_when_database_unreachable(
        self: TestPasdDatabase,
    ) -> None:
        """Constructing a PasdDatabase must never raise, even with no Tango DB."""
        with patch(
            "ska_low_mccs_pasd.pasd_utils.Database", side_effect=DevFailed("no db")
        ):
            database = PasdDatabase()
            assert database._get_database() is None

    def test_put_value_survives_devfailed(self: TestPasdDatabase) -> None:
        """put_value() must not raise when the Tango DB is unreachable."""
        with patch(
            "ska_low_mccs_pasd.pasd_utils.Database", side_effect=DevFailed("no db")
        ):
            PasdDatabase().put_value("test/device/1", {"thresholds": [1, 2, 3]})

    def test_get_value_returns_none_when_unavailable(
        self: TestPasdDatabase,
    ) -> None:
        """get_value() must return None when the Tango DB is unreachable."""
        with patch(
            "ska_low_mccs_pasd.pasd_utils.Database", side_effect=DevFailed("no db")
        ):
            value = PasdDatabase().get_value("test/device/1", "thresholds")
        assert value is None

    def test_clear_thresholds_survives_devfailed(self: TestPasdDatabase) -> None:
        """clear_thresholds() must not raise when the Tango DB is unreachable."""
        with patch(
            "ska_low_mccs_pasd.pasd_utils.Database", side_effect=DevFailed("no db")
        ):
            PasdDatabase().clear_thresholds("test/device/1", {"thresholds": [1, 2, 3]})

    def test_connection_is_retried_lazily(self: TestPasdDatabase) -> None:
        """A later call retries the connection, rather than caching the failure."""
        with patch(
            "ska_low_mccs_pasd.pasd_utils.Database", side_effect=DevFailed("no db")
        ) as mock_database:
            database = PasdDatabase()
            database.get_value("test/device/1", "thresholds")
            database.get_value("test/device/1", "thresholds")
        assert mock_database.call_count == 2

    def test_put_value_delegates_to_database_when_available(
        self: TestPasdDatabase,
    ) -> None:
        """put_value() writes through to the Tango database when it is reachable."""
        mock_db_instance = MagicMock()
        with patch(
            "ska_low_mccs_pasd.pasd_utils.Database", return_value=mock_db_instance
        ):
            PasdDatabase().put_value("test/device/1", {"thresholds": [1, 2, 3]})
        mock_db_instance.put_device_attribute_property.assert_called_once_with(
            "test/device/1", {"cache_threshold": {"thresholds": [1, 2, 3]}}
        )
