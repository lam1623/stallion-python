import { type PointerEvent, useState } from "react";
import { useT } from "@/lib/i18n";
import { HISTORY_SIZE } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Tip } from "../ui/overlay";

export type VizColor = "cpu" | "gpu" | "mem";

// Validated series colors (see index.css): fill, and the same hue as a lighter track
const FILL: Record<VizColor, string> = { cpu: "bg-viz-cpu", gpu: "bg-viz-gpu", mem: "bg-viz-mem" };
const TRACK: Record<VizColor, string> = { cpu: "bg-viz-cpu/15", gpu: "bg-viz-gpu/15", mem: "bg-viz-mem/15" };
const STROKE: Record<VizColor, string> = { cpu: "var(--viz-cpu)", gpu: "var(--viz-gpu)", mem: "var(--viz-mem)" };

export function percent(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value)} %`;
}

/** Horizontal meter: a value against its limit, track in a lighter step of the same hue. */
export function Meter({ value, color, label, className }: { value: number; color: VizColor; label: string; className?: string }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(width)}
      className={cn("h-2 overflow-hidden rounded-full", TRACK[color], className)}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-700 ease-out", FILL[color])} style={{ width: `${width}%` }} />
    </div>
  );
}

/** Group many cores into at most `max` bars (each shows the average of its group). */
function binned(cores: number[], max: number): number[] {
  if (cores.length <= max) return cores;
  const size = Math.ceil(cores.length / max);
  const out: number[] = [];
  for (let i = 0; i < cores.length; i += size) {
    const group = cores.slice(i, i + size);
    out.push(group.reduce((a, b) => a + b, 0) / group.length);
  }
  return out;
}

const BAR_SIZES = {
  // status bar: a few pixels per core, groups beyond 16
  sm: { max: 16, box: "h-5 gap-0.5", bar: "h-5 w-[5px] flex-none rounded-t-[2px]" },
  // activity strip
  md: { max: 24, box: "h-14 flex-none gap-[3px]", bar: "h-full w-2 flex-none rounded-t-[3px]" },
  // monitor panel: every core
  lg: { max: Infinity, box: "h-24 gap-[3px]", bar: "h-full min-w-1.5 max-w-6 rounded-t-[4px]" },
} as const;

/** One vertical meter per logical core (or group of cores); each bar has its own tooltip. */
export function CoreBars({
  cores,
  size = "lg",
  className,
}: {
  cores: number[];
  size?: keyof typeof BAR_SIZES;
  className?: string;
}) {
  const t = useT();
  const spec = BAR_SIZES[size];
  const values = binned(cores, spec.max);
  const grouped = values.length < cores.length;
  return (
    <div className={cn("flex items-end", spec.box, className)} role="group" aria-label={t("mon.cores", { count: cores.length })}>
      {values.map((value, index) => {
        const label = grouped ? t("mon.coreGroup", { n: index + 1 }) : t("mon.core", { n: index + 1 });
        const bar = (
          <div key={index} className={cn("relative flex-1 overflow-hidden", spec.bar, TRACK.cpu)}>
            <div
              className={cn("absolute inset-x-0 bottom-0 transition-[height] duration-700 ease-out", FILL.cpu)}
              style={{ height: `${Math.max(0, Math.min(100, value))}%` }}
            />
          </div>
        );
        // The status bar readout is one button: no per-core focus stops inside it
        if (size === "sm") return bar;
        return (
          <Tip key={index} content={`${label} · ${percent(value)}`}>
            <div
              tabIndex={0}
              className={cn(
                "flex h-full items-end outline-none focus-visible:ring-2 focus-visible:ring-ring",
                size === "md" ? "w-2 flex-none" : "min-w-1.5 max-w-6 flex-1",
              )}
            >
              {bar}
            </div>
          </Tip>
        );
      })}
    </div>
  );
}

/** Recent samples of a 0–100 % series: 2px line over a 10 % wash, crosshair + readout on hover. */
export function HistoryChart({
  values,
  times,
  color,
  label,
  compact = false,
  className,
}: {
  values: number[];
  times: number[];
  color: VizColor;
  label: string;
  /** Sparkline: shorter, baseline only, no captions */
  compact?: boolean;
  className?: string;
}) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  const latest = times[times.length - 1] ?? 0;
  const secondsBefore = (index: number) => Math.round((latest - times[index]) / 1000);
  const width = 300;
  const height = compact ? 56 : 88;
  const step = width / (HISTORY_SIZE - 1);
  const x = (index: number) => width - (values.length - 1 - index) * step;
  const y = (value: number) => height - (Math.max(0, Math.min(100, value)) / 100) * height;
  const line = values.map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const area = values.length ? `${x(0).toFixed(1)},${height} ${line} ${width},${height}` : "";
  const hovered = hover != null && hover < values.length ? hover : null;

  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    if (!values.length) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * width;
    const index = Math.round(values.length - 1 - (width - px) / step);
    setHover(Math.max(0, Math.min(values.length - 1, index)));
  };

  return (
    <figure className={cn("m-0 space-y-1.5", className)}>
      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className={cn("block w-full touch-none overflow-visible", compact ? "h-14" : "h-[88px]")}
          role="img"
          aria-label={`${label}: ${percent(values[values.length - 1])}`}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          {(compact ? [0] : [0, 50, 100]).map((tick) => (
            <line key={tick} x1={0} x2={width} y1={y(tick)} y2={y(tick)} stroke="var(--border)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          {values.length > 1 && (
            <>
              <polygon points={area} fill={STROKE[color]} fillOpacity={0.1} />
              <polyline points={line} fill="none" stroke={STROKE[color]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            </>
          )}
          {hovered != null && (
            <line x1={x(hovered)} x2={x(hovered)} y1={0} y2={height} stroke="var(--border-strong)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        {hovered != null && (
          <>
            <span
              className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface"
              style={{ left: `${(x(hovered) / width) * 100}%`, top: `${(y(values[hovered]) / height) * 100}%`, background: STROKE[color] }}
            />
            <span
              className="pointer-events-none absolute -top-1 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md bg-fg px-2 py-1 text-xs text-bg shadow-lg"
              style={{ left: `${Math.min(88, Math.max(12, (x(hovered) / width) * 100))}%` }}
            >
              <strong className="font-semibold">{percent(values[hovered])}</strong>
              <span className="ml-1.5 opacity-75">
                {secondsBefore(hovered) ? t("mon.ago", { s: secondsBefore(hovered) }) : t("mon.now")}
              </span>
            </span>
          </>
        )}
        {!compact && (
          <span className="pointer-events-none absolute left-0 top-0 text-[10px] leading-none text-subtle">100 %</span>
        )}
      </div>
      {!compact && (
        <figcaption className="flex justify-between text-[11px] text-subtle">
          <span>{values.length > 1 ? t("mon.ago", { s: secondsBefore(0) }) : ""}</span>
          <span>{t("mon.now")}</span>
        </figcaption>
      )}
    </figure>
  );
}
