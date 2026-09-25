// Mirrors the pydantic models exposed by the Python API

export type JobStatus = "queued" | "running" | "paused" | "completed" | "failed" | "canceled";
export type SubtitleMode = "none" | "soft" | "burn";
export type Speed = "fast" | "balanced" | "quality";
export type PresetCategory = "video" | "social" | "editing" | "audio" | "remux" | "legacy";
export type Localized = Record<string, string>;

export interface SubtitleStyle {
  font: string;
  size: number;
  color: string;
  outline_color: string;
  outline: number;
  bold: boolean;
  box: boolean;
  margin: number;
}

export interface JobOptions {
  preset_id: string;
  quality: number | null;
  speed: Speed;
  max_height: number | null;
  audio_bitrate_kbps: number | null;
  volume_db: number;
  normalize_audio: boolean;
  audio_track: number | null;
  subtitle_mode: SubtitleMode;
  subtitle_track: number | null;
  subtitle_file: string | null;
  subtitle_style: SubtitleStyle;
  output_dir: string | null;
  output_name: string | null;
}

export interface VideoStream {
  index: number;
  codec: string;
  width: number;
  height: number;
  fps: number | null;
  pix_fmt: string | null;
  bitrate: number | null;
  rotation: number;
  display_aspect: number | null;
  hdr: boolean;
}

export interface AudioStream {
  index: number;
  position: number;
  codec: string;
  language: string | null;
  title: string | null;
  channels: number | null;
  channel_layout: string | null;
  sample_rate: number | null;
  bitrate: number | null;
  default: boolean;
}

export interface SubtitleStream {
  index: number;
  position: number;
  codec: string;
  language: string | null;
  title: string | null;
  bitmap: boolean;
  default: boolean;
  forced: boolean;
}

export interface MediaInfo {
  path: string;
  format_name: string;
  format_label: string | null;
  duration_s: number;
  size_bytes: number;
  bitrate: number | null;
  video: VideoStream | null;
  cover_art_index: number | null;
  audio: AudioStream[];
  subtitles: SubtitleStream[];
}

export interface Progress {
  percent: number;
  out_time_s: number;
  speed: number | null;
  fps: number | null;
  size_bytes: number | null;
  bitrate_kbps: number | null;
  eta_s: number | null;
  elapsed_s: number;
}

export interface Job {
  id: string;
  name: string;
  input_path: string;
  size_bytes: number;
  media: MediaInfo;
  options: JobOptions;
  output_path: string;
  status: JobStatus;
  progress: Progress;
  error: string | null;
  external_subtitles: string[];
  thumbnail: boolean;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  output_size: number | null;
  revision: number;
}

export interface QueueState {
  running: boolean;
  counts: Record<JobStatus, number>;
}

// crf: lower is better · bitrate: kb/s · quality: 0-100, higher is better · size: target size in MB
export type RateControl = "crf" | "bitrate" | "quality" | "size" | "none";

export interface VideoSpec {
  codec: string;
  rate_control: RateControl;
  quality: number | null;
  quality_min: number | null;
  quality_max: number | null;
  quality_choices: number[];
  speed_family: "x26x" | "svtav1" | "vpx" | null;
  pix_fmt: string | null;
  max_height: number | null;
  max_width: number | null;
  fps: number | null;
  min_frame: [number, number] | null;
}

export interface AudioSpec {
  codec: string;
  bitrate_kbps: number | null;
  bitrate_choices: number[];
  channels: number | null;
  sample_rate: number | null;
}

export interface Preset {
  id: string;
  category: PresetCategory;
  name: Localized;
  description: Localized;
  extension: string;
  video: VideoSpec | null;
  audio: AudioSpec | null;
  target: string | null;
  widescreen: boolean;
  remux: boolean;
  soft_subtitles: "mov_text" | "webvtt" | "copy" | null;
  soft_bitmap_subtitles: boolean;
  fixed_resolution: boolean;
  frame: string | null;
  layout: "blur_fill" | null;
  animation: "gif" | null;
  tags: string[];
  available: boolean;
  missing_encoders: string[];
}

export interface Settings {
  output_dir: string | null;
  default_preset: string;
  concurrency: number;
  auto_start: boolean;
  autoload_subtitles: boolean;
  overwrite: boolean;
  delete_partial: boolean;
  notify_on_finish: boolean;
  theme: "system" | "dark" | "light";
  language: "auto" | "es" | "en";
}

export interface Root {
  name: string;
  path: string;
}

export interface SystemInfo {
  version: string;
  platform: string;
  desktop: boolean;
  pause_supported: boolean;
  data_dir: string;
  roots: Root[];
  ffmpeg: {
    available: boolean;
    version: string | null;
    path: string | null;
    error: string | null;
    can_tonemap: boolean;
  };
}

export type EntryKind = "dir" | "video" | "audio" | "subtitle" | "file";

export interface FsEntry {
  name: string;
  path: string;
  kind: EntryKind;
  size: number | null;
  modified: number | null;
}

export interface FsListing {
  path: string;
  parent: string | null;
  root: string;
  entries: FsEntry[];
  truncated: boolean;
}

export interface AddError {
  path: string;
  code: string;
  message: string;
}

export type ServerEvent =
  | { type: "snapshot"; jobs: Job[]; queue: QueueState }
  | { type: "job"; job: Job }
  | { type: "progress"; items: { id: string; progress: Progress }[] }
  | { type: "removed"; ids: string[] }
  | { type: "queue"; queue: QueueState }
  | { type: "queue_finished"; counts: Record<JobStatus, number> }
  | { type: "settings"; settings: Settings }
  | { type: "resync" };
