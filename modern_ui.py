from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.convert import ConversionError, FFmpegConverter
from core.models import ConversionJob, ConversionPreset
from core.probe import ProbeError, probe_media


@dataclass
class UiJob:
    job: ConversionJob
    duration_s: float


class StallionModernApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Stallion Modern")
        self.root.geometry("1080x640")

        self.converter = FFmpegConverter()
        self.jobs: dict[str, UiJob] = {}
        self.job_order: list[str] = []
        self.events: queue.Queue[tuple[str, str, dict]] = queue.Queue()
        self.is_running = False

        self._build_styles()
        self._build_layout()

        self.root.after(100, self._drain_events)

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", foreground="#5f6368")

    def _build_layout(self) -> None:
        wrapper = ttk.Frame(self.root, padding=16)
        wrapper.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(wrapper)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Stallion · Modern Converter", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="Cross-platform UI (Windows/Linux/macOS) with queue and real-time progress",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(4, 10))

        controls = ttk.LabelFrame(wrapper, text="Conversion", padding=12)
        controls.pack(fill=tk.X, pady=(0, 12))

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.crf_var = tk.IntVar(value=23)
        self.preset_var = tk.StringVar(value="medium")

        self._field_with_button(controls, "Input file", self.in_var, self._pick_input).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=4
        )
        self._field_with_button(controls, "Output file", self.out_var, self._pick_output).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=4
        )

        ttk.Label(controls, text="CRF").grid(row=2, column=0, sticky="w", pady=(8, 2))
        ttk.Spinbox(controls, from_=14, to=40, textvariable=self.crf_var, width=8).grid(
            row=3, column=0, sticky="w"
        )

        ttk.Label(controls, text="Preset").grid(row=2, column=1, sticky="w", pady=(8, 2))
        preset_combo = ttk.Combobox(
            controls,
            textvariable=self.preset_var,
            values=("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"),
            state="readonly",
            width=14,
        )
        preset_combo.grid(row=3, column=1, sticky="w")

        ttk.Button(controls, text="Add to queue", command=self.add_job).grid(row=3, column=2, sticky="e")

        for col in range(3):
            controls.columnconfigure(col, weight=1)

        queue_frame = ttk.LabelFrame(wrapper, text="Job queue", padding=12)
        queue_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("input", "output", "status", "progress", "speed", "fps")
        self.tree = ttk.Treeview(queue_frame, columns=columns, show="headings", height=14)
        heads = {
            "input": "Input",
            "output": "Output",
            "status": "Status",
            "progress": "Progress",
            "speed": "Speed",
            "fps": "FPS",
        }
        widths = {"input": 200, "output": 220, "status": 110, "progress": 110, "speed": 90, "fps": 70}
        for c in columns:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)

        footer = ttk.Frame(wrapper)
        footer.pack(fill=tk.X, pady=(12, 0))

        self.total_progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
        self.total_progress.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status_var).pack(side=tk.LEFT, padx=(12, 0))

        actions = ttk.Frame(wrapper)
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(actions, text="Start queue", command=self.start_queue).pack(side=tk.LEFT)
        ttk.Button(actions, text="Clear completed", command=self.clear_completed).pack(side=tk.LEFT, padx=8)

    def _field_with_button(
        self, parent: ttk.Frame, label: str, var: tk.StringVar, command
    ) -> ttk.Frame:
        frame = ttk.Frame(parent)
        ttk.Label(frame, text=label).pack(anchor=tk.W)
        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse", command=command).pack(side=tk.LEFT, padx=(8, 0))
        return frame

    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(title="Select video")
        if path:
            self.in_var.set(path)
            if not self.out_var.get():
                source = Path(path)
                self.out_var.set(str(source.with_name(f"{source.stem}_converted.mp4")))

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save output",
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.out_var.set(path)

    def add_job(self) -> None:
        input_path = Path(self.in_var.get().strip())
        output_path = Path(self.out_var.get().strip())

        if not input_path.exists():
            messagebox.showerror("Error", "Select a valid input file")
            return
        if not output_path:
            messagebox.showerror("Error", "Select an output path")
            return

        job_id = f"job-{len(self.job_order) + 1}"
        preset = ConversionPreset(crf=self.crf_var.get(), encoder_preset=self.preset_var.get())
        job = ConversionJob(input_path=input_path, output_path=output_path, preset=preset, id=job_id)

        try:
            info = probe_media(input_path)
        except ProbeError as exc:
            messagebox.showerror("ffprobe error", str(exc))
            return

        self.jobs[job_id] = UiJob(job=job, duration_s=info.duration_s)
        self.job_order.append(job_id)

        self.tree.insert(
            "",
            tk.END,
            iid=job_id,
            values=(input_path.name, output_path.name, "queued", "0.0%", "-", "-"),
        )
        self.status_var.set(f"{len(self.job_order)} job(s) queued")

    def start_queue(self) -> None:
        if self.is_running:
            return
        pending = [jid for jid in self.job_order if self.jobs[jid].job.status.value in {"queued", "failed"}]
        if not pending:
            self.status_var.set("No pending jobs")
            return

        self.is_running = True
        self.status_var.set("Converting...")
        thread = threading.Thread(target=self._run_queue_worker, args=(pending,), daemon=True)
        thread.start()

    def _run_queue_worker(self, pending_ids: list[str]) -> None:
        for job_id in pending_ids:
            uijob = self.jobs[job_id]
            self.events.put(("status", job_id, {"status": "running"}))

            try:
                self.converter.run(
                    uijob.job,
                    duration_s=uijob.duration_s,
                    on_progress=lambda update, jid=job_id: self.events.put(
                        (
                            "progress",
                            jid,
                            {
                                "percent": update.percent,
                                "speed": update.speed or "-",
                                "fps": "-" if update.fps is None else f"{update.fps:.1f}",
                            },
                        )
                    ),
                )
                self.events.put(("status", job_id, {"status": "completed"}))
            except ConversionError as exc:
                self.events.put(("status", job_id, {"status": "failed", "error": str(exc)}))

        self.events.put(("queue_done", "", {}))

    def _drain_events(self) -> None:
        processed = False
        while True:
            try:
                event_type, job_id, payload = self.events.get_nowait()
            except queue.Empty:
                break

            processed = True
            if event_type == "status":
                status = payload["status"]
                cur = list(self.tree.item(job_id, "values"))
                cur[2] = status
                self.tree.item(job_id, values=cur)
                if status == "failed" and payload.get("error"):
                    self.status_var.set(f"Error in {job_id}: {payload['error']}")
            elif event_type == "progress":
                cur = list(self.tree.item(job_id, "values"))
                cur[3] = f"{payload['percent']:.1f}%"
                cur[4] = payload["speed"]
                cur[5] = payload["fps"]
                self.tree.item(job_id, values=cur)
            elif event_type == "queue_done":
                self.is_running = False
                self.status_var.set("Queue finished")

        if processed:
            self._refresh_total_progress()

        self.root.after(100, self._drain_events)

    def _refresh_total_progress(self) -> None:
        if not self.job_order:
            self.total_progress["value"] = 0
            return

        total = 0.0
        for jid in self.job_order:
            values = self.tree.item(jid, "values")
            txt = str(values[3]).replace("%", "")
            try:
                total += float(txt)
            except ValueError:
                total += 0.0
        self.total_progress["value"] = total / len(self.job_order)

    def clear_completed(self) -> None:
        to_remove = []
        for jid in self.job_order:
            status = self.tree.item(jid, "values")[2]
            if status == "completed":
                to_remove.append(jid)

        for jid in to_remove:
            self.tree.delete(jid)
            self.job_order.remove(jid)
            self.jobs.pop(jid, None)

        self._refresh_total_progress()
        self.status_var.set(f"Removed {len(to_remove)} completed jobs")


def main() -> int:
    root = tk.Tk()
    StallionModernApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
