"""Tests for the message view used by the HTML template."""

from __future__ import annotations

from datetime import datetime, timezone

from asc.models import Message


def test_message_view_uses_the_local_timezone(set_timezone):
    set_timezone("Pacific/Auckland")
    message = Message(
        timestamp=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
        nickname="alice",
        text="hello",
    )

    view = message.view()

    assert view["time"] == "23:00"
    assert view["timestamp"] == "Sun 15 Nov 23:00 NZDT"
    # The anchor stays UTC so it does not change with the viewer's timezone.
    assert view["anchor"] == "2026-11-15T10:00:00"
