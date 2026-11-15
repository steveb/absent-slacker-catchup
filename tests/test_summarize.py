"""Tests for the ollama summariser."""

from __future__ import annotations

import pytest

from asc import summarize as summarize_module
from asc.config import Config
from asc.summarize import (
    THINK_CLOSE,
    THINK_OPEN,
    SummaryError,
    split_thinking,
    strip_thinking,
    summarize,
)


def test_split_thinking_without_reasoning():
    assert split_thinking("just the answer") == ("", "just the answer")


def test_split_thinking_extracts_the_reasoning():
    raw = f"{THINK_OPEN}step one{THINK_CLOSE}the answer"
    assert split_thinking(raw) == ("step one", "the answer")


def test_split_thinking_handles_several_blocks():
    raw = f"{THINK_OPEN}one{THINK_CLOSE}{THINK_OPEN}two{THINK_CLOSE}answer"
    assert split_thinking(raw) == ("one\ntwo", "answer")


def test_split_thinking_with_unclosed_block():
    raw = f"{THINK_OPEN}still thinking"
    thinking, answer = split_thinking(raw)
    assert thinking == raw
    assert answer == ""


def test_strip_thinking():
    raw = f"before{THINK_OPEN}secret{THINK_CLOSE}after"
    assert strip_thinking(raw) == "beforeafter"


def test_summarize_streams_tokens(monkeypatch, cfg):
    calls = {}

    def fake_chat(model, **kwargs):
        calls["model"] = model
        calls.update(kwargs)
        return iter(
            [
                {"message": {"content": "hello "}},
                {"message": {"content": "world"}},
            ]
        )

    monkeypatch.setattr("ollama.chat", fake_chat)

    tokens: list[str] = []
    result = summarize("chat", cfg, on_token=tokens.append)

    assert result == "hello world"
    assert tokens == ["hello ", "world"]
    assert calls["model"] == cfg.summary_model
    assert calls["stream"] is True
    assert calls["options"] == {"num_predict": cfg.num_predict}
    assert calls["messages"][0]["role"] == "user"
    assert "<chat>\nchat\n</chat>" in calls["messages"][0]["content"]


def test_summarize_uses_configured_host(monkeypatch, cfg):
    cfg.ollama_host = "http://ollama.example:11434"
    seen = {}

    class FakeClient:
        def __init__(self, host):
            seen["host"] = host

        def chat(self, model, **kwargs):
            return iter([{"message": {"content": "ok"}}])

    monkeypatch.setattr("ollama.Client", FakeClient)

    assert summarize("chat", cfg) == "ok"
    assert seen["host"] == cfg.ollama_host


def test_summarize_empty_response_raises(monkeypatch, cfg):
    monkeypatch.setattr("ollama.chat", lambda *a, **k: iter([]))

    with pytest.raises(SummaryError):
        summarize("chat", cfg)


def test_summarize_wraps_client_errors(monkeypatch, cfg):
    def boom(*args, **kwargs):
        raise RuntimeError("no ollama here")

    monkeypatch.setattr("ollama.chat", boom)

    with pytest.raises(SummaryError) as excinfo:
        summarize("chat", cfg)

    assert "no ollama here" in str(excinfo.value)


def test_module_exposes_the_prompt():
    assert "{chat}" in summarize_module.SUMMARY_PROMPT
