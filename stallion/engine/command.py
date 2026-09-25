"""Translate (media, preset, options) into a validated ffmpeg argument vector."""

from __future__ import annotations

import codecs
import os
import re
import sys
from pathlib import Path

from .options import JobOptions, SubtitleStyle
from .presets import Preset, VideoSpec
from .probe import ASS_SUBTITLE_CODECS, MediaInfo, SubtitleStream, VideoStream

SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")
MKV_COPYABLE_SUBTITLES = frozenset(
    {"subrip", "ass", "ssa", "webvtt", "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle"}
)
LOSSLESS_AUDIO = frozenset({"flac", "pcm_s16le", "pcm_s24le", "alac"})
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
SPEED_ARGS: dict[str, dict[str, list[str]]] = {
    "x26x": {
        "fast": ["-preset", "veryfast"],
        "balanced": ["-preset", "medium"],
        "quality": ["-preset", "slow"],
    },
    "svtav1": {"fast": ["-preset", "10"], "balanced": ["-preset", "8"], "quality": ["-preset", "5"]},
    "vpx": {
        "fast": ["-deadline", "good", "-cpu-used", "4"],
        "balanced": ["-deadline", "good", "-cpu-used", "2"],
        "quality": ["-deadline", "good", "-cpu-used", "1"],
    },
}
_EXTERNAL_SUBTITLE_CODECS = {".srt": "subrip", ".ass": "ass", ".ssa": "ass", ".vtt": "webvtt"}
_INVALID_NAME_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]' if sys.platform == "win32" else r"[\x00-\x1f/]")

# Two escaping levels: filter option value, then the filtergraph itself
_FILTER_OPTION_ESCAPES = str.maketrans({"\\": "\\\\", "'": "\\'", ":": "\\:"})
_FILTERGRAPH_ESCAPES = str.maketrans(
    {"\\": "\\\\", "'": "\\'", "[": "\\[", "]": "\\]", ",": "\\,", ";": "\\;"}
)


class OptionsError(ValueError):
    """Options that cannot be applied to this media/preset combination."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def escape_filter_value(value: str) -> str:
    """Escape ``value`` so it survives as a filter option inside a filtergraph."""

    return value.translate(_FILTER_OPTION_ESCAPES).translate(_FILTERGRAPH_ESCAPES)


def detect_text_encoding(path: str | Path) -> str:
    """Best-effort charset of a subtitle file (UTF-8/16, else Windows-1252)."""

    try:
        raw = Path(path).read_bytes()[:20_000_000]
    except OSError:
        return "UTF-8"
    if raw.startswith(codecs.BOM_UTF8):
        return "UTF-8"
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "UTF-16"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "CP1252"
    return "UTF-8"


def find_external_subtitles(media_path: str | Path, limit: int = 20) -> list[Path]:
    """Subtitle files next to the media sharing its name (``movie.srt``, ``movie.es.srt``)."""

    media_path = Path(media_path)
    stem = media_path.stem.casefold()
    found: list[Path] = []
    try:
        with os.scandir(media_path.parent) as entries:
            for entry in entries:
                name = Path(entry.name)
                if name.suffix.lower() not in SUBTITLE_EXTENSIONS or not entry.is_file():
                    continue
                candidate = name.stem.casefold()
                if candidate == stem or candidate.startswith(stem + "."):
                    found.append(Path(entry.path))
    except OSError:
        return []
    found.sort(key=lambda p: (p.stem.casefold() != stem, p.name.casefold()))
    return found[:limit]


def sanitize_name(name: str) -> str:
    cleaned = _INVALID_NAME_CHARS.sub("_", name).strip().rstrip(".")
    return cleaned[:180] or "output"


def plan_output_path(
    media_path: str | Path, preset: Preset, options: JobOptions, default_dir: Path | None
) -> Path:
    source = Path(media_path)
    directory = Path(options.output_dir) if options.output_dir else (default_dir or source.parent)
    stem = sanitize_name(options.output_name) if options.output_name else source.stem
    return directory / f"{stem}{preset.extension}"


def unique_path(
    path: Path, *, reserved: set[Path], overwrite: bool = False, avoid: set[Path] | None = None
) -> Path:
    """First free variant of ``path`` (``name (1).ext``...), never an input or reserved path."""

    avoid = avoid or set()
    candidate, counter = path, 1
    while (
        candidate in reserved
        or candidate in avoid
        or (not overwrite and (candidate.exists() or candidate.is_symlink()))
    ):
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    return candidate


def _even(value: float) -> int:
    return max(2, round(value / 2) * 2)


def square_pixel_size(video: VideoStream) -> tuple[int, int]:
    width, height = video.width, video.height
    if video.display_aspect and height:
        width = round(height * video.display_aspect)
    if video.rotation in (90, 270):
        width, height = height, width
    return width, height


def scale_limits(preset: Preset, options: JobOptions) -> tuple[int | None, tuple[int, int] | None]:
    """Return (short-side limit, device bounding box) for this preset/options pair."""

    spec = preset.video
    if spec is None or preset.fixed_resolution or preset.remux:
        return None, None
    box = (spec.max_width, spec.max_height) if spec.max_width and spec.max_height else None
    default_short = spec.max_height if box is None else None
    short = default_short if options.max_height is None else (options.max_height or None)
    return short, box


def compute_scale(
    video: VideoStream, short_side: int | None, box: tuple[int, int] | None
) -> tuple[int, int] | None:
    width, height = square_pixel_size(video)
    if width <= 0 or height <= 0:
        return None
    factor = 1.0
    if short_side and min(width, height) > short_side:
        factor = short_side / min(width, height)
    if box:
        factor = min(factor, box[0] / width, box[1] / height)
    if factor >= 1.0:
        return None
    return _even(width * factor), _even(height * factor)


def subtitles_filter(
    path: str,
    *,
    stream_position: int | None = None,
    style: SubtitleStyle | None = None,
    charenc: str | None = None,
) -> str:
    parts = [f"filename={escape_filter_value(path)}"]
    if stream_position is not None:
        parts.append(f"si={stream_position}")
    if charenc and charenc.upper() not in ("UTF-8", "UTF8"):
        parts.append(f"charenc={escape_filter_value(charenc)}")
    if style is not None:
        parts.append(f"force_style={escape_filter_value(style.to_ass())}")
    return "subtitles=" + ":".join(parts)


def resolve_quality(spec: VideoSpec, options: JobOptions) -> int | None:
    if spec.rate_control == "none" or spec.quality is None:
        return None
    value = options.quality if options.quality is not None else spec.quality
    if spec.quality_min is not None:
        value = max(value, spec.quality_min)
    if spec.quality_max is not None:
        value = min(value, spec.quality_max)
    return value


def _selected_subtitle(media: MediaInfo, options: JobOptions) -> SubtitleStream | None:
    if options.subtitle_mode == "none" or options.subtitle_track is None:
        return None
    return media.subtitles[options.subtitle_track]


def _soft_codec(preset: Preset, source_codec: str) -> str:
    if preset.soft_subtitles == "copy":
        return "copy" if source_codec in MKV_COPYABLE_SUBTITLES else "srt"
    return preset.soft_subtitles or "copy"


def validate_options(media: MediaInfo, preset: Preset, options: JobOptions) -> None:
    """Raise :class:`OptionsError` when options make no sense for this file/preset."""

    has_video = media.video is not None
    if preset.video is None and not media.audio:
        raise OptionsError("needs_audio", "This file has no audio track to convert")
    if preset.target and not has_video:
        raise OptionsError("needs_video", "Disc formats need a video track")
    if preset.remux:
        if options.max_height:
            raise OptionsError("remux_filters", "Changing the resolution needs re-encoding")
        if options.volume_db or options.normalize_audio:
            raise OptionsError("remux_filters", "Changing the volume needs re-encoding")
        if options.subtitle_mode == "burn":
            raise OptionsError("remux_filters", "Burning subtitles needs re-encoding")
    if options.audio_track is not None and options.audio_track >= len(media.audio):
        raise OptionsError("bad_audio_track", "The selected audio track does not exist")

    if options.subtitle_mode == "none":
        return
    if options.subtitle_track is not None:
        if options.subtitle_track >= len(media.subtitles):
            raise OptionsError("bad_subtitle_track", "The selected subtitle track does not exist")
        bitmap = media.subtitles[options.subtitle_track].bitmap
    elif options.subtitle_file:
        if Path(options.subtitle_file).suffix.lower() not in SUBTITLE_EXTENSIONS:
            raise OptionsError("bad_subtitle_file", "Subtitle files must be .srt, .ass, .ssa or .vtt")
        bitmap = False
    else:
        raise OptionsError("no_subtitle_source", "Choose a subtitle track or file")

    if options.subtitle_mode == "burn":
        if not preset.can_burn_subtitles or not has_video:
            raise OptionsError("cannot_burn", "Subtitles can only be burned into a video")
    elif preset.soft_subtitles is None:
        raise OptionsError("no_soft_subtitles", "This format cannot carry subtitle tracks; burn them instead")
    elif bitmap and not preset.soft_bitmap_subtitles:
        raise OptionsError("bitmap_soft", "Image subtitles (PGS/VobSub) can only be burned or kept in MKV")


def _video_codec_args(preset: Preset, options: JobOptions) -> list[str]:
    spec = preset.video
    if spec is None or preset.target:
        return []
    if spec.codec == "copy":
        return ["-c:v", "copy"]
    args = ["-c:v", spec.codec]
    quality = resolve_quality(spec, options)
    if quality is not None:
        if spec.rate_control == "crf":
            args += ["-crf", str(quality)]
            if spec.codec == "libvpx-vp9":
                args += ["-b:v", "0"]
        elif spec.rate_control == "bitrate":
            args += ["-b:v", f"{quality}k"]
        elif spec.rate_control == "qscale":
            args += ["-q:v", str(quality)]
    if spec.speed_family:
        args += SPEED_ARGS[spec.speed_family][options.speed]
    if spec.pix_fmt:
        args += ["-pix_fmt", spec.pix_fmt]
    return args + spec.args


def _audio_codec_args(preset: Preset, options: JobOptions, source_rate: int | None) -> list[str]:
    spec = preset.audio
    if spec is None or preset.target:
        return []
    if spec.codec == "copy":
        return ["-c:a", "copy"]
    args = ["-c:a", spec.codec]
    bitrate = options.audio_bitrate_kbps or spec.bitrate_kbps
    if bitrate and spec.codec not in LOSSLESS_AUDIO:
        args += ["-b:a", f"{bitrate}k"]
    if spec.channels:
        args += ["-ac", str(spec.channels)]
    rate = spec.sample_rate
    if rate is None and options.normalize_audio:
        # loudnorm resamples to 192 kHz internally; bring it back to a sane rate
        rate = min(source_rate or 48000, 48000)
    if rate:
        args += ["-ar", str(rate)]
    return args + spec.args


def _disc_video_filters(video: VideoStream, preset: Preset) -> list[str]:
    """Letterbox wide sources for 4:3-only discs (VCD)."""

    if preset.widescreen:
        return []
    width, height = square_pixel_size(video)
    if not width or not height or width / height <= 4 / 3 + 0.01:
        return []
    scaled_h = _even(704 * height / width)
    pad_y = _even((528 - scaled_h) / 2) if scaled_h < 528 else 0
    return [f"scale=704:{scaled_h},setsar=1", f"pad=704:528:0:{pad_y}:black"]


def _disc_aspect(video: VideoStream, preset: Preset) -> str:
    return "16:9" if preset.widescreen and video.aspect >= 1.5 else "4:3"


def build_command(
    *,
    ffmpeg: str,
    media: MediaInfo,
    preset: Preset,
    options: JobOptions,
    output: str | Path,
    overwrite: bool = False,
    subtitle_charenc: str | None = None,
) -> list[str]:
    """Build the full ffmpeg argv. Raises :class:`OptionsError` for invalid combinations."""

    validate_options(media, preset, options)

    source = media.path
    mode = options.subtitle_mode
    embedded_sub = _selected_subtitle(media, options)
    external_sub = options.subtitle_file if mode != "none" and embedded_sub is None else None

    argv = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    argv += ["-y" if overwrite else "-n", "-i", source]
    if external_sub and mode == "soft":
        if subtitle_charenc and subtitle_charenc.upper() not in ("UTF-8", "UTF8"):
            argv += ["-sub_charenc", subtitle_charenc]
        argv += ["-i", external_sub]

    maps: list[str] = []
    out: list[str] = []
    if preset.target:
        out += ["-target", preset.target]

    video = media.video if preset.video is not None else None
    if video is not None:
        vfilters: list[str] = []
        overlay_source: str | None = None
        if mode == "burn":
            if embedded_sub is not None and embedded_sub.bitmap:
                overlay_source = f"[0:{embedded_sub.index}]"
            elif embedded_sub is not None:
                style = None if embedded_sub.codec in ASS_SUBTITLE_CODECS else options.subtitle_style
                vfilters.append(subtitles_filter(source, stream_position=embedded_sub.position, style=style))
            elif external_sub:
                is_ass = Path(external_sub).suffix.lower() in (".ass", ".ssa")
                style = None if is_ass else options.subtitle_style
                vfilters.append(subtitles_filter(external_sub, style=style, charenc=subtitle_charenc))
        if preset.target:
            vfilters += _disc_video_filters(video, preset)
        else:
            size = compute_scale(video, *scale_limits(preset, options))
            if size:
                vfilters.append(f"scale={size[0]}:{size[1]},setsar=1")

        if overlay_source:
            graph = f"[0:{video.index}]{overlay_source}overlay=eof_action=pass"
            if vfilters:
                graph += "," + ",".join(vfilters)
            argv += ["-filter_complex", graph + "[vout]"]
            maps.append("[vout]")
        else:
            maps.append(f"0:{video.index}")
            if vfilters:
                out += ["-vf", ",".join(vfilters)]
        out += _video_codec_args(preset, options)
        if preset.target:
            out += ["-aspect", _disc_aspect(video, preset)]

    if preset.audio is not None and media.audio:
        if preset.remux and options.audio_track is None:
            tracks = list(media.audio)
        else:
            position = (
                options.audio_track if options.audio_track is not None else media.default_audio_position
            )
            tracks = [media.audio[position]]
        maps += [f"0:{track.index}" for track in tracks]
        afilters = []
        if options.normalize_audio:
            afilters.append(LOUDNORM)
        if options.volume_db:
            afilters.append(f"volume={options.volume_db:g}dB")
        if afilters:
            out += ["-af", ",".join(afilters)]
        out += _audio_codec_args(preset, options, tracks[0].sample_rate)

    if preset.remux and preset.soft_subtitles == "copy":
        # Remuxing to MKV keeps every subtitle track plus attachments such as fonts
        out_index = 0
        for track in media.subtitles:
            if track.codec in MKV_COPYABLE_SUBTITLES or not track.bitmap:
                maps.append(f"0:{track.index}")
                out += [f"-c:s:{out_index}", _soft_codec(preset, track.codec)]
                out_index += 1
        if external_sub and mode == "soft":
            maps.append("1:0")
            out += [f"-c:s:{out_index}", "copy"]
        maps.append("0:t?")
        out += ["-c:t", "copy"]
    elif mode == "soft":
        if embedded_sub is not None:
            maps.append(f"0:{embedded_sub.index}")
            out += ["-c:s", _soft_codec(preset, embedded_sub.codec)]
        elif external_sub:
            maps.append("1:0")
            source_codec = _EXTERNAL_SUBTITLE_CODECS.get(Path(external_sub).suffix.lower(), "subrip")
            out += ["-c:s", _soft_codec(preset, source_codec)]

    for stream_map in maps:
        argv += ["-map", stream_map]
    argv += out
    argv += ["-max_muxing_queue_size", "4096"]
    if preset.muxer:
        argv += ["-f", preset.muxer]
    argv += preset.output_args
    argv.append(str(output))
    return argv
