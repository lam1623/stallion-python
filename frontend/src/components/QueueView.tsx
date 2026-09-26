import {
  CheckCheck,
  ChevronDown,
  Eraser,
  FilePlus2,
  FolderPlus,
  LayoutList,
  ListChecks,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Rows3,
  Search,
  SearchX,
  Trash2,
  X,
} from "lucide-react";
import { type MouseEvent, useEffect, useMemo } from "react";
import { useShallow } from "zustand/react/shallow";
import { addFiles, addFolder, clearQueue, removeJobs, toggleQueue } from "@/lib/actions";
import { formatBytes } from "@/lib/format";
import { type TranslationKey, useLang, useT } from "@/lib/i18n";
import { type QueueFilter, type QueueLayout, useStore, visibleOrder } from "@/lib/store";
import { cn, isMac } from "@/lib/utils";
import { InspectorDrawer, InspectorSheet } from "./inspector/Inspector";
import { ActivityStrip } from "./queue/ActivityStrip";
import { JobColumns, JobRow } from "./queue/JobRow";
import { StatusBar } from "./queue/StatusBar";
import { Button } from "./ui/button";
import { Segmented } from "./ui/controls";
import { Badge, Kbd } from "./ui/misc";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger, Tip } from "./ui/overlay";

const MOD = isMac ? "⌘" : "Ctrl";
const SEARCH_ID = "queue-search";

function useQueueShortcuts() {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Open dropdowns and dialogs handle Escape/arrows themselves and mark the event as handled
      if (event.defaultPrevented) return;
      const store = useStore.getState();
      if (store.view !== "queue" || store.browser || !store.order.length) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (mod && key === "f") {
        event.preventDefault();
        const input = document.getElementById(SEARCH_ID) as HTMLInputElement | null;
        input?.focus();
        input?.select();
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog'], [role='menu']")) return;
      // Inside the options panel only Escape (close) belongs to the queue
      if (target?.closest("[data-inspector]") && event.key !== "Escape") return;
      const shown = visibleOrder(store);
      if (mod && key === "o") {
        event.preventDefault();
        void addFiles();
      } else if (mod && key === "a") {
        event.preventDefault();
        store.setSelection(shown);
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
        if (!shown.length) return;
        event.preventDefault();
        const last = store.selected[store.selected.length - 1];
        const current = last ? shown.indexOf(last) : -1;
        const next =
          current === -1
            ? 0
            : event.key === "ArrowDown"
              ? Math.min(shown.length - 1, current + 1)
              : Math.max(0, current - 1);
        const id = shown[next];
        if (event.shiftKey) store.select(id, "range");
        else store.setSelection([id]);
        const row = document.querySelector<HTMLElement>(`[data-job-id="${id}"]`);
        row?.scrollIntoView({ block: "nearest" });
        row?.focus({ preventScroll: true });
      } else if (event.key === "Escape" && store.selected.length) {
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
    <header className="flex flex-wrap items-center gap-3 px-6 pb-3 pt-4">
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
            <MenuItem
              icon={<ListChecks />}
              shortcut={`${MOD}+A`}
              onSelect={() => setSelection(visibleOrder(useStore.getState()))}
            >
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

const FILTERS: { value: QueueFilter; label: TranslationKey }[] = [
  { value: "all", label: "queue.filter.all" },
  { value: "active", label: "queue.filter.active" },
  { value: "queued", label: "queue.filter.queued" },
  { value: "completed", label: "queue.filter.completed" },
  { value: "failed", label: "queue.filter.failed" },
  { value: "canceled", label: "queue.filter.canceled" },
];

/** Proposal C: status chips, search and the cards/table switch. */
function QueueToolbar() {
  const t = useT();
  const counts = useStore((s) => s.queue.counts);
  const total = useStore((s) => s.order.length);
  const filter = useStore((s) => s.queueFilter);
  const query = useStore((s) => s.queueQuery);
  const layout = useStore((s) => s.layout);
  const setFilter = useStore((s) => s.setQueueFilter);
  const setQuery = useStore((s) => s.setQueueQuery);
  const setLayout = useStore((s) => s.setLayout);

  const count = (value: QueueFilter) =>
    value === "all" ? total : value === "active" ? counts.running + counts.paused : counts[value];

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-6 pb-3">
      <div role="group" aria-label={t("queue.filters")} className="flex min-w-0 flex-wrap items-center gap-1.5">
        {FILTERS.map(({ value, label }) => {
          const n = count(value);
          // Chips for empty states only clutter the bar
          if (!n && value !== "all" && value !== filter) return null;
          const active = filter === value;
          return (
            <button
              key={value}
              aria-pressed={active}
              onClick={() => setFilter(value)}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded-full border px-3 text-xs font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "border-fg bg-fg text-bg"
                  : "border-border bg-surface text-muted shadow-card hover:border-border-strong hover:text-fg",
              )}
            >
              {t(label)}
              <span className={cn("tabular", active ? "text-bg/70" : "text-subtle")}>{n}</span>
            </button>
          );
        })}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <div className="flex h-8 w-44 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 shadow-card transition focus-within:border-accent focus-within:ring-2 focus-within:ring-ring lg:w-64">
          <Search className="size-3.5 shrink-0 text-subtle" />
          <input
            id={SEARCH_ID}
            type="search"
            value={query}
            placeholder={t("queue.search")}
            aria-label={t("queue.search")}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Escape") return;
              event.preventDefault();
              if (query) setQuery("");
              else event.currentTarget.blur();
            }}
            className="h-full min-w-0 flex-1 bg-transparent text-[13px] text-fg outline-none placeholder:text-subtle [&::-webkit-search-cancel-button]:hidden"
          />
          {query ? (
            <button
              onClick={() => setQuery("")}
              aria-label={t("queue.clearSearch")}
              className="grid size-5 shrink-0 place-items-center rounded text-subtle outline-none hover:text-fg focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="size-3.5" />
            </button>
          ) : (
            <Kbd className="hidden h-[18px] text-[10px] shadow-none lg:inline-flex">{MOD}+F</Kbd>
          )}
        </div>
        <Segmented<QueueLayout>
          size="sm"
          aria-label={t("queue.layout")}
          value={layout}
          onValueChange={setLayout}
          className="h-8 items-center"
          options={[
            {
              value: "cards",
              label: (
                <>
                  <LayoutList />
                  <span className="hidden xl:inline">{t("queue.layout.cards")}</span>
                </>
              ),
              hint: t("queue.layout.cards"),
            },
            {
              value: "table",
              label: (
                <>
                  <Rows3 />
                  <span className="hidden xl:inline">{t("queue.layout.table")}</span>
                </>
              ),
              hint: t("queue.layout.table"),
            },
          ]}
        />
      </div>
    </div>
  );
}

function NoMatch() {
  const t = useT();
  const setFilter = useStore((s) => s.setQueueFilter);
  const setQuery = useStore((s) => s.setQueueQuery);
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="grid size-12 place-items-center rounded-2xl bg-elevated text-subtle">
        <SearchX className="size-5" />
      </div>
      <div>
        <p className="text-sm font-medium text-fg">{t("queue.noMatch")}</p>
        <p className="mt-1 text-[13px] text-muted">{t("queue.noMatchHint")}</p>
      </div>
      <Button
        size="sm"
        onClick={() => {
          setFilter("all");
          setQuery("");
        }}
      >
        {t("queue.showAll")}
      </Button>
    </div>
  );
}

function JobList({ layout }: { layout: QueueLayout }) {
  const t = useT();
  const shown = useStore(useShallow(visibleOrder));
  const nothingSelected = useStore((s) => s.selected.length === 0);
  const setSelection = useStore((s) => s.setSelection);
  const table = layout === "table";

  // A click on empty space (not on a file, not inside a popup) closes the options
  const onBackground = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    if (!event.currentTarget.contains(target) || target.closest("[role='option'], button, a, input")) return;
    setSelection([]);
  };

  return (
    <div className={cn("@container min-h-0 flex-1 overflow-y-auto", table && "bg-surface")} onClick={onBackground}>
      {shown.length === 0 ? (
        <NoMatch />
      ) : (
        <div className={cn(!table && "px-6 pb-6")}>
          <JobColumns layout={layout} />
          <div
            role="listbox"
            aria-multiselectable
            aria-label={t("queue.title")}
            className={cn(!table && "flex flex-col gap-2")}
          >
            {shown.map((id) => (
              <JobRow key={id} id={id} layout={layout} />
            ))}
          </div>
          {nothingSelected && (
            <p className={cn("text-center text-xs text-subtle", table ? "py-5" : "pt-5")}>{t("queue.hint")}</p>
          )}
        </div>
      )}
    </div>
  );
}

const EMPTY_BADGES = ["MP4", "AV1", "HEVC HDR", "WebM", "Reels · TikTok", "GIF", "WebP", "ProRes", "MP3", "FLAC"];

function EmptyState() {
  const t = useT();
  const formatCount = useStore((s) => s.presets.length);
  const [before, after] = t("empty.shortcut", { keys: "§" }).split("§");
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto border-t border-border p-8">
      <div className="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-dashed border-border-strong bg-surface/60 px-8 py-14 text-center sm:px-12">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 left-1/2 h-72 w-[40rem] -translate-x-1/2 rounded-full bg-brand opacity-[0.13] blur-3xl dark:opacity-[0.06]"
        />
        <div className="relative mx-auto mb-6 grid size-16 place-items-center rounded-2xl bg-brand text-white shadow-[0_16px_40px_-16px_var(--glow)] ring-1 ring-white/20 ring-inset">
          <FilePlus2 className="size-7" />
        </div>
        <h2 className="relative text-2xl font-semibold tracking-tight text-fg">{t("empty.title")}</h2>
        <p className="relative mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-muted">
          {t("empty.body", { count: formatCount || "30+" })}
        </p>
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
          {EMPTY_BADGES.map((format) => (
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

/**
 * Cards (proposal A): activity strip on top, options slide in from the right, optionally pinned.
 * Table (proposal C): dense rows, options open underneath, slim status bar at the bottom.
 */
export function QueueView() {
  const hasJobs = useStore((s) => s.order.length > 0);
  const layout = useStore((s) => s.layout);
  const pinned = useStore((s) => s.pinned);
  useQueueShortcuts();
  const cards = layout === "cards";

  return (
    <div className="flex min-w-0 flex-1">
      <section className="flex min-w-0 flex-1 flex-col">
        <QueueHeader />
        {hasJobs ? (
          <>
            <QueueToolbar />
            <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
              {cards && <ActivityStrip />}
              <JobList layout={layout} />
              {cards && !pinned && <InspectorDrawer docked={false} />}
            </div>
            {!cards && <InspectorSheet />}
            {!cards && <StatusBar />}
          </>
        ) : (
          <EmptyState />
        )}
      </section>
      {hasJobs && cards && pinned && <InspectorDrawer docked />}
    </div>
  );
}
