"""Data model for a summarized IRC window."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .timeutil import format_local, iso_utc


@dataclass(slots=True)
class Message:
    """A single IRC message with timestamp, nickname and content."""

    timestamp: datetime
    nickname: str
    text: str
    # Messages from ignored nicknames or bot patterns stay in the transcript but
    # are left out of the summarisation prompt.
    ignored: bool = False

    def format(
        self,
        prev_message: Message | None = None,
        nicknames: frozenset[str] = frozenset(),
        *,
        verbose: bool = False,
    ) -> str:
        """Format the message for the summarisation prompt."""
        msg = self.text
        context = f"\n\n{self.nickname} said:\n"
        timestamp = f"\n{self.timestamp}" if verbose else ""

        if prev_message and prev_message.nickname == self.nickname:
            context = ""
            timestamp = ""

        replied = None
        for nickname in nicknames:
            if msg.startswith(nickname):
                msg = msg[len(nickname) :].strip()
                replied = nickname
                if msg.startswith(":"):
                    msg = msg[1:].strip()
                break

        if replied:
            context = f"\n\n{self.nickname} replied to {replied}:\n"
        return f"{timestamp}{context}{msg}"

    def view(self) -> dict[str, str]:
        """Return the fields needed by the HTML template."""
        return {
            "time": self.timestamp.strftime("%H:%M"),
            "nickname": self.nickname,
            "text": self.text,
            "anchor": self.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "ignored": self.ignored,
        }


@dataclass(slots=True)
class ChatLog:
    """The messages collected for one channel window."""

    channel: str
    window_start: datetime
    window_end: datetime
    messages: list[Message] = field(default_factory=list)
    nicknames: set[str] = field(default_factory=set)

    @property
    def human_messages(self) -> list[Message]:
        """Messages that are eligible for the summary."""
        return [message for message in self.messages if not message.ignored]

    @property
    def ignored_messages(self) -> list[Message]:
        return [message for message in self.messages if message.ignored]

    @property
    def human_nicknames(self) -> set[str]:
        return {message.nickname for message in self.human_messages}

    def chat_text(self, *, verbose: bool = False) -> str:
        """Render the conversation the way the summariser expects it."""
        parts: list[str] = []
        prev_message: Message | None = None
        nicknames = frozenset(self.nicknames)
        for message in self.human_messages:
            parts.append(
                message.format(prev_message, nicknames, verbose=verbose)
            )
            prev_message = message
        return "".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "window_start": iso_utc(self.window_start),
            "window_end": iso_utc(self.window_end),
            "window_hours": (
                self.window_end - self.window_start
            ).total_seconds()
            / 3600,
            "message_count": len(self.messages),
            "human_message_count": len(self.human_messages),
            "ignored_message_count": len(self.ignored_messages),
            "nicknames": sorted(self.nicknames),
            "generated": format_local(self.window_end),
        }


@dataclass(slots=True)
class Report:
    """A collected window plus whatever was generated from it."""

    log: ChatLog
    summary: str = ""
    thinking: str = ""
    audio_file: str | None = None
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = self.log.as_dict()
        data.update(
            {
                "summary": self.summary,
                "thinking": self.thinking,
                "audio_file": self.audio_file,
                "errors": list(self.errors),
            }
        )
        return data
