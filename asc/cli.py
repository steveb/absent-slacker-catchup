"""Command line interface for ASC"""

import argparse
import datetime
import logging
import re
import os
import sys
from typing import Optional
import urllib.parse
import wave
import webbrowser

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


class Context:
    def __init__(self, args):
        self.args = args
        self.channel_encoded = urllib.parse.quote(args.channel.lstrip("#"), safe="")
        self.output_dir = os.path.join(
            args.output_directory,
            self.channel_encoded
            + "-"
            + datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self.messages = []
        self.nicknames = set()
        self.chat = ""
        self.summary = ""
        self.chat_file = os.path.join(self.output_dir, "chat.txt")
        self.html_file = os.path.join(self.output_dir, "summary.html")
        self.wav_filename = "summary.wav"
        self.wav_file = os.path.join(self.output_dir, self.wav_filename)


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
    fetch_parser.add_argument(
        "--output-directory",
        default=".",
        help="Directory to create output directory in",
    )
    fetch_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open generated HTML file in web browser",
    )
    # Example command: status
    status_parser = subparsers.add_parser("status", help="Show status information")

    return parser


def cmd_fetch(args) -> int:
    """Handle the fetch command"""
    LOG.info(f"Fetching {args.hours} hours from channel {args.channel}!")
    context = Context(args)
    get_messages(context)
    if args.output_type == "CHAT":
        generate_chat(context)
        generate_html_summary(
            context, include_chat=True, include_summary=False, include_audio=False
        )
    elif args.output_type == "SUMMARY":
        generate_chat(context)
        generate_summary(context)
        generate_html_summary(
            context, include_chat=True, include_summary=True, include_audio=False
        )
    elif args.output_type == "SPEECH_SUMMARY":
        generate_chat(context)
        generate_summary(context)
        generate_speech_summary(context)
        generate_html_summary(
            context, include_chat=True, include_summary=True, include_audio=True
        )
    else:
        raise ValueError(f"Invalid output type: {args.output_type}")
    return 0


def generate_chat(context):
    LOG.debug(f"Generating chat for {context.args.channel}")
    prev_message = None
    # write to file and print with the verbose argument
    with open(context.chat_file, "w") as f:
        for message in context.messages:
            m = message.format(
                prev_message, context.nicknames, verbose=context.args.verbose
            )
            print(m, end="", flush=True)
            f.write(m)
            context.chat += m
            prev_message = message

    # Generate the chat for the summary
    context.chat = ""
    prev_message = None
    for message in context.messages:
        m = message.format(prev_message, context.nicknames)
        context.chat += m
        prev_message = message


def generate_summary(context):
    """Generate a summary of the chat"""
    LOG.debug(f"Generating summary for {context.args.channel}")
    model = context.args.summary_model
    context.summary = ""

    prompt = f"""
    You are an assistant that summarizes chat logs without additional commentary.
    Use exclusively they/them pronouns when referring to people in this chat log.
    Always reply in English.
    Summarize the following chat log, do not include any other text in your response:

    <chat>
    {context.chat}
    </chat>
    """

    response = ollama.chat(
        model, messages=[{"role": "user", "content": prompt}], stream=True
    )
    for chunk in response:
        print(chunk["message"]["content"], end="", flush=True)
        context.summary += chunk["message"]["content"]


def generate_speech_summary(context):
    """Generate a speech summary of the chat"""
    LOG.debug(f"Generating speech summary for {context.args.channel}")
    tts_model = context.args.tts_model

    voice = piper.PiperVoice.load(tts_model)

    # Split the summary on </think> choose the last part
    summary = re.split(r"</think>", context.summary, flags=re.DOTALL)[-1]
    # Replace any astrisk bullet points with hyphens
    summary = re.sub(r"^\* ", "- ", summary, flags=re.DOTALL)
    # Remove any other asterisks
    summary = re.sub(r"\*", "", summary, flags=re.DOTALL)
    # Remove # from the summary
    summary = re.sub(r"#", "", summary, flags=re.DOTALL)
    # Replace any other punctuation with a full stop
    summary = re.sub(r"[^\w\s,] ", ". ", summary, flags=re.DOTALL)

    syn_config = piper.SynthesisConfig(
        # length_scale=1.1,  # slightly slower
        # noise_scale=1.0,  # more audio variation
        noise_w_scale=1.0,  # more speaking variation
        # normalize_audio=False,  # use raw audio from voice
    )
    with wave.open(context.wav_file, "wb") as wav_file:
        voice.synthesize_wav(summary, wav_file, syn_config=syn_config)


def generate_html_summary(
    context, include_chat=False, include_summary=False, include_audio=False
):
    """Generate a HTML document with text and embedded audio player"""
    # Convert markdown to HTML
    import markdown

    # Split the summary on </think>
    summary_parts = re.split(r"</think>", context.summary, flags=re.DOTALL)
    summary_text = re.sub(
        r"<think>(.*?)</think>", r"<i>\1</i>", context.summary, flags=re.DOTALL
    )
    html_thinking = "<i>"
    for part in summary_parts[:-1]:
        html_thinking += f"<p>{part}</p>"
    html_thinking += "</i>"
    html_summary = markdown.markdown(summary_parts[-1], extensions=["nl2br", "fenced_code"])
    with open(context.html_file, "w") as f:
        f.write(
            f"""
<html>
<head>
    <title>Chat Summary for {context.channel_encoded}</title>
        """
        )
        f.write(
            """
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
            color: #333;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        audio {
            width: 100%;
            margin: 20px 0;
        }
        pre {
            background-color: #f4f4f4;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            overflow-x: auto;
            font-size: 14px;
        }
        i {
            color: #7f8c8d;
            font-style: italic;
        }
        p {
            margin-bottom: 16px;
        }
        ul, ol {
            margin-bottom: 16px;
            padding-left: 30px;
        }
        li {
            margin-bottom: 8px;
        }
        code {
            background-color: #f1f2f6;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        }
        table.irclog {
            width: 100%;
            border-collapse: collapse;
        }
        table.irclog th, table.irclog td {
            padding: 8px;
            text-align: left;
            vertical-align: top;
        }
        table.irclog td.nick {
            font-weight: bold;
            text-align: right;
        }
    </style>
</head>
<body>
        """
        )
        f.write(
            f"""
    <h1>Chat Summary for {context.channel_encoded} on {context.messages[0].timestamp.strftime("%Y-%m-%d")}</h1>
        """
        )

        if include_audio:
            f.write(
                f"""
    <h2>Audio Summary</h2>
    <audio src="{context.wav_filename}" controls></audio>
            """
            )
        if include_summary:
            f.write(
                f"""
    <h2>Summary</h2>
    {html_summary}
    <h2>Thinking</h2>
    {html_thinking}
            """
            )

        if include_chat:
            f.write(
                f"""
    <h2>Chat</h2>
    <table class="irclog">
            """
            )
            for message in context.messages:
                f.write(
                    f"""
        <tr id="{message.timestamp}">
            <td class="time">{message.timestamp.strftime("%H:%M")}</td>
            <td class="nick">{message.nickname}</th>
            <td class="text">{message.text}</td>
        </tr>
                """
                )
            f.write(
                """
    </table>
            """
            )
        f.write(
            """
</body>
</html>
        """
        )
    LOG.info(f"Generated HTML summary in {context.html_file}")
    if context.args.open_browser:
        webbrowser.open(context.html_file)


def get_messages(context):

    LOG.debug(
        f"Getting messages for {context.args.channel} from {context.args.hours} hours ago"
    )
    args = context.args
    nicknames = context.nicknames
    now = pytz.timezone(args.timezone).localize(datetime.datetime.now())
    now_utc = now.astimezone(pytz.utc).replace(tzinfo=None)

    cutoff_time = now_utc - datetime.timedelta(hours=args.hours)
    messages = context.messages

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
