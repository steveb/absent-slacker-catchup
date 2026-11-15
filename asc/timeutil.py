"""Timestamp parsing and formatting helpers.

The IRC logs record naive local timestamps (``t2024-01-15T14:30:25``); the
window is computed in UTC and rendering happens in the local timezone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime (naive values are assumed UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def window_start(now: datetime, hours: float) -> datetime:
    return ensure_utc(now) - timedelta(hours=hours)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, accepting a trailing ``Z``."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(text))


def iso_utc(value: datetime) -> str:
    """Format a datetime as an ISO-8601 UTC string."""
    return ensure_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_local(value: datetime) -> str:
    """Format a datetime in the local timezone for display."""
    return ensure_utc(value).astimezone().strftime("%a %d %b %H:%M %Z")


def local_stamp(value: datetime) -> str:
    """Return a filesystem friendly datestamp such as ``2024-01-15-14-30-25``."""
    return ensure_utc(value).astimezone().strftime("%Y-%m-%d-%H-%M-%S")
