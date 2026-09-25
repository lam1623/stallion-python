"""Location of the compiled single-page app (built from ``frontend/``)."""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "dist"
