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
        self.root.geometry("1240x760")
        self.root.minsize(980, 640)

        self.converter = FFmpegConverter()
        self.jobs: dict[str, UiJob] = {}
        self.job_order: list[str] = []
        self.events: queue.Queue[tuple[str, str, dict]] = queue.Queue()
        self.is_running = False

        self._build_styles()
        self._build_menu()
        self._build_layout()

        self.root.after(80, self._drain_events)

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        self.root.configure(bg="#101214")
        style.configure("Root.TFrame", background="#101214")
        style.configure("Card.TFrame", background="#171a1f")
        style.configure("CardHeader.TLabel", background="#171a1f", foreground="#f5f5f5", font=("Segoe UI", 16, "bold"))
        style.configure("Muted.TLabel", background="#171a1f", foreground="#98a2b3")
        style.configure("Form.TLabel", background="#171a1f", foreground="#d0d5dd", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background="#101214", foreground="#d0d5dd")
        style.configure("TFrame", background="#101214")
        style.configure("TLabelframe", background="#171a1f", bordercolor="#2a2f38", lightcolor="#2a2f38", darkcolor="#2a2f38")
        style.configure("TLabelframe.Label", background="#171a1f", foreground="#f2f4f7", font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", focusthickness=0)
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.configure("TButton", padding=(10, 6))
        style.configure("Treeview", background="#111318", foreground="#e5e7eb", fieldbackground="#111318", bordercolor="#2a2f38", rowheight=30)
        style.configure("Treeview.Heading", background="#1f2430", foreground="#f8fafc", relief="flat")
        style.map("Treeview", background=[("selected", "#1d4ed8")])
        style.configure("Horizontal.TProgressbar", troughcolor="#1f2430", background="#22c55e", bordercolor="#1f2430", lightcolor="#22c55e", darkcolor="#22c55e")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open input file", command=self._pick_input)
        file_menu.add_command(label="Save output as", command=self._pick_output)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        queue_menu = tk.Menu(menubar, tearoff=0)
        queue_menu.add_command(label="Add job", command=self.add_job)
        queue_menu.add_command(label="Start queue", command=self.start_queue)
        queue_menu.add_command(label="Clear completed", command=self.clear_completed)
        menubar.add_cascade(label="Queue", menu=queue_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_layout(self) -> None:
        wrapper = ttk.Frame(self.root, style="Root.TFrame", padding=14)
        wrapper.pack(fill=tk.BOTH, expand=True)

        card = ttk.Frame(wrapper, style="Card.TFrame", padding=14)
        card.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card, text="Stallion Modern", style="CardHeader.TLabel").pack(anchor=tk.W)
        ttk.Label(
            card,
            text="Cross-platform FFmpeg queue with live progress (desktop + web-ready backend)",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 10))

        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(toolbar, text="Open", command=self._pick_input).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Output", command=self._pick_output).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Add to queue", style="Accent.TButton", command=self.add_job).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Start", style="Accent.TButton", command=self.start_queue).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Clear completed", command=self.clear_completed).pack(side=tk.LEFT, padx=(8, 0))

        paned = ttk.Panedwindow(card, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, style="Card.TFrame", padding=8)
        right = ttk.Frame(paned, style="Card.TFrame", padding=8)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        queue_frame = ttk.LabelFrame(left, text="Jobs", padding=8)
        queue_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("input", "output", "status", "progress", "speed", "fps")
        self.tree = ttk.Treeview(queue_frame, columns=columns, show="headings")
        heads = {
            "input": "Input",
            "output": "Output",
            "status": "Status",
            "progress": "Progress",
            "speed": "Speed",
            "fps": "FPS",
        }
        widths = {"input": 220, "output": 220, "status": 110, "progress": 100, "speed": 100, "fps": 80}
        for c in columns:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)

        config_frame = ttk.LabelFrame(right, text="Job details", padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True)

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.crf_var = tk.IntVar(value=23)
        self.preset_var = tk.StringVar(value="medium")

        self._field(config_frame, "Input file", self.in_var, self._pick_input, row=0)
        self._field(config_frame, "Output file", self.out_var, self._pick_output, row=1)

        ttk.Label(config_frame, text="CRF", style="Form.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 4))
        ttk.Spinbox(config_frame, from_=14, to=40, textvariable=self.crf_var, width=8).grid(row=3, column=0, sticky="w")

        ttk.Label(config_frame, text="Preset", style="Form.TLabel").grid(row=2, column=1, sticky="w", pady=(10, 4))
        preset_combo = ttk.Combobox(
            config_frame,
            textvariable=self.preset_var,
            values=("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"),
            state="readonly",
            width=14,
        )
        preset_combo.grid(row=3, column=1, sticky="w")

        ttk.Button(config_frame, text="Add to queue", style="Accent.TButton", command=self.add_job).grid(
            row=3, column=2, sticky="e"
        )

        stats = ttk.LabelFrame(right, text="Statistics", padding=10)
        stats.pack(fill=tk.X, pady=(8, 0))
        self.status_var = tk.StringVar(value="Ready")
        self.jobs_var = tk.StringVar(value="Jobs: 0")
        self.done_var = tk.StringVar(value="Completed: 0")
        ttk.Label(stats, textvariable=self.status_var).pack(anchor=tk.W)
        ttk.Label(stats, textvariable=self.jobs_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(stats, textvariable=self.done_var).pack(anchor=tk.W, pady=(4, 0))

        bottom = ttk.Frame(card, style="Card.TFrame")
        bottom.pack(fill=tk.X, pady=(10, 0))
        self.total_progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.total_progress.pack(fill=tk.X)

        config_frame.columnconfigure(0, weight=1)
        config_frame.columnconfigure(1, weight=1)
        config_frame.columnconfigure(2, weight=1)

    def _field(self, parent: ttk.Frame, label: str, var: tk.StringVar, command, row: int) -> None:
        ttk.Label(parent, text=label, style="Form.TLabel").grid(row=row * 2, column=0, columnspan=3, sticky="w", pady=(2, 4))
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row * 2 + 1, column=0, columnspan=2, sticky="ew")
        ttk.Button(parent, text="Browse", command=command).grid(row=row * 2 + 1, column=2, sticky="e", padx=(8, 0))

    def _show_about(self) -> None:
        messagebox.showinfo("About", "Stallion Modern\nFFmpeg-based cross-platform converter")

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
        self.jobs_var.set(f"Jobs: {len(self.job_order)}")

    def start_queue(self) -> None:
        if self.is_running:
            return

        pending = [jid for jid in self.job_order if self.jobs[jid].job.status.value in {"queued", "failed"}]
        if not pending:
            self.status_var.set("No pending jobs")
            return

        self.is_running = True
        self.status_var.set("Converting...")
        threading.Thread(target=self._run_queue_worker, args=(pending,), daemon=True).start()

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
        changed = False
        while True:
            try:
                event_type, job_id, payload = self.events.get_nowait()
            except queue.Empty:
                break

            changed = True
            if event_type == "status":
                values = list(self.tree.item(job_id, "values"))
                values[2] = payload["status"]
                self.tree.item(job_id, values=values)
                if payload["status"] == "failed":
                    self.status_var.set(f"Error in {job_id}: {payload.get('error', 'unknown')}" )
            elif event_type == "progress":
                values = list(self.tree.item(job_id, "values"))
                values[3] = f"{payload['percent']:.1f}%"
                values[4] = payload["speed"]
                values[5] = payload["fps"]
                self.tree.item(job_id, values=values)
            elif event_type == "queue_done":
                self.is_running = False
                self.status_var.set("Queue finished")

        if changed:
            self._refresh_metrics()

        self.root.after(80, self._drain_events)

    def _refresh_metrics(self) -> None:
        if not self.job_order:
            self.total_progress["value"] = 0
            self.jobs_var.set("Jobs: 0")
            self.done_var.set("Completed: 0")
            return

        total_progress = 0.0
        completed = 0

        for jid in self.job_order:
            values = self.tree.item(jid, "values")
            try:
                total_progress += float(str(values[3]).replace("%", ""))
            except ValueError:
                pass
            if values[2] == "completed":
                completed += 1

        self.total_progress["value"] = total_progress / len(self.job_order)
        self.jobs_var.set(f"Jobs: {len(self.job_order)}")
        self.done_var.set(f"Completed: {completed}")

    def clear_completed(self) -> None:
        completed_ids = [jid for jid in self.job_order if self.tree.item(jid, "values")[2] == "completed"]
        for jid in completed_ids:
            self.tree.delete(jid)
            self.job_order.remove(jid)
            self.jobs.pop(jid, None)

        self._refresh_metrics()
        self.status_var.set(f"Removed {len(completed_ids)} completed jobs")


def main() -> int:
    root = tk.Tk()
    StallionModernApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
