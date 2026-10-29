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
  template_id?: string | null;
  transcript_purged_at?: string | null;
}

export type NoteKind = "decision" | "task" | "important" | "question";

export interface UserNote {
  id: string;
  session_id: string;
  at_ms: number;
  text: string;
  created_at: string;
  kind?: NoteKind | null;
  ai_context?: string | null;
}

export interface NoteTemplate {
  id: string;
  kind: "note" | "recipe";
  name: string;
  body: string;
  capture_mode?: CaptureMode | null;
  builtin: boolean;
}

export interface TaskItem {
  id: string;
  text: string;
  owner: string | null;
  due: string | null;
  done: boolean;
  done_at: string | null;
  origin: "ai" | "manual";
  created_at: string;
  session_id: string | null;
  session_title: string | null;
  session_started_at: string | null;
}

export type TaskStatus = "open" | "done" | "all";

export interface BriefSession {
  session_id: string;
  title: string;
  started_at: string;
  reason: "title" | "people" | "both";
  overview: string;
  decisions: string[];
  open_items: string[];
  tasks: TaskItem[];
}

export interface Brief {
  title: string;
  people: string[];
  related: BriefSession[];
  pending: TaskItem[];
}

/** Mapa mental da conversa: dados no formato do editor (mind-elixir) mais origem e esboço. */
export interface MindMap {
  session_id: string;
  origin: "auto" | "edited" | "ai";
  summary_id: string | null;
  updated_at: string;
  data: { nodeData: unknown; direction?: number };
  markdown: string;
}

export interface MemoryThread {
  session_id: string;
  title: string;
  started_at: string;
  reason: "title" | "people" | "both";
  has_summary: boolean;
  decisions: string[];
  open_items: string[];
}

export interface MemoryResolved {
  item: string;
  how: string;
  task_id: string | null;
}

export interface MemoryChange {
  before: string;
  now: string;
}

/** Memória da série: o que liga esta reunião às anteriores e o que mudou. */
export interface Memory {
  session_id: string;
  mode: "before" | "after";
  generated: boolean;
  stale: boolean;
  language: string | null;
  created_at: string | null;
  thread: MemoryThread[];
  resolved: MemoryResolved[];
  still_open: string[];
  changed: MemoryChange[];
  new_items: string[];
  watch: string[];
  pending: TaskItem[];
}

export interface CalendarEvent {
  uid: string;
  title: string;
  start: string;
  end: string;
  location: string | null;
  attendees: string[];
  brief: Brief;
}

export interface Upcoming {
  configured: boolean;
  error: string | null;
  events: CalendarEvent[];
}

export interface RetentionReport {
  audio_files: number;
  transcripts: number;
  audio_days: number;
  transcript_days: number;
}

export type MeetingMode = "off" | "ask" | "auto";

export interface MeetingStatus {
  available: boolean;
  active: boolean;
  app?: string | null;
  browser?: boolean;
  since?: string | null;
  dismissed?: boolean;
  auto_session_id?: string | null;
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
  speaker_cluster?: string | null;
  speaker_confidence?: number | null;
  speaker_locked?: boolean;
}

export interface Person {
  id: string;
  name: string;
  has_voiceprint?: boolean;
}

export interface Voice {
  cluster: string;
  index: number;
  person_id: string | null;
  person_name: string | null;
  talk_ms: number;
  share: number;
  segments: number;
  first_ms: number;
  sources: string[];
  confidence: number;
  has_voiceprint: boolean;
}

export interface VoicesResult {
  engine_ready: boolean;
  model: string;
  live: boolean;
  voices: Voice[];
  segments: Segment[];
}

export interface ChannelLevel {
  rms: number;
  speech: boolean;
  echo?: number;
  gain_db?: number;
}

export interface LiveVoice {
  /** Nulo quando a pessoa foi reconhecida pela impressão vocal antes de ter uma voz na sessão. */
  cluster: string | null;
  person_id: string | null;
  name: string | null;
  source: string | null;
  at_ms: number;
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
  channels?: { mic: ChannelLevel; system: ChannelLevel | null } | null;
  voice?: LiveVoice | null;
}

export interface SetupComponent {
  status: "missing" | "downloading" | "installing" | "ready" | "error";
  progress: number;
  message: string;
}

export interface SetupStatus {
  llm: SetupComponent;
  whisper: SetupComponent;
  voice?: SetupComponent | null;
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
  ui_language?: string;
  data_dir?: string;
  recordings_dir?: string;
  self_person_id?: string;
  save_recordings?: boolean;
  openai_disclaimer_accepted?: boolean;
  disclaimer_kind?: "local" | "openai";
  meeting_detection?: MeetingMode;
  has_calendar?: boolean;
  calendar_hint?: string;
  consent_message?: string;
  retention_audio_days?: number;
  retention_transcript_days?: number;
  auto_gain?: boolean;
  auto_summary?: boolean;
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
  total_ram_gb?: number;
  free_ram_gb?: number;
  gpu_name?: string;
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

export interface ChatFocus {
  prompt?: string;
  sessionId?: string;
  sessionTitle?: string;
  segmentId?: string;
  excerpt?: string;
}

export interface ChatCitation {
  session_id: string;
  session_title: string;
  segment_id?: string | null;
  start_ms: number;
  excerpt: string;
  document_id?: string | null;
  document_name?: string;
  page?: number | null;
}

export interface ChatDocument {
  id: string;
  name: string;
  kind: "pdf" | "word" | "excel" | "csv" | "text" | string;
  size: number;
  pages: number;
  chunks: number;
  chars: number;
  created_at: string;
  chat_id: string | null;
  session_id?: string | null;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  citations: ChatCitation[];
}

export interface ChatThread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  focus_session_id?: string | null;
}

export interface ChatDetail {
  chat: ChatThread;
  messages: ChatMessage[];
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
  notes: { id: string; session_id: string; at_ms: number; text: string; kind: string | null }[];
  summaries: { session_id: string; excerpt: string }[];
  tasks: { id: string; session_id: string | null; text: string; done: boolean }[];
}
