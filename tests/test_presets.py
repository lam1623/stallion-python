"""Every built-in preset (and the subtitle paths) must produce a playable file with real ffmpeg."""

from __future__ import annotations

import subprocess
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

EXPECTED: dict[str, tuple[str | None, str | None]] = {
    "mp4-h264": ("h264", "aac"),
    "mp4-h265": ("hevc", "aac"),
    "mp4-hevc-10bit": ("hevc", "aac"),
    "mp4-av1": ("av1", "aac"),
    "webm-av1": ("av1", "opus"),
    "webm-vp9": ("vp9", "opus"),
    "mkv-hevc": ("hevc", "aac"),
    "mkv-h264": ("h264", "aac"),
    "social-youtube": ("h264", "aac"),
    "social-vertical": ("h264", "aac"),
    "mp4-mobile": ("h264", "aac"),
    "share-size": ("h264", "aac"),
    "gif": ("gif", None),
    "webp-anim": ("webp", None),
    "prores-hq": ("prores", "pcm_s24le"),
    "prores-proxy": ("prores", "pcm_s16le"),
    "dnxhr-hq": ("dnxhd", "pcm_s16le"),
    "avi-xvid": ("mpeg4", "mp3"),
    "wmv": ("wmv2", "wmav2"),
    "flv": ("h264", "aac"),
    "mp3": (None, "mp3"),
    "m4a": (None, "aac"),
    "opus": (None, "opus"),
    "flac": (None, "flac"),
    "alac": (None, "alac"),
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


async def encode(
    ffmpeg: FFmpegInfo, source: Path, out_dir: Path, options: JobOptions, name: str = "out"
) -> tuple[Path, list[str]]:
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
        can_tonemap=ffmpeg.has_filter("zscale"),
    )
    result = await FFmpegRun(argv, media.duration_s).run()
    assert result.returncode == 0, f"{options.preset_id} failed: {result.log[-5:]}\n{argv}"
    assert output.stat().st_size > 0
    return output, result.log


async def convert(
    ffmpeg: FFmpegInfo, source: Path, out_dir: Path, options: JobOptions, name: str = "out"
) -> tuple[MediaInfo, list[str]]:
    output, log = await encode(ffmpeg, source, out_dir, options, name)
    return await probe_media(output, ffmpeg.ffprobe), log


def color_tags(ffprobe: str, path: Path) -> str:
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer"]
    return subprocess.run(
        [*argv, "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_expectations_cover_every_preset() -> None:
    assert set(EXPECTED) == {p.id for p in CATALOG}


@pytest.mark.parametrize("preset_id", sorted(EXPECTED))
async def test_preset_converts(
    preset_id: str, ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path
) -> None:
    missing = PresetCatalog.builtin(ffmpeg_info).missing_encoders(CATALOG.get(preset_id))
    if missing:
        pytest.skip(f"ffmpeg build lacks {missing}")
    options = JobOptions(preset_id=preset_id, speed="fast")
    if preset_id == "webp-anim":
        # Older ffprobe builds cannot decode animated WebP: check the RIFF container instead
        output, _ = await encode(ffmpeg_info, media_dir / "clip.mp4", tmp_path, options)
        data = output.read_bytes()
        assert data[:4] == b"RIFF" and data[8:16] == b"WEBPVP8X" and b"ANIM" in data[:64]
        return
    out, _ = await convert(ffmpeg_info, media_dir / "clip.mp4", tmp_path, options)
    video_codec, audio_codec = EXPECTED[preset_id]
    assert (out.video.codec if out.video else None) == video_codec
    assert [track.codec for track in out.audio] == ([audio_codec] if audio_codec else [])
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


async def test_vertical_video_and_gif_sizes(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> None:
    vertical, _ = await convert(
        ffmpeg_info,
        media_dir / "hd.mp4",
        tmp_path,
        JobOptions(preset_id="social-vertical", speed="fast"),
        "v",
    )
    assert vertical.video and (vertical.video.width, vertical.video.height) == (1080, 1920)
    gif, _ = await convert(ffmpeg_info, media_dir / "hd.mp4", tmp_path, JobOptions(preset_id="gif"), "g")
    assert gif.video and (gif.video.width, gif.video.height) == (640, 360)
    assert gif.video.fps and gif.video.fps <= 12.5


async def test_target_size_is_respected(ffmpeg_info: FFmpegInfo, long_video: Path, tmp_path: Path) -> None:
    options = JobOptions(preset_id="share-size", quality=2, speed="fast")
    output, _ = await encode(ffmpeg_info, long_video, tmp_path, options)
    assert 1_000_000 < output.stat().st_size <= 2_000_000


async def test_hdr_is_kept_or_tone_mapped(ffmpeg_info: FFmpegInfo, hdr_clip: Path, tmp_path: Path) -> None:
    source = await probe_media(hdr_clip, ffmpeg_info.ffprobe)
    assert source.video and source.video.hdr
    if not ffmpeg_info.has_encoder("libx265"):
        pytest.skip("ffmpeg build lacks libx265")
    kept, _ = await convert(
        ffmpeg_info, hdr_clip, tmp_path, JobOptions(preset_id="mp4-hevc-10bit", speed="fast"), "kept"
    )
    assert kept.video and kept.video.hdr and kept.video.pix_fmt == "yuv420p10le"
    if not ffmpeg_info.has_filter("zscale"):
        pytest.skip("ffmpeg build lacks zscale")
    sdr, _ = await encode(ffmpeg_info, hdr_clip, tmp_path, JobOptions(speed="fast"), "sdr")
    assert color_tags(ffmpeg_info.ffprobe, sdr) == "bt709"
