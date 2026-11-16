from __future__ import annotations

import os
import pathlib
import time

import pytest

from asc.config import Config

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def cfg(tmp_path) -> Config:
    config = Config(channel="#openstack-ironic", window_hours=24)
    config.output_dir = tmp_path / "output"
    return config


@pytest.fixture
def set_timezone(monkeypatch):
    """Switch the process timezone for the duration of a test."""
    original = os.environ.get("TZ")
    tzset = getattr(time, "tzset", None)

    def _set(name: str) -> None:
        monkeypatch.setenv("TZ", name)
        if tzset is not None:
            tzset()

    yield _set

    if original is None:
        monkeypatch.delenv("TZ", raising=False)
    else:
        monkeypatch.setenv("TZ", original)
    if tzset is not None:
        tzset()
