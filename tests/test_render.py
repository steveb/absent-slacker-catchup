"""Tests for the HTML and JSON rendering."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from asc.models import ChatLog, Message, Report
from asc.render import render_page, summary_to_html, write_report

START = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)


def make_report(summary="", thinking=""):
    messages = [
        Message(
            timestamp=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
            nickname="mallory",
            text="<script>alert('xss')</script>",
        ),
        Message(
            timestamp=datetime(2026, 11, 15, 10, 5, tzinfo=timezone.utc),
            nickname="alice",
            text="hello",
        ),
    ]
    log = ChatLog(
        channel="#openstack-ironic",
        window_start=START,
        window_end=END,
        messages=messages,
        nicknames={"mallory", "alice"},
    )
    return Report(log=log, summary=summary, thinking=thinking)


def test_chat_text_is_escaped(cfg):
    html = render_page(make_report(), cfg)

    assert "&lt;script&gt;" in html
    assert "<script>alert('xss')</script>" not in html
    assert "mallory" in html


def test_chat_urls_are_hyperlinked(cfg):
    log = ChatLog(
        channel="#openstack-ironic",
        window_start=START,
        window_end=END,
        messages=[
            Message(
                timestamp=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
                nickname="alice",
                text="review at https://review.opendev.org/c/openstack/ironic/+/1",
            )
        ],
        nicknames={"alice"},
    )

    html = render_page(Report(log=log), cfg)

    assert '<a href="https://review.opendev.org/c/openstack/ironic/+/1"' in html


def test_summary_urls_are_hyperlinked(cfg):
    html = render_page(
        make_report(summary="see https://bugs.launchpad.net/ironic/+bug/1"),
        cfg,
        include_summary=True,
    )

    assert '<a href="https://bugs.launchpad.net/ironic/+bug/1"' in html


def test_summary_reference_numbers_are_linked(cfg):
    html = render_page(
        make_report(summary="Ironic change 1013352 and bug 2123456"),
        cfg,
        include_summary=True,
    )

    assert '<a href="https://review.opendev.org/c/1013352"' in html
    assert '<a href="https://bugs.launchpad.net/ironic/+bug/2123456"' in html


def test_all_links_open_in_a_new_tab(cfg):
    html = render_page(
        make_report(summary="change 1013352 and https://example.com/x"),
        cfg,
        include_summary=True,
    )

    assert '<base target="_blank">' in html
    anchors = BeautifulSoup(html, "html.parser").find_all("a")
    assert anchors
    assert all(anchor.get("target") == "_blank" for anchor in anchors)


def test_thinking_urls_are_hyperlinked(cfg):
    html = render_page(
        make_report(summary="done", thinking="checked https://example.com/build/1"),
        cfg,
        include_summary=True,
    )

    assert '<a href="https://example.com/build/1"' in html


def test_summary_markdown_is_rendered(cfg):
    html = render_page(
        make_report(summary="* one\n* two", thinking="because"),
        cfg,
        include_summary=True,
    )

    assert "<li>one</li>" in html
    assert "<li>two</li>" in html
    assert "because" in html
    assert "<h2>Summary</h2>" in html


def test_audio_is_linked(cfg):
    html = render_page(
        make_report(summary="text"), cfg, include_summary=True, include_audio=True
    )
    assert '<audio src="summary.wav"' not in html
    assert "<audio" not in html

    html = render_page(
        make_report(summary="text"),
        cfg,
        include_summary=True,
        include_audio=True,
        audio_href="summary.wav",
    )
    assert '<audio src="summary.wav"' in html


def test_ignored_messages_are_shown_dimmed(cfg):
    ignored = Message(
        timestamp=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
        nickname="opendevreview",
        text="proposed a change",
        ignored=True,
    )
    log = ChatLog(
        channel="#openstack-ironic",
        window_start=START,
        window_end=END,
        messages=[ignored],
        nicknames={"opendevreview"},
    )

    html = render_page(Report(log=log), cfg)

    assert 'class="ignored"' in html
    assert "proposed a change" in html
    assert "nothing to summarize" in html


def test_errors_are_reported_in_the_page(cfg):
    report = make_report()
    report.errors.append("summary endpoint: unavailable")

    html = render_page(report, cfg)

    assert "This report is incomplete" in html
    assert "summary endpoint: unavailable" in html


def test_empty_window_renders_a_notice(cfg):
    log = ChatLog(
        channel="#openstack-ironic",
        window_start=START,
        window_end=END,
    )
    html = render_page(Report(log=log), cfg)

    assert "No messages in this window." in html


def test_summary_to_html_uses_markdown():
    assert summary_to_html("**bold**") == "<p><strong>bold</strong></p>"


def test_write_report_creates_the_run_and_latest(cfg, tmp_path):
    report = make_report(summary="* one")
    report.audio_file = "summary.wav"
    run_dir = tmp_path / "output" / "#openstack-ironic-2026-11-15-11-00-00"

    paths = write_report(
        report,
        cfg,
        run_dir,
        include_summary=True,
        include_audio=True,
        write_json=True,
    )

    assert paths["chat"].read_text(encoding="utf-8")
    assert paths["html"].exists()
    assert paths["latest"] == tmp_path / "output" / "latest.html"
    assert paths["json"].exists()
    assert paths["audio"] == run_dir / "summary.wav"

    latest = paths["latest"].read_text(encoding="utf-8")
    assert f"{run_dir.name}/summary.wav" in latest
    assert 'src="summary.wav"' in paths["html"].read_text(encoding="utf-8")

    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["channel"] == "#openstack-ironic"
    assert data["message_count"] == 2
    assert data["summary"] == "* one"
    assert data["audio_file"] == "summary.wav"
