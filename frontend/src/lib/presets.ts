import type { HardwareInfo, MediaInfo, Preset } from "./types";

// Mirrors stallion/engine/command.py (size_budget, auto_short_side) so the UI can preview the result
const SIZE_MARGIN = 0.96;
const FRAME_OVERHEAD_BITS = 112;
const AAC_FRAMES_PER_S = 47;
const AUTO_SHORT_SIDE: [number, number][] = [
  [350, 360],
  [700, 480],
  [1500, 720],
  [4000, 1080],
];

/** Formats that must have a video stream (disc targets, layouts, animations, video-only outputs). */
export function needsVideo(preset: Preset): boolean {
  return !!(preset.target || preset.layout || preset.animation || !preset.audio);
}

/** Whether HDR survives the conversion (10-bit video or stream copy); otherwise it is tone-mapped. */
export function keepsHdr(preset: Preset): boolean {
  return preset.remux || /10|12|16/.test(preset.video?.pix_fmt ?? "");
}

export function autoShortSide(videoKbps: number): number | null {
  return AUTO_SHORT_SIDE.find(([limit]) => videoKbps < limit)?.[1] ?? null;
}

export interface SizePlan {
  videoKbps: number;
  audioKbps: number | null;
  shortSide: number | null;
}

/** Bitrates and resolution the engine will use to fit `media` into `targetMb` (decimal megabytes). */
export function sizePlan(media: MediaInfo, targetMb: number, audioKbps: number | null): SizePlan | null {
  if (!media.video || media.duration_s <= 0) return null;
  const requested = media.audio.length ? audioKbps : null;
  const framesPerSecond = (media.video.fps || 30) + (requested ? AAC_FRAMES_PER_S : 0);
  const total = (targetMb * 8000 * SIZE_MARGIN) / media.duration_s - (framesPerSecond * FRAME_OVERHEAD_BITS) / 1000;
  const audio = requested && total < requested * 3 ? Math.max(32, Math.trunc(total * 0.25)) : requested;
  const videoKbps = Math.max(40, Math.trunc(total - (audio ?? 0)));
  return { videoKbps, audioKbps: audio, shortSide: autoShortSide(videoKbps) };
}

/** "1080x1920" → "1080×1920" */
export function frameLabel(frame: string | null): string {
  return frame ? frame.replace("x", "×") : "";
}

// Mirrors stallion/engine/hwaccel.py: CPU encoders a GPU encoder can replace
const GPU_FAMILIES: Record<string, string> = { libx264: "h264", libx265: "hevc", libsvtav1: "av1", "libaom-av1": "av1" };

/** Can this machine encode `preset` on its GPU? "tenBit": the GPU has the codec but not in 10 bits. */
export function gpuSupport(preset: Preset, hardware: HardwareInfo | undefined): "ok" | "format" | "tenBit" | "none" {
  if (!hardware?.available) return "none";
  if (hardware.presets.includes(preset.id)) return "ok";
  const family = preset.video ? GPU_FAMILIES[preset.video.codec] : undefined;
  const tenBit = /10|12|16/.test(preset.video?.pix_fmt ?? "");
  if (family && tenBit && hardware.codecs.includes(family) && !hardware.ten_bit.includes(family)) return "tenBit";
  return "format";
}
