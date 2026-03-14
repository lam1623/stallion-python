"""Modern conversion core for Stallion.

This package is intentionally UI-agnostic so it can be reused by desktop,
web, or CLI frontends.
"""

from .models import ConversionJob, ConversionPreset, JobStatus, MediaInfo, ProgressUpdate
from .probe import probe_media
from .convert import FFmpegConverter

__all__ = [
    "ConversionJob",
    "ConversionPreset",
    "FFmpegConverter",
    "JobStatus",
    "MediaInfo",
    "ProgressUpdate",
    "probe_media",
]
