"""Turn bare URLs and bug/review numbers into safe hyperlinks.

The chat transcript and the model's answer are plain text, so links that people
pasted (review URLs, bug URLs, …) would otherwise be dead text. The helpers only
ever treat ``http(s)://`` as a link, and escape the text first, so IRC content
cannot inject HTML.

The summariser often writes "Ironic change 1013352" or "bug 2123456" without a
URL, so :func:`linkify_references` rewrites those numbers into explicit Markdown
links before the answer is rendered.
"""

from __future__ import annotations

import re

from markupsafe import Markup, escape

DEFAULT_GERRIT_BASE_URL = "https://review.opendev.org"
DEFAULT_LAUNCHPAD_BASE_URL = "https://bugs.launchpad.net"

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Reference numbers are long enough to be unambiguous (OpenStack Gerrit changes
# and Launchpad bugs are both in the millions today).
_REF_NUMBER = r"(?P<num>\d{5,9})"
_REVIEW_REF_RE = re.compile(
    r"\b(?P<word>change(?:s)?|review(?:s)?|patch(?:es)?|gerrit)"
    r"(?P<middle>(?:\s+(?:requests?|proposals?))?\s*:?\s*)"
    r"(?P<sigil>#?)"
    + _REF_NUMBER
    + r"\b",
    re.IGNORECASE,
)
_BUG_REF_RE = re.compile(
    r"\b(?P<word>bug(?:s)?|launchpad(?:\s+bugs?)?|lp)"
    r"(?P<middle>\s*:?\s*)"
    r"(?P<sigil>#?)"
    + _REF_NUMBER
    + r"\b",
    re.IGNORECASE,
)

# Regions where a number must not be rewritten: code, existing Markdown links
# and bare/auto URLs.
_REF_PROTECTED_RE = re.compile(
    r"```.*?```"
    r"|~~~.*?~~~"
    r"|`[^`\n]+`"
    r"|!?\[[^\]]*\]\([^)]*\)"
    r"|<https?://[^>\s]+>"
    r"|https?://[^\s<>\"']+",
    re.DOTALL | re.IGNORECASE,
)

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
            f'<a href="{url}" rel="nofollow noopener" target="_blank">'
            f"{url}</a>{trailing}"
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


def launchpad_project_for(channel: str | None) -> str | None:
    """Return the Launchpad project hinted by an ``#openstack-…`` channel name."""
    if not channel:
        return None
    name = channel.strip().lstrip("#")
    prefix = "openstack-"
    if name.startswith(prefix):
        return name[len(prefix) :] or None
    return None


def _reference_url(
    base_url: str, path: str, number: str, *, bug: bool = False
) -> str:
    base = base_url.rstrip("/")
    if bug:
        return f"{base}/{path}/+bug/{number}" if path else f"{base}/bugs/{number}"
    return f"{base}/{path}/{number}"


def _link_references(
    text: str,
    *,
    gerrit_base_url: str,
    launchpad_base_url: str,
    launchpad_project: str | None,
) -> str:
    if not text:
        return text

    def review_link(match: re.Match[str]) -> str:
        number = match.group("num")
        label = f"{match.group('sigil')}{number}"
        url = _reference_url(gerrit_base_url, "c", number)
        return f"{match.group('word')}{match.group('middle')}[{label}]({url})"

    def bug_link(match: re.Match[str]) -> str:
        number = match.group("num")
        label = f"{match.group('sigil')}{number}"
        url = _reference_url(
            launchpad_base_url, launchpad_project or "", number, bug=True
        )
        return f"{match.group('word')}{match.group('middle')}[{label}]({url})"

    text = _REVIEW_REF_RE.sub(review_link, text)
    return _BUG_REF_RE.sub(bug_link, text)


def linkify_references(
    text: str,
    *,
    gerrit_base_url: str = DEFAULT_GERRIT_BASE_URL,
    launchpad_base_url: str = DEFAULT_LAUNCHPAD_BASE_URL,
    launchpad_project: str | None = None,
) -> str:
    """Turn bare review and bug numbers into Markdown links.

    Code spans, fenced blocks, existing Markdown links and URLs are left alone.
    Gerrit change URLs do not need the project (Gerrit redirects to the right
    one); the Launchpad project is only a hint and Launchpad redirects too.
    """
    if not text:
        return ""

    parts: list[str] = []
    last = 0
    for match in _REF_PROTECTED_RE.finditer(text):
        parts.append(
            _link_references(
                text[last : match.start()],
                gerrit_base_url=gerrit_base_url,
                launchpad_base_url=launchpad_base_url,
                launchpad_project=launchpad_project,
            )
        )
        parts.append(match.group(0))
        last = match.end()
    parts.append(
        _link_references(
            text[last:],
            gerrit_base_url=gerrit_base_url,
            launchpad_base_url=launchpad_base_url,
            launchpad_project=launchpad_project,
        )
    )
    return "".join(parts)
