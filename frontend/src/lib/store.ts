import { create } from "zustand";
import type { Job, JobOptions, Preset, Progress, QueueState, Settings, SystemInfo, SystemStats } from "./types";

export type View = "queue" | "formats" | "settings";
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

  select: (id: string, mode?: "single" | "toggle" | "range") => void;
  setSelection: (ids: string[]) => void;
}

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
      const selected = state.selected.filter((id) => id in jobs);
      return { jobs, order, queue, selected: selected.length || !order.length ? selected : [order[0]] };
    }),

  upsertJob: (job) =>
    set((state) => {
      const current = state.jobs[job.id];
      // Ignore copies older than what the WebSocket already delivered
      if (current && current.revision > job.revision) return state;
      const exists = current !== undefined;
      const order = exists ? state.order : [...state.order, job.id];
      const selected = state.selected.length ? state.selected : [job.id];
      return { jobs: { ...state.jobs, [job.id]: job }, order, selected };
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
      let selected = state.selected.filter((id) => !gone.has(id));
      if (!selected.length && order.length) {
        // Keep the inspector useful: select the neighbour of what was removed
        const firstRemoved = state.order.findIndex((id) => gone.has(id));
        selected = [order[Math.min(Math.max(firstRemoved, 0), order.length - 1)]];
      }
      return { jobs, order, selected };
    }),

  setQueue: (queue) => set({ queue }),

  applyStats: (stats) =>
    set((state) => ({
      stats,
      history: [...state.history, { at: Date.now(), cpu: stats.cpu.total, gpu: stats.gpu?.util ?? null }].slice(
        -HISTORY_SIZE,
      ),
    })),

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
        const a = state.order.indexOf(state.anchor);
        const b = state.order.indexOf(id);
        if (a >= 0 && b >= 0) {
          const [from, to] = a < b ? [a, b] : [b, a];
          return { selected: state.order.slice(from, to + 1) };
        }
      }
      return { selected: [id], anchor: id };
    }),

  setSelection: (selected) => set({ selected, anchor: selected[0] ?? null }),
}));

export const usePreset = (id: string | undefined) =>
  useStore((s) => (id ? s.presets.find((p) => p.id === id) : undefined));
