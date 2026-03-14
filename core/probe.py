from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .models import MediaInfo


class ProbeError(RuntimeError):
    """Raised when ffprobe fails or returns invalid metadata."""


def probe_media(input_path: str | Path, ffprobe_bin: str = "ffprobe") -> MediaInfo:
    """Return media metadata using ffprobe JSON output."""

    path = Path(input_path)
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ProbeError(proc.stderr.strip() or "ffprobe failed")

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Invalid ffprobe JSON: {exc}") from exc

    streams = payload.get("streams", [])
    format_info = payload.get("format", {})

    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    duration_text = format_info.get("duration") or video.get("duration") or 0
    try:
        duration_s = float(duration_text)
    except (TypeError, ValueError):
        duration_s = 0.0

    return MediaInfo(
        duration_s=duration_s,
        width=_to_int(video.get("width")),
        height=_to_int(video.get("height")),
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name"),
        format_name=str(format_info.get("format_name", "unknown")),
        raw=payload,
    )


def _to_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
