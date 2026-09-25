"""Desktop mode: private local server plus a native window (pywebview) or the browser."""

from __future__ import annotations

import importlib
import importlib.util
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn

from .api import create_app
from .config import AppConfig
from .fs import AUDIO_EXTENSIONS, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from .settings import SettingsStore

# Window color shown before the UI paints, matching --bg of each theme in index.css
WINDOW_BACKGROUNDS = {"light": "#f4f4f6", "dark": "#1a1b1f"}


def _window_background(config: AppConfig) -> str:
    theme = SettingsStore(config.settings_path).current.theme
    return WINDOW_BACKGROUNDS.get(theme, WINDOW_BACKGROUNDS["light"])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _patterns(extensions: frozenset[str]) -> str:
    return ";".join(f"*{ext}" for ext in sorted(extensions))


class NativeBridge:
    """Methods exposed to the web UI as ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._window: Any = None

    def attach(self, window: Any) -> None:
        self._window = window

    def _dialog(self, kind: str, **kwargs: Any) -> list[str]:
        import webview

        dialog_enum = getattr(webview, "FileDialog", None)
        dialog_type = getattr(dialog_enum, kind) if dialog_enum else getattr(webview, f"{kind}_DIALOG")
        result = self._window.create_file_dialog(dialog_type, **kwargs)
        return [str(p) for p in result] if result else []

    def pick_files(self) -> list[str]:
        media = _patterns(VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
        return self._dialog(
            "OPEN", allow_multiple=True, file_types=(f"Media files ({media})", "All files (*.*)")
        )

    def pick_folder(self) -> str | None:
        folders = self._dialog("FOLDER")
        return folders[0] if folders else None

    def pick_subtitle(self) -> str | None:
        subs = _patterns(SUBTITLE_EXTENSIONS)
        files = self._dialog(
            "OPEN", allow_multiple=False, file_types=(f"Subtitles ({subs})", "All files (*.*)")
        )
        return files[0] if files else None

    def open_path(self, path: str) -> bool:
        target = Path(path)
        if not target.exists():
            return False
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(target)], stdin=subprocess.DEVNULL, start_new_session=True)
        return True


def _preferred_gui() -> str | None:
    """On Linux, pick the installed toolkit so pywebview does not try (and log) GTK first."""

    if not sys.platform.startswith("linux"):
        return None
    if importlib.util.find_spec("qtpy") and importlib.util.find_spec("PyQt6"):
        return "qt"
    if importlib.util.find_spec("gi"):
        return "gtk"
    return None


def _start_server(config: AppConfig) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(
        uvicorn.Config(create_app(config), host=config.host, port=config.port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, name="stallion-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("The local Stallion server did not start")
        time.sleep(0.05)
    return server, thread


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=20)


def run_desktop(config: AppConfig, *, prefer_browser: bool = False) -> int:
    config.host = "127.0.0.1"
    config.port = _free_port()
    config.auth_token = secrets.token_urlsafe(24)
    config.desktop = True
    server, thread = _start_server(config)
    url = f"http://127.0.0.1:{config.port}/auth?token={config.auth_token}"

    webview: Any = None
    if not prefer_browser:
        try:
            webview = importlib.import_module("webview")
        except ImportError:
            print("pywebview is not installed; opening Stallion in your browser instead.")

    try:
        if webview is None:
            print(f"Stallion is running at {url}\nPress Ctrl+C to quit.")
            webbrowser.open(url)
            while thread.is_alive():
                thread.join(0.5)
            return 0
        bridge = NativeBridge()
        window = webview.create_window(
            "Stallion",
            url,
            js_api=bridge,
            width=1360,
            height=860,
            min_size=(980, 640),
            background_color=_window_background(config),
        )
        bridge.attach(window)
        webview.start(gui=_preferred_gui(), private_mode=False, storage_path=str(config.data_dir / "webview"))
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        _stop_server(server, thread)
