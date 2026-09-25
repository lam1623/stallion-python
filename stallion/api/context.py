"""Shared application state handed to request handlers."""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import HTTPConnection

from ..config import AppConfig
from ..engine.ffmpeg import FFmpegInfo
from ..engine.presets import PresetCatalog
from ..fs import FileSystem
from ..jobs import JobManager
from ..settings import SettingsStore


@dataclass
class AppContext:
    config: AppConfig
    ffmpeg: FFmpegInfo | None
    ffmpeg_error: str | None
    settings: SettingsStore
    catalog: PresetCatalog
    fs: FileSystem
    manager: JobManager


async def get_ctx(conn: HTTPConnection) -> AppContext:
    ctx: AppContext = conn.app.state.ctx
    return ctx
