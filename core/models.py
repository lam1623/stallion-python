from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(slots=True)
class ConversionPreset:
    """Encoding options that can be reused across jobs."""

    name: str = "h264-balanced"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 23
    encoder_preset: str = "medium"
    audio_bitrate: str = "128k"
    extra_args: tuple[str, ...] = ()


@dataclass(slots=True)
class MediaInfo:
    """Relevant metadata from ffprobe."""

    duration_s: float
    width: Optional[int]
    height: Optional[int]
    video_codec: Optional[str]
    audio_codec: Optional[str]
    format_name: str
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ConversionJob:
    """A conversion unit executed by ffmpeg."""

    input_path: Path
    output_path: Path
    preset: ConversionPreset = field(default_factory=ConversionPreset)
    status: JobStatus = JobStatus.QUEUED
    error: Optional[str] = None
    id: Optional[str] = None


@dataclass(slots=True)
class ProgressUpdate:
    """Progress event emitted while ffmpeg runs."""

    job_id: Optional[str]
    percent: float
    out_time_s: float
    speed: Optional[str]
    fps: Optional[float]
    raw: Dict[str, str] = field(default_factory=dict)
