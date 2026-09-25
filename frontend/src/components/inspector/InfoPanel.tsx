import type { ReactNode } from "react";
import {
  channelsLabel,
  codecName,
  displaySize,
  formatBitrate,
  formatBytes,
  formatDuration,
  formatNumber,
  languageName,
  resolutionLabel,
} from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import type { Job } from "@/lib/types";
import { Badge, SectionTitle } from "../ui/misc";

function Def({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 py-2 text-[13px]">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 text-fg">{children}</dd>
    </div>
  );
}

function Block({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section>
      <SectionTitle className="mb-1">{title}</SectionTitle>
      <dl className="divide-y divide-border">{children}</dl>
    </section>
  );
}

export function InfoPanel({ job }: { job: Job }) {
  const t = useT();
  const lang = useLang();
  const { media } = job;
  const video = media.video;
  const [w, h] = video ? displaySize(video) : [0, 0];

  return (
    <div className="space-y-6">
      <Block title={t("info.file")}>
        <Def label={t("info.location")}>
          <span className="break-all font-mono text-xs leading-relaxed text-muted">{job.input_path}</span>
        </Def>
        <Def label={t("info.container")}>{media.format_label ?? media.format_name}</Def>
        <Def label={t("info.duration")}>
          <span className="tabular">{formatDuration(media.duration_s)}</span>
        </Def>
        <Def label={t("info.size")}>{formatBytes(media.size_bytes, lang)}</Def>
        <Def label={t("info.bitrate")}>{formatBitrate(media.bitrate, lang)}</Def>
      </Block>

      <Block title={t("info.video")}>
        {video ? (
          <>
            <Def label={t("info.codec")}>
              <span className="flex items-center gap-2">
                {codecName(video.codec)}
                {video.hdr && <Badge className="border-warning/30 bg-warning/10 text-warning">HDR</Badge>}
              </span>
            </Def>
            <Def label={t("info.resolution")}>
              <span className="tabular">
                {w}×{h} <span className="text-muted">· {resolutionLabel(video)}</span>
              </span>
            </Def>
            <Def label={t("info.fps")}>{video.fps ? `${formatNumber(video.fps, lang, 3)} fps` : "—"}</Def>
            <Def label={t("info.pixfmt")}>{video.pix_fmt ?? "—"}</Def>
            {video.rotation !== 0 && <Def label={t("info.rotation")}>{video.rotation}°</Def>}
            {video.bitrate && <Def label={t("info.bitrate")}>{formatBitrate(video.bitrate, lang)}</Def>}
          </>
        ) : (
          <Def label={t("info.codec")}>{t("info.noVideo")}</Def>
        )}
      </Block>

      <Block title={t("info.audioTracks")}>
        {media.audio.length ? (
          media.audio.map((track) => (
            <Def key={track.index} label={`#${track.position + 1}`}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span>{languageName(track.language, lang) ?? codecName(track.codec)}</span>
                <span className="text-muted">
                  {[
                    codecName(track.codec),
                    channelsLabel(track, t),
                    track.sample_rate ? `${formatNumber(track.sample_rate / 1000, lang, 1)} kHz` : null,
                    track.bitrate ? formatBitrate(track.bitrate, lang) : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {track.default && <Badge>{t("tracks.default")}</Badge>}
              </div>
              {track.title && <div className="text-xs text-subtle">{track.title}</div>}
            </Def>
          ))
        ) : (
          <Def label="—">{t("info.none")}</Def>
        )}
      </Block>

      <Block title={t("info.subtitleTracks")}>
        {media.subtitles.length ? (
          media.subtitles.map((track) => (
            <Def key={track.index} label={`#${track.position + 1}`}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span>{languageName(track.language, lang) ?? codecName(track.codec)}</span>
                <span className="text-muted">{codecName(track.codec)}</span>
                {track.bitmap && <Badge>{t("sub.image")}</Badge>}
                {track.forced && <Badge>{t("sub.forced")}</Badge>}
              </div>
              {track.title && <div className="text-xs text-subtle">{track.title}</div>}
            </Def>
          ))
        ) : (
          <Def label="—">{t("info.none")}</Def>
        )}
      </Block>
    </div>
  );
}
