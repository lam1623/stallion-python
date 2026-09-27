from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stallion.engine.ffmpeg import FFmpegInfo, FFmpegNotFoundError, discover

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe")) and not os.environ.get(
    "STALLION_SKIP_FFMPEG_TESTS"
)
# Windows forbids ":" in file names
WEIRD_SUBTITLE = "weird 'name', [x]; y.srt" if sys.platform == "win32" else "weird 'name', [x]; y:z.srt"
requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")

SRT_UTF8 = """1
00:00:00,000 --> 00:00:01,500
Hello, world!

2
00:00:01,500 --> 00:00:03,000
Second line
"""

SRT_CP1252 = """1
00:00:00,000 --> 00:00:02,000
¿Qué pasó, señor Ñandú?
"""

ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 384
PlayResY: 288

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, \
MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hola desde ASS
"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def ffmpeg_info() -> FFmpegInfo:
    try:
        return discover()
    except FFmpegNotFoundError:
        pytest.skip("ffmpeg/ffprobe not installed")


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder with small synthetic media covering the interesting cases."""

    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not installed")
    root = tmp_path_factory.mktemp("media")
    (root / "subs").mkdir()
    (root / "subs" / "eng.srt").write_text(SRT_UTF8, encoding="utf-8")
    (root / "subs" / "spa.ass").write_text(ASS, encoding="utf-8")
    lavfi_video = ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=3"]
    lavfi_audio = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3"]

    _ff(
        *lavfi_video,
        *lavfi_audio,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-shortest",
        str(root / "clip.mp4"),
    )
    # Two audio tracks (the second one is the default) plus SRT and ASS subtitles
    _ff(
        "-i",
        str(root / "clip.mp4"),
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=48000:duration=3",
        "-i",
        str(root / "subs" / "eng.srt"),
        "-i",
        str(root / "subs" / "spa.ass"),
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-map",
        "1:a",
        "-map",
        "2:0",
        "-map",
        "3:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-c:s:0",
        "srt",
        "-c:s:1",
        "ass",
        "-metadata:s:a:0",
        "language=eng",
        "-metadata:s:a:1",
        "language=spa",
        "-metadata:s:s:0",
        "language=eng",
        "-metadata:s:s:1",
        "language=spa",
        "-disposition:a:1",
        "default",
        "-disposition:a:0",
        "0",
        str(root / "movie.mkv"),
    )
    # MP4 with an embedded mov_text track (cannot be copied into MKV as-is)
    _ff(
        "-i",
        str(root / "clip.mp4"),
        "-i",
        str(root / "subs" / "eng.srt"),
        "-map",
        "0",
        "-map",
        "1",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        str(root / "with_subs.mp4"),
    )
    (root / "movie.srt").write_text(SRT_UTF8, encoding="utf-8")
    (root / "latin1.srt").write_bytes(SRT_CP1252.encode("cp1252"))
    (root / WEIRD_SUBTITLE).write_text(SRT_UTF8, encoding="utf-8")
    _ff(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=330:duration=3",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "96k",
        str(root / "song.mp3"),
    )
    _ff(
        "-f",
        "lavfi",
        "-i",
        "aevalsrc=sin(440*2*PI*t)|sin(550*2*PI*t)|sin(660*2*PI*t)|0|sin(220*2*PI*t)|sin(330*2*PI*t)"
        ":channel_layout=5.1(side):sample_rate=48000:duration=2",
        "-c:a",
        "ac3",
        str(root / "surround.ac3"),
    )
    _ff(
        *lavfi_video[:3],
        "testsrc2=size=1280x720:rate=25:duration=2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-an",
        str(root / "hd.mp4"),
    )
    return root


@pytest.fixture(scope="session")
def long_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A clip slow enough to encode that cancellation and pausing can be observed."""

    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not installed")
    path = tmp_path_factory.mktemp("long") / "long.mp4"
    _ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1280x720:rate=30:duration=90",
        "-f",
        "lavfi",
        "-i",
        "sine=duration=90",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "30",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    )
    return path


@pytest.fixture(scope="session")
def hdr_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """10-bit video tagged as HDR10 (PQ transfer, BT.2020 primaries)."""

    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not installed")
    path = tmp_path_factory.mktemp("hdr") / "hdr.mkv"
    _ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=640x360:rate=25:duration=1",
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "yuv420p10le",
        "-color_primaries",
        "bt2020",
        "-color_trc",
        "smpte2084",
        "-colorspace",
        "bt2020nc",
        str(path),
    )
    return path
