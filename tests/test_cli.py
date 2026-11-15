"""Tests for the CLI wiring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from asc import cli
from asc.config import Config
from asc.models import ChatLog, Message
from asc.summarize import SummaryError

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def fake_log() -> ChatLog:
    return ChatLog(
        channel="#openstack-ironic",
        window_start=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc),
        messages=[
            Message(
                timestamp=datetime(2026, 11, 15, 10, 30, tzinfo=timezone.utc),
                nickname="alice",
                text="morning",
            )
        ],
        nicknames={"alice"},
    )


@pytest.fixture(autouse=True)
def headless(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)


def test_defaults_to_the_configured_window():
    args = cli.build_parser().parse_args(["fetch"])
    cfg = Config()
    cli._apply_overrides(cfg, args)
    assert cli._resolve_since(args, NOW, cfg) == datetime(
        2026, 11, 14, 22, 0, tzinfo=timezone.utc
    )


def test_explicit_since_wins():
    args = cli.build_parser().parse_args(["fetch", "--since", "2026-11-14T06:00:00Z"])
    since = cli._resolve_since(args, NOW, Config())
    assert since == datetime(2026, 11, 14, 6, 0, tzinfo=timezone.utc)


def test_future_since_is_rejected():
    args = cli.build_parser().parse_args(["fetch", "--since", "2027-01-01T00:00:00Z"])
    with pytest.raises(SystemExit):
        cli._resolve_since(args, NOW, Config())


def test_invalid_since_is_rejected():
    args = cli.build_parser().parse_args(["fetch", "--since", "yesterday"])
    with pytest.raises(SystemExit):
        cli._resolve_since(args, NOW, Config())


def test_overrides():
    args = cli.build_parser().parse_args(
        [
            "fetch",
            "#openstack-nova",
            "--hours",
            "48",
            "--output-dir",
            "/tmp/out",
            "--output-type",
            "SUMMARY",
            "--ignore-nicks",
            "bot1",
            "bot2",
            "--summary-model",
            "tiny",
            "--tts-model",
            "voice.onnx",
            "--tts-model-dir",
            "/models",
            "--json",
            "--no-open",
        ]
    )
    cfg = Config()
    cli._apply_overrides(cfg, args)

    assert cfg.channel == "#openstack-nova"
    assert cfg.window_hours == 48
    assert cfg.output_dir == Path("/tmp/out")
    assert cfg.output_type == "SUMMARY"
    assert cfg.ignore_nicks == ["bot1", "bot2"]
    assert cfg.summary_model == "tiny"
    assert cfg.tts_model == "voice.onnx"
    assert cfg.tts_model_dir == Path("/models")
    assert cfg.write_json is True
    assert cfg.open_browser is False


def test_legacy_flags_still_work():
    args = cli.build_parser().parse_args(
        ["fetch", "--output-directory", "/tmp/out", "--open-browser"]
    )
    cfg = Config()
    cli._apply_overrides(cfg, args)
    assert cfg.output_dir == Path("/tmp/out")
    assert cfg.open_browser is True


def test_non_positive_window_is_rejected():
    args = cli.build_parser().parse_args(["fetch", "--hours", "0"])
    with pytest.raises(SystemExit):
        cli._apply_overrides(Config(), args)


def test_browser_auto_detection(monkeypatch):
    assert cli._should_open_browser(Config()) is False
    monkeypatch.setenv("DISPLAY", ":0")
    assert cli._should_open_browser(Config()) is True

    forced_off = Config(open_browser=False)
    assert cli._should_open_browser(forced_off) is False


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 1
    assert "usage:" in capsys.readouterr().out.lower()


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "asc 0.1.0" in capsys.readouterr().out


def test_unknown_command_exits_with_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["nonsense"])
    assert excinfo.value.code == 2


def test_status_reports_configuration(capsys):
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "asc 0.1.0" in out
    assert "#openstack-ironic" in out
    assert "voice model" in out


def test_fetch_writes_a_run_directory(monkeypatch, cfg, tmp_path, capsys):
    monkeypatch.setattr(cli, "collect", lambda client, config, since, now: (fake_log(), []))

    result = cli.main(
        ["fetch", "--hours", "1", "--output-dir", str(tmp_path)]
    )

    assert result == 0
    runs = list(tmp_path.glob("openstack-ironic-*"))
    assert len(runs) == 1
    assert (runs[0] / "chat.txt").exists()
    assert (runs[0] / "summary.html").exists()
    assert (tmp_path / "latest.html").exists()
    assert "Summary:" in capsys.readouterr().out


def test_fetch_json_twin(monkeypatch, cfg, tmp_path):
    monkeypatch.setattr(cli, "collect", lambda client, config, since, now: (fake_log(), []))

    cli.main(["fetch", "--hours", "1", "--output-dir", str(tmp_path), "--json"])

    run_dir = next(tmp_path.glob("openstack-ironic-*"))
    data = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert data["message_count"] == 1


def test_fetch_stdout_prints_html(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "collect", lambda client, config, since, now: (fake_log(), []))

    result = cli.main(
        ["fetch", "--hours", "1", "--output-dir", str(tmp_path), "--stdout"]
    )

    assert result == 0
    assert "<!DOCTYPE html>" in capsys.readouterr().out
    assert not list(tmp_path.glob("openstack-ironic-*"))


def test_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "collect", lambda client, config, since, now: (fake_log(), []))

    result = cli.main(
        ["fetch", "--hours", "1", "--output-dir", str(tmp_path), "--dry-run"]
    )

    assert result == 0
    assert "messages 1" in capsys.readouterr().out
    assert not list(tmp_path.glob("openstack-ironic-*"))


def test_collect_errors_set_the_exit_status(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli, "collect", lambda client, config, since, now: (fake_log(), ["boom"])
    )

    result = cli.main(
        ["fetch", "--hours", "1", "--output-dir", str(tmp_path), "--quiet"]
    )

    assert result == 1
    html = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "This report is incomplete" in html
    assert "boom" in html


def test_summary_failure_keeps_the_chat_page(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "collect", lambda client, config, since, now: (fake_log(), []))

    def boom(*args, **kwargs):
        raise SummaryError("ollama is down")

    monkeypatch.setattr(cli, "summarize", boom)

    result = cli.main(
        [
            "fetch",
            "--hours",
            "1",
            "--output-dir",
            str(tmp_path),
            "--output-type",
            "SPEECH_SUMMARY",
        ]
    )

    assert result == 1
    html = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "ollama is down" in html
    assert "<h2>Summary</h2>" not in html
    assert "Summary:" in capsys.readouterr().out


def test_empty_window_skips_the_summary(monkeypatch, tmp_path):
    empty = ChatLog(
        channel="#openstack-ironic",
        window_start=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(cli, "collect", lambda client, config, since, now: (empty, []))

    def fail(*args, **kwargs):
        raise AssertionError("summarize should not run for an empty window")

    monkeypatch.setattr(cli, "summarize", fail)

    result = cli.main(
        [
            "fetch",
            "--hours",
            "1",
            "--output-dir",
            str(tmp_path),
            "--output-type",
            "SUMMARY",
        ]
    )

    assert result == 0
    html = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "No messages in this window." in html
