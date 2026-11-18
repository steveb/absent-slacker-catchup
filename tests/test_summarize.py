"""Tests for the summariser."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from datetime import datetime, timezone

from asc import summarize as summarize_module
from asc.summarize import (
    SYSTEM_PROMPT,
    THINK_CLOSE,
    THINK_OPEN,
    SummaryError,
    build_messages,
    split_thinking,
    strip_thinking,
    summarize,
)


def chunk(
    content: str | None = None,
    reasoning: str | None = None,
    finish: str | None = None,
):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)]
    )


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
    assert request["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert request["messages"][1]["role"] == "user"
    assert "<chat>\nchat\n</chat>" in request["messages"][1]["content"]


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


def test_reasoning_exhausting_the_budget_is_reported(monkeypatch, cfg):
    install_fake(monkeypatch, [chunk(reasoning="thinking and thinking", finish="length")])

    with pytest.raises(SummaryError) as excinfo:
        summarize("chat", cfg)

    message = str(excinfo.value)
    assert str(cfg.max_tokens) in message
    assert "summary.max_tokens" in message


def test_truncated_answer_warns(monkeypatch, cfg, caplog):
    install_fake(monkeypatch, [chunk("partial answer", finish="length")])
    caplog.set_level(logging.WARNING)

    assert summarize("chat", cfg) == "partial answer"
    assert "truncated" in caplog.text


def test_summarize_wraps_request_errors(monkeypatch, cfg):
    def boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.OpenAI", boom)

    with pytest.raises(SummaryError) as excinfo:
        summarize("chat", cfg)

    assert cfg.base_url in str(excinfo.value)
    assert "connection refused" in str(excinfo.value)


def test_system_prompt_requests_a_substantial_brief():
    assert "## Overview" in SYSTEM_PROMPT
    assert "## Key points" in SYSTEM_PROMPT
    assert "## Decisions" in SYSTEM_PROMPT
    assert "## Action items" in SYSTEM_PROMPT
    assert "250-500 words" in SYSTEM_PROMPT
    assert "they/them" in SYSTEM_PROMPT


def test_module_exposes_the_user_template():
    assert "{chat}" in summarize_module.USER_TEMPLATE


def test_messages_include_the_window_context(cfg):
    messages = build_messages(
        "alice said:\nhello",
        cfg,
        channel="#openstack-nova",
        window_start=datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 11, 15, 0, 0, tzinfo=timezone.utc),
        message_count=42,
    )
    user = messages[1]["content"]
    assert "Channel: #openstack-nova" in user
    assert "Messages: 42" in user
    assert "Window: " in user
    assert "alice said:" in user


def test_messages_fall_back_to_the_configured_channel(cfg):
    messages = build_messages("chat", cfg)
    assert f"Channel: {cfg.channel}" in messages[1]["content"]
    assert "the requested period" in messages[1]["content"]


def test_authentication_failure_names_the_key_without_leaking_it(monkeypatch):
    import httpx
    import openai

    from asc.config import Config, key_fingerprint

    def factory(**kwargs):
        raise openai.AuthenticationError(
            "Error code: 401 - Unauthorized",
            response=httpx.Response(
                401, request=httpx.Request("POST", "https://example.test/v1")
            ),
            body=None,
        )

    monkeypatch.setattr("openai.OpenAI", factory)
    with pytest.raises(SummaryError) as excinfo:
        summarize("hello", Config())

    message = str(excinfo.value)
    assert key_fingerprint("test-key") in message
    assert "test-key" not in message
    assert "401" in message
