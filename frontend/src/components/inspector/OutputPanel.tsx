import { Folder, Info } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { pickPaths, updateOptions } from "@/lib/actions";
import { basename, displaySize } from "@/lib/format";
import { localized, type Translator, useLang, useT } from "@/lib/i18n";
import { frameLabel, keepsHdr, type SizePlan, sizePlan } from "@/lib/presets";
import { useStore } from "@/lib/store";
import type { Job, JobOptions, Preset, Speed } from "@/lib/types";
import { PresetIcon } from "../Brand";
import { PresetPicker } from "../PresetPicker";
import { Button } from "../ui/button";
import { Select, Segmented, Slider, Switch } from "../ui/controls";
import { Badge, Field, SectionTitle } from "../ui/misc";

const HEIGHTS = [2160, 1440, 1080, 720, 480, 360];
// Below this video bitrate a size target gives visibly poor quality
const LOW_SIZE_KBPS = 150;

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-xl border border-border bg-elevated/60 p-3 text-[13px] leading-relaxed text-muted">
      <Info className="mt-0.5 size-4 shrink-0 text-subtle" />
      <div>{children}</div>
    </div>
  );
}

/** Patch applied when switching format: reset per-format values and keep subtitles valid. */
export function presetPatch(job: Job, preset: Preset): Partial<JobOptions> {
  const patch: Partial<JobOptions> = {
    preset_id: preset.id,
    quality: null,
    audio_bitrate_kbps: null,
    max_height: null,
  };
  const options = job.options;
  const canBurn = !!preset.video && !preset.remux && !!job.media.video;
  if (options.subtitle_mode === "soft") {
    const track = options.subtitle_track != null ? job.media.subtitles[options.subtitle_track] : null;
    const softOk = !!preset.soft_subtitles && (!track?.bitmap || preset.soft_bitmap_subtitles);
    if (!softOk) patch.subtitle_mode = canBurn ? "burn" : "none";
  } else if (options.subtitle_mode === "burn" && !canBurn) {
    patch.subtitle_mode = "none";
  }
  if (preset.remux) {
    patch.volume_db = 0;
    patch.normalize_audio = false;
  }
  return patch;
}

function qualityLabel(spec: NonNullable<Preset["video"]>, value: number, t: Translator): string {
  if (spec.quality_min == null || spec.quality_max == null) return "";
  if (spec.rate_control !== "crf" && spec.rate_control !== "quality") return "";
  const span = spec.quality_max - spec.quality_min || 1;
  // CRF: lower is better · quality (WebP): higher is better
  const score = spec.rate_control === "crf" ? (spec.quality_max - value) / span : (value - spec.quality_min) / span;
  if (score > 0.85) return t("opt.q.max");
  if (score > 0.6) return t("opt.q.high");
  if (score > 0.35) return t("opt.q.balanced");
  return t("opt.q.compact");
}

function QualityField({ preset, options, onCommit, disabled }: {
  preset: Preset;
  options: JobOptions;
  onCommit: (value: number) => void;
  disabled: boolean;
}) {
  const t = useT();
  const lang = useLang();
  const spec = preset.video!;
  const min = spec.quality_min ?? 0;
  const max = spec.quality_max ?? 51;
  const actual = options.quality ?? spec.quality ?? min;
  const crf = spec.rate_control === "crf";
  const bitrate = spec.rate_control === "bitrate";
  // CRF: lower is better, so the slider is mirrored to keep "better" on the right
  const toSlider = (value: number) => (crf ? min + max - value : value);
  const [position, setPosition] = useState(toSlider(actual));
  useEffect(() => setPosition(crf ? min + max - actual : actual), [actual, min, max, crf]);
  const value = crf ? min + max - position : position;

  return (
    <Field
      label={bitrate ? t("opt.bitrate") : t("opt.quality")}
      aside={
        bitrate ? (
          `${value.toLocaleString(lang)} kb/s`
        ) : (
          <span>
            {qualityLabel(spec, value, t)} <span className="text-subtle">· {crf ? `CRF ${value}` : value}</span>
          </span>
        )
      }
    >
      <Slider
        aria-label={t("opt.quality")}
        min={min}
        max={max}
        step={bitrate ? 100 : 1}
        value={position}
        disabled={disabled}
        onValueChange={setPosition}
        onValueCommit={(v) => onCommit(crf ? min + max - v : v)}
      />
      <div className="flex justify-between text-[11px] text-subtle">
        <span>{t("opt.smaller")}</span>
        <span>{t("opt.better")}</span>
      </div>
    </Field>
  );
}

function formatKbps(kbps: number, lang: string): string {
  return kbps >= 1000
    ? `${(kbps / 1000).toLocaleString(lang, { maximumFractionDigits: 1 })} Mb/s`
    : `${kbps.toLocaleString(lang)} kb/s`;
}

/** Target file size in MB: quick picks plus a free value; shows the bitrate the engine will use. */
function SizeField({
  preset,
  value,
  plan,
  resolution,
  onCommit,
  disabled,
}: {
  preset: Preset;
  value: number;
  plan: SizePlan | null;
  resolution: string | null;
  onCommit: (value: number) => void;
  disabled: boolean;
}) {
  const t = useT();
  const lang = useLang();
  const spec = preset.video!;
  const min = spec.quality_min ?? 1;
  const max = spec.quality_max ?? 4000;
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);

  const commit = () => {
    const parsed = Math.round(Number(draft));
    if (!Number.isFinite(parsed) || parsed <= 0) return setDraft(String(value));
    const clamped = Math.min(max, Math.max(min, parsed));
    setDraft(String(clamped));
    if (clamped !== value) onCommit(clamped);
  };

  return (
    <Field
      label={t("opt.targetSize")}
      aside={
        plan
          ? t("opt.sizeEstimate", {
              bitrate: formatKbps(plan.videoKbps, lang),
              resolution: resolution ?? "",
            })
          : undefined
      }
      hint={t("opt.targetSizeHint")}
    >
      {spec.quality_choices.length > 0 && (
        <Segmented<string>
          size="sm"
          className="w-full"
          value={String(value)}
          disabled={disabled}
          onValueChange={(mb) => onCommit(Number(mb))}
          options={spec.quality_choices.map((mb) => ({ value: String(mb), label: `${mb} MB` }))}
        />
      )}
      <div className="flex h-9 items-center rounded-lg border border-border bg-surface shadow-card transition focus-within:border-accent focus-within:ring-2 focus-within:ring-ring">
        <input
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          value={draft}
          disabled={disabled}
          aria-label={t("opt.targetSize")}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()}
          className="h-full min-w-0 flex-1 bg-transparent px-3 text-sm text-fg outline-none tabular disabled:opacity-50"
        />
        <span className="pr-3 text-sm text-subtle">MB</span>
      </div>
      {plan && plan.videoKbps < LOW_SIZE_KBPS && <p className="text-xs text-warning">{t("opt.sizeTooSmall")}</p>}
    </Field>
  );
}

function VolumeField({ value, onCommit, disabled }: { value: number; onCommit: (v: number) => void; disabled: boolean }) {
  const t = useT();
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  return (
    <Field label={t("opt.volume")} aside={`${local > 0 ? "+" : ""}${local} dB`}>
      <Slider
        aria-label={t("opt.volume")}
        min={-20}
        max={20}
        step={0.5}
        value={local}
        disabled={disabled}
        onValueChange={setLocal}
        onValueCommit={onCommit}
      />
    </Field>
  );
}

function FileNameField({ job, preset, disabled }: { job: Job; preset: Preset; disabled: boolean }) {
  const t = useT();
  const stem = basename(job.input_path).replace(/\.[^.]+$/, "");
  const [value, setValue] = useState(job.options.output_name ?? "");
  useEffect(() => setValue(job.options.output_name ?? ""), [job.options.output_name]);
  const commit = () => {
    const next = value.trim();
    const normalized = !next || next === stem ? null : next;
    if (normalized !== job.options.output_name) void updateOptions([job.id], { output_name: normalized });
  };
  return (
    <Field label={t("opt.fileName")}>
      <div className="flex h-9 items-center rounded-lg border border-border bg-surface shadow-card transition focus-within:border-accent focus-within:ring-2 focus-within:ring-ring">
        <input
          value={value}
          placeholder={stem}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()}
          className="h-full min-w-0 flex-1 bg-transparent px-3 text-sm text-fg outline-none placeholder:text-subtle disabled:opacity-50"
        />
        <span className="pr-3 text-sm text-subtle">{preset.extension}</span>
      </div>
    </Field>
  );
}

export function OutputPanel({ jobs, locked }: { jobs: Job[]; locked: boolean }) {
  const t = useT();
  const lang = useLang();
  const [job] = jobs;
  const ids = jobs.map((j) => j.id);
  const multi = jobs.length > 1;
  const presets = useStore((s) => s.presets);
  const settings = useStore((s) => s.settings);
  const canTonemap = useStore((s) => s.system?.ffmpeg.can_tonemap ?? false);
  const preset = presets.find((p) => p.id === job.options.preset_id);
  const [pickerOpen, setPickerOpen] = useState(false);
  if (!preset) return null;

  const options = job.options;
  const update = (patch: Partial<JobOptions>) => void updateOptions(ids, patch);
  const video = jobs.find((j) => j.media.video)?.media.video ?? null;
  const hasAudio = jobs.some((j) => j.media.audio.length > 0);
  const spec = preset.video;
  const encodesVideo = !!spec && !!video && !preset.remux;
  const showQuality = encodesVideo && ["crf", "bitrate", "quality"].includes(spec.rate_control);
  const showSize = encodesVideo && spec.rate_control === "size";
  const showResolution = encodesVideo;
  const targetMb = options.quality ?? spec?.quality ?? 10;
  const audioKbps = options.audio_bitrate_kbps ?? preset.audio?.bitrate_kbps ?? null;
  const plan = showSize && !multi ? sizePlan(job.media, targetMb, audioKbps) : null;

  let hdrNote: string | null = null;
  if (encodesVideo && jobs.some((j) => j.media.video?.hdr)) {
    hdrNote = keepsHdr(preset) ? t("opt.hdrKept") : canTonemap ? t("opt.hdrTonemap") : t("opt.hdrNoTonemap");
  }

  const choosePreset = (next: Preset) => {
    setPickerOpen(false);
    for (const item of jobs) void updateOptions([item.id], presetPatch(item, next));
  };

  let resolution: ReactNode = null;
  let outputShortSide: string | null = null;
  if (showResolution && video) {
    const [w, h] = displaySize(video);
    const short = Math.min(w, h);
    const chosen = options.max_height ? options.max_height : options.max_height === 0 ? null : plan?.shortSide;
    outputShortSide = `${Math.min(short, chosen ?? short)}p`;
    if (preset.fixed_resolution) {
      resolution = (
        <Field label={t("opt.resolution")}>
          <Note>{t("opt.res.fixed", { value: frameLabel(preset.frame) })}</Note>
        </Field>
      );
    } else {
      const presetDefault = spec?.max_height && !spec.max_width ? spec.max_height : null;
      const autoLabel = plan
        ? t("opt.res.auto", { value: plan.shortSide && plan.shortSide < short ? `${plan.shortSide}p` : `${short}p` })
        : t("opt.res.autoPlain");
      const choices = [
        ...(showSize ? [{ value: "preset", label: autoLabel }] : []),
        ...(presetDefault ? [{ value: "preset", label: t("opt.res.preset", { value: `${presetDefault}p` }) }] : []),
        { value: "0", label: t("opt.res.original", { value: `${w}×${h}` }) },
        ...HEIGHTS.filter((height) => height < short).map((height) => ({
          value: String(height),
          label: height === 2160 ? "4K · 2160p" : `${height}p`,
        })),
      ];
      const current =
        options.max_height == null ? (presetDefault || showSize ? "preset" : "0") : String(options.max_height);
      resolution = (
        <Field label={t("opt.resolution")}>
          <Select
            aria-label={t("opt.resolution")}
            value={choices.some((c) => c.value === current) ? current : "0"}
            options={choices}
            disabled={locked}
            onValueChange={(value) => update({ max_height: value === "preset" ? null : Number(value) })}
          />
        </Field>
      );
    }
  }

  const outputDir = options.output_dir ?? settings?.output_dir ?? null;

  return (
    <div className="space-y-6">
      <Field label={t("opt.format")}>
        <button
          onClick={() => setPickerOpen(true)}
          disabled={locked}
          className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface p-3 text-left shadow-card outline-none transition hover:border-border-strong focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
        >
          <PresetIcon preset={preset} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-fg">{localized(preset.name, lang)}</div>
            <div className="truncate text-xs text-muted">{localized(preset.description, lang)}</div>
          </div>
          <span className="text-xs font-semibold text-accent">{t("opt.change")}</span>
        </button>
        <div className="flex flex-wrap gap-1">
          <Badge>{preset.extension}</Badge>
          {preset.tags.map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>
      </Field>

      {preset.remux && <Note>{t("opt.remuxNote")}</Note>}
      {preset.category === "editing" && <Note>{t("opt.editingNote")}</Note>}
      {!preset.audio && !!spec?.fps && <Note>{t("opt.animationNote", { fps: spec.fps })}</Note>}
      {hdrNote && <Note>{hdrNote}</Note>}

      {(showQuality || showSize || spec?.speed_family || showResolution) && (
        <div className="space-y-5">
          <SectionTitle>{t("info.video")}</SectionTitle>
          {showQuality && (
            <QualityField preset={preset} options={options} disabled={locked} onCommit={(q) => update({ quality: q })} />
          )}
          {showSize && (
            <SizeField
              preset={preset}
              value={targetMb}
              plan={plan}
              resolution={outputShortSide}
              disabled={locked}
              onCommit={(q) => update({ quality: q })}
            />
          )}
          {spec?.speed_family && video && (
            <Field label={t("opt.speed")} hint={t("opt.speedHint")}>
              <Segmented<Speed>
                className="w-full"
                value={options.speed}
                disabled={locked}
                onValueChange={(speed) => update({ speed })}
                options={[
                  { value: "fast", label: t("opt.speed.fast") },
                  { value: "balanced", label: t("opt.speed.balanced") },
                  { value: "quality", label: t("opt.speed.quality") },
                ]}
              />
            </Field>
          )}
          {resolution}
        </div>
      )}

      {preset.audio && hasAudio && !preset.remux && (
        <div className="space-y-5">
          <SectionTitle>{t("opt.audio")}</SectionTitle>
          {preset.audio.bitrate_choices.length > 0 && (
            <Field label={t("opt.audioBitrate")}>
              <Select
                aria-label={t("opt.audioBitrate")}
                value={String(options.audio_bitrate_kbps ?? preset.audio.bitrate_kbps)}
                disabled={locked}
                options={preset.audio.bitrate_choices.map((kbps) => ({ value: String(kbps), label: `${kbps} kb/s` }))}
                onValueChange={(value) => update({ audio_bitrate_kbps: Number(value) })}
              />
            </Field>
          )}
          <VolumeField value={options.volume_db} disabled={locked} onCommit={(volume_db) => update({ volume_db })} />
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="block text-[13px] font-medium text-fg">{t("opt.normalize")}</span>
              <span className="block text-xs text-subtle">{t("opt.normalizeHint")}</span>
            </span>
            <Switch
              checked={options.normalize_audio}
              disabled={locked}
              onCheckedChange={(normalize_audio) => update({ normalize_audio })}
            />
          </label>
        </div>
      )}

      <div className="space-y-5">
        <SectionTitle>{t("opt.destination")}</SectionTitle>
        <div className="flex items-center gap-2 rounded-xl border border-border bg-surface p-2 pl-3 shadow-card">
          <Folder className="size-4 shrink-0 text-subtle" />
          <span className="min-w-0 flex-1 truncate text-[13px] text-fg" title={outputDir ?? undefined}>
            {outputDir ?? t("opt.nextToOriginal")}
          </span>
          {options.output_dir && (
            <Button variant="ghost" size="xs" disabled={locked} onClick={() => update({ output_dir: null })}>
              {t("opt.reset")}
            </Button>
          )}
          <Button
            size="xs"
            disabled={locked}
            onClick={async () => {
              const [dir] = await pickPaths("folder");
              if (dir) update({ output_dir: dir });
            }}
          >
            {t("opt.change")}
          </Button>
        </div>
        {!multi && <FileNameField job={job} preset={preset} disabled={locked} />}
        {!multi && (
          <p className="break-all text-xs text-subtle" title={job.output_path}>
            {t("opt.outputPath", { path: job.output_path })}
          </p>
        )}
      </div>

      <PresetPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        value={preset.id}
        onSelect={choosePreset}
        audioOnly={!video}
      />
    </div>
  );
}
