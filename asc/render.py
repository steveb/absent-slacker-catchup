"""Render the summary page, its JSON twin and the ``latest.html`` copy."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config
from .models import Report
from .timeutil import format_local

LOG = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "htm", "j2", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def summary_to_html(summary: str) -> str:
    """Convert the markdown answer into HTML."""
    return markdown.markdown(summary, extensions=["nl2br", "fenced_code"])


def build_context(
    report: Report,
    cfg: Config,
    *,
    include_summary: bool,
    include_chat: bool,
    include_audio: bool,
    audio_href: str | None = None,
) -> dict[str, Any]:
    log = report.log
    return {
        "channel": log.channel,
        "date": log.window_end.astimezone().strftime("%Y-%m-%d"),
        "css": (TEMPLATE_DIR / "style.css").read_text(encoding="utf-8"),
        "generated": format_local(log.window_end),
        "window_start": format_local(log.window_start),
        "window_end": format_local(log.window_end),
        "message_count": len(log.messages),
        "nickname_count": len(log.nicknames),
        "messages": [message.view() for message in log.messages],
        "summary_html": summary_to_html(report.summary),
        "thinking": report.thinking,
        "errors": report.errors,
        "include_summary": include_summary,
        "include_chat": include_chat,
        "include_audio": include_audio,
        "audio_href": audio_href,
    }


def render_page(
    report: Report,
    cfg: Config,
    *,
    include_summary: bool = False,
    include_chat: bool = True,
    include_audio: bool = False,
    audio_href: str | None = None,
) -> str:
    """Render the self-contained summary page."""
    template = _environment().get_template("summary.html.j2")
    return template.render(
        **build_context(
            report,
            cfg,
            include_summary=include_summary,
            include_chat=include_chat,
            include_audio=include_audio,
            audio_href=audio_href,
        )
    )


def write_report(
    report: Report,
    cfg: Config,
    directory: Path,
    *,
    include_summary: bool = False,
    include_chat: bool = True,
    include_audio: bool = False,
    write_json: bool = False,
) -> dict[str, Path]:
    """Write the run directory and refresh ``latest.html`` next to it."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    chat_path = directory / "chat.txt"
    chat_path.write_text(report.log.chat_text(), encoding="utf-8")
    paths["chat"] = chat_path

    html = render_page(
        report,
        cfg,
        include_summary=include_summary,
        include_chat=include_chat,
        include_audio=include_audio,
        audio_href=report.audio_file,
    )
    html_path = directory / "summary.html"
    html_path.write_text(html, encoding="utf-8")
    paths["html"] = html_path

    # latest.html lives one level up, so the audio reference has to include the
    # run directory name.
    latest_path = directory.parent / "latest.html"
    latest_html = render_page(
        report,
        cfg,
        include_summary=include_summary,
        include_chat=include_chat,
        include_audio=include_audio,
        audio_href=(
            f"{directory.name}/{report.audio_file}" if report.audio_file else None
        ),
    )
    latest_path.write_text(latest_html, encoding="utf-8")
    paths["latest"] = latest_path

    if write_json:
        json_path = directory / "summary.json"
        json_path.write_text(
            json.dumps(report.as_dict(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        paths["json"] = json_path

    if report.audio_file:
        paths["audio"] = directory / report.audio_file

    return paths
