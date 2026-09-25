import { Check, FilePlus2, Pipette } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { pickPaths, updateOptions } from "@/lib/actions";
import { thumbnailUrl } from "@/lib/api";
import { basename, channelsLabel, codecName, formatBitrate, languageName } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { usePreset, useStore } from "@/lib/store";
import type { Job, JobOptions, SubtitleMode, SubtitleStyle } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { Segmented, Select, Slider, Switch } from "../ui/controls";
import { Badge, Field, SectionTitle } from "../ui/misc";
import { Note } from "./OutputPanel";

interface Choice {
  value: string;
  title: ReactNode;
  meta?: ReactNode;
  badges?: ReactNode[];
  disabled?: boolean;
}

function RadioList({
  value,
  items,
  onChange,
  disabled,
}: {
  value: string | null;
  items: Choice[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div role="radiogroup" className="space-y-1.5">
      {items.map((item) => {
        const checked = item.value === value;
        return (
          <button
            key={item.value}
            role="radio"
            aria-checked={checked}
            disabled={disabled || item.disabled}
            onClick={() => onChange(item.value)}
            className={cn(
              "flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45",
              checked ? "border-accent/50 bg-accent-soft" : "border-border bg-surface hover:border-border-strong",
            )}
          >
            <span
              className={cn(
                "grid size-4 shrink-0 place-items-center rounded-full border",
                checked ? "border-accent bg-accent" : "border-border-strong",
              )}
            >
              {checked && <span className="size-1.5 rounded-full bg-white" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium text-fg">{item.title}</span>
              {item.meta && <span className="block truncate text-xs text-muted">{item.meta}</span>}
            </span>
            {item.badges?.filter(Boolean).map((badge, index) => (
              <Badge key={index} className="shrink-0">
                {badge}
              </Badge>
            ))}
          </button>
        );
      })}
    </div>
  );
}

const SWATCHES = ["#FFFFFF", "#FFD400", "#00E5FF", "#7CFC00", "#FF5C8A", "#000000"];

function ColorField({ label, value, onChange, disabled }: {
  label: string;
  value: string;
  onChange: (color: string) => void;
  disabled?: boolean;
}) {
  const custom = !SWATCHES.includes(value.toUpperCase());
  return (
    <Field label={label}>
      <div className="flex flex-wrap items-center gap-1.5">
        {SWATCHES.map((color) => (
          <button
            key={color}
            aria-label={color}
            disabled={disabled}
            onClick={() => onChange(color)}
            className={cn(
              "grid size-7 place-items-center rounded-full border border-border-strong outline-none transition hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring",
              value.toUpperCase() === color && "ring-2 ring-accent ring-offset-2 ring-offset-surface",
            )}
            style={{ background: color }}
          >
            {value.toUpperCase() === color && (
              <Check className="size-3.5" style={{ color: color === "#000000" ? "#fff" : "#000" }} />
            )}
          </button>
        ))}
        <label
          className={cn(
            "relative grid size-7 cursor-pointer place-items-center overflow-hidden rounded-full border border-border-strong bg-[conic-gradient(red,yellow,lime,cyan,blue,magenta,red)] transition hover:scale-110",
            custom && "ring-2 ring-accent ring-offset-2 ring-offset-surface",
          )}
        >
          <Pipette className="size-3.5 text-white drop-shadow" />
          <input
            type="color"
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value.toUpperCase())}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </label>
      </div>
    </Field>
  );
}

function outlineShadow(width: number, color: string): string {
  if (width <= 0) return "none";
  const steps = 16;
  return Array.from({ length: steps }, (_, i) => {
    const angle = (i / steps) * Math.PI * 2;
    return `${(Math.cos(angle) * width).toFixed(2)}px ${(Math.sin(angle) * width).toFixed(2)}px 0 ${color}`;
  }).join(", ");
}

function SubtitlePreview({ style, job }: { style: SubtitleStyle; job: Job }) {
  const t = useT();
  const url = thumbnailUrl(job);
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(180);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setHeight(entry.contentRect.height));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  // libass sizes SRT text against a 288-line script, so scale everything to the preview height
  const scale = height / 288;
  return (
    <div ref={ref} className="relative aspect-video overflow-hidden rounded-lg bg-black">
      {url && <img src={url} alt="" className="absolute inset-0 size-full object-cover opacity-80" />}
      <div className="absolute inset-x-0 flex justify-center px-3" style={{ bottom: style.margin * scale }}>
        <span
          className="text-center leading-tight"
          style={{
            fontFamily: `"${style.font}", sans-serif`,
            fontSize: style.size * scale,
            fontWeight: style.bold ? 700 : 500,
            color: style.color,
            textShadow: style.box ? "none" : outlineShadow(style.outline * scale, style.outline_color),
            background: style.box ? "rgba(0,0,0,0.5)" : "transparent",
            padding: style.box ? `${2 * scale}px ${6 * scale}px` : 0,
          }}
        >
          {t("sub.previewText")}
        </span>
      </div>
    </div>
  );
}

function StyleEditor({ job, disabled }: { job: Job; disabled: boolean }) {
  const t = useT();
  const fonts = useStore((s) => s.fonts);
  const saved = job.options.subtitle_style;
  const [style, setStyle] = useState(saved);
  useEffect(() => setStyle(saved), [saved]);
  const commit = (patch: Partial<SubtitleStyle>) => {
    const next = { ...style, ...patch };
    setStyle(next);
    void updateOptions([job.id], { subtitle_style: next });
  };
  const fontOptions = Array.from(new Set([style.font, ...fonts])).map((font) => ({ value: font, label: font }));

  return (
    <div className="space-y-4 rounded-xl border border-border bg-surface p-4 shadow-card">
      <SubtitlePreview style={style} job={job} />
      <Field label={t("sub.font")}>
        <Select
          aria-label={t("sub.font")}
          value={style.font}
          disabled={disabled}
          options={fontOptions}
          onValueChange={(font) => commit({ font })}
        />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label={t("sub.size")} aside={style.size}>
          <Slider
            aria-label={t("sub.size")}
            min={12}
            max={48}
            value={style.size}
            disabled={disabled}
            onValueChange={(size) => setStyle({ ...style, size })}
            onValueCommit={(size) => commit({ size })}
          />
        </Field>
        <Field label={t("sub.outline")} aside={style.outline}>
          <Slider
            aria-label={t("sub.outline")}
            min={0}
            max={4}
            step={0.5}
            value={style.outline}
            disabled={disabled || style.box}
            onValueChange={(outline) => setStyle({ ...style, outline })}
            onValueCommit={(outline) => commit({ outline })}
          />
        </Field>
      </div>
      <ColorField label={t("sub.color")} value={style.color} disabled={disabled} onChange={(color) => commit({ color })} />
      <ColorField
        label={t("sub.outlineColor")}
        value={style.outline_color}
        disabled={disabled || style.box}
        onChange={(outline_color) => commit({ outline_color })}
      />
      <div className="flex items-center justify-between gap-4">
        <span className="text-[13px] font-medium text-fg">{t("sub.bold")}</span>
        <Switch checked={style.bold} disabled={disabled} onCheckedChange={(bold) => commit({ bold })} />
      </div>
      <div className="flex items-center justify-between gap-4">
        <span className="text-[13px] font-medium text-fg">{t("sub.box")}</span>
        <Switch checked={style.box} disabled={disabled} onCheckedChange={(box) => commit({ box })} />
      </div>
    </div>
  );
}

export function TracksPanel({ job, locked }: { job: Job; locked: boolean }) {
  const t = useT();
  const lang = useLang();
  const preset = usePreset(job.options.preset_id);
  if (!preset) return null;
  const { media, options } = job;
  const update = (patch: Partial<JobOptions>) => void updateOptions([job.id], patch);
  const canBurn = !!preset.video && !preset.remux && !!media.video;
  const remuxKeepsSubs = preset.remux && preset.soft_subtitles === "copy";

  const trackTitle = (language: string | null, position: number) =>
    languageName(language, lang) ?? t("common.track", { n: position + 1 });

  const fileChoices = Array.from(
    new Set([...job.external_subtitles, ...(options.subtitle_file ? [options.subtitle_file] : [])]),
  );
  const sourceValue =
    options.subtitle_track != null ? `track:${options.subtitle_track}` : options.subtitle_file ? `file:${options.subtitle_file}` : null;
  const selectedTrack = options.subtitle_track != null ? media.subtitles[options.subtitle_track] : null;
  const isAss = selectedTrack
    ? ["ass", "ssa"].includes(selectedTrack.codec)
    : /\.(ass|ssa)$/i.test(options.subtitle_file ?? "");
  const isBitmap = !!selectedTrack?.bitmap;

  const chooseFile = async () => {
    const [file] = await pickPaths("subtitle");
    if (!file) return null;
    return file;
  };

  const setMode = async (mode: SubtitleMode) => {
    if (mode === "none") return update({ subtitle_mode: "none" });
    if (options.subtitle_track != null || options.subtitle_file) return update({ subtitle_mode: mode });
    const external = job.external_subtitles[0];
    if (external) return update({ subtitle_mode: mode, subtitle_file: external, subtitle_track: null });
    const track = media.subtitles.find((s) => mode === "burn" || !s.bitmap || preset.soft_bitmap_subtitles);
    if (track) return update({ subtitle_mode: mode, subtitle_track: track.position, subtitle_file: null });
    const file = await chooseFile();
    if (file) update({ subtitle_mode: mode, subtitle_file: file, subtitle_track: null });
  };

  const setSource = (value: string) => {
    if (value.startsWith("track:")) update({ subtitle_track: Number(value.slice(6)), subtitle_file: null });
    else update({ subtitle_track: null, subtitle_file: value.slice(5) });
  };

  return (
    <div className="space-y-7">
      <section className="space-y-3">
        <SectionTitle>{t("tracks.audio")}</SectionTitle>
        {!media.audio.length ? (
          <Note>{t("tracks.noAudio")}</Note>
        ) : preset.remux ? (
          <Note>{t("tracks.allAudio")}</Note>
        ) : (
          <RadioList
            value={String(options.audio_track ?? media.audio.find((a) => a.default)?.position ?? 0)}
            disabled={locked}
            onChange={(value) => update({ audio_track: Number(value) })}
            items={media.audio.map((track) => ({
              value: String(track.position),
              title: track.title ? `${trackTitle(track.language, track.position)} · ${track.title}` : trackTitle(track.language, track.position),
              meta: [codecName(track.codec), channelsLabel(track, t), track.bitrate ? formatBitrate(track.bitrate, lang) : null]
                .filter(Boolean)
                .join(" · "),
              badges: track.default ? [t("tracks.default")] : [],
            }))}
          />
        )}
      </section>

      {preset.video && media.video && (
        <section className="space-y-4">
          <SectionTitle>{t("tracks.subtitles")}</SectionTitle>
          {remuxKeepsSubs ? (
            <Note>{t("sub.remuxKeep")}</Note>
          ) : (
            <>
              <Segmented<SubtitleMode>
                className="w-full"
                value={options.subtitle_mode}
                disabled={locked}
                onValueChange={(mode) => void setMode(mode)}
                options={[
                  { value: "none", label: t("sub.mode.none") },
                  {
                    value: "soft",
                    label: t("sub.mode.soft"),
                    disabled: !preset.soft_subtitles,
                    hint: preset.soft_subtitles ? undefined : t("sub.noSoft"),
                  },
                  { value: "burn", label: t("sub.mode.burn"), disabled: !canBurn },
                ]}
              />
              {options.subtitle_mode !== "none" && (
                <p className="text-xs leading-relaxed text-subtle">
                  {options.subtitle_mode === "soft" ? t("sub.modeHint.soft") : t("sub.modeHint.burn")}
                </p>
              )}
              {!preset.soft_subtitles && options.subtitle_mode === "none" && (
                <p className="text-xs text-subtle">{t("sub.noSoft")}</p>
              )}

              {options.subtitle_mode !== "none" && (
                <Field label={t("sub.source")}>
                  <RadioList
                    value={sourceValue}
                    disabled={locked}
                    onChange={setSource}
                    items={[
                      ...media.subtitles.map((track) => ({
                        value: `track:${track.position}`,
                        title: track.title ? `${trackTitle(track.language, track.position)} · ${track.title}` : trackTitle(track.language, track.position),
                        meta: codecName(track.codec),
                        badges: [track.bitmap ? t("sub.image") : null, track.forced ? t("sub.forced") : null],
                        disabled: options.subtitle_mode === "soft" && track.bitmap && !preset.soft_bitmap_subtitles,
                      })),
                      ...fileChoices.map((path) => ({
                        value: `file:${path}`,
                        title: basename(path),
                        meta: job.external_subtitles.includes(path) ? t("sub.detected") : t("sub.external"),
                      })),
                    ]}
                  />
                  {!media.subtitles.length && !fileChoices.length && (
                    <p className="text-xs text-subtle">{t("sub.noTracks")}</p>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={locked}
                    className="-ml-2"
                    onClick={async () => {
                      const file = await chooseFile();
                      if (file) update({ subtitle_file: file, subtitle_track: null });
                    }}
                  >
                    <FilePlus2 />
                    {t("sub.chooseFile")}
                  </Button>
                </Field>
              )}

              {options.subtitle_mode === "burn" && sourceValue && !isBitmap && (
                <Field label={t("sub.style")}>
                  {isAss ? <Note>{t("sub.assNote")}</Note> : <StyleEditor job={job} disabled={locked} />}
                </Field>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
