"""Tests for the IRC log collector."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asc.http import HttpError
from asc.logs import collect, log_url, parse_log_html

WINDOW_END = datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)
WINDOW_START = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class FakeClient:
    """Returns canned pages and records the URLs it was asked for."""

    def __init__(self, pages, default_status: int = 404):
        self.pages = pages
        self.default_status = default_status
        self.requested: list[str] = []

    def get(self, url, params=None, allow_status=()):
        self.requested.append(url)
        page = self.pages.get(url)
        if page is None:
            return FakeResponse("", status_code=self.default_status)
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)


def test_log_url_quotes_the_channel():
    url = log_url(
        "https://meetings.opendev.org/irclogs/",
        "#openstack-ironic",
        datetime(2026, 11, 15),
    )
    assert url == (
        "https://meetings.opendev.org/irclogs/%23openstack-ironic/"
        "%23openstack-ironic.2026-11-15.log.html"
    )


def test_parse_log_html_extracts_messages(load_fixture):
    messages = list(parse_log_html(load_fixture("irclog-2026-11-12.html")))
    assert len(messages) > 50
    first = messages[0]
    assert first.nickname == "opendevreview"
    assert first.timestamp == datetime(2026, 11, 12, 7, 44, 28, tzinfo=timezone.utc)
    assert "Add warm available configuration" in first.text


def test_parse_log_html_skips_malformed_rows(load_fixture):
    messages = list(parse_log_html(load_fixture("irclog-synthetic.html")))
    assert [message.nickname for message in messages] == [
        "alice",
        "bob",
        "opendevreview",
        "mallory",
        "build-bot",
        "carol",
    ]


def test_parse_log_html_without_table_is_empty():
    assert list(parse_log_html("<html><body>nothing</body></html>")) == []


def test_collect_filters_bots_and_the_window(cfg, load_fixture):
    cfg.max_days = 1
    start = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 11, 12, 23, 59, tzinfo=timezone.utc)
    url = log_url(cfg.irclog_base_url, cfg.channel, start)
    client = FakeClient({url: load_fixture("irclog-2026-11-12.html")})

    log, errors = collect(client, cfg, start, end)

    assert errors == []
    assert log.nicknames == {"JayF", "TheJulia", "stephenfin", "cardoe", "cid"}
    assert "opendevreview" not in log.nicknames
    assert len(client.requested) == 1


def test_collect_drops_messages_outside_the_window(cfg):
    cfg.max_days = 1
    html = (
        '<table class="irclog">'
        '<tr id="t2026-11-15T08:59:59"><th class="nick">early</th>'
        '<td class="text">before</td></tr>'
        '<tr id="t2026-11-15T09:30:00"><th class="nick">inside</th>'
        '<td class="text">during</td></tr>'
        "</table>"
    )
    url = log_url(cfg.irclog_base_url, cfg.channel, WINDOW_START)
    log, _ = collect(FakeClient({url: html}), cfg, WINDOW_START, WINDOW_END)
    assert [message.nickname for message in log.messages] == ["inside"]


def test_collect_stops_at_the_first_missing_day(cfg, load_fixture):
    cfg.max_days = 10
    first = log_url(cfg.irclog_base_url, cfg.channel, WINDOW_START)
    client = FakeClient({first: load_fixture("irclog-synthetic.html")})

    _, errors = collect(client, cfg, WINDOW_START, WINDOW_END)

    assert errors == []
    assert len(client.requested) == 1


def test_collect_honours_max_days(cfg):
    cfg.max_days = 2
    start = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 11, 15, 0, 0, tzinfo=timezone.utc)
    client = FakeClient({}, default_status=200)
    _, errors = collect(client, cfg, start, end)
    assert errors == []
    assert len(client.requested) == 2


def test_collect_records_http_errors(cfg):
    cfg.max_days = 1
    url = log_url(cfg.irclog_base_url, cfg.channel, WINDOW_START)
    client = FakeClient({url: HttpError("boom", url=url)})

    log, errors = collect(client, cfg, WINDOW_START, WINDOW_END)

    assert log.messages == []
    assert errors == [f"2026-11-15: boom"]


@pytest.mark.parametrize(
    "channel,slug",
    [("#openstack-ironic", "%23openstack-ironic")],
)
def test_log_url_uses_the_quoted_slug(channel, slug):
    assert slug in log_url("https://example.com/irclogs", channel, WINDOW_START)
