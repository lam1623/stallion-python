"""Runtime configuration from CLI flags and ``STALLION_*`` environment variables."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

from .fs import filesystem_roots


def default_data_dir() -> Path:
    env = os.environ.get("STALLION_DATA_DIR")
    return Path(env) if env else Path(user_data_dir("stallion", appauthor=False))


def default_media_roots(desktop: bool) -> list[Path]:
    env = os.environ.get("STALLION_MEDIA_ROOTS")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p.strip()]
    if desktop:
        # The desktop app runs as the logged-in user with native file dialogs
        return filesystem_roots()
    roots = [Path.home()]
    if sys.platform.startswith("linux"):
        roots += [p for p in (Path("/media"), Path("/mnt"), Path("/run/media")) if p.is_dir()]
    elif sys.platform == "darwin":
        roots.append(Path("/Volumes"))
    return roots


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


@dataclass
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    # None disables authentication (only for trusted reverse-proxy setups)
    auth_token: str | None = None
    media_roots: list[Path] = field(default_factory=lambda: default_media_roots(desktop=False))
    data_dir: Path = field(default_factory=default_data_dir)
    ffmpeg_bin: str | None = None
    ffprobe_bin: str | None = None
    desktop: bool = False
    static_dir: Path | None = None
    # Look for GPU encoders at startup (STALLION_HWENC=0 turns it off)
    detect_gpu: bool = field(default_factory=lambda: gpu_detection_from_env())

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def formats_path(self) -> Path:
        """The user's own formats."""

        return self.data_dir / "presets.json"


def auth_enabled_from_env() -> bool:
    return _env_bool("STALLION_AUTH", True)


def gpu_detection_from_env() -> bool:
    return _env_bool("STALLION_HWENC", True)
