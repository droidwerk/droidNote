import type {
  BackendInfo,
  CaptureMode,
  CaptureState,
  Device,
  ModelsCatalog,
  Person,
  SearchResult,
  Segment,
  Session,
  SessionDetail,
  Settings,
  SetupPlan,
  SetupStatus,
  Summary,
  Tag,
} from "./types";

export type { SearchResult } from "./types";

const TOKEN_HEADER = "X-DroidNote-Token";

let backend: BackendInfo = {
  url: import.meta.env.VITE_DROIDNOTE_URL ?? "http://127.0.0.1:8765",
  token: import.meta.env.VITE_DROIDNOTE_TOKEN ?? "",
};

export function setBackend(info: BackendInfo): void {
  backend = info;
}

export function getBackend(): BackendInfo {
  return backend;
}

function readErrorDetail(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "";
      })
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set(TOKEN_HEADER, backend.token);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${backend.url}${path}`, { ...init, headers });
  if (response.status === 204) {
    return undefined as T;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const parsed: unknown = await response.json();
      detail = readErrorDetail(parsed) || detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

async function download(path: string): Promise<Blob> {
  const response = await fetch(`${backend.url}${path}`, {
    headers: { [TOKEN_HEADER]: backend.token },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const parsed: unknown = await response.json();
      detail = readErrorDetail(parsed) || detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return response.blob();
}

export const api = {
  health: () => request<{ status: string; capture: string }>("/health"),
  setupStatus: () => request<SetupStatus>("/setup/status"),
  setupPlan: () => request<SetupPlan>("/setup/plan"),
  acceptDisclaimer: (kind: "local" | "openai" = "local") =>
    request<SetupStatus>("/setup/disclaimer", {
      method: "POST",
      body: JSON.stringify({ accepted: true, kind }),
    }),
  bootstrap: (payload?: {
    provider?: Settings["provider"];
    ollama_model?: string;
    whisper_model?: string;
    save_recordings?: boolean;
  }) =>
    request<SetupStatus>("/setup/bootstrap", {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),
  getSettings: () => request<Settings>("/setup/settings"),
  listModels: () => request<ModelsCatalog>("/setup/models"),
  exportDiagnostics: () => download("/setup/diagnostics"),
  saveSettings: (payload: Partial<Settings> & { asr_api_key?: string }) =>
    request<Settings>("/setup/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testApiKey: (asr_api_key?: string) =>
    request<{ ok: boolean; message: string }>("/setup/test-key", {
      method: "POST",
      body: JSON.stringify({ asr_api_key: asr_api_key ?? null }),
    }),
  people: () => request<Person[]>("/people"),
  createPerson: (name: string) =>
    request<Person>("/people", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deletePerson: (id: string) => request<void>(`/people/${id}`, { method: "DELETE" }),
  tags: () => request<Tag[]>("/tags"),
  createTag: (name: string) =>
    request<Tag>("/tags", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteTag: (id: string) => request<void>(`/tags/${id}`, { method: "DELETE" }),
  setSessionTags: (sessionId: string, tagIds: string[]) =>
    request<Tag[]>(`/sessions/${sessionId}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tag_ids: tagIds }),
    }),
  setParticipants: (sessionId: string, personIds: string[]) =>
    request<Person[]>(`/sessions/${sessionId}/participants`, {
      method: "PUT",
      body: JSON.stringify({ person_ids: personIds }),
    }),
  assignSegmentSpeaker: (
    sessionId: string,
    segmentId: string,
    payload: { speaker_id?: string | null; name?: string; text?: string; apply_forward?: boolean },
  ) =>
    request<Segment>(`/sessions/${sessionId}/segments/${segmentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  assignSpeakers: (sessionId: string) =>
    request<Segment[]>(`/sessions/${sessionId}/speakers/assign`, { method: "POST" }),
  devices: () => request<Device[]>("/capture/devices"),
  captureState: () => request<CaptureState>("/capture/state"),
  startCapture: (payload: {
    mic_only?: boolean;
    title?: string;
    loopback_id?: string;
    microphone_id?: string;
    participant_ids?: string[];
    capture_mode?: CaptureMode;
  }) =>
    request<CaptureState>("/capture/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  stopCapture: () => request<CaptureState>("/capture/stop", { method: "POST" }),
  sessions: (tagId?: string) => {
    const query = tagId ? `?tag_id=${encodeURIComponent(tagId)}` : "";
    return request<Session[]>(`/sessions${query}`);
  },
  session: (id: string) => request<SessionDetail>(`/sessions/${id}`),
  renameSession: (id: string, title: string) =>
    request<Session>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteSession: (id: string) =>
    request<void>(`/sessions/${id}`, { method: "DELETE" }),
  search: (q: string, sessionId?: string) => {
    const path = sessionId
      ? `/sessions/${sessionId}/search?q=${encodeURIComponent(q)}`
      : `/sessions/search?q=${encodeURIComponent(q)}`;
    return request<{ query: string; segments: SearchResult["segments"] }>(path);
  },
  summarize: (id: string) =>
    request<Summary>(`/sessions/${id}/summarize`, { method: "POST" }),
  saveNote: (id: string, notes_markdown: string) =>
    request<Summary>(`/sessions/${id}/note`, {
      method: "PUT",
      body: JSON.stringify({ notes_markdown }),
    }),
  sessionAudio: (id: string) => download(`/sessions/${id}/audio`),
  exportSession: (id: string, format: "markdown" | "json" | "pdf" | "docx") =>
    download(`/sessions/${id}/export?format=${format}`),
  exportMarkdown: async (id: string): Promise<string> => {
    const blob = await download(`/sessions/${id}/export?format=markdown`);
    return blob.text();
  },
};

export function openTranscriptSocket(
  onEvent: (event: Record<string, unknown>) => void,
  onStatus?: (live: boolean) => void,
): () => void {
  const url = new URL(backend.url.replace(/^http/, "ws") + "/ws/transcript");
  url.searchParams.set("token", backend.token);
  let closed = false;
  let socket: WebSocket | null = null;
  let retry: number | undefined;

  const connect = () => {
    if (closed) return;
    socket = new WebSocket(url);
    socket.onopen = () => onStatus?.(true);
    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data as string) as Record<string, unknown>);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onerror = () => {
      socket?.close();
    };
    socket.onclose = () => {
      onStatus?.(false);
      if (!closed) {
        if (retry) window.clearTimeout(retry);
        retry = window.setTimeout(connect, 1500);
      }
    };
  };
  connect();
  return () => {
    closed = true;
    if (retry) window.clearTimeout(retry);
    socket?.close();
  };
}
