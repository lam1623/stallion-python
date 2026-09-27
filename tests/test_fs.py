from __future__ import annotations

import os
from pathlib import Path

import pytest

from stallion.fs import FileSystem, PathError


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "Season 1").mkdir(parents=True)
    (root / "Season 1" / "ep10.mkv").touch()
    (root / "Season 1" / "ep2.mkv").touch()
    (root / "Season 1" / "ep2.srt").touch()
    (root / "Season 1" / "notes.txt").touch()
    (root / ".hidden.mp4").touch()
    (tmp_path / "outside.mp4").touch()
    return root


def test_listing_filters_and_sorts_naturally(tree: Path) -> None:
    fs = FileSystem([tree])
    listing = fs.list_dir(str(tree / "Season 1"))
    assert [e.name for e in listing.entries] == ["ep2.mkv", "ep2.srt", "ep10.mkv"]
    assert [e.kind for e in listing.entries] == ["video", "subtitle", "video"]
    assert listing.parent == str(tree)
    assert "notes.txt" in [e.name for e in fs.list_dir(str(tree / "Season 1"), show_all=True).entries]

    top = fs.list_dir(str(tree))
    assert top.parent is None and [e.name for e in top.entries] == ["Season 1"]
    assert ".hidden.mp4" in [e.name for e in fs.list_dir(str(tree), show_hidden=True).entries]


@pytest.mark.parametrize("relative", ["../outside.mp4", "Season 1/../../outside.mp4"])
def test_traversal_is_blocked(tree: Path, relative: str) -> None:
    with pytest.raises(PathError) as err:
        FileSystem([tree]).resolve(str(tree / relative), kind="file")
    assert err.value.code == "outside_roots"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_cannot_escape(tree: Path) -> None:
    (tree / "link.mp4").symlink_to(tree.parent / "outside.mp4")
    (tree / "linkdir").symlink_to(tree.parent)
    fs = FileSystem([tree])
    with pytest.raises(PathError):
        fs.resolve(str(tree / "link.mp4"), kind="file")
    with pytest.raises(PathError):
        fs.list_dir(str(tree / "linkdir"))


def test_bad_inputs(tree: Path) -> None:
    fs = FileSystem([tree])
    for raw in ["", "relative/path.mp4", "/x\x00y"]:
        with pytest.raises(PathError):
            fs.resolve(raw)
    with pytest.raises(PathError) as err:
        fs.resolve(str(tree / "missing.mp4"))
    assert err.value.code == "not_found"
    with pytest.raises(PathError) as err:
        fs.resolve(str(tree / "Season 1"), kind="file")
    assert err.value.code == "not_a_file"


def test_missing_roots_are_ignored(tree: Path) -> None:
    fs = FileSystem([tree / "nope", tree])
    assert fs.roots == [tree.resolve()]
    assert fs.root_views()[0].path == str(tree.resolve())
