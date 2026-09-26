from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from stallion.api import create_app
from stallion.config import AppConfig
from stallion.engine.command import SAMPLE_MEDIA, build_command, display_command
from stallion.engine.custom import (
    CustomPresetStore,
    DraftError,
    FormatDraft,
    compile_draft,
    draft_from_preset,
    draft_issues,
    parse_extra_args,
)
from stallion.engine.options import JobOptions
from stallion.engine.presets import PresetCatalog

from .conftest import requires_ffmpeg
from .test_api import AUTH, TOKEN

CATALOG = PresetCatalog.builtin()


def draft(**overrides: Any) -> FormatDraft:
    return FormatDraft.model_validate({"name": "Mi formato", **overrides})


def codes(value: FormatDraft) -> set[str]:
    return {issue.code for issue in draft_issues(value)}


def test_compile_a_hevc_10bit_mp4() -> None:
    preset = compile_draft(
        draft(
            video_codec="hevc",
            ten_bit=True,
            quality=22,
            max_height=1080,
            fps=30,
            audio_bitrate=256,
            audio_channels="stereo",
            extra_args="-tune grain -x265-params aq-mode=3 -movflags +faststart+frag_keyframe",
            accel="cpu",
        ),
        "custom-abc12345",
    )
    assert preset.category == "custom" and preset.extension == ".mp4" and preset.muxer == "mp4"
    video, audio = preset.video, preset.audio
    assert video is not None and audio is not None
    assert (video.codec, video.quality, video.pix_fmt) == ("libx265", 22, "yuv420p10le")
    assert (video.max_height, video.fps, video.speed_family) == (1080, 30, "x26x")
    # Base arguments, the Apple tag for HEVC in MP4, then the vetted extras
    assert video.args == [
        "-x265-params",
        "log-level=error",
        "-tag:v",
        "hvc1",
        "-tune",
        "grain",
        "-x265-params",
        "aq-mode=3",
    ]
    assert (audio.codec, audio.bitrate_kbps, audio.channels) == ("aac", 256, 2)
    assert preset.output_args == ["-movflags", "+faststart", "-movflags", "+faststart+frag_keyframe"]
    assert preset.accel == "cpu" and preset.tags == ["HEVC 10-bit", "AAC", "MP4"]
    assert preset.soft_subtitles == "mov_text" and preset.keeps_hdr and not preset.remux


def test_audio_only_and_copy_formats() -> None:
    song = compile_draft(draft(container="opus", video_codec="none", audio_codec="opus"), "custom-1")
    assert song.video is None and song.extension == ".opus" and song.soft_subtitles is None
    remux = compile_draft(draft(container="mkv", video_codec="copy", audio_codec="copy"), "custom-2")
    assert remux.remux and remux.soft_subtitles == "copy" and remux.soft_bitmap_subtitles
    # Copying video while re-encoding audio is not a remux: volume and normalization still work
    keep_video = compile_draft(draft(container="mkv", video_codec="copy", audio_codec="opus"), "custom-3")
    assert not keep_video.remux and keep_video.keeps_hdr
    argv = build_command(
        ffmpeg="ffmpeg",
        media=SAMPLE_MEDIA.model_copy(update={"video": SAMPLE_MEDIA.video.model_copy(update={"hdr": True})}),  # type: ignore[union-attr]
        preset=keep_video,
        options=JobOptions(preset_id="custom-3", normalize_audio=True),
        output="/out/x.mkv",
        can_tonemap=True,
    )
    assert argv[argv.index("-c:v") + 1] == "copy" and "-vf" not in argv and "loudnorm" in " ".join(argv)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"container": "webm", "video_codec": "h264", "audio_codec": "opus"}, "video_container"),
        ({"container": "mp4", "audio_codec": "opus"}, "audio_container"),
        ({"container": "mp3", "video_codec": "h264", "audio_codec": "mp3"}, "video_container"),
        ({"video_codec": "h264", "ten_bit": True}, "ten_bit"),
        ({"video_codec": "copy", "max_height": 720}, "copy_filters"),
        ({"container": "mkv", "video_codec": "none", "audio_codec": "none"}, "empty"),
        ({"video_codec": "h264", "quality": 60}, "quality"),
        ({"max_height": 999}, "resolution"),
        ({"fps": 29}, "fps"),
        ({"audio_bitrate": 200}, "audio_bitrate"),
        ({"container": "mkv", "audio_codec": "flac", "audio_bitrate": 192}, "audio_bitrate"),
    ],
)
def test_impossible_combinations(overrides: dict[str, Any], code: str) -> None:
    assert code in codes(draft(**overrides))
    with pytest.raises(DraftError):
        compile_draft(draft(**overrides), "custom-x")


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ("-vf scale=1:1", "extra_flag"),
        ("-i /etc/passwd", "extra_flag"),
        ("-report 1", "extra_flag"),
        ("-f null", "extra_flag"),
        ("-x265-params 'a=1;b=2'", "extra_value"),
        ("-tag:v ../x", "extra_value"),
        ("-maxrate file:/tmp/x", "extra_value"),
        ("-preset", "extra_syntax"),
        ("-tune 'film", "extra_syntax"),
    ],
)
def test_extra_options_are_allowlisted(extra: str, code: str) -> None:
    assert code in codes(draft(extra_args=extra))


def test_extra_options_are_routed_by_kind() -> None:
    video, audio, output = parse_extra_args("-g 48 -ar 44100 -movflags +faststart -maxrate 5M -bufsize 10M")
    assert video == ["-g", "48", "-maxrate", "5M", "-bufsize", "10M"]
    assert audio == ["-ar", "44100"] and output == ["-movflags", "+faststart"]


def test_builtins_reopen_in_the_editor_with_the_same_command() -> None:
    editable = {p.id: d for p in CATALOG if (d := draft_from_preset(p))}
    assert {
        "mp4-h264",
        "mp4-hevc-10bit",
        "mkv-hevc",
        "webm-vp9",
        "social-youtube",
        "mp3",
        "flac",
        "remux-mkv",
    } <= set(editable)
    # Layouts, animations, size targets, intermediates and disc formats are outside the editor
    assert not {"social-vertical", "gif", "share-size", "prores-hq", "dvd-pal", "alac"} & set(editable)
    for preset_id, value in editable.items():
        builtin = CATALOG.get(preset_id)
        copy = compile_draft(value, "custom-copy")
        commands = [
            build_command(
                ffmpeg="ffmpeg",
                media=SAMPLE_MEDIA,
                preset=p,
                options=JobOptions(preset_id=p.id),
                output="/out/x" + p.extension,
            )
            for p in (builtin, copy)
        ]
        assert sorted(commands[0]) == sorted(commands[1]), preset_id


def test_display_command_hides_the_plumbing() -> None:
    argv = build_command(
        ffmpeg="/usr/bin/ffmpeg",
        media=SAMPLE_MEDIA,
        preset=CATALOG.get("mp3"),
        options=JobOptions(preset_id="mp3"),
        output="out.mp3",
    )
    shown = display_command(argv)
    assert shown[:3] == ["ffmpeg", "-i", "input.mkv"]
    assert not {"-progress", "-loglevel", "-nostdin", "-n", "-max_muxing_queue_size"} & set(shown)


def test_store_persists_and_skips_broken_entries(tmp_path: Path) -> None:
    path = tmp_path / "data" / "presets.json"
    store = CustomPresetStore(path)
    store.save("custom-aaaa1111", draft(name="Uno"))
    store.save("custom-bbbb2222", draft(name="Dos", container="mkv", video_codec="av1", audio_codec="opus"))
    reloaded = CustomPresetStore(path)
    assert [p.name["es"] for p in reloaded.presets()] == ["Uno", "Dos"]
    raw = json.loads(path.read_text())
    raw["formats"].append(
        {"id": "custom-broken", "draft": {"name": "x", "container": "webm", "video_codec": "h264"}}
    )
    raw["formats"].append({"nope": True})
    path.write_text(json.dumps(raw))
    assert len(CustomPresetStore(path).drafts()) == 2
    path.write_text("{not json")
    assert CustomPresetStore(path).drafts() == {}
    store.delete("custom-aaaa1111")
    assert list(CustomPresetStore(path).drafts()) == ["custom-bbbb2222"]


@pytest.fixture
def client(tmp_path: Path, media_dir: Path) -> Iterator[TestClient]:
    config = AppConfig(
        auth_token=TOKEN, media_roots=[media_dir, tmp_path], data_dir=tmp_path / "data", detect_gpu=False
    )
    with TestClient(create_app(config), base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


@requires_ffmpeg
def test_formats_api_lifecycle(client: TestClient, media_dir: Path, tmp_path: Path) -> None:
    body = {
        "name": "Jellyfin 480p",
        "container": "mkv",
        "video_codec": "vp9",
        "max_height": 480,
        "audio_codec": "opus",
    }
    preview = client.post("/api/presets/preview", json={"draft": body}, headers=AUTH).json()
    assert preview["ok"] and preview["extension"] == ".mkv" and preview["engine"] == "cpu"
    assert preview["command"].startswith("ffmpeg -i input.mkv") and "libvpx-vp9" in preview["command"]
    bad = client.post(
        "/api/presets/preview", json={"draft": {**body, "container": "mp4"}}, headers=AUTH
    ).json()
    assert not bad["ok"] and {e["code"] for e in bad["errors"]} == {"video_container", "audio_container"}
    unnamed = client.post("/api/presets/preview", json={"draft": {**body, "name": ""}}, headers=AUTH).json()
    assert unnamed["errors"][0]["code"] == "invalid" and unnamed["errors"][0]["params"]["field"] == "name"

    created = client.post("/api/presets", json=body, headers=AUTH)
    assert created.status_code == 201
    view = created.json()
    preset_id = view["id"]
    assert preset_id.startswith("custom-") and view["custom"] and view["draft"]["max_height"] == 480
    listed = client.get("/api/presets", headers=AUTH).json()
    assert listed[0]["id"] == preset_id and len(listed) == 35
    assert next(p for p in listed if p["id"] == "mp4-h264")["draft"]["video_codec"] == "h264"
    assert "libvpx-vp9" in client.get(f"/api/presets/{preset_id}/command", headers=AUTH).json()["command"]
    assert client.post("/api/presets", json={**body, "container": "mp4"}, headers=AUTH).status_code == 422
    assert client.put("/api/presets/mp4-h264", json=body, headers=AUTH).status_code == 404

    added = client.post(
        "/api/jobs",
        json={"paths": [str(media_dir / "clip.mp4")], "options": {"preset_id": preset_id}},
        headers=AUTH,
    )
    job = added.json()["jobs"][0]
    assert job["output_path"].endswith("clip.mkv")
    # Editing the format re-plans the files waiting for it
    changed = client.put(f"/api/presets/{preset_id}", json={**body, "container": "webm"}, headers=AUTH)
    assert changed.status_code == 200 and changed.json()["extension"] == ".webm"
    assert client.get(f"/api/jobs/{job['id']}", headers=AUTH).json()["output_path"].endswith("clip.webm")
    assert client.delete(f"/api/presets/{preset_id}", headers=AUTH).json()["code"] == "preset_in_use"

    assert client.put("/api/settings", json={"default_preset": preset_id}, headers=AUTH).status_code == 200
    client.post("/api/jobs/remove", json={"ids": [job["id"]]}, headers=AUTH)
    assert client.delete(f"/api/presets/{preset_id}", headers=AUTH).status_code == 204
    assert client.get("/api/settings", headers=AUTH).json()["default_preset"] == "mp4-h264"
    assert len(client.get("/api/presets", headers=AUTH).json()) == 34
    assert json.loads((tmp_path / "data" / "presets.json").read_text())["formats"] == []


@requires_ffmpeg
def test_a_custom_format_really_converts(client: TestClient, media_dir: Path, tmp_path: Path) -> None:
    body = {
        "name": "WebM ligero",
        "container": "webm",
        "video_codec": "vp9",
        "quality": 40,
        "fps": 24,
        "audio_codec": "opus",
        "audio_bitrate": 96,
        "audio_channels": "mono",
        "extra_args": "-deadline good -cpu-used 5 -g 48",
    }
    preset_id = client.post("/api/presets", json=body, headers=AUTH).json()["id"]
    options = {"preset_id": preset_id, "output_dir": str(tmp_path)}
    job = client.post(
        "/api/jobs", json={"paths": [str(media_dir / "clip.mp4")], "options": options}, headers=AUTH
    ).json()["jobs"][0]
    client.post("/api/queue/start", headers=AUTH)
    for _ in range(600):
        state = client.get(f"/api/jobs/{job['id']}", headers=AUTH).json()
        if state["status"] in ("completed", "failed"):
            break
        __import__("time").sleep(0.1)
    assert state["status"] == "completed", state["error"]
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,avg_frame_rate,channels",
            "-of",
            "json",
            state["output_path"],
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    video = next(s for s in streams if s["codec_name"] == "vp9")
    audio = next(s for s in streams if s["codec_name"] == "opus")
    assert video["avg_frame_rate"] == "24/1" and audio["channels"] == 1
