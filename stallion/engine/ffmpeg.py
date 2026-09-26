"""Locate the ffmpeg/ffprobe binaries and inspect their capabilities."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Keep Windows from flashing a console window for every ffmpeg child process
POPEN_KWARGS: dict[str, Any] = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_VERSION_RE = re.compile(r"ffmpeg version (\S+)")
_ENCODER_RE = re.compile(r"^\s*[VAS][A-Z.]{5}\s+(\S+)")
# Flag columns: "TSC" up to FFmpeg 7, "TS" since FFmpeg 8 (command support was dropped)
_FILTER_RE = re.compile(r"^\s*[T.][S.][C.]?\s+(\S+)\s+\S+->\S+")
# Built into every FFmpeg: when none of them is listed, the list itself could not be read
_NATIVE_ENCODERS = frozenset({"aac", "flac", "pcm_s16le"})
_NATIVE_FILTERS = frozenset({"scale", "format", "volume"})
# (ffmpeg, "encoder"/"filter", name) -> answer of a one-off `ffmpeg -h` query
_probes: dict[tuple[str, str, str], bool] = {}


class FFmpegNotFoundError(RuntimeError):
    """Raised when ffmpeg or ffprobe cannot be located."""


@dataclass(frozen=True, slots=True)
class FFmpegInfo:
    ffmpeg: str
    ffprobe: str
    version: str
    encoders: frozenset[str] = field(default_factory=frozenset)
    filters: frozenset[str] = field(default_factory=frozenset)

    def has_encoder(self, name: str) -> bool:
        if self.encoders:
            return name in self.encoders
        return probe_component(self.ffmpeg, "encoder", name)

    def has_filter(self, name: str) -> bool:
        if self.filters:
            return name in self.filters
        return probe_component(self.ffmpeg, "filter", name)


def probe_component(ffmpeg: str, kind: str, name: str) -> bool:
    """Ask ffmpeg about a single encoder or filter (fallback when its full list could not be read).

    An unclear answer counts as available: a format is never blocked by a failed check, and a
    missing encoder still gets a clear error from ffmpeg at conversion time.
    """

    key = (ffmpeg, kind, name)
    if key not in _probes:
        try:
            text = _capture([ffmpeg, "-hide_banner", "-h", f"{kind}={name}"])
        except (OSError, subprocess.SubprocessError):
            text = ""
        _probes[key] = "is not recognized" not in text and "Unknown filter" not in text
    return _probes[key]


def _resolve_binary(explicit: str | None, env_var: str, default: str) -> str | None:
    candidate = explicit or os.environ.get(env_var) or default
    if os.path.dirname(candidate):
        return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else None
    return shutil.which(candidate)


def _capture(argv: list[str]) -> str:
    proc = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        **POPEN_KWARGS,
    )
    return proc.stdout


def parse_encoders(text: str) -> frozenset[str]:
    names: set[str] = set()
    started = False
    for line in text.splitlines():
        if line.strip().startswith("------"):
            started = True
            continue
        if started and (match := _ENCODER_RE.match(line)):
            names.add(match.group(1))
    return frozenset(names)


def parse_filters(text: str) -> frozenset[str]:
    return frozenset(m.group(1) for line in text.splitlines() if (m := _FILTER_RE.match(line)))


def discover(ffmpeg_bin: str | None = None, ffprobe_bin: str | None = None) -> FFmpegInfo:
    """Find ffmpeg/ffprobe (explicit path, STALLION_FFMPEG/STALLION_FFPROBE, then PATH)."""

    ffmpeg = _resolve_binary(ffmpeg_bin, "STALLION_FFMPEG", "ffmpeg")
    ffprobe = _resolve_binary(ffprobe_bin, "STALLION_FFPROBE", "ffprobe")
    missing = [name for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if not path]
    if missing or ffmpeg is None or ffprobe is None:
        raise FFmpegNotFoundError(
            f"{' and '.join(missing)} not found. Install FFmpeg or set STALLION_FFMPEG / STALLION_FFPROBE."
        )

    try:
        version_text = _capture([ffmpeg, "-hide_banner", "-version"])
        encoder_text = _capture([ffmpeg, "-hide_banner", "-encoders"])
        filter_text = _capture([ffmpeg, "-hide_banner", "-filters"])
    except (OSError, subprocess.SubprocessError) as exc:
        raise FFmpegNotFoundError(f"ffmpeg at {ffmpeg} is not usable: {exc}") from exc

    encoders = parse_encoders(encoder_text)
    if not encoders & _NATIVE_ENCODERS:
        log.warning(
            "Could not read the encoder list of %s, checking encoders one by one. It began with: %r",
            ffmpeg,
            encoder_text[:240],
        )
        encoders = frozenset()
    filters = parse_filters(filter_text)
    if not filters & _NATIVE_FILTERS:
        log.warning(
            "Could not read the filter list of %s, checking filters one by one. It began with: %r",
            ffmpeg,
            filter_text[:240],
        )
        filters = frozenset()
    log.info("FFmpeg capabilities: %d encoders, %d filters", len(encoders), len(filters))

    match = _VERSION_RE.search(version_text)
    return FFmpegInfo(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        version=match.group(1) if match else "unknown",
        encoders=encoders,
        filters=filters,
    )
