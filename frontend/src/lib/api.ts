import type {
  AddError,
  FormatDraft,
  FormatExample,
  FormatPreview,
  FsListing,
  Job,
  JobOptions,
  Preset,
  QueueState,
  Root,
  Settings,
  SystemInfo,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

function errorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.detail === "string") return record.detail;
    if (Array.isArray(record.detail)) {
      return record.detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
    }
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    const code =
      data && typeof data === "object" && typeof (data as { code?: unknown }).code === "string"
        ? (data as { code: string }).code
        : `http_${response.status}`;
    throw new ApiError(response.status, code, errorMessage(data, response.statusText));
  }
  return data as T;
}

type JobsResult = { jobs: Job[]; errors: AddError[] };

export const api = {
  authStatus: () => request<{ required: boolean; authenticated: boolean }>("GET", "/api/auth/status"),
  login: (token: string) => request<void>("POST", "/api/auth/login", { token }),
  logout: () => request<void>("POST", "/api/auth/logout"),

  system: () => request<SystemInfo>("GET", "/api/system"),
  presets: () => request<Preset[]>("GET", "/api/presets"),
  presetExample: (id: string) => request<FormatExample>("GET", `/api/presets/${encodeURIComponent(id)}/command`),
  previewFormat: (draft: FormatDraft) => request<FormatPreview>("POST", "/api/presets/preview", { draft }),
  createFormat: (draft: FormatDraft) => request<Preset>("POST", "/api/presets", draft),
  updateFormat: (id: string, draft: FormatDraft) =>
    request<Preset>("PUT", `/api/presets/${encodeURIComponent(id)}`, draft),
  deleteFormat: (id: string) => request<void>("DELETE", `/api/presets/${encodeURIComponent(id)}`),
  fonts: () => request<string[]>("GET", "/api/fonts"),
  settings: () => request<Settings>("GET", "/api/settings"),
  saveSettings: (patch: Partial<Settings>) => request<Settings>("PUT", "/api/settings", patch),

  roots: () => request<Root[]>("GET", "/api/fs/roots"),
  list: (path: string, all = false) =>
    request<FsListing>("GET", `/api/fs/list?path=${encodeURIComponent(path)}${all ? "&all=true" : ""}`),

  jobs: () => request<{ jobs: Job[]; queue: QueueState }>("GET", "/api/jobs"),
  addJobs: (paths: string[], options: Partial<JobOptions> = {}) =>
    request<JobsResult>("POST", "/api/jobs", { paths, options }),
  updateJob: (id: string, options: Partial<JobOptions>) => request<Job>("PATCH", `/api/jobs/${id}`, { options }),
  updateJobs: (ids: string[], options: Partial<JobOptions>) =>
    request<{ jobs: Job[]; errors: { id: string; name: string; message: string }[] }>("PATCH", "/api/jobs", {
      ids,
      options,
    }),
  removeJobs: (ids: string[]) => request<{ removed: string[] }>("POST", "/api/jobs/remove", { ids }),
  jobAction: (id: string, action: "pause" | "resume" | "cancel" | "retry") =>
    request<Job>("POST", `/api/jobs/${id}/${action}`),
  jobLog: (id: string) => request<{ log: string[]; error: string | null; command: string }>("GET", `/api/jobs/${id}/log`),

  startQueue: () => request<QueueState>("POST", "/api/queue/start"),
  pauseQueue: () => request<QueueState>("POST", "/api/queue/pause"),
  clearQueue: (statuses: string[]) => request<{ removed: string[] }>("POST", "/api/queue/clear", { statuses }),
};

export function thumbnailUrl(job: Job): string | null {
  return job.thumbnail ? `/api/jobs/${job.id}/thumbnail` : null;
}
