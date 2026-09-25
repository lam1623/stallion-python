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
import { localized, useLang, useT } from "@/lib/i18n";
import { nativeApi } from "@/lib/native";
import { usePreset, useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { ProgressBar, StatusBadge } from "./ui/misc";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger, Tip } from "./ui/overlay";

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
          <Icon className="size-6" />
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
  const stop = (event: MouseEvent | KeyboardEvent) => event.stopPropagation();

  return (
    <div className="-mr-1 -mt-0.5 flex shrink-0 items-center gap-0.5" onClick={stop} onKeyDown={stop}>
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

export const JobCard = memo(function JobCard({ id }: { id: string }) {
  const job = useStore((s) => s.jobs[id]);
  const selected = useStore((s) => s.selected.includes(id));
  const select = useStore((s) => s.select);
  const preset = usePreset(job?.options.preset_id);
  const lang = useLang();
  const t = useT();
  if (!job) return null;

  const { status, progress, media } = job;
  const active = status === "running" || status === "paused";
  const indeterminate = status === "running" && !media.duration_s;
  const percent = status === "completed" ? 100 : progress.percent;

  const onSelect = (event: MouseEvent | KeyboardEvent) => {
    select(id, event.shiftKey ? "range" : event.metaKey || event.ctrlKey ? "toggle" : "single");
  };

  let trailing: ReactNode = null;
  if (status === "running" && progress.eta_s != null) trailing = t("job.eta", { time: formatRelative(progress.eta_s) });
  else if (active) trailing = t("job.elapsed", { time: formatDuration(progress.elapsed_s) });
  else if (status === "completed") trailing = `${formatBytes(job.size_bytes, lang)} → ${formatBytes(job.output_size, lang)}`;

  return (
    <div
      role="option"
      tabIndex={0}
      aria-selected={selected}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(event);
        }
      }}
      className={cn(
        "group relative flex cursor-default select-none gap-4 rounded-xl border p-3 outline-none transition-[background-color,border-color,box-shadow] duration-150 focus-visible:ring-2 focus-visible:ring-ring",
        selected
          ? "border-accent/50 bg-accent-soft shadow-[0_0_0_1px_var(--accent-soft)]"
          : "border-border bg-surface shadow-card hover:border-border-strong",
      )}
    >
      <div className="relative">
        <Thumbnail job={job} className="w-32 sm:w-36" />
        <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-px text-[10px] font-semibold text-white tabular backdrop-blur-sm">
          {formatDuration(media.duration_s)}
        </span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col py-0.5">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-medium text-fg" title={job.input_path}>
              {job.name}
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-1.5 text-xs text-muted">
              <span className="truncate">{mediaSummary(media, lang).join(" · ")}</span>
              <ArrowRight className="size-3 shrink-0 text-subtle" />
              <span className="shrink-0 font-medium text-fg/85">
                {preset ? localized(preset.name, lang) : job.options.preset_id}
              </span>
              {job.options.subtitle_mode !== "none" && (
                <Tip content={t(job.options.subtitle_mode === "burn" ? "sub.chip.burn" : "sub.chip.soft")}>
                  <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-elevated px-1.5 py-0.5 text-[10px] font-semibold text-muted">
                    <Captions className="size-3" />
                    {job.options.subtitle_mode === "burn" ? "CC" : "SUB"}
                  </span>
                </Tip>
              )}
            </div>
          </div>
          <StatusBadge status={status} className="mt-0.5" />
          <JobActions job={job} />
        </div>

        <div className="mt-auto pt-3">
          {status === "queued" && (
            <p className="truncate text-xs text-subtle">{t("job.waiting", { name: basename(job.output_path) })}</p>
          )}
          {(active || status === "completed") && (
            <>
              <ProgressBar value={percent} status={status} indeterminate={indeterminate} />
              <div className="mt-1.5 flex items-center gap-3 text-xs text-muted tabular">
                <span className="font-semibold text-fg">
                  {indeterminate
                    ? formatDuration(progress.out_time_s)
                    : `${formatNumber(percent, lang, percent < 10 && percent > 0 ? 1 : 0)} %`}
                </span>
                {active && progress.speed != null && <span>{formatSpeed(progress.speed, lang)}</span>}
                {active && progress.size_bytes != null && <span>{formatBytes(progress.size_bytes, lang)}</span>}
                {status === "completed" && (
                  <span className="min-w-0 truncate">{t("job.savedAs", { name: basename(job.output_path) })}</span>
                )}
                {trailing && <span className="ml-auto shrink-0">{trailing}</span>}
              </div>
            </>
          )}
          {status === "failed" && <p className="line-clamp-2 text-xs leading-relaxed text-danger">{job.error}</p>}
          {status === "canceled" && <p className="text-xs text-subtle">{t("job.canceledNote")}</p>}
        </div>
      </div>
    </div>
  );
});
