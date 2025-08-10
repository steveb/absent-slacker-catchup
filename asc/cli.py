"""Command line interface for ASC"""

import argparse
import datetime
import logging
import sys
from typing import Optional
import urllib.parse
import wave

from bs4 import BeautifulSoup
import requests
import ollama
import piper
import pytz

from asc.message import parse_message_from_tr

from . import __version__, __description__

# Initialize logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
LOG = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser"""
    parser = argparse.ArgumentParser(
        prog="asc",
        description=__description__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"asc {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: fetch
    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch meeting log from OpenDev IRC logs"
    )
    fetch_parser.add_argument(
        "channel", nargs="?", default="#openstack-ironic", help="IRC channel name"
    )
    fetch_parser.add_argument(
        "--ignore-nicks",
        nargs="*",
        default=["opendevreview"],
        help="List of nicknames to ignore when fetching messages",
    )
    fetch_parser.add_argument(
        "--timezone",
        default="Pacific/Auckland",
        help="Timezone to use for calculating relative times",
    )
    fetch_parser.add_argument(
        "--hours",
        type=int,
        default=14,
        help="Number of hours to look back for messages (default: 14)",
    )
    fetch_parser.add_argument(
        "--file",
        help="File to write the chat output to (if not specified, output to stdout)",
    )
    fetch_parser.add_argument(
        "--output-type",
        choices=["CHAT", "SUMMARY", "SPEECH_SUMMARY"],
        default="CHAT",
        help="Type of output to generate. "
        "CHAT: chat text. "
        "SUMMARY: summary of the chat as text. "
        "SPEECH_SUMMARY: summary of the chat as an audio file. "
        "(default: CHAT)",
    )
    fetch_parser.add_argument(
        "--summary-model",
        default="hf.co/mradermacher/Josiefied-DeepSeek-R1-0528-Qwen3-8B-abliterated-v1-i1-GGUF:Q4_K_M",
        help="Model to use for generating summaries",
    )
    fetch_parser.add_argument(
        "--tts-model",
        default="en_GB-jenny_dioco-medium.onnx",
        help="Piper TTS model to use for generating speech summaries",
    )
    # Example command: status
    status_parser = subparsers.add_parser("status", help="Show status information")

    return parser


def cmd_fetch(args) -> int:
    """Handle the fetch command"""
    LOG.info(f"Fetching {args.hours} hours from channel {args.channel}!")
    nicknames = set()
    messages = get_messages(args, nicknames)
    if args.output_type == "CHAT":
        prev_message = None
        for message in messages:
            print(message.format(prev_message, nicknames, verbose=args.verbose))
            prev_message = message
    elif args.output_type == "SUMMARY":
        for summary in generate_summary(messages, nicknames, args.summary_model):
            print(summary, end="", flush=True)
    elif args.output_type == "SPEECH_SUMMARY":
        generate_speech_summary(messages, nicknames, args.summary_model, args.tts_model)
    else:
        raise ValueError(f"Invalid output type: {args.output_type}")
    return 0


def generate_summary(messages, nicknames, model):
    """Generate a summary of the chat"""
    prev_message = None
    message_string = ""
    for message in messages:
        message_string += message.format(prev_message, nicknames)
        prev_message = message

    prompt = f"""
    You are an assistant that summarizes chat logs in a very concise manner.
    Summarize this chat log:
    {messages}"""
    response = ollama.chat(
        model, messages=[{"role": "user", "content": prompt}], stream=True
    )
    for chunk in response:
        yield chunk["message"]["content"]






def generate_speech_summary(messages, nicknames, summary_model, tts_model):
    """Generate a speech summary of the chat"""

    voice = piper.PiperVoice.load(tts_model)
    summary_text = ""
    for summary in generate_summary(messages, nicknames, summary_model):
        print(summary, end="", flush=True)
        summary_text += summary

    syn_config = piper.SynthesisConfig(
        length_scale=1.1,  # slightly slower
        noise_scale=1.0,  # more audio variation
        noise_w_scale=1.0,  # more speaking variation
        normalize_audio=False,  # use raw audio from voice
    )
    with wave.open("test.wav", "wb") as wav_file:
        voice.synthesize_wav(summary_text, wav_file, syn_config=syn_config)

def get_messages(args, nicknames):

    now = pytz.timezone(args.timezone).localize(datetime.datetime.now())
    now_utc = now.astimezone(pytz.utc).replace(tzinfo=None)

    cutoff_time = now_utc - datetime.timedelta(hours=args.hours)
    messages = []

    day = cutoff_time.replace(hour=0, minute=0, second=0, microsecond=0)
    while True:
        try:
            day_log = fetch_meeting_log(args.channel, day)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                break
            else:
                raise

        for message in parse_irc_log_html(day_log):
            if not message:
                continue
            if message.timestamp < cutoff_time:
                continue
            if message.nickname in args.ignore_nicks:
                continue
            nicknames.add(message.nickname)
            messages.append(message)
        day = day + datetime.timedelta(days=1)
    return messages


def parse_irc_log_html(html_content: str):
    """Parse HTML content and yield each <tr> element from the irclog table

    Args:
        html_content: HTML string containing the IRC log

    Yields:
        <tr> elements from the table with class "irclog"
    """

    soup = BeautifulSoup(html_content, "html.parser")

    # Find the table with class "irclog"
    irclog_table = soup.find("table", class_="irclog")

    if irclog_table:
        # Yield each <tr> element in the table
        for tr in irclog_table.find_all("tr"):
            yield parse_message_from_tr(tr)


def cmd_status(args) -> int:
    """Handle the status command"""
    print("ASC Status: Running")
    if args.verbose:
        print(f"Version: {__version__}")
        print("All systems operational.")
    return 0


def fetch_meeting_log(channel: str, date: datetime.datetime) -> str:
    """Fetch meeting log from OpenDev IRC logs

    Args:
        channel: IRC channel name
        date: Date of the meeting

    Returns:
        Response text from the log URL
    """
    year = date.year
    month = f"{date.month:02d}"
    day = f"{date.day:02d}"
    # URL escape the channel name
    channel = urllib.parse.quote(channel)

    url = f"https://meetings.opendev.org/irclogs/{channel}/{channel}.{year}-{month}-{day}.log.html"
    LOG.debug(f"Fetching log from {url}")

    response = requests.get(url)
    response.raise_for_status()

    return response.text


def main(argv: Optional[list] = None) -> int:
    """Main entry point for the CLI"""
    if argv is None:
        argv = sys.argv[1:]

    parser = create_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        LOG.debug(f"args: {args}")

    # If no command is specified, show help
    if not args.command:
        parser.print_help()
        return 1

    # Dispatch to command handlers
    if args.command == "fetch":
        return cmd_fetch(args)
    elif args.command == "status":
        return cmd_status(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
