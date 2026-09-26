from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from stallion.monitor import (
    _NVIDIA_BASIC_FIELDS,
    GpuReader,
    SystemMonitor,
    amd_stats,
    find_drm_gpus,
    parse_nvidia_smi,
)

MIB = 1024 * 1024


def test_parse_nvidia_smi() -> None:
    stats = parse_nvidia_smi("NVIDIA GeForce RTX 3060, 41, 38, 12, 1130, 12288\n")
    assert stats is not None
    assert stats["name"] == "NVIDIA GeForce RTX 3060"
    assert (stats["util"], stats["encoder"], stats["decoder"]) == (41, 38, 12)
    assert stats["memory_used"] == 1130 * MIB and stats["memory_total"] == 12288 * MIB
    # Data-center cards and old drivers report some fields as N/A
    partial = parse_nvidia_smi("Tesla T4, 5, [N/A], [Not Supported], 300, 15360")
    assert partial is not None and partial["encoder"] is None and partial["decoder"] is None
    basic = parse_nvidia_smi("Quadro P400, 3, 100, 2000", _NVIDIA_BASIC_FIELDS)
    assert basic is not None and basic["util"] == 3 and basic["encoder"] is None
    assert parse_nvidia_smi("") is None


def _card(root: Path, name: str, vendor: str, **files: str) -> Path:
    device = root / name / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text(vendor + "\n")
    for key, value in files.items():
        (device / key).write_text(value + "\n")
    return device


def test_drm_gpus_and_amd_sysfs(tmp_path: Path) -> None:
    _card(tmp_path, "card0", "0x8086")
    amd = _card(
        tmp_path,
        "card1",
        "0x1002",
        gpu_busy_percent="37",
        mem_info_vram_used=str(1024 * MIB),
        mem_info_vram_total=str(8192 * MIB),
    )
    (tmp_path / "card1-HDMI-A-1").mkdir()  # a connector, not a card
    assert find_drm_gpus(tmp_path) == [("intel", tmp_path / "card0" / "device"), ("amd", amd)]
    stats = amd_stats(amd)
    assert stats["name"] == "AMD GPU" and stats["util"] == 37
    assert stats["memory_used"] == 1024 * MIB and stats["memory_total"] == 8192 * MIB


@pytest.mark.anyio
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="sysfs GPUs are Linux only")
async def test_gpu_reader_prefers_amd_over_intel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("stallion.monitor.shutil.which", lambda _name: None)
    _card(tmp_path, "card0", "0x8086")
    assert (await GpuReader(tmp_path).read() or {})["vendor"] == "intel"
    _card(tmp_path, "card1", "0x1002", gpu_busy_percent="12")
    assert (await GpuReader(tmp_path).read() or {})["util"] == 12
    assert await GpuReader(tmp_path / "missing").read() is None


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform == "win32", reason="stands in a shell script for nvidia-smi")
async def test_nvidia_readings_survive_a_failed_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    down = tmp_path / "down"
    smi = tmp_path / "nvidia-smi"
    smi.write_text(f'#!/bin/sh\n[ -e "{down}" ] && exit 9\necho "RTX 3060, 40, 30, 5, 1000, 12288"\n')
    smi.chmod(0o755)
    monkeypatch.setattr(
        "stallion.monitor.shutil.which", lambda name: str(smi) if name == "nvidia-smi" else None
    )

    reader = GpuReader(tmp_path / "no-drm")
    first = await reader.read()
    assert first is not None and first["util"] == 40 and first["encoder"] == 30
    down.touch()  # the driver misses a reading, e.g. with the machine at full load
    assert await reader.read() == first
    down.unlink()
    assert (await reader.read() or {})["util"] == 40

    # Without a working driver it stops asking after a few attempts
    down.touch()
    broken = GpuReader(tmp_path / "no-drm")
    for _ in range(3):
        assert await broken.read() is None
    assert broken._smi is None


class _NoGpu(GpuReader):
    async def read(self) -> None:
        return None


@pytest.mark.anyio
async def test_sample_reports_cpu_memory_and_job_processes() -> None:
    busy = subprocess.Popen([sys.executable, "-c", "import time\nwhile True: time.sleep(0.01)"])
    try:
        events: list[dict[str, object]] = []
        monitor = SystemMonitor(events.append, lambda: {"job-1": busy.pid}, lambda: True, gpu=_NoGpu())
        await monitor.sample()  # baseline for the per-process reading
        await asyncio.sleep(0.2)
        sample = await monitor.sample()
    finally:
        busy.kill()
        busy.wait()
    cpu = sample["cpu"]
    assert isinstance(cpu, dict) and cpu["cores"] and 0 <= cpu["total"] <= 100
    memory = sample["memory"]
    assert isinstance(memory, dict) and 0 < memory["used"] <= memory["total"]
    assert sample["gpu"] is None
    processes = sample["processes"]
    assert isinstance(processes, list) and len(processes) == 1
    assert processes[0]["job_id"] == "job-1" and processes[0]["cpu"] >= 0 and processes[0]["threads"] >= 1
