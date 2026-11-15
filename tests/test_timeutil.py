"""Tests for the timestamp helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from asc.timeutil import (
    ensure_utc,
    iso_utc,
    local_stamp,
    parse_timestamp,
    utcnow,
    window_start,
)


def test_naive_values_are_assumed_utc():
    naive = datetime(2026, 11, 15, 10, 0)
    assert ensure_utc(naive) == datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)


def test_aware_values_are_converted():
    value = datetime(2026, 11, 15, 23, 0, tzinfo=timezone(timedelta(hours=13)))
    assert ensure_utc(value) == datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)


def test_window_start_subtracts_hours():
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    assert window_start(now, 14) == datetime(
        2026, 11, 14, 22, 0, tzinfo=timezone.utc
    )


def test_parse_timestamp_accepts_z_suffix():
    assert parse_timestamp("2026-11-14T06:00:00Z") == datetime(
        2026, 11, 14, 6, 0, tzinfo=timezone.utc
    )


def test_parse_timestamp_accepts_offsets():
    assert parse_timestamp("2026-11-14T19:00:00+13:00") == datetime(
        2026, 11, 14, 6, 0, tzinfo=timezone.utc
    )


def test_iso_utc_round_trips():
    value = datetime(2026, 11, 15, 10, 30, tzinfo=timezone.utc)
    assert iso_utc(value) == "2026-11-15T10:30:00Z"


def test_local_stamp_shape():
    stamp = local_stamp(utcnow())
    datetime.strptime(stamp, "%Y-%m-%d-%H-%M-%S")
