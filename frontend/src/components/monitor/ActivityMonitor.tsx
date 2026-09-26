import { ChevronUp, Cpu, Gpu } from "lucide-react";
import { Popover } from "radix-ui";
import { type ReactNode, useState } from "react";
import { saveSettings } from "@/lib/actions";
import { formatBytes } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { SystemStats } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Segmented } from "../ui/controls";
import { CoreBars, HistoryChart, Meter, percent } from "./charts";

function Divider() {
  return <span aria-hidden className="h-4 w-px shrink-0 bg-border-strong" />;
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle">{children}</h3>;
}

/** Opens the full monitor from any trigger (a plain button, so it can take the ref). */
export function MonitorPopover({
  children,
  side = "top",
  align = "start",
}: {
  children: ReactNode;
  side?: "top" | "bottom";
  align?: "start" | "end";
}) {
  const stats = useStore((s) => s.stats);
  const [open, setOpen] = useState(false);
  return (
    <Popover.Root open={open && !!stats} onOpenChange={setOpen}>
      <Popover.Trigger asChild>{children}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side={side}
          align={align}
          sideOffset={10}
          collisionPadding={16}
          // Opening the panel must not jump focus (and a tooltip) onto the first core
          onOpenAutoFocus={(event) => event.preventDefault()}
          className="z-50 w-[min(900px,calc(100vw-32px))] overflow-hidden rounded-2xl border border-border-strong bg-panel shadow-2xl outline-none animate-fade-in"
        >
          {stats && <MonitorPanel stats={stats} />}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Compact readout for the status bar; opens the full monitor above it. */
export function ActivityMonitor({ className }: { className?: string }) {
  const t = useT();
  const lang = useLang();
  const stats = useStore((s) => s.stats);
  if (!stats) return null;
  const { cpu, gpu, memory } = stats;

  return (
    <MonitorPopover>
      <button
        aria-label={t("mon.title")}
        className={cn(
          "flex h-8 shrink-0 items-center gap-3 rounded-lg px-2.5 text-xs text-muted outline-none transition hover:bg-elevated hover:text-fg focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-elevated data-[state=open]:text-fg",
          className,
        )}
      >
        <span className="flex items-center gap-2">
          <CoreBars cores={cpu.cores} size="sm" />
          <span className="font-semibold text-fg tabular">CPU {percent(cpu.total)}</span>
        </span>
        {gpu && (
          <>
            <Divider />
            <span className="flex items-center gap-2">
              {gpu.util != null && <Meter value={gpu.util} color="gpu" label={t("mon.gpuLoad")} className="h-1.5 w-9" />}
              <span className="font-semibold text-fg tabular">GPU {percent(gpu.util)}</span>
            </span>
          </>
        )}
        <Divider />
        <span className="hidden tabular xl:inline">
          RAM {t("mon.of", { used: formatBytes(memory.used, lang), total: formatBytes(memory.total, lang) })}
        </span>
        <ChevronUp className="size-3.5 text-subtle" />
      </button>
    </MonitorPopover>
  );
}

export function MonitorPanel({ stats }: { stats: SystemStats }) {
  const t = useT();
  const lang = useLang();
  const history = useStore((s) => s.history);
  const jobs = useStore((s) => s.jobs);
  const concurrency = useStore((s) => s.settings?.concurrency ?? 1);
  const { cpu, gpu, memory, processes } = stats;
  const times = history.map((h) => h.at);
  const gpuPoints = history.filter((h) => h.gpu != null);
  const memoryShare = memory.total ? (memory.used / memory.total) * 100 : 0;

  return (
    <div className="grid md:grid-cols-[1.35fr_1fr_1.15fr]">
      <section className="min-w-0 space-y-4 p-5" aria-labelledby="mon-cpu">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="mon-cpu" className="flex items-center gap-2 text-sm font-semibold text-fg">
              <Cpu className="size-4 text-subtle" />
              CPU
            </h2>
            <p className="mt-0.5 truncate text-xs text-muted" title={cpu.model}>
              {cpu.model} · {t("mon.cores", { count: cpu.cores.length })}
            </p>
          </div>
          <span className="shrink-0 whitespace-nowrap text-3xl font-semibold tracking-tight text-fg">{percent(cpu.total)}</span>
        </div>
        <CoreBars cores={cpu.cores} size="lg" />
        <HistoryChart values={history.map((h) => h.cpu)} times={times} color="cpu" label="CPU" />
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted">{t("mon.memory")}</span>
            <span className="font-medium text-fg tabular">
              {t("mon.of", { used: formatBytes(memory.used, lang), total: formatBytes(memory.total, lang) })}
            </span>
          </div>
          <Meter value={memoryShare} color="mem" label={t("mon.memory")} />
        </div>
      </section>

      <section className="min-w-0 space-y-4 border-t border-border p-5 md:border-l md:border-t-0" aria-labelledby="mon-gpu">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="mon-gpu" className="flex items-center gap-2 text-sm font-semibold text-fg">
              <Gpu className="size-4 text-subtle" />
              GPU
            </h2>
            {gpu && (
              <p className="mt-0.5 truncate text-xs text-muted" title={gpu.name}>
                {gpu.name}
              </p>
            )}
          </div>
          {gpu?.util != null && <span className="shrink-0 whitespace-nowrap text-3xl font-semibold tracking-tight text-fg">{percent(gpu.util)}</span>}
        </div>
        {!gpu && <p className="rounded-xl bg-elevated/70 p-3 text-xs leading-relaxed text-muted">{t("mon.noGpu")}</p>}
        {gpu && gpu.util == null && (
          <p className="rounded-xl bg-elevated/70 p-3 text-xs leading-relaxed text-muted">{t("mon.noGpuStats")}</p>
        )}
        {gpu && (
          <div className="space-y-3">
            {gpu.encoder != null && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-muted">{t("mon.encoder")}</span>
                  <span className="font-medium text-fg tabular">{percent(gpu.encoder)}</span>
                </div>
                <Meter value={gpu.encoder} color="gpu" label={t("mon.encoder")} />
              </div>
            )}
            {gpu.decoder != null && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-muted">{t("mon.decoder")}</span>
                  <span className="font-medium text-fg tabular">{percent(gpu.decoder)}</span>
                </div>
                <Meter value={gpu.decoder} color="gpu" label={t("mon.decoder")} />
              </div>
            )}
            {gpu.memory_total ? (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-muted">{t("mon.vram")}</span>
                  <span className="font-medium text-fg tabular">
                    {t("mon.of", {
                      used: formatBytes(gpu.memory_used ?? 0, lang),
                      total: formatBytes(gpu.memory_total, lang),
                    })}
                  </span>
                </div>
                <Meter value={((gpu.memory_used ?? 0) / gpu.memory_total) * 100} color="gpu" label={t("mon.vram")} />
              </div>
            ) : null}
            {gpuPoints.length > 1 && (
              <HistoryChart
                values={gpuPoints.map((h) => h.gpu ?? 0)}
                times={gpuPoints.map((h) => h.at)}
                color="gpu"
                label="GPU"
              />
            )}
          </div>
        )}
      </section>

      <section className="flex min-w-0 flex-col gap-3 border-t border-border p-5 md:border-l md:border-t-0">
        <SectionLabel>{t("mon.processes")}</SectionLabel>
        {processes.length === 0 && <p className="text-xs text-muted">{t("mon.idle")}</p>}
        {processes.map((process) => {
          const job = jobs[process.job_id];
          const gpu = job?.engine === "gpu";
          return (
            <div key={process.job_id} className="space-y-1 rounded-xl border border-border bg-surface px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[13px] font-semibold text-fg">{job?.name ?? process.job_id}</span>
                <span
                  className={cn(
                    "shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-bold text-fg",
                    gpu ? "bg-viz-gpu/15" : "bg-viz-cpu/15",
                  )}
                >
                  {gpu ? "GPU" : "CPU"}
                </span>
              </div>
              <p className="truncate text-xs text-muted tabular">
                {job?.encoder && `${job.encoder} · `}
                CPU {percent(process.cpu)} · {t("mon.threads", { count: process.threads })}
                {job?.progress.speed ? ` · ${job.progress.speed.toLocaleString(lang, { maximumFractionDigits: 1 })}×` : ""}
              </p>
            </div>
          );
        })}
        <div className="mt-auto flex items-center justify-between gap-3 border-t border-border pt-3 text-xs">
          <span className="text-muted">{t("mon.concurrency")}</span>
          <Segmented<string>
            size="sm"
            value={String(concurrency)}
            onValueChange={(value) => void saveSettings({ concurrency: Number(value) })}
            options={["1", "2", "3", "4"].map((value) => ({ value, label: value }))}
          />
        </div>
      </section>
    </div>
  );
}
