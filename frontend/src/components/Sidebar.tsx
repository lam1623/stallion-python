import { LayoutGrid, ListVideo, Monitor, Moon, Settings2, Sun, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { saveSettings } from "@/lib/actions";
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
}: {
  view: View;
  icon: ReactNode;
  label: string;
  badge?: number;
}) {
  const active = useStore((s) => s.view === view);
  const setView = useStore((s) => s.setView);
  return (
    <button
      onClick={() => setView(view)}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex h-9 w-full items-center gap-3 rounded-lg px-2.5 text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-[18px]",
        active ? "bg-elevated text-fg shadow-card" : "text-muted hover:bg-elevated/60 hover:text-fg",
      )}
    >
      <span className={cn("transition", active ? "text-accent" : "text-subtle group-hover:text-muted")}>{icon}</span>
      <span className="hidden flex-1 text-left lg:block">{label}</span>
      {!!badge && (
        <span className="hidden min-w-5 rounded-full bg-accent-soft px-1.5 py-0.5 text-center text-[11px] font-semibold text-accent tabular lg:inline">
          {badge}
        </span>
      )}
    </button>
  );
}

function ThemeSwitch() {
  const t = useT();
  const theme = useStore((s) => s.settings?.theme ?? "system");
  const options = [
    { value: "system", icon: <Monitor />, label: t("theme.system") },
    { value: "light", icon: <Sun />, label: t("theme.light") },
    { value: "dark", icon: <Moon />, label: t("theme.dark") },
  ] as const;
  return (
    <div className="flex rounded-lg border border-border bg-bg/60 p-0.5 max-lg:flex-col">
      {options.map((option) => (
        <Tip key={option.value} content={option.label}>
          <button
            onClick={() => saveSettings({ theme: option.value })}
            aria-label={option.label}
            aria-pressed={theme === option.value}
            className={cn(
              "grid h-7 flex-1 place-items-center rounded-md text-subtle outline-none transition hover:text-fg focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-3.5",
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
  const ffmpeg = system?.ffmpeg;

  return (
    <aside className="flex w-16 shrink-0 flex-col border-r border-border bg-panel px-2.5 py-4 lg:w-60 lg:px-3">
      <div className="mb-6 flex items-center gap-3 px-1 max-lg:justify-center">
        <Logo />
        <div className="hidden min-w-0 lg:block">
          <div className="text-[15px] font-semibold tracking-tight text-fg">Stallion</div>
          <div className="truncate text-xs text-subtle">{t("app.tagline")}</div>
        </div>
      </div>

      <nav className="space-y-1">
        <NavItem view="queue" icon={<ListVideo />} label={t("nav.queue")} badge={pending} />
        <NavItem view="formats" icon={<LayoutGrid />} label={t("nav.formats")} />
        <NavItem view="settings" icon={<Settings2 />} label={t("nav.settings")} />
      </nav>

      <div className="mt-auto space-y-3">
        {connection === "offline" && (
          <div className="flex items-center gap-2 rounded-lg border border-warning/25 bg-warning/10 px-2.5 py-2 text-xs font-medium text-warning max-lg:justify-center">
            <WifiOff className="size-3.5 shrink-0" />
            <span className="hidden lg:inline">{t("conn.offline")}</span>
          </div>
        )}
        <Tip content={ffmpeg?.available ? ffmpeg.path : t("engine.missingHelp")} side="right">
          <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-muted max-lg:justify-center">
            <span className="relative flex size-2">
              {ffmpeg?.available && (
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-40" />
              )}
              <span
                className={cn("relative inline-flex size-2 rounded-full", ffmpeg?.available ? "bg-success" : "bg-danger")}
              />
            </span>
            <span className="hidden truncate lg:inline">
              {ffmpeg?.available ? t("engine.ok", { version: ffmpeg.version ?? "" }) : t("engine.missing")}
            </span>
          </div>
        </Tip>
        <ThemeSwitch />
        <div className="hidden px-2.5 text-[11px] text-subtle lg:block">v{system?.version}</div>
      </div>
    </aside>
  );
}
