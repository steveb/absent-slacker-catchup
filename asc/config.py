"""Configuration defaults and optional TOML overrides."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .links import DEFAULT_GERRIT_BASE_URL, DEFAULT_LAUNCHPAD_BASE_URL

LOG = logging.getLogger(__name__)

DEFAULT_CHANNEL = "#openstack-ironic"
DEFAULT_IRCLOG_BASE_URL = "https://meetings.opendev.org/irclogs"
DEFAULT_SUMMARY_BASE_URL = "https://api.enmaas.devshift.net/v1"
DEFAULT_SUMMARY_MODEL = "rits/deepseek-ai/DeepSeek-V4.1-Flash-1017"
DEFAULT_API_KEY_ENV = "ENMAAS_KEY"
DEFAULT_TTS_MODEL = "en_GB-jenny_dioco-medium.onnx"

OUTPUT_TYPES = ("CHAT", "SUMMARY", "SPEECH_SUMMARY")

DEFAULT_IGNORE_NICKS = [
    "opendevreview",
]

DEFAULT_BOT_PATTERNS = [
    r"^opendevreview$",
    r"^openstack(gerrit|zuul|infra)$",
    r"^zuul$",
    r"-bot$",
    r"\[bot\]$",
]


@dataclass
class Config:
    # general
    channel: str = DEFAULT_CHANNEL
    window_hours: float = 24.0
    output_dir: Path = Path("output")
    output_type: str = "CHAT"
    write_json: bool = False
    open_browser: bool | None = None
    request_timeout: float = 30.0
    user_agent: str = f"asc/{__version__} (IRC channel summariser)"

    # irc logs
    irclog_base_url: str = DEFAULT_IRCLOG_BASE_URL
    ignore_nicks: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_NICKS))
    bot_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_BOT_PATTERNS))
    max_days: int = 31

    # summariser
    base_url: str = DEFAULT_SUMMARY_BASE_URL
    summary_model: str = DEFAULT_SUMMARY_MODEL
    api_key_env: str = DEFAULT_API_KEY_ENV
    max_tokens: int = 32768

    # links in the rendered summary
    gerrit_base_url: str = DEFAULT_GERRIT_BASE_URL
    launchpad_base_url: str = DEFAULT_LAUNCHPAD_BASE_URL
    # Empty means "derive from an #openstack-… channel name".
    launchpad_project: str = ""

    # text to speech
    tts_model: str = DEFAULT_TTS_MODEL
    tts_model_dir: Path | None = None

    def resolve_tts_model(self) -> Path:
        """Return the configured voice model as an absolute path.

        Relative names are looked up in ``tts_model_dir`` (default
        ``~/.local/share/asc/models``), then next to the current directory, so
        a model downloaded into the data directory works from anywhere.
        """
        candidate = Path(self.tts_model).expanduser()
        if candidate.is_absolute() or candidate.exists():
            return candidate
        directories = (
            self.tts_model_dir.expanduser()
            if self.tts_model_dir is not None
            else Path("~/.local/share/asc/models").expanduser(),
            Path.cwd(),
        )
        for directory in directories:
            nested = directory / candidate
            if nested.exists():
                return nested
        return candidate


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _apply_section(cfg: Config, name: str, values: dict[str, Any]) -> None:
    simple: dict[str, dict[str, tuple[Any, str]]] = {
        "general": {
            "channel": (str, "channel"),
            "window_hours": (float, "window_hours"),
            "output_dir": (Path, "output_dir"),
            "output_type": (str, "output_type"),
            "write_json": (bool, "write_json"),
            "open_browser": (bool, "open_browser"),
            "request_timeout": (float, "request_timeout"),
            "user_agent": (str, "user_agent"),
        },
        "irc": {
            "base_url": (str, "irclog_base_url"),
            "ignore_nicks": (list, "ignore_nicks"),
            "bot_patterns": (list, "bot_patterns"),
            "max_days": (int, "max_days"),
        },
        "summary": {
            "base_url": (str, "base_url"),
            "model": (str, "summary_model"),
            "api_key_env": (str, "api_key_env"),
            "max_tokens": (int, "max_tokens"),
        },
        "links": {
            "gerrit_base_url": (str, "gerrit_base_url"),
            "launchpad_base_url": (str, "launchpad_base_url"),
            "launchpad_project": (str, "launchpad_project"),
        },
        "tts": {
            "model": (str, "tts_model"),
            "model_dir": (Path, "tts_model_dir"),
        },
    }

    mapping = simple.get(name)
    if mapping is None:
        LOG.warning("ignoring unknown config section [%s]", name)
        return

    for key, value in values.items():
        spec = mapping.get(key)
        if spec is None:
            LOG.warning("ignoring unknown config key %s.%s", name, key)
            continue
        converter, target = spec
        if converter is list:
            setattr(cfg, target, [str(item) for item in _as_list(value)])
        else:
            setattr(cfg, target, converter(value))


def load_config(path: Path | None = None) -> Config:
    """Load configuration, applying TOML overrides when a file is available."""
    cfg = Config()
    if path is None:
        return cfg
    if not path.exists():
        LOG.warning("config file %s does not exist, using defaults", path)
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    for section, values in data.items():
        if isinstance(values, dict):
            _apply_section(cfg, section, values)
        else:
            LOG.warning("ignoring top level config key %s", section)
    if cfg.output_type not in OUTPUT_TYPES:
        LOG.warning(
            "unknown output_type %r, falling back to %s",
            cfg.output_type,
            OUTPUT_TYPES[0],
        )
        cfg.output_type = OUTPUT_TYPES[0]
    return cfg


def default_config_path(cwd: Path | None = None) -> Path | None:
    """Return ``./config.toml`` when it exists, otherwise ``None``."""
    candidate = (cwd or Path.cwd()) / "config.toml"
    return candidate if candidate.exists() else None
