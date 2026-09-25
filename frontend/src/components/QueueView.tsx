import {
  CheckCheck,
  ChevronDown,
  Eraser,
  FilePlus2,
  FolderPlus,
  ListChecks,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo } from "react";
import { addFiles, addFolder, clearQueue, removeJobs, toggleQueue } from "@/lib/actions";
import { formatBytes, formatRelative } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import { cn, isMac } from "@/lib/utils";
import { Inspector } from "./inspector/Inspector";
import { JobCard } from "./JobCard";
import { Button } from "./ui/button";
import { Badge, Kbd, ProgressBar } from "./ui/misc";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger, Tip } from "./ui/overlay";

const MOD = isMac ? "⌘" : "Ctrl";

function useQueueShortcuts() {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog'], [role='menu']")) return;
      const store = useStore.getState();
      if (store.view !== "queue" || store.browser) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (mod && key === "o") {
        event.preventDefault();
        void addFiles();
      } else if (mod && key === "a") {
        event.preventDefault();
        store.setSelection(store.order);
      } else if (event.key === "Delete" || (isMac && event.key === "Backspace")) {
        const removable = store.selected.filter((id) => {
          const status = store.jobs[id]?.status;
          return status && status !== "running" && status !== "paused";
        });
        if (removable.length) {
          event.preventDefault();
          void removeJobs(removable);
        }
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (!store.order.length) return;
        event.preventDefault();
        const current = store.order.indexOf(store.selected[store.selected.length - 1] ?? "");
        const next = event.key === "ArrowDown" ? Math.min(store.order.length - 1, current + 1) : Math.max(0, current - 1);
        store.select(store.order[next === -1 ? 0 : next], event.shiftKey ? "range" : "single");
        document.querySelector(`[data-job-id="${store.order[next]}"]`)?.scrollIntoView({ block: "nearest" });
      } else if (event.key === "Escape") {
        store.setSelection([]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

function QueueHeader() {
  const t = useT();
  const lang = useLang();
  const jobs = useStore((s) => s.jobs);
  const order = useStore((s) => s.order);
  const selected = useStore((s) => s.selected);
  const queue = useStore((s) => s.queue);
  const ffmpegReady = useStore((s) => s.system?.ffmpeg.available ?? false);
  const setSelection = useStore((s) => s.setSelection);

  const totalSize = useMemo(() => order.reduce((sum, id) => sum + (jobs[id]?.size_bytes ?? 0), 0), [jobs, order]);
  const { counts, running } = queue;
  const canStart = counts.queued > 0 || counts.paused > 0;
  const label = running ? t("queue.pause") : counts.paused && !counts.queued ? t("queue.resume") : t("queue.start");
  const finished = counts.completed + counts.failed + counts.canceled;
  const removable = selected.filter((id) => jobs[id] && jobs[id].status !== "running" && jobs[id].status !== "paused");

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-4">
      <div className="min-w-0 flex-1">
        <h1 className="text-lg font-semibold tracking-tight text-fg">{t("queue.title")}</h1>
        <p className="text-[13px] text-muted tabular">
          {order.length === 0
            ? t("queue.emptySummary")
            : order.length === 1
              ? t("queue.summaryOne", { size: formatBytes(totalSize, lang) })
              : t("queue.summary", { count: order.length, size: formatBytes(totalSize, lang) })}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex">
          <Button onClick={() => void addFiles()} className="rounded-r-none border-r-0">
            <Plus />
            {t("queue.add")}
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <Button className="rounded-l-none px-2" aria-label={t("queue.addFolder")}>
                <ChevronDown />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuItem icon={<FilePlus2 />} shortcut={`${MOD}+O`} onSelect={() => void addFiles()}>
                {t("queue.add")}
              </MenuItem>
              <MenuItem icon={<FolderPlus />} onSelect={() => void addFolder()}>
                {t("queue.addFolder")}
              </MenuItem>
            </MenuContent>
          </Menu>
        </div>
        <Tip content={ffmpegReady ? null : t("engine.missingHelp")}>
          <span>
            <Button
              variant="primary"
              onClick={() => void toggleQueue()}
              disabled={!ffmpegReady || (!running && !canStart)}
              className="min-w-28"
            >
              {running ? <Pause /> : <Play className="fill-current" />}
              {label}
            </Button>
          </span>
        </Tip>
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t("queue.more")}>
              <MoreHorizontal />
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuItem icon={<ListChecks />} shortcut={`${MOD}+A`} onSelect={() => setSelection(order)}>
              {t("queue.selectAll")}
            </MenuItem>
            <MenuItem
              icon={<Trash2 />}
              shortcut={isMac ? "⌫" : "Del"}
              disabled={!removable.length}
              onSelect={() => void removeJobs(removable)}
            >
              {t("queue.removeSelected")}
            </MenuItem>
            <MenuSeparator />
            <MenuItem icon={<CheckCheck />} disabled={!counts.completed} onSelect={() => void clearQueue(["completed"])}>
              {t("queue.clearCompleted")}
            </MenuItem>
            <MenuItem
              icon={<Eraser />}
              disabled={!finished}
              onSelect={() => void clearQueue(["completed", "failed", "canceled"])}
            >
              {t("queue.clearFinished")}
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>
    </header>
  );
}

function QueueFooter() {
  const t = useT();
  const jobs = useStore((s) => s.jobs);
  const order = useStore((s) => s.order);
  const queue = useStore((s) => s.queue);

  const stats = useMemo(() => {
    let weight = 0;
    let done = 0;
    let remaining = 0;
    let speed = 0;
    let total = 0;
    let completed = 0;
    for (const id of order) {
      const job = jobs[id];
      if (!job || job.status === "canceled" || job.status === "failed") continue;
      const duration = Math.max(job.media.duration_s, 1);
      const percent = job.status === "completed" ? 100 : job.progress.percent;
      total += 1;
      weight += duration;
      done += (duration * percent) / 100;
      if (job.status === "completed") completed += 1;
      else remaining += duration * (1 - percent / 100);
      if (job.status === "running" && job.progress.speed) speed += job.progress.speed;
    }
    return {
      percent: weight ? (done / weight) * 100 : 0,
      eta: speed > 0 ? remaining / speed : null,
      total,
      completed,
    };
  }, [jobs, order]);

  const active = queue.counts.running + queue.counts.paused;
  const status = queue.running ? t("footer.active", { count: active }) : active ? t("footer.paused") : t("footer.idle");

  return (
    <footer className="border-t border-border bg-panel/70 px-6 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="w-12 text-sm font-semibold text-fg tabular">{Math.floor(stats.percent)} %</span>
        <ProgressBar
          value={stats.percent}
          status={queue.running ? "running" : stats.percent >= 100 ? "completed" : "queued"}
          className="h-2 flex-1"
        />
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted tabular">
          <span>{t("footer.counts", { done: stats.completed, total: stats.total })}</span>
          <span className="text-subtle">·</span>
          <span className={cn(queue.running && "text-accent")}>{status}</span>
          {queue.running && stats.eta != null && (
            <>
              <span className="text-subtle">·</span>
              <span>{t("footer.eta", { time: formatRelative(stats.eta) })}</span>
            </>
          )}
        </div>
      </div>
    </footer>
  );
}

function EmptyState() {
  const t = useT();
  const [before, after] = t("empty.shortcut", { keys: "§" }).split("§");
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto p-8">
      <div className="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-dashed border-border-strong bg-surface/60 px-8 py-14 text-center sm:px-12">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 left-1/2 h-72 w-[40rem] -translate-x-1/2 rounded-full bg-brand opacity-[0.13] blur-3xl"
        />
        <div className="relative mx-auto mb-6 grid size-16 place-items-center rounded-2xl bg-brand text-white shadow-[0_16px_40px_-16px_var(--accent)] ring-1 ring-white/20 ring-inset">
          <FilePlus2 className="size-7" />
        </div>
        <h2 className="relative text-2xl font-semibold tracking-tight text-fg">{t("empty.title")}</h2>
        <p className="relative mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-muted">{t("empty.body")}</p>
        <div className="relative mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button variant="primary" size="lg" onClick={() => void addFiles()}>
            <Plus />
            {t("queue.add")}
          </Button>
          <Button size="lg" onClick={() => void addFolder()}>
            <FolderPlus />
            {t("queue.addFolder")}
          </Button>
        </div>
        <div className="relative mt-9 flex flex-wrap justify-center gap-1.5">
          {["MP4", "H.265", "AV1", "WebM", "MKV", "AVI", "MP3", "FLAC", "Opus", "DVD"].map((format) => (
            <Badge key={format}>{format}</Badge>
          ))}
        </div>
        <p className="relative mt-6 flex items-center justify-center gap-1.5 text-xs text-subtle">
          {before}
          <Kbd>{MOD}</Kbd>
          <Kbd>O</Kbd>
          {after}
        </p>
      </div>
    </div>
  );
}

export function QueueView() {
  const order = useStore((s) => s.order);
  useQueueShortcuts();
  const hasJobs = order.length > 0;
  return (
    <div className="flex min-w-0 flex-1">
      <section className="flex min-w-0 flex-1 flex-col">
        <QueueHeader />
        {hasJobs ? (
          <div role="listbox" aria-multiselectable className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            <div className="mx-auto flex max-w-5xl flex-col gap-2.5">
              {order.map((id) => (
                <div key={id} data-job-id={id}>
                  <JobCard id={id} />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState />
        )}
        {hasJobs && <QueueFooter />}
      </section>
      {hasJobs && <Inspector />}
    </div>
  );
}
