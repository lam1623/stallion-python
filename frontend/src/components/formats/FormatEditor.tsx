import { AlertTriangle, ArrowLeft, Check, CircleX, Cpu, Gpu, Sparkles } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";
import { errorText } from "@/lib/actions";
import { api } from "@/lib/api";
import {
  AUDIO_CODECS,
  AUDIO_CONTAINER,
  CODEC_LABELS,
  CONTAINERS,
  FRAME_RATES,
  fitContainer,
  issueParams,
  RESOLUTIONS,
  VIDEO_CODECS,
  VIDEO_CONTAINERS,
  withAudioCodec,
  withVideoCodec,
} from "@/lib/formats";
import { hasKey, type TranslationKey, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { Accel, FormatDraft, FormatIssue, FormatPreview } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { Input, Segmented, Select, Slider } from "../ui/controls";
import { Field, SectionTitle } from "../ui/misc";

type VideoCodec = FormatDraft["video_codec"];
type AudioCodec = FormatDraft["audio_codec"];

function Card({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-5 rounded-2xl border border-border bg-surface p-5 shadow-card">
      <SectionTitle>{title}</SectionTitle>
      {children}
    </section>
  );
}

function IssueList({ issues, tone }: { issues: FormatIssue[]; tone: "error" | "warning" }) {
  const t = useT();
  const Icon = tone === "error" ? CircleX : AlertTriangle;
  return (
    <ul
      className={cn(
        "space-y-1.5 rounded-xl border p-3 text-[13px] leading-relaxed",
        tone === "error" ? "border-danger/25 bg-danger/10 text-danger" : "border-warning/25 bg-warning/10 text-warning",
      )}
    >
      {issues.map((issue, index) => {
        const key = `fmt.${tone === "error" ? "err" : "warn"}.${issue.code}`;
        return (
          <li key={index} className="flex gap-2">
            <Icon className="mt-0.5 size-4 shrink-0" />
            <span>{hasKey(key) ? t(key as TranslationKey, issueParams(issue.params, t)) : issue.message}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Choice cards for the encoder preference, with a note under each. */
function AccelChoice({ draft, onChange }: { draft: FormatDraft; onChange: (accel: Accel) => void }) {
  const t = useT();
  const hardware = useStore((s) => s.system?.hardware);
  const gpuCodec = ["h264", "hevc", "av1"].includes(draft.video_codec);
  const disabled = !gpuCodec;
  const gpuNote = !gpuCodec
    ? t("editor.accel.noCodec", { codec: CODEC_LABELS[draft.video_codec] ?? t("editor.copy") })
    : hardware?.available
      ? `${hardware.label} · ${t("editor.accel.gpuNote")}`
      : t("editor.accel.noGpu");
  const options: { value: Accel; icon: ReactNode; label: string; note: string }[] = [
    { value: "auto", icon: <Sparkles />, label: t("editor.accel.auto"), note: t("editor.accel.autoNote") },
    { value: "cpu", icon: <Cpu />, label: t("editor.accel.cpu"), note: t("editor.accel.cpuNote") },
    { value: "gpu", icon: <Gpu />, label: t("editor.accel.gpu"), note: gpuNote },
  ];
  return (
    <div role="radiogroup" aria-label={t("editor.accel")} className="grid gap-2 sm:grid-cols-3">
      {options.map((option) => {
        const active = draft.accel === option.value;
        return (
          <button
            key={option.value}
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "flex flex-col items-start gap-1 rounded-xl border p-3 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:size-4",
              active ? "border-accent/60 bg-accent-soft" : "border-border bg-surface hover:border-border-strong",
            )}
          >
            <span className="flex items-center gap-2 text-[13px] font-semibold text-fg">
              <span className={active ? "text-accent" : "text-subtle"}>{option.icon}</span>
              {option.label}
            </span>
            <span className="text-xs leading-snug text-muted">{option.note}</span>
          </button>
        );
      })}
    </div>
  );
}

function QualitySlider({ draft, onChange }: { draft: FormatDraft; onChange: (quality: number) => void }) {
  const t = useT();
  const spec = VIDEO_CODECS[draft.video_codec as keyof typeof VIDEO_CODECS];
  const [fallback, min, max] = spec.crf;
  const value = draft.quality ?? fallback;
  // CRF: lower is better, so the slider is mirrored to keep "better" on the right
  const [position, setPosition] = useState(min + max - value);
  useEffect(() => setPosition(min + max - value), [value, min, max]);
  const shown = min + max - position;
  return (
    <Field label={t("editor.quality")} aside={`CRF ${shown}`}>
      <Slider
        aria-label={t("editor.quality")}
        min={min}
        max={max}
        value={position}
        onValueChange={setPosition}
        onValueCommit={(next) => onChange(min + max - next)}
      />
      <div className="flex justify-between text-[11px] text-subtle">
        <span>{t("opt.smaller")}</span>
        <span>{t("opt.better")}</span>
      </div>
    </Field>
  );
}

function usePreview(draft: FormatDraft): FormatPreview | null {
  const t = useT();
  const [preview, setPreview] = useState<FormatPreview | null>(null);
  const key = JSON.stringify(draft);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      // An empty name is fine while typing: check the rest with a placeholder
      const body = { ...draft, name: draft.name.trim() || t("editor.namePlaceholder") };
      api
        .previewFormat(body)
        .then((result) => alive && setPreview(result))
        .catch(() => alive && setPreview(null));
    }, 220);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // The serialized draft is the real dependency
    // (a new object with the same content must not refetch)
  }, [key, t]); // eslint-disable-line react-hooks/exhaustive-deps
  return preview;
}

export function FormatEditor({
  presetId,
  initial,
  onClose,
}: {
  presetId: string | null;
  initial: FormatDraft;
  onClose: (savedId?: string) => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState<FormatDraft>(initial);
  const [saving, setSaving] = useState(false);
  const preview = usePreview(draft);
  const patch = (next: Partial<FormatDraft>) => setDraft((current) => ({ ...current, ...next }));
  const audioOnly = draft.video_codec === "none";
  const box = CONTAINERS[draft.container];
  const encodes = draft.video_codec in VIDEO_CODECS;
  const sound = draft.audio_codec in AUDIO_CODECS ? AUDIO_CODECS[draft.audio_codec as keyof typeof AUDIO_CODECS] : null;
  const canSave = !!draft.name.trim() && !!preview?.ok && !saving;

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...draft, name: draft.name.trim(), description: draft.description.trim() };
      const saved = presetId ? await api.updateFormat(presetId, body) : await api.createFormat(body);
      toast.success(t("formats.saved"));
      onClose(saved.id);
    } catch (error) {
      toast.error(errorText(error));
      setSaving(false);
    }
  };

  const videoCodecs: { value: VideoCodec; label: string }[] = [
    { value: "h264", label: "H.264" },
    { value: "hevc", label: "H.265 / HEVC" },
    { value: "av1", label: "AV1" },
    { value: "vp9", label: "VP9" },
    { value: "copy", label: t("editor.copy") },
  ];
  const audioCodecs: { value: AudioCodec; label: string }[] = audioOnly
    ? [
        { value: "aac", label: "AAC · M4A" },
        { value: "mp3", label: "MP3" },
        { value: "opus", label: "Opus" },
        { value: "flac", label: "FLAC" },
      ]
    : [
        { value: "aac", label: "AAC" },
        { value: "opus", label: "Opus" },
        { value: "mp3", label: "MP3" },
        { value: "flac", label: "FLAC" },
        { value: "copy", label: t("editor.copy") },
        { value: "none", label: t("editor.noAudio") },
      ];

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-4">
        <Button variant="ghost" size="icon" aria-label={t("editor.cancel")} onClick={() => onClose()}>
          <ArrowLeft />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-subtle">{t("formats.title")}</p>
          <h1 className="truncate text-lg font-semibold tracking-tight text-fg">
            {presetId ? t("editor.editTitle") : t("editor.newTitle")}
          </h1>
        </div>
        <Button variant="ghost" onClick={() => onClose()}>
          {t("editor.cancel")}
        </Button>
        <Button variant="primary" disabled={!canSave} onClick={() => void save()}>
          <Check />
          {t("editor.save")}
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-6xl items-start gap-6 px-6 py-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            <Card title={t("editor.kind")}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("editor.name")}>
                  <Input
                    autoFocus
                    value={draft.name}
                    maxLength={60}
                    placeholder={t("editor.namePlaceholder")}
                    onChange={(event) => patch({ name: event.target.value })}
                  />
                </Field>
                <Field label={t("editor.description")}>
                  <Input
                    value={draft.description}
                    maxLength={200}
                    placeholder={t("editor.descriptionPlaceholder")}
                    onChange={(event) => patch({ description: event.target.value })}
                  />
                </Field>
              </div>
              <Field label={t("editor.kind")}>
                <Segmented<"video" | "audio">
                  className="w-full"
                  value={audioOnly ? "audio" : "video"}
                  onValueChange={(kind) =>
                    setDraft((current) =>
                      kind === "audio"
                        ? withAudioCodec(
                            { ...withVideoCodec(current, "none"), container: "m4a", accel: "auto" },
                            current.audio_codec in AUDIO_CONTAINER ? current.audio_codec : "aac",
                          )
                        : fitContainer({ ...current, video_codec: "h264", quality: null }, "mp4"),
                    )
                  }
                  options={[
                    { value: "video", label: t("editor.kind.video") },
                    { value: "audio", label: t("editor.kind.audio") },
                  ]}
                />
              </Field>
              {!audioOnly && (
                <Field label={t("editor.container")}>
                  <Segmented<string>
                    className="w-full"
                    value={draft.container}
                    onValueChange={(container) => setDraft((current) => fitContainer(current, container as FormatDraft["container"]))}
                    options={VIDEO_CONTAINERS.map((value) => ({ value, label: CONTAINERS[value].label }))}
                  />
                </Field>
              )}
            </Card>

            {!audioOnly && (
              <Card title={t("param.video")}>
                <Field label={t("editor.videoCodec")}>
                  <Segmented<VideoCodec>
                    className="w-full"
                    value={draft.video_codec}
                    onValueChange={(codec) => setDraft((current) => withVideoCodec(current, codec))}
                    options={videoCodecs.map((option) => ({
                      ...option,
                      disabled: !box.video.includes(option.value),
                      hint: box.video.includes(option.value)
                        ? undefined
                        : t("fmt.err.video_container", { codec: option.label, container: box.label }),
                    }))}
                  />
                </Field>
                <Field label={t("editor.accel")}>
                  <AccelChoice draft={draft} onChange={(accel) => patch({ accel })} />
                </Field>
                {encodes && <QualitySlider draft={draft} onChange={(quality) => patch({ quality })} />}
                <div className="grid gap-4 sm:grid-cols-3">
                  <Field label={t("editor.depth")}>
                    <Segmented<string>
                      className="w-full"
                      size="sm"
                      value={draft.ten_bit ? "10" : "8"}
                      disabled={!encodes}
                      onValueChange={(depth) => patch({ ten_bit: depth === "10" })}
                      options={[
                        { value: "8", label: t("editor.depth.8") },
                        {
                          value: "10",
                          label: t("editor.depth.10"),
                          disabled: !VIDEO_CODECS[draft.video_codec as keyof typeof VIDEO_CODECS]?.tenBit,
                        },
                      ]}
                    />
                  </Field>
                  <Field label={t("editor.maxRes")}>
                    <Select<string>
                      aria-label={t("editor.maxRes")}
                      value={String(draft.max_height ?? "source")}
                      disabled={!encodes}
                      onValueChange={(value) => patch({ max_height: value === "source" ? null : Number(value) })}
                      options={[
                        { value: "source", label: t("editor.original") },
                        ...RESOLUTIONS.map((h) => ({ value: String(h), label: h === 2160 ? "4K · 2160p" : `${h}p` })),
                      ]}
                    />
                  </Field>
                  <Field label={t("editor.fps")}>
                    <Select<string>
                      aria-label={t("editor.fps")}
                      value={String(draft.fps ?? "source")}
                      disabled={!encodes}
                      onValueChange={(value) => patch({ fps: value === "source" ? null : Number(value) })}
                      options={[
                        { value: "source", label: t("editor.fpsSource") },
                        ...FRAME_RATES.map((fps) => ({ value: String(fps), label: `${fps} fps` })),
                      ]}
                    />
                  </Field>
                </div>
              </Card>
            )}

            <Card title={t("param.audio")}>
              <Field label={t("editor.audioCodec")}>
                <Segmented<AudioCodec>
                  className="w-full"
                  value={draft.audio_codec}
                  onValueChange={(codec) => setDraft((current) => withAudioCodec(current, codec))}
                  options={audioCodecs.map((option) => ({
                    ...option,
                    disabled: !audioOnly && !box.audio.includes(option.value),
                    hint:
                      audioOnly || box.audio.includes(option.value)
                        ? undefined
                        : t("fmt.err.audio_container", { codec: option.label, container: box.label }),
                  }))}
                />
              </Field>
              {sound && sound.choices.length > 0 && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t("editor.audioBitrate")}>
                    <Select<string>
                      aria-label={t("editor.audioBitrate")}
                      value={String(draft.audio_bitrate ?? "default")}
                      onValueChange={(value) => patch({ audio_bitrate: value === "default" ? null : Number(value) })}
                      options={[
                        { value: "default", label: t("editor.defaultBitrate", { value: sound.bitrate ?? "" }) },
                        ...sound.choices.map((kbps) => ({ value: String(kbps), label: `${kbps} kb/s` })),
                      ]}
                    />
                  </Field>
                  <Field label={t("editor.channels")}>
                    <Segmented<FormatDraft["audio_channels"]>
                      className="w-full"
                      value={draft.audio_channels}
                      onValueChange={(audio_channels) => patch({ audio_channels })}
                      options={[
                        { value: "source", label: t("editor.original") },
                        { value: "stereo", label: t("val.stereo") },
                        { value: "mono", label: t("val.mono") },
                      ]}
                    />
                  </Field>
                </div>
              )}
            </Card>

            <Card title={t("editor.extra")}>
              <Field label={t("editor.extra")} hint={t("editor.extraHint")}>
                <Input
                  value={draft.extra_args}
                  maxLength={400}
                  spellCheck={false}
                  placeholder="-tune film -g 48"
                  onChange={(event) => patch({ extra_args: event.target.value })}
                  className="font-mono text-[13px]"
                />
              </Field>
            </Card>
          </div>

          <aside className="space-y-4 lg:sticky lg:top-6">
            <section className="space-y-4 rounded-2xl border border-border bg-surface p-5 shadow-card">
              <SectionTitle>{t("editor.preview")}</SectionTitle>
              <div className="flex items-center gap-3">
                <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-brand text-[13px] font-bold text-white">
                  {(preview?.extension ?? `.${draft.container}`).slice(1).toUpperCase()}
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-fg">
                    {draft.name.trim() || t("editor.namePlaceholder")}
                  </div>
                  <div className="truncate text-xs text-muted">{(preview?.tags ?? []).join(" · ") || "…"}</div>
                </div>
              </div>
              {preview?.ok && preview.encoder && (
                <p className="flex items-center gap-2 text-xs text-muted">
                  <span
                    className={cn(
                      "rounded-md px-1.5 py-0.5 text-[10.5px] font-bold text-fg",
                      preview.engine === "gpu" ? "bg-viz-gpu/15" : "bg-viz-cpu/15",
                    )}
                  >
                    {preview.engine === "gpu" ? "GPU" : "CPU"}
                  </span>
                  {t("editor.encodesOn", { engine: preview.engine === "gpu" ? "GPU" : "CPU", encoder: preview.encoder })}
                </p>
              )}
              <div className="space-y-1.5">
                <div className="text-xs font-medium text-muted">{t("editor.command")}</div>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-xl border border-border bg-bg px-3.5 py-3 font-mono text-[11.5px] leading-relaxed text-muted">
                  {preview?.command ?? (preview ? "—" : t("editor.checking"))}
                </pre>
              </div>
              {preview && preview.errors.length > 0 && <IssueList issues={preview.errors} tone="error" />}
              {preview && preview.warnings.length > 0 && <IssueList issues={preview.warnings} tone="warning" />}
              {preview?.ok && preview.warnings.length === 0 && (
                <p className="flex items-center gap-2 text-[13px] font-medium text-success">
                  <Check className="size-4" />
                  {t("editor.compatible")}
                </p>
              )}
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
}
