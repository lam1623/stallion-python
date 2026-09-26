"""REST endpoints. Everything here requires authentication (see ``app.py``)."""

from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..engine.custom import FormatDraft
from ..engine.presets import PresetView
from ..fonts import list_fonts
from ..fs import Listing, Root
from ..jobs import JobStatus, ManagerError
from ..settings import Settings, SettingsPatch
from .context import AppContext, get_ctx

router = APIRouter(prefix="/api")


class AddJobsRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=2000)
    options: dict[str, Any] = {}


class UpdateJobRequest(BaseModel):
    options: dict[str, Any]


class BulkUpdateRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=2000)
    options: dict[str, Any]


class IdsRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=2000)


class ClearRequest(BaseModel):
    statuses: list[JobStatus] = [JobStatus.COMPLETED]


def _pause_supported() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import psutil  # noqa: F401
    except ImportError:
        return False
    return True


@router.get("/system")
async def system_info(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ff = ctx.ffmpeg
    return {
        "version": __version__,
        "platform": sys.platform,
        "desktop": ctx.config.desktop,
        "pause_supported": _pause_supported(),
        "data_dir": str(ctx.config.data_dir),
        "roots": [r.model_dump() for r in ctx.fs.root_views()],
        "ffmpeg": {
            "available": ff is not None,
            "version": ff.version if ff else None,
            "path": ff.ffmpeg if ff else None,
            "error": ctx.ffmpeg_error,
            # HDR sources are tone-mapped to SDR for 8-bit formats only when zscale exists
            "can_tonemap": bool(ff and ff.has_filter("zscale")),
        },
        # GPU encoders proven by a test encode ("detecting" for the first seconds after start)
        "hardware": ctx.manager.hardware_summary(),
    }


@router.get("/presets")
async def presets(ctx: AppContext = Depends(get_ctx)) -> list[PresetView]:
    return ctx.manager.preset_views()


class PreviewRequest(BaseModel):
    # Checked by the manager, so half-filled editor forms still get a useful answer
    draft: dict[str, Any]


@router.post("/presets/preview")
async def preview_format(body: PreviewRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.preview_format(body.draft)


@router.post("/presets", status_code=status.HTTP_201_CREATED)
async def create_format(draft: FormatDraft, ctx: AppContext = Depends(get_ctx)) -> PresetView:
    return ctx.manager.save_format(None, draft)


@router.put("/presets/{preset_id}")
async def update_format(preset_id: str, draft: FormatDraft, ctx: AppContext = Depends(get_ctx)) -> PresetView:
    return ctx.manager.save_format(preset_id, draft)


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_format(preset_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.manager.delete_format(preset_id)


@router.get("/presets/{preset_id}/command")
async def preset_command(preset_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.preset_example(preset_id)


@router.get("/fonts")
def fonts() -> list[str]:
    return list_fonts()


@router.get("/settings")
async def get_settings(ctx: AppContext = Depends(get_ctx)) -> Settings:
    return ctx.settings.current


@router.put("/settings")
async def put_settings(body: SettingsPatch, ctx: AppContext = Depends(get_ctx)) -> Settings:
    patch = body.model_dump(exclude_unset=True)
    if patch.get("output_dir"):
        patch["output_dir"] = str(ctx.fs.resolve(str(patch["output_dir"]), kind="dir"))
    if "default_preset" in patch and patch["default_preset"] not in ctx.catalog:
        raise ManagerError("unknown_preset", "Unknown format", 422)
    updated = ctx.settings.update(patch)
    ctx.manager.settings_changed()
    return updated


@router.get("/fs/roots")
def fs_roots(ctx: AppContext = Depends(get_ctx)) -> list[Root]:
    return ctx.fs.root_views()


@router.get("/fs/list")
def fs_list(
    path: str,
    show_all: bool = Query(False, alias="all"),
    hidden: bool = False,
    ctx: AppContext = Depends(get_ctx),
) -> Listing:
    return ctx.fs.list_dir(path, show_all=show_all, show_hidden=hidden)


@router.get("/jobs")
async def list_jobs(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    manager = ctx.manager
    return {"jobs": [manager.dump(j) for j in manager.jobs.values()], "queue": manager.queue_state()}


@router.post("/jobs")
async def add_jobs(payload: AddJobsRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    jobs, errors = await ctx.manager.add_files(payload.paths, payload.options)
    return {"jobs": [ctx.manager.dump(j) for j in jobs], "errors": errors}


@router.patch("/jobs")
async def update_jobs(payload: BulkUpdateRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    jobs, errors = ctx.manager.update_many(payload.ids, payload.options)
    return {"jobs": [ctx.manager.dump(j) for j in jobs], "errors": errors}


@router.post("/jobs/remove")
async def remove_jobs(payload: IdsRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"removed": await ctx.manager.remove_jobs(payload.ids)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.get(job_id))


@router.patch("/jobs/{job_id}")
async def update_job(
    job_id: str, payload: UpdateJobRequest, ctx: AppContext = Depends(get_ctx)
) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.update_options(job_id, payload.options))


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.manager.get(job_id)
    await ctx.manager.remove_jobs([job_id])


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.pause_job(job_id))


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.resume_job(job_id))


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(await ctx.manager.cancel_job(job_id))


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.retry_job(job_id))


@router.get("/jobs/{job_id}/log")
async def job_log(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    manager = ctx.manager
    job = manager.get(job_id)
    try:
        command = manager.format_command(manager.command_preview(job_id))
    except Exception as exc:  # invalid options still deserve a readable log view
        command = f"# {exc}"
    return {"log": manager.logs.get(job_id, []), "error": job.error, "command": command}


@router.get("/jobs/{job_id}/thumbnail")
async def job_thumbnail(job_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    path = ctx.manager.thumbnail_path(job_id)
    if path is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/queue/start")
async def queue_start(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ctx.manager.start_queue()
    return ctx.manager.queue_state()


@router.post("/queue/pause")
async def queue_pause(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ctx.manager.pause_queue()
    return ctx.manager.queue_state()


@router.post("/queue/clear")
async def queue_clear(payload: ClearRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"removed": await ctx.manager.clear(payload.statuses)}


@router.post("/queue/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def queue_reorder(payload: IdsRequest, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.manager.reorder(payload.ids)
