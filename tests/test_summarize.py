"""Tests for the summariser."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from asc import summarize as summarize_module
from asc.summarize import (
    THINK_CLOSE,
    THINK_OPEN,
    SummaryError,
    split_thinking,
    strip_thinking,
    summarize,
)


def chunk(content: str | None = None, reasoning: str | None = None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class FakeEndpoint:
    """A stand-in for ``openai.OpenAI`` that records the call arguments."""

    def __init__(self, chunks, calls):
        self.chunks = chunks
        self.calls = calls
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls["create"] = kwargs
        return iter(self.chunks)


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("ENMAAS_KEY", "test-key")


def install_fake(monkeypatch, chunks):
    calls: dict = {}

    def factory(**kwargs):
        calls["client"] = kwargs
        return FakeEndpoint(chunks, calls)

    monkeypatch.setattr("openai.OpenAI", factory)
    return calls


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


def test_summarize_streams_the_answer(monkeypatch, cfg):
    calls = install_fake(monkeypatch, [chunk("hello "), chunk("world")])

    tokens: list[str] = []
    result = summarize("chat", cfg, on_token=tokens.append)

    assert result == "hello world"
    assert tokens == ["hello ", "world"]
    assert calls["client"] == {
        "base_url": cfg.base_url,
        "api_key": "test-key",
        "timeout": cfg.request_timeout,
    }
    request = calls["create"]
    assert request["model"] == cfg.summary_model
    assert request["stream"] is True
    assert request["max_tokens"] == cfg.max_tokens
    assert request["messages"][0]["role"] == "user"
    assert "<chat>\nchat\n</chat>" in request["messages"][0]["content"]


def test_summarize_surfaces_separate_reasoning(monkeypatch, cfg):
    calls = install_fake(
        monkeypatch,
        [chunk(reasoning="thinking hard"), chunk("the answer")],
    )

    tokens: list[str] = []
    raw = summarize("chat", cfg, on_token=tokens.append)

    assert tokens == ["the answer"]
    assert raw.startswith(THINK_OPEN)
    assert raw.endswith("the answer")
    assert split_thinking(raw) == ("thinking hard", "the answer")
    assert calls["create"]["model"] == "rits/deepseek-ai/DeepSeek-V4.1-Flash-1017"


def test_summarize_requires_the_api_key(monkeypatch, cfg):
    monkeypatch.delenv("ENMAAS_KEY", raising=False)

    with pytest.raises(SummaryError) as excinfo:
        summarize("chat", cfg)

    assert "ENMAAS_KEY is not set" in str(excinfo.value)


def test_summarize_ignores_chunks_without_choices(monkeypatch, cfg):
    install_fake(
        monkeypatch,
        [SimpleNamespace(choices=[]), chunk("fine")],
    )

    assert summarize("chat", cfg) == "fine"


def test_summarize_empty_response_raises(monkeypatch, cfg):
    install_fake(monkeypatch, [])

    with pytest.raises(SummaryError) as excinfo:
        summarize("chat", cfg)

    assert "empty response" in str(excinfo.value)


def test_summarize_wraps_request_errors(monkeypatch, cfg):
    def boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.OpenAI", boom)

    with pytest.raises(SummaryError) as excinfo:
        summarize("chat", cfg)

    assert cfg.base_url in str(excinfo.value)
    assert "connection refused" in str(excinfo.value)


def test_module_exposes_the_prompt():
    assert "{chat}" in summarize_module.SUMMARY_PROMPT
