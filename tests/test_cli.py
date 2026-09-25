from __future__ import annotations

from pathlib import Path

import pytest

from stallion.cli import main

from .conftest import requires_ffmpeg


def test_unknown_preset_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "x.mp4", "-p", "bogus"]) == 2
    assert "unknown preset" in capsys.readouterr().err


def test_presets_listing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["presets"]) == 0
    out = capsys.readouterr().out
    assert "mp4-h264" in out and "dvd-pal" in out


@requires_ffmpeg
def test_convert_reports_skipped_inputs(
    media_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "convert",
            str(media_dir / "clip.mp4"),
            str(tmp_path / "missing.mp4"),
            "-p",
            "mp3",
            "-o",
            str(tmp_path / "out"),
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    output = capsys.readouterr()
    assert (tmp_path / "out" / "clip.mp3").stat().st_size > 0
    assert "missing.mp4" in output.err and "1 skipped" in output.out
    assert code == 1


@requires_ffmpeg
def test_convert_success(media_dir: Path, tmp_path: Path) -> None:
    args = ["convert", str(media_dir / "hd.mp4"), "-p", "mp4-h264", "--max-height", "360", "--speed", "fast"]
    assert main([*args, "-o", str(tmp_path), "--data-dir", str(tmp_path / "data")]) == 0
    assert (tmp_path / "hd.mp4").stat().st_size > 0
