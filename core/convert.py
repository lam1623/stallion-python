from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional

from .models import ConversionJob, JobStatus, ProgressUpdate


class ConversionError(RuntimeError):
    """Raised when ffmpeg conversion fails."""


class FFmpegConverter:
    """Run ffmpeg conversions and emit progress updates."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg") -> None:
        self.ffmpeg_bin = ffmpeg_bin

    def build_command(self, job: ConversionJob) -> list[str]:
        preset = job.preset
        return [
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(job.input_path),
            "-c:v",
            preset.video_codec,
            "-preset",
            preset.encoder_preset,
            "-crf",
            str(preset.crf),
            "-c:a",
            preset.audio_codec,
            "-b:a",
            preset.audio_bitrate,
            *preset.extra_args,
            "-progress",
            "pipe:1",
            "-nostats",
            str(job.output_path),
        ]

    def run(
        self,
        job: ConversionJob,
        duration_s: float,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> None:
        """Execute one conversion and optionally stream progress events."""

        job.status = JobStatus.RUNNING
        cmd = self.build_command(job)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True,
        )

        progress_data: Dict[str, str] = {}

        assert proc.stdout is not None
        for line in proc.stdout:
            parsed = _parse_progress_line(line)
            if not parsed:
                continue
            key, value = parsed
            progress_data[key] = value

            if key == "progress":
                update = _build_update(progress_data, duration_s, job.id)
                if on_progress:
                    on_progress(update)
                if value == "end":
                    break

        stderr_out = ""
        if proc.stderr:
            stderr_out = proc.stderr.read().strip()
        retcode = proc.wait()

        if retcode == 0:
            job.status = JobStatus.COMPLETED
            job.error = None
            return

        job.status = JobStatus.FAILED
        job.error = stderr_out or f"ffmpeg failed with code {retcode}"
        raise ConversionError(job.error)


def _parse_progress_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or "=" not in line:
        return None
    key, value = line.split("=", 1)
    return key.strip(), value.strip()


def _build_update(progress_data: Dict[str, str], duration_s: float, job_id: str | None) -> ProgressUpdate:
    out_time_us = _to_int(progress_data.get("out_time_us"), default=0)
    out_time_s = out_time_us / 1_000_000

    if duration_s > 0:
        percent = min(100.0, max(0.0, (out_time_s / duration_s) * 100.0))
    else:
        percent = 0.0

    fps_value = progress_data.get("fps")
    fps = None
    if fps_value is not None:
        try:
            fps = float(fps_value)
        except ValueError:
            fps = None

    return ProgressUpdate(
        job_id=job_id,
        percent=percent,
        out_time_s=out_time_s,
        speed=progress_data.get("speed"),
        fps=fps,
        raw=dict(progress_data),
    )


def _to_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default
