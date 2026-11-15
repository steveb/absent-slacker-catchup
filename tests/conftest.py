from __future__ import annotations

import pathlib

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
