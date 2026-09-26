import {
  ArrowRight,
  Captions,
  FileText,
  FolderOpen,
  Film,
  MoreHorizontal,
  Music,
  Pause,
  Play,
  RotateCcw,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { memo, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { jobAction, openPath, removeJobs } from "@/lib/actions";
import { thumbnailUrl } from "@/lib/api";
import {
  basename,
  dirname,
  formatBytes,
  formatDuration,
  formatNumber,
  formatRelative,
  formatSpeed,
  mediaSummary,
} from "@/lib/format";
import { type Lang, localized, type Translator, useLang, useT } from "@/lib/i18n";
import { nativeApi } from "@/lib/native";
import type { QueueLayout } from "@/lib/prefs";
import { usePreset, useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { ProgressBar, StatusBadge } from "../ui/misc";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger, Tip } from "../ui/overlay";

/*
 * One grid per row, sized by the width of the list (container queries), so columns line up
 * across rows and give way from the right as space runs out.
 *   cards: thumb · file · [format] · status · [result · time] · actions
 *   table: thumb · file · [source] · [format] · status · progress · [speed · result · remaining] · actions
 */
export const GRID: Record<QueueLayout, string> = {
  cards:
    "grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)_5.5rem] @3xl:grid-cols-[7rem_minmax(0,1.4fr)_minmax(0,1.1fr)_minmax(0,1.5fr)_5.5rem] @6xl:grid-cols-[7rem_minmax(0,1.4fr)_minmax(0,1.1fr)_minmax(0,1.5fr)_7.5rem_8.5rem_5.5rem]",
  table:
    "grid-cols-[4rem_minmax(0,1.6fr)_7.5rem_minmax(0,1.3fr)_5.5rem] @3xl:grid-cols-[4rem_minmax(0,1.6fr)_minmax(0,1.1fr)_7.5rem_minmax(0,1.3fr)_5.5rem] @5xl:grid-cols-[4rem_minmax(0,1.6fr)_minmax(0,1.3fr)_minmax(0,1.1fr)_7.5rem_minmax(0,1.3fr)_5.5rem] @6xl:grid-cols-[4rem_minmax(0,1.6fr)_minmax(0,1.3fr)_minmax(0,1.1fr)_7.5rem_minmax(0,1.3fr)_5.5rem_6.5rem_7.5rem_5.5rem]",
};

// Optional columns: hidden cells take no grid track
export const SHOW = {
  format: "hidden @3xl:flex",
  source: "hidden @5xl:block",
  wide: "hidden @6xl:block",
  narrow: "@6xl:hidden",
};

export function Thumbnail({ job, className }: { job: Job; className?: string }) {
  const url = thumbnailUrl(job);
  const [failed, setFailed] = useState(false);
  const Icon = job.media.video ? Film : Music;
  return (
    <div
      className={cn(
        "relative aspect-video shrink-0 overflow-hidden rounded-lg bg-elevated ring-1 ring-border ring-inset",
        className,
      )}
    >
      {url && !failed ? (
        <img
          src={url}
          alt=""
          loading="lazy"
          draggable={false}
          onError={() => setFailed(true)}
          className="size-full object-cover"
        />
      ) : (
        <div className="grid size-full place-items-center bg-gradient-to-br from-elevated to-surface text-subtle">
          <Icon className="size-1/3 max-h-6 max-w-6" />
        </div>
      )}
    </div>
  );
}

function IconAction({ tip, onClick, children }: { tip: string; onClick: () => void; children: ReactNode }) {
  return (
    <Tip content={tip}>
      <Button variant="ghost" size="icon-sm" aria-label={tip} onClick={onClick}>
        {children}
      </Button>
    </Tip>
  );
}

function JobActions({ job }: { job: Job }) {
  const t = useT();
  const pauseSupported = useStore((s) => s.system?.pause_supported ?? true);
  const setInspectorTab = useStore((s) => s.setInspectorTab);
  const setSelection = useStore((s) => s.setSelection);
  const native = nativeApi() !== null;
  const { status } = job;
  const active = status === "running" || status === "paused";
  const finished = status === "completed" || status === "failed" || status === "canceled";
  // Buttons act on this file only: never change the selection or open the panel
  const stop = (event: MouseEvent | KeyboardEvent) => event.stopPropagation();

  return (
    <div className="flex items-center justify-end gap-0.5" onClick={stop} onKeyDown={stop}>
      {status === "running" && pauseSupported && (
        <IconAction tip={t("job.pause")} onClick={() => jobAction(job.id, "pause")}>
          <Pause />
        </IconAction>
      )}
      {status === "paused" && (
        <IconAction tip={t("job.resume")} onClick={() => jobAction(job.id, "resume")}>
          <Play />
        </IconAction>
      )}
      {active && (
        <IconAction tip={t("job.cancel")} onClick={() => jobAction(job.id, "cancel")}>
          <Square />
        </IconAction>
      )}
      {(status === "failed" || status === "canceled") && (
        <IconAction tip={t("job.retry")} onClick={() => jobAction(job.id, "retry")}>
          <RotateCcw />
        </IconAction>
      )}
      {status === "completed" && native && (
        <IconAction tip={t("job.openFolder")} onClick={() => openPath(dirname(job.output_path))}>
          <FolderOpen />
        </IconAction>
      )}
      {status === "queued" && (
        <IconAction tip={t("job.remove")} onClick={() => removeJobs([job.id])}>
          <X />
        </IconAction>
      )}
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={t("job.actions")}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          {status === "completed" && native && (
            <>
              <MenuItem icon={<Play />} onSelect={() => openPath(job.output_path)}>
                {t("job.openFile")}
              </MenuItem>
              <MenuItem icon={<FolderOpen />} onSelect={() => openPath(dirname(job.output_path))}>
                {t("job.openFolder")}
              </MenuItem>
            </>
          )}
          {finished && (
            <MenuItem icon={<RotateCcw />} onSelect={() => jobAction(job.id, "retry")}>
              {t("job.retry")}
            </MenuItem>
          )}
          <MenuItem
            icon={<FileText />}
            onSelect={() => {
              setSelection([job.id]);
              setInspectorTab("log");
            }}
          >
            {t("job.viewLog")}
          </MenuItem>
          <MenuSeparator />
          <MenuItem icon={<Trash2 />} danger onSelect={() => removeJobs([job.id])}>
            {t("job.remove")}
          </MenuItem>
        </MenuContent>
      </Menu>
    </div>
  );
}

function percentOf(job: Job): number {
  return job.status === "completed" ? 100 : job.progress.percent;
}

function percentLabel(job: Job, lang: Lang): string {
  const value = percentOf(job);
  return `${formatNumber(value, lang, value < 10 && value > 0 ? 1 : 0)} %`;
}

/** Output size so far, or the final size against the source. */
function result(job: Job, t: Translator, lang: Lang): { main: string; note: string | null; title?: string } {
  if (job.status === "running" || job.status === "paused") {
    return job.progress.size_bytes
      ? { main: formatBytes(job.progress.size_bytes, lang), note: t("job.soFar") }
      : { main: "—", note: null };
  }
  if (job.status === "completed" && job.output_size) {
    const change = job.size_bytes ? (job.output_size / job.size_bytes - 1) * 100 : 0;
    const amount = `${formatNumber(Math.abs(change), lang, Math.abs(change) < 10 ? 1 : 0)} %`;
    return {
      main: formatBytes(job.output_size, lang),
      note: `${change < 0 ? "−" : "+"}${amount}`,
      title: t(change < 0 ? "job.smaller" : "job.larger", { percent: amount }),
    };
  }
  return { main: "—", note: null };
}

/** Remaining time while converting, conversion time once done. */
function timing(job: Job, t: Translator, lang: Lang): { main: string; note: string | null } {
  const { progress, status } = job;
  const rate = [progress.speed ? formatSpeed(progress.speed, lang) : null, progress.fps ? `${Math.round(progress.fps)} fps` : null]
    .filter(Boolean)
    .join(" · ");
  if (status === "running") {
    return {
      main: progress.eta_s != null ? t("job.eta", { time: formatRelative(progress.eta_s) }) : formatDuration(progress.elapsed_s),
      note: rate || null,
    };
  }
  if (status === "paused") return { main: t("job.elapsed", { time: formatDuration(progress.elapsed_s) }), note: null };
  if (status === "completed" && progress.elapsed_s) {
    const average = job.media.duration_s ? job.media.duration_s / progress.elapsed_s : null;
    return { main: formatDuration(progress.elapsed_s), note: average ? formatSpeed(average, lang) : null };
  }
  return { main: "—", note: null };
}

function SubtitleChip({ job }: { job: Job }) {
  const t = useT();
  if (job.options.subtitle_mode === "none") return null;
  const burn = job.options.subtitle_mode === "burn";
  return (
    <Tip content={t(burn ? "sub.chip.burn" : "sub.chip.soft")}>
      <span
        aria-label={t(burn ? "sub.chip.burn" : "sub.chip.soft")}
        className="inline-grid size-5 shrink-0 place-items-center rounded-md bg-elevated text-muted"
      >
        <Captions className="size-3" />
      </span>
    </Tip>
  );
}

/** Status line under the badge: what happens next, the error, or (when the time column is hidden) speed and ETA. */
function StatusDetail({ job }: { job: Job }) {
  const t = useT();
  const lang = useLang();
  const { status } = job;
  if (status === "queued") {
    return <p className="truncate text-xs text-subtle">{t("job.waiting", { name: basename(job.output_path) })}</p>;
  }
  if (status === "failed") {
    return (
      <p className="truncate text-xs text-danger" title={job.error ?? undefined}>
        {job.error}
      </p>
    );
  }
  if (status === "canceled") return <p className="truncate text-xs text-subtle">{t("job.canceledNote")}</p>;
  const indeterminate = status === "running" && !job.media.duration_s;
  const time = timing(job, t, lang);
  return (
    <div className="space-y-1.5">
      <ProgressBar value={percentOf(job)} status={status} indeterminate={indeterminate} />
      <p className={cn("flex gap-2 truncate text-xs text-muted tabular", SHOW.narrow)}>
        {status === "completed" ? (
          <span className="truncate">{t("job.savedAs", { name: basename(job.output_path) })}</span>
        ) : (
          <>
            {time.note && <span>{time.note}</span>}
            <span className="ml-auto shrink-0">{time.main}</span>
          </>
        )}
      </p>
    </div>
  );
}

function Stacked({ main, note, title, className }: { main: string; note: string | null; title?: string; className?: string }) {
  return (
    <div className={cn("min-w-0 text-[13px] tabular", className)} title={title}>
      <div className="truncate text-fg">{main}</div>
      {note && <div className="mt-1 truncate text-xs text-muted">{note}</div>}
    </div>
  );
}

export const JobRow = memo(function JobRow({ id, layout }: { id: string; layout: QueueLayout }) {
  const job = useStore((s) => s.jobs[id]);
  const selected = useStore((s) => s.selected.includes(id));
  const preset = usePreset(job?.options.preset_id);
  const lang = useLang();
  const t = useT();
  if (!job) return null;

  const { status, media } = job;
  const table = layout === "table";
  const presetName = preset ? localized(preset.name, lang) : job.options.preset_id;
  const summary = mediaSummary(media, lang);
  const size = result(job, t, lang);
  const time = timing(job, t, lang);

  const onSelect = (event: MouseEvent | KeyboardEvent) => {
    const store = useStore.getState();
    const mode = event.shiftKey ? "range" : event.metaKey || event.ctrlKey ? "toggle" : "single";
    // Picking the only selected file again closes its panel
    if (mode === "single" && store.selected.length === 1 && store.selected[0] === id) store.setSelection([]);
    else store.select(id, mode);
  };

  return (
    <div
      role="option"
      tabIndex={0}
      data-job-id={id}
      aria-selected={selected}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(event);
        }
      }}
      className={cn(
        "group grid cursor-default select-none items-center outline-none transition-[background-color,border-color,box-shadow] duration-150",
        GRID[layout],
        table
          ? "h-14 gap-x-4 border-b border-border px-6 focus-visible:bg-elevated/70"
          : "gap-x-5 rounded-xl border px-3 py-2.5 focus-visible:ring-2 focus-visible:ring-ring",
        table &&
          (selected ? "bg-accent-soft shadow-[inset_3px_0_0_var(--accent)]" : "hover:bg-elevated/50"),
        !table &&
          (selected
            ? "border-accent/50 bg-accent-soft shadow-[0_0_0_1px_var(--accent-soft)]"
            : "border-border bg-surface shadow-card hover:border-border-strong"),
      )}
    >
      <div className="relative">
        <Thumbnail job={job} className={table ? "w-16 rounded-md" : "w-full"} />
        {!table && (
          <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-px text-[10px] font-semibold text-white tabular backdrop-blur-sm">
            {formatDuration(media.duration_s)}
          </span>
        )}
      </div>

      <div className="min-w-0">
        <div className={cn("truncate font-medium text-fg", table ? "text-[13px]" : "text-sm")} title={job.input_path}>
          {job.name}
        </div>
        {!table && (
          <div className="mt-1 flex min-w-0 items-center gap-1.5 text-xs text-muted">
            <span className="truncate">{summary.join(" · ")}</span>
            {/* The format column is hidden on narrow lists: show it here instead */}
            <span className="flex min-w-0 max-w-[55%] shrink-0 items-center gap-1.5 @3xl:hidden">
              <ArrowRight className="size-3 shrink-0 text-subtle" />
              <span className="truncate font-medium text-fg/85">{presetName}</span>
            </span>
          </div>
        )}
      </div>

      {table && <div className={cn("truncate text-[13px] text-muted", SHOW.source)}>{summary.join(" · ")}</div>}

      <div className={cn("min-w-0 items-center gap-2", SHOW.format)}>
        {!table && <ArrowRight className="size-3.5 shrink-0 text-subtle" />}
        <span className="truncate text-[13px] font-medium text-fg/90">{presetName}</span>
        <SubtitleChip job={job} />
      </div>

      {table ? (
        <>
          <div className="min-w-0">
            <StatusBadge status={status} />
          </div>
          <div className="flex min-w-0 items-center gap-2.5">
            {status === "failed" ? (
              <span className="truncate text-xs text-danger" title={job.error ?? undefined}>
                {job.error}
              </span>
            ) : status === "queued" || status === "canceled" ? (
              <span className="text-xs text-subtle">—</span>
            ) : (
              <>
                <ProgressBar
                  value={percentOf(job)}
                  status={status}
                  indeterminate={status === "running" && !media.duration_s}
                  className="flex-1"
                />
                <span className="w-11 shrink-0 text-right text-xs text-muted tabular">{percentLabel(job, lang)}</span>
              </>
            )}
          </div>
          <div className={cn("truncate text-[13px] text-muted tabular", SHOW.wide)}>
            {status === "running" && job.progress.speed ? formatSpeed(job.progress.speed, lang) : "—"}
          </div>
          <div className={cn("truncate text-[13px] text-fg tabular", SHOW.wide)} title={size.title}>
            {size.main}
          </div>
          <div className={cn("truncate text-[13px] text-muted tabular", SHOW.wide)}>
            {status === "completed" && job.progress.elapsed_s
              ? t("job.doneIn", { time: formatDuration(job.progress.elapsed_s) })
              : status === "running" || status === "paused"
                ? time.main
                : "—"}
          </div>
        </>
      ) : (
        <>
          <div className="min-w-0 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <StatusBadge status={status} />
              {(status === "running" || status === "paused" || status === "completed") && (
                <span className="text-xs font-semibold text-fg tabular">
                  {status === "running" && !media.duration_s
                    ? formatDuration(job.progress.out_time_s)
                    : percentLabel(job, lang)}
                </span>
              )}
            </div>
            <StatusDetail job={job} />
          </div>
          <Stacked {...size} className={SHOW.wide} />
          <Stacked {...time} className={SHOW.wide} />
        </>
      )}

      <JobActions job={job} />
    </div>
  );
});

/** Column titles, on the same grid as the rows. */
export function JobColumns({ layout }: { layout: QueueLayout }) {
  const t = useT();
  const table = layout === "table";
  return (
    <div
      aria-hidden
      className={cn(
        "grid items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.07em] text-subtle [&>*]:truncate",
        GRID[layout],
        table
          ? "sticky top-0 z-10 h-10 gap-x-4 border-b border-border bg-panel px-6"
          : "gap-x-5 px-3 pb-1 pt-4",
      )}
    >
      <span />
      <span>{t("col.file")}</span>
      {table && <span className={SHOW.source}>{t("col.source")}</span>}
      <span className={SHOW.format}>{table ? t("col.formatShort") : t("col.format")}</span>
      <span>{t("col.status")}</span>
      {table && <span>{t("col.progress")}</span>}
      {table && <span className={SHOW.wide}>{t("col.speed")}</span>}
      <span className={SHOW.wide}>{t("col.result")}</span>
      <span className={SHOW.wide}>{table ? t("col.remaining") : t("col.time")}</span>
      <span />
    </div>
  );
}
