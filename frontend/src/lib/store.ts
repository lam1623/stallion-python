import { create } from "zustand";
import { loadPrefs, type QueueLayout, savePrefs } from "./prefs";
import type { Job, JobOptions, Preset, Progress, QueueState, Settings, SystemInfo, SystemStats } from "./types";

export type { QueueLayout } from "./prefs";
export type View = "queue" | "formats" | "settings";
/** Queue filter chips: "active" groups running and paused jobs. */
export type QueueFilter = "all" | "active" | "queued" | "completed" | "failed" | "canceled";
export type Connection = "connecting" | "online" | "offline";
export type BrowserMode = "files" | "folder" | "subtitle";

export interface BrowserRequest {
  mode: BrowserMode;
  title?: string;
  resolve: (paths: string[]) => void;
}

const EMPTY_COUNTS = { queued: 0, running: 0, paused: 0, completed: 0, failed: 0, canceled: 0 };
// Samples kept for the activity charts (a minute while converting, 1 s apart)
export const HISTORY_SIZE = 60;

export interface Sample {
  at: number;
  cpu: number;
  gpu: number | null;
}

interface State {
  booted: boolean;
  authRequired: boolean;
  authenticated: boolean;
  system: SystemInfo | null;
  presets: Preset[];
  settings: Settings | null;
  fonts: string[];
  jobs: Record<string, Job>;
  order: string[];
  queue: QueueState;
  selected: string[];
  anchor: string | null;
  view: View;
  connection: Connection;
  browser: BrowserRequest | null;
  inspectorTab: string;
  stats: SystemStats | null;
  history: Sample[];
  queueFilter: QueueFilter;
  queueQuery: string;
  layout: QueueLayout;
  pinned: boolean;
  sidebarCollapsed: boolean;

  setBoot: (patch: Partial<Pick<State, "booted" | "authRequired" | "authenticated">>) => void;
  setData: (patch: Partial<Pick<State, "system" | "presets" | "settings" | "fonts">>) => void;
  setView: (view: View) => void;
  setConnection: (connection: Connection) => void;
  setInspectorTab: (tab: string) => void;
  openBrowser: (request: BrowserRequest | null) => void;

  applySnapshot: (jobs: Job[], queue: QueueState) => void;
  upsertJob: (job: Job) => void;
  applyProgress: (items: { id: string; progress: Progress }[]) => void;
  removeJobs: (ids: string[]) => void;
  setQueue: (queue: QueueState) => void;
  patchOptions: (ids: string[], patch: Partial<JobOptions>) => void;
  applyStats: (stats: SystemStats) => void;
  setQueueFilter: (filter: QueueFilter) => void;
  setQueueQuery: (query: string) => void;
  setLayout: (layout: QueueLayout) => void;
  setPinned: (pinned: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  select: (id: string, mode?: "single" | "toggle" | "range") => void;
  setSelection: (ids: string[]) => void;
}

export function matchesFilter(job: Job, filter: QueueFilter): boolean {
  if (filter === "all") return true;
  if (filter === "active") return job.status === "running" || job.status === "paused";
  return job.status === filter;
}

/** Lower case without accents, so "cancion" finds "Canción". */
export function searchable(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/** Jobs shown by the current filter and search, in queue order. */
export function visibleOrder(state: Pick<State, "order" | "jobs" | "queueFilter" | "queueQuery">): string[] {
  const query = searchable(state.queueQuery.trim());
  if (state.queueFilter === "all" && !query) return state.order;
  return state.order.filter((id) => {
    const job = state.jobs[id];
    return !!job && matchesFilter(job, state.queueFilter) && (!query || searchable(job.name).includes(query));
  });
}

const prefs = loadPrefs();

export const useStore = create<State>()((set) => ({
  booted: false,
  authRequired: false,
  authenticated: false,
  system: null,
  presets: [],
  settings: null,
  fonts: [],
  jobs: {},
  order: [],
  queue: { running: false, counts: EMPTY_COUNTS },
  selected: [],
  anchor: null,
  view: "queue",
  connection: "connecting",
  browser: null,
  inspectorTab: "output",
  stats: null,
  history: [],
  queueFilter: "all",
  queueQuery: "",
  layout: prefs.layout,
  pinned: prefs.pinned,
  sidebarCollapsed: prefs.sidebarCollapsed,

  setBoot: (patch) => set(patch),
  setData: (patch) => set(patch),
  setView: (view) => set({ view }),
  setConnection: (connection) => set({ connection }),
  setInspectorTab: (inspectorTab) => set({ inspectorTab }),
  openBrowser: (browser) => set({ browser }),

  applySnapshot: (list, queue) =>
    set((state) => {
      const jobs = Object.fromEntries(list.map((job) => [job.id, job]));
      const order = list.map((job) => job.id);
      return { jobs, order, queue, selected: state.selected.filter((id) => id in jobs) };
    }),

  upsertJob: (job) =>
    set((state) => {
      const current = state.jobs[job.id];
      // Ignore copies older than what the WebSocket already delivered
      if (current && current.revision > job.revision) return state;
      const order = current !== undefined ? state.order : [...state.order, job.id];
      return { jobs: { ...state.jobs, [job.id]: job }, order };
    }),

  applyProgress: (items) =>
    set((state) => {
      const jobs = { ...state.jobs };
      for (const { id, progress } of items) {
        const job = jobs[id];
        if (job) jobs[id] = { ...job, progress };
      }
      return { jobs };
    }),

  removeJobs: (ids) =>
    set((state) => {
      const gone = new Set(ids);
      const jobs = { ...state.jobs };
      ids.forEach((id) => delete jobs[id]);
      const order = state.order.filter((id) => !gone.has(id));
      const selected = state.selected.filter((id) => !gone.has(id));
      const anchor = state.anchor && gone.has(state.anchor) ? (selected[0] ?? null) : state.anchor;
      return { jobs, order, selected, anchor };
    }),

  setQueue: (queue) => set({ queue }),

  applyStats: (stats) =>
    set((state) => ({
      stats,
      history: [...state.history, { at: Date.now(), cpu: stats.cpu.total, gpu: stats.gpu?.util ?? null }].slice(
        -HISTORY_SIZE,
      ),
    })),

  // Changing what is shown drops the hidden files from the selection
  setQueueFilter: (queueFilter) =>
    set((state) => {
      const shown = new Set(visibleOrder({ ...state, queueFilter }));
      return { queueFilter, selected: state.selected.filter((id) => shown.has(id)) };
    }),
  setQueueQuery: (queueQuery) =>
    set((state) => {
      const shown = new Set(visibleOrder({ ...state, queueQuery }));
      return { queueQuery, selected: state.selected.filter((id) => shown.has(id)) };
    }),
  setLayout: (layout) => {
    savePrefs({ layout });
    set({ layout });
  },
  setPinned: (pinned) => {
    savePrefs({ pinned });
    set({ pinned });
  },
  setSidebarCollapsed: (sidebarCollapsed) => {
    savePrefs({ sidebarCollapsed });
    set({ sidebarCollapsed });
  },

  patchOptions: (ids, patch) =>
    set((state) => {
      const jobs = { ...state.jobs };
      for (const id of ids) {
        const job = jobs[id];
        if (job) jobs[id] = { ...job, options: { ...job.options, ...patch } };
      }
      return { jobs };
    }),

  select: (id, mode = "single") =>
    set((state) => {
      if (mode === "toggle") {
        const has = state.selected.includes(id);
        const selected = has ? state.selected.filter((x) => x !== id) : [...state.selected, id];
        return { selected, anchor: id };
      }
      if (mode === "range" && state.anchor) {
        // Ranges follow what is on screen, never files hidden by the filter
        const shown = visibleOrder(state);
        const a = shown.indexOf(state.anchor);
        const b = shown.indexOf(id);
        if (a >= 0 && b >= 0) {
          const [from, to] = a < b ? [a, b] : [b, a];
          return { selected: shown.slice(from, to + 1) };
        }
      }
      return { selected: [id], anchor: id };
    }),

  setSelection: (selected) => set({ selected, anchor: selected[0] ?? null }),
}));

export const usePreset = (id: string | undefined) =>
  useStore((s) => (id ? s.presets.find((p) => p.id === id) : undefined));
