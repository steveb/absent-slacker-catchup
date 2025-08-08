"""Tests for the CLI module"""

import pytest
from asc.cli import main, create_parser


def test_parser_creation():
    """Test that the parser can be created successfully"""
    parser = create_parser()
    assert parser.prog == "asc"


def test_hello_command(capsys):
    """Test the hello command"""
    result = main(["hello"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Hello, World!" in captured.out


def test_hello_command_with_name(capsys):
    """Test the hello command with a custom name"""
    result = main(["hello", "Alice"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Hello, Alice!" in captured.out


def test_status_command(capsys):
    """Test the status command"""
    result = main(["status"])
    captured = capsys.readouterr()
    assert result == 0
    assert "ASC Status: Running" in captured.out


def test_verbose_flag(capsys):
    """Test the verbose flag"""
    result = main(["-v", "status"])
    captured = capsys.readouterr()
    assert result == 0
    assert "Version:" in captured.out
    assert "All systems operational." in captured.out


def test_no_command(capsys):
    """Test behavior when no command is provided"""
    result = main([])
    captured = capsys.readouterr()
    assert result == 1
    assert "usage:" in captured.out.lower()


def test_unknown_command(capsys):
    """Test behavior with unknown command"""
    with pytest.raises(SystemExit) as exc_info:
        main(["unknown"])
    
    captured = capsys.readouterr()
    # argparse exits with code 2 for invalid arguments
    assert exc_info.value.code == 2
    assert "invalid choice: 'unknown'" in captured.err


def test_version_flag(capsys):
    """Test the version flag"""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    
    # argparse exits with code 0 for --version
    assert exc_info.value.code == 0 