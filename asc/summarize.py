"""Summarise a chat log with an OpenAI-compatible chat completion endpoint."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable

from .config import Config

LOG = logging.getLogger(__name__)

SUMMARY_PROMPT = """You are an assistant that summarizes chat logs
without additional commentary.

Use exclusively they/them pronouns when
referring to people in this chat log.

Always reply in English.

Summarize the following chat log:

<chat>
{chat}
</chat>
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
    prompt = SUMMARY_PROMPT.format(chat=chat_text)
    answer: list[str] = []
    thinking: list[str] = []

    try:
        client = openai.OpenAI(
            base_url=cfg.base_url,
            api_key=api_key,
            timeout=cfg.request_timeout,
        )
        stream = client.chat.completions.create(
            model=cfg.summary_model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=cfg.max_tokens,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
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
        raise SummaryError("the summariser returned an empty response")
    if thinking:
        return f"{THINK_OPEN}{''.join(thinking).strip()}{THINK_CLOSE}{text}"
    return text
