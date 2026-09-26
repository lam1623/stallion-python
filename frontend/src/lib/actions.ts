import { toast } from "sonner";
import { ApiError, api } from "./api";
import { hasKey, resolveLang, type TranslationKey, translate } from "./i18n";
import { nativeApi } from "./native";
import { type BrowserMode, useStore } from "./store";
import type { JobOptions, JobStatus, Settings } from "./types";

function tr(key: TranslationKey, vars?: Record<string, string | number>): string {
  return translate(resolveLang(useStore.getState().settings?.language), key, vars);
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const key = `errors.${error.code}`;
    return hasKey(key) ? tr(key) : error.message;
  }
  return error instanceof Error ? error.message : tr("errors.generic");
}

function reportError(error: unknown) {
  toast.error(errorText(error));
}

/** Native dialogs in the desktop app, the built-in browser everywhere else. */
export async function pickPaths(mode: BrowserMode): Promise<string[]> {
  const native = nativeApi();
  if (native) {
    try {
      if (mode === "files") return await native.pick_files();
      const picked = mode === "folder" ? await native.pick_folder() : await native.pick_subtitle();
      return picked ? [picked] : [];
    } catch (error) {
      reportError(error);
      return [];
    }
  }
  return new Promise((resolve) => useStore.getState().openBrowser({ mode, resolve }));
}

export async function addPaths(paths: string[]) {
  if (!paths.length) return;
  const toastId = toast.loading(tr("toast.analyzing"));
  try {
    const { jobs, errors } = await api.addJobs(paths);
    const store = useStore.getState();
    jobs.forEach(store.upsertJob);
    toast.dismiss(toastId);
    if (jobs.length) {
      toast.success(jobs.length === 1 ? tr("toast.addedOne") : tr("toast.added", { count: jobs.length }));
    }
    if (errors.length) {
      const first = errors[0];
      const reason = hasKey(`errors.${first.code}`) ? tr(`errors.${first.code}` as TranslationKey) : first.message;
      toast.warning(tr("toast.skipped", { count: errors.length }), {
        description: errors.length === 1 ? `${first.path.split(/[\\/]/).pop()}: ${reason}` : reason,
      });
    }
  } catch (error) {
    toast.dismiss(toastId);
    reportError(error);
  }
}

export async function addFiles() {
  await addPaths(await pickPaths("files"));
}

export async function addFolder() {
  const [folder] = await pickPaths("folder");
  if (!folder) return;
  try {
    const listing = await api.list(folder);
    const media = listing.entries.filter((e) => e.kind === "video" || e.kind === "audio").map((e) => e.path);
    if (!media.length) toast(tr("toast.noMedia"));
    else await addPaths(media);
  } catch (error) {
    reportError(error);
  }
}

export async function updateOptions(ids: string[], patch: Partial<JobOptions>) {
  if (!ids.length) return;
  const store = useStore.getState();
  const previous = ids.map((id) => store.jobs[id]).filter(Boolean);
  store.patchOptions(ids, patch);
  try {
    if (ids.length === 1) {
      store.upsertJob(await api.updateJob(ids[0], patch));
    } else {
      const result = await api.updateJobs(ids, patch);
      result.jobs.forEach(store.upsertJob);
      if (result.errors.length) {
        toast.warning(result.errors[0].name, { description: result.errors[0].message });
        const { jobs } = await api.jobs();
        jobs.forEach(useStore.getState().upsertJob);
      }
    }
  } catch (error) {
    previous.forEach(useStore.getState().upsertJob);
    reportError(error);
  }
}

export async function jobAction(id: string, action: "pause" | "resume" | "cancel" | "retry") {
  try {
    useStore.getState().upsertJob(await api.jobAction(id, action));
  } catch (error) {
    reportError(error);
  }
}

export async function removeJobs(ids: string[]) {
  if (!ids.length) return;
  try {
    const { removed } = await api.removeJobs(ids);
    useStore.getState().removeJobs(removed);
  } catch (error) {
    reportError(error);
  }
}

export async function toggleQueue() {
  const { queue } = useStore.getState();
  try {
    useStore.getState().setQueue(queue.running ? await api.pauseQueue() : await api.startQueue());
  } catch (error) {
    reportError(error);
  }
}

export async function clearQueue(statuses: JobStatus[]) {
  try {
    const { removed } = await api.clearQueue(statuses);
    useStore.getState().removeJobs(removed);
  } catch (error) {
    reportError(error);
  }
}

export async function saveSettings(patch: Partial<Settings>) {
  const store = useStore.getState();
  const previous = store.settings;
  if (previous) store.setData({ settings: { ...previous, ...patch } });
  try {
    store.setData({ settings: await api.saveSettings(patch) });
  } catch (error) {
    store.setData({ settings: previous });
    reportError(error);
  }
}

export async function openPath(path: string) {
  const native = nativeApi();
  if (!native) return;
  try {
    await native.open_path(path);
  } catch (error) {
    reportError(error);
  }
}

export async function logout() {
  try {
    await api.logout();
  } finally {
    window.location.reload();
  }
}
