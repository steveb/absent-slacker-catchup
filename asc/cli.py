"""Command line entry point for ASC."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import OUTPUT_TYPES, Config, default_config_path, load_config
from .http import HttpClient
from .logs import collect
from .models import Report
from .render import render_page, write_report
from .summarize import SummaryError, split_thinking, summarize
from .timeutil import (
    format_local,
    local_stamp,
    parse_timestamp,
    utcnow,
    window_start,
)
from .tts import TtsError, clean_for_speech, synthesize

LOG = logging.getLogger("asc")


def _logging_options() -> argparse.ArgumentParser:
    """Return the ``-v``/``-q`` flags, usable before or after the subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=argparse.SUPPRESS,
        help="increase logging verbosity",
    )
    common.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="only print errors",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asc",
        description=(
            "Summarize the previous hours of an OpenStack IRC channel archived "
            "at https://meetings.opendev.org/irclogs/"
        ),
        parents=[_logging_options()],
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML config file (default: ./config.toml when present)",
    )
    parser.add_argument("--version", action="version", version=f"asc {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    fetch = subparsers.add_parser(
        "fetch",
        help="Summarize a channel from the IRC logs",
        parents=[_logging_options()],
    )
    fetch.add_argument(
        "channel", nargs="?", default=None, help="IRC channel name (default: configured)"
    )
    fetch.add_argument(
        "--hours",
        type=float,
        default=None,
        help="number of hours to look back (default: 14)",
    )
    fetch.add_argument(
        "--since",
        default=None,
        metavar="ISO8601",
        help="explicit start of the window, e.g. 2026-11-14T06:00:00Z",
    )
    fetch.add_argument(
        "--output-dir",
        "--output-directory",
        dest="output_dir",
        type=Path,
        default=None,
        help="directory to create the run directory in (default: ./output)",
    )
    fetch.add_argument(
        "--output-type",
        choices=OUTPUT_TYPES,
        default=None,
        help="CHAT: chat text, SUMMARY: chat plus summary, "
        "SPEECH_SUMMARY: summary plus audio (default: CHAT)",
    )
    fetch.add_argument(
        "--ignore-nicks",
        nargs="*",
        default=None,
        help="nicknames to ignore when fetching messages",
    )
    fetch.add_argument(
        "--summary-model",
        default=None,
        help="ollama model used to generate the summary",
    )
    fetch.add_argument(
        "--tts-model",
        default=None,
        help="Piper voice model used for speech summaries",
    )
    fetch.add_argument(
        "--tts-model-dir",
        type=Path,
        default=None,
        help="directory searched for a relative --tts-model",
    )
    fetch.add_argument(
        "--json",
        dest="write_json",
        action="store_true",
        default=None,
        help="also write a machine-readable summary.json",
    )
    fetch.add_argument(
        "--no-json",
        dest="write_json",
        action="store_false",
        help="do not write the JSON twin",
    )
    fetch.add_argument(
        "--open",
        "--open-browser",
        dest="open_browser",
        action="store_true",
        default=None,
        help="open the generated page in a browser",
    )
    fetch.add_argument(
        "--no-open",
        dest="open_browser",
        action="store_false",
        help="never open a browser",
    )
    fetch.add_argument(
        "--stdout",
        action="store_true",
        help="print the HTML to stdout instead of writing files",
    )
    fetch.add_argument(
        "--dry-run",
        action="store_true",
        help="collect and print a summary only; write nothing",
    )

    subparsers.add_parser(
        "status",
        help="Show the effective configuration",
        parents=[_logging_options()],
    )

    return parser


def _configure_logging(verbosity: int, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _apply_overrides(cfg: Config, args: argparse.Namespace) -> None:
    if args.channel is not None:
        cfg.channel = args.channel
    if args.hours is not None:
        cfg.window_hours = float(args.hours)
    if args.output_dir is not None:
        cfg.output_dir = Path(args.output_dir).expanduser()
    if args.output_type is not None:
        cfg.output_type = args.output_type
    if args.ignore_nicks is not None:
        cfg.ignore_nicks = list(args.ignore_nicks)
    if args.summary_model is not None:
        cfg.summary_model = args.summary_model
    if args.tts_model is not None:
        cfg.tts_model = args.tts_model
    if args.tts_model_dir is not None:
        cfg.tts_model_dir = Path(args.tts_model_dir).expanduser()
    if args.write_json is not None:
        cfg.write_json = args.write_json
    if args.open_browser is not None:
        cfg.open_browser = args.open_browser
    if cfg.window_hours <= 0:
        raise SystemExit("--hours must be greater than zero")
    if not cfg.channel.strip():
        raise SystemExit("channel must not be empty")


def _resolve_since(
    args: argparse.Namespace, now: datetime, cfg: Config
) -> datetime:
    if args.since:
        try:
            since = parse_timestamp(args.since)
        except ValueError as exc:
            raise SystemExit(f"invalid --since value: {exc}") from exc
        if since >= now:
            raise SystemExit("--since must be in the past")
        return since
    return window_start(now, cfg.window_hours)


def _should_open_browser(cfg: Config) -> bool:
    if cfg.open_browser is not None:
        return cfg.open_browser
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _open_in_browser(path: Path) -> None:
    uri = path.resolve().as_uri()
    try:
        launched = webbrowser.open(uri)
    except Exception as exc:  # pragma: no cover - environment dependent
        LOG.warning("could not open %s in a browser: %s", uri, exc)
        return
    if not launched:
        LOG.warning("no browser available to open %s", uri)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lstrip("#").lower()).strip("-")
    return slug or "channel"


def _print_summary(report: Report, cfg: Config) -> None:
    log = report.log
    print(f"{log.channel}")
    print(
        f"  window   {format_local(log.window_start)} -> "
        f"{format_local(log.window_end)} ({cfg.window_hours:g}h)"
    )
    print(f"  messages {len(log.messages)} from {len(log.nicknames)} people")
    print(f"  summary  {'yes' if report.summary else 'no'}")
    print(f"  audio    {report.audio_file or 'no'}")
    if report.errors:
        print(f"  errors   {len(report.errors)}")
        for error in report.errors:
            print(f"           - {error}")


def _stream_token(token: str) -> None:
    print(token, end="", flush=True)


def cmd_fetch(args: argparse.Namespace, cfg: Config) -> int:
    quiet = getattr(args, "quiet", False)
    now = utcnow()
    since = _resolve_since(args, now, cfg)

    errors: list[str] = []
    client = HttpClient(
        cfg.user_agent,
        timeout=cfg.request_timeout,
        min_interval=0.2,
    )
    with client:
        log, collect_errors = collect(client, cfg, since, now)
    errors.extend(collect_errors)

    report = Report(log=log, errors=errors)
    include_chat = True
    include_summary = cfg.output_type in ("SUMMARY", "SPEECH_SUMMARY")
    include_audio = cfg.output_type == "SPEECH_SUMMARY"

    if args.dry_run:
        _print_summary(report, cfg)
        return 1 if errors else 0

    if include_summary and not log.messages:
        LOG.warning("no messages in the window; skipping the summary")
        include_summary = False
        include_audio = False

    if include_summary:
        echo = not (quiet or args.stdout)
        try:
            raw = summarize(
                log.chat_text(), cfg, on_token=_stream_token if echo else None
            )
        except SummaryError as exc:
            LOG.error("%s", exc)
            errors.append(str(exc))
            include_summary = False
            include_audio = False
        else:
            report.thinking, report.summary = split_thinking(raw)
            if echo:
                print(flush=True)

    run_dir = Path(cfg.output_dir) / f"{_slug(cfg.channel)}-{local_stamp(now)}"

    if include_audio and report.summary:
        try:
            synthesize(
                clean_for_speech(report.summary),
                run_dir / "summary.wav",
                cfg.resolve_tts_model(),
            )
            report.audio_file = "summary.wav"
        except TtsError as exc:
            LOG.error("%s", exc)
            errors.append(str(exc))

    if args.stdout:
        sys.stdout.write(
            render_page(
                report,
                cfg,
                include_summary=include_summary,
                include_chat=include_chat,
                include_audio=report.audio_file is not None,
                audio_href=report.audio_file,
            )
        )
        sys.stdout.flush()
        return 1 if errors else 0

    paths = write_report(
        report,
        cfg,
        run_dir,
        include_summary=include_summary,
        include_chat=include_chat,
        include_audio=report.audio_file is not None,
        write_json=bool(cfg.write_json),
    )
    if not quiet:
        print(f"Summary: {paths['html']}")
        print(f"Latest:  {paths['latest']}")
        if "json" in paths:
            print(f"JSON:    {paths['json']}")

    if _should_open_browser(cfg):
        _open_in_browser(paths["html"])

    return 1 if errors else 0


def cmd_status(args: argparse.Namespace, cfg: Config, config_path: Path | None) -> int:
    voice = cfg.resolve_tts_model()
    print(f"asc {__version__}")
    print(f"  config        {config_path or '(defaults)'}")
    print(f"  channel       {cfg.channel}")
    print(f"  window        {cfg.window_hours:g}h")
    print(f"  output type   {cfg.output_type}")
    print(f"  output dir    {cfg.output_dir}")
    print(f"  summary model {cfg.summary_model}")
    print(f"  voice model   {voice} ({'found' if voice.exists() else 'missing'})")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(
        getattr(args, "verbose", 0), getattr(args, "quiet", False)
    )

    if not args.command:
        parser.print_help()
        return 1

    config_path = args.config or default_config_path()
    cfg = load_config(config_path)

    if args.command == "status":
        return cmd_status(args, cfg, args.config if args.config else config_path)

    _apply_overrides(cfg, args)
    return cmd_fetch(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
