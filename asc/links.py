"""Turn bare URLs into safe hyperlinks.

The chat transcript and the model's answer are plain text, so links that people
pasted (review URLs, bug URLs, …) would otherwise be dead text. Both helpers
only ever treat ``http(s)://`` as a link and escape the text first, so IRC
content cannot inject HTML.
"""

from __future__ import annotations

import re

from markupsafe import Markup, escape

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Markdown link targets ("](https://…)"), existing angle autolinks ("<https://…>")
# and attribute values must be left alone when rewriting the markdown source.
_MD_URL_RE = re.compile(r"(?<![<(\"'=])https?://[^\s<>\"']+", re.IGNORECASE)

# Fenced code blocks and inline code spans are not linking targets.
_MD_CODE_RE = re.compile(
    r"(```.*?```|~~~.*?~~~|`[^`\n]+`)",
    re.DOTALL,
)

_TRAILING_PUNCTUATION = ".,;:!?"


def _trim(url: str) -> str:
    """Strip sentence punctuation that is not part of the URL."""
    while url and url[-1] in _TRAILING_PUNCTUATION:
        url = url[:-1]
    # Drop a closing bracket only when it has no matching opening bracket, so
    # wiki style URLs survive while "(see https://example.com/x)" is trimmed.
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def linkify_text(text: str) -> Markup:
    """Escape ``text`` and wrap any bare URL in an anchor tag."""
    if not text:
        return Markup("")

    escaped = str(escape(text))

    def replace(match: re.Match[str]) -> str:
        # ``escaped`` is already HTML-escaped, so the URL text and the trailing
        # punctuation can be embedded as-is.
        raw = match.group(0)
        url = _trim(raw)
        trailing = raw[len(url) :]
        return (
            f'<a href="{url}" rel="nofollow noopener">{url}</a>{trailing}'
        )

    return Markup(URL_RE.sub(replace, escaped))


def linkify_markdown(text: str) -> str:
    """Turn bare URLs in markdown into ``<url>`` autolinks.

    Python-Markdown already understands ``<https://…>`` and escapes the result,
    so the source is rewritten (skipping code) rather than the generated HTML.
    """
    if not text:
        return ""

    parts = _MD_CODE_RE.split(text)
    for index in range(0, len(parts), 2):
        parts[index] = _MD_URL_RE.sub(
            lambda match: f"<{_trim(match.group(0))}>"
            + match.group(0)[len(_trim(match.group(0))) :],
            parts[index],
        )
    return "".join(parts)
