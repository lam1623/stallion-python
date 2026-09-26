"""GPU video encoders: find the ones that really work here, and translate preset settings for them.

A GPU encoder only counts as available after a short test encode succeeds: FFmpeg builds list
``h264_nvenc`` & co. whether or not the machine has the hardware and drivers to run them.
Decoding and filters (scaling, subtitles, tone mapping) stay on the CPU, so every preset
feature keeps working; only the final encode moves to the GPU.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .ffmpeg import POPEN_KWARGS, FFmpegInfo
from .options import JobOptions, Speed
from .presets import Preset, VideoSpec

log = logging.getLogger(__name__)

Backend = Literal["nvenc", "qsv", "vaapi", "amf", "videotoolbox"]
Family = Literal["h264", "hevc", "av1"]

FAMILIES: tuple[Family, ...] = ("h264", "hevc", "av1")
# CPU encoders a GPU encoder can stand in for
CPU_FAMILIES: dict[str, Family] = {
    "libx264": "h264",
    "libx265": "hevc",
    "libsvtav1": "av1",
    "libaom-av1": "av1",
}
# Rate controls with a GPU equivalent (animations, intermediates and lossless formats stay on the CPU)
GPU_RATE_CONTROLS = frozenset({"crf", "size", "bitrate"})
LABELS: dict[Backend, str] = {
    "nvenc": "NVIDIA NVENC",
    "qsv": "Intel Quick Sync",
    "vaapi": "VA-API",
    "amf": "AMD AMF",
    "videotoolbox": "Apple VideoToolbox",
}
# CRF scales: x264/x265 and the GPU encoders use 0–51, SVT-AV1 uses 0–63
_CRF_MAX: dict[Family, int] = {"h264": 51, "hevc": 51, "av1": 63}
_SPEEDS: dict[Backend, dict[Speed, list[str]]] = {
    "nvenc": {
        "fast": ["-preset", "p3", "-tune", "hq"],
        "balanced": ["-preset", "p5", "-tune", "hq"],
        "quality": ["-preset", "p7", "-tune", "hq"],
    },
    "qsv": {
        "fast": ["-preset", "faster"],
        "balanced": ["-preset", "medium"],
        "quality": ["-preset", "slower"],
    },
    "amf": {
        "fast": ["-quality", "speed"],
        "balanced": ["-quality", "balanced"],
        "quality": ["-quality", "quality"],
    },
}
# Codec-specific preset arguments that are safe to pass on: container tags and H.264 profiles
_PORTABLE_ARGS = frozenset({"-tag:v", "-profile:v"})
_TEST_TIMEOUT = 20.0


@dataclass(frozen=True, slots=True)
class GpuEncoder:
    """One working GPU encoder, e.g. ``hevc_nvenc``."""

    backend: Backend
    family: Family
    name: str
    ten_bit: bool


@dataclass(frozen=True, slots=True)
class HardwareEncoders:
    """The GPU encoders this machine can use (empty when there is no usable GPU)."""

    backend: Backend | None = None
    # VA-API render node, e.g. /dev/dri/renderD128
    device: str | None = None
    encoders: Mapping[Family, GpuEncoder] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return bool(self.encoders)

    @property
    def label(self) -> str | None:
        return LABELS[self.backend] if self.backend else None

    def plan_for(self, preset: Preset) -> GpuPlan | None:
        """How ``preset`` would be encoded on the GPU, or None when it has to stay on the CPU."""

        spec = preset.video
        if spec is None or preset.remux or preset.target or spec.rate_control not in GPU_RATE_CONTROLS:
            return None
        family = CPU_FAMILIES.get(spec.codec)
        encoder = self.encoders.get(family) if family else None
        if encoder is None or (spec.high_bit_depth and not encoder.ten_bit):
            return None
        return GpuPlan(encoder, self.device)

    def summary(self, presets: list[Preset] | None = None) -> dict[str, Any]:
        return {
            "available": self.available,
            "backend": self.backend,
            "label": self.label,
            "codecs": [family for family in FAMILIES if family in self.encoders],
            "ten_bit": [family for family, enc in self.encoders.items() if enc.ten_bit],
            "presets": [p.id for p in presets or [] if self.plan_for(p) is not None],
        }


NO_HARDWARE = HardwareEncoders()


def wants_gpu(options: JobOptions, prefer_gpu: bool) -> bool:
    """``accel`` "auto" follows the global setting; "cpu"/"gpu" are explicit per-file choices."""

    return options.accel == "gpu" or (options.accel == "auto" and prefer_gpu)


def _scaled_quality(value: int, family: Family, top: int) -> int:
    """Map a CPU CRF value onto a GPU encoder's 0–``top`` quantizer scale."""

    return max(1, min(top, round(value * top / _CRF_MAX[family])))


@dataclass(frozen=True, slots=True)
class GpuPlan:
    encoder: GpuEncoder
    device: str | None = None

    @property
    def backend(self) -> Backend:
        return self.encoder.backend

    def input_args(self) -> list[str]:
        """Global options placed before the input."""

        if self.backend == "vaapi" and self.device:
            return ["-vaapi_device", self.device]
        return []

    def upload_filters(self, ten_bit: bool) -> list[str]:
        """Filters that end the (CPU) video chain and hand the frames to the GPU."""

        if self.backend == "vaapi":
            return ["format=p010" if ten_bit else "format=nv12", "hwupload"]
        return []

    def codec_args(
        self,
        spec: VideoSpec,
        *,
        quality: int | None,
        size_kbps: int | None,
        speed: Speed,
    ) -> list[str]:
        encoder = self.encoder
        ten_bit = spec.high_bit_depth
        args = ["-c:v", encoder.name, *_SPEEDS.get(self.backend, {}).get(speed, [])]
        if spec.rate_control == "crf" and quality is not None:
            args += self._constant_quality(quality)
        elif spec.rate_control in ("size", "bitrate"):
            kbps = size_kbps if spec.rate_control == "size" else quality
            if kbps:
                args += self._bitrate(kbps, capped=spec.rate_control == "size")
        if self.backend != "vaapi":
            args += ["-pix_fmt", "p010le" if ten_bit else "nv12"]
        extra = _portable_args(spec.args, keep_profile=encoder.family == "h264")
        if ten_bit and encoder.family == "hevc":
            extra += ["-profile:v", "main10"]
        return args + extra

    def _constant_quality(self, crf: int) -> list[str]:
        family = self.encoder.family
        if self.backend == "nvenc":
            cq = str(_scaled_quality(crf, family, 51))
            return ["-rc", "vbr", "-cq", cq, "-b:v", "0", "-spatial-aq", "1"]
        if self.backend == "qsv":
            return ["-global_quality", str(_scaled_quality(crf, family, 51))]
        if self.backend == "vaapi":
            if family == "av1":
                return ["-rc_mode", "CQP", "-global_quality", str(_scaled_quality(crf, family, 255))]
            return ["-rc_mode", "CQP", "-qp", str(_scaled_quality(crf, family, 51))]
        if self.backend == "amf":
            qp = _scaled_quality(crf, family, 255 if family == "av1" else 51)
            args = ["-rc", "cqp", "-qp_i", str(qp), "-qp_p", str(qp)]
            # Only the H.264 encoder has B-frames (and a quantizer for them)
            return args + (["-qp_b", str(min(51, qp + 2))] if family == "h264" else [])
        # VideoToolbox: 1–100, higher is better (constant quality needs Apple silicon)
        share = _scaled_quality(crf, family, 51) / 51
        return ["-q:v", str(max(1, min(100, round(100 - share * 90))))]

    def _bitrate(self, kbps: int, *, capped: bool) -> list[str]:
        rate = ["-b:v", f"{kbps}k"]
        if capped and self.backend != "videotoolbox":
            rate += ["-maxrate", f"{kbps * 3 // 2}k", "-bufsize", f"{kbps * 2}k"]
        if self.backend == "nvenc":
            return ["-rc", "vbr", *rate]
        if self.backend == "vaapi":
            return ["-rc_mode", "VBR", *rate]
        if self.backend == "amf":
            return ["-rc", "vbr_peak" if capped else "vbr_latency", *rate]
        return rate


def _portable_args(args: list[str], *, keep_profile: bool) -> list[str]:
    """Keep the preset arguments every GPU encoder understands (x264/x265 tuning is dropped)."""

    kept: list[str] = []
    for key, value in zip(args[::2], args[1::2], strict=False):
        if key in _PORTABLE_ARGS and (key != "-profile:v" or keep_profile):
            kept += [key, value]
    return kept


# ---------------------------------------------------------------------------- discovery


def platform_backends(platform: str = sys.platform) -> list[Backend]:
    if platform == "darwin":
        return ["videotoolbox"]
    if platform == "win32":
        return ["nvenc", "amf", "qsv"]
    return ["nvenc", "vaapi", "qsv"]


def render_node(dri: Path = Path("/dev/dri")) -> str | None:
    """First DRM render node (VA-API needs one)."""

    try:
        nodes = sorted(p for p in dri.iterdir() if p.name.startswith("renderD"))
    except OSError:
        return None
    return str(nodes[0]) if nodes else None


# A tiny synthetic clip: big enough for every encoder's minimum frame size
_TEST_SOURCE = ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=0.4"]
_TEST_SPECS: dict[Family, VideoSpec] = {
    "h264": VideoSpec(codec="libx264", quality=23, pix_fmt="yuv420p", args=["-profile:v", "high"]),
    "hevc": VideoSpec(codec="libx265", quality=26, pix_fmt="yuv420p"),
    "av1": VideoSpec(codec="libsvtav1", quality=32, pix_fmt="yuv420p"),
}


def probe_command(ffmpeg: str, plan: GpuPlan, ten_bit: bool) -> list[str]:
    """A test encode using the same arguments a real conversion would."""

    spec = _TEST_SPECS[plan.encoder.family]
    if ten_bit:
        spec = spec.model_copy(update={"pix_fmt": "yuv420p10le"})
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", *plan.input_args(), *_TEST_SOURCE]
    filters = plan.upload_filters(ten_bit)
    if filters:
        argv += ["-vf", ",".join(filters)]
    argv += plan.codec_args(spec, quality=spec.quality, size_kbps=None, speed="balanced")
    return [*argv, "-frames:v", "10", "-f", "null", "-"]


def _runs(argv: list[str]) -> bool:
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_TEST_TIMEOUT,
            check=False,
            **POPEN_KWARGS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("GPU test encode could not run: %s", exc)
        return False
    if proc.returncode:
        log.debug("GPU test encode failed: %s: %s", argv[-8:], proc.stderr.strip()[-300:])
    return proc.returncode == 0


def detect_hardware(
    ffmpeg: FFmpegInfo,
    *,
    platform: str = sys.platform,
    dri: Path = Path("/dev/dri"),
    runner: Callable[[list[str]], bool] = _runs,
) -> HardwareEncoders:
    """Try each GPU encoder family with a real encode; the first backend that works wins."""

    for backend in platform_backends(platform):
        device = render_node(dri) if backend == "vaapi" else None
        if backend == "vaapi" and device is None:
            continue
        found: dict[Family, GpuEncoder] = {}
        for family in FAMILIES:
            name = f"{family}_{backend}"
            if backend == "videotoolbox" and family == "av1":
                continue  # Apple GPUs decode AV1 but cannot encode it
            if not ffmpeg.has_encoder(name):
                continue
            candidate = GpuEncoder(backend, family, name, ten_bit=False)
            if not runner(probe_command(ffmpeg.ffmpeg, GpuPlan(candidate, device), ten_bit=False)):
                continue
            ten_bit = family != "h264" and runner(
                probe_command(ffmpeg.ffmpeg, GpuPlan(candidate, device), ten_bit=True)
            )
            found[family] = GpuEncoder(backend, family, name, ten_bit)
        if found:
            hardware = HardwareEncoders(backend, device, found)
            log.info(
                "GPU encoding: %s (%s)",
                hardware.label,
                ", ".join(f"{e.name}{' 10-bit' if e.ten_bit else ''}" for e in found.values()),
            )
            return hardware
    log.info("GPU encoding: no usable GPU encoder, conversions run on the CPU")
    return NO_HARDWARE
