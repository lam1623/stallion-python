import { type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const KEY_STEP = 24;

/**
 * Drag handle along the top or left edge of a panel; dragging away from the panel makes it bigger.
 * Arrow keys resize, Home/End jump to the limits and a double-click or Enter restores the default.
 */
export function ResizeHandle({
  edge,
  value,
  min,
  max,
  label,
  onResize,
  onCommit,
  className,
}: {
  edge: "top" | "left";
  value: number;
  min: number;
  max: number;
  label: string;
  /** Live size while dragging; null once the drag ends. */
  onResize: (value: number | null) => void;
  /** Final size; null restores the default. */
  onCommit: (value: number | null) => void;
  className?: string;
}) {
  const drag = useRef<{ from: number; start: number; last: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const horizontal = edge === "top";
  const clamp = (size: number) => Math.round(Math.min(max, Math.max(min, size)));
  const position = (event: PointerEvent) => (horizontal ? event.clientY : event.clientX);

  // The pointer leaves the thin handle while dragging: keep the resize cursor everywhere
  useEffect(() => {
    if (!dragging) return;
    const root = document.documentElement;
    root.style.cursor = horizontal ? "row-resize" : "col-resize";
    root.style.userSelect = "none";
    return () => {
      root.style.cursor = "";
      root.style.userSelect = "";
    };
  }, [dragging, horizontal]);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { from: position(event), start: value, last: value };
    setDragging(true);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const state = drag.current;
    if (!state) return;
    state.last = clamp(state.start + state.from - position(event));
    onResize(state.last);
  };
  const onPointerUp = () => {
    const state = drag.current;
    if (!state) return;
    drag.current = null;
    setDragging(false);
    // Commit first: the saved size must be in place before the live one goes away
    if (state.last !== state.start) onCommit(state.last);
    onResize(null);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const grow = horizontal ? "ArrowUp" : "ArrowLeft";
    const shrink = horizontal ? "ArrowDown" : "ArrowRight";
    let next: number | null | undefined;
    if (event.key === grow) next = clamp(value + KEY_STEP);
    else if (event.key === shrink) next = clamp(value - KEY_STEP);
    else if (event.key === "Home") next = min;
    else if (event.key === "End") next = max;
    else if (event.key === "Enter") next = null;
    if (next === undefined) return;
    event.preventDefault();
    onCommit(next);
  };

  return (
    <div
      role="separator"
      aria-orientation={horizontal ? "horizontal" : "vertical"}
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title={label}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={() => onCommit(null)}
      onKeyDown={onKeyDown}
      className={cn(
        "group/resize absolute z-30 touch-none outline-none",
        horizontal ? "inset-x-0 top-0 h-2 cursor-row-resize" : "inset-y-0 left-0 w-2 cursor-col-resize",
        className,
      )}
    >
      {/* The edge lights up on hover, focus and while dragging */}
      <span
        className={cn(
          "pointer-events-none absolute bg-accent opacity-0 transition-opacity duration-150 group-hover/resize:opacity-60 group-focus-visible/resize:opacity-100",
          horizontal ? "inset-x-0 top-0 h-0.5" : "inset-y-0 left-0 w-0.5",
          dragging && "opacity-100",
        )}
      />
      <span
        className={cn(
          "pointer-events-none absolute rounded-full bg-border-strong transition-colors group-hover/resize:bg-accent",
          horizontal ? "left-1/2 top-1 h-1 w-10 -translate-x-1/2" : "left-1 top-1/2 h-10 w-1 -translate-y-1/2",
          dragging && "bg-accent",
        )}
      />
    </div>
  );
}
