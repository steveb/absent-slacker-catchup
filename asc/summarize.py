"""Summarise a chat log with an OpenAI-compatible chat completion endpoint."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from datetime import datetime

from .config import Config
from .timeutil import format_local

LOG = logging.getLogger(__name__)

# The instructions below target a capable hosted model (DeepSeek V4.1 Flash by
# default). They are deliberately explicit about structure and length: the
# previous prompt was tuned for a small local model and produced one or two
# terse bullets, which is not a useful catch-up for someone who was away.
SYSTEM_PROMPT = """You are an experienced OpenStack engineer writing a catch-up \
brief for a colleague who missed an IRC channel window. They know the project \
well: do not explain basics, do not restate the transcript message by message, \
and do not describe what you are doing.

Write in English as Markdown. Always use they/them pronouns for the people in \
the log. Use the first name or nickname they use in the channel.

Structure the brief like this, with these exact headings, and omit a heading \
when it has nothing under it:

## Overview
Two to four sentences on what the window was about and what changed.

## Key points
The substantive discussion, grouped by topic rather than by time. Give enough \
detail that the reader understands what was proposed, argued or investigated, \
and why. Cover every topic that had real discussion, not just the loudest one.

## Decisions
Anything that was agreed, concluded or settled.

## Action items
Who is doing what, plus reviews, bugs or follow-ups that were requested. Name \
the person where the log makes the owner clear.

## Open questions
Unresolved questions or disagreements that still need an answer.

## Links
Notable URLs from the log, each with a few words on why it matters. Keep the \
full URL so it stays clickable.

Guidelines:
- Let the material set the length: a quiet window gets a couple of sentences, \
a normal day is usually 250-500 words, and a busy multi-day window can be \
longer. Never pad and never repeat a point to fill space.
- Prefer concrete specifics (names, services, bugs, commands, numbers, review \
links) over generic statements.
- Quote a short phrase only when the exact wording matters.
- Never invent people, numbers, links, decisions or outcomes. If something in \
the log is ambiguous or unresolved, say that plainly.
- Do not add a title, a preamble, a closing remark, or a statement that this \
is a summary.
"""

USER_TEMPLATE = """Channel: {channel}
Window: {window}
Messages: {message_count}

<chat>
{chat}
</chat>

Write the catch-up brief for this window.
"""

# Reasoning models may wrap their scratch pad in these tags. They are assembled
# from fragments so the tags do not appear literally in this source file.
THINK_OPEN = "<" + "think" + ">"
THINK_CLOSE = "<" + "/think" + ">"

_THINKING_RE = re.compile(
    re.escape(THINK_OPEN) + r"(.*?)" + re.escape(THINK_CLOSE), re.DOTALL
)


class SummaryError(RuntimeError):
    """Raised when the summariser fails."""


def strip_thinking(text: str) -> str:
    """Drop any reasoning block from ``text``."""
    return _THINKING_RE.sub("", text)


def split_thinking(summary: str) -> tuple[str, str]:
    """Split a model response into ``(thinking, answer)``.

    Models that expose a reasoning block wrap it in ``THINK_OPEN`` and
    ``THINK_CLOSE``; anything else is treated as the answer.
    """
    matches = list(_THINKING_RE.finditer(summary))
    if matches:
        thinking = "\n".join(
            match.group(1).strip() for match in matches if match.group(1).strip()
        )
        answer = summary[matches[-1].end() :].strip()
        return thinking, answer
    # Unclosed reasoning block: nothing but the scratch pad so far.
    if THINK_OPEN in summary:
        return summary.strip(), ""
    return "", summary.strip()


def _window_label(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None:
        return "the requested period"
    return f"{format_local(start)} to {format_local(end)}"


def build_messages(
    chat_text: str,
    cfg: Config,
    *,
    channel: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    message_count: int | None = None,
) -> list[dict[str, str]]:
    """Build the system/user message pair sent to the endpoint."""
    prompt = USER_TEMPLATE.format(
        channel=channel or cfg.channel,
        window=_window_label(window_start, window_end),
        message_count=message_count if message_count is not None else "unknown",
        chat=chat_text,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def _api_key(cfg: Config) -> str:
    key = os.environ.get(cfg.api_key_env, "").strip()
    if not key:
        raise SummaryError(
            f"{cfg.api_key_env} is not set; export it, or point "
            "summary.api_key_env at the variable that holds the key"
        )
    return key


def summarize(
    chat_text: str,
    cfg: Config,
    *,
    channel: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    message_count: int | None = None,
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Ask the configured endpoint for a summary of ``chat_text``.

    ``on_token`` is called for each streamed chunk of the answer, so callers
    can echo the summary while it is generated. Any separate reasoning the
    model streams is wrapped in the ``think`` tags and returned with the answer
    so :func:`split_thinking` can present it.
    """
    import openai

    api_key = _api_key(cfg)
    messages = build_messages(
        chat_text,
        cfg,
        channel=channel,
        window_start=window_start,
        window_end=window_end,
        message_count=message_count,
    )
    answer: list[str] = []
    thinking: list[str] = []
    finish_reason: str | None = None

    try:
        client = openai.OpenAI(
            base_url=cfg.base_url,
            api_key=api_key,
            timeout=cfg.request_timeout,
        )
        stream = client.chat.completions.create(
            model=cfg.summary_model,
            messages=messages,
            stream=True,
            max_tokens=cfg.max_tokens,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = choice.delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                thinking.append(reasoning)
            content = getattr(delta, "content", None)
            if content:
                answer.append(content)
                if on_token is not None:
                    on_token(content)
    except Exception as exc:
        raise SummaryError(
            f"summary request to {cfg.base_url} failed: {exc}"
        ) from exc

    text = "".join(answer).strip()
    if not text:
        if finish_reason == "length":
            raise SummaryError(
                f"the model spent the whole {cfg.max_tokens} token budget on "
                "reasoning without writing an answer; raise summary.max_tokens"
            )
        raise SummaryError("the summariser returned an empty response")
    if finish_reason == "length":
        LOG.warning(
            "summary was truncated at summary.max_tokens=%d tokens", cfg.max_tokens
        )
    if thinking:
        return f"{THINK_OPEN}{''.join(thinking).strip()}{THINK_CLOSE}{text}"
    return text
