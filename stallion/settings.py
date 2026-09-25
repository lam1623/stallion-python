"""User preferences persisted as JSON."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # None writes each file next to its source
    output_dir: str | None = None
    default_preset: str = "mp4-h264"
    concurrency: int = Field(1, ge=1, le=8)
    auto_start: bool = False
    autoload_subtitles: bool = True
    overwrite: bool = False
    delete_partial: bool = True
    notify_on_finish: bool = True
    theme: Literal["system", "dark", "light"] = "system"
    language: Literal["auto", "es", "en"] = "auto"


class SettingsPatch(BaseModel):
    """Partial update; only fields present in the request are applied."""

    model_config = ConfigDict(extra="forbid")

    output_dir: str | None = None
    default_preset: str | None = None
    concurrency: int | None = Field(None, ge=1, le=8)
    auto_start: bool | None = None
    autoload_subtitles: bool | None = None
    overwrite: bool | None = None
    delete_partial: bool | None = None
    notify_on_finish: bool | None = None
    theme: Literal["system", "dark", "light"] | None = None
    language: Literal["auto", "es", "en"] | None = None


class SettingsStore:
    """Settings persisted to ``path``; with ``path=None`` they live only in memory."""

    def __init__(self, path: Path | None, initial: Settings | None = None) -> None:
        self.path = path
        self._settings = initial or self._load()

    @property
    def current(self) -> Settings:
        return self._settings

    def _load(self) -> Settings:
        if self.path is None:
            return Settings()
        try:
            return Settings.model_validate_json(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValidationError, ValueError) as exc:
            log.warning("Ignoring unreadable settings file %s: %s", self.path, exc)
            return Settings()

    def update(self, patch: dict[str, Any]) -> Settings:
        merged = Settings.model_validate({**self._settings.model_dump(), **patch})
        self._write(merged)
        self._settings = merged
        return merged

    def _write(self, settings: Settings) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(settings.model_dump(), fh, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
