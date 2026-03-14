from __future__ import annotations

import argparse
from pathlib import Path

from .convert import FFmpegConverter
from .models import ConversionJob, ConversionPreset
from .probe import probe_media


def main() -> int:
    parser = argparse.ArgumentParser(description="Stallion modern converter MVP")
    parser.add_argument("input", help="Input media file")
    parser.add_argument("output", help="Output media file")
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--preset", default="medium")
    args = parser.parse_args()

    info = probe_media(args.input)

    job = ConversionJob(
        input_path=Path(args.input),
        output_path=Path(args.output),
        preset=ConversionPreset(crf=args.crf, encoder_preset=args.preset),
        id="cli-job-1",
    )

    converter = FFmpegConverter()

    def print_progress(update):
        print(f"[{update.job_id}] {update.percent:6.2f}% speed={update.speed} fps={update.fps}")

    converter.run(job, duration_s=info.duration_s, on_progress=print_progress)
    print(f"Done: {job.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
