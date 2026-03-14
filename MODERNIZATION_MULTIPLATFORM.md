# Stallion modernization plan (functional + visual + cross-platform)

## Goal
Modernize Stallion to:
1. improve visual UX,
2. improve functionality (conversion engine, queue, presets, reliability),
3. run on Linux, Windows, and macOS.

## Main recommendation
Adopt a **Modern Frontend + Python Backend** architecture:
- **UI:** Tauri + React (or Vue) + Tailwind + component library (shadcn/ui or similar).
- **Engine:** Python 3.12+ with `ffmpeg`/`ffprobe` (instead of mencoder/mplayer).
- **Packaging:** Tauri bundler per platform.

> This route enables a major visual upgrade while preserving Python conversion logic.

---

## Proposed architecture

### 1) Core layer (Python)
A UI-agnostic `core/` package with:
- `probe.py`: metadata via `ffprobe`.
- `jobs.py`: conversion job model (Job, state, progress, ETA).
- `convert.py`: `ffmpeg` execution per job.
- `presets.py`: versioned presets (JSON/YAML).
- `events.py`: progress/state events.

### 2) App API layer
A stable bridge between UI and Python:
- start queue,
- pause/resume/cancel,
- read presets,
- inspect file,
- query global state.

### 3) UI layer (Tauri)
Recommended screens:
- Conversion queue,
- Per-file details,
- Presets,
- Settings,
- History/Logs.

Suggested UX:
- dark/light theme,
- drag & drop,
- per-item and total progress,
- notifications,
- keyboard shortcuts,
- responsive layout.

---

## Priority functional improvements

### Conversion
- Migrate to `ffmpeg` + `ffprobe`.
- Support modern codecs (H.264/H.265/AV1, AAC/Opus).
- Quality control via CRF/preset.
- Robust audio/subtitle track selection.

### Productivity
- Configurable concurrent queue (N workers).
- Automatic retry policies.
- Resume batches and persist session.
- Editable presets with validation.

### Reliability
- Per-job structured error logs.
- Better speed and ETA metrics.
- Tests for metadata parsing and command building.

---

## Phased plan

### Phase 1 — Foundations (1–2 weeks)
- Migrate to Python 3.12+
- Build UI-independent `core/` package.
- Introduce `ffprobe` and `ffmpeg` wrappers.
- Define event/state contract.

### Phase 2 — Cross-platform MVP (2–4 weeks)
- Create base Tauri app with queue screen.
- Implement bridge with basic commands.
- Show real-time progress.
- Package internal builds for Linux/Windows.

### Phase 3 — Visual + functional upgrade (2–4 weeks)
- Design system (components + visual tokens).
- Preset editor.
- History/logs and better error UX.
- Drag & drop and advanced batch mode.

### Phase 4 — Stabilization & release (1–2 weeks)
- Cross-platform QA (Linux/Windows/macOS).
- Performance and memory tuning.
- Semantic versioning + changelog.
- Installer release.

---

## Suggested stack

### Backend
- Python 3.12+
- `pydantic` (validation/models)
- `typer` (optional internal CLI)
- `pytest` + `pytest-cov`
- `ruff` + `black` + `mypy`

### Frontend
- Tauri 2
- React + TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query (if using remote state)
- Zustand (simple local state)

### CI/CD
- GitHub Actions
- Build matrix: ubuntu-latest, windows-latest, macos-latest
- Release artifacts per platform

---

## Risks and mitigations
- **Risk:** Tauri ↔ Python bridge complexity.
  - **Mitigation:** simple versioned API contract + integration tests.
- **Risk:** ffmpeg differences across platforms.
  - **Mitigation:** binary discovery + smoke tests by OS.
- **Risk:** large migration blast radius.
  - **Mitigation:** incremental phases with early MVP.

---

## First concrete deliverable (initial sprint)
1. Implement `core/probe.py` metadata extraction with `ffprobe`.
2. Implement `core/convert.py` for one conversion job with parsed progress.
3. Expose `start_job` through bridge/API.
4. Build minimal UI with job list and progress bar.

This provides a modern, visually improved, and truly cross-platform foundation.
