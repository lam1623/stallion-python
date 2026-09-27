import { ChevronDown, Cpu, Gpu, MemoryStick } from "lucide-react";
import type { ReactNode } from "react";
import { formatBytes, formatRelative } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { useQueueProgress } from "@/lib/queueStats";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { MonitorPopover } from "../monitor/ActivityMonitor";
import { CoreBars, HistoryChart, Meter, percent } from "../monitor/charts";
import { ProgressBar } from "../ui/misc";

function Label({ icon, children, aside }: { icon?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3">
      <span className="flex min-w-0 items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.07em] text-subtle [&_svg]:size-3.5 [&_svg]:shrink-0">
        {icon}
        <span className="truncate">{children}</span>
      </span>
      {aside}
    </div>
  );
}

function Big({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("whitespace-nowrap text-[26px] font-semibold leading-none tracking-tight text-fg", className)}>
      {children}
    </div>
  );
}

function Caption({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <p className="truncate text-xs text-muted" title={title}>
      {children}
    </p>
  );
}

const CELL = "flex min-w-0 flex-col gap-2.5 bg-surface px-5 py-3 @4xl:py-4";

/** Proposal A: queue progress and machine load above the list, readable at a glance. */
export function ActivityStrip() {
  const t = useT();
  const lang = useLang();
  const stats = useStore((s) => s.stats);
  const history = useStore((s) => s.history);
  const running = useStore((s) => s.queue.running);
  const progress = useQueueProgress();
  const cpu = stats?.cpu;
  const gpu = stats?.gpu ?? null;
  const memory = stats?.memory;
  const converting = stats?.processes.length ?? progress.running;

  return (
    <div className="@container shrink-0 px-6 pt-4">
      <section
        aria-label={t("mon.title")}
        className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border shadow-card @4xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1.9fr)_minmax(0,0.9fr)_minmax(0,1fr)]"
      >
        <div className={CELL}>
          <Label>{t("act.progress")}</Label>
          <div className="flex min-w-0 items-baseline gap-2.5">
            <Big>{Math.floor(progress.percent)} %</Big>
            {running && progress.eta != null && (
              <span className="truncate text-xs text-muted tabular">
                {t("act.left", { time: formatRelative(progress.eta) })}
              </span>
            )}
          </div>
          <ProgressBar
            value={progress.percent}
            status={running ? "running" : progress.percent >= 100 ? "completed" : "queued"}
            className="h-2"
          />
          <Caption>
            {t("act.summary", { done: progress.completed, total: progress.total })}
            {progress.running > 0 && ` · ${t("act.converting", { count: progress.running })}`}
          </Caption>
        </div>

        <div className="@container/cpu flex min-w-0 items-center gap-5 bg-surface px-5 py-3 @4xl:py-4">
          <div className="flex w-28 shrink-0 flex-col gap-2.5">
            <Label icon={<Cpu />}>CPU</Label>
            <Big>{percent(cpu?.total)}</Big>
            <Caption title={cpu?.model}>
              {cpu ? t("mon.cores", { count: cpu.cores.length }) : "—"}
              {converting > 0 && ` · ${t("act.converting", { count: converting })}`}
            </Caption>
          </div>
          {cpu && <CoreBars cores={cpu.cores} size="md" />}
          {history.length > 1 && (
            <HistoryChart
              compact
              values={history.map((h) => h.cpu)}
              times={history.map((h) => h.at)}
              color="cpu"
              label="CPU"
              className="hidden min-w-0 flex-1 @[22rem]/cpu:block"
            />
          )}
        </div>

        <div className={CELL}>
          <Label icon={<MemoryStick />}>{t("mon.memory")}</Label>
          <div className="flex items-baseline gap-1.5 whitespace-nowrap">
            <span className="text-lg font-semibold leading-none text-fg">{formatBytes(memory?.used, lang)}</span>
            {memory && <span className="truncate text-xs text-muted">{t("act.ofTotal", { total: formatBytes(memory.total, lang) })}</span>}
          </div>
          <Meter value={memory?.total ? (memory.used / memory.total) * 100 : 0} color="mem" label={t("mon.memory")} />
        </div>

        <div className={CELL}>
          <Label
            icon={<Gpu />}
            aside={
              <MonitorPopover side="bottom" align="end">
                <button className="-my-1 -mr-1.5 flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-accent outline-none transition hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-accent-soft">
                  {t("mon.details")}
                  <ChevronDown className="size-3.5" />
                </button>
              </MonitorPopover>
            }
          >
            GPU
          </Label>
          {!gpu ? (
            <p className="text-xs leading-relaxed text-muted">{t("act.gpuNone")}</p>
          ) : (
            <>
              <span className="text-lg font-semibold leading-none text-fg">
                {gpu.util == null ? <span className="text-sm font-medium text-muted">{t("act.gpuNoLoad")}</span> : percent(gpu.util)}
              </span>
              {gpu.util != null && <Meter value={gpu.util} color="gpu" label={t("mon.gpuLoad")} />}
              <Caption title={gpu.name}>
                {gpu.encoder != null && `${t("act.encoder", { value: percent(gpu.encoder) })} · `}
                {gpu.name}
              </Caption>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
