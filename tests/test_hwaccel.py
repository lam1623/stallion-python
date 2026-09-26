from __future__ import annotations

from pathlib import Path

import pytest

from stallion.engine.command import build_command
from stallion.engine.ffmpeg import FFmpegInfo
from stallion.engine.hwaccel import (
    NO_HARDWARE,
    Backend,
    Family,
    GpuEncoder,
    GpuPlan,
    HardwareEncoders,
    detect_hardware,
    render_node,
    wants_gpu,
)
from stallion.engine.options import JobOptions
from stallion.engine.presets import PresetCatalog

from .conftest import requires_ffmpeg
from .test_command import media, value_after

CATALOG = PresetCatalog.builtin()


def hardware(
    backend: Backend = "nvenc", ten_bit: tuple[Family, ...] = ("hevc", "av1"), **extra: object
) -> HardwareEncoders:
    families: tuple[Family, ...] = extra.pop("families", ("h264", "hevc", "av1"))  # type: ignore[assignment]
    encoders = {f: GpuEncoder(backend, f, f"{f}_{backend}", f in ten_bit) for f in families}
    return HardwareEncoders(backend, extra.get("device"), encoders)  # type: ignore[arg-type]


def gpu_argv(preset_id: str, hw: HardwareEncoders, **opts: object) -> list[str]:
    preset = CATALOG.get(preset_id)
    plan = hw.plan_for(preset)
    assert plan is not None, f"{preset_id} should be GPU-capable"
    return build_command(
        ffmpeg="ffmpeg",
        media=media(),
        preset=preset,
        options=JobOptions(preset_id=preset_id, **opts),  # type: ignore[arg-type]
        output="/out/x" + preset.extension,
        gpu=plan,
    )


def test_formats_that_can_move_to_the_gpu() -> None:
    hw = hardware(ten_bit=("hevc",), families=("h264", "hevc"))
    names = {p.id: plan.encoder.name for p in CATALOG if (plan := hw.plan_for(p))}
    assert names["mp4-h264"] == "h264_nvenc" and names["social-vertical"] == "h264_nvenc"
    assert names["mp4-h265"] == names["mkv-hevc"] == names["mp4-hevc-10bit"] == "hevc_nvenc"
    # No AV1 encoder here; animations, intermediates, copies and discs always stay on the CPU
    for cpu_only in ("mp4-av1", "webm-vp9", "gif", "webp-anim", "prores-hq", "remux-mkv", "dvd-pal", "mp3"):
        assert cpu_only not in names
    # A 10-bit format needs a GPU that encodes 10-bit
    assert hardware(ten_bit=()).plan_for(CATALOG.get("mkv-hevc")) is None
    assert NO_HARDWARE.plan_for(CATALOG.get("mp4-h264")) is None
    summary = hw.summary(list(CATALOG))
    assert summary["label"] == "NVIDIA NVENC" and summary["codecs"] == ["h264", "hevc"]
    assert summary["ten_bit"] == ["hevc"] and "mp4-h264" in summary["presets"]


def test_accel_choice() -> None:
    assert wants_gpu(JobOptions(), prefer_gpu=True)
    assert not wants_gpu(JobOptions(), prefer_gpu=False)
    assert wants_gpu(JobOptions(accel="gpu"), prefer_gpu=False)
    assert not wants_gpu(JobOptions(accel="cpu"), prefer_gpu=True)


def test_nvenc_constant_quality() -> None:
    args = gpu_argv("social-youtube", hardware(), speed="quality")
    assert value_after(args, "-c:v") == "h264_nvenc"
    assert value_after(args, "-preset") == "p7" and value_after(args, "-tune") == "hq"
    assert value_after(args, "-rc") == "vbr" and value_after(args, "-cq") == "18"
    assert value_after(args, "-b:v") == "0" and value_after(args, "-pix_fmt") == "nv12"
    # H.264 profile survives, x264-only tuning (-bf) does not
    assert value_after(args, "-profile:v") == "high" and "-bf" not in args and "-crf" not in args


def test_hevc_10bit_keeps_container_tag_and_drops_x265_params() -> None:
    args = gpu_argv("mp4-hevc-10bit", hardware("qsv"))
    assert value_after(args, "-c:v") == "hevc_qsv" and value_after(args, "-preset") == "medium"
    assert value_after(args, "-global_quality") == "24"
    assert value_after(args, "-pix_fmt") == "p010le" and value_after(args, "-profile:v") == "main10"
    assert value_after(args, "-tag:v") == "hvc1" and "-x265-params" not in args


def test_vaapi_uploads_frames_after_the_cpu_filters() -> None:
    hw = hardware("vaapi", device="/dev/dri/renderD128")
    args = gpu_argv("mp4-h264", hw, max_height=720, subtitle_mode="burn", subtitle_track=0)
    assert args.index("-vaapi_device") < args.index("-i")
    chain = value_after(args, "-vf")
    assert chain.startswith("subtitles=") and chain.endswith("scale=1280:720,setsar=1,format=nv12,hwupload")
    assert value_after(args, "-rc_mode") == "CQP" and value_after(args, "-qp") == "23"
    assert "-pix_fmt" not in args
    # Branching graphs (bitmap subtitles) end with the upload too
    graph = value_after(gpu_argv("mkv-hevc", hw, subtitle_mode="burn", subtitle_track=1), "-filter_complex")
    assert graph.endswith("format=p010,hwupload[vout]")


def test_av1_quality_is_rescaled_per_encoder() -> None:
    # SVT-AV1 CRF runs 0-63; GPU encoders use 0-51 or 0-255
    assert value_after(gpu_argv("mp4-av1", hardware()), "-cq") == "26"
    assert (
        value_after(gpu_argv("mp4-av1", hardware("vaapi", device="/dev/dri/renderD128")), "-global_quality")
        == "130"
    )
    amf = gpu_argv("mp4-av1", hardware("amf"))
    assert value_after(amf, "-qp_i") == value_after(amf, "-qp_p") == "130" and "-qp_b" not in amf


def test_amf_and_videotoolbox() -> None:
    amf = gpu_argv("mp4-h264", hardware("amf"), speed="fast")
    assert value_after(amf, "-quality") == "speed" and value_after(amf, "-rc") == "cqp"
    assert (value_after(amf, "-qp_i"), value_after(amf, "-qp_p"), value_after(amf, "-qp_b")) == (
        "23",
        "23",
        "25",
    )
    vt = gpu_argv("mp4-h264", hardware("videotoolbox", families=("h264", "hevc")))
    assert value_after(vt, "-c:v") == "h264_videotoolbox" and value_after(vt, "-q:v") == "59"
    assert "-preset" not in vt


def test_size_target_uses_a_capped_bitrate() -> None:
    args = gpu_argv("share-size", hardware(), quality=10)
    kbps = int(value_after(args, "-b:v").rstrip("k"))
    assert value_after(args, "-rc") == "vbr" and "-cq" not in args
    assert (
        value_after(args, "-maxrate") == f"{kbps * 3 // 2}k"
        and value_after(args, "-bufsize") == f"{kbps * 2}k"
    )


def test_audio_only_input_never_uses_the_gpu() -> None:
    plan = hardware().plan_for(CATALOG.get("mp4-h264"))
    audio_only = media(video=None, subtitles=[])
    args = build_command(
        ffmpeg="ffmpeg",
        media=audio_only,
        preset=CATALOG.get("mp3"),
        options=JobOptions(preset_id="mp3"),
        output="/out/x.mp3",
        gpu=plan,
    )
    assert not any("nvenc" in a for a in args)


def _info(*encoders: str) -> FFmpegInfo:
    return FFmpegInfo("ffmpeg", "ffprobe", "8.0", encoders=frozenset({"aac", *encoders}))


def test_detection_keeps_only_encoders_that_really_run(tmp_path: Path) -> None:
    ran: list[list[str]] = []

    def runner(argv: list[str]) -> bool:
        ran.append(argv)
        encoder = argv[argv.index("-c:v") + 1]
        ten_bit = "p010le" in argv
        return (encoder == "h264_nvenc" and not ten_bit) or encoder == "hevc_nvenc"

    info = _info("h264_nvenc", "hevc_nvenc", "av1_nvenc", "h264_vaapi")
    found = detect_hardware(info, platform="linux", dri=tmp_path, runner=runner)
    assert found.backend == "nvenc" and set(found.encoders) == {"h264", "hevc"}
    assert found.encoders["hevc"].ten_bit and not found.encoders["h264"].ten_bit
    # Every probe is a real encode of a synthetic clip, thrown away
    assert all(a[-3:] == ["-f", "null", "-"] and "lavfi" in a for a in ran)
    # Test encodes use the production arguments
    assert any(a[a.index("-c:v") + 1] == "av1_nvenc" and "-cq" in a for a in ran)


def test_detection_falls_through_to_vaapi_with_a_render_node(tmp_path: Path) -> None:
    (tmp_path / "card0").touch()
    (tmp_path / "renderD128").touch()
    assert render_node(tmp_path) == str(tmp_path / "renderD128")
    info = _info("h264_nvenc", "h264_vaapi", "hevc_vaapi")

    def runner(argv: list[str]) -> bool:
        return "-vaapi_device" in argv

    found = detect_hardware(info, platform="linux", dri=tmp_path, runner=runner)
    assert found.backend == "vaapi" and found.device == str(tmp_path / "renderD128")
    assert set(found.encoders) == {"h264", "hevc"}
    assert detect_hardware(info, platform="linux", dri=tmp_path / "none", runner=runner) is NO_HARDWARE


def test_detection_per_platform(tmp_path: Path) -> None:
    info = _info("h264_videotoolbox", "hevc_videotoolbox", "h264_nvenc", "h264_amf")
    mac = detect_hardware(info, platform="darwin", dri=tmp_path, runner=lambda _argv: True)
    assert mac.backend == "videotoolbox" and set(mac.encoders) == {"h264", "hevc"}
    tried: list[str] = []

    def windows(argv: list[str]) -> bool:
        tried.append(argv[argv.index("-c:v") + 1])
        return "amf" in tried[-1]

    win = detect_hardware(info, platform="win32", dri=tmp_path, runner=windows)
    assert win.backend == "amf" and tried[0] == "h264_nvenc"


@requires_ffmpeg
def test_detection_on_this_machine(ffmpeg_info: FFmpegInfo) -> None:
    found = detect_hardware(ffmpeg_info)
    # Whatever the hardware, the answer is consistent (usually "none" on CI runners)
    assert found.available == bool(found.backend)
    for encoder in found.encoders.values():
        assert encoder.backend == found.backend and ffmpeg_info.has_encoder(encoder.name)


def test_plan_is_frozen() -> None:
    plan = GpuPlan(GpuEncoder("nvenc", "h264", "h264_nvenc", False))
    with pytest.raises(AttributeError):
        plan.device = "x"  # type: ignore[misc]
