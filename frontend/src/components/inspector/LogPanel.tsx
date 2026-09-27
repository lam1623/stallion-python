import { AlertTriangle, Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Job } from "@/lib/types";
import { copyText } from "@/lib/utils";
import { Button } from "../ui/button";
import { Field } from "../ui/misc";

function CopyButton({ text }: { text: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="xs"
      onClick={async () => {
        if (await copyText(text)) {
          setCopied(true);
          toast.success(t("toast.copied"));
          setTimeout(() => setCopied(false), 1500);
        }
      }}
    >
      {copied ? <Check /> : <Copy />}
      {t("log.copy")}
    </Button>
  );
}

export function LogPanel({ job }: { job: Job }) {
  const t = useT();
  const [data, setData] = useState<{ log: string[]; command: string } | null>(null);
  const optionsKey = JSON.stringify(job.options);

  useEffect(() => {
    let alive = true;
    api
      .jobLog(job.id)
      .then((result) => alive && setData(result))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [job.id, job.status, optionsKey]);

  return (
    <div className="grid grid-cols-1 items-start gap-x-8 gap-y-5 @3xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      {job.error && (
        <div className="flex gap-3 rounded-xl border border-danger/25 bg-danger/10 p-3.5 text-[13px] text-danger @3xl:col-span-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0">
            <div className="font-semibold">{t("log.error")}</div>
            <p className="mt-1 break-words leading-relaxed opacity-90">{job.error}</p>
          </div>
        </div>
      )}
      <Field label={t("log.command")} aside={data?.command ? <CopyButton text={data.command} /> : null}>
        <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-xl border border-border bg-bg p-3 font-mono text-[11.5px] leading-relaxed text-muted">
          {data?.command ?? "…"}
        </pre>
      </Field>
      <Field label={t("log.output")}>
        <pre className="max-h-80 min-h-24 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-bg p-3 font-mono text-[11.5px] leading-relaxed text-muted">
          {data?.log.length ? data.log.join("\n") : t("log.empty")}
        </pre>
      </Field>
    </div>
  );
}
