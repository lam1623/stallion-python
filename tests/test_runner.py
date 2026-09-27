from __future__ import annotations

import asyncio
import sys

import pytest

from stallion.engine.runner import FFmpegRun, Progress, parse_progress

pytestmark = pytest.mark.anyio

TICKER = """
import sys, time
i = 0
while True:
    i += 1
    sys.stdout.write(f"out_time_us={i * 100000}\\nspeed=2.0x\\nfps=25\\ntotal_size={i * 1000}\\nprogress=continue\\n")
    sys.stdout.flush()
    time.sleep(0.05)
"""


def fake(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_parse_progress_block() -> None:
    progress = parse_progress(
        {
            "out_time_us": "5000000",
            "speed": "2.5x",
            "fps": "48.0",
            "total_size": "1024",
            "bitrate": "800.1kbits/s",
        },
        duration_s=10.0,
        elapsed_s=2.0,
    )
    assert progress.percent == 50.0 and progress.eta_s == 2.0
    assert progress.fps == 48.0 and progress.size_bytes == 1024 and progress.bitrate_kbps == 800.1


def test_parse_progress_edge_cases() -> None:
    assert parse_progress({"out_time_us": "N/A", "speed": "N/A"}, 10, 0) == Progress()
    assert parse_progress({"out_time_ms": "-9223372036854775807"}, 10, 0).out_time_s == 0
    # Never report 100% before ffmpeg actually exits successfully
    assert parse_progress({"out_time_us": "20000000", "progress": "end"}, 10, 0).percent == 99.9
    assert parse_progress({"out_time_us": "1000000"}, 0, 0).percent == 0


async def test_large_stderr_does_not_deadlock() -> None:
    code = (
        "import sys\n"
        "sys.stderr.write('w' * 400_000 + '\\n'); sys.stderr.flush()\n"
        "print('out_time_us=1000000'); print('progress=end')\n"
    )
    updates: list[Progress] = []
    result = await asyncio.wait_for(FFmpegRun(fake(code), 1.0, updates.append).run(), timeout=15)
    assert result.returncode == 0 and not result.canceled
    assert updates and updates[-1].percent == 99.9
    # Huge lines are kept but truncated so a chatty process cannot exhaust memory
    assert len(result.log) == 1 and len(result.log[0]) == 8192


async def test_missing_binary_raises_oserror() -> None:
    with pytest.raises(OSError):
        await FFmpegRun(["/nonexistent/ffmpeg"], 1.0).run()


async def test_cancel_kills_the_process() -> None:
    first = asyncio.Event()
    run = FFmpegRun(fake(TICKER), 100.0, lambda _p: first.set())
    task = asyncio.create_task(run.run())
    await asyncio.wait_for(first.wait(), 10)
    await run.cancel()
    result = await asyncio.wait_for(task, 10)
    assert result.canceled and result.returncode != 0
    assert exited(run)


async def test_task_cancellation_kills_the_process() -> None:
    first = asyncio.Event()
    run = FFmpegRun(fake(TICKER), 100.0, lambda _p: first.set())
    task = asyncio.create_task(run.run())
    await asyncio.wait_for(first.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exited(run)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
async def test_pause_and_resume() -> None:
    seen: list[Progress] = []
    run = FFmpegRun(fake(TICKER), 100.0, seen.append)
    task = asyncio.create_task(run.run())
    while len(seen) < 3:
        await asyncio.sleep(0.02)
    run.pause()
    await asyncio.sleep(0.3)  # let already-buffered output drain
    frozen = len(seen)
    await asyncio.sleep(0.4)
    assert len(seen) == frozen and run.paused
    run.resume()
    await asyncio.sleep(0.4)
    assert len(seen) > frozen
    await run.cancel()
    assert (await task).canceled


def exited(run: FFmpegRun) -> bool:
    """True once the child has been reaped (portable, unlike probing a PID)."""

    return run._proc is not None and run._proc.returncode is not None
