import { useCallback, useEffect, useRef, useState } from "react";

import { FolderSidebar } from "../features/session/FolderSidebar";
import { SessionSidebarItem } from "../features/session/SessionSidebarItem";
import { Wizard } from "../features/setup/Wizard";
import { LivePage } from "../pages/LivePage";
import { SessionPage } from "../pages/SessionPage";
import { SettingsPage } from "../pages/SettingsPage";
import { api, openTranscriptSocket, setBackend } from "../shared/api/client";
import type { CaptureMode, CaptureState, Device, MonitorFrame, Provider, Segment, Session, Settings, Tag } from "../shared/api/types";
import { mergeSegmentLists } from "../shared/lib/segments";
import { AppVersion, BrandLockup, SiteCredit } from "../shared/ui/Brand";
import { BootScreen } from "../shared/ui/BootScreen";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { EngineSwitch } from "../shared/ui/EngineSwitch";
import { useToast } from "../shared/ui/Toast";

type View = "live" | "session" | "settings";

const idleCapture: CaptureState = {
  recording: false,
  session_id: null,
  mic_only: false,
  warning: null,
  phase: "idle",
  started_at: null,
};

export function App() {
  const [ready, setReady] = useState(false);
  const [needsWizard, setNeedsWizard] = useState(true);
  const [view, setView] = useState<View>("live");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [capture, setCapture] = useState<CaptureState>(idleCapture);
  const [liveSegments, setLiveSegments] = useState<Segment[]>([]);
  const [micOnly, setMicOnly] = useState(false);
  const [captureMode, setCaptureMode] = useState<CaptureMode>("meeting");
  const [loopbackId, setLoopbackId] = useState("");
  const [participantIds, setParticipantIds] = useState<string[]>([]);
  const [language, setLanguage] = useState("pt");
  const [asrProvider, setAsrProvider] = useState<Provider>("neste_pc");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [openaiDisclaimer, setOpenaiDisclaimer] = useState(false);
  const [providerBusy, setProviderBusy] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const confirm = useConfirm();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<"start" | "stop" | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [monitor, setMonitor] = useState<MonitorFrame | null>(null);
  const [asrBusy, setAsrBusy] = useState(false);
  const [asrEmpty, setAsrEmpty] = useState(false);
  const [asrQueued, setAsrQueued] = useState(0);
  const [speakersBusy, setSpeakersBusy] = useState(false);
  const [socketLive, setSocketLive] = useState(false);
  const [lastMonitorAt, setLastMonitorAt] = useState<number | null>(null);
  const [monitorStale, setMonitorStale] = useState(false);
  const [socketGeneration, setSocketGeneration] = useState(0);
  const staleReconnectTriggered = useRef(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [bootAttempt, setBootAttempt] = useState(0);

  const loadSessions = useCallback(async () => {
    const listed = await api.sessions();
    setSessions(listed);
    try {
      setTags(await api.tags());
    } catch {
      setTags([]);
    }
  }, []);

  const applyEngineSettings = useCallback((settings: Settings) => {
    setAsrProvider(settings.provider === "openai" ? "openai" : "neste_pc");
    setHasApiKey(Boolean(settings.has_api_key));
    setOpenaiDisclaimer(Boolean(settings.openai_disclaimer_accepted));
  }, []);

  const enginePrepRef = useRef(0);

  const prepareLocalEngine = useCallback(async () => {
    const token = ++enginePrepRef.current;
    let status = await api.setupStatus();
    if (token !== enginePrepRef.current) return;
    if (status.capture_ready) {
      setCaptureError(null);
      return;
    }
    toast.push({
      tone: "info",
      title: "Preparando modelos locais",
      description: "O Whisper ainda não está neste PC. O download começa agora.",
    });
    setCaptureError(status.whisper.message);
    await api.bootstrap({ provider: "neste_pc" });
    let stuckMissing = 0;
    while (token === enginePrepRef.current) {
      status = await api.setupStatus();
      if (token !== enginePrepRef.current) return;
      if (status.capture_ready) {
        setCaptureError(null);
        toast.push({
          tone: "success",
          title: "Modelos locais prontos",
          description: "Pode ligar a captura.",
        });
        return;
      }
      if (status.whisper.status === "error") {
        setCaptureError(status.whisper.message);
        toast.push({
          tone: "error",
          title: "Não deu para carregar os modelos locais",
          description: status.whisper.message,
        });
        return;
      }
      if (status.whisper.status === "missing") {
        stuckMissing += 1;
        if (stuckMissing > 8) {
          setCaptureError(status.whisper.message);
          return;
        }
      } else {
        stuckMissing = 0;
      }
      setCaptureError(status.whisper.message);
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
  }, [toast]);

  const switchProvider = useCallback(
    async (next: Provider) => {
      if (next === asrProvider || providerBusy) return;
      if (next === "openai" && !hasApiKey) {
        toast.push({
          tone: "info",
          title: "Falta a chave da OpenAI",
          description: "Cole a chave em Preferências para ligar a API.",
        });
        setView("settings");
        return;
      }
      if (next === "openai" && !openaiDisclaimer) {
        const ok = await confirm({
          title: "Usar a API OpenAI?",
          description:
            "O áudio da transcrição e trechos da nota saem deste computador e vão para a OpenAI.",
          confirmLabel: "Usar OpenAI",
        });
        if (!ok) return;
      }
      setProviderBusy(true);
      try {
        const saved = await api.saveSettings({
          provider: next,
          openai_disclaimer_accepted: next === "openai" ? true : undefined,
        });
        applyEngineSettings(saved);
        if (next === "neste_pc") {
          void prepareLocalEngine();
        } else {
          enginePrepRef.current += 1;
          setCaptureError(null);
        }
      } catch (err) {
        toast.push({
          tone: "error",
          title: "Não foi possível trocar o motor",
          description: err instanceof Error ? err.message : "Tente de novo em Preferências.",
        });
      } finally {
        setProviderBusy(false);
      }
    },
    [
      applyEngineSettings,
      asrProvider,
      confirm,
      hasApiKey,
      openaiDisclaimer,
      prepareLocalEngine,
      providerBusy,
      toast,
    ],
  );

  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      setBootError(null);
      setReady(false);
      try {
        const invoke = await getTauriInvoke();
        if (invoke) {
          const info = await invoke("get_backend");
          setBackend(info);
        }
        const status = await api.setupStatus();
        const settings = await api.getSettings();
        if (!cancelled) {
          setMicOnly(settings.mic_only_default);
          setLanguage(settings.language ?? "pt");
          applyEngineSettings(settings);
          const wizard = !status.disclaimer_accepted || !status.setup_complete;
          setNeedsWizard(wizard);
          if (!status.audio_ok) {
            setCaptureError(
              status.audio_message ||
                "Nenhum microfone detectado. Verifique as permissões de privacidade do Windows.",
            );
          } else if (!status.capture_ready) {
            setCaptureError(status.whisper.message || "Modelo de transcrição ainda não está pronto");
            if (settings.provider !== "openai" && !wizard) void prepareLocalEngine();
          }
          setReady(true);
        }
        try {
          const listed = await api.devices();
          if (!cancelled) setDevices(listed);
        } catch {
          /* devices optional until capture */
        }
        await loadSessions();
        const state = await api.captureState();
        if (!cancelled) {
          setCapture(state);
          if (state.session_id) setActiveId(state.session_id);
        }
      } catch (err) {
        if (!cancelled) {
          setBootError(
            err instanceof Error
              ? err.message
              : "Não foi possível abrir o backend local. Feche outras janelas do DroidNote e tente de novo.",
          );
          setReady(true);
        }
      }
    };
    void boot();
    return () => {
      cancelled = true;
    };
  }, [loadSessions, bootAttempt]);

  useEffect(() => {
    if (!ready || needsWizard) return;
    return openTranscriptSocket(
      (event) => {
        if (event.type === "hello") {
          setCapture((current) => ({
            ...current,
            recording:
              typeof event.recording === "boolean" ? event.recording : current.recording,
            session_id:
              typeof event.session_id === "string" ? event.session_id : current.session_id,
            started_at:
              typeof event.started_at === "string" ? event.started_at : current.started_at,
          }));
          if (event.recording === false) {
            setMonitor(null);
            setLastMonitorAt(null);
          } else if (event.recording === true) {
            setLastMonitorAt((current) => current ?? Date.now());
          }
        }
        if (event.type === "segment" && isSegment(event.segment)) {
          const segment = event.segment;
          setLiveSegments((current) => {
            const existing = current.find((item) => item.id === segment.id);
            const next =
              existing?.speaker_id && !segment.speaker_id
                ? {
                    ...segment,
                    speaker_id: existing.speaker_id,
                    speaker_name: existing.speaker_name ?? segment.speaker_name,
                  }
                : segment;
            return [...current.filter((item) => item.id !== next.id), next];
          });
        }
        if (event.type === "capture") {
          setCapture((current) => ({
            ...current,
            recording: Boolean(event.recording),
            session_id: typeof event.session_id === "string" ? event.session_id : current.session_id,
            phase: isPhase(event.phase) ? event.phase : current.phase,
            warning: typeof event.warning === "string" ? event.warning : current.warning,
            loopback_name:
              typeof event.loopback_name === "string" ? event.loopback_name : current.loopback_name,
            started_at: event.recording
              ? typeof event.started_at === "string"
                ? event.started_at
                : current.started_at
              : null,
          }));
          if (typeof event.session_id === "string") setActiveId(event.session_id);
          if (!event.recording) {
            setMonitor(null);
            setLastMonitorAt(null);
          } else {
            setLastMonitorAt((current) => current ?? Date.now());
          }
          void loadSessions();
        }
        if (event.type === "monitor" && isMonitor(event)) {
          setMonitor(toMonitor(event));
          setLastMonitorAt(Date.now());
          setMonitorStale(false);
          staleReconnectTriggered.current = false;
        }
        if (event.type === "asr") {
          const queued = typeof event.queued === "number" ? event.queued : 0;
          if (typeof event.queued === "number") setAsrQueued(queued);
          if (event.status === "start" || queued > 0) {
            setAsrBusy(true);
          }
          if (event.status === "done") {
            setAsrEmpty(Boolean(event.empty));
            if (queued === 0) setAsrBusy(false);
          }
        }
        if (event.type === "speakers") {
          setSpeakersBusy(event.status === "start");
        }
      },
      (live) => {
        setSocketLive(live);
        if (!live) {
          setMonitor(null);
          setLastMonitorAt(null);
          setMonitorStale(true);
        }
      },
    );
  }, [ready, needsWizard, loadSessions, socketGeneration]);

  useEffect(() => {
    if (!capture.recording) {
      setMonitorStale(false);
      return undefined;
    }
    const check = () => {
      const stale = !socketLive || lastMonitorAt === null || Date.now() - lastMonitorAt > 2400;
      setMonitorStale(stale);
      if (stale && socketLive && !staleReconnectTriggered.current) {
        staleReconnectTriggered.current = true;
        setSocketGeneration((generation) => generation + 1);
      }
    };
    check();
    const timer = window.setInterval(check, 600);
    return () => window.clearInterval(timer);
  }, [capture.recording, lastMonitorAt, socketLive]);

  useEffect(() => {
    if (!capture.recording || !activeId) return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const detail = await api.session(activeId);
        if (cancelled) return;
        setLiveSegments((current) => mergeSegmentLists(current, detail.segments));
      } catch {
        /* poll is a fallback */
      }
    };
    const timer = window.setInterval(() => void tick(), 2000);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [capture.recording, activeId]);

  const toggle = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setCaptureError(null);
    const previous = capture;
    try {
      if (capture.recording) {
        setPending("stop");
        setCapture({ ...capture, recording: false, phase: "idle" });
        const state = await api.stopCapture();
        setCapture(state);
        setMonitor(null);
        setLastMonitorAt(null);
        await loadSessions();
        return;
      }
      setPending("start");
      setAsrEmpty(false);
      staleReconnectTriggered.current = false;
      const state = await api.startCapture({
        mic_only: captureMode === "dictation" ? true : micOnly,
        loopback_id: loopbackId || undefined,
        participant_ids: participantIds,
        capture_mode: captureMode,
      });
      setCapture(state);
      setLastMonitorAt(Date.now());
      setLiveSegments([]);
      if (state.session_id) setActiveId(state.session_id);
      setView("live");
      await loadSessions();
    } catch (error) {
      setCapture(previous);
      setCaptureError(error instanceof Error ? error.message : "Falha na captura");
      try {
        setCapture(await api.captureState());
      } catch {
        /* keep previous */
      }
    } finally {
      setPending(null);
      setBusy(false);
    }
  }, [busy, capture, loadSessions, micOnly, loopbackId, participantIds, captureMode]);

  useEffect(() => {
    if (!ready || needsWizard) return undefined;
    let unlisten: (() => void) | undefined;
    void import("@tauri-apps/api/event")
      .then(({ listen }) => listen("tray-toggle-capture", () => void toggle()))
      .then((fn) => {
        unlisten = fn;
      })
      .catch(() => undefined);
    return () => unlisten?.();
  }, [ready, needsWizard, toggle]);

  if (!ready) {
    return <BootScreen message="Carregando…" />;
  }

  if (bootError) {
    return (
      <BootScreen
        message="Carregando…"
        error={bootError}
        onRetry={() => {
          setReady(false);
          setBootAttempt((current) => current + 1);
        }}
      />
    );
  }

  if (needsWizard) {
    return <Wizard onDone={() => setNeedsWizard(false)} />;
  }

  const visibleSessions = tagFilter
    ? sessions.filter((item) => (item.tags ?? []).some((tag) => tag.id === tagFilter))
    : sessions;
  const sessionCountByFolder = new Map<string, number>();
  for (const session of sessions) {
    for (const tag of session.tags ?? []) {
      sessionCountByFolder.set(tag.id, (sessionCountByFolder.get(tag.id) ?? 0) + 1);
    }
  }

  const createFolder = async (name: string) => {
    const folder = await api.createTag(name);
    setTags(await api.tags());
    setTagFilter(folder.id);
  };

  const deleteFolder = async (folder: Tag) => {
    await api.deleteTag(folder.id);
    if (tagFilter === folder.id) setTagFilter(null);
    await loadSessions();
  };

  const moveSessionToFolder = async (sessionId: string, folderId: string | null) => {
    const assigned = await api.setSessionTags(sessionId, folderId ? [folderId] : []);
    setSessions((current) =>
      current.map((session) => session.id === sessionId ? { ...session, tags: assigned } : session),
    );
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <BrandLockup size="sidebar" />
          <EngineSwitch
            value={asrProvider}
            disabled={providerBusy || capture.recording || pending !== null}
            onChange={(next) => void switchProvider(next)}
          />
        </div>
        <nav className="nav nav-primary" aria-label="Principal">
          <button
            className={view === "live" ? "active" : ""}
            aria-current={view === "live" ? "page" : undefined}
            onClick={() => setView("live")}
            type="button"
          >
            <NavIcon name="live" />
            <span>Ao vivo</span>
          </button>
          <button
            className={view === "settings" ? "active" : ""}
            aria-current={view === "settings" ? "page" : undefined}
            onClick={() => setView("settings")}
            type="button"
          >
            <NavIcon name="settings" />
            <span>Preferências</span>
          </button>
        </nav>
        <div className="sidebar-section">
          <FolderSidebar
            folders={tags}
            selectedId={tagFilter}
            sessionCount={sessions.length}
            countByFolder={sessionCountByFolder}
            onSelect={setTagFilter}
            onCreate={createFolder}
            onDelete={deleteFolder}
            onMoveSession={(sessionId, folderId) => moveSessionToFolder(sessionId, folderId)}
          />
          <div className="conversation-heading">Conversas</div>
          <div className="session-list">
            {visibleSessions.length === 0 ? (
              <div className="empty-block">Nenhuma sessão ainda. Ligue a captura para criar a primeira.</div>
            ) : (
              visibleSessions.map((session) => (
                <SessionSidebarItem
                  key={session.id}
                  session={session}
                  folders={tags}
                  active={session.id === activeId && view === "session"}
                  onOpen={() => {
                    setActiveId(session.id);
                    setView("session");
                  }}
                  onMove={moveSessionToFolder}
                />
              ))
            )}
          </div>
        </div>
        <div className="sidebar-footer">
          <AppVersion />
          <SiteCredit className="sidebar-credit" />
        </div>
      </aside>
      <main className={view === "live" || view === "session" ? "main main-workspace" : "main"}>
        {view !== "live" && (capture.recording || asrBusy || speakersBusy) ? (
          <p className="banner processing-banner">Há uma transcrição ativa</p>
        ) : null}
        {view === "live" ? (
          <LivePage
            capture={capture}
            sessionId={activeId}
            liveSegments={liveSegments}
            busy={busy}
            error={captureError}
            pending={pending}
            micOnly={micOnly}
            monitor={monitor}
            asrBusy={asrBusy}
            asrEmpty={asrEmpty}
            asrQueued={asrQueued}
            speakersBusy={speakersBusy}
            socketLive={socketLive}
            monitorStale={monitorStale}
            loopbackId={loopbackId}
            devices={devices}
            onMicOnlyChange={setMicOnly}
            onLoopbackChange={setLoopbackId}
            onToggle={() => void toggle()}
            onTitleChange={async (title) => {
              if (!activeId) return;
              const updated = await api.renameSession(activeId, title);
              setSessions((current) =>
                current.map((item) => (item.id === updated.id ? updated : item)),
              );
            }}
            participantIds={participantIds}
            onParticipantIdsChange={setParticipantIds}
            languageLocked={language !== "auto"}
            captureMode={captureMode}
            engineProvider={asrProvider}
            onCaptureModeChange={(mode) => {
              setCaptureMode(mode);
              if (mode === "dictation") setMicOnly(true);
              if (mode === "lecture" || mode === "meeting") setMicOnly(false);
            }}
          />
        ) : null}
        {view === "session" && activeId ? (
          <SessionPage
            sessionId={activeId}
            onDeleted={() => {
              setActiveId(null);
              setView("live");
              void loadSessions();
            }}
            onRenamed={(title) => {
              if (!activeId) return;
              setSessions((current) =>
                current.map((item) => (item.id === activeId ? { ...item, title } : item)),
              );
            }}
            onTagsChanged={() => void loadSessions()}
            languageLocked={language !== "auto"}
          />
        ) : null}
        {view === "settings" ? (
          <SettingsPage
            engineProvider={asrProvider}
            onSaved={(next) => {
              setMicOnly(next.mic_only_default);
              setLanguage(next.language ?? "pt");
              applyEngineSettings(next);
            }}
          />
        ) : null}
      </main>
    </div>
  );
}

type NavIconName = "live" | "settings";

function NavIcon({ name }: { name: NavIconName }) {
  return (
    <span className="nav-icon" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none">
        {name === "live" ? (
          <>
            <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
            <path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4" />
            <path d="M4.6 4.6a10.5 10.5 0 0 0 0 14.8M19.4 4.6a10.5 10.5 0 0 1 0 14.8" />
          </>
        ) : null}
        {name === "settings" ? (
          <>
            <path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h7M15 18h5" />
            <circle cx="16" cy="6" r="2" />
            <circle cx="8" cy="12" r="2" />
            <circle cx="13" cy="18" r="2" />
          </>
        ) : null}
      </svg>
    </span>
  );
}

function isSegment(value: unknown): value is Segment {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.id === "string" && typeof record.text === "string";
}

function isPhase(value: unknown): value is NonNullable<CaptureState["phase"]> {
  return value === "idle" || value === "loading" || value === "listening" || value === "transcribing";
}

function isMonitor(value: Record<string, unknown>): boolean {
  return Array.isArray(value.bars) && typeof value.rms === "number";
}

function toMonitor(value: Record<string, unknown>): MonitorFrame {
  const bars = Array.isArray(value.bars)
    ? value.bars.filter((item): item is number => typeof item === "number")
    : [];
  return {
    rms: typeof value.rms === "number" ? value.rms : 0,
    speech: Boolean(value.speech),
    bars,
    queued: typeof value.queued === "number" ? value.queued : 0,
    buffer_ms: typeof value.buffer_ms === "number" ? value.buffer_ms : 0,
    phase: typeof value.phase === "string" ? value.phase : "listening",
    whisper_loaded: Boolean(value.whisper_loaded),
  };
}

async function getTauriInvoke(): Promise<
  | ((cmd: string) => Promise<{ url: string; token: string }>)
  | null
> {
  if (!("__TAURI_INTERNALS__" in window)) {
    return null;
  }
  try {
    const module = await import("@tauri-apps/api/core");
    return module.invoke as (cmd: string) => Promise<{ url: string; token: string }>;
  } catch {
    return null;
  }
}
