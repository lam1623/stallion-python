import { Check } from "lucide-react";
import { saveSettings } from "@/lib/actions";
import { localized, useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import { CATEGORIES, CATEGORY_ORDER, PresetIcon } from "./Brand";
import { Button } from "./ui/button";
import { Badge, SectionTitle } from "./ui/misc";

export function FormatsView() {
  const t = useT();
  const lang = useLang();
  const presets = useStore((s) => s.presets);
  const defaultPreset = useStore((s) => s.settings?.default_preset);

  return (
    <div className="min-w-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{t("formats.title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("formats.subtitle", { count: presets.length })}</p>
        {CATEGORY_ORDER.map((category) => {
          const items = presets.filter((p) => p.category === category);
          if (!items.length) return null;
          const Icon = CATEGORIES[category].icon;
          return (
            <section key={category} className="mt-8">
              <SectionTitle className="flex items-center gap-2">
                <Icon className="size-3.5" />
                {t(CATEGORIES[category].label)}
              </SectionTitle>
              <p className="mt-1 mb-3 text-[13px] text-muted">{t(CATEGORIES[category].hint)}</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((preset) => {
                  const isDefault = preset.id === defaultPreset;
                  return (
                    <article
                      key={preset.id}
                      className="flex flex-col rounded-2xl border border-border bg-surface p-4 shadow-card transition hover:border-border-strong"
                    >
                      <div className="flex items-start gap-3">
                        <PresetIcon preset={preset} className="size-10 rounded-xl" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="truncate text-sm font-semibold text-fg">{localized(preset.name, lang)}</h3>
                            <span className="text-xs text-subtle">{preset.extension}</span>
                          </div>
                          <p className="mt-1 text-[13px] leading-relaxed text-muted">
                            {localized(preset.description, lang)}
                          </p>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-1">
                        {preset.tags.map((tag) => (
                          <Badge key={tag}>{tag}</Badge>
                        ))}
                      </div>
                      <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
                        {preset.available ? (
                          <span className="text-xs text-subtle">
                            {[preset.video?.codec, preset.audio?.codec].filter((c) => c && c !== "copy").join(" + ") ||
                              "stream copy"}
                          </span>
                        ) : (
                          <span className="text-xs font-medium text-warning">
                            {t("picker.unavailable", { encoders: preset.missing_encoders.join(", ") })}
                          </span>
                        )}
                        {isDefault ? (
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-accent">
                            <Check className="size-3.5" />
                            {t("formats.isDefault")}
                          </span>
                        ) : (
                          <Button
                            variant="ghost"
                            size="xs"
                            disabled={!preset.available}
                            onClick={() => void saveSettings({ default_preset: preset.id })}
                          >
                            {t("formats.makeDefault")}
                          </Button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
