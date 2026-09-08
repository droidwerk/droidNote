export interface ActionItem {
  text: string;
  owner: string | null;
  due?: string | null;
}

export interface SummaryTopic {
  title: string;
  points: string[];
}

export interface Session {
  id: string;
  title: string;
  started_at: string;
  ended_at: string | null;
  status: "recording" | "stopped";
  language: string | null;
  duration_ms: number;
  capture_mode?: CaptureMode;
  tags?: Tag[];
  has_audio?: boolean;
}

export type CaptureMode = "dictation" | "lecture" | "meeting";

export interface Tag {
  id: string;
  name: string;
}

export interface Segment {
  id: string;
  session_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  language: string | null;
  speaker_id?: string | null;
  speaker_name?: string | null;
  source?: "mic" | "loopback" | string | null;
}

export interface Person {
  id: string;
  name: string;
}

export interface Summary {
  id: string;
  session_id: string;
  overview?: string;
  topics?: SummaryTopic[];
  highlights: string[];
  decisions: string[];
  action_items: ActionItem[];
  open_items?: string[];
  language?: string | null;
  raw_text: string;
  created_at: string;
  notes_markdown?: string;
}

export interface SessionDetail {
  session: Session;
  segments: Segment[];
  summary: Summary | null;
  participants?: Person[];
}

export interface CaptureState {
  recording: boolean;
  session_id: string | null;
  mic_only: boolean;
  warning: string | null;
  phase?: "idle" | "loading" | "listening" | "transcribing";
  loopback_name?: string | null;
  started_at?: string | null;
}

export interface MonitorFrame {
  rms: number;
  speech: boolean;
  bars: number[];
  queued: number;
  buffer_ms: number;
  phase: string;
  whisper_loaded: boolean;
}

export interface SetupComponent {
  status: "missing" | "downloading" | "installing" | "ready" | "error";
  progress: number;
  message: string;
}

export interface SetupStatus {
  llm: SetupComponent;
  whisper: SetupComponent;
  disclaimer_accepted: boolean;
  audio_ok: boolean;
  capture_ready: boolean;
  summarize_ready: boolean;
  audio_message?: string;
  provider?: Provider;
  ram_gb?: number;
  suggested_note_model?: string;
  suggested_whisper_model?: string;
  ollama_binary?: boolean;
  save_recordings?: boolean;
  disclaimer_kind?: "local" | "openai";
  setup_complete?: boolean;
}

export type Provider = "neste_pc" | "openai";

export interface Settings {
  whisper_model: string;
  ollama_model: string;
  mic_only_default: boolean;
  whisper_device?: string;
  provider?: Provider;
  asr_cloud_model?: string;
  llm_cloud_model?: string;
  has_api_key?: boolean;
  api_key_hint?: string;
  language?: string;
  data_dir?: string;
  recordings_dir?: string;
  self_person_id?: string;
  save_recordings?: boolean;
  openai_disclaimer_accepted?: boolean;
  disclaimer_kind?: "local" | "openai";
}

export interface ModelOption {
  id: string;
  label: string;
  installed: boolean;
  source: "whisper" | "ollama" | "openai";
  detail?: string;
  recommended?: boolean;
  learn_more?: string;
}

export interface ModelsCatalog {
  whisper: ModelOption[];
  ollama: ModelOption[];
  asr_cloud?: ModelOption[];
  llm_cloud?: ModelOption[];
  ollama_online: boolean;
}

export interface SetupPlan {
  ram_gb: number;
  suggested_note_model: string;
  suggested_whisper_model: string;
  ollama_binary: boolean;
  ollama_online: boolean;
  current_note_model: string;
  current_whisper_model: string;
  provider: Provider;
  whisper: ModelOption[];
  ollama: ModelOption[];
  asr_cloud?: ModelOption[];
  llm_cloud?: ModelOption[];
  save_recordings: boolean;
  vram_gb?: number;
  free_disk_gb?: number;
  download_gb?: number;
  required_disk_gb?: number;
  disk_ok?: boolean;
  disk_margin?: number;
  whisper_download_gb?: Record<string, number>;
  ollama_download_gb?: Record<string, number>;
  ollama_installer_gb?: number;
}

export interface BackendInfo {
  url: string;
  token: string;
}

export interface TranscriptEvent {
  type: string;
  recording?: boolean;
  session_id?: string | null;
  segment?: Segment;
}

export interface Device {
  id: string;
  name: string;
  kind: string;
  recommended?: boolean;
}

export interface SearchResult {
  query: string;
  segments: Segment[];
}
