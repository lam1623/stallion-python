"""Conversion queue: jobs, scheduling, lifecycle and change events."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import shlex
import time
import uuid
from collections.abc import Coroutine, Iterable
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .engine.command import (
    SAMPLE_MEDIA,
    OptionsError,
    build_command,
    detect_text_encoding,
    display_command,
    find_external_subtitles,
    plan_output_path,
    unique_path,
    validate_options,
)
from .engine.custom import (
    CustomPresetStore,
    DraftError,
    FormatDraft,
    Issue,
    compile_draft,
    draft_issues,
    draft_warnings,
    new_preset_id,
)
from .engine.ffmpeg import POPEN_KWARGS, FFmpegInfo
from .engine.hwaccel import NO_HARDWARE, GpuPlan, HardwareEncoders, detect_hardware, wants_gpu
from .engine.options import JobOptions
from .engine.presets import Preset, PresetCatalog, PresetView
from .engine.probe import MediaInfo, ProbeError, probe_media
from .engine.runner import FFmpegRun, PauseNotSupportedError, Progress, RunResult
from .fs import FileSystem, PathError
from .monitor import SystemMonitor
from .settings import SettingsStore

log = logging.getLogger(__name__)

Event = dict[str, Any]


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


ACTIVE = frozenset({JobStatus.RUNNING, JobStatus.PAUSED})
FINISHED = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED})


class Job(BaseModel):
    id: str
    name: str
    input_path: str
    size_bytes: int
    media: MediaInfo
    options: JobOptions
    output_path: str
    status: JobStatus = JobStatus.QUEUED
    progress: Progress = Field(default_factory=Progress)
    error: str | None = None
    external_subtitles: list[str] = []
    thumbnail: bool = False
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    output_size: int | None = None
    # Where the video is encoded: planned while queued, the real one once started
    engine: Literal["cpu", "gpu"] = "cpu"
    # Video encoder, e.g. "hevc_nvenc" or "libx265" (None for audio-only and copied video)
    encoder: str | None = None
    # The GPU encoder failed and the file was converted on the CPU instead
    gpu_fallback: bool = False
    # Bumped on every published change so clients can drop stale copies (e.g. late HTTP responses)
    revision: int = 0


class ManagerError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def summarize_error(result: RunResult | None, fallback: str) -> str:
    if result is None:
        return fallback
    lines = [line.strip() for line in result.log if line.strip()]
    if not lines:
        return f"ffmpeg exited with code {result.returncode}"
    return " · ".join(lines[-3:])[:600]


class JobManager:
    def __init__(
        self,
        *,
        ffmpeg: FFmpegInfo | None,
        catalog: PresetCatalog,
        settings: SettingsStore,
        fs: FileSystem,
        cache_dir: Path,
        system_monitor: bool = True,
        detect_gpu: bool = True,
        custom: CustomPresetStore | None = None,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.catalog = catalog
        # The user's own formats (in memory only when no store is given)
        self.custom = custom or CustomPresetStore(None)
        self.catalog.set_custom(self.custom.presets())
        self.settings = settings
        self.fs = fs
        self.thumb_dir = cache_dir / "thumbs"
        self.jobs: dict[str, Job] = {}
        self.logs: dict[str, list[str]] = {}
        self.queue_running = False
        self._runs: dict[str, FFmpegRun] = {}
        self._job_tasks: dict[str, asyncio.Task[None]] = {}
        self._background: set[asyncio.Task[Any]] = set()
        self._reserved: set[Path] = set()
        self._paused_by_queue: set[str] = set()
        # Jobs asked to stop, including between a failed GPU attempt and its CPU retry
        self._cancel_requested: set[str] = set()
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._dirty: set[str] = set()
        self._flusher: asyncio.Task[None] | None = None
        self._launched_since_start = False
        self._probe_limit = asyncio.Semaphore(4)
        self._thumb_limit = asyncio.Semaphore(2)
        self._closing = False
        self._monitor = (
            SystemMonitor(self._publish, self.active_pids, lambda: bool(self._subscribers))
            if system_monitor
            else None
        )
        self._monitor_task: asyncio.Task[None] | None = None
        # GPU encoders, known once the test encodes finish (None while they run)
        self.hardware: HardwareEncoders | None = None if detect_gpu and ffmpeg else NO_HARDWARE
        self._hardware_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._flusher = asyncio.create_task(self._flush_progress())
        if self._monitor is not None:
            self._monitor_task = asyncio.create_task(self._monitor.run())
        if self.hardware is None:
            self._hardware_task = asyncio.create_task(self._detect_hardware())

    async def _detect_hardware(self) -> None:
        assert self.ffmpeg is not None
        try:
            hardware = await asyncio.to_thread(detect_hardware, self.ffmpeg)
        except Exception:  # never let a driver quirk take the app down
            log.exception("GPU encoder detection failed")
            hardware = NO_HARDWARE
        self.hardware = hardware
        for job in self.jobs.values():
            if job.status == JobStatus.QUEUED and self._plan_engine(job):
                self._emit_job(job)
        self._publish({"type": "hardware", "hardware": self.hardware_summary()})

    async def hardware_ready(self) -> HardwareEncoders:
        """Wait for GPU detection (the CLI wants it settled before converting)."""

        if self._hardware_task is not None:
            await asyncio.shield(self._hardware_task)
        return self.hardware or NO_HARDWARE

    def hardware_summary(self) -> dict[str, Any]:
        if self.hardware is None:
            return {"state": "detecting", **NO_HARDWARE.summary()}
        return {"state": "ready", **self.hardware.summary(list(self.catalog))}

    async def shutdown(self) -> None:
        """Stop everything and make sure no ffmpeg process outlives the app."""

        self._closing = True
        self.queue_running = False
        for run in list(self._runs.values()):
            with contextlib.suppress(Exception):
                await run.cancel()
        job_tasks = list(self._job_tasks.values())
        if job_tasks:
            await asyncio.wait(job_tasks, timeout=10)
        pending = [
            t
            for t in [*job_tasks, *self._background, self._flusher, self._monitor_task, self._hardware_task]
            if t is not None and not t.done()
        ]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # ------------------------------------------------------------------ events

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def _publish(self, event: Event) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow client: drop its backlog and ask it to reload a snapshot
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "resync"})

    def active_pids(self) -> dict[str, int]:
        """ffmpeg process of each running job (for the activity monitor)."""

        return {job_id: run.pid for job_id, run in self._runs.items() if run.pid is not None}

    def snapshot(self) -> Event:
        return {
            "type": "snapshot",
            "jobs": [self.dump(j) for j in self.jobs.values()],
            "queue": self.queue_state(),
        }

    def queue_state(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in JobStatus}
        for job in self.jobs.values():
            counts[job.status.value] += 1
        return {"running": self.queue_running, "counts": counts}

    @staticmethod
    def dump(job: Job) -> dict[str, Any]:
        return job.model_dump(mode="json")

    def _emit_job(self, job: Job) -> None:
        if job.id in self.jobs:
            job.revision += 1
            self._publish({"type": "job", "job": self.dump(job)})

    def _emit_queue(self) -> None:
        self._publish({"type": "queue", "queue": self.queue_state()})

    def emit_settings(self) -> None:
        self._publish({"type": "settings", "settings": self.settings.current.model_dump()})

    def settings_changed(self) -> None:
        """Re-plan queued jobs (e.g. GPU encoding switched on or off) and tell the clients."""

        for job in self.jobs.values():
            if job.status == JobStatus.QUEUED and self._plan_engine(job):
                self._emit_job(job)
        self.emit_settings()
        self._schedule()

    async def _flush_progress(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            if not self._dirty:
                continue
            items = [
                {"id": job_id, "progress": self.jobs[job_id].progress.model_dump()}
                for job_id in self._dirty
                if job_id in self.jobs
            ]
            self._dirty.clear()
            if items:
                self._publish({"type": "progress", "items": items})

    def _on_progress(self, job_id: str, progress: Progress) -> None:
        job = self.jobs.get(job_id)
        if job is not None and job.status in ACTIVE:
            job.progress = progress
            self._dirty.add(job_id)

    # ------------------------------------------------------------------ helpers

    def get(self, job_id: str) -> Job:
        try:
            return self.jobs[job_id]
        except KeyError:
            raise ManagerError("job_not_found", "Job not found", 404) from None

    def _require_ffmpeg(self) -> FFmpegInfo:
        if self.ffmpeg is None:
            raise ManagerError("ffmpeg_missing", "FFmpeg is not installed or could not be found", 503)
        return self.ffmpeg

    def _preset(self, preset_id: str) -> Preset:
        if preset_id not in self.catalog:
            raise ManagerError("unknown_preset", f"Unknown format '{preset_id}'", 422)
        preset = self.catalog.get(preset_id)
        missing = self.catalog.missing_encoders(preset)
        if missing:
            raise ManagerError("encoder_missing", f"Your FFmpeg lacks: {', '.join(missing)}", 422)
        return preset

    def _gpu_plan(self, job: Job) -> GpuPlan | None:
        if self.hardware is None or job.media.video is None or job.options.preset_id not in self.catalog:
            return None
        preset = self.catalog.get(job.options.preset_id)
        if not wants_gpu(job.options, self.settings.current.gpu_encoding, preset.accel):
            return None
        return self.hardware.plan_for(preset)

    def _set_engine(self, job: Job, plan: GpuPlan | None) -> bool:
        """Record where the video will be encoded; True when that changed."""

        if job.options.preset_id not in self.catalog:
            return False  # its custom format was deleted: keep what it last used
        spec = self.catalog.get(job.options.preset_id).video
        engine: Literal["cpu", "gpu"] = "cpu"
        encoder: str | None = None
        if plan is not None:
            engine, encoder = "gpu", plan.encoder.name
        elif spec is not None and spec.codec != "copy" and job.media.video is not None:
            encoder = spec.codec
        changed = (job.engine, job.encoder) != (engine, encoder)
        job.engine, job.encoder = engine, encoder
        return changed

    def _plan_engine(self, job: Job) -> bool:
        return self._set_engine(job, self._gpu_plan(job))

    def _planned_output(self, job: Job) -> Path:
        preset = self.catalog.get(job.options.preset_id)
        default_dir = Path(self.settings.current.output_dir) if self.settings.current.output_dir else None
        return plan_output_path(job.input_path, preset, job.options, default_dir)

    def _normalize_options(self, options: JobOptions, media: MediaInfo) -> JobOptions:
        """Validate paths and the preset/media combination; returns the cleaned options."""

        updates: dict[str, Any] = {}
        if options.subtitle_file:
            updates["subtitle_file"] = str(self.fs.resolve(options.subtitle_file, kind="file"))
        if options.output_dir:
            updates["output_dir"] = str(self.fs.resolve(options.output_dir, kind="dir"))
        cleaned = options.model_copy(update=updates) if updates else options
        validate_options(media, self._preset(cleaned.preset_id), cleaned)
        return cleaned

    def _default_options(self, media: MediaInfo, patch: dict[str, Any]) -> JobOptions:
        settings = self.settings.current
        preset_id = settings.default_preset if settings.default_preset in self.catalog else "mp4-h264"
        if (
            "preset_id" not in patch
            and media.video is None
            and self.catalog.get(preset_id).category != "audio"
        ):
            preset_id = "mp3"
        return JobOptions.model_validate(_deep_merge({"preset_id": preset_id}, patch))

    # ------------------------------------------------------------------ jobs

    async def _probe(self, path: Path) -> MediaInfo:
        ffmpeg = self._require_ffmpeg()
        async with self._probe_limit:
            return await probe_media(path, ffmpeg.ffprobe)

    async def add_files(
        self, raw_paths: Iterable[str], patch: dict[str, Any] | None = None
    ) -> tuple[list[Job], list[dict[str, str]]]:
        self._require_ffmpeg()
        patch = patch or {}
        errors: list[dict[str, str]] = []
        paths: list[Path] = []
        existing = {Path(j.input_path) for j in self.jobs.values() if j.status not in FINISHED}
        for raw in raw_paths:
            try:
                path = self.fs.resolve(raw, kind="file")
            except PathError as exc:
                errors.append({"path": raw, "code": exc.code, "message": exc.message})
                continue
            if path in existing:
                errors.append({"path": raw, "code": "duplicate", "message": "Already in the queue"})
            elif path not in paths:
                paths.append(path)

        probes = await asyncio.gather(*(self._probe(p) for p in paths), return_exceptions=True)
        created: list[Job] = []
        for path, media in zip(paths, probes, strict=True):
            if isinstance(media, BaseException):
                if not isinstance(media, ProbeError | OSError):
                    raise media
                errors.append({"path": str(path), "code": "not_media", "message": str(media)})
                continue
            try:
                created.append(self._create_job(path, media, patch))
            except (OptionsError, PathError, ManagerError) as exc:
                errors.append({"path": str(path), "code": exc.code, "message": exc.message})
            except ValidationError as exc:
                errors.append({"path": str(path), "code": "invalid_options", "message": str(exc)})

        for job in created:
            self.jobs[job.id] = job
            self._emit_job(job)
            self._spawn(self._make_thumbnail(job))
        if created:
            if self.settings.current.auto_start and not self.queue_running:
                self.start_queue()
            else:
                self._emit_queue()
                self._schedule()
        return created, errors

    def _create_job(self, path: Path, media: MediaInfo, patch: dict[str, Any]) -> Job:
        options = self._default_options(media, patch)
        externals = [p for p in find_external_subtitles(path) if self.fs.root_of(p.resolve()) is not None]
        preset = self._preset(options.preset_id)
        if self.settings.current.autoload_subtitles and externals and "subtitle_mode" not in patch:
            # Same behaviour as the classic app: a matching .srt gets burned in
            mode = (
                "burn"
                if preset.can_burn_subtitles and media.video
                else "soft"
                if preset.soft_subtitles
                else None
            )
            if mode:
                candidate = options.model_copy(
                    update={"subtitle_mode": mode, "subtitle_file": str(externals[0])}
                )
                try:
                    options = self._normalize_options(candidate, media)
                except (OptionsError, PathError):
                    options = self._normalize_options(options, media)
            else:
                options = self._normalize_options(options, media)
        else:
            options = self._normalize_options(options, media)

        job = Job(
            id=uuid.uuid4().hex[:12],
            name=path.name,
            input_path=str(path),
            size_bytes=media.size_bytes or path.stat().st_size,
            media=media,
            options=options,
            output_path="",
            external_subtitles=[str(p) for p in externals],
            created_at=time.time(),
        )
        job.output_path = str(self._planned_output(job))
        self._plan_engine(job)
        return job

    def update_options(self, job_id: str, patch: dict[str, Any]) -> Job:
        job = self.get(job_id)
        if job.status in ACTIVE:
            raise ManagerError("job_active", "A job cannot be edited while it is converting", 409)
        try:
            merged = JobOptions.model_validate(_deep_merge(job.options.model_dump(), patch))
        except ValidationError as exc:
            raise ManagerError("invalid_options", str(exc), 422) from exc
        try:
            job.options = self._normalize_options(merged, job.media)
        except (OptionsError, PathError) as exc:
            raise ManagerError(exc.code, exc.message, 422) from exc
        job.output_path = str(self._planned_output(job))
        job.gpu_fallback = False
        self._plan_engine(job)
        self._emit_job(job)
        return job

    def update_many(
        self, job_ids: Iterable[str], patch: dict[str, Any]
    ) -> tuple[list[Job], list[dict[str, str]]]:
        updated, errors = [], []
        for job_id in job_ids:
            try:
                updated.append(self.update_options(job_id, patch))
            except ManagerError as exc:
                name = self.jobs[job_id].name if job_id in self.jobs else job_id
                errors.append({"id": job_id, "name": name, "code": exc.code, "message": exc.message})
        return updated, errors

    def command_preview(self, job_id: str) -> list[str]:
        job = self.get(job_id)
        ffmpeg = self._require_ffmpeg()
        charenc = self._subtitle_charenc(job.options)
        started = job.status in ACTIVE | FINISHED
        output = job.output_path if started else str(self._planned_output(job))
        # Once started, show what really ran (the CPU command after a GPU fallback)
        plan = self._gpu_plan(job) if not started or job.engine == "gpu" else None
        return build_command(
            ffmpeg=Path(ffmpeg.ffmpeg).name,
            media=job.media,
            preset=self.catalog.get(job.options.preset_id),
            options=job.options,
            output=output,
            overwrite=self.settings.current.overwrite,
            subtitle_charenc=charenc,
            can_tonemap=ffmpeg.has_filter("zscale"),
            gpu=plan,
        )

    @staticmethod
    def format_command(argv: list[str]) -> str:
        return shlex.join(argv)

    # ------------------------------------------------------------------ formats

    def preset_views(self) -> list[PresetView]:
        drafts = {key: draft.model_dump() for key, draft in self.custom.drafts().items()}
        return self.catalog.views(drafts)

    def preset_view(self, preset_id: str) -> PresetView:
        return next(view for view in self.preset_views() if view.id == preset_id)

    def _example(self, preset: Preset) -> dict[str, Any]:
        """The command ``preset`` runs on a typical 1080p file, with its encoder."""

        ffmpeg = self.ffmpeg.ffmpeg if self.ffmpeg else "ffmpeg"
        plan = None
        if self.hardware is not None and wants_gpu(
            JobOptions(preset_id=preset.id), self.settings.current.gpu_encoding, preset.accel
        ):
            plan = self.hardware.plan_for(preset)
        argv = build_command(
            ffmpeg=ffmpeg,
            media=SAMPLE_MEDIA,
            preset=preset,
            options=JobOptions(preset_id=preset.id),
            output=f"output{preset.extension}",
            can_tonemap=bool(self.ffmpeg and self.ffmpeg.has_filter("zscale")),
            gpu=plan,
        )
        encoder = plan.encoder.name if plan else preset.video.codec if preset.video else None
        return {
            "command": self.format_command(display_command(argv)),
            "engine": "gpu" if plan else "cpu",
            "encoder": None if encoder == "copy" else encoder,
        }

    def preset_example(self, preset_id: str) -> dict[str, Any]:
        if preset_id not in self.catalog:
            raise ManagerError("unknown_preset", f"Unknown format '{preset_id}'", 404)
        return self._example(self.catalog.get(preset_id))

    def preview_format(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Check an editor draft: errors, warnings and the command it would run."""

        try:
            draft = FormatDraft.model_validate(raw)
        except ValidationError as exc:
            errors = [
                Issue("invalid", str(err["msg"]), {"field": ".".join(str(loc) for loc in err["loc"])})
                for err in exc.errors()
            ]
            return {"ok": False, "errors": [e.to_json() for e in errors], "warnings": []}
        issues = draft_issues(draft)
        if issues:
            return {"ok": False, "errors": [e.to_json() for e in issues], "warnings": []}
        preset = compile_draft(draft, "custom-preview")
        warnings = draft_warnings(draft) + self._gpu_warnings(draft, preset)
        return {
            "ok": True,
            "errors": [],
            "warnings": [w.to_json() for w in warnings],
            "tags": preset.tags,
            "extension": preset.extension,
            **self._example(preset),
        }

    def _gpu_warnings(self, draft: FormatDraft, preset: Preset) -> list[Issue]:
        if draft.accel == "cpu" or draft.video_codec not in ("h264", "hevc", "av1") or self.hardware is None:
            return []
        if not self.hardware.available:
            if draft.accel != "gpu":
                return []
            return [Issue("gpu_none", "No working GPU encoder here, so the CPU encodes it")]
        if self.hardware.plan_for(preset) is None:
            codec = draft.video_codec.upper() + (" 10-bit" if draft.ten_bit else "")
            return [Issue("gpu_codec", f"This GPU cannot encode {codec}, so the CPU does", {"codec": codec})]
        return []

    def save_format(self, preset_id: str | None, draft: FormatDraft) -> PresetView:
        """Create (``preset_id=None``) or replace one of the user's formats."""

        if preset_id is not None and not self.catalog.is_custom(preset_id):
            raise ManagerError("not_custom", "Only your own formats can be edited", 404)
        preset_id = preset_id or new_preset_id()
        try:
            self.custom.save(preset_id, draft)
        except DraftError as exc:
            raise ManagerError("invalid_format", str(exc), 422) from exc
        self._formats_changed(preset_id)
        return self.preset_view(preset_id)

    def delete_format(self, preset_id: str) -> None:
        if not self.catalog.is_custom(preset_id):
            raise ManagerError("not_custom", "Only your own formats can be deleted", 404)
        if any(j.options.preset_id == preset_id and j.status not in FINISHED for j in self.jobs.values()):
            raise ManagerError("preset_in_use", "Files in the queue still use this format", 409)
        self.custom.delete(preset_id)
        if self.settings.current.default_preset == preset_id:
            self.settings.update({"default_preset": "mp4-h264"})
            self.emit_settings()
        self._formats_changed(preset_id)

    def _formats_changed(self, preset_id: str) -> None:
        self.catalog.set_custom(self.custom.presets())
        for job in self.jobs.values():
            if job.options.preset_id == preset_id and job.status == JobStatus.QUEUED:
                job.output_path = str(self._planned_output(job))
                self._plan_engine(job)
                self._emit_job(job)
        self._publish(
            {
                "type": "presets",
                "presets": [view.model_dump() for view in self.preset_views()],
                "hardware": self.hardware_summary(),
            }
        )

    @staticmethod
    def _subtitle_charenc(options: JobOptions) -> str | None:
        if options.subtitle_mode != "none" and options.subtitle_track is None and options.subtitle_file:
            return detect_text_encoding(options.subtitle_file)
        return None

    # ------------------------------------------------------------------ queue

    def start_queue(self) -> None:
        self._require_ffmpeg()
        self.queue_running = True
        for job_id in list(self._paused_by_queue):
            with contextlib.suppress(ManagerError):
                self.resume_job(job_id)
        self._paused_by_queue.clear()
        self._emit_queue()
        self._schedule()

    def pause_queue(self) -> None:
        self.queue_running = False
        for job in self.jobs.values():
            if job.status == JobStatus.RUNNING:
                with contextlib.suppress(ManagerError):
                    self.pause_job(job.id)
                    self._paused_by_queue.add(job.id)
        self._emit_queue()

    def schedule(self) -> None:
        self._schedule()

    def _schedule(self) -> None:
        if self._closing or not self.queue_running:
            return
        active = sum(1 for j in self.jobs.values() if j.status in ACTIVE)
        slots = self.settings.current.concurrency - active
        for job in list(self.jobs.values()):
            if slots <= 0:
                break
            if job.status == JobStatus.QUEUED:
                self._launch(job)
                slots -= 1
        if not any(j.status in ACTIVE or j.status == JobStatus.QUEUED for j in self.jobs.values()):
            self.queue_running = False
            self._emit_queue()
            if self._launched_since_start:
                self._launched_since_start = False
                self._publish({"type": "queue_finished", "counts": self.queue_state()["counts"]})

    def _launch(self, job: Job) -> None:
        self._launched_since_start = True
        self._cancel_requested.discard(job.id)
        job.gpu_fallback = False
        job.status = JobStatus.RUNNING
        job.progress = Progress()
        job.error = None
        job.started_at = time.time()
        job.finished_at = None
        job.output_size = None
        task = asyncio.create_task(self._run(job))
        self._job_tasks[job.id] = task
        task.add_done_callback(functools.partial(self._forget_task, job.id))

    def _forget_task(self, job_id: str, _task: asyncio.Task[None]) -> None:
        self._job_tasks.pop(job_id, None)

    def _command(self, job: Job, output: Path, plan: GpuPlan | None) -> list[str]:
        ffmpeg = self._require_ffmpeg()
        return build_command(
            ffmpeg=ffmpeg.ffmpeg,
            media=job.media,
            preset=self._preset(job.options.preset_id),
            options=job.options,
            output=output,
            overwrite=self.settings.current.overwrite,
            subtitle_charenc=self._subtitle_charenc(job.options),
            can_tonemap=ffmpeg.has_filter("zscale"),
            gpu=plan,
        )

    async def _execute(self, job: Job, argv: list[str], output: Path) -> tuple[RunResult | None, str]:
        """Run one ffmpeg attempt; returns (result, error when it could not even start)."""

        run = FFmpegRun(argv, job.media.duration_s, on_progress=lambda p: self._on_progress(job.id, p))
        if job.id in self._cancel_requested:
            await run.cancel()  # canceled before this attempt started
        self._runs[job.id] = run
        try:
            return await run.run(), ""
        except OSError as exc:
            return None, f"Could not start ffmpeg: {exc}"
        except asyncio.CancelledError:
            _remove_file(output)
            raise
        finally:
            self._runs.pop(job.id, None)

    def _gpu_failed(self, job: Job, result: RunResult | None, output: Path) -> bool:
        if result is None or result.canceled or self._closing or job.id in self._cancel_requested:
            return False
        return result.returncode != 0 or not _file_size(output)

    async def _run(self, job: Job) -> None:
        settings = self.settings.current
        output: Path | None = None
        plan = self._gpu_plan(job)
        try:
            planned = self._planned_output(job)
            self.fs.resolve(str(planned.parent), kind="any", must_exist=False)
            output = unique_path(
                planned, reserved=self._reserved, overwrite=settings.overwrite, avoid={Path(job.input_path)}
            )
            self._reserved.add(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            argv = self._command(job, output, plan)
        except (OptionsError, PathError, ManagerError) as exc:
            self._release(output)
            self._finish(job, JobStatus.FAILED, error=exc.message)
            return
        except OSError as exc:
            self._release(output)
            self._finish(job, JobStatus.FAILED, error=f"Cannot write output: {exc}")
            return

        job.output_path = str(output)
        self._set_engine(job, plan)
        self._emit_job(job)
        self._emit_queue()
        try:
            result, start_error = await self._execute(job, argv, output)
            lines = result.log if result else [start_error]
            if plan is not None and self._gpu_failed(job, result, output):
                # Drivers, session limits or odd frame sizes can defeat the GPU; the CPU always works
                reason = summarize_error(result, "")
                log.warning("GPU encode of %s failed, retrying on the CPU: %s", job.name, reason)
                _remove_file(output)
                job.gpu_fallback = True
                job.progress = Progress()
                self._set_engine(job, None)
                self._emit_job(job)
                gpu_lines = lines
                result, start_error = await self._execute(job, self._command(job, output, None), output)
                lines = [
                    f"{plan.encoder.name} failed, converted on the CPU instead:",
                    *gpu_lines[-6:],
                    "",
                    *(result.log if result else [start_error]),
                ]
        finally:
            self._paused_by_queue.discard(job.id)
            self._release(output)

        self.logs[job.id] = lines
        if (result is not None and result.canceled) or job.id in self._cancel_requested:
            _remove_file(output)
            self._finish(job, JobStatus.CANCELED)
        elif result is not None and result.returncode == 0 and _file_size(output):
            job.progress = job.progress.model_copy(update={"percent": 100.0, "eta_s": 0.0})
            job.output_size = _file_size(output)
            self._finish(job, JobStatus.COMPLETED)
        else:
            if settings.delete_partial:
                _remove_file(output)
            error = (
                summarize_error(result, start_error)
                if result is None or result.returncode
                else "No output produced"
            )
            self._finish(job, JobStatus.FAILED, error=error)

    def _release(self, output: Path | None) -> None:
        if output is not None:
            self._reserved.discard(output)

    def _finish(self, job: Job, status: JobStatus, error: str | None = None) -> None:
        job.status = status
        job.error = error
        job.finished_at = time.time()
        if job.started_at:
            job.progress = job.progress.model_copy(
                update={"elapsed_s": round(job.finished_at - job.started_at, 1)}
            )
        self._dirty.discard(job.id)
        self._emit_job(job)
        self._emit_queue()
        self._schedule()

    def pause_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        run = self._runs.get(job_id)
        if job.status != JobStatus.RUNNING or run is None:
            raise ManagerError("not_running", "Only running jobs can be paused", 409)
        try:
            run.pause()
        except (PauseNotSupportedError, OSError) as exc:
            raise ManagerError("pause_unsupported", str(exc), 409) from exc
        job.status = JobStatus.PAUSED
        self._emit_job(job)
        self._emit_queue()
        return job

    def resume_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        run = self._runs.get(job_id)
        if job.status != JobStatus.PAUSED or run is None:
            raise ManagerError("not_paused", "Only paused jobs can be resumed", 409)
        try:
            run.resume()
        except (PauseNotSupportedError, OSError) as exc:
            raise ManagerError("pause_unsupported", str(exc), 409) from exc
        self._paused_by_queue.discard(job_id)
        job.status = JobStatus.RUNNING
        self._emit_job(job)
        self._emit_queue()
        return job

    async def cancel_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status == JobStatus.QUEUED:
            self._finish(job, JobStatus.CANCELED)
        elif job.status in ACTIVE:
            self._cancel_requested.add(job_id)
            run = self._runs.get(job_id)
            if run is not None:
                await run.cancel()
            task = self._job_tasks.get(job_id)
            if task is not None:
                await asyncio.wait([task], timeout=10)
        else:
            raise ManagerError("not_cancelable", "This job has already finished", 409)
        return job

    def retry_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status not in FINISHED:
            raise ManagerError("not_finished", "Only finished jobs can be converted again", 409)
        job.status = JobStatus.QUEUED
        job.progress = Progress()
        job.error = None
        job.started_at = job.finished_at = None
        job.output_size = None
        job.output_path = str(self._planned_output(job))
        job.gpu_fallback = False
        self._plan_engine(job)
        self.logs.pop(job_id, None)
        self._emit_job(job)
        self._emit_queue()
        self._schedule()
        return job

    async def remove_jobs(self, job_ids: Iterable[str]) -> list[str]:
        removed = []
        for job_id in list(job_ids):
            job = self.jobs.get(job_id)
            if job is None:
                continue
            if job.status in ACTIVE:
                await self.cancel_job(job_id)
            self.jobs.pop(job_id, None)
            self.logs.pop(job_id, None)
            self._dirty.discard(job_id)
            _remove_file(self.thumb_dir / f"{job_id}.jpg")
            removed.append(job_id)
        if removed:
            self._publish({"type": "removed", "ids": removed})
            self._emit_queue()
            self._schedule()
        return removed

    async def clear(self, statuses: Iterable[str]) -> list[str]:
        wanted = {JobStatus(s) for s in statuses} & FINISHED
        return await self.remove_jobs([j.id for j in self.jobs.values() if j.status in wanted])

    def reorder(self, job_ids: list[str]) -> None:
        """Move the given jobs to the front, in the given order."""

        front = {job_id: self.jobs[job_id] for job_id in job_ids if job_id in self.jobs}
        rest = {job_id: job for job_id, job in self.jobs.items() if job_id not in front}
        self.jobs = {**front, **rest}
        self._publish(self.snapshot())

    # ------------------------------------------------------------------ thumbnails

    def thumbnail_path(self, job_id: str) -> Path | None:
        job = self.get(job_id)
        path = self.thumb_dir / f"{job_id}.jpg"
        return path if job.thumbnail and path.is_file() else None

    async def _make_thumbnail(self, job: Job) -> None:
        if self.ffmpeg is None:
            return
        media = job.media
        if media.video is not None:
            seek = min(max(media.duration_s * 0.1, 0.0), 60.0)
            source = ["-ss", f"{seek:.2f}", "-i", job.input_path, "-map", f"0:{media.video.index}"]
        elif media.cover_art_index is not None:
            source = ["-i", job.input_path, "-map", f"0:{media.cover_art_index}"]
        else:
            return
        target = self.thumb_dir / f"{job.id}.jpg"
        vf = "scale=trunc(iw*sar/2)*2:ih,setsar=1,scale=w=480:h=480:force_original_aspect_ratio=decrease"
        argv = [self.ffmpeg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", *source]
        argv += ["-frames:v", "1", "-vf", vf, "-q:v", "4", "-y", str(target)]
        async with self._thumb_limit:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    **POPEN_KWARGS,
                )
                try:
                    await asyncio.wait_for(proc.wait(), 30)
                except (TimeoutError, asyncio.CancelledError):
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(proc.wait(), 5)
                    raise
            except (OSError, TimeoutError) as exc:
                log.debug("Thumbnail failed for %s: %s", job.input_path, exc)
                return
        if proc.returncode == 0 and target.is_file() and job.id in self.jobs:
            job.thumbnail = True
            self._emit_job(job)


def _file_size(path: Path | None) -> int | None:
    try:
        return path.stat().st_size if path else None
    except OSError:
        return None


def _remove_file(path: Path | None) -> None:
    if path is not None:
        with contextlib.suppress(OSError):
            path.unlink()
