// Per-device layout preferences (the desktop webview keeps localStorage between runs)

export type QueueLayout = "cards" | "table";

export interface Prefs {
  layout: QueueLayout;
  pinned: boolean;
  sidebarCollapsed: boolean;
}

const KEY = "stallion-ui";
const DEFAULTS: Prefs = { layout: "cards", pinned: false, sidebarCollapsed: false };

export function loadPrefs(): Prefs {
  let stored: Record<string, unknown> = {};
  try {
    stored = JSON.parse(localStorage.getItem(KEY) ?? "{}") ?? {};
  } catch {
    // storage unavailable or corrupt: fall back to the defaults
  }
  return {
    layout: stored.layout === "table" ? "table" : DEFAULTS.layout,
    pinned: typeof stored.pinned === "boolean" ? stored.pinned : DEFAULTS.pinned,
    sidebarCollapsed:
      typeof stored.sidebarCollapsed === "boolean" ? stored.sidebarCollapsed : DEFAULTS.sidebarCollapsed,
  };
}

export function savePrefs(patch: Partial<Prefs>) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...loadPrefs(), ...patch }));
  } catch {
    // storage may be unavailable (private windows, blocked site data)
  }
}
