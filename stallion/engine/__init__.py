"""UI-agnostic conversion engine built on ffmpeg/ffprobe."""

from .command import OptionsError, build_command, find_external_subtitles, validate_options
from .ffmpeg import FFmpegInfo, FFmpegNotFoundError, discover
from .options import JobOptions, SubtitleStyle
from .presets import Preset, PresetCatalog
from .probe import MediaInfo, ProbeError, probe_media
from .runner import FFmpegRun, Progress, RunResult

__all__ = [
    "FFmpegInfo",
    "FFmpegNotFoundError",
    "FFmpegRun",
    "JobOptions",
    "MediaInfo",
    "OptionsError",
    "Preset",
    "PresetCatalog",
    "ProbeError",
    "Progress",
    "RunResult",
    "SubtitleStyle",
    "build_command",
    "discover",
    "find_external_subtitles",
    "probe_media",
    "validate_options",
]
