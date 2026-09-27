import { Check, Copy, Pencil, Plus, Search, SearchX, Star, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { errorText, saveSettings } from "@/lib/actions";
import { api } from "@/lib/api";
import { describePreset, EMPTY_DRAFT, presetSummary } from "@/lib/formats";
import { localized, useLang, useT } from "@/lib/i18n";
import { searchable, useStore } from "@/lib/store";
import type { FormatDraft, FormatExample, Preset } from "@/lib/types";
import { cn, copyText } from "@/lib/utils";
import { CATEGORIES, CATEGORY_ORDER, PresetIcon } from "./Brand";
import { FormatEditor } from "./formats/FormatEditor";
import { Button } from "./ui/button";
import { Input } from "./ui/controls";
import { Badge, SectionTitle } from "./ui/misc";
import { Modal } from "./ui/overlay";

function matches(preset: Preset, needle: string, lang: "en" | "es"): boolean {
  if (!needle) return true;
  const haystack = [
    localized(preset.name, lang),
    localized(preset.description, lang),
    preset.extension,
    preset.video?.codec ?? "",
    preset.audio?.codec ?? "",
    ...preset.tags,
  ].join(" ");
  return searchable(haystack).includes(needle);
}

function FormatList({
  presets,
  selected,
  onSelect,
  query,
}: {
  presets: Preset[];
  selected: string | null;
  onSelect: (id: string) => void;
  query: string;
}) {
  const t = useT();
  const lang = useLang();
  const defaultPreset = useStore((s) => s.settings?.default_preset);
  const needle = searchable(query.trim());
  const groups = CATEGORY_ORDER.map((cat) => ({
    cat,
    items: presets.filter((p) => p.category === cat && matches(p, needle, lang)),
  })).filter((group) => group.items.length);

  if (!groups.length) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-12 text-center text-sm text-muted">
        <SearchX className="size-5 text-subtle" />
        {t("formats.noMatch")}
      </div>
    );
  }
  return (
    <div className="space-y-5">
      {groups.map(({ cat, items }) => (
        <section key={cat} aria-label={t(CATEGORIES[cat].label)}>
          <SectionTitle className="mb-1.5 flex items-center justify-between px-2.5">
            {t(CATEGORIES[cat].label)}
            <span className="font-medium tabular">{items.length}</span>
          </SectionTitle>
          <div className="space-y-0.5">
            {items.map((preset) => (
              <button
                key={preset.id}
                onClick={() => onSelect(preset.id)}
                aria-current={preset.id === selected ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
                  preset.id === selected ? "bg-elevated shadow-card" : "hover:bg-elevated/60",
                  !preset.available && "opacity-55",
                )}
              >
                <PresetIcon preset={preset} className="size-8 rounded-lg [&_svg]:size-4" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate text-[13px] font-semibold text-fg">{localized(preset.name, lang)}</span>
                    <span className="shrink-0 text-[11px] text-subtle">{preset.extension}</span>
                    {preset.id === defaultPreset && <Star className="size-3 shrink-0 fill-current text-accent" />}
                  </span>
                  <span className="block truncate text-xs text-muted">{presetSummary(preset, lang)}</span>
                </span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function CommandBox({ preset }: { preset: Preset }) {
  const t = useT();
  const hardware = useStore((s) => s.system?.hardware);
  const preferGpu = useStore((s) => s.settings?.gpu_encoding);
  const [example, setExample] = useState<FormatExample | null>(null);
  const [copied, setCopied] = useState(false);

  // The example changes with the format itself, the GPU found and the GPU setting
  useEffect(() => {
    let alive = true;
    api
      .presetExample(preset.id)
      .then((result) => alive && setExample(result))
      .catch(() => alive && setExample(null));
    return () => {
      alive = false;
    };
  }, [preset, hardware?.state, hardware?.presets, preferGpu]);

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
      <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <span className="text-[13px] font-semibold text-fg">{t("formats.command")}</span>
          <span className="ml-2 text-xs text-subtle">{t("formats.commandHint")}</span>
        </div>
        {example?.encoder && (
          <span
            className={cn(
              "shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-bold text-fg",
              example.engine === "gpu" ? "bg-viz-gpu/15" : "bg-viz-cpu/15",
            )}
          >
            {example.engine === "gpu" ? "GPU" : "CPU"} · {example.encoder}
          </span>
        )}
        <Button
          variant="ghost"
          size="xs"
          disabled={!example}
          onClick={async () => {
            if (example && (await copyText(example.command))) {
              setCopied(true);
              toast.success(t("toast.copied"));
              setTimeout(() => setCopied(false), 1500);
            }
          }}
        >
          {copied ? <Check /> : <Copy />}
          {t("log.copy")}
        </Button>
      </div>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all bg-bg/60 px-4 py-3 font-mono text-[12px] leading-relaxed text-muted">
        {example?.command ?? "…"}
      </pre>
    </section>
  );
}

function FormatDetail({
  preset,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  preset: Preset;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const hardware = useStore((s) => s.system?.hardware);
  const isDefault = useStore((s) => s.settings?.default_preset === preset.id);
  const cards = describePreset(preset, t, lang, hardware);
  const gpu = hardware?.presets.includes(preset.id);

  return (
    <div className="@container mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-start gap-4">
        <PresetIcon preset={preset} className="size-14 rounded-2xl [&_svg]:size-6" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight text-fg">{localized(preset.name, lang)}</h2>
            <span className="text-sm text-subtle">{preset.extension}</span>
            <Badge className={cn(preset.custom && "border-transparent bg-accent-soft text-accent")}>
              {preset.custom ? t("formats.mine") : t("formats.builtin")}
            </Badge>
            {gpu && (
              <Badge title={t("formats.gpuYes", { label: hardware?.label ?? "GPU" })} className="border-transparent bg-viz-gpu/15 font-bold text-fg">
                GPU
              </Badge>
            )}
          </div>
          {localized(preset.description, lang) && (
            <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-muted">{localized(preset.description, lang)}</p>
          )}
          {!preset.available && (
            <p className="mt-2 text-[13px] font-medium text-warning">
              {t("picker.unavailable", { encoders: preset.missing_encoders.join(", ") })}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {isDefault ? (
            <span className="inline-flex h-9 items-center gap-1.5 px-2 text-[13px] font-semibold text-accent">
              <Check className="size-4" />
              {t("formats.isDefault")}
            </span>
          ) : (
            <Button disabled={!preset.available} onClick={() => void saveSettings({ default_preset: preset.id })}>
              <Star />
              {t("formats.makeDefault")}
            </Button>
          )}
          {preset.custom ? (
            <>
              <Button onClick={onEdit}>
                <Pencil />
                {t("formats.edit")}
              </Button>
              <Button variant="ghost" size="icon" aria-label={t("formats.delete")} onClick={onDelete}>
                <Trash2 />
              </Button>
            </>
          ) : (
            preset.draft && (
              <Button onClick={onDuplicate}>
                <Copy />
                {t("formats.duplicate")}
              </Button>
            )
          )}
        </div>
      </header>

      {/* Columns instead of a grid: each card keeps its own height, no empty boxes */}
      <div className="gap-4 @2xl:columns-2 @6xl:columns-4">
        {cards.map((card) => (
          <section
            key={card.title}
            className="mb-4 break-inside-avoid rounded-2xl border border-border bg-surface p-4 shadow-card"
          >
            <SectionTitle className="mb-2.5">{t(card.title)}</SectionTitle>
            <dl className="space-y-2.5">
              {card.rows.map((row, index) => (
                <div key={index} className="min-w-0">
                  <dt className="text-xs text-muted">{row.label}</dt>
                  <dd className={cn("text-[13px] font-medium text-fg", row.mono && "break-all font-mono text-xs font-normal")}>
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

      <CommandBox preset={preset} />
    </div>
  );
}

export function FormatsView() {
  const t = useT();
  const lang = useLang();
  const presets = useStore((s) => s.presets);
  const defaultPreset = useStore((s) => s.settings?.default_preset);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editor, setEditor] = useState<{ id: string | null; draft: FormatDraft } | null>(null);
  const [deleting, setDeleting] = useState<Preset | null>(null);

  const custom = presets.filter((p) => p.custom).length;
  const selected = useMemo(
    () =>
      presets.find((p) => p.id === selectedId) ??
      presets.find((p) => p.custom) ??
      presets.find((p) => p.id === defaultPreset) ??
      presets[0],
    [presets, selectedId, defaultPreset],
  );

  const refresh = () =>
    api
      .presets()
      .then((list) => useStore.getState().setData({ presets: list }))
      .catch(() => undefined);

  if (editor) {
    return (
      <FormatEditor
        presetId={editor.id}
        initial={editor.draft}
        onClose={(savedId) => {
          setEditor(null);
          if (savedId) {
            setSelectedId(savedId);
            void refresh();
          }
        }}
      />
    );
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold tracking-tight text-fg">{t("formats.title")}</h1>
          <p className="text-[13px] text-muted tabular">
            {t("formats.summary", { builtin: presets.length - custom, custom })}
          </p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" />
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("picker.search")}
            aria-label={t("picker.search")}
            className="pl-9"
          />
        </div>
        <Button variant="primary" onClick={() => setEditor({ id: null, draft: EMPTY_DRAFT })}>
          <Plus />
          {t("formats.new")}
        </Button>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav className="w-72 shrink-0 overflow-y-auto border-r border-border px-3 py-4 xl:w-80" aria-label={t("formats.title")}>
          <FormatList presets={presets} selected={selected?.id ?? null} onSelect={setSelectedId} query={query} />
        </nav>
        <section className="min-w-0 flex-1 overflow-y-auto px-8 py-6">
          {selected && (
            <FormatDetail
              key={selected.id}
              preset={selected}
              onEdit={() => selected.draft && setEditor({ id: selected.id, draft: selected.draft })}
              onDuplicate={() =>
                selected.draft &&
                setEditor({
                  id: null,
                  draft: {
                    ...selected.draft,
                    name: t("formats.copyName", { name: localized(selected.name, lang) }).slice(0, 60),
                    description: localized(selected.description, lang).slice(0, 200),
                  },
                })
              }
              onDelete={() => setDeleting(selected)}
            />
          )}
        </section>
      </div>
      <Modal
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={deleting ? t("formats.deleteTitle", { name: localized(deleting.name, lang) }) : ""}
        description={t("formats.deleteBody")}
        className="w-[min(440px,calc(100vw-32px))]"
        footer={
          <>
            <span className="flex-1" />
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              {t("editor.cancel")}
            </Button>
            <Button
              variant="danger"
              onClick={async () => {
                if (!deleting) return;
                try {
                  await api.deleteFormat(deleting.id);
                  toast.success(t("formats.deleted"));
                  setSelectedId(null);
                  await refresh();
                } catch (error) {
                  toast.error(errorText(error));
                }
                setDeleting(null);
              }}
            >
              <Trash2 />
              {t("formats.delete")}
            </Button>
          </>
        }
      >
        <span />
      </Modal>
    </div>
  );
}
