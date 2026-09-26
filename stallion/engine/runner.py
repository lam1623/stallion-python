"""Run one ffmpeg process with live progress, pause/resume and cancellation."""

from __future__ import annotations

import asyncio
import collections
import os
import signal
import sys
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, NamedTuple

from pydantic import BaseModel

from .ffmpeg import POPEN_KWARGS

MAX_LINE = 8192

# SVT-AV1 logs through its own channel; keep only its errors
_CHILD_ENV = {**os.environ, "SVT_LOG": "1", "AV_LOG_FORCE_NOCOLOR": "1"}


class Progress(BaseModel):
    percent: float = 0.0
    out_time_s: float = 0.0
    speed: float | None = None
    fps: float | None = None
    size_bytes: int | None = None
    bitrate_kbps: float | None = None
    eta_s: float | None = None
    elapsed_s: float = 0.0


class RunResult(NamedTuple):
    returncode: int
    canceled: bool
    log: list[str]


class PauseNotSupportedError(RuntimeError):
    """Raised when the platform cannot suspend a child process."""


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip().rstrip("x").replace("kbits/s", ""))
    except ValueError:
        return None


def parse_progress(block: dict[str, str], duration_s: float, elapsed_s: float) -> Progress:
    """Build a :class:`Progress` from one ``-progress`` key/value block."""

    out_us = _num(block.get("out_time_us")) or _num(block.get("out_time_ms"))
    out_time = max(0.0, (out_us or 0.0) / 1_000_000)
    speed = _num(block.get("speed"))
    size = _num(block.get("total_size"))
    percent = min(99.9, out_time / duration_s * 100.0) if duration_s > 0 else 0.0
    eta = None
    if speed and speed > 0 and duration_s > 0:
        eta = max(0.0, (duration_s - out_time) / speed)
    return Progress(
        percent=round(percent, 2),
        out_time_s=round(out_time, 3),
        speed=speed if speed and speed > 0 else None,
        fps=_num(block.get("fps")),
        size_bytes=int(size) if size and size > 0 else None,
        bitrate_kbps=_num(block.get("bitrate")),
        eta_s=round(eta, 1) if eta is not None else None,
        elapsed_s=round(elapsed_s, 1),
    )


class FFmpegRun:
    """A single ffmpeg invocation; both output pipes are drained concurrently."""

    def __init__(
        self,
        argv: list[str],
        duration_s: float,
        on_progress: Callable[[Progress], None] | None = None,
        log_lines: int = 300,
    ) -> None:
        self.argv = argv
        self.duration_s = duration_s
        self.on_progress = on_progress
        self.log: collections.deque[str] = collections.deque(maxlen=log_lines)
        self._proc: asyncio.subprocess.Process | None = None
        self._cancel_requested = False
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._started_at = 0.0

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def elapsed(self) -> float:
        if not self._started_at:
            return 0.0
        now = self._paused_at or time.monotonic()
        return max(0.0, now - self._started_at - self._paused_total)

    async def run(self) -> RunResult:
        """Start ffmpeg and wait for it. ``OSError`` propagates if it cannot start."""

        kwargs: dict[str, Any] = dict(POPEN_KWARGS)
        self._proc = await asyncio.create_subprocess_exec(
            *self.argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_CHILD_ENV,
            **kwargs,
        )
        self._started_at = time.monotonic()
        if self._cancel_requested:
            await self._terminate()  # canceled while the process was starting
        try:
            await asyncio.gather(self._read_progress(), self._read_log())
            returncode = await self._proc.wait()
        except asyncio.CancelledError:
            await self._terminate()
            raise
        return RunResult(returncode, self._cancel_requested, list(self.log))

    async def _read_progress(self) -> None:
        assert self._proc and self._proc.stdout
        block: dict[str, str] = {}
        async for line in _lines(self._proc.stdout):
            key, sep, value = line.strip().partition("=")
            if not sep:
                continue
            block[key.strip()] = value.strip()
            if key == "progress":
                if self.on_progress:
                    self.on_progress(parse_progress(block, self.duration_s, self.elapsed()))
                block = {}

    async def _read_log(self) -> None:
        assert self._proc and self._proc.stderr
        async for line in _lines(self._proc.stderr):
            if line.strip():
                self.log.append(line.rstrip())

    def pause(self) -> None:
        if self._proc is None or self._proc.returncode is not None or self.paused:
            return
        _suspend(self._proc.pid, suspend=True)
        self._paused_at = time.monotonic()

    def resume(self) -> None:
        if self._proc is None or not self.paused:
            return
        if self._proc.returncode is None:
            _suspend(self._proc.pid, suspend=False)
        assert self._paused_at is not None
        self._paused_total += time.monotonic() - self._paused_at
        self._paused_at = None

    async def cancel(self) -> None:
        self._cancel_requested = True
        await self._terminate()

    async def _terminate(self, grace: float = 5.0) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        if self.paused:
            self.resume()  # a stopped process never handles SIGTERM
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), grace)
        except ProcessLookupError:
            return
        except TimeoutError:
            proc.kill()
            await proc.wait()


async def _lines(stream: asyncio.StreamReader, max_line: int = MAX_LINE) -> AsyncIterator[str]:
    """Yield decoded lines; unlike ``readline`` this survives arbitrarily long lines."""

    buffer = b""
    while chunk := await stream.read(65536):
        buffer += chunk
        *complete, buffer = buffer.split(b"\n")
        for raw in complete:
            yield raw[:max_line].decode("utf-8", "replace").rstrip("\r")
        if len(buffer) > max_line:
            buffer = buffer[:max_line]
    if buffer:
        yield buffer[:max_line].decode("utf-8", "replace").rstrip("\r")


def _suspend(pid: int, *, suspend: bool) -> None:
    if sys.platform == "win32":
        try:
            import psutil
        except ImportError as exc:  # pragma: no cover - windows only
            raise PauseNotSupportedError("Pausing needs the psutil package on Windows") from exc
        process = psutil.Process(pid)
        if suspend:
            process.suspend()
        else:
            process.resume()
        return
    os.kill(pid, signal.SIGSTOP if suspend else signal.SIGCONT)
