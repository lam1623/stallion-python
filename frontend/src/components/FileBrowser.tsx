import { ArrowUp, Captions, ChevronRight, File, Film, Folder, HardDrive, Music } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { errorText } from "@/lib/actions";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { EntryKind, FsEntry, FsListing } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Checkbox, Select, Switch } from "./ui/controls";
import { Spinner } from "./ui/misc";
import { Modal } from "./ui/overlay";

const LAST_DIR_KEY = "stallion-last-dir";
const NO_ROOTS: never[] = [];

const ICONS: Record<EntryKind, ReactNode> = {
  dir: <Folder className="size-4 fill-accent/20 text-accent" />,
  video: <Film className="size-4 text-violet-400" />,
  audio: <Music className="size-4 text-emerald-400" />,
  subtitle: <Captions className="size-4 text-sky-400" />,
  file: <File className="size-4 text-subtle" />,
};

function readLastDir(): string | null {
  try {
    return localStorage.getItem(LAST_DIR_KEY);
  } catch {
    return null;
  }
}

function crumbs(listing: FsListing): { label: string; path: string }[] {
  const sep = listing.path.includes("\\") ? "\\" : "/";
  const root = listing.root;
  const rest = listing.path.slice(root.length).split(/[\\/]/).filter(Boolean);
  const items = [{ label: root, path: root }];
  let current = root;
  for (const part of rest) {
    current = current.endsWith(sep) ? current + part : current + sep + part;
    items.push({ label: part, path: current });
  }
  return items;
}

export function FileBrowser() {
  const t = useT();
  const lang = useLang();
  const request = useStore((s) => s.browser);
  const openBrowser = useStore((s) => s.openBrowser);
  const roots = useStore((s) => s.system?.roots ?? NO_ROOTS);
  const mode = request?.mode ?? "files";

  const [path, setPath] = useState<string | null>(null);
  const [listing, setListing] = useState<FsListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!request) return;
    setSelected([]);
    setError(null);
    setPath(readLastDir() ?? roots[0]?.path ?? null);
  }, [request, roots]);

  const load = useCallback(
    async (target: string) => {
      setLoading(true);
      try {
        const result = await api.list(target, showAll);
        setListing(result);
        setError(null);
        try {
          localStorage.setItem(LAST_DIR_KEY, result.path);
        } catch {
          // storage may be unavailable
        }
      } catch (err) {
        setError(errorText(err));
        // A stale remembered folder should not trap the user: fall back to the first root
        if (target !== roots[0]?.path && roots[0]) setPath(roots[0].path);
      } finally {
        setLoading(false);
      }
    },
    [showAll, roots],
  );

  useEffect(() => {
    if (request && path) void load(path);
  }, [request, path, load]);

  const entries = useMemo(() => {
    const all = listing?.entries ?? [];
    if (mode === "folder") return all.filter((e) => e.kind === "dir");
    if (mode === "subtitle") return all.filter((e) => e.kind === "dir" || e.kind === "subtitle" || showAll);
    return all.filter((e) => e.kind !== "subtitle" || showAll);
  }, [listing, mode, showAll]);

  const selectable = entries.filter((e) => e.kind !== "dir");
  const close = (paths: string[]) => {
    request?.resolve(paths);
    openBrowser(null);
  };

  const onEntry = (entry: FsEntry) => {
    if (entry.kind === "dir") {
      setPath(entry.path);
      setSelected([]);
      return;
    }
    if (mode === "subtitle") setSelected([entry.path]);
    else if (mode === "files")
      setSelected((current) =>
        current.includes(entry.path) ? current.filter((p) => p !== entry.path) : [...current, entry.path],
      );
  };

  const title = mode === "folder" ? t("fb.chooseFolder") : mode === "subtitle" ? t("fb.chooseSubtitle") : t("fb.addFiles");
  const allChecked = selectable.length > 0 && selectable.every((e) => selected.includes(e.path));
  const someChecked = selected.length > 0 && !allChecked;
  const dateFormat = new Intl.DateTimeFormat(lang, { dateStyle: "medium" });
  const currentRoot = listing?.root ?? roots[0]?.path ?? "";

  return (
    <Modal
      open={!!request}
      onOpenChange={(open) => !open && close([])}
      title={title}
      className="w-[min(860px,calc(100vw-32px))]"
      footer={
        <>
          {mode === "files" && (
            <label className="flex items-center gap-2 text-xs text-muted">
              <Switch checked={showAll} onCheckedChange={setShowAll} />
              {t("fb.showAll")}
            </label>
          )}
          <span className="ml-auto text-xs text-muted tabular">
            {mode === "files" && selected.length > 0 && t("fb.selected", { count: selected.length })}
          </span>
          <Button variant="ghost" onClick={() => close([])}>
            {t("fb.cancel")}
          </Button>
          {mode === "folder" ? (
            <Button variant="primary" disabled={!listing} onClick={() => listing && close([listing.path])}>
              {t("fb.useFolder")}
            </Button>
          ) : (
            <Button variant="primary" disabled={!selected.length} onClick={() => close(selected)}>
              {mode === "files" ? t("fb.add", { count: selected.length || "" }) : t("fb.choose")}
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3">
        {roots.length > 1 && (
          <Select
            aria-label="Root"
            className="w-44"
            value={currentRoot}
            options={roots.map((root) => ({ value: root.path, label: root.name, hint: root.path }))}
            onValueChange={(value) => setPath(value)}
          />
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("fb.up")}
          title={t("fb.up")}
          disabled={!listing?.parent}
          onClick={() => listing?.parent && setPath(listing.parent)}
        >
          <ArrowUp />
        </Button>
        <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto text-[13px]">
          {listing &&
            crumbs(listing).map((crumb, index, all) => (
              <span key={crumb.path} className="flex shrink-0 items-center gap-0.5">
                {index > 0 && <ChevronRight className="size-3.5 text-subtle" />}
                <button
                  onClick={() => setPath(crumb.path)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-1.5 py-1 outline-none transition hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring",
                    index === all.length - 1 ? "font-medium text-fg" : "text-muted",
                  )}
                >
                  {index === 0 && <HardDrive className="size-3.5" />}
                  {index === 0 ? roots.find((r) => r.path === crumb.path)?.name ?? crumb.label : crumb.label}
                </button>
              </span>
            ))}
        </div>
        {loading && <Spinner className="text-subtle" />}
      </div>

      {mode === "files" && selectable.length > 0 && (
        <div className="flex items-center gap-3 border-b border-border px-5 py-2 text-xs text-muted">
          <Checkbox
            aria-label={t("fb.selectAll")}
            checked={allChecked ? true : someChecked ? "indeterminate" : false}
            onCheckedChange={() => setSelected(allChecked ? [] : selectable.map((e) => e.path))}
          />
          {t("fb.selectAll")}
        </div>
      )}

      <div className="min-h-[340px] px-2 py-2">
        {error && <p className="px-3 py-10 text-center text-sm text-danger">{error}</p>}
        {!error && listing && !entries.length && (
          <p className="px-3 py-16 text-center text-sm text-muted">{t("fb.empty")}</p>
        )}
        {!error &&
          entries.map((entry) => {
            const checked = selected.includes(entry.path);
            return (
              <div
                key={entry.path}
                role="button"
                tabIndex={0}
                onClick={() => onEntry(entry)}
                onDoubleClick={() => mode === "subtitle" && entry.kind === "subtitle" && close([entry.path])}
                onKeyDown={(event) => event.key === "Enter" && onEntry(entry)}
                className={cn(
                  "grid grid-cols-[1.25rem_1.25rem_1fr_auto_auto] items-center gap-3 rounded-lg px-3 py-2 text-[13px] outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
                  checked ? "bg-accent-soft" : "hover:bg-elevated/70",
                )}
              >
                <span className="grid place-items-center">
                  {entry.kind !== "dir" && mode === "files" && (
                    <Checkbox checked={checked} tabIndex={-1} onClick={(event) => event.stopPropagation()} onCheckedChange={() => onEntry(entry)} />
                  )}
                </span>
                {ICONS[entry.kind]}
                <span className={cn("truncate", entry.kind === "dir" ? "font-medium text-fg" : "text-fg")}>
                  {entry.name}
                </span>
                <span className="w-20 text-right text-xs text-muted tabular">
                  {entry.size != null ? formatBytes(entry.size, lang) : ""}
                </span>
                <span className="hidden w-28 text-right text-xs text-subtle sm:block">
                  {entry.modified ? dateFormat.format(entry.modified * 1000) : ""}
                </span>
              </div>
            );
          })}
        {listing?.truncated && (
          <p className="px-3 py-3 text-center text-xs text-subtle">
            {t("fb.truncated", { count: listing.entries.length })}
          </p>
        )}
      </div>
    </Modal>
  );
}
