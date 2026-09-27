import { formatRelative } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useQueueProgress } from "@/lib/queueStats";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { ActivityMonitor } from "../monitor/ActivityMonitor";
import { ProgressBar } from "../ui/misc";

/** Proposal C: one slim line with the machine load and the queue's overall progress. */
export function StatusBar() {
  const t = useT();
  const queue = useStore((s) => s.queue);
  const progress = useQueueProgress();
  const paused = queue.counts.running + queue.counts.paused;
  const status = queue.running
    ? t("footer.active", { count: queue.counts.running })
    : paused
      ? t("footer.paused")
      : t("footer.idle");

  return (
    <footer className="flex h-11 shrink-0 items-center gap-3 border-t border-border bg-panel px-4 text-xs text-muted">
      <ActivityMonitor />
      <span aria-hidden className="h-4 w-px shrink-0 bg-border-strong" />
      <span className={cn("truncate", queue.running && "font-medium text-accent")}>{status}</span>
      <span className="hidden truncate tabular md:inline">
        {t("footer.counts", { done: progress.completed, total: progress.total })}
      </span>
      <span className="flex-1" />
      {queue.running && progress.eta != null && (
        <span className="hidden shrink-0 tabular sm:inline">{t("footer.eta", { time: formatRelative(progress.eta) })}</span>
      )}
      <span className="w-10 shrink-0 text-right font-semibold text-fg tabular">{Math.floor(progress.percent)} %</span>
      <ProgressBar
        value={progress.percent}
        status={queue.running ? "running" : progress.percent >= 100 ? "completed" : "queued"}
        className="w-24 shrink-0 lg:w-56"
      />
    </footer>
  );
}
