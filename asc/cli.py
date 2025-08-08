"""Command line interface for ASC"""

import argparse
import datetime
import requests
import sys
from typing import Optional
import urllib.parse

from . import __version__, __description__


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser"""
    parser = argparse.ArgumentParser(
        prog="asc",
        description=__description__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"asc {__version__}"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Command: fetch
    fetch_parser = subparsers.add_parser("fetch", help="Fetch meeting log from OpenDev IRC logs")
    fetch_parser.add_argument("channel", nargs="?", default="#openstack-ironic", help="IRC channel name")
    
    # Example command: status
    status_parser = subparsers.add_parser("status", help="Show status information")
    
    return parser


def cmd_fetch(args) -> int:
    """Handle the fetch command"""
    print(f"fetch, {args.channel}!")
    if args.verbose:
        print("This is verbose output from the fetch command.")
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    day_before_yesterday = yesterday - datetime.timedelta(days=1)
    log_yesterday = fetch_meeting_log(args.channel, yesterday)
    log_day_before_yesterday = fetch_meeting_log(args.channel, day_before_yesterday)
    print(log_yesterday)
    print(log_day_before_yesterday)

    return 0

def parse_irc_log_html(html_content: str):
    """Parse HTML content and yield each <tr> element from the irclog table
    
    Args:
        html_content: HTML string containing the IRC log
        
    Yields:
        <tr> elements from the table with class "irclog"
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the table with class "irclog"
    irclog_table = soup.find('table', class_='irclog')
    
    if irclog_table:
        # Yield each <tr> element in the table
        for tr in irclog_table.find_all('tr'):
            yield tr



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
    
    response = requests.get(url)
    response.raise_for_status()
    
    return response.text





def main(argv: Optional[list] = None) -> int:
    """Main entry point for the CLI"""
    if argv is None:
        argv = sys.argv[1:]
    
    parser = create_parser()
    args = parser.parse_args(argv)
    
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