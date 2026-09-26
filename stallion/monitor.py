"""Live CPU, memory and GPU usage for the activity monitor.

NVIDIA cards are read through ``nvidia-smi``, AMD cards through sysfs (``gpu_busy_percent``);
Intel GPUs are reported by name only, since their load needs elevated privileges to read.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import platform
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import psutil

from .engine.ffmpeg import POPEN_KWARGS

log = logging.getLogger(__name__)

ACTIVE_INTERVAL = 1.0
IDLE_INTERVAL = 3.0
DRM_ROOT = Path("/sys/class/drm")
_NVIDIA_FIELDS = "name,utilization.gpu,utilization.encoder,utilization.decoder,memory.used,memory.total"
# Older drivers do not know the encoder/decoder utilization fields
_NVIDIA_BASIC_FIELDS = "name,utilization.gpu,memory.used,memory.total"
_MIB = 1024 * 1024

Event = dict[str, Any]


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None  # "[N/A]", "[Not Supported]"


def parse_nvidia_smi(text: str, fields: str = _NVIDIA_FIELDS) -> dict[str, Any] | None:
    """First GPU of ``nvidia-smi --query-gpu=<fields> --format=csv,noheader,nounits``."""

    line = next((ln for ln in text.splitlines() if ln.strip()), "")
    values = dict(zip(fields.split(","), (part.strip() for part in line.split(",")), strict=False))
    if not values.get("name"):
        return None
    used, total = _number(values.get("memory.used", "")), _number(values.get("memory.total", ""))
    return {
        "vendor": "nvidia",
        "name": values["name"],
        "util": _number(values.get("utilization.gpu", "")),
        "encoder": _number(values.get("utilization.encoder", "")),
        "decoder": _number(values.get("utilization.decoder", "")),
        "memory_used": used * _MIB if used is not None else None,
        "memory_total": total * _MIB if total is not None else None,
    }


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def find_drm_gpus(root: Path = DRM_ROOT) -> list[tuple[str, Path]]:
    """(vendor, device dir) of each display card, e.g. ("amd", /sys/class/drm/card1/device)."""

    vendors = {"0x1002": "amd", "0x8086": "intel", "0x10de": "nvidia"}
    found = []
    for card in sorted(root.glob("card[0-9]*")):
        if "-" in card.name:  # connectors such as card1-HDMI-A-1
            continue
        vendor = vendors.get(_read(card / "device" / "vendor") or "")
        if vendor:
            found.append((vendor, card / "device"))
    return found


def amd_stats(device: Path) -> dict[str, Any]:
    busy = _read(device / "gpu_busy_percent")
    used = _read(device / "mem_info_vram_used")
    total = _read(device / "mem_info_vram_total")
    return {
        "vendor": "amd",
        "name": _read(device / "product_name") or "AMD GPU",
        "util": _number(busy) if busy else None,
        "encoder": None,
        "decoder": None,
        "memory_used": _number(used) if used else None,
        "memory_total": _number(total) if total else None,
    }


def cpu_model() -> str:
    if sys.platform.startswith("linux"):
        for line in (_read(Path("/proc/cpuinfo")) or "").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or platform.machine()


# nvidia-smi attempts before deciding there is no usable NVIDIA driver
_SMI_PROBES = 3
# Once it has answered, missed readings (driver busy, machine under load) reuse the last one
_SMI_STALE = 5


class GpuReader:
    """Current usage of the main GPU, or None when no supported GPU is present."""

    def __init__(self, drm_root: Path = DRM_ROOT) -> None:
        self._smi = shutil.which("nvidia-smi")
        self._fields = _NVIDIA_FIELDS
        self._smi_ok = False
        self._misses = 0
        self._last: dict[str, Any] | None = None
        cards = find_drm_gpus(drm_root) if sys.platform.startswith("linux") else []
        self._amd = next((path for vendor, path in cards if vendor == "amd"), None)
        self._intel = next((path for vendor, path in cards if vendor == "intel"), None)

    async def read(self) -> dict[str, Any] | None:
        if self._smi:
            stats = await self._nvidia()
            if stats is not None:
                return stats
        if self._amd:
            return amd_stats(self._amd)
        if self._intel:
            return {"vendor": "intel", "name": "Intel GPU", "util": None, "encoder": None, "decoder": None}
        return None

    async def _nvidia(self) -> dict[str, Any] | None:
        assert self._smi
        stats = await self._query(self._fields)
        if stats is None and not self._smi_ok and self._fields == _NVIDIA_FIELDS:
            # Older drivers reject the encoder/decoder fields: settle on the basic set
            stats = await self._query(_NVIDIA_BASIC_FIELDS)
            if stats is not None:
                self._fields = _NVIDIA_BASIC_FIELDS
        if stats is not None:
            self._smi_ok = True
            self._misses = 0
            self._last = stats
            return stats
        self._misses += 1
        if not self._smi_ok:
            if self._misses >= _SMI_PROBES:
                self._smi = None  # no usable NVIDIA driver: stop asking
            return None
        # A known GPU does not vanish because one reading failed
        return self._last if self._misses <= _SMI_STALE else None

    async def _query(self, fields: str) -> dict[str, Any] | None:
        assert self._smi
        text = await _output([self._smi, f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
        return parse_nvidia_smi(text, fields) if text else None


async def _output(argv: list[str], time_limit: float = 3.0) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            **POPEN_KWARGS,
        )
    except OSError:
        return None
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), time_limit)
    except (TimeoutError, asyncio.CancelledError) as exc:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), 2)
        if isinstance(exc, asyncio.CancelledError):
            raise
        return None
    return stdout.decode("utf-8", "replace") if proc.returncode == 0 else None


class SystemMonitor:
    """Samples the machine and hands ``{"type": "system"}`` events to ``publish``.

    ``pids`` maps job ids to the ffmpeg process running them; ``listening`` tells whether
    anyone is watching (no sampling otherwise).
    """

    def __init__(
        self,
        publish: Callable[[Event], None],
        pids: Callable[[], Mapping[str, int]],
        listening: Callable[[], bool],
        gpu: GpuReader | None = None,
    ) -> None:
        self._publish = publish
        self._pids = pids
        self._listening = listening
        self._gpu = gpu or GpuReader()
        self._procs: dict[int, psutil.Process] = {}
        self._cpu_model = cpu_model()

    async def run(self) -> None:
        psutil.cpu_percent(percpu=True)  # the first reading only sets the baseline
        while True:
            await asyncio.sleep(ACTIVE_INTERVAL if self._pids() else IDLE_INTERVAL)
            if not self._listening():
                continue
            try:
                self._publish(await self.sample())
            except Exception:  # the monitor must never take the queue down with it
                log.exception("System monitor sample failed")

    async def sample(self) -> Event:
        cores = psutil.cpu_percent(percpu=True)
        memory = psutil.virtual_memory()
        return {
            "type": "system",
            "cpu": {
                "model": self._cpu_model,
                "total": round(sum(cores) / len(cores), 1) if cores else 0.0,
                "cores": [round(value, 1) for value in cores],
            },
            "memory": {"used": memory.total - memory.available, "total": memory.total},
            "gpu": await self._gpu.read(),
            "processes": self._processes(),
        }

    def _processes(self) -> list[dict[str, Any]]:
        pids = dict(self._pids())
        for pid in set(self._procs) - set(pids.values()):
            del self._procs[pid]
        rows = []
        for job_id, pid in pids.items():
            try:
                proc = self._procs.get(pid)
                if proc is None:
                    proc = self._procs[pid] = psutil.Process(pid)
                    proc.cpu_percent(None)  # baseline; the next sample reports real usage
                cpu = round(proc.cpu_percent(None), 1)
                rows.append({"job_id": job_id, "cpu": cpu, "threads": proc.num_threads()})
            except psutil.Error:
                self._procs.pop(pid, None)
        return rows
