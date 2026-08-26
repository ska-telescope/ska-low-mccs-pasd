# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module contains the tests for pasd_utils."""
from __future__ import annotations

import logging
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest
from tango import DevFailed

from ska_low_mccs_pasd.pasd_utils import PasdDatabase, _is_running_without_database

DEV_NAME = "test/device/1"
THRESHOLDS = {"thresholds": [1, 2, 3]}


def _patch_is_running_without_database(file_db: bool) -> Any:
    """
    Patch _is_running_without_database() to return file_db.

    :param file_db: the value it should return.

    :return: a patch context manager.
    """
    return patch(
        "ska_low_mccs_pasd.pasd_utils._is_running_without_database",
        return_value=file_db,
    )


def _patch_database(**kwargs: Any) -> Any:
    """
    Patch the Database class used by PasdDatabase.

    :param kwargs: passed through to unittest.mock.patch.

    :return: a patch context manager.
    """
    return patch("ska_low_mccs_pasd.pasd_utils.Database", **kwargs)


class TestPasdDatabase:
    """Tests for PasdDatabase."""

    @pytest.fixture(name="mock_database")
    def mock_database_fixture(self: TestPasdDatabase) -> Iterator[MagicMock]:
        """
        Patch Database so PasdDatabase connects to a mock instance.

        :yield: the mock database instance.
        """
        mock_db_instance = MagicMock()
        with _patch_database(return_value=mock_db_instance):
            yield mock_db_instance

    @pytest.mark.parametrize(
        ("file_db", "should_raise"),
        [
            pytest.param(True, False, id="file_db_mode_swallows_failure"),
            pytest.param(False, True, id="real_db_mode_propagates_failure"),
        ],
    )
    def test_construction_when_database_unreachable(
        self: TestPasdDatabase, file_db: bool, should_raise: bool
    ) -> None:
        """
        Construction only swallows a connection failure in file-db mode.

        :param file_db: value _is_running_without_database() should return.
        :param should_raise: whether construction is expected to raise.
        """
        with (
            _patch_is_running_without_database(file_db),
            _patch_database(side_effect=DevFailed("no db")),
        ):
            if should_raise:
                with pytest.raises(DevFailed):
                    PasdDatabase()
            else:
                assert PasdDatabase()._database is None

    @pytest.mark.parametrize(
        ("method", "args"),
        [
            pytest.param("put_value", (DEV_NAME, THRESHOLDS), id="put_value"),
            pytest.param("get_value", (DEV_NAME, "thresholds"), id="get_value"),
            pytest.param(
                "clear_thresholds", (DEV_NAME, THRESHOLDS), id="clear_thresholds"
            ),
        ],
    )
    def test_methods_skip_when_database_unavailable(
        self: TestPasdDatabase,
        caplog: pytest.LogCaptureFixture,
        method: str,
        args: tuple,
    ) -> None:
        """
        Every method logs and skips when the database can't be reached.

        :param caplog: pytest fixture that captures log records.
        :param method: name of the PasdDatabase method under test.
        :param args: positional arguments to call it with.
        """
        with (
            _patch_is_running_without_database(True),
            _patch_database(side_effect=DevFailed("no db")),
            caplog.at_level(logging.INFO),
        ):
            database = PasdDatabase()
            result = getattr(database, method)(*args)
        assert result is None
        assert any(f"skipping {method}" in record.message for record in caplog.records)

    @pytest.mark.parametrize(
        ("method", "expected_payload"),
        [
            pytest.param("put_value", THRESHOLDS, id="put_value"),
            pytest.param("clear_thresholds", {"thresholds": []}, id="clear"),
        ],
    )
    def test_write_methods_write_to_database(
        self: TestPasdDatabase,
        mock_database: MagicMock,
        method: str,
        expected_payload: dict,
    ) -> None:
        """
        put_value() and clear_thresholds() write through when reachable.

        :param mock_database: the mock database instance.
        :param method: name of the PasdDatabase method under test.
        :param expected_payload: the payload it should persist.
        """
        getattr(PasdDatabase(), method)(DEV_NAME, THRESHOLDS)
        mock_database.put_device_attribute_property.assert_called_once_with(
            DEV_NAME, {"cache_threshold": expected_payload}
        )

    @pytest.mark.parametrize(
        ("side_effect", "return_value", "expected"),
        [
            pytest.param(None, {"cache_threshold": [1, 2, 3]}, [1, 2, 3], id="ok"),
            pytest.param(DevFailed("read failed"), None, None, id="devfailed"),
        ],
    )
    def test_get_value_reads_from_database(
        self: TestPasdDatabase,
        mock_database: MagicMock,
        side_effect: DevFailed | None,
        return_value: dict | None,
        expected: list | None,
    ) -> None:
        """
        get_value() reads through to the database, returning None on failure.

        :param mock_database: the mock database instance.
        :param side_effect: side effect for get_device_attribute_property.
        :param return_value: return value for get_device_attribute_property.
        :param expected: the value get_value() is expected to return.
        """
        mock_database.get_device_attribute_property.side_effect = side_effect
        mock_database.get_device_attribute_property.return_value = return_value
        value = PasdDatabase().get_value(DEV_NAME, "thresholds")
        assert value == expected

    @pytest.mark.parametrize("method", ["put_value", "clear_thresholds"])
    def test_write_methods_survive_devfailed_during_write(
        self: TestPasdDatabase, mock_database: MagicMock, method: str
    ) -> None:
        """
        put_value() and clear_thresholds() log rather than raise on failure.

        :param mock_database: the mock database instance.
        :param method: name of the PasdDatabase method under test.
        """
        mock_database.put_device_attribute_property.side_effect = DevFailed(
            "write failed"
        )
        getattr(PasdDatabase(), method)(DEV_NAME, THRESHOLDS)


# pylint: disable=too-few-public-methods
class TestIsRunningWithoutDatabase:
    """Tests for the _is_running_without_database() detection helper."""

    @pytest.mark.parametrize(
        ("file_db", "expected"),
        [
            pytest.param(None, False, id="util_singleton_not_created"),
            pytest.param(True, True, id="running_against_file_db"),
            pytest.param(False, False, id="running_against_real_db"),
        ],
    )
    def test_is_running_without_database(
        self: TestIsRunningWithoutDatabase,
        file_db: bool | None,
        expected: bool,
    ) -> None:
        """
        _is_running_without_database() reflects the Util singleton's state.

        :param file_db: the mocked Util singleton's _FileDb attribute, or
            None to simulate no Util singleton existing yet.
        :param expected: the expected return value.
        """
        if file_db is None:
            patched_instance = patch(
                "ska_low_mccs_pasd.pasd_utils.tango.Util.instance",
                side_effect=DevFailed("Util singleton not created"),
            )
        else:
            mock_util = MagicMock()
            mock_util._FileDb = file_db
            patched_instance = patch(
                "ska_low_mccs_pasd.pasd_utils.tango.Util.instance",
                return_value=mock_util,
            )
        with patched_instance:
            assert _is_running_without_database() is expected
