"""Tests for config defaults and TOML overrides."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from asc.config import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_CHANNEL,
    DEFAULT_SUMMARY_BASE_URL,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_TTS_MODEL,
    Config,
    default_config_path,
    load_config,
)


def test_defaults():
    cfg = Config()
    assert cfg.channel == DEFAULT_CHANNEL
    assert cfg.window_hours == 24
    assert cfg.output_type == "CHAT"
    assert cfg.write_json is False
    assert "opendevreview" in cfg.ignore_nicks
    assert cfg.base_url == DEFAULT_SUMMARY_BASE_URL
    assert cfg.summary_model == DEFAULT_SUMMARY_MODEL
    assert cfg.api_key_env == DEFAULT_API_KEY_ENV
    assert cfg.max_tokens == 1024


def test_load_config_without_path_returns_defaults():
    assert load_config(None).channel == DEFAULT_CHANNEL


def test_missing_config_file_is_ignored(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.channel == DEFAULT_CHANNEL
    assert "does not exist" in caplog.text


def test_toml_overrides(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[general]
channel = "#openstack-nova"
window_hours = 3
output_dir = "out"
output_type = "SUMMARY"
write_json = true

[irc]
ignore_nicks = ["someone"]
bot_patterns = ["^bot$"]
max_days = 2

[summary]
base_url = "http://localhost:11434/v1"
model = "tiny"
api_key_env = "OTHER_KEY"
max_tokens = 10

[tts]
model = "voice.onnx"
model_dir = "/models"
""",
        encoding="utf-8",
    )
    cfg = load_config(config)
    assert cfg.channel == "#openstack-nova"
    assert cfg.window_hours == 3.0
    assert cfg.output_dir == Path("out")
    assert cfg.output_type == "SUMMARY"
    assert cfg.write_json is True
    assert cfg.ignore_nicks == ["someone"]
    assert cfg.bot_patterns == ["^bot$"]
    assert cfg.max_days == 2
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.summary_model == "tiny"
    assert cfg.api_key_env == "OTHER_KEY"
    assert cfg.max_tokens == 10
    assert cfg.tts_model == "voice.onnx"
    assert cfg.tts_model_dir == Path("/models")


def test_unknown_sections_and_keys_warn(tmp_path, caplog):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[nonsense]
key = "value"

[general]
unknown = true
channel = "#openstack-ironic"
""",
        encoding="utf-8",
    )
    caplog.set_level(logging.WARNING)
    cfg = load_config(config)
    assert cfg.channel == DEFAULT_CHANNEL
    assert "unknown config section [nonsense]" in caplog.text
    assert "unknown config key general.unknown" in caplog.text


def test_invalid_output_type_falls_back(tmp_path, caplog):
    config = tmp_path / "config.toml"
    config.write_text('[general]\noutput_type = "NOPE"\n', encoding="utf-8")
    caplog.set_level(logging.WARNING)
    cfg = load_config(config)
    assert cfg.output_type == "CHAT"
    assert "unknown output_type" in caplog.text


def test_resolve_tts_model_absolute_path(tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_text("x", encoding="utf-8")
    cfg = Config(tts_model=str(model))
    assert cfg.resolve_tts_model() == model


def test_resolve_tts_model_uses_model_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    models = tmp_path / "models"
    models.mkdir()
    (models / DEFAULT_TTS_MODEL).write_text("x", encoding="utf-8")
    cfg = Config(tts_model_dir=models)
    assert cfg.resolve_tts_model() == models / DEFAULT_TTS_MODEL


def test_resolve_tts_model_falls_back_to_cwd(tmp_path, monkeypatch):
    (tmp_path / "local.onnx").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cfg = Config(tts_model="local.onnx", tts_model_dir=tmp_path / "missing")
    assert cfg.resolve_tts_model() == Path("local.onnx")


def test_resolve_tts_model_missing_returns_candidate(tmp_path):
    cfg = Config(tts_model="absent.onnx", tts_model_dir=tmp_path)
    assert cfg.resolve_tts_model() == Path("absent.onnx")


def test_default_config_path(tmp_path):
    assert default_config_path(tmp_path) is None
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    assert default_config_path(tmp_path) == config
