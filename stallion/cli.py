"""Command line entry point: desktop app, web server and headless batch conversion."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import AppConfig, auth_enabled_from_env, default_data_dir, default_media_roots
from .engine.ffmpeg import FFmpegNotFoundError, discover
from .engine.presets import CATEGORY_ORDER, PresetCatalog
from .fs import FileSystem, filesystem_roots
from .jobs import JobManager, JobStatus, ManagerError
from .settings import Settings, SettingsStore


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ffmpeg", help="Path to the ffmpeg binary (default: $STALLION_FFMPEG or PATH)")
    parser.add_argument("--ffprobe", help="Path to the ffprobe binary (default: $STALLION_FFPROBE or PATH)")
    parser.add_argument(
        "--data-dir", type=Path, help="Where settings and caches live (default: $STALLION_DATA_DIR)"
    )
    parser.add_argument("--log-level", default=os.environ.get("STALLION_LOG_LEVEL", "info"))


def _media_roots(args: argparse.Namespace, desktop: bool) -> list[Path]:
    return [Path(p) for p in args.media_root] if args.media_root else default_media_roots(desktop)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stallion", description="Modern FFmpeg video and audio converter.")
    parser.add_argument("--version", action="version", version=f"stallion {__version__}")
    sub = parser.add_subparsers(dest="command")

    desktop = sub.add_parser("desktop", help="open the desktop app (default)")
    desktop.add_argument(
        "--browser", action="store_true", help="use the web browser instead of a native window"
    )
    desktop.add_argument("--media-root", action="append", default=[], help="restrict browsing to this folder")
    _common(desktop)

    serve = sub.add_parser("serve", help="run the web UI/API server (Docker, NAS, headless)")
    serve.add_argument("--host", default=os.environ.get("STALLION_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("STALLION_PORT", "8000")))
    serve.add_argument(
        "--token", default=os.environ.get("STALLION_TOKEN"), help="access token (default: random)"
    )
    serve.add_argument("--no-auth", action="store_true", help="disable authentication (trusted proxies only)")
    serve.add_argument(
        "--media-root", action="append", default=[], help="folder the UI may access (repeatable)"
    )
    serve.add_argument("--open", action="store_true", help="open the UI in the default browser")
    _common(serve)

    convert = sub.add_parser("convert", help="convert files from the terminal")
    convert.add_argument("inputs", nargs="+", type=Path)
    convert.add_argument("-p", "--preset", default="mp4-h264", help="format id (see `stallion presets`)")
    convert.add_argument("-o", "--out-dir", type=Path, help="output folder (default: next to each input)")
    convert.add_argument("-q", "--quality", type=int, help="CRF or bitrate in kbps, depending on the format")
    convert.add_argument("--max-height", type=int, help="limit the short side, e.g. 1080 or 720")
    convert.add_argument("--speed", choices=["fast", "balanced", "quality"], default="balanced")
    convert.add_argument("--subtitles", choices=["auto", "none", "soft", "burn"], default="auto")
    convert.add_argument("-j", "--jobs", type=int, default=1, help="parallel conversions")
    convert.add_argument("--overwrite", action="store_true", help="replace existing output files")
    _common(convert)

    presets = sub.add_parser("presets", help="list the available formats")
    presets.add_argument("--ffmpeg", help=argparse.SUPPRESS)
    presets.add_argument("--ffprobe", help=argparse.SUPPRESS)
    return parser


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _config(args: argparse.Namespace, *, desktop: bool) -> AppConfig:
    return AppConfig(
        media_roots=_media_roots(args, desktop),
        data_dir=args.data_dir or default_data_dir(),
        ffmpeg_bin=args.ffmpeg,
        ffprobe_bin=args.ffprobe,
    )


def cmd_desktop(args: argparse.Namespace) -> int:
    from .desktop import run_desktop

    _setup_logging(args.log_level)
    return run_desktop(_config(args, desktop=True), prefer_browser=args.browser)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    _setup_logging(args.log_level)
    config = _config(args, desktop=False)
    config.host, config.port = args.host, args.port
    auth = auth_enabled_from_env() and not args.no_auth
    config.auth_token = (args.token or secrets.token_urlsafe(24)) if auth else None

    shown_host = "localhost" if args.host in ("0.0.0.0", "::", "") else args.host
    url = f"http://{shown_host}:{args.port}/"
    if config.auth_token:
        url += f"auth?token={config.auth_token}"
    else:
        logging.getLogger("stallion").warning("Authentication is DISABLED: only use behind a trusted proxy")
    print(f"\n  Stallion {__version__} → {url}\n", flush=True)
    if args.open:
        import webbrowser

        webbrowser.open(url)
    uvicorn.run(
        create_app(config),
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
    return 0


def cmd_presets(args: argparse.Namespace) -> int:
    try:
        ffmpeg = discover(args.ffmpeg, args.ffprobe)
    except FFmpegNotFoundError:
        ffmpeg = None
    views = PresetCatalog.builtin(ffmpeg).views()
    for category in CATEGORY_ORDER:
        items = [v for v in views if v.category == category]
        if not items:
            continue
        print(f"\n{category.upper()}")
        for view in items:
            flag = "" if view.available else f"  (missing: {', '.join(view.missing_encoders)})"
            print(f"  {view.id:<12} {view.name['en']:<22} {view.description['en']}{flag}")
    return 0


def _fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60:02d}:{rest % 60:02d}"


async def _convert(args: argparse.Namespace) -> int:
    try:
        ffmpeg = discover(args.ffmpeg, args.ffprobe)
    except FFmpegNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    catalog = PresetCatalog.builtin(ffmpeg)
    if args.preset not in catalog:
        print(f"error: unknown preset '{args.preset}' (see `stallion presets`)", file=sys.stderr)
        return 2

    settings = Settings(
        output_dir=str(args.out_dir.resolve()) if args.out_dir else None,
        concurrency=max(1, min(args.jobs, 8)),
        overwrite=args.overwrite,
        autoload_subtitles=args.subtitles != "none",
        default_preset=args.preset,
    )
    manager = JobManager(
        ffmpeg=ffmpeg,
        catalog=catalog,
        settings=SettingsStore(None, settings),
        fs=FileSystem(filesystem_roots()),
        cache_dir=(args.data_dir or default_data_dir()) / "cache",
    )
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    patch: dict[str, Any] = {"preset_id": args.preset, "speed": args.speed}
    if args.quality is not None:
        patch["quality"] = args.quality
    if args.max_height is not None:
        patch["max_height"] = args.max_height
    if args.subtitles == "none":
        patch["subtitle_mode"] = "none"

    await manager.start()
    events = manager.subscribe()
    try:
        jobs, errors = await manager.add_files([str(p.resolve()) for p in args.inputs], patch)
        for error in errors:
            print(f"skip  {error['path']}: {error['message']}", file=sys.stderr)
        if args.subtitles in ("soft", "burn"):
            for job in jobs:
                update: dict[str, Any] = {"subtitle_mode": args.subtitles}
                if not job.options.subtitle_file:
                    if not job.media.subtitles:
                        continue
                    update["subtitle_track"] = 0  # no matching file: first embedded track
                try:
                    manager.update_options(job.id, update)
                except ManagerError as exc:
                    print(f"warn  {job.name}: {exc.message}", file=sys.stderr)
        if not jobs:
            return 1
        manager.start_queue()
        interactive = sys.stdout.isatty()
        while True:
            event = await events.get()
            if event["type"] == "progress" and interactive:
                parts = []
                for item in event["items"]:
                    active = manager.jobs.get(item["id"])
                    if active:
                        p = item["progress"]
                        speed = f"{p['speed']:.1f}x" if p.get("speed") else "…"
                        parts.append(
                            f"{active.name[:32]} {p['percent']:5.1f}% {speed} ETA {_fmt_time(p.get('eta_s'))}"
                        )
                print("\r\033[K" + " | ".join(parts), end="", flush=True)
            elif event["type"] == "job":
                job_data = event["job"]
                status = job_data["status"]
                if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED):
                    if interactive:
                        print("\r\033[K", end="")
                    detail = (
                        job_data["output_path"]
                        if status == JobStatus.COMPLETED
                        else job_data.get("error") or ""
                    )
                    print(f"{status:<9} {job_data['name']} → {detail}", flush=True)
            elif event["type"] == "queue_finished":
                counts = event["counts"]
                print(f"\nDone: {counts['completed']} completed, {counts['failed']} failed.")
                return 0 if counts["failed"] == 0 and counts["canceled"] == 0 else 1
    finally:
        manager.unsubscribe(events)
        await manager.shutdown()


def cmd_convert(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING)
    try:
        return asyncio.run(_convert(args))
    except KeyboardInterrupt:
        print("\nCanceled.", file=sys.stderr)
        return 130


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["desktop", *(argv or sys.argv[1:])])
    handlers = {"desktop": cmd_desktop, "serve": cmd_serve, "convert": cmd_convert, "presets": cmd_presets}
    return handlers[args.command](args)
