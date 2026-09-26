import { LayoutGrid, ListVideo, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Settings2, Sun, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { saveSettings } from "@/lib/actions";
import { useMediaQuery } from "@/lib/hooks";
import { useT } from "@/lib/i18n";
import { useStore, type View } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Logo } from "./Brand";
import { Tip } from "./ui/overlay";

function NavItem({
  view,
  icon,
  label,
  badge,
  rail,
}: {
  view: View;
  icon: ReactNode;
  label: string;
  badge?: number;
  rail: boolean;
}) {
  const active = useStore((s) => s.view === view);
  const setView = useStore((s) => s.setView);
  const button = (
    <button
      onClick={() => setView(view)}
      aria-current={active ? "page" : undefined}
      aria-label={rail ? label : undefined}
      className={cn(
        "group relative flex h-9 w-full items-center gap-3 rounded-lg px-2.5 text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-[18px]",
        rail && "justify-center px-0",
        active ? "bg-elevated text-fg shadow-card" : "text-muted hover:bg-elevated/60 hover:text-fg",
      )}
    >
      <span className={cn("transition", active ? "text-accent" : "text-subtle group-hover:text-muted")}>{icon}</span>
      {!rail && <span className="flex-1 text-left">{label}</span>}
      {!!badge &&
        (rail ? (
          <span className="absolute right-1 top-0.5 min-w-4 rounded-full bg-accent px-1 text-center text-[10px] font-semibold leading-4 text-accent-fg tabular">
            {badge}
          </span>
        ) : (
          <span className="min-w-5 rounded-full bg-accent-soft px-1.5 py-0.5 text-center text-[11px] font-semibold text-accent tabular">
            {badge}
          </span>
        ))}
    </button>
  );
  return rail ? (
    <Tip content={label} side="right">
      {button}
    </Tip>
  ) : (
    button
  );
}

function ThemeSwitch({ rail }: { rail: boolean }) {
  const t = useT();
  const theme = useStore((s) => s.settings?.theme ?? "light");
  const options = [
    { value: "light", icon: <Sun />, label: t("theme.light") },
    { value: "dark", icon: <Moon />, label: t("theme.dark") },
    { value: "system", icon: <Monitor />, label: t("theme.system") },
  ] as const;
  return (
    <div className={cn("flex rounded-lg border border-border bg-bg/60 p-0.5", rail && "flex-col")}>
      {options.map((option) => (
        <Tip key={option.value} content={option.label} side={rail ? "right" : "top"}>
          <button
            onClick={() => saveSettings({ theme: option.value })}
            aria-label={option.label}
            aria-pressed={theme === option.value}
            className={cn(
              "grid h-7 place-items-center rounded-md text-subtle outline-none transition hover:text-fg focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-3.5",
              // In a column, flex-1 would squeeze the buttons below their height
              rail ? "w-full" : "flex-1",
              theme === option.value && "bg-surface text-fg shadow-card",
            )}
          >
            {option.icon}
          </button>
        </Tip>
      ))}
    </div>
  );
}

export function Sidebar() {
  const t = useT();
  const system = useStore((s) => s.system);
  const connection = useStore((s) => s.connection);
  const pending = useStore((s) => s.queue.counts.queued + s.queue.counts.running + s.queue.counts.paused);
  const collapsed = useStore((s) => s.sidebarCollapsed);
  const setCollapsed = useStore((s) => s.setSidebarCollapsed);
  // Small windows always get the icon rail; wide ones follow the user's choice
  const roomy = useMediaQuery("(min-width: 1024px)");
  const rail = collapsed || !roomy;
  const ffmpeg = system?.ffmpeg;

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-border bg-panel py-4 transition-[width] duration-200 ease-out",
        rail ? "w-16 px-2.5" : "w-60 px-3",
      )}
    >
      <div className={cn("mb-6 flex items-center gap-3 px-1", rail && "justify-center")}>
        <Logo />
        {!rail && (
          <div className="min-w-0">
            <div className="text-[15px] font-semibold tracking-tight text-fg">Stallion</div>
            <div className="truncate text-xs text-subtle">{t("app.tagline")}</div>
          </div>
        )}
      </div>

      <nav className="space-y-1">
        <NavItem view="queue" icon={<ListVideo />} label={t("nav.queue")} badge={pending} rail={rail} />
        <NavItem view="formats" icon={<LayoutGrid />} label={t("nav.formats")} rail={rail} />
        <NavItem view="settings" icon={<Settings2 />} label={t("nav.settings")} rail={rail} />
      </nav>

      <div className="mt-auto space-y-3">
        {connection === "offline" && (
          <div
            className={cn(
              "flex items-center gap-2 rounded-lg border border-warning/25 bg-warning/10 px-2.5 py-2 text-xs font-medium text-warning",
              rail && "justify-center",
            )}
          >
            <WifiOff className="size-3.5 shrink-0" />
            {!rail && <span>{t("conn.offline")}</span>}
          </div>
        )}
        <Tip content={ffmpeg?.available ? ffmpeg.path : t("engine.missingHelp")} side="right">
          <div className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-muted", rail && "justify-center")}>
            <span className="relative flex size-2">
              {ffmpeg?.available && (
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-40" />
              )}
              <span
                className={cn("relative inline-flex size-2 rounded-full", ffmpeg?.available ? "bg-success" : "bg-danger")}
              />
            </span>
            {!rail && (
              <span className="truncate">
                {ffmpeg?.available ? t("engine.ok", { version: ffmpeg.version ?? "" }) : t("engine.missing")}
              </span>
            )}
          </div>
        </Tip>
        <ThemeSwitch rail={rail} />
        <div className={cn("flex items-center gap-2", rail ? "justify-center" : "justify-between pl-2.5")}>
          {!rail && <span className="text-[11px] text-subtle">v{system?.version}</span>}
          {roomy && (
            <Tip content={collapsed ? t("nav.expand") : t("nav.collapse")} side="right">
              <button
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
                className="grid size-7 place-items-center rounded-md text-subtle outline-none transition hover:bg-elevated hover:text-fg focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-4"
              >
                {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              </button>
            </Tip>
          )}
        </div>
      </div>
    </aside>
  );
}
