from __future__ import annotations

from pathlib import Path

from stallion.config import AppConfig
from stallion.desktop import WINDOW_BACKGROUNDS, _window_background
from stallion.settings import SettingsStore


def test_window_background_follows_the_saved_theme(tmp_path: Path) -> None:
    config = AppConfig(media_roots=[tmp_path], data_dir=tmp_path)
    assert _window_background(config) == WINDOW_BACKGROUNDS["light"]
    SettingsStore(config.settings_path).update({"theme": "dark"})
    assert _window_background(config) == WINDOW_BACKGROUNDS["dark"]
    SettingsStore(config.settings_path).update({"theme": "system"})
    assert _window_background(config) == WINDOW_BACKGROUNDS["light"]
