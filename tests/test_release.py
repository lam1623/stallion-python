"""Releases are published for __version__ in stallion/__init__.py: everything else must follow it."""

import tomllib
from pathlib import Path

import pytest

from stallion import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_the_version_has_a_single_source() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]


def test_the_metainfo_lists_the_current_release() -> None:
    # Software centers (GNOME Software, Discover) show this history: every release adds its entry
    metainfo = ROOT / "packaging" / "linux" / "io.github.lam1623.stallion.metainfo.xml"
    if not metainfo.exists():
        pytest.skip("packaging/ is only part of a source checkout")
    assert f'<release version="{__version__}"' in metainfo.read_text(encoding="utf-8")
