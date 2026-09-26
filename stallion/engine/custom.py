"""User-defined formats.

The format editor sends a :class:`FormatDraft`: a deliberately small model (container, codecs,
quality, size limits and a few vetted extra options) that compiles into a regular :class:`Preset`.
Nothing the user types reaches ffmpeg unchecked: codecs come from fixed tables and extra options
must be on an allowlist with a value pattern, so no draft can read or write arbitrary files.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .options import Accel
from .presets import AudioSpec, Preset, SoftSubtitleCodec, SpeedFamily, VideoSpec

log = logging.getLogger(__name__)

VideoCodec = Literal["h264", "hevc", "av1", "vp9", "copy", "none"]
AudioCodec = Literal["aac", "opus", "mp3", "flac", "copy", "none"]
Container = Literal["mp4", "mkv", "webm", "mov", "m4a", "mp3", "opus", "flac"]
Channels = Literal["source", "stereo", "mono"]

RESOLUTIONS = (360, 480, 720, 1080, 1440, 2160)
FRAME_RATES = (24, 25, 30, 50, 60)
CUSTOM_PREFIX = "custom-"


class FormatDraft(BaseModel):
    """What the format editor sends; :func:`compile_draft` turns it into a preset."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    description: str = Field("", max_length=200)
    container: Container = "mp4"
    video_codec: VideoCodec = "h264"
    # CRF; None uses the codec default
    quality: int | None = Field(None, ge=0, le=63)
    ten_bit: bool = False
    # Short-side limit (1080 = "1080p"); None keeps the source size
    max_height: int | None = None
    # Frame-rate cap; None keeps the source rate
    fps: int | None = None
    # Preferred encoder for this format; per-file choices still win
    accel: Accel = "auto"
    audio_codec: AudioCodec = "aac"
    audio_bitrate: int | None = None
    audio_channels: Channels = "source"
    extra_args: str = Field("", max_length=400)


@dataclass(frozen=True, slots=True)
class _Video:
    encoder: str
    label: str
    # default, minimum and maximum CRF
    crf: tuple[int, int, int]
    speed: SpeedFamily
    args: tuple[str, ...] = ()
    ten_bit: bool = True


@dataclass(frozen=True, slots=True)
class _Audio:
    encoder: str
    label: str
    bitrate: int | None = None
    choices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Container:
    extension: str
    muxer: str
    label: str
    video: frozenset[str]
    audio: frozenset[str]
    soft: SoftSubtitleCodec | None = None
    bitmap: bool = False
    output_args: tuple[str, ...] = ()


VIDEO: dict[str, _Video] = {
    "h264": _Video("libx264", "H.264", (21, 14, 34), "x26x", ten_bit=False),
    "hevc": _Video("libx265", "HEVC", (24, 16, 34), "x26x", ("-x265-params", "log-level=error")),
    "av1": _Video("libsvtav1", "AV1", (32, 20, 50), "svtav1"),
    "vp9": _Video("libvpx-vp9", "VP9", (32, 15, 45), "vpx", ("-row-mt", "1")),
}
AUDIO: dict[str, _Audio] = {
    "aac": _Audio("aac", "AAC", 192, (96, 128, 160, 192, 224, 256, 320, 384)),
    "opus": _Audio("libopus", "Opus", 128, (64, 96, 128, 160, 192, 256)),
    "mp3": _Audio("libmp3lame", "MP3", 192, (128, 160, 192, 256, 320)),
    "flac": _Audio("flac", "FLAC"),
}
_FASTSTART = ("-movflags", "+faststart")
CONTAINERS: dict[str, _Container] = {
    "mp4": _Container(
        ".mp4",
        "mp4",
        "MP4",
        frozenset({"h264", "hevc", "av1", "copy"}),
        frozenset({"aac", "mp3", "copy", "none"}),
        soft="mov_text",
        output_args=_FASTSTART,
    ),
    "mkv": _Container(
        ".mkv",
        "matroska",
        "MKV",
        frozenset({"h264", "hevc", "av1", "vp9", "copy"}),
        frozenset({"aac", "opus", "mp3", "flac", "copy", "none"}),
        soft="copy",
        bitmap=True,
    ),
    "webm": _Container(
        ".webm", "webm", "WebM", frozenset({"av1", "vp9"}), frozenset({"opus", "none"}), soft="webvtt"
    ),
    "mov": _Container(
        ".mov",
        "mov",
        "MOV",
        frozenset({"h264", "hevc", "copy"}),
        frozenset({"aac", "copy", "none"}),
        soft="mov_text",
        output_args=_FASTSTART,
    ),
    # Audio-only files: the container follows the codec
    "m4a": _Container(".m4a", "ipod", "M4A", frozenset({"none"}), frozenset({"aac"}), output_args=_FASTSTART),
    "mp3": _Container(
        ".mp3", "mp3", "MP3", frozenset({"none"}), frozenset({"mp3"}), output_args=("-id3v2_version", "3")
    ),
    "opus": _Container(".opus", "opus", "Opus", frozenset({"none"}), frozenset({"opus"})),
    "flac": _Container(".flac", "flac", "FLAC", frozenset({"none"}), frozenset({"flac"})),
}

# Extra options: flag -> (where it goes, value pattern). Anything else is refused.
_INT = r"\d{1,6}"
_WORD = r"[A-Za-z0-9_.+-]{1,32}"
_PARAMS = r"[A-Za-z0-9_.:=+,-]{1,300}"
_RATE = r"\d{1,6}(\.\d{1,3})?[kKmM]?"
EXTRA_OPTIONS: dict[str, tuple[Literal["video", "audio", "output"], str]] = {
    "-preset": ("video", _WORD),
    "-tune": ("video", _WORD),
    "-profile:v": ("video", _WORD),
    "-level:v": ("video", r"\d(\.\d)?"),
    "-x264-params": ("video", _PARAMS),
    "-x265-params": ("video", _PARAMS),
    "-svtav1-params": ("video", _PARAMS),
    "-g": ("video", _INT),
    "-bf": ("video", _INT),
    "-refs": ("video", _INT),
    "-keyint_min": ("video", _INT),
    "-sc_threshold": ("video", _INT),
    "-aq-mode": ("video", _INT),
    "-tile-columns": ("video", _INT),
    "-cpu-used": ("video", _INT),
    "-deadline": ("video", _WORD),
    "-lag-in-frames": ("video", _INT),
    "-maxrate": ("video", _RATE),
    "-bufsize": ("video", _RATE),
    "-tag:v": ("video", r"[A-Za-z0-9]{4}"),
    "-color_primaries": ("video", _WORD),
    "-color_trc": ("video", _WORD),
    "-colorspace": ("video", _WORD),
    "-ar": ("audio", _INT),
    "-cutoff": ("audio", _INT),
    "-application": ("audio", _WORD),
    "-compression_level": ("audio", _INT),
    "-movflags": ("output", r"[+-]?[a-z_]{1,32}([+-][a-z_]{1,32}){0,5}"),
}


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    message: str
    params: dict[str, str | int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "params": self.params}


class DraftError(ValueError):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues


def parse_extra_args(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split vetted extra options into (video, audio, output) argument lists."""

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise DraftError([Issue("extra_syntax", f"Could not read the extra options: {exc}")]) from None
    groups: dict[str, list[str]] = {"video": [], "audio": [], "output": []}
    if len(tokens) % 2:
        raise DraftError([Issue("extra_syntax", "Every extra option needs a value")])
    for flag, value in zip(tokens[::2], tokens[1::2], strict=True):
        rule = EXTRA_OPTIONS.get(flag)
        if rule is None:
            raise DraftError([Issue("extra_flag", f"Option not allowed: {flag}", {"flag": flag})])
        target, pattern = rule
        if not re.fullmatch(pattern, value):
            raise DraftError([Issue("extra_value", f"Bad value for {flag}: {value}", {"flag": flag})])
        groups[target] += [flag, value]
    return groups["video"], groups["audio"], groups["output"]


def draft_issues(draft: FormatDraft) -> list[Issue]:
    """Combinations that cannot work (the editor shows them and refuses to save)."""

    issues: list[Issue] = []
    box = CONTAINERS[draft.container]
    video, audio = draft.video_codec, draft.audio_codec
    if video not in box.video:
        issues.append(
            Issue(
                "video_container",
                f"{video} video does not fit in {box.label}",
                {"codec": video, "container": box.label},
            )
        )
    if audio not in box.audio:
        issues.append(
            Issue(
                "audio_container",
                f"{audio} audio does not fit in {box.label}",
                {"codec": audio, "container": box.label},
            )
        )
    if video == "none" and audio == "none":
        issues.append(Issue("empty", "The format needs video or audio"))
    spec = VIDEO.get(video)
    if draft.ten_bit and (spec is None or not spec.ten_bit):
        issues.append(Issue("ten_bit", f"{video} cannot be encoded in 10 bits here", {"codec": video}))
    if spec and draft.quality is not None and not spec.crf[1] <= draft.quality <= spec.crf[2]:
        issues.append(
            Issue(
                "quality",
                f"Quality must be between {spec.crf[1]} and {spec.crf[2]}",
                {"min": spec.crf[1], "max": spec.crf[2]},
            )
        )
    if draft.max_height is not None and draft.max_height not in RESOLUTIONS:
        issues.append(Issue("resolution", "Unsupported resolution"))
    if draft.fps is not None and draft.fps not in FRAME_RATES:
        issues.append(Issue("fps", "Unsupported frame rate"))
    if video == "copy" and (draft.max_height or draft.fps):
        issues.append(Issue("copy_filters", "Copied video cannot change its size or frame rate"))
    sound = AUDIO.get(audio)
    if draft.audio_bitrate is not None and (sound is None or draft.audio_bitrate not in sound.choices):
        issues.append(Issue("audio_bitrate", "Choose one of the listed audio bitrates"))
    try:
        parse_extra_args(draft.extra_args)
    except DraftError as exc:
        issues += exc.issues
    return issues


def compile_draft(draft: FormatDraft, preset_id: str) -> Preset:
    """Build the preset for a valid draft; raises :class:`DraftError` otherwise."""

    issues = draft_issues(draft)
    if issues:
        raise DraftError(issues)
    box = CONTAINERS[draft.container]
    extra_video, extra_audio, extra_output = parse_extra_args(draft.extra_args)
    tags: list[str] = []

    video: VideoSpec | None = None
    if draft.video_codec == "copy":
        video = VideoSpec(codec="copy", rate_control="none")
        tags.append("Copy")
    elif draft.video_codec != "none":
        spec = VIDEO[draft.video_codec]
        default, low, high = spec.crf
        args = [*spec.args]
        if draft.video_codec == "hevc" and draft.container in ("mp4", "mov"):
            args += ["-tag:v", "hvc1"]  # plays on Apple devices
        video = VideoSpec(
            codec=spec.encoder,
            rate_control="crf",
            quality=draft.quality if draft.quality is not None else default,
            quality_min=low,
            quality_max=high,
            speed_family=spec.speed,
            pix_fmt="yuv420p10le" if draft.ten_bit else "yuv420p",
            max_height=draft.max_height,
            fps=draft.fps,
            args=args + extra_video,
        )
        tags.append(spec.label + (" 10-bit" if draft.ten_bit else ""))

    audio: AudioSpec | None = None
    if draft.audio_codec == "copy":
        audio = AudioSpec(codec="copy")
    elif draft.audio_codec != "none":
        sound = AUDIO[draft.audio_codec]
        channels = {"stereo": 2, "mono": 1}.get(draft.audio_channels)
        audio = AudioSpec(
            codec=sound.encoder,
            bitrate_kbps=draft.audio_bitrate or sound.bitrate,
            bitrate_choices=list(sound.choices),
            channels=channels,
            args=extra_audio,
        )
        tags.append(sound.label)
    tags.append(box.label)

    names = {"en": draft.name.strip(), "es": draft.name.strip()}
    description = draft.description.strip()
    remux = draft.video_codec == "copy" and draft.audio_codec in ("copy", "none")
    return Preset(
        id=preset_id,
        category="custom",
        name=names,
        description={"en": description, "es": description},
        extension=box.extension,
        muxer=box.muxer,
        video=video,
        audio=audio,
        remux=remux,
        soft_subtitles=box.soft if video is not None else None,
        soft_bitmap_subtitles=box.bitmap,
        output_args=[*box.output_args, *extra_output],
        accel=draft.accel,
        tags=tags,
    )


def draft_warnings(draft: FormatDraft) -> list[Issue]:
    """Things that work but deserve a note (GPU notes that need the hardware come from the caller)."""

    warnings: list[Issue] = []
    if draft.video_codec == "copy" and draft.container != "mkv":
        label = CONTAINERS[draft.container].label
        message = f"Copying only works when the original video fits {label}"
        warnings.append(Issue("copy_source", message, {"container": label}))
    if draft.accel != "cpu" and draft.video_codec == "vp9":
        warnings.append(Issue("gpu_vp9", "VP9 has no GPU encoder, so the CPU encodes it"))
    if draft.accel != "cpu" and draft.video_codec in ("h264", "hevc", "av1"):
        video_extra, _, _ = parse_extra_args(draft.extra_args)
        if video_extra:
            warnings.append(Issue("gpu_extra", "Extra video options only apply when the CPU encodes"))
    return warnings


_REVERSE_VIDEO = {spec.encoder: key for key, spec in VIDEO.items()}
_REVERSE_AUDIO = {spec.encoder: key for key, spec in AUDIO.items()}
_BASE_ARGS = {("-x265-params", "log-level=error"), ("-row-mt", "1"), ("-tag:v", "hvc1")}


def draft_from_preset(preset: Preset) -> FormatDraft | None:
    """The editor's view of a preset, when the editor can express it (for "duplicate and edit")."""

    if preset.target or preset.layout or preset.animation or preset.fixed_resolution:
        return None
    wanted = (preset.extension, preset.muxer)
    container = next((key for key, box in CONTAINERS.items() if (box.extension, box.muxer) == wanted), None)
    if container is None:
        return None
    spec, sound = preset.video, preset.audio
    if spec is None:
        video_codec = "none"
    elif spec.codec == "copy":
        video_codec = "copy"
    else:
        video_codec = _REVERSE_VIDEO.get(spec.codec, "")
        if not video_codec or spec.rate_control != "crf" or spec.max_width:
            return None
    if sound is None:
        audio_codec = "none"
    else:
        audio_codec = "copy" if sound.codec == "copy" else _REVERSE_AUDIO.get(sound.codec, "")
    if not audio_codec:
        return None
    extra: list[str] = []
    if spec is not None:
        pairs = zip(spec.args[::2], spec.args[1::2], strict=False)
        extra += [part for pair in pairs if pair not in _BASE_ARGS for part in pair]
    if sound is not None:
        pairs = zip(sound.args[::2], sound.args[1::2], strict=False)
        extra += [part for pair in pairs for part in pair]
        if sound.sample_rate:
            extra += ["-ar", str(sound.sample_rate)]
    channels: Channels = "source"
    if sound is not None and sound.channels in (1, 2):
        channels = "stereo" if sound.channels == 2 else "mono"
    try:
        draft = FormatDraft(
            name=preset.name.get("en", preset.id)[:60],
            description=preset.description.get("en", "")[:200],
            container=container,
            video_codec=video_codec,
            quality=spec.quality if spec is not None and spec.codec != "copy" else None,
            ten_bit=bool(spec and spec.high_bit_depth),
            max_height=spec.max_height if spec is not None else None,
            fps=spec.fps if spec is not None else None,
            accel=preset.accel,
            audio_codec=audio_codec,
            audio_bitrate=sound.bitrate_kbps if sound is not None and sound.codec != "copy" else None,
            audio_channels=channels,
            extra_args=shlex.join(extra),
        )
    except ValidationError:
        return None
    return None if draft_issues(draft) else draft


def new_preset_id() -> str:
    return f"{CUSTOM_PREFIX}{uuid.uuid4().hex[:8]}"


class CustomPresetStore:
    """Custom formats saved as their drafts in ``path`` (JSON); ``path=None`` keeps them in memory."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._drafts: dict[str, FormatDraft] = self._load()

    def _load(self) -> dict[str, FormatDraft]:
        if self.path is None or not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Ignoring unreadable custom formats file %s: %s", self.path, exc)
            return {}
        drafts: dict[str, FormatDraft] = {}
        for item in raw.get("formats", []) if isinstance(raw, dict) else []:
            try:
                preset_id = str(item["id"])
                draft = FormatDraft.model_validate(item["draft"])
                compile_draft(draft, preset_id)
            except (KeyError, TypeError, ValidationError, DraftError, ValueError) as exc:
                log.warning("Skipping a custom format that no longer validates: %s", exc)
                continue
            drafts[preset_id] = draft
        return drafts

    def drafts(self) -> dict[str, FormatDraft]:
        return dict(self._drafts)

    def presets(self) -> list[Preset]:
        return [compile_draft(draft, preset_id) for preset_id, draft in self._drafts.items()]

    def save(self, preset_id: str, draft: FormatDraft) -> Preset:
        preset = compile_draft(draft, preset_id)
        drafts = {**self._drafts, preset_id: draft}
        self._write(drafts)
        self._drafts = drafts
        return preset

    def delete(self, preset_id: str) -> None:
        drafts = {key: value for key, value in self._drafts.items() if key != preset_id}
        self._write(drafts)
        self._drafts = drafts

    def _write(self, drafts: dict[str, FormatDraft]) -> None:
        if self.path is None:
            return
        payload = {
            "version": 1,
            "formats": [{"id": key, "draft": draft.model_dump()} for key, draft in drafts.items()],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".presets-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
