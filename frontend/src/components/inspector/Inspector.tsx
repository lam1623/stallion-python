import { Lock, Pin, PinOff, X } from "lucide-react";
import { Tabs } from "radix-ui";
import { type ReactNode, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import { dirname } from "@/lib/format";
import { type TranslationKey, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Thumbnail } from "../queue/JobRow";
import { Button } from "../ui/button";
import { StatusBadge } from "../ui/misc";
import { Tip } from "../ui/overlay";
import { InfoPanel } from "./InfoPanel";
import { LogPanel } from "./LogPanel";
import { OutputPanel } from "./OutputPanel";
import { TracksPanel } from "./TracksPanel";

const TABS: { value: string; label: TranslationKey }[] = [
  { value: "output", label: "insp.tab.output" },
  { value: "tracks", label: "insp.tab.tracks" },
  { value: "info", label: "insp.tab.info" },
  { value: "log", label: "insp.tab.log" },
];

/**
 * The selected jobs, plus the last non-empty selection while the panel slides away,
 * so it never goes blank mid-animation.
 */
function useInspectorJobs(): { jobs: Job[]; open: boolean } {
  const jobs = useStore(useShallow((s) => s.selected.map((id) => s.jobs[id]).filter(Boolean)));
  const last = useRef<Job[]>([]);
  if (jobs.length) last.current = jobs;
  return { jobs: jobs.length ? jobs : last.current, open: jobs.length > 0 };
}

function Stack({ jobs, className }: { jobs: Job[]; className?: string }) {
  return (
    <div className={cn("relative shrink-0", className)}>
      {jobs.length > 1 && (
        <div className="absolute -right-1.5 -top-1.5 aspect-video w-full rounded-lg bg-elevated ring-1 ring-border" />
      )}
      <Thumbnail job={jobs[0]} className="relative w-full shadow-card" />
    </div>
  );
}

function Title({ jobs, badge = false }: { jobs: Job[]; badge?: boolean }) {
  const t = useT();
  const [job] = jobs;
  const multi = jobs.length > 1;
  return (
    <div className="min-w-0 flex-1">
      <div className="truncate text-sm font-semibold text-fg" title={multi ? undefined : job.name}>
        {multi ? t("insp.multi", { count: jobs.length }) : job.name}
      </div>
      <div className="mt-0.5 truncate text-xs text-muted" title={multi ? undefined : job.input_path}>
        {multi ? t("insp.multiHint") : dirname(job.input_path)}
      </div>
      {badge && !multi && <StatusBadge status={job.status} className="mt-1.5" />}
    </div>
  );
}

function CloseButton() {
  const t = useT();
  const setSelection = useStore((s) => s.setSelection);
  return (
    <Tip content={`${t("insp.close")} · Esc`}>
      <Button variant="ghost" size="icon" aria-label={t("insp.close")} onClick={() => setSelection([])}>
        <X />
      </Button>
    </Tip>
  );
}

function TabList({ multi, className }: { multi: boolean; className?: string }) {
  const t = useT();
  return (
    <Tabs.List className={cn("flex gap-1", className)}>
      {TABS.map((item) => (
        <Tabs.Trigger
          key={item.value}
          value={item.value}
          disabled={multi && item.value !== "output"}
          className="relative -mb-px border-b-2 border-transparent px-2.5 py-2.5 text-[13px] font-medium text-muted outline-none transition hover:text-fg focus-visible:text-fg disabled:pointer-events-none disabled:opacity-35 data-[state=active]:border-accent data-[state=active]:text-fg"
        >
          {t(item.label)}
        </Tabs.Trigger>
      ))}
    </Tabs.List>
  );
}

/** Tab bodies; they lay out in columns when the panel is wide (the bottom sheet). */
function TabBodies({ jobs, locked, current }: { jobs: Job[]; locked: boolean; current: string }) {
  const t = useT();
  const multi = jobs.length > 1;
  return (
    <div className="@container min-h-0 flex-1 overflow-y-auto">
      {locked && current !== "info" && current !== "log" && (
        <div className="flex items-center gap-2 border-b border-border bg-elevated/50 px-5 py-2 text-xs text-muted">
          <Lock className="size-3.5 shrink-0" />
          {t("insp.locked")}
        </div>
      )}
      <Tabs.Content value="output" className="p-5 outline-none">
        <OutputPanel jobs={jobs} locked={locked} />
      </Tabs.Content>
      {!multi && (
        <>
          <Tabs.Content value="tracks" className="p-5 outline-none">
            <TracksPanel job={jobs[0]} locked={locked} />
          </Tabs.Content>
          <Tabs.Content value="info" className="p-5 outline-none">
            <InfoPanel job={jobs[0]} />
          </Tabs.Content>
          <Tabs.Content value="log" className="p-5 outline-none">
            <LogPanel job={jobs[0]} />
          </Tabs.Content>
        </>
      )}
    </div>
  );
}

function InspectorTabs({ jobs, children }: { jobs: Job[]; children: (current: string, locked: boolean) => ReactNode }) {
  const tab = useStore((s) => s.inspectorTab);
  const setTab = useStore((s) => s.setInspectorTab);
  const multi = jobs.length > 1;
  const locked = jobs.some((job) => job.status === "running" || job.status === "paused");
  const current = multi ? "output" : tab;
  return (
    <Tabs.Root value={current} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
      {children(current, locked)}
    </Tabs.Root>
  );
}

/**
 * Proposal A: options slide in from the right when a file is picked.
 * Floating, it covers the end of the list; pinned, it sits beside the queue and the list makes room.
 */
export function InspectorDrawer({ docked }: { docked: boolean }) {
  const t = useT();
  const { jobs, open } = useInspectorJobs();
  const setPinned = useStore((s) => s.setPinned);
  const multi = jobs.length > 1;

  // Always mounted (empty until the first pick) so opening animates every time
  const body = jobs.length > 0 && (
    <InspectorTabs jobs={jobs}>
      {(current, locked) => (
        <>
          <div className="flex items-start gap-3 px-4 pb-3 pt-4">
            <Stack jobs={jobs} className="w-24" />
            <Title jobs={jobs} badge />
            <div className="-mr-1 -mt-1 flex shrink-0 items-center gap-0.5">
              <Tip content={docked ? t("insp.unpin") : t("insp.pin")}>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={docked ? t("insp.unpin") : t("insp.pin")}
                  aria-pressed={docked}
                  onClick={() => setPinned(!docked)}
                  className={cn(docked && "bg-accent-soft text-accent hover:bg-accent-soft hover:text-accent")}
                >
                  {docked ? <PinOff /> : <Pin />}
                </Button>
              </Tip>
              <CloseButton />
            </div>
          </div>
          <TabList multi={multi} className="border-b border-border px-3" />
          <TabBodies jobs={jobs} locked={locked} current={current} />
        </>
      )}
    </InspectorTabs>
  );

  if (docked) {
    return (
      <aside
        aria-label={t("insp.label")}
        data-inspector
        inert={!open}
        className={cn(
          "flex shrink-0 flex-col overflow-hidden border-border bg-panel transition-[width] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]",
          open ? "w-[400px] border-l xl:w-[440px]" : "w-0",
        )}
      >
        <div className="flex h-full w-[400px] flex-col xl:w-[440px]">{body}</div>
      </aside>
    );
  }
  return (
    <aside
      aria-label={t("insp.label")}
      data-inspector
      inert={!open}
      className={cn(
        "absolute inset-y-0 right-0 z-20 flex w-full max-w-[440px] flex-col border-l border-border-strong bg-panel transition-[transform,box-shadow,visibility] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]",
        open ? "translate-x-0 shadow-[-24px_0_48px_-24px_rgb(16_18_27/0.3)]" : "invisible translate-x-[105%]",
      )}
    >
      {body}
    </aside>
  );
}

/** Proposal C: the table keeps its full width and the options open underneath it, in columns. */
export function InspectorSheet() {
  const t = useT();
  const { jobs, open } = useInspectorJobs();
  const multi = jobs.length > 1;

  return (
    <section
      aria-label={t("insp.label")}
      data-inspector
      inert={!open}
      className={cn(
        "shrink-0 overflow-hidden border-border-strong bg-panel transition-[height] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]",
        open ? "h-[min(400px,48vh)] border-t shadow-[0_-18px_40px_-28px_rgb(16_18_27/0.35)]" : "h-0",
      )}
    >
      {jobs.length > 0 && (
        <div className="flex h-[min(400px,48vh)] flex-col">
          <InspectorTabs jobs={jobs}>
            {(current, locked) => (
              <>
                <div className="flex h-14 shrink-0 items-stretch gap-3 border-b border-border pl-6 pr-3">
                  <div className="flex min-w-0 max-w-[45%] items-center gap-3">
                    <Stack jobs={jobs} className="w-16" />
                    <Title jobs={jobs} />
                    {!multi && <StatusBadge status={jobs[0].status} />}
                  </div>
                  <TabList multi={multi} className="ml-4" />
                  <span className="flex-1" />
                  <div className="flex items-center">
                    <CloseButton />
                  </div>
                </div>
                <TabBodies jobs={jobs} locked={locked} current={current} />
              </>
            )}
          </InspectorTabs>
        </div>
      )}
    </section>
  );
}
