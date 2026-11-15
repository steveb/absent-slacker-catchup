"""Summarise a chat log with a local model served by ollama."""

from __future__ import annotations

import logging
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


def summarize(
    chat_text: str,
    cfg: Config,
    *,
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Ask ollama for a summary of ``chat_text``.

    ``on_token`` is called for each streamed chunk so callers can echo the
    summary while it is generated.
    """
    import ollama

    prompt = SUMMARY_PROMPT.format(chat=chat_text)
    options = {"num_predict": cfg.num_predict}
    try:
        if cfg.ollama_host:
            client = ollama.Client(host=cfg.ollama_host)
            stream = client.chat(
                cfg.summary_model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options=options,
            )
        else:
            stream = ollama.chat(
                cfg.summary_model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options=options,
            )
        summary = ""
        for chunk in stream:
            content = chunk["message"]["content"]
            summary += content
            if on_token is not None:
                on_token(content)
    except Exception as exc:  # ollama raises its own error hierarchy
        raise SummaryError(f"ollama summarisation failed: {exc}") from exc
    if not summary.strip():
        raise SummaryError("ollama returned an empty summary")
    return summary
