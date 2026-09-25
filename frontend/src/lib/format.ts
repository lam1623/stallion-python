import type { Lang } from "./i18n";
import type { AudioStream, MediaInfo, VideoStream } from "./types";

const LANGUAGE_ALIASES: Record<string, string> = {
  eng: "en", spa: "es", fre: "fr", fra: "fr", ger: "de", deu: "de", ita: "it", por: "pt", jpn: "ja",
  chi: "zh", zho: "zh", kor: "ko", rus: "ru", ara: "ar", dut: "nl", nld: "nl", pol: "pl", tur: "tr",
  swe: "sv", nor: "no", dan: "da", fin: "fi", cat: "ca", glg: "gl", baq: "eu", eus: "eu", hin: "hi",
  heb: "he", gre: "el", ell: "el", cze: "cs", ces: "cs", hun: "hu", rum: "ro", ron: "ro", ukr: "uk",
  tha: "th", vie: "vi", ind: "id", may: "ms", msa: "ms",
};

export function formatBytes(bytes: number | null | undefined, lang: Lang): string {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / 1024 ** exponent;
  const digits = exponent >= 2 && value < 100 ? 1 : 0;
  return `${value.toLocaleString(lang, { maximumFractionDigits: digits })} ${units[exponent]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  return h ? `${h}:${mm}:${String(s).padStart(2, "0")}` : `${mm}:${String(s).padStart(2, "0")}`;
}

/** Human "remaining" time: 45 s, 12 min, 1 h 20 min */
export function formatRelative(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} s`;
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function formatSpeed(speed: number | null | undefined, lang: Lang): string {
  if (!speed) return "—";
  return `${speed.toLocaleString(lang, { maximumFractionDigits: speed < 10 ? 1 : 0 })}×`;
}

export function formatBitrate(bps: number | null | undefined, lang: Lang): string {
  if (!bps) return "—";
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toLocaleString(lang, { maximumFractionDigits: 1 })} Mb/s`;
  return `${Math.round(bps / 1000).toLocaleString(lang)} kb/s`;
}

export function formatNumber(value: number, lang: Lang, digits = 0): string {
  return value.toLocaleString(lang, { maximumFractionDigits: digits });
}

export function displaySize(video: VideoStream): [number, number] {
  let width = video.width;
  if (video.display_aspect && video.height) width = Math.round(video.height * video.display_aspect);
  return video.rotation === 90 || video.rotation === 270 ? [video.height, width] : [width, video.height];
}

export function resolutionLabel(video: VideoStream | null | undefined): string {
  if (!video) return "";
  const [w, h] = displaySize(video);
  const short = Math.min(w, h);
  if (short >= 2100) return "4K";
  if (short >= 1400) return "1440p";
  if (short >= 1000) return "1080p";
  if (short >= 700) return "720p";
  if (short >= 560) return "576p";
  if (short >= 470) return "480p";
  return `${w}×${h}`;
}

const CODEC_NAMES: Record<string, string> = {
  h264: "H.264", hevc: "H.265", av1: "AV1", vp9: "VP9", vp8: "VP8", mpeg4: "MPEG-4", mpeg2video: "MPEG-2",
  mpeg1video: "MPEG-1", wmv2: "WMV", wmv3: "WMV", msmpeg4v3: "DivX 3", prores: "ProRes", theora: "Theora",
  aac: "AAC", mp3: "MP3", ac3: "AC-3", eac3: "E-AC-3", dts: "DTS", truehd: "TrueHD", opus: "Opus",
  vorbis: "Vorbis", flac: "FLAC", mp2: "MP2", wmav2: "WMA", alac: "ALAC", pcm_s16le: "PCM", pcm_s24le: "PCM",
  subrip: "SRT", ass: "ASS", ssa: "SSA", mov_text: "MP4 Text", webvtt: "WebVTT", hdmv_pgs_subtitle: "PGS",
  dvd_subtitle: "VobSub", dvb_subtitle: "DVB",
};

export function codecName(codec: string | null | undefined): string {
  if (!codec) return "—";
  return CODEC_NAMES[codec] ?? codec.toUpperCase();
}

export function channelsLabel(track: AudioStream, t: (key: "channels.1" | "channels.2") => string): string {
  if (track.channels === 1) return t("channels.1");
  if (track.channels === 2) return t("channels.2");
  if (track.channels === 6) return "5.1";
  if (track.channels === 8) return "7.1";
  return track.channels ? `${track.channels} ch` : "";
}

export function languageName(code: string | null | undefined, lang: Lang): string | null {
  if (!code) return null;
  const normalized = LANGUAGE_ALIASES[code.toLowerCase()] ?? code;
  try {
    const name = new Intl.DisplayNames([lang], { type: "language" }).of(normalized);
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : code;
  } catch {
    return code;
  }
}

export function mediaSummary(media: MediaInfo, lang: Lang): string[] {
  const parts: string[] = [];
  if (media.video) {
    parts.push(resolutionLabel(media.video));
    parts.push(codecName(media.video.codec));
  }
  const audio = media.audio[0];
  if (audio) parts.push(codecName(audio.codec));
  parts.push(formatDuration(media.duration_s));
  parts.push(formatBytes(media.size_bytes, lang));
  return parts.filter(Boolean);
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

export function dirname(path: string): string {
  const index = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return index > 0 ? path.slice(0, index) : path.slice(0, index + 1) || path;
}
