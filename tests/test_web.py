from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pytest

from stallion.web import ensure_built, stale_reason

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="uses a shell script as a stand-in for npm")

# Logs its arguments; `ci` installs the packages and `run build` writes the bundle
FAKE_NPM = """#!/bin/sh
echo "$*" >> "$FAKE_NPM_LOG"
if [ -n "$FAKE_NPM_FAIL" ]; then echo "boom" >&2; exit 3; fi
case "$1" in
  ci) mkdir -p node_modules && touch node_modules/.package-lock.json ;;
  run) mkdir -p "$FAKE_DIST" && echo "<html></html>" > "$FAKE_DIST/index.html" ;;
esac
"""

# An hour ago, so a build made by the test is always newer
PAST = time.time() - 3600


def _stamp(path: Path, when: float) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    os.utime(path, (when, when))
    return path


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    """A frontend/ source tree and the folder its build goes to."""

    frontend = tmp_path / "frontend"
    for name in ("package.json", "package-lock.json", "src/main.tsx"):
        _stamp(frontend / name, PAST)
    return frontend, tmp_path / "dist"


@pytest.fixture
def npm_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(FAKE_NPM)
    npm.chmod(0o755)
    log = tmp_path / "npm.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_NPM_LOG", str(log))
    monkeypatch.setenv("FAKE_DIST", str(tmp_path / "dist"))
    return log


def _calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_installed_packages_are_never_checked(tmp_path: Path) -> None:
    # Wheels and the Docker image have no frontend/ next to the package
    assert stale_reason(tmp_path / "frontend", tmp_path / "dist") is None


def test_the_build_goes_stale_when_a_source_changes(tmp_path: Path) -> None:
    frontend, dist = _checkout(tmp_path)
    assert stale_reason(frontend, dist) == "not built yet"

    _stamp(dist / "index.html", PAST + 60)
    # Installed packages are not sources of the build
    _stamp(frontend / "node_modules" / "react" / "index.js", PAST + 120)
    assert stale_reason(frontend, dist) is None

    _stamp(frontend / "src" / "main.tsx", PAST + 120)  # what a git pull does to a changed file
    assert stale_reason(frontend, dist) == "older than the sources in frontend/"


@posix_only
def test_a_stale_ui_is_rebuilt_before_serving(tmp_path: Path, npm_calls: Path) -> None:
    frontend, dist = _checkout(tmp_path)
    # A fresh checkout: the packages are installed first
    assert ensure_built(frontend, dist) is True
    assert _calls(npm_calls) == ["ci --no-audit --no-fund", "run build"]
    assert stale_reason(frontend, dist) is None

    # Changed sources with current packages: only the build runs
    npm_calls.unlink()
    _stamp(dist / "index.html", PAST + 60)
    _stamp(frontend / "src" / "main.tsx", PAST + 120)
    assert ensure_built(frontend, dist) is True
    assert _calls(npm_calls) == ["run build"]
    assert stale_reason(frontend, dist) is None

    # Nothing changed: npm is not run at all
    npm_calls.unlink()
    assert ensure_built(frontend, dist) is True
    assert _calls(npm_calls) == []


@posix_only
def test_a_failed_build_keeps_the_previous_ui(
    tmp_path: Path, npm_calls: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    frontend, dist = _checkout(tmp_path)
    monkeypatch.setenv("FAKE_NPM_FAIL", "1")
    with caplog.at_level(logging.ERROR, logger="stallion.web"):
        assert ensure_built(frontend, dist) is False
    # Stops at the first failing step and shows why
    assert _calls(npm_calls) == ["ci --no-audit --no-fund"]
    assert "exited with 3" in caplog.text and "boom" in caplog.text


@posix_only
def test_it_only_warns_when_disabled_or_without_npm(
    tmp_path: Path, npm_calls: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    frontend, dist = _checkout(tmp_path)
    with caplog.at_level(logging.WARNING, logger="stallion.web"):
        assert ensure_built(frontend, dist, enabled=False) is False
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        assert ensure_built(frontend, dist) is False
    assert _calls(npm_calls) == []
    assert caplog.text.count("run `make build`") == 2
