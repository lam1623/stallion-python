import { FolderOpen, LogOut, RotateCcw } from "lucide-react";
import { type ReactNode, useState } from "react";
import { logout, pickPaths, saveSettings } from "@/lib/actions";
import { localized, useLang, useT } from "@/lib/i18n";
import { usePreset, useStore } from "@/lib/store";
import type { Settings } from "@/lib/types";
import { PresetIcon } from "./Brand";
import { PresetPicker } from "./PresetPicker";
import { Button } from "./ui/button";
import { Segmented, Select, Switch } from "./ui/controls";
import { Row, SectionTitle } from "./ui/misc";

function Card({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
      <div className="border-b border-border px-5 py-3">
        <SectionTitle>{title}</SectionTitle>
      </div>
      <div className="divide-y divide-border px-5">{children}</div>
    </section>
  );
}

function Toggle({ field }: { field: keyof Settings }) {
  const value = useStore((s) => Boolean(s.settings?.[field]));
  return <Switch checked={value} onCheckedChange={(checked) => void saveSettings({ [field]: checked })} />;
}

export function SettingsView() {
  const t = useT();
  const lang = useLang();
  const settings = useStore((s) => s.settings);
  const system = useStore((s) => s.system);
  const authRequired = useStore((s) => s.authRequired);
  const preset = usePreset(settings?.default_preset);
  const [pickerOpen, setPickerOpen] = useState(false);
  if (!settings) return null;

  return (
    <div className="min-w-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{t("set.title")}</h1>

        <Card title={t("set.appearance")}>
          <Row
            title={t("set.theme")}
            control={
              <Segmented
                value={settings.theme}
                onValueChange={(theme) => void saveSettings({ theme })}
                options={[
                  { value: "system", label: t("theme.system") },
                  { value: "light", label: t("theme.light") },
                  { value: "dark", label: t("theme.dark") },
                ]}
              />
            }
          />
          <Row
            title={t("set.language")}
            control={
              <Select
                aria-label={t("set.language")}
                className="w-44"
                value={settings.language}
                onValueChange={(language) => void saveSettings({ language })}
                options={[
                  { value: "auto", label: t("set.lang.auto") },
                  { value: "es", label: "Español" },
                  { value: "en", label: "English" },
                ]}
              />
            }
          />
        </Card>

        <Card title={t("set.conversion")}>
          <Row
            title={t("set.defaultFormat")}
            description={t("set.defaultFormatHint")}
            control={
              <Button onClick={() => setPickerOpen(true)} className="h-auto py-1.5 pl-1.5">
                {preset && <PresetIcon preset={preset} className="size-7 rounded-md [&_svg]:size-4" />}
                {preset ? localized(preset.name, lang) : settings.default_preset}
              </Button>
            }
          />
          <Row
            title={t("set.outputDir")}
            description={
              <span className="break-all">{settings.output_dir ?? t("opt.nextToOriginal")}</span>
            }
            control={
              <div className="flex gap-2">
                {settings.output_dir && (
                  <Button variant="ghost" size="sm" onClick={() => void saveSettings({ output_dir: null })}>
                    <RotateCcw />
                    {t("opt.reset")}
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={async () => {
                    const [dir] = await pickPaths("folder");
                    if (dir) void saveSettings({ output_dir: dir });
                  }}
                >
                  <FolderOpen />
                  {t("common.change")}
                </Button>
              </div>
            }
          />
          <Row
            title={t("set.concurrency")}
            description={t("set.concurrencyHint")}
            control={
              <Segmented
                value={String(settings.concurrency)}
                onValueChange={(value) => void saveSettings({ concurrency: Number(value) })}
                options={["1", "2", "3", "4"].map((n) => ({ value: n, label: n }))}
              />
            }
          />
          <Row title={t("set.autoStart")} description={t("set.autoStartHint")} control={<Toggle field="auto_start" />} />
          <Row title={t("set.overwrite")} description={t("set.overwriteHint")} control={<Toggle field="overwrite" />} />
          <Row title={t("set.deletePartial")} control={<Toggle field="delete_partial" />} />
        </Card>

        <Card title={t("set.subtitles")}>
          <Row
            title={t("set.autoloadSubs")}
            description={t("set.autoloadSubsHint")}
            control={<Toggle field="autoload_subtitles" />}
          />
        </Card>

        <Card title={t("set.notifications")}>
          <Row
            title={t("set.notify")}
            control={
              <Switch
                checked={settings.notify_on_finish}
                onCheckedChange={(checked) => {
                  if (checked && "Notification" in window && Notification.permission === "default") {
                    void Notification.requestPermission();
                  }
                  void saveSettings({ notify_on_finish: checked });
                }}
              />
            }
          />
        </Card>

        <Card title={t("set.system")}>
          <Row
            title="FFmpeg"
            description={
              <span className="break-all">
                {system?.ffmpeg.available ? `${system.ffmpeg.version} · ${system.ffmpeg.path}` : system?.ffmpeg.error}
              </span>
            }
            control={
              <span
                className={
                  system?.ffmpeg.available
                    ? "rounded-full bg-success/12 px-2 py-0.5 text-xs font-semibold text-success"
                    : "rounded-full bg-danger/12 px-2 py-0.5 text-xs font-semibold text-danger"
                }
              >
                {system?.ffmpeg.available ? "OK" : t("engine.missing")}
              </span>
            }
          />
          <Row title={t("set.version")} control={<span className="text-sm text-muted tabular">{system?.version}</span>} />
          <Row
            title={t("set.dataDir")}
            description={<span className="break-all font-mono text-xs">{system?.data_dir}</span>}
            control={null}
          />
          <Row
            title={t("set.roots")}
            description={
              <span className="break-all font-mono text-xs">{system?.roots.map((r) => r.path).join(" · ")}</span>
            }
            control={null}
          />
          {authRequired && !system?.desktop && (
            <Row
              title={t("set.logout")}
              control={
                <Button variant="danger" size="sm" onClick={() => void logout()}>
                  <LogOut />
                  {t("set.logout")}
                </Button>
              }
            />
          )}
        </Card>
      </div>
      <PresetPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        value={settings.default_preset}
        onSelect={(next) => {
          setPickerOpen(false);
          void saveSettings({ default_preset: next.id });
        }}
      />
    </div>
  );
}
