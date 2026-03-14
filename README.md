# Stallion

Legacy GTK interface for mencoder (original project), now with a modern FFmpeg-based core that can be reused by desktop and web frontends.

Copyright 2013-2014 Lino Alfonso <lino@lt.desoft.cu>

## Modern MVP (new code)

A new UI-agnostic core was added under `core/`:

- `core/probe.py`: media metadata extraction with `ffprobe`.
- `core/convert.py`: `ffmpeg` conversion with progress parsing (`-progress pipe:1`).
- `core/models.py`: typed models for jobs, presets, and progress updates.
- `core/cli.py`: CLI smoke path for end-to-end usage.
- `core/web_api.py`: FastAPI app exposing probe and conversion endpoints (desktop/web reuse).

## Run modern desktop UI

A modern cross-platform desktop UI is available in `modern_ui.py` (Tkinter/ttk):

- conversion queue,
- per-job and total progress,
- CRF + encoder preset controls,
- real-time conversion status.

```bash
python modern_ui.py
```

## Run CLI

```bash
python -m core.cli input.mp4 output.mp4 --crf 23 --preset medium
```

## Run Web API (for web frontends)

```bash
uvicorn core.web_api:app --reload --port 8000
```

Endpoints:
- `GET /health`
- `POST /probe`
- `POST /convert` (streaming progress events)

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` installed on the system
- Install Python deps:

```bash
pip install -r requirements.txt
```
