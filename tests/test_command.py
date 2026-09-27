from __future__ import annotations

from pathlib import Path

import pytest

from stallion.engine.command import (
    TONEMAP_FILTERS,
    OptionsError,
    build_command,
    compute_scale,
    detect_text_encoding,
    escape_filter_value,
    find_external_subtitles,
    plan_output_path,
    sanitize_name,
    unique_path,
)
from stallion.engine.options import JobOptions, SubtitleStyle
from stallion.engine.presets import PresetCatalog
from stallion.engine.probe import AudioStream, MediaInfo, SubtitleStream, VideoStream

CATALOG = PresetCatalog.builtin()


def media(**overrides: object) -> MediaInfo:
    base: dict[str, object] = {
        "path": "/media/in.mkv",
        "format_name": "matroska,webm",
        "duration_s": 60.0,
        "size_bytes": 1000,
        "video": VideoStream(index=0, codec="h264", width=1920, height=1080, display_aspect=16 / 9),
        "audio": [
            AudioStream(index=1, position=0, codec="aac", language="eng", sample_rate=44100),
            AudioStream(index=2, position=1, codec="ac3", language="spa", default=True, sample_rate=48000),
        ],
        "subtitles": [
            SubtitleStream(index=3, position=0, codec="subrip", language="eng"),
            SubtitleStream(index=4, position=1, codec="hdmv_pgs_subtitle", bitmap=True),
            SubtitleStream(index=5, position=2, codec="ass"),
            SubtitleStream(index=6, position=3, codec="mov_text"),
        ],
    }
    base.update(overrides)
    return MediaInfo.model_validate(base)


def argv(
    preset_id: str = "mp4-h264", info: MediaInfo | None = None, *, can_tonemap: bool = False, **opts: object
) -> list[str]:
    return build_command(
        ffmpeg="ffmpeg",
        media=info or media(),
        preset=CATALOG.get(preset_id),
        options=JobOptions(preset_id=preset_id, **opts),  # type: ignore[arg-type]
        output="/out/x" + CATALOG.get(preset_id).extension,
        can_tonemap=can_tonemap,
    )


def video(**overrides: object) -> VideoStream:
    base: dict[str, object] = {
        "index": 0,
        "codec": "h264",
        "width": 1920,
        "height": 1080,
        "display_aspect": 16 / 9,
        "fps": 30,
    }
    base.update(overrides)
    return VideoStream.model_validate(base)


def value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def maps(args: list[str]) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args) if a == "-map"]


# --------------------------------------------------------------------------- escaping


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("/plain/path.srt", "/plain/path.srt"),
        ("C:\\subs\\a.srt", "C\\\\:\\\\\\\\subs\\\\\\\\a.srt"),
        ("it's: here, [x]; y", "it\\\\\\'s\\\\: here\\, \\[x\\]\\; y"),
    ],
)
def test_escape_filter_value(raw: str, escaped: str) -> None:
    assert escape_filter_value(raw) == escaped


# --------------------------------------------------------------------------- defaults


def test_h264_defaults_are_safe() -> None:
    args = argv()
    assert args[:10] == [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-nostats",
        "-progress",
        "pipe:1",
        "-n",
        "-i",
    ]
    assert value_after(args, "-c:v") == "libx264"
    assert value_after(args, "-crf") == "23"
    assert value_after(args, "-preset") == "medium"
    assert value_after(args, "-pix_fmt") == "yuv420p"
    assert value_after(args, "-f") == "mp4"
    assert "+faststart" in args
    # The default-flagged audio track wins, subtitles are not copied implicitly
    assert maps(args) == ["0:0", "0:2"]
    assert "-sn" not in args and args[-1] == "/out/x.mp4"


def test_quality_is_clamped_to_the_preset_range() -> None:
    assert value_after(argv(quality=2), "-crf") == "16"
    assert value_after(argv(quality=99), "-crf") == "34"
    assert value_after(argv("avi-xvid", quality=1800), "-b:v") == "1800k"


def test_speed_maps_per_encoder_family() -> None:
    assert value_after(argv(speed="fast"), "-preset") == "veryfast"
    assert value_after(argv("mp4-av1", speed="quality"), "-preset") == "5"
    vp9 = argv("webm-vp9", speed="fast")
    assert value_after(vp9, "-cpu-used") == "4" and value_after(vp9, "-b:v") == "0"


# --------------------------------------------------------------------------- scaling


def test_scaling_limits_short_side_without_upscaling() -> None:
    assert value_after(argv(max_height=720), "-vf") == "scale=1280:720,setsar=1"
    assert "-vf" not in argv(max_height=2160)


def test_portrait_video_limits_its_width() -> None:
    portrait = VideoStream(index=0, codec="h264", width=1920, height=1080, rotation=90)
    assert compute_scale(portrait, 720, None) == (720, 1280)


def test_anamorphic_source_is_resampled_to_square_pixels() -> None:
    dvd = VideoStream(index=0, codec="mpeg2video", width=720, height=576, display_aspect=16 / 9)
    assert compute_scale(dvd, 480, None) == (854, 480)
    assert compute_scale(dvd, None, None) is None


def test_device_box_and_preset_default() -> None:
    assert value_after(argv("avi-xvid"), "-vf") == "scale=720:404,setsar=1"
    assert value_after(argv("mp4-mobile"), "-vf") == "scale=1280:720,setsar=1"
    assert "-vf" not in argv("mp4-mobile", max_height=0)


# --------------------------------------------------------------------------- audio


def test_audio_track_selection_and_filters() -> None:
    args = argv(audio_track=0, volume_db=-3.5, normalize_audio=True)
    assert maps(args) == ["0:0", "0:1"]
    assert value_after(args, "-af") == "loudnorm=I=-16:TP=-1.5:LRA=11,volume=-3.5dB"
    # loudnorm upsamples internally, so the source rate is restored
    assert value_after(args, "-ar") == "44100"


def test_audio_only_preset_maps_only_audio() -> None:
    args = argv("mp3", audio_bitrate_kbps=320)
    assert maps(args) == ["0:2"]
    assert value_after(args, "-b:a") == "320k"
    assert "-c:v" not in args


def test_lossless_audio_ignores_bitrate() -> None:
    assert "-b:a" not in argv("flac", audio_bitrate_kbps=320)


# --------------------------------------------------------------------------- subtitles


def test_burn_external_srt_with_style_and_charset() -> None:
    style = SubtitleStyle(font="DejaVu Sans", size=30, color="#FFCC00", box=True)
    args = build_command(
        ffmpeg="ffmpeg",
        media=media(),
        preset=CATALOG.get("mp4-h264"),
        options=JobOptions(subtitle_mode="burn", subtitle_file="/subs/it's.srt", subtitle_style=style),
        output="/out/x.mp4",
        subtitle_charenc="CP1252",
    )
    vf = value_after(args, "-vf")
    assert vf.startswith("subtitles=filename=/subs/it\\\\\\'s.srt:charenc=CP1252:force_style=")
    assert "PrimaryColour=&H0000CCFF" in vf and "BorderStyle=3" in vf and "FontName=DejaVu Sans" in vf
    assert "\\," in vf  # style commas are escaped for the filtergraph


def test_burn_embedded_ass_keeps_original_styling() -> None:
    vf = value_after(argv(subtitle_mode="burn", subtitle_track=2), "-vf")
    assert vf == "subtitles=filename=/media/in.mkv:si=2"


def test_burn_bitmap_subtitles_uses_overlay() -> None:
    args = argv(subtitle_mode="burn", subtitle_track=1, max_height=720)
    graph = value_after(args, "-filter_complex")
    assert graph == "[0:0][0:4]overlay=eof_action=pass[v1];[v1]scale=1280:720,setsar=1[vout]"
    assert maps(args)[0] == "[vout]" and "-vf" not in args


def test_soft_subtitles_per_container() -> None:
    assert value_after(argv(subtitle_mode="soft", subtitle_track=0), "-c:s") == "mov_text"
    assert value_after(argv("webm-vp9", subtitle_mode="soft", subtitle_track=0), "-c:s") == "webvtt"
    assert value_after(argv("mkv-h264", subtitle_mode="soft", subtitle_track=1), "-c:s") == "copy"
    # mov_text cannot live in Matroska: it is converted to SRT
    assert value_after(argv("mkv-h264", subtitle_mode="soft", subtitle_track=3), "-c:s") == "srt"


def test_soft_external_subtitle_is_a_second_input() -> None:
    args = build_command(
        ffmpeg="ffmpeg",
        media=media(),
        preset=CATALOG.get("mkv-h264"),
        options=JobOptions(preset_id="mkv-h264", subtitle_mode="soft", subtitle_file="/subs/a.srt"),
        output="/out/x.mkv",
        subtitle_charenc="CP1252",
    )
    assert args[args.index("/subs/a.srt") - 3 : args.index("/subs/a.srt")] == ["-sub_charenc", "CP1252", "-i"]
    assert "1:0" in maps(args)


@pytest.mark.parametrize(
    ("preset_id", "options", "code"),
    [
        ("remux-mkv", {"max_height": 720}, "remux_filters"),
        ("remux-mp4", {"volume_db": 3}, "remux_filters"),
        ("mp4-h264", {"subtitle_mode": "soft", "subtitle_track": 1}, "bitmap_soft"),
        ("avi-xvid", {"subtitle_mode": "soft", "subtitle_track": 0}, "no_soft_subtitles"),
        ("mp4-h264", {"subtitle_mode": "burn"}, "no_subtitle_source"),
        ("mp4-h264", {"subtitle_mode": "burn", "subtitle_track": 9}, "bad_subtitle_track"),
        ("mp4-h264", {"audio_track": 5}, "bad_audio_track"),
        ("mp4-h264", {"subtitle_mode": "burn", "subtitle_file": "/x/readme.txt"}, "bad_subtitle_file"),
        ("mp3", {"subtitle_mode": "burn", "subtitle_track": 0}, "cannot_burn"),
        ("gif", {"subtitle_mode": "soft", "subtitle_track": 0}, "no_soft_subtitles"),
        ("dnxhr-hq", {"max_height": 100}, "too_small"),
    ],
)
def test_invalid_combinations_are_rejected(preset_id: str, options: dict[str, object], code: str) -> None:
    with pytest.raises(OptionsError) as err:
        argv(preset_id, **options)
    assert err.value.code == code


def test_media_without_needed_streams() -> None:
    silent = media(audio=[])
    with pytest.raises(OptionsError, match="no audio"):
        argv("mp3", silent)
    with pytest.raises(OptionsError, match="video"):
        argv("dvd-pal", media(video=None))
    for preset_id in ("gif", "webp-anim", "social-vertical"):
        with pytest.raises(OptionsError) as err:
            argv(preset_id, media(video=None))
        assert err.value.code == "needs_video"


# --------------------------------------------------------------------------- disc & remux


def test_dvd_uses_target_and_keeps_widescreen() -> None:
    args = argv("dvd-pal")
    assert value_after(args, "-target") == "pal-dvd"
    assert value_after(args, "-aspect") == "16:9"
    assert "-c:v" not in args and "-vf" not in args


def test_vcd_letterboxes_wide_sources() -> None:
    args = argv("vcd-ntsc")
    assert value_after(args, "-vf") == "scale=704:396,setsar=1,pad=704:528:0:66:black"
    assert value_after(args, "-aspect") == "4:3"


def test_remux_mkv_keeps_every_track() -> None:
    args = argv("remux-mkv")
    assert maps(args) == ["0:0", "0:1", "0:2", "0:3", "0:4", "0:5", "0:6", "0:t?"]
    assert value_after(args, "-c:v") == "copy" and value_after(args, "-c:a") == "copy"
    assert value_after(args, "-c:s:3") == "srt"


# --------------------------------------------------------------------------- modern formats


def test_size_target_picks_bitrate_and_resolution() -> None:
    # 10 MB for 60 s: 1280 kbps minus container overhead, 96 for audio, the rest for 720p video
    args = argv("share-size")
    assert value_after(args, "-b:v") == "1175k"
    assert value_after(args, "-maxrate") == "1762k" and value_after(args, "-bufsize") == "2350k"
    assert value_after(args, "-b:a") == "96k"
    assert value_after(args, "-vf") == "scale=1280:720,setsar=1"
    assert "-crf" not in args
    # A generous budget keeps the source resolution, an explicit choice always wins
    assert "-vf" not in argv("share-size", quality=100)
    assert value_after(argv("share-size", max_height=480), "-vf") == "scale=854:480,setsar=1"


def test_size_target_shrinks_audio_on_tight_budgets() -> None:
    args = argv("share-size", media(duration_s=600), quality=8)
    assert value_after(args, "-b:a") == "32k" and value_after(args, "-b:v") == "61k"
    assert value_after(args, "-vf") == "scale=640:360,setsar=1"
    podcast = argv("share-size", media(video=None, duration_s=3600))
    assert maps(podcast) == ["0:2"] and value_after(podcast, "-b:a") == "32k" and "-c:v" not in podcast


def test_size_target_needs_a_duration() -> None:
    with pytest.raises(OptionsError) as err:
        argv("share-size", media(duration_s=0))
    assert err.value.code == "needs_duration"


def test_vertical_layout_blurs_the_background() -> None:
    args = argv("social-vertical", media(video=video()))
    assert value_after(args, "-filter_complex") == (
        "[0:0]split[v1bg][v1fg];"
        "[v1bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
        "gblur=sigma=12,scale=1080:1920,setsar=1[v1b];"
        "[v1fg]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[v1f];"
        "[v1b][v1f]overlay=(W-w)/2:(H-h)/2[vout]"
    )
    assert maps(args) == ["[vout]", "0:2"] and "-vf" not in args
    assert value_after(args, "-ar") == "48000"


def test_frame_rate_is_capped_not_raised() -> None:
    fast = argv("social-vertical", media(video=video(fps=120)))
    assert value_after(fast, "-filter_complex").startswith("[0:0]fps=60[v1];[v1]split")
    assert "fps=" not in value_after(
        argv("social-vertical", media(video=video(fps=59.94))), "-filter_complex"
    )


def test_gif_uses_per_frame_palettes_and_no_audio() -> None:
    args = argv("gif", media(video=video()))
    assert value_after(args, "-filter_complex") == (
        "[0:0]fps=12,scale=640:360,setsar=1[v1];"
        "[v1]split[v2a][v2b];[v2a]palettegen=stats_mode=single[v2p];"
        "[v2b][v2p]paletteuse=new=1:dither=bayer:bayer_scale=4[vout]"
    )
    assert maps(args) == ["[vout]"] and "-c:a" not in args
    assert value_after(args, "-f") == "gif" and value_after(args, "-loop") == "0"


def test_animated_webp_quality_is_clamped() -> None:
    args = argv("webp-anim", media(video=video()), quality=90)
    assert value_after(args, "-c:v") == "libwebp_anim" and value_after(args, "-q:v") == "90"
    assert value_after(args, "-vf") == "fps=15,scale=854:480,setsar=1"
    assert maps(args) == ["0:0"] and value_after(args, "-loop") == "0"
    assert value_after(argv("webp-anim", quality=5), "-q:v") == "40"


def test_hdr_is_tone_mapped_only_for_8_bit_formats() -> None:
    hdr = media(video=video(hdr=True, pix_fmt="yuv420p10le"))
    tonemap = ",".join(TONEMAP_FILTERS)
    assert value_after(argv("mp4-h264", hdr, can_tonemap=True), "-vf") == f"{tonemap},format=yuv420p"
    assert value_after(argv("dnxhr-hq", hdr, can_tonemap=True), "-vf") == f"{tonemap},format=yuv422p"
    # 10-bit formats and remuxing keep HDR; without zscale the picture is left alone
    for preset_id in ("mp4-hevc-10bit", "mkv-hevc", "prores-hq", "remux-mkv"):
        assert "-vf" not in argv(preset_id, hdr, can_tonemap=True)
    assert "-vf" not in argv("mp4-h264", hdr)
    assert "-vf" not in argv("mp4-h264", can_tonemap=True)
    # Subtitles are drawn after tone mapping so their colors stay right
    burned = value_after(
        argv("mp4-h264", hdr, can_tonemap=True, subtitle_mode="burn", subtitle_track=0), "-vf"
    )
    assert burned.index("format=yuv420p") < burned.index("subtitles=")


def test_editing_and_lossless_formats() -> None:
    prores = argv("prores-hq")
    assert value_after(prores, "-c:v") == "prores_ks" and value_after(prores, "-profile:v") == "3"
    assert value_after(prores, "-pix_fmt") == "yuv422p10le" and value_after(prores, "-c:a") == "pcm_s24le"
    assert value_after(prores, "-f") == "mov" and "-crf" not in prores and "-b:a" not in prores
    dnxhr = argv("dnxhr-hq")
    assert value_after(dnxhr, "-profile:v") == "dnxhr_hq" and value_after(dnxhr, "-pix_fmt") == "yuv422p"
    with pytest.raises(OptionsError) as err:
        argv("dnxhr-hq", media(video=video(width=200, height=112)))
    assert err.value.code == "too_small"
    alac = argv("alac", audio_bitrate_kbps=320)
    assert value_after(alac, "-c:a") == "alac" and value_after(alac, "-f") == "ipod" and "-b:a" not in alac


def test_catalog_metadata() -> None:
    assert CATALOG.get("social-vertical").frame_size == (1080, 1920)
    assert CATALOG.get("mp4-hevc-10bit").keeps_hdr and CATALOG.get("remux-mp4").keeps_hdr
    assert not CATALOG.get("mp4-h264").keeps_hdr and not CATALOG.get("gif").keeps_hdr
    for preset in CATALOG:
        if preset.target:
            assert preset.frame_size, preset.id
        if preset.video and preset.video.quality is not None and preset.video.quality_min is not None:
            assert preset.video.quality_min <= preset.video.quality <= (preset.video.quality_max or 10**9)


# --------------------------------------------------------------------------- paths


def test_output_paths(tmp_path: Path) -> None:
    preset = CATALOG.get("mp4-h264")
    planned = plan_output_path(tmp_path / "in.mkv", preset, JobOptions(), None)
    assert planned == tmp_path / "in.mp4"
    assert (
        plan_output_path(tmp_path / "in.mkv", preset, JobOptions(output_name="a/b"), tmp_path / "o").name
        == "a_b.mp4"
    )

    (tmp_path / "in.mp4").touch()
    assert unique_path(planned, reserved=set()) == tmp_path / "in (1).mp4"
    assert unique_path(planned, reserved={tmp_path / "in (1).mp4"}) == tmp_path / "in (2).mp4"
    assert unique_path(planned, reserved=set(), overwrite=True) == planned
    assert unique_path(planned, reserved=set(), overwrite=True, avoid={planned}) == tmp_path / "in (1).mp4"
    assert sanitize_name("  \x00bad.. ") == "_bad"


def test_external_subtitles_and_charset(tmp_path: Path) -> None:
    movie = tmp_path / "Movie.mkv"
    movie.touch()
    (tmp_path / "Movie.srt").write_text("hola", encoding="utf-8")
    (tmp_path / "Movie.es.srt").write_bytes("¿Qué?".encode("cp1252"))
    (tmp_path / "Other.srt").touch()
    found = find_external_subtitles(movie)
    assert [p.name for p in found] == ["Movie.srt", "Movie.es.srt"]
    assert detect_text_encoding(found[0]) == "UTF-8"
    assert detect_text_encoding(found[1]) == "CP1252"
