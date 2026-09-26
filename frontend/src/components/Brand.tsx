import {
  Archive,
  AudioLines,
  AudioWaveform,
  Boxes,
  ChessKnight,
  Clapperboard,
  Disc3,
  Film,
  Gauge,
  Globe,
  Headphones,
  ImagePlay,
  Images,
  type LucideIcon,
  MessageCircle,
  Monitor,
  MonitorPlay,
  Music,
  Share2,
  SlidersHorizontal,
  Smartphone,
  Sparkles,
  Sun,
  Tv,
} from "lucide-react";
import type { TranslationKey } from "@/lib/i18n";
import type { Preset, PresetCategory } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Logo({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const box = size === "lg" ? "size-14 rounded-2xl" : size === "sm" ? "size-7 rounded-lg" : "size-9 rounded-xl";
  const icon = size === "lg" ? "size-9" : size === "sm" ? "size-[18px]" : "size-6";
  return (
    <div
      className={cn(
        "grid shrink-0 place-items-center bg-brand text-white shadow-[0_8px_24px_-10px_var(--glow)] ring-1 ring-white/15 ring-inset",
        box,
        className,
      )}
    >
      <ChessKnight className={icon} strokeWidth={2.25} />
    </div>
  );
}

interface CategoryMeta {
  icon: LucideIcon;
  label: TranslationKey;
  hint: TranslationKey;
  tint: string;
}

export const CATEGORIES: Record<PresetCategory, CategoryMeta> = {
  custom: {
    icon: SlidersHorizontal,
    label: "cat.custom",
    hint: "cat.custom.hint",
    tint: "bg-brand text-white shadow-[0_6px_16px_-10px_var(--glow)]",
  },
  video: {
    icon: Film,
    label: "cat.video",
    hint: "cat.video.hint",
    tint: "bg-violet-500/14 text-violet-500 dark:text-violet-300",
  },
  social: {
    icon: Share2,
    label: "cat.social",
    hint: "cat.social.hint",
    tint: "bg-sky-500/14 text-sky-600 dark:text-sky-300",
  },
  editing: {
    icon: Clapperboard,
    label: "cat.editing",
    hint: "cat.editing.hint",
    tint: "bg-rose-500/14 text-rose-600 dark:text-rose-300",
  },
  audio: {
    icon: Music,
    label: "cat.audio",
    hint: "cat.audio.hint",
    tint: "bg-emerald-500/14 text-emerald-600 dark:text-emerald-300",
  },
  remux: {
    icon: Boxes,
    label: "cat.remux",
    hint: "cat.remux.hint",
    tint: "bg-slate-500/14 text-slate-600 dark:text-slate-300",
  },
  legacy: {
    icon: Archive,
    label: "cat.legacy",
    hint: "cat.legacy.hint",
    tint: "bg-amber-500/14 text-amber-600 dark:text-amber-300",
  },
};

export const CATEGORY_ORDER: PresetCategory[] = ["custom", "video", "social", "editing", "audio", "remux", "legacy"];

const PRESET_ICONS: Record<string, LucideIcon> = {
  "mp4-av1": Sparkles,
  "webm-av1": Sparkles,
  "mp4-hevc-10bit": Sun,
  "social-youtube": MonitorPlay,
  "social-vertical": Smartphone,
  "mp4-mobile": MessageCircle,
  "share-size": Gauge,
  gif: ImagePlay,
  "webp-anim": Images,
  flac: AudioLines,
  alac: Headphones,
  wav: AudioWaveform,
  "avi-xvid": Tv,
  wmv: Monitor,
  flv: Globe,
  "dvd-pal": Disc3,
  "dvd-ntsc": Disc3,
  "svcd-pal": Disc3,
  "svcd-ntsc": Disc3,
  "vcd-pal": Disc3,
  "vcd-ntsc": Disc3,
};

export function PresetIcon({ preset, className }: { preset: Pick<Preset, "id" | "category">; className?: string }) {
  const meta = CATEGORIES[preset.category];
  const Icon = PRESET_ICONS[preset.id] ?? meta.icon;
  return (
    <div className={cn("grid size-9 shrink-0 place-items-center rounded-lg", meta.tint, className)}>
      <Icon className="size-[18px]" />
    </div>
  );
}
