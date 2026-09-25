import { Check, LayoutGrid, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { localized, useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { Preset, PresetCategory } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CATEGORIES, CATEGORY_ORDER, PresetIcon } from "./Brand";
import { Input } from "./ui/controls";
import { Badge, SectionTitle } from "./ui/misc";
import { Modal } from "./ui/overlay";

export function PresetCard({
  preset,
  selected,
  disabled,
  onSelect,
  note,
}: {
  preset: Preset;
  selected?: boolean;
  disabled?: boolean;
  onSelect?: () => void;
  note?: string;
}) {
  const lang = useLang();
  return (
    <button
      disabled={disabled}
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "group relative flex w-full items-start gap-3 rounded-xl border p-3 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45",
        selected
          ? "border-accent/60 bg-accent-soft"
          : "border-border bg-surface hover:border-border-strong hover:shadow-card",
      )}
    >
      <PresetIcon preset={preset} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-semibold text-fg">{localized(preset.name, lang)}</span>
          <span className="text-[11px] text-subtle">{preset.extension}</span>
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-muted">{localized(preset.description, lang)}</p>
        {note ? (
          <p className="mt-1.5 text-[11px] font-medium text-warning">{note}</p>
        ) : (
          <div className="mt-2 flex flex-wrap gap-1">
            {preset.tags.map((tag) => (
              <Badge key={tag} className="px-1 py-px text-[10px]">
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </div>
      {selected && (
        <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent text-white">
          <Check className="size-3" strokeWidth={3} />
        </span>
      )}
    </button>
  );
}

export function PresetPicker({
  open,
  onOpenChange,
  value,
  onSelect,
  audioOnly = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string;
  onSelect: (preset: Preset) => void;
  audioOnly?: boolean;
}) {
  const t = useT();
  const lang = useLang();
  const presets = useStore((s) => s.presets);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<PresetCategory | "all">("all");

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const order = audioOnly ? (["audio", ...CATEGORY_ORDER.filter((c) => c !== "audio")] as PresetCategory[]) : CATEGORY_ORDER;
    return order
      .filter((cat) => category === "all" || cat === category)
      .map((cat) => ({
        cat,
        items: presets.filter((preset) => {
          if (preset.category !== cat) return false;
          if (!needle) return true;
          const haystack = [
            localized(preset.name, lang),
            localized(preset.description, lang),
            preset.extension,
            ...preset.tags,
          ]
            .join(" ")
            .toLowerCase();
          return haystack.includes(needle);
        }),
      }))
      .filter((group) => group.items.length);
  }, [presets, query, category, lang, audioOnly]);

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={t("picker.title")} className="w-[min(900px,calc(100vw-32px))]">
      <div className="flex min-h-[460px]">
        <nav className="hidden w-48 shrink-0 space-y-0.5 border-r border-border p-3 sm:block">
          {(["all", ...CATEGORY_ORDER] as const).map((cat) => {
            const meta = cat === "all" ? null : CATEGORIES[cat];
            const Icon = meta?.icon;
            return (
              <button
                key={cat}
                onClick={() => setCategory(cat)}
                className={cn(
                  "flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-left text-[13px] font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
                  category === cat ? "bg-elevated text-fg" : "text-muted hover:bg-elevated/60 hover:text-fg",
                )}
              >
                {Icon ? <Icon className="size-4 text-subtle" /> : <LayoutGrid className="size-4 text-subtle" />}
                {meta ? t(meta.label) : t("picker.all")}
                <span className="ml-auto text-[11px] text-subtle tabular">
                  {cat === "all" ? presets.length : presets.filter((p) => p.category === cat).length}
                </span>
              </button>
            );
          })}
        </nav>
        <div className="min-w-0 flex-1 p-4">
          <div className="relative mb-4">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" />
            <Input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("picker.search")}
              className="pl-9"
            />
          </div>
          {groups.map(({ cat, items }) => (
            <section key={cat} className="mb-5 last:mb-0">
              <SectionTitle className="mb-2">{t(CATEGORIES[cat].label)}</SectionTitle>
              <div className="grid gap-2 md:grid-cols-2">
                {items.map((preset) => {
                  const needsVideo = audioOnly && preset.category === "disc";
                  const disabled = !preset.available || needsVideo;
                  return (
                    <PresetCard
                      key={preset.id}
                      preset={preset}
                      selected={preset.id === value}
                      disabled={disabled}
                      note={
                        !preset.available
                          ? t("picker.unavailable", { encoders: preset.missing_encoders.join(", ") })
                          : needsVideo
                            ? t("errors.needs_video")
                            : undefined
                      }
                      onSelect={() => onSelect(preset)}
                    />
                  );
                })}
              </div>
            </section>
          ))}
          {!groups.length && <p className="py-16 text-center text-sm text-muted">{t("picker.noResults")}</p>}
        </div>
      </div>
    </Modal>
  );
}
