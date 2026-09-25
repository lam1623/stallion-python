"""Font families available for burned-in subtitles."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache

from .engine.ffmpeg import POPEN_KWARGS

FALLBACK_FONTS = [
    "Arial",
    "DejaVu Sans",
    "Georgia",
    "Liberation Sans",
    "Noto Sans",
    "Roboto",
    "Tahoma",
    "Times New Roman",
    "Trebuchet MS",
    "Verdana",
]


@lru_cache(maxsize=1)
def list_fonts() -> list[str]:
    """Installed families via fontconfig (what libass uses), else a safe list."""

    fc_list = shutil.which("fc-list")
    if not fc_list:
        return FALLBACK_FONTS
    try:
        proc = subprocess.run(
            [fc_list, ":", "family"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            stdin=subprocess.DEVNULL,
            **POPEN_KWARGS,
        )
    except (OSError, subprocess.SubprocessError):
        return FALLBACK_FONTS
    families = {line.split(",")[0].strip() for line in proc.stdout.splitlines() if line.strip()}
    families = {f for f in families if f and not f.startswith(".")}
    return sorted(families | {"Arial"}, key=str.casefold) if families else FALLBACK_FONTS
