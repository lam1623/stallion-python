"""Translate (media, preset, options) into a validated ffmpeg argument vector."""

from __future__ import annotations

import codecs
import os
import re
import sys
from pathlib import Path

from .hwaccel import GpuPlan
from .options import JobOptions, SubtitleStyle
from .presets import Preset, VideoSpec
from .probe import ASS_SUBTITLE_CODECS, AudioStream, MediaInfo, SubtitleStream, VideoStream

SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")
MKV_COPYABLE_SUBTITLES = frozenset(
    {"subrip", "ass", "ssa", "webvtt", "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle"}
)
LOSSLESS_AUDIO = frozenset({"flac", "pcm_s16le", "pcm_s24le", "alac"})
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
# HDR (PQ/HLG) to SDR BT.709 with a filmic curve; needs the zscale filter (libzimg).
# A final format=<8-bit pix_fmt> is appended per preset.
TONEMAP_FILTERS = (
    "zscale=t=linear:npl=100",
    "format=gbrpf32le",
    "zscale=p=bt709",
    "tonemap=tonemap=hable:desat=0",
    "zscale=t=bt709:m=bt709:r=tv",
)
# Per-frame palettes keep GIF quality high without buffering the whole clip in memory
GIF_PALETTE = (
    "[{inp}]split[{out}a][{out}b];[{out}a]palettegen=stats_mode=single[{out}p];"
    "[{out}b][{out}p]paletteuse=new=1:dither=bayer:bayer_scale=4[{out}]"
)
# Headroom for rate-control drift when targeting a file size
SIZE_MARGIN = 0.96
# Container index cost per audio/video frame (MP4 sample tables, Matroska block headers)
FRAME_OVERHEAD_BITS = 112
AAC_FRAMES_PER_S = 47
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


def scale_limits(
    preset: Preset, options: JobOptions, auto_short_side: int | None = None
) -> tuple[int | None, tuple[int, int] | None]:
    """Return (short-side limit, device bounding box) for this preset/options pair."""

    spec = preset.video
    if spec is None or preset.fixed_resolution or preset.remux or spec.codec == "copy":
        return None, None
    box = (spec.max_width, spec.max_height) if spec.max_width and spec.max_height else None
    default_short = auto_short_side or (spec.max_height if box is None else None)
    short = default_short if options.max_height is None else (options.max_height or None)
    return short, box


def size_budget(
    duration_s: float, target_mb: int, audio_kbps: int | None, fps: float | None = None
) -> tuple[int, int | None]:
    """Video and audio kbps that make ``duration_s`` of media fit in ``target_mb`` (decimal MB)."""

    total = target_mb * 8000 * SIZE_MARGIN / duration_s
    # The container overhead grows with the frame count, which matters at low bitrates
    frames_per_s = (fps or 30) + (AAC_FRAMES_PER_S if audio_kbps else 0)
    total -= frames_per_s * FRAME_OVERHEAD_BITS / 1000
    audio = audio_kbps
    if audio and total < audio * 3:
        audio = max(32, int(total * 0.25))
    return max(40, int(total - (audio or 0))), audio


def size_rates(media: MediaInfo, preset: Preset, options: JobOptions) -> tuple[int | None, int | None]:
    """(video kbps, audio kbps) for presets that target a file size, else (None, None)."""

    spec = preset.video
    if spec is None or spec.rate_control != "size" or media.duration_s <= 0:
        return None, None
    target_mb = resolve_quality(spec, options) or 10
    audio_kbps = options.audio_bitrate_kbps or (preset.audio.bitrate_kbps if preset.audio else None)
    if not media.audio:
        audio_kbps = None
    if media.video is None:
        # Audio-only input: shrink the audio bitrate instead
        if audio_kbps is None:
            return None, None
        budget = int(target_mb * 8000 * SIZE_MARGIN / media.duration_s)
        return None, max(32, min(audio_kbps, budget))
    return size_budget(media.duration_s, target_mb, audio_kbps, media.video.fps)


def auto_short_side(video_kbps: int) -> int | None:
    """Resolution that still looks sharp at this bitrate (None keeps the source size)."""

    for limit, side in ((350, 360), (700, 480), (1500, 720), (4000, 1080)):
        if video_kbps < limit:
            return side
    return None


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
    needs_video = preset.target or preset.layout or preset.animation or preset.audio is None
    if needs_video and not has_video:
        raise OptionsError("needs_video", "This format needs a video track")
    if preset.video and preset.video.rate_control == "size" and has_video and media.duration_s <= 0:
        raise OptionsError("needs_duration", "The duration is unknown, so the file size cannot be targeted")
    spec = preset.video
    if spec is not None and spec.min_frame and media.video is not None:
        min_w, min_h = spec.min_frame
        size = compute_scale(media.video, *scale_limits(preset, options))
        width, height = size or square_pixel_size(media.video)
        if width < min_w or height < min_h:
            raise OptionsError("too_small", f"This format needs a picture of at least {min_w}×{min_h}")
    copies_video = preset.video is not None and preset.video.codec == "copy"
    if (preset.remux or copies_video) and options.max_height:
        raise OptionsError("remux_filters", "Changing the resolution needs re-encoding")
    if preset.remux:
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


def _video_codec_args(
    preset: Preset, options: JobOptions, size_kbps: int | None, gpu: GpuPlan | None = None
) -> list[str]:
    spec = preset.video
    if spec is None or preset.target:
        return []
    if spec.codec == "copy":
        return ["-c:v", "copy"]
    quality = resolve_quality(spec, options)
    if gpu is not None:
        return gpu.codec_args(spec, quality=quality, size_kbps=size_kbps, speed=options.speed)
    args = ["-c:v", spec.codec]
    if quality is not None:
        if spec.rate_control == "crf":
            args += ["-crf", str(quality)]
            if spec.codec == "libvpx-vp9":
                args += ["-b:v", "0"]
        elif spec.rate_control == "bitrate":
            args += ["-b:v", f"{quality}k"]
        elif spec.rate_control == "quality":
            args += ["-q:v", str(quality)]
        elif spec.rate_control == "size" and size_kbps:
            # Average bitrate with a VBV cap lands within a few percent of the target size
            args += [
                "-b:v",
                f"{size_kbps}k",
                "-maxrate",
                f"{size_kbps * 3 // 2}k",
                "-bufsize",
                f"{size_kbps * 2}k",
            ]
    if spec.speed_family:
        args += SPEED_ARGS[spec.speed_family][options.speed]
    if spec.pix_fmt:
        args += ["-pix_fmt", spec.pix_fmt]
    return args + spec.args


def _audio_codec_args(
    preset: Preset, options: JobOptions, source_rate: int | None, bitrate_override: int | None = None
) -> list[str]:
    spec = preset.audio
    if spec is None or preset.target:
        return []
    if spec.codec == "copy":
        return ["-c:a", "copy"]
    args = ["-c:a", spec.codec]
    bitrate = bitrate_override or options.audio_bitrate_kbps or spec.bitrate_kbps
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


def _blur_fill(width: int, height: int) -> str:
    """Fit the picture inside width x height over a blurred, zoomed copy of itself."""

    small_w, small_h = _even(width / 4), _even(height / 4)
    return (
        "[{inp}]split[{out}bg][{out}fg];"
        f"[{{out}}bg]scale={small_w}:{small_h}:force_original_aspect_ratio=increase,crop={small_w}:{small_h},"
        f"gblur=sigma=12,scale={width}:{height},setsar=1[{{out}}b];"
        f"[{{out}}fg]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        "setsar=1[{out}f];[{out}b][{out}f]overlay=(W-w)/2:(H-h)/2[{out}]"
    )


# A typical source for command previews of formats (no real file involved)
SAMPLE_MEDIA = MediaInfo(
    path="input.mkv",
    format_name="matroska,webm",
    duration_s=600.0,
    size_bytes=750_000_000,
    video=VideoStream(index=0, codec="h264", width=1920, height=1080, fps=30.0, pix_fmt="yuv420p"),
    audio=[AudioStream(index=1, position=0, codec="aac", channels=2, sample_rate=48000, default=True)],
    subtitles=[],
)
# Plumbing every job carries; left out when a command is shown as an example
_QUIET_FLAGS = {"-hide_banner", "-nostdin", "-nostats", "-n", "-y"}
_QUIET_OPTIONS = {"-loglevel", "-progress", "-max_muxing_queue_size"}


def display_command(argv: list[str]) -> list[str]:
    """``argv`` without the logging/progress plumbing, for showing a format's command."""

    shown: list[str] = ["ffmpeg"]
    skip = False
    for arg in argv[1:]:
        if skip:
            skip = False
        elif arg in _QUIET_OPTIONS:
            skip = True
        elif arg not in _QUIET_FLAGS:
            shown.append(arg)
    return shown


class _VideoGraph:
    """Video filters: a plain ``-vf`` chain when linear, ``-filter_complex`` once branching is needed."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._label = source
        self._pending: list[str] = []
        self._segments: list[str] = []
        self._count = 0

    def add(self, *filters: str) -> None:
        self._pending.extend(filters)

    def _next_label(self) -> str:
        self._count += 1
        return f"v{self._count}"

    def _flush(self) -> None:
        if self._pending:
            out = self._next_label()
            self._segments.append(f"[{self._label}]{','.join(self._pending)}[{out}]")
            self._label, self._pending = out, []

    def overlay(self, stream: str) -> None:
        self._flush()
        out = self._next_label()
        self._segments.append(f"[{self._label}][{stream}]overlay=eof_action=pass[{out}]")
        self._label = out

    def raw(self, template: str) -> None:
        """Append a sub-graph written with ``{inp}``/``{out}`` label placeholders."""

        self._flush()
        out = self._next_label()
        self._segments.append(template.format(inp=self._label, out=out))
        self._label = out

    def finish(self) -> tuple[list[str], list[str], str]:
        """Return (global args, output args, stream to map)."""

        if not self._segments:
            return [], (["-vf", ",".join(self._pending)] if self._pending else []), self._source
        self._flush()
        last = self._segments[-1]
        self._segments[-1] = last[: last.rindex("[")] + "[vout]"
        return ["-filter_complex", ";".join(self._segments)], [], "[vout]"


def build_command(
    *,
    ffmpeg: str,
    media: MediaInfo,
    preset: Preset,
    options: JobOptions,
    output: str | Path,
    overwrite: bool = False,
    subtitle_charenc: str | None = None,
    can_tonemap: bool = False,
    gpu: GpuPlan | None = None,
) -> list[str]:
    """Build the full ffmpeg argv. Raises :class:`OptionsError` for invalid combinations.

    ``can_tonemap`` tells whether this ffmpeg has ``zscale`` to turn HDR into SDR for 8-bit formats.
    ``gpu`` moves the video encode to a GPU encoder (see :meth:`HardwareEncoders.plan_for`).
    """

    validate_options(media, preset, options)
    if media.video is None or preset.video is None:
        gpu = None

    source = media.path
    mode = options.subtitle_mode
    embedded_sub = _selected_subtitle(media, options)
    external_sub = options.subtitle_file if mode != "none" and embedded_sub is None else None

    argv = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    argv += ["-y" if overwrite else "-n", *(gpu.input_args() if gpu else []), "-i", source]
    if external_sub and mode == "soft":
        if subtitle_charenc and subtitle_charenc.upper() not in ("UTF-8", "UTF8"):
            argv += ["-sub_charenc", subtitle_charenc]
        argv += ["-i", external_sub]

    maps: list[str] = []
    out: list[str] = []
    if preset.target:
        out += ["-target", preset.target]

    video = media.video if preset.video is not None else None
    size_video, size_audio = size_rates(media, preset, options)

    if video is not None and preset.video is not None:
        spec = preset.video
        graph = _VideoGraph(f"0:{video.index}")
        if video.hdr and not preset.keeps_hdr and can_tonemap:
            graph.add(*TONEMAP_FILTERS, f"format={spec.pix_fmt or 'yuv420p'}")
        if spec.fps and (video.fps is None or video.fps > spec.fps + 0.01):
            graph.add(f"fps={spec.fps}")
        if mode == "burn":
            if embedded_sub is not None and embedded_sub.bitmap:
                graph.overlay(f"0:{embedded_sub.index}")
            elif embedded_sub is not None:
                style = None if embedded_sub.codec in ASS_SUBTITLE_CODECS else options.subtitle_style
                graph.add(subtitles_filter(source, stream_position=embedded_sub.position, style=style))
            elif external_sub:
                is_ass = Path(external_sub).suffix.lower() in (".ass", ".ssa")
                style = None if is_ass else options.subtitle_style
                graph.add(subtitles_filter(external_sub, style=style, charenc=subtitle_charenc))
        if preset.target:
            graph.add(*_disc_video_filters(video, preset))
        elif preset.layout == "blur_fill" and preset.frame_size:
            graph.raw(_blur_fill(*preset.frame_size))
        else:
            auto = auto_short_side(size_video) if size_video else None
            size = compute_scale(video, *scale_limits(preset, options, auto))
            if size:
                graph.add(f"scale={size[0]}:{size[1]},setsar=1")
        if preset.animation == "gif":
            graph.raw(GIF_PALETTE)
        if gpu is not None:
            graph.add(*gpu.upload_filters(spec.high_bit_depth))

        global_args, filter_args, video_map = graph.finish()
        argv += global_args
        maps.append(video_map)
        out += filter_args
        out += _video_codec_args(preset, options, size_video, gpu)
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
        out += _audio_codec_args(preset, options, tracks[0].sample_rate, size_audio)

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
