"""Filesystem access restricted to configured media roots."""

from __future__ import annotations

import os
import re
import string
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".mpg",
        ".mpeg",
        ".vob",
        ".ts",
        ".m2ts",
        ".mts",
        ".3gp",
        ".ogv",
        ".divx",
        ".asf",
        ".rm",
        ".rmvb",
        ".f4v",
        ".mxf",
        ".dv",
        ".y4m",
    }
)
AUDIO_EXTENSIONS = frozenset(
    {
        ".mp3",
        ".m4a",
        ".aac",
        ".flac",
        ".wav",
        ".ogg",
        ".oga",
        ".opus",
        ".wma",
        ".ac3",
        ".dts",
        ".aiff",
        ".aif",
        ".alac",
        ".amr",
        ".mka",
        ".ape",
        ".wv",
    }
)
SUBTITLE_EXTENSIONS = frozenset([".srt", ".ass", ".ssa", ".vtt"])

EntryKind = Literal["dir", "video", "audio", "subtitle", "file"]


class PathError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Root(BaseModel):
    name: str
    path: str


class Entry(BaseModel):
    name: str
    path: str
    kind: EntryKind
    size: int | None = None
    modified: float | None = None


class Listing(BaseModel):
    path: str
    parent: str | None
    root: str
    entries: list[Entry]
    truncated: bool = False


def classify(path: Path) -> EntryKind:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in SUBTITLE_EXTENSIONS:
        return "subtitle"
    return "file"


def _natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]


def filesystem_roots() -> list[Path]:
    if sys.platform == "win32":
        return [Path(f"{letter}:\\") for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
    return [Path("/")]


class FileSystem:
    def __init__(self, roots: list[Path], max_entries: int = 5000) -> None:
        resolved: list[Path] = []
        for root in roots:
            try:
                path = root.expanduser().resolve(strict=True)
            except OSError:
                continue
            if path.is_dir() and path not in resolved:
                resolved.append(path)
        self._roots = resolved
        self.max_entries = max_entries

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def root_views(self) -> list[Root]:
        home = Path.home()
        views = []
        for root in self._roots:
            if root == home:
                name = "Home"
            elif root == Path(root.anchor):
                name = root.anchor.rstrip("\\") or "/"
            else:
                name = root.name or str(root)
            views.append(Root(name=name, path=str(root)))
        return views

    def root_of(self, path: Path) -> Path | None:
        matches = [root for root in self._roots if path == root or path.is_relative_to(root)]
        return max(matches, key=lambda r: len(r.parts)) if matches else None

    def resolve(
        self, raw: str, *, kind: Literal["file", "dir", "any"] = "any", must_exist: bool = True
    ) -> Path:
        if not raw or "\x00" in raw:
            raise PathError("bad_path", "Empty or invalid path")
        path = Path(raw)
        if not path.is_absolute():
            raise PathError("bad_path", "Paths must be absolute")
        try:
            resolved = path.resolve(strict=must_exist)
        except (OSError, RuntimeError) as exc:
            raise PathError("not_found", f"Not found: {raw}") from exc
        if self.root_of(resolved) is None:
            raise PathError("outside_roots", "This location is outside the folders Stallion can access")
        if must_exist:
            if kind == "file" and not resolved.is_file():
                raise PathError("not_a_file", f"Not a file: {raw}")
            if kind == "dir" and not resolved.is_dir():
                raise PathError("not_a_dir", f"Not a folder: {raw}")
        return resolved

    def list_dir(self, raw: str, *, show_all: bool = False, show_hidden: bool = False) -> Listing:
        directory = self.resolve(raw, kind="dir")
        root = self.root_of(directory)
        assert root is not None
        entries: list[Entry] = []
        truncated = False
        try:
            with os.scandir(directory) as scan:
                for item in scan:
                    if not show_hidden and item.name.startswith("."):
                        continue
                    try:
                        is_dir = item.is_dir()
                        stat = item.stat() if not is_dir else None
                    except OSError:
                        continue
                    item_kind: EntryKind = "dir" if is_dir else classify(Path(item.name))
                    if not show_all and item_kind == "file":
                        continue
                    if len(entries) >= self.max_entries:
                        truncated = True
                        break
                    entries.append(
                        Entry(
                            name=item.name,
                            path=str(directory / item.name),
                            kind=item_kind,
                            size=stat.st_size if stat else None,
                            modified=stat.st_mtime if stat else None,
                        )
                    )
        except PermissionError as exc:
            raise PathError("forbidden", f"Permission denied: {directory}") from exc
        entries.sort(key=lambda e: (e.kind != "dir", _natural_key(e.name)))
        parent = directory.parent if directory != root else None
        return Listing(
            path=str(directory),
            parent=str(parent) if parent else None,
            root=str(root),
            entries=entries,
            truncated=truncated,
        )
