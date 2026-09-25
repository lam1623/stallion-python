import {
  AudioLines,
  AudioWaveform,
  Boxes,
  ChessKnight,
  Disc3,
  Film,
  Globe,
  type LucideIcon,
  MonitorPlay,
  Music,
  Smartphone,
  Sparkles,
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
        "grid shrink-0 place-items-center bg-brand text-white shadow-[0_8px_24px_-10px_var(--accent)] ring-1 ring-white/15 ring-inset",
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
  tint: string;
}

export const CATEGORIES: Record<PresetCategory, CategoryMeta> = {
  video: { icon: Film, label: "cat.video", tint: "bg-violet-500/14 text-violet-500 dark:text-violet-300" },
  device: { icon: Smartphone, label: "cat.device", tint: "bg-sky-500/14 text-sky-600 dark:text-sky-300" },
  audio: { icon: Music, label: "cat.audio", tint: "bg-emerald-500/14 text-emerald-600 dark:text-emerald-300" },
  disc: { icon: Disc3, label: "cat.disc", tint: "bg-amber-500/14 text-amber-600 dark:text-amber-300" },
  remux: { icon: Boxes, label: "cat.remux", tint: "bg-slate-500/14 text-slate-600 dark:text-slate-300" },
};

export const CATEGORY_ORDER: PresetCategory[] = ["video", "device", "audio", "disc", "remux"];

const PRESET_ICONS: Record<string, LucideIcon> = {
  "mp4-av1": Sparkles,
  "mp4-mobile": Smartphone,
  "avi-xvid": Tv,
  wmv: MonitorPlay,
  flv: Globe,
  flac: AudioLines,
  wav: AudioWaveform,
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
