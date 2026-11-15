"""Collect IRC logs from the OpenDev archive at meetings.opendev.org."""

from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Iterator

from bs4 import BeautifulSoup, Tag

from .config import Config
from .http import HttpClient, HttpError
from .models import ChatLog, Message
from .timeutil import ensure_utc

LOG = logging.getLogger(__name__)


def log_url(base_url: str, channel: str, day: datetime) -> str:
    """Return the archived log URL for ``channel`` on ``day``."""
    quoted = urllib.parse.quote(channel, safe="")
    return (
        f"{base_url.rstrip('/')}/{quoted}/"
        f"{quoted}.{day:%Y-%m-%d}.log.html"
    )


def parse_message_from_tr(row: Tag) -> Message | None:
    """Parse a :class:`Message` from a BeautifulSoup ``<tr>`` element."""
    timestamp_str = row.get("id")
    if not timestamp_str:
        return None
    # The archive uses ids such as "t2024-01-15T14:30:25".
    if timestamp_str.startswith("t"):
        timestamp_str = timestamp_str[1:20]
    try:
        timestamp = ensure_utc(datetime.fromisoformat(timestamp_str))
    except ValueError:
        LOG.debug("skipping row with unparseable timestamp %r", timestamp_str)
        return None

    nick_cell = row.find("th", class_="nick")
    text_cell = row.find("td", class_="text")
    if not nick_cell or not text_cell:
        return None
    return Message(
        timestamp=timestamp,
        nickname=nick_cell.get_text(strip=True),
        text=text_cell.get_text(strip=True),
    )


def parse_log_html(html_content: str) -> Iterator[Message]:
    """Yield every message in an archived IRC log page."""
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", class_="irclog")
    if not table:
        return
    for row in table.find_all("tr"):
        message = parse_message_from_tr(row)
        if message is not None:
            yield message


def is_ignored(nickname: str, cfg: Config, patterns: list[re.Pattern[str]]) -> bool:
    if nickname in cfg.ignore_nicks:
        return True
    return any(pattern.search(nickname) for pattern in patterns)


def collect(
    client: HttpClient,
    cfg: Config,
    since: datetime,
    now: datetime,
) -> tuple[ChatLog, list[str]]:
    """Collect the messages posted in ``cfg.channel`` since ``since``.

    Returns the collected log and a list of human readable errors. A missing
    log page (HTTP 404) ends the scan: it means the channel was quiet that day.
    """
    since = ensure_utc(since)
    now = ensure_utc(now)
    log = ChatLog(channel=cfg.channel, window_start=since, window_end=now)
    errors: list[str] = []
    patterns = [re.compile(pattern) for pattern in cfg.bot_patterns]

    day = since.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_day = now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    scanned = 0
    while day <= last_day and scanned < cfg.max_days:
        scanned += 1
        url = log_url(cfg.irclog_base_url, cfg.channel, day)
        LOG.debug("fetching %s", url)
        try:
            response = client.get(url, allow_status=(404,))
        except HttpError as exc:
            errors.append(f"{day:%Y-%m-%d}: {exc}")
            LOG.error("could not fetch %s: %s", url, exc)
            break
        if response.status_code == 404:
            LOG.debug("no log for %s, stopping the scan", day.date())
            break

        for message in parse_log_html(response.text):
            if message.timestamp < since or message.timestamp > now:
                continue
            if is_ignored(message.nickname, cfg, patterns):
                LOG.debug("ignoring message from %s", message.nickname)
                continue
            log.nicknames.add(message.nickname)
            log.messages.append(message)
        day += timedelta(days=1)

    if scanned >= cfg.max_days:
        LOG.warning("stopped after scanning %d days; raise irc.max_days", scanned)

    log.messages.sort(key=lambda message: message.timestamp)
    return log, errors
