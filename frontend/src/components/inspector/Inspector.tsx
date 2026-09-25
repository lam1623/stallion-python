import { Lock, MousePointerClick } from "lucide-react";
import { Tabs } from "radix-ui";
import { useShallow } from "zustand/react/shallow";
import { dirname } from "@/lib/format";
import { type TranslationKey, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { Thumbnail } from "../JobCard";
import { StatusBadge } from "../ui/misc";
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

function Header({ jobs }: { jobs: Job[] }) {
  const t = useT();
  const [job] = jobs;
  const multi = jobs.length > 1;
  return (
    <div className="flex items-center gap-3 border-b border-border p-4">
      <div className="relative w-24 shrink-0">
        {multi && (
          <div className="absolute -right-1.5 -top-1.5 aspect-video w-full rounded-lg bg-elevated ring-1 ring-border" />
        )}
        <Thumbnail job={job} className="relative w-full shadow-card" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-fg" title={multi ? undefined : job.name}>
          {multi ? t("insp.multi", { count: jobs.length }) : job.name}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted" title={multi ? undefined : job.input_path}>
          {multi ? t("insp.multiHint") : dirname(job.input_path)}
        </div>
      </div>
      {!multi && <StatusBadge status={job.status} />}
    </div>
  );
}

export function Inspector() {
  const t = useT();
  const jobs = useStore(useShallow((s) => s.selected.map((id) => s.jobs[id]).filter(Boolean)));
  const tab = useStore((s) => s.inspectorTab);
  const setTab = useStore((s) => s.setInspectorTab);

  if (!jobs.length) {
    return (
      <aside className="hidden w-[380px] shrink-0 flex-col items-center justify-center gap-3 border-l border-border bg-panel p-8 text-center md:flex xl:w-[420px]">
        <div className="grid size-12 place-items-center rounded-2xl bg-elevated text-subtle">
          <MousePointerClick className="size-5" />
        </div>
        <p className="max-w-52 text-sm text-muted">{t("insp.empty")}</p>
      </aside>
    );
  }

  const multi = jobs.length > 1;
  const locked = jobs.some((job) => job.status === "running" || job.status === "paused");
  const current = multi ? "output" : tab;

  return (
    <aside className="hidden w-[380px] shrink-0 flex-col border-l border-border bg-panel md:flex xl:w-[420px]">
      <Header jobs={jobs} />
      <Tabs.Root value={current} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        <Tabs.List className="flex gap-1 border-b border-border px-3">
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
        {locked && current !== "info" && current !== "log" && (
          <div className="flex items-center gap-2 border-b border-border bg-elevated/50 px-4 py-2 text-xs text-muted">
            <Lock className="size-3.5 shrink-0" />
            {t("insp.locked")}
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
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
      </Tabs.Root>
    </aside>
  );
}
