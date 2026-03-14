from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .convert import FFmpegConverter, _build_update, _parse_progress_line
from .models import ConversionJob, ConversionPreset
from .probe import ProbeError, probe_media

app = FastAPI(title="Stallion Core API", version="0.1.0")


class ProbeRequest(BaseModel):
    input_path: str


class ConvertRequest(BaseModel):
    input_path: str
    output_path: str
    crf: int = Field(default=23, ge=0, le=51)
    encoder_preset: str = "medium"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
    ffmpeg_bin: str = "ffmpeg"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/probe")
def probe(payload: ProbeRequest) -> dict:
    try:
        info = probe_media(payload.input_path)
    except ProbeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "duration_s": info.duration_s,
        "width": info.width,
        "height": info.height,
        "video_codec": info.video_codec,
        "audio_codec": info.audio_codec,
        "format_name": info.format_name,
    }


@app.post("/convert")
async def convert(payload: ConvertRequest) -> StreamingResponse:
    input_path = Path(payload.input_path)
    if not input_path.exists():
        raise HTTPException(status_code=400, detail="input file does not exist")

    try:
        media = probe_media(input_path)
    except ProbeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preset = ConversionPreset(
        crf=payload.crf,
        encoder_preset=payload.encoder_preset,
        video_codec=payload.video_codec,
        audio_codec=payload.audio_codec,
        audio_bitrate=payload.audio_bitrate,
    )
    job = ConversionJob(
        input_path=input_path,
        output_path=Path(payload.output_path),
        preset=preset,
        id="api-job-1",
    )

    async def event_stream() -> AsyncIterator[str]:
        converter = FFmpegConverter(ffmpeg_bin=payload.ffmpeg_bin)
        cmd = converter.build_command(job)

        import asyncio

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        progress_data: dict[str, str] = {}

        assert proc.stdout is not None
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace")
            parsed = _parse_progress_line(line)
            if not parsed:
                continue
            key, value = parsed
            progress_data[key] = value
            if key == "progress":
                update = _build_update(progress_data, media.duration_s, job.id)
                yield json.dumps(
                    {
                        "type": "progress",
                        "job_id": update.job_id,
                        "percent": update.percent,
                        "out_time_s": update.out_time_s,
                        "speed": update.speed,
                        "fps": update.fps,
                    }
                ) + "\n"
                if value == "end":
                    break

        stderr_output: Optional[str] = None
        if proc.stderr:
            stderr_output = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() or None

        code = await proc.wait()
        if code != 0:
            yield json.dumps({"type": "error", "message": stderr_output or f"ffmpeg failed ({code})"}) + "\n"
        else:
            yield json.dumps({"type": "completed", "output_path": str(job.output_path)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
