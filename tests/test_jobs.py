from __future__ import annotations

import asyncio
import shutil
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from stallion.engine.ffmpeg import FFmpegInfo
from stallion.engine.presets import PresetCatalog
from stallion.fs import FileSystem
from stallion.jobs import JobManager, JobStatus, ManagerError
from stallion.settings import Settings, SettingsStore

from .conftest import requires_ffmpeg
from .test_runner import exited

pytestmark = [pytest.mark.anyio, requires_ffmpeg]


async def wait_for(predicate: Callable[[], bool], timeout: float = 60) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.05)


@pytest.fixture
async def manager(ffmpeg_info: FFmpegInfo, media_dir: Path, tmp_path: Path) -> AsyncIterator[JobManager]:
    settings = SettingsStore(None, Settings(output_dir=str(tmp_path / "out"), concurrency=2))
    mgr = JobManager(
        ffmpeg=ffmpeg_info,
        catalog=PresetCatalog.builtin(ffmpeg_info),
        settings=settings,
        fs=FileSystem([media_dir, tmp_path]),
        cache_dir=tmp_path / "cache",
    )
    (tmp_path / "out").mkdir()
    await mgr.start()
    yield mgr
    await mgr.shutdown()


async def test_add_files_applies_smart_defaults(manager: JobManager, media_dir: Path, tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_text("nope")
    jobs, errors = await manager.add_files(
        [str(media_dir / "movie.mkv"), str(media_dir / "song.mp3"), str(junk), "/etc/passwd"]
    )
    by_name = {job.name: job for job in jobs}
    assert set(by_name) == {"movie.mkv", "song.mp3"}
    # A matching .srt next to the movie is burned in, like the classic app did
    movie = by_name["movie.mkv"]
    assert movie.options.subtitle_mode == "burn" and movie.options.subtitle_file == str(
        media_dir / "movie.srt"
    )
    assert movie.output_path == str(tmp_path / "out" / "movie.mp4")
    # Audio-only input gets an audio format instead of an empty MP4 video
    assert by_name["song.mp3"].options.preset_id == "mp3"
    assert {e["code"] for e in errors} == {"not_media", "outside_roots"}

    _, again = await manager.add_files([str(media_dir / "movie.mkv")])
    assert again[0]["code"] == "duplicate"
    first_revision = movie.revision
    await wait_for(lambda: all(job.thumbnail for job in jobs if job.media.video))
    assert movie.revision > first_revision, "thumbnail updates must bump the revision"


async def test_queue_runs_to_completion(manager: JobManager, media_dir: Path, tmp_path: Path) -> None:
    events = manager.subscribe()
    clash = tmp_path / "clip.mkv"
    shutil.copy(media_dir / "movie.mkv", clash)
    jobs, _ = await manager.add_files([str(media_dir / "clip.mp4"), str(clash)], {"speed": "fast"})
    manager.start_queue()
    seen: list[dict[str, object]] = []
    while True:
        event = await asyncio.wait_for(events.get(), 60)
        seen.append(event)
        if event["type"] == "queue_finished":
            break
    assert all(job.status == JobStatus.COMPLETED for job in jobs)
    assert all(job.progress.percent == 100 and job.output_size for job in jobs)
    # Both inputs map to out/clip.mp4: the second one gets a unique name
    assert sorted(Path(job.output_path).name for job in jobs) == ["clip (1).mp4", "clip.mp4"]
    assert {"job", "queue", "queue_finished"} <= {e["type"] for e in seen}
    assert not manager.queue_running


async def test_edit_validation(manager: JobManager, media_dir: Path) -> None:
    [job], _ = await manager.add_files([str(media_dir / "clip.mp4")])
    updated = manager.update_options(job.id, {"preset_id": "webm-vp9", "subtitle_style": {"size": 40}})
    assert updated.output_path.endswith("clip.webm") and updated.options.subtitle_style.size == 40
    with pytest.raises(ManagerError) as err:
        manager.update_options(job.id, {"preset_id": "remux-mkv", "max_height": 480})
    assert err.value.status == 422 and err.value.code == "remux_filters"
    with pytest.raises(ManagerError) as err:
        manager.update_options(job.id, {"subtitle_file": "/etc/hosts", "subtitle_mode": "burn"})
    assert err.value.code == "outside_roots"
    with pytest.raises(ManagerError):
        manager.update_options(job.id, {"bogus": 1})
    _, errors = manager.update_many([job.id, "missing"], {"quality": 20})
    assert errors[0]["code"] == "job_not_found"


async def test_cancel_pause_retry_remove(manager: JobManager, long_video: Path, tmp_path: Path) -> None:
    manager.fs = FileSystem([*manager.fs.roots, long_video.parent])
    [job], _ = await manager.add_files([str(long_video)], {"preset_id": "mp4-h265", "speed": "quality"})
    manager.start_queue()
    await wait_for(lambda: job.status == JobStatus.RUNNING and job.progress.out_time_s > 0)
    run = manager._runs[job.id]
    output = Path(job.output_path)
    assert output.exists()
    with pytest.raises(ManagerError):
        manager.update_options(job.id, {"quality": 30})

    if sys.platform != "win32":
        manager.pause_queue()
        assert job.status == JobStatus.PAUSED and not manager.queue_running
        manager.start_queue()
        assert job.status == JobStatus.RUNNING
        manager.pause_job(job.id)
        await asyncio.sleep(0.5)
        frozen = job.progress.out_time_s
        await asyncio.sleep(0.8)
        assert job.progress.out_time_s == frozen
        manager.resume_job(job.id)

    await manager.cancel_job(job.id)
    assert job.status == JobStatus.CANCELED
    assert not output.exists(), "partial output must be removed"
    assert exited(run)

    manager.retry_job(job.id)
    assert job.status == JobStatus.QUEUED and job.progress.percent == 0
    removed = await manager.remove_jobs([job.id])
    assert removed == [job.id] and job.id not in manager.jobs


async def test_shutdown_leaves_no_ffmpeg_behind(
    ffmpeg_info: FFmpegInfo, long_video: Path, tmp_path: Path
) -> None:
    mgr = JobManager(
        ffmpeg=ffmpeg_info,
        catalog=PresetCatalog.builtin(ffmpeg_info),
        settings=SettingsStore(None, Settings(output_dir=str(tmp_path))),
        fs=FileSystem([long_video.parent, tmp_path]),
        cache_dir=tmp_path / "cache",
    )
    await mgr.start()
    [job], _ = await mgr.add_files([str(long_video)], {"preset_id": "mp4-h265"})
    mgr.start_queue()
    await wait_for(lambda: job.id in mgr._runs and mgr._runs[job.id].pid is not None)
    run = mgr._runs[job.id]
    await mgr.shutdown()
    assert exited(run)
    assert not Path(job.output_path).exists()
