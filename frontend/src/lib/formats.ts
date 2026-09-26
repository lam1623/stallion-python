import { localized, type Lang, type Translator } from "./i18n";
import { frameLabel, keepsHdr } from "./presets";
import type { FormatDraft, HardwareInfo, Preset } from "./types";

// Mirrors stallion/engine/custom.py: the editor offers only what the server accepts

type VideoCodec = FormatDraft["video_codec"];
type AudioCodec = FormatDraft["audio_codec"];
type Container = FormatDraft["container"];

export const VIDEO_CODECS: Record<Exclude<VideoCodec, "copy" | "none">, { crf: [number, number, number]; tenBit: boolean }> = {
  h264: { crf: [21, 14, 34], tenBit: false },
  hevc: { crf: [24, 16, 34], tenBit: true },
  av1: { crf: [32, 20, 50], tenBit: true },
  vp9: { crf: [32, 15, 45], tenBit: true },
};

export const AUDIO_CODECS: Record<Exclude<AudioCodec, "copy" | "none">, { bitrate: number | null; choices: number[] }> = {
  aac: { bitrate: 192, choices: [96, 128, 160, 192, 224, 256, 320, 384] },
  opus: { bitrate: 128, choices: [64, 96, 128, 160, 192, 256] },
  mp3: { bitrate: 192, choices: [128, 160, 192, 256, 320] },
  flac: { bitrate: null, choices: [] },
};

export const CONTAINERS: Record<Container, { label: string; video: VideoCodec[]; audio: AudioCodec[] }> = {
  mp4: { label: "MP4", video: ["h264", "hevc", "av1", "copy"], audio: ["aac", "mp3", "copy", "none"] },
  mkv: { label: "MKV", video: ["h264", "hevc", "av1", "vp9", "copy"], audio: ["aac", "opus", "mp3", "flac", "copy", "none"] },
  webm: { label: "WebM", video: ["av1", "vp9"], audio: ["opus", "none"] },
  mov: { label: "MOV", video: ["h264", "hevc", "copy"], audio: ["aac", "copy", "none"] },
  m4a: { label: "M4A", video: ["none"], audio: ["aac"] },
  mp3: { label: "MP3", video: ["none"], audio: ["mp3"] },
  opus: { label: "Opus", video: ["none"], audio: ["opus"] },
  flac: { label: "FLAC", video: ["none"], audio: ["flac"] },
};

export const VIDEO_CONTAINERS: Container[] = ["mp4", "mkv", "webm", "mov"];
/** Audio-only files: the container follows the codec */
export const AUDIO_CONTAINER: Record<string, Container> = { aac: "m4a", mp3: "mp3", opus: "opus", flac: "flac" };
export const RESOLUTIONS = [2160, 1440, 1080, 720, 480, 360];
export const FRAME_RATES = [60, 50, 30, 25, 24];

export const EMPTY_DRAFT: FormatDraft = {
  name: "",
  description: "",
  container: "mp4",
  video_codec: "h264",
  quality: null,
  ten_bit: false,
  max_height: null,
  fps: null,
  accel: "auto",
  audio_codec: "aac",
  audio_bitrate: null,
  audio_channels: "source",
  extra_args: "",
};

/** Keep a draft valid after the container changed: first allowed codec wins. */
export function fitContainer(draft: FormatDraft, container: Container): FormatDraft {
  const box = CONTAINERS[container];
  const video = box.video.includes(draft.video_codec) ? draft.video_codec : box.video[0];
  const audio = box.audio.includes(draft.audio_codec) ? draft.audio_codec : box.audio[0];
  return withVideoCodec({ ...draft, container, audio_codec: audio, ...audioReset(draft, audio) }, video);
}

function audioReset(draft: FormatDraft, audio: AudioCodec): Partial<FormatDraft> {
  return audio === draft.audio_codec ? {} : { audio_bitrate: null };
}

export function withVideoCodec(draft: FormatDraft, video: VideoCodec): FormatDraft {
  if (video === draft.video_codec) return draft;
  const spec = video in VIDEO_CODECS ? VIDEO_CODECS[video as keyof typeof VIDEO_CODECS] : null;
  return {
    ...draft,
    video_codec: video,
    quality: null,
    ten_bit: draft.ten_bit && !!spec?.tenBit,
    max_height: video === "copy" || video === "none" ? null : draft.max_height,
    fps: video === "copy" || video === "none" ? null : draft.fps,
  };
}

export function withAudioCodec(draft: FormatDraft, audio: AudioCodec): FormatDraft {
  const container = draft.video_codec === "none" ? AUDIO_CONTAINER[audio] ?? draft.container : draft.container;
  return { ...draft, audio_codec: audio, container, audio_bitrate: audio === draft.audio_codec ? draft.audio_bitrate : null };
}

export const CODEC_LABELS: Record<string, string> = {
  h264: "H.264",
  hevc: "HEVC",
  av1: "AV1",
  vp9: "VP9",
  aac: "AAC",
  opus: "Opus",
  mp3: "MP3",
  flac: "FLAC",
  libx264: "H.264",
  libx265: "H.265 / HEVC",
  libsvtav1: "AV1",
  "libaom-av1": "AV1",
  "libvpx-vp9": "VP9",
  libwebp_anim: "WebP",
  gif: "GIF",
  prores_ks: "Apple ProRes",
  dnxhd: "Avid DNxHR",
  libxvid: "Xvid (MPEG-4)",
  wmv2: "Windows Media Video 8",
  mpeg2video: "MPEG-2",
  mpeg1video: "MPEG-1",
  libopus: "Opus",
  libmp3lame: "MP3",
  alac: "Apple Lossless",
  pcm_s16le: "PCM 16 bits",
  pcm_s24le: "PCM 24 bits",
  ac3: "Dolby Digital (AC-3)",
  mp2: "MPEG-1 Layer II",
  wmav2: "Windows Media Audio",
  mov_text: "mov_text",
  webvtt: "WebVTT",
};

const MUXERS: Record<string, string> = {
  mp4: "MP4",
  matroska: "Matroska",
  webm: "WebM",
  mov: "QuickTime",
  ipod: "MPEG-4 Audio",
  mp3: "MP3",
  opus: "Ogg Opus",
  flac: "FLAC",
  wav: "WAV",
  avi: "AVI",
  asf: "ASF",
  flv: "Flash Video",
  gif: "GIF",
  webp: "WebP",
};

export interface ParamCard {
  title: "param.container" | "param.video" | "param.audio" | "param.extras";
  rows: { label: string; value: string; mono?: boolean }[];
}

function pixelLabel(pixFmt: string | null): string | null {
  if (!pixFmt) return null;
  const depth = /12/.test(pixFmt) ? "12 bits" : /10/.test(pixFmt) ? "10 bits" : "8 bits";
  const chroma = /444/.test(pixFmt) ? "4:4:4" : /422/.test(pixFmt) ? "4:2:2" : "4:2:0";
  return `${depth} ${chroma} · ${pixFmt}`;
}

/** The settings behind a format, as the Formats page shows them. */
export function describePreset(preset: Preset, t: Translator, lang: Lang, hardware?: HardwareInfo): ParamCard[] {
  const spec = preset.video;
  const audio = preset.audio;
  const container: ParamCard = { title: "param.container", rows: [] };
  const muxer = preset.muxer ? (MUXERS[preset.muxer] ?? preset.muxer) : null;
  container.rows.push({ label: t("param.format"), value: `${muxer ?? preset.extension.slice(1).toUpperCase()} (${preset.extension})` });
  if (preset.target) container.rows.push({ label: t("param.format"), value: t("val.target", { target: preset.target.toUpperCase() }) });
  if (preset.remux) container.rows.push({ label: t("param.tracks"), value: t("val.remux") });
  if (preset.output_args.join(" ").includes("faststart")) container.rows.push({ label: "Web", value: t("val.faststart") });

  const video: ParamCard = { title: "param.video", rows: [] };
  if (!spec) video.rows.push({ label: t("param.video"), value: t("val.none") });
  else if (spec.codec === "copy") video.rows.push({ label: t("param.codec"), value: t("val.copy") });
  else {
    video.rows.push({ label: t("param.codec"), value: `${CODEC_LABELS[spec.codec] ?? spec.codec} · ${spec.codec}` });
    const q = spec.quality;
    let quality = t("val.fixed");
    if (spec.rate_control === "crf" && q != null)
      quality = t("val.crf", { value: q, min: spec.quality_min ?? q, max: spec.quality_max ?? q });
    else if (spec.rate_control === "bitrate" && q != null) quality = t("val.choosable", { value: t("val.kbps", { value: q }) });
    else if (spec.rate_control === "quality" && q != null) quality = t("val.q100", { value: q });
    else if (spec.rate_control === "size" && q != null) quality = t("val.targetMb", { value: q });
    video.rows.push({ label: t("param.quality"), value: quality });
    if (spec.speed_family) video.rows.push({ label: t("param.speed"), value: t("val.speedAdjustable") });
    const pixels = pixelLabel(spec.pix_fmt);
    if (pixels) video.rows.push({ label: t("param.color"), value: pixels });
    video.rows.push({ label: t("param.hdr"), value: keepsHdr(preset) ? t("val.hdrKept") : t("val.hdrToSdr") });
    if (preset.layout === "blur_fill" && preset.frame)
      video.rows.push({ label: t("param.frame"), value: t("val.blurFill", { frame: frameLabel(preset.frame) }) });
    else if (preset.fixed_resolution && preset.frame) video.rows.push({ label: t("param.frame"), value: frameLabel(preset.frame) });
    else if (spec.max_width && spec.max_height)
      video.rows.push({ label: t("param.maxRes"), value: `${spec.max_width}×${spec.max_height}` });
    else if (spec.max_height) video.rows.push({ label: t("param.maxRes"), value: `${spec.max_height}p` });
    if (spec.fps) video.rows.push({ label: t("param.fps"), value: t("val.maxFps", { fps: spec.fps }) });
    const gpu = hardware?.presets.includes(preset.id);
    video.rows.push({
      label: t("param.engine"),
      value: gpu ? t("val.gpuOrCpu", { label: hardware?.label ?? "GPU" }) : t("val.cpu"),
    });
  }

  const sound: ParamCard = { title: "param.audio", rows: [] };
  if (!audio) sound.rows.push({ label: t("param.audio"), value: t("val.none") });
  else if (audio.codec === "copy") sound.rows.push({ label: t("param.codec"), value: preset.remux ? t("val.copyAll") : t("val.copy") });
  else {
    sound.rows.push({ label: t("param.codec"), value: `${CODEC_LABELS[audio.codec] ?? audio.codec} · ${audio.codec}` });
    const lossless = ["flac", "alac", "pcm_s16le", "pcm_s24le"].includes(audio.codec);
    const rate = audio.bitrate_kbps ? t("val.kbps", { value: audio.bitrate_kbps }) : null;
    sound.rows.push({
      label: t("param.bitrate"),
      value: lossless ? t("val.lossless") : rate ? (audio.bitrate_choices.length ? t("val.choosable", { value: rate }) : rate) : t("val.fixed"),
    });
    const channels = audio.channels === 2 ? t("val.stereo") : audio.channels === 1 ? t("val.mono") : audio.channels ? String(audio.channels) : t("val.source");
    sound.rows.push({ label: t("param.channels"), value: channels });
    if (audio.sample_rate) sound.rows.push({ label: t("param.sampleRate"), value: `${(audio.sample_rate / 1000).toLocaleString(lang)} kHz` });
  }

  const extras: ParamCard = { title: "param.extras", rows: [] };
  if (spec && spec.codec !== "copy") {
    const soft = preset.soft_subtitles;
    extras.rows.push({
      label: t("param.subtitles"),
      value:
        soft === "copy"
          ? t("val.subsAll")
          : soft
            ? t("val.subsText", { codec: CODEC_LABELS[soft] ?? soft })
            : t("val.subsBurn"),
    });
  } else if (preset.soft_subtitles === "copy") {
    extras.rows.push({ label: t("param.subtitles"), value: t("val.subsAll") });
  }
  // Quiet-logging switches are plumbing, not settings worth showing
  const pairs = [...(spec?.args ?? []), ...(audio?.args ?? [])].flatMap((arg, i, all) => (i % 2 ? [] : [[arg, all[i + 1]]]));
  const options = pairs.filter(([key, value]) => !(key === "-x265-params" && value === "log-level=error")).flat();
  if (options.length) extras.rows.push({ label: t("param.options"), value: options.join(" "), mono: true });
  const cards = [container, video, sound];
  if (extras.rows.length) cards.push(extras);
  return cards;
}

/** Short line under a format's name in the list. */
export function presetSummary(preset: Preset, lang: Lang): string {
  if (preset.custom) return preset.tags.join(" · ");
  return localized(preset.description, lang);
}

export function issueParams(params: Record<string, string | number>, t: Translator): Record<string, string | number> {
  const out: Record<string, string | number> = { ...params };
  if (typeof out.codec === "string") out.codec = out.codec === "copy" ? t("editor.copy") : (CODEC_LABELS[out.codec] ?? out.codec);
  if (typeof out.field === "string") {
    const field = out.field.replace(/^draft\./, "");
    out.field = field === "name" ? t("editor.name") : field;
  }
  return out;
}
