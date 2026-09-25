from __future__ import annotations

from pathlib import Path

import pytest

from stallion.engine.ffmpeg import FFmpegInfo, parse_encoders, parse_filters
from stallion.engine.probe import ProbeError, parse_probe, probe_media

from .conftest import requires_ffmpeg


def stream(**fields: object) -> dict[str, object]:
    return {"index": 0, "codec_name": "h264", "codec_type": "video", "width": 1920, "height": 1080, **fields}


def test_parse_probe_extracts_tracks() -> None:
    info = parse_probe(
        {
            "format": {
                "format_name": "matroska,webm",
                "duration": "12.5",
                "size": "2048",
                "bit_rate": "1000",
            },
            "streams": [
                stream(avg_frame_rate="30000/1001", display_aspect_ratio="16:9"),
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 6,
                    "tags": {"language": "spa"},
                },
                {
                    "index": 2,
                    "codec_type": "audio",
                    "codec_name": "ac3",
                    "disposition": {"default": 1},
                    "tags": {"language": "und", "title": "Commentary"},
                },
                {
                    "index": 3,
                    "codec_type": "subtitle",
                    "codec_name": "hdmv_pgs_subtitle",
                    "disposition": {"forced": 1},
                },
            ],
        },
        "/x.mkv",
    )
    assert info.duration_s == 12.5 and info.size_bytes == 2048
    assert info.video is not None and round(info.video.fps or 0, 3) == 29.97
    assert [a.language for a in info.audio] == ["spa", None]
    assert info.audio[1].title == "Commentary" and info.default_audio_position == 1
    assert info.subtitles[0].bitmap and info.subtitles[0].forced


def test_rotation_and_cover_art() -> None:
    rotated = parse_probe(
        {"format": {"format_name": "mov"}, "streams": [stream(side_data_list=[{"rotation": -90}])]}, "/r.mp4"
    )
    assert rotated.video is not None and rotated.video.rotation == 270
    assert (rotated.video.display_width, rotated.video.display_height) == (1080, 1920)

    song = parse_probe(
        {
            "format": {"format_name": "mp3", "duration": "3"},
            "streams": [
                {"index": 0, "codec_type": "audio", "codec_name": "mp3"},
                stream(index=1, codec_name="mjpeg", disposition={"attached_pic": 1}),
            ],
        },
        "/s.mp3",
    )
    assert song.video is None and song.cover_art_index == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "format": {"format_name": "srt"},
            "streams": [{"index": 0, "codec_type": "subtitle", "codec_name": "subrip"}],
        },
        {"format": {"format_name": "png_pipe"}, "streams": [stream(codec_name="png")]},
    ],
)
def test_non_media_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ProbeError):
        parse_probe(payload, "/nope")


def test_capability_parsers() -> None:
    encoders = parse_encoders(" V..... = Video\n ------\n V....D libx264   H.264\n A....D aac   AAC\n")
    filters = parse_filters(" ... loudnorm   A->A  EBU\n TSC overlay   VV->V  Overlay\n")
    assert encoders == {"libx264", "aac"} and filters == {"loudnorm", "overlay"}


@requires_ffmpeg
@pytest.mark.anyio
async def test_probe_real_file(media_dir: Path, ffmpeg_info: FFmpegInfo) -> None:
    info = await probe_media(media_dir / "movie.mkv", ffmpeg_info.ffprobe)
    assert info.video is not None and (info.video.width, info.video.height) == (640, 360)
    assert [a.language for a in info.audio] == ["eng", "spa"]
    assert info.default_audio_position == 1
    assert [(s.codec, s.language) for s in info.subtitles] == [("subrip", "eng"), ("ass", "spa")]


@requires_ffmpeg
@pytest.mark.anyio
async def test_probe_errors(tmp_path: Path, ffmpeg_info: FFmpegInfo) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video at all")
    with pytest.raises(ProbeError):
        await probe_media(junk, ffmpeg_info.ffprobe)
    with pytest.raises(ProbeError, match="Cannot run ffprobe"):
        await probe_media(junk, "/nonexistent/ffprobe")
