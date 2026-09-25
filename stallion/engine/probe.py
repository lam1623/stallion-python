"""Media inspection through ffprobe."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .ffmpeg import POPEN_KWARGS

BITMAP_SUBTITLE_CODECS = frozenset(
    {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub", "dvb_teletext", "arib_caption"}
)
ASS_SUBTITLE_CODECS = frozenset({"ass", "ssa"})
IMAGE_FORMATS = frozenset({"image2", "png_pipe", "jpeg_pipe", "webp_pipe", "bmp_pipe", "tiff_pipe"})


class ProbeError(RuntimeError):
    """Raised when a file cannot be inspected or is not usable media."""


class VideoStream(BaseModel):
    index: int
    codec: str
    width: int
    height: int
    fps: float | None = None
    pix_fmt: str | None = None
    bitrate: int | None = None
    rotation: int = 0
    display_aspect: float | None = None
    hdr: bool = False

    @property
    def display_width(self) -> int:
        return self.height if self.rotation in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.rotation in (90, 270) else self.height

    @property
    def aspect(self) -> float:
        if self.display_aspect:
            return self.display_aspect
        return self.display_width / self.display_height if self.display_height else 16 / 9


class AudioStream(BaseModel):
    index: int
    position: int
    codec: str
    language: str | None = None
    title: str | None = None
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    bitrate: int | None = None
    default: bool = False


class SubtitleStream(BaseModel):
    index: int
    position: int
    codec: str
    language: str | None = None
    title: str | None = None
    bitmap: bool = False
    default: bool = False
    forced: bool = False


class MediaInfo(BaseModel):
    path: str
    format_name: str
    format_label: str | None = None
    duration_s: float = 0.0
    size_bytes: int = 0
    bitrate: int | None = None
    video: VideoStream | None = None
    cover_art_index: int | None = None
    audio: list[AudioStream] = []
    subtitles: list[SubtitleStream] = []

    @property
    def default_audio_position(self) -> int:
        for track in self.audio:
            if track.default:
                return track.position
        return 0


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        return None


def _ratio(value: Any) -> float | None:
    if not isinstance(value, str) or value in ("0/0", "N/A"):
        return None
    sep = "/" if "/" in value else ":" if ":" in value else None
    if sep is None:
        return _float(value)
    num, _, den = value.partition(sep)
    n, d = _float(num), _float(den)
    return n / d if n and d else None


def _rotation(stream: dict[str, Any]) -> int:
    raw: Any = (stream.get("tags") or {}).get("rotate")
    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            raw = side_data["rotation"]
    value = _int(raw)
    return (round(value / 90) * 90) % 360 if value else 0


def _tag(stream: dict[str, Any], key: str) -> str | None:
    value = (stream.get("tags") or {}).get(key)
    if not value or (key == "language" and value == "und"):
        return None
    return str(value)


def parse_probe(payload: dict[str, Any], path: str | Path) -> MediaInfo:
    """Turn ffprobe JSON into :class:`MediaInfo` (pure, easy to test)."""

    fmt = payload.get("format") or {}
    streams = payload.get("streams") or []
    format_name = str(fmt.get("format_name") or "unknown")

    video: VideoStream | None = None
    cover_art_index: int | None = None
    audio: list[AudioStream] = []
    subtitles: list[SubtitleStream] = []

    for stream in streams:
        kind = stream.get("codec_type")
        disposition = stream.get("disposition") or {}
        index = int(stream.get("index", 0))
        codec = str(stream.get("codec_name") or "unknown")

        if kind == "video":
            if disposition.get("attached_pic"):
                cover_art_index = cover_art_index if cover_art_index is not None else index
                continue
            if video is not None:
                continue
            color_transfer = str(stream.get("color_transfer") or "")
            video = VideoStream(
                index=index,
                codec=codec,
                width=_int(stream.get("width")) or 0,
                height=_int(stream.get("height")) or 0,
                fps=_ratio(stream.get("avg_frame_rate")) or _ratio(stream.get("r_frame_rate")),
                pix_fmt=stream.get("pix_fmt"),
                bitrate=_int(stream.get("bit_rate")),
                rotation=_rotation(stream),
                display_aspect=_ratio(stream.get("display_aspect_ratio")),
                hdr=color_transfer in ("smpte2084", "arib-std-b67"),
            )
        elif kind == "audio":
            audio.append(
                AudioStream(
                    index=index,
                    position=len(audio),
                    codec=codec,
                    language=_tag(stream, "language"),
                    title=_tag(stream, "title"),
                    channels=_int(stream.get("channels")),
                    channel_layout=stream.get("channel_layout"),
                    sample_rate=_int(stream.get("sample_rate")),
                    bitrate=_int(stream.get("bit_rate")),
                    default=bool(disposition.get("default")),
                )
            )
        elif kind == "subtitle":
            subtitles.append(
                SubtitleStream(
                    index=index,
                    position=len(subtitles),
                    codec=codec,
                    language=_tag(stream, "language"),
                    title=_tag(stream, "title"),
                    bitmap=codec in BITMAP_SUBTITLE_CODECS,
                    default=bool(disposition.get("default")),
                    forced=bool(disposition.get("forced")),
                )
            )

    if video is None and not audio:
        raise ProbeError("No audio or video streams found")
    if video is not None and format_name in IMAGE_FORMATS:
        raise ProbeError("This is a still image, not a video")

    duration = _float(fmt.get("duration")) or 0.0
    if duration <= 0 and video is not None:
        duration = (
            _float(next((s.get("duration") for s in streams if s.get("index") == video.index), 0)) or 0.0
        )

    return MediaInfo(
        path=str(path),
        format_name=format_name,
        format_label=fmt.get("format_long_name"),
        duration_s=max(0.0, duration),
        size_bytes=_int(fmt.get("size")) or 0,
        bitrate=_int(fmt.get("bit_rate")),
        video=video,
        cover_art_index=cover_art_index,
        audio=audio,
        subtitles=subtitles,
    )


async def probe_media(path: str | Path, ffprobe: str, time_limit: float = 60.0) -> MediaInfo:
    """Inspect ``path`` with ffprobe; both pipes are drained concurrently."""

    argv = [ffprobe, "-v", "error", "-hide_banner", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **POPEN_KWARGS,
        )
    except OSError as exc:
        raise ProbeError(f"Cannot run ffprobe: {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), time_limit)
    except (TimeoutError, asyncio.CancelledError) as exc:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), 5)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise ProbeError("ffprobe timed out") from exc

    if proc.returncode != 0:
        lines = [ln for ln in stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
        raise ProbeError(lines[-1] if lines else "Not a media file")

    try:
        payload = json.loads(stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Invalid ffprobe output: {exc}") from exc
    return parse_probe(payload, path)
