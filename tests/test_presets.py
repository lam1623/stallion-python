"""Every built-in preset (and the subtitle paths) must produce a playable file with real ffmpeg."""

from __future__ import annotations

from pathlib import Path

import pytest

from stallion.engine.command import build_command, detect_text_encoding
from stallion.engine.ffmpeg import FFmpegInfo
from stallion.engine.options import JobOptions, SubtitleStyle
from stallion.engine.presets import PresetCatalog
from stallion.engine.probe import MediaInfo, probe_media
from stallion.engine.runner import FFmpegRun

from .conftest import WEIRD_SUBTITLE, requires_ffmpeg

pytestmark = [pytest.mark.anyio, requires_ffmpeg, pytest.mark.ffmpeg]

CATALOG = PresetCatalog.builtin()

EXPECTED = {
    "mp4-h264": ("h264", "aac"),
    "mp4-h265": ("hevc", "aac"),
    "mp4-av1": ("av1", "aac"),
    "webm-vp9": ("vp9", "opus"),
    "mkv-h264": ("h264", "aac"),
    "mp4-mobile": ("h264", "aac"),
    "avi-xvid": ("mpeg4", "mp3"),
    "wmv": ("wmv2", "wmav2"),
    "flv": ("h264", "aac"),
    "mp3": (None, "mp3"),
    "m4a": (None, "aac"),
    "opus": (None, "opus"),
    "flac": (None, "flac"),
    "wav": (None, "pcm_s16le"),
    "dvd-pal": ("mpeg2video", "ac3"),
    "dvd-ntsc": ("mpeg2video", "ac3"),
    "svcd-pal": ("mpeg2video", "mp2"),
    "svcd-ntsc": ("mpeg2video", "mp2"),
    "vcd-pal": ("mpeg1video", "mp2"),
    "vcd-ntsc": ("mpeg1video", "mp2"),
    "remux-mkv": ("h264", "aac"),
    "remux-mp4": ("h264", "aac"),
}


async def convert(
    ffmpeg: FFmpegInfo, source: Path, out_dir: Path, options: JobOptions, name: str = "out"
) -> tuple[MediaInfo, list[str]]:
    media = await probe_media(source, ffmpeg.ffprobe)
    preset = CATALOG.get(options.preset_id)
    output = out_dir / f"{name}{preset.extension}"
    charenc = detect_text_encoding(options.subtitle_file) if options.subtitle_file else None
    argv = build_command(
        ffmpeg=ffmpeg.ffmpeg,
        media=media,
        preset=preset,
        options=options,
        output=output,
        subtitle_charenc=charenc,
    )
    result = await FFmpegRun(argv, media.duration_s).run()
    assert result.returncode == 0, f"{options.preset_id} failed: {result.log[-5:]}\n{argv}"
    assert output.stat().st_size > 0
    return await probe_media(output, ffmpeg.ffprobe), result.log


def test_expectations_cover_every_preset() -> None:
    assert set(EXPECTED) == {p.id for p in CATALOG}


@pytest.mark.parametrize("preset_id", sorted(EXPECTED))
async def test_preset_converts(
    preset_id: str, ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path
) -> None:
    missing = PresetCatalog.builtin(ffmpeg_info).missing_encoders(CATALOG.get(preset_id))
    if missing:
        pytest.skip(f"ffmpeg build lacks {missing}")
    out, _ = await convert(ffmpeg_info, media_dir / "clip.mp4", tmp_path, JobOptions(preset_id=preset_id))
    video_codec, audio_codec = EXPECTED[preset_id]
    assert (out.video.codec if out.video else None) == video_codec
    assert out.audio and out.audio[0].codec == audio_codec
    assert out.duration_s == pytest.approx(3.0, abs=0.6)


async def test_disc_aspect_and_letterbox(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    dvd, _ = await convert(
        ffmpeg_info, media_dir / "hd.mp4", tmp_path, JobOptions(preset_id="dvd-pal"), "dvd"
    )
    assert dvd.video and (dvd.video.width, dvd.video.height) == (720, 576)
    assert dvd.video.display_aspect == pytest.approx(16 / 9, abs=0.01)
    vcd, _ = await convert(
        ffmpeg_info, media_dir / "hd.mp4", tmp_path, JobOptions(preset_id="vcd-ntsc"), "vcd"
    )
    assert vcd.video and (vcd.video.width, vcd.video.height) == (352, 240)


async def test_scaling_and_audio_filters(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    options = JobOptions(max_height=240, volume_db=4, normalize_audio=True, speed="fast")
    out, _ = await convert(ffmpeg_info, media_dir / "clip.mp4", tmp_path, options)
    assert out.video and (out.video.width, out.video.height) == (426, 240)
    assert out.audio[0].sample_rate == 48000


@pytest.mark.parametrize("name", [WEIRD_SUBTITLE, "latin1.srt", "movie.srt"])
async def test_burn_external_subtitles(
    name: str, ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path
) -> None:
    options = JobOptions(
        subtitle_mode="burn",
        subtitle_file=str(media_dir / name),
        subtitle_style=SubtitleStyle(size=28, color="#FFD400", box=True),
    )
    out, log = await convert(ffmpeg_info, media_dir / "clip.mp4", tmp_path, options)
    assert out.video is not None
    assert not [line for line in log if "Invalid UTF-8" in line or "Unable to open" in line]


async def test_burn_embedded_ass(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    options = JobOptions(subtitle_mode="burn", subtitle_track=1)
    out, _ = await convert(ffmpeg_info, media_dir / "movie.mkv", tmp_path, options)
    assert out.video is not None and not out.subtitles


async def test_soft_subtitles(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    mp4, _ = await convert(
        ffmpeg_info,
        media_dir / "movie.mkv",
        tmp_path,
        JobOptions(subtitle_mode="soft", subtitle_track=0),
        "a",
    )
    assert [s.codec for s in mp4.subtitles] == ["mov_text"]
    mkv, _ = await convert(
        ffmpeg_info,
        media_dir / "clip.mp4",
        tmp_path,
        JobOptions(preset_id="mkv-h264", subtitle_mode="soft", subtitle_file=str(media_dir / "latin1.srt")),
        "b",
    )
    assert [s.codec for s in mkv.subtitles] == ["subrip"]
    webm, _ = await convert(
        ffmpeg_info,
        media_dir / "with_subs.mp4",
        tmp_path,
        JobOptions(preset_id="webm-vp9", subtitle_mode="soft", subtitle_track=0, speed="fast"),
        "c",
    )
    assert [s.codec for s in webm.subtitles] == ["webvtt"]


async def test_audio_track_choice_and_remux(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    one, _ = await convert(ffmpeg_info, media_dir / "movie.mkv", tmp_path, JobOptions(audio_track=0), "one")
    assert len(one.audio) == 1
    remux, _ = await convert(
        ffmpeg_info, media_dir / "with_subs.mp4", tmp_path, JobOptions(preset_id="remux-mkv"), "remux"
    )
    assert [s.codec for s in remux.subtitles] == ["subrip"]
    full, _ = await convert(
        ffmpeg_info, media_dir / "movie.mkv", tmp_path, JobOptions(preset_id="remux-mkv"), "all"
    )
    assert len(full.audio) == 2 and [s.codec for s in full.subtitles] == ["subrip", "ass"]


async def test_surround_to_opus(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    out, _ = await convert(ffmpeg_info, media_dir / "surround.ac3", tmp_path, JobOptions(preset_id="opus"))
    assert out.audio[0].codec == "opus" and out.audio[0].channels == 2
