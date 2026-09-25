"""Conversion presets: typed models plus the built-in catalog shipped as JSON."""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ffmpeg import FFmpegInfo

Category = Literal["video", "device", "audio", "disc", "remux"]
RateControl = Literal["crf", "bitrate", "qscale", "none"]
SpeedFamily = Literal["x26x", "svtav1", "vpx"]
SoftSubtitleCodec = Literal["mov_text", "webvtt", "copy"]

# Encoders implied by ffmpeg's -target shortcuts
TARGET_ENCODERS: dict[str, set[str]] = {
    "dvd": {"mpeg2video", "ac3"},
    "svcd": {"mpeg2video", "mp2"},
    "vcd": {"mpeg1video", "mp2"},
}

CATEGORY_ORDER: tuple[Category, ...] = ("video", "device", "audio", "disc", "remux")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoSpec(_Strict):
    codec: str
    rate_control: RateControl = "crf"
    quality: int | None = None
    quality_min: int | None = None
    quality_max: int | None = None
    speed_family: SpeedFamily | None = None
    pix_fmt: str | None = None
    max_height: int | None = None
    max_width: int | None = None
    args: list[str] = []


class AudioSpec(_Strict):
    codec: str
    bitrate_kbps: int | None = None
    bitrate_choices: list[int] = []
    channels: int | None = None
    sample_rate: int | None = None
    args: list[str] = []


class Preset(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: Category
    name: dict[str, str]
    description: dict[str, str]
    extension: str = Field(pattern=r"^\.[a-z0-9]+$")
    muxer: str | None = None
    video: VideoSpec | None = None
    audio: AudioSpec | None = None
    target: str | None = None
    widescreen: bool = True
    remux: bool = False
    soft_subtitles: SoftSubtitleCodec | None = None
    soft_bitmap_subtitles: bool = False
    fixed_resolution: bool = False
    output_args: list[str] = []
    tags: list[str] = []

    @property
    def can_burn_subtitles(self) -> bool:
        return self.video is not None and self.video.codec != "copy"

    @property
    def target_family(self) -> str | None:
        return self.target.split("-", 1)[1] if self.target else None

    def required_encoders(self) -> set[str]:
        needed = {spec.codec for spec in (self.video, self.audio) if spec is not None}
        if self.target_family:
            needed |= TARGET_ENCODERS.get(self.target_family, set())
        needed.discard("copy")
        return needed


class PresetView(Preset):
    """Preset as exposed by the API, annotated with local encoder availability."""

    available: bool = True
    missing_encoders: list[str] = []


class PresetCatalog:
    def __init__(self, presets: list[Preset], ffmpeg: FFmpegInfo | None = None) -> None:
        self._presets = {p.id: p for p in presets}
        self._ffmpeg = ffmpeg

    @classmethod
    def builtin(cls, ffmpeg: FFmpegInfo | None = None) -> PresetCatalog:
        raw = json.loads(resources.files("stallion.engine").joinpath("presets.json").read_text("utf-8"))
        return cls([Preset.model_validate(item) for item in raw["presets"]], ffmpeg)

    def __contains__(self, preset_id: object) -> bool:
        return preset_id in self._presets

    def __iter__(self) -> Iterator[Preset]:
        return iter(self._presets.values())

    def get(self, preset_id: str) -> Preset:
        try:
            return self._presets[preset_id]
        except KeyError:
            raise KeyError(f"Unknown preset '{preset_id}'") from None

    def missing_encoders(self, preset: Preset) -> list[str]:
        if self._ffmpeg is None:
            return sorted(preset.required_encoders())
        return sorted(e for e in preset.required_encoders() if not self._ffmpeg.has_encoder(e))

    def views(self) -> list[PresetView]:
        ordered = sorted(self._presets.values(), key=lambda p: CATEGORY_ORDER.index(p.category))
        views = []
        for preset in ordered:
            missing = self.missing_encoders(preset)
            views.append(PresetView(**preset.model_dump(), available=not missing, missing_encoders=missing))
        return views
