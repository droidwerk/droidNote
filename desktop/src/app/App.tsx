import { useCallback, useEffect, useRef, useState } from "react";

import { CommandPalette } from "../features/command/CommandPalette";
import { MeetingBanner, type MeetingNotice } from "../features/meeting/MeetingBanner";
import { SessionSidebarItem } from "../features/session/SessionSidebarItem";
import { Wizard } from "../features/setup/Wizard";
import { ChatPage } from "../pages/ChatPage";
import { LivePage } from "../pages/LivePage";
import { SessionPage } from "../pages/SessionPage";
import { SettingsPage, type SettingsTab } from "../pages/SettingsPage";
import { LibraryPage } from "../pages/LibraryPage";
import { TasksPage } from "../pages/TasksPage";
import { copyConsent } from "../features/consent/consent";
import { api, openTranscriptSocket, setBackend } from "../shared/api/client";
import type { CaptureMode, CaptureState, ChatFocus, Device, MonitorFrame, NoteTemplate, Provider, Segment, Session, Settings, Tag } from "../shared/api/types";
import { isCaptureLanguage, isUiLanguage, useI18n, type CaptureLanguage } from "../shared/i18n";
import { openMiniWindow, requestAttention } from "../shared/lib/miniWindow";
import { mergeSegmentLists } from "../shared/lib/segments";
import { useFlag } from "../shared/lib/useFlag";
import { useUpdateNotice } from "../shared/lib/useUpdateNotice";
import { AppVersion, BrandLockup, SiteCredit } from "../shared/ui/Brand";
import { BootScreen } from "../shared/ui/BootScreen";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { EngineSwitch } from "../shared/ui/EngineSwitch";
import { Icon, type IconName } from "../shared/ui/Icon";
import { StatusStrip } from "../shared/ui/StatusStrip";
import { useToast } from "../shared/ui/Toast";

type View = "live" | "session" | "settings" | "chat" | "tasks" | "library";

const RECENT_LIMIT = 14;

const idleCapture: CaptureState = {
  recording: false,
  session_id: null,
  mic_only: false,
  warning: null,
  phase: "idle",
  started_at: null,
};

export function App() {
  const { t, setLocale } = useI18n();
  const [ready, setReady] = useState(false);
  const [needsWizard, setNeedsWizard] = useState(true);
  const [view, setView] = useState<View>("live");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  /** Sessão da captura (a que o "Ao vivo" mostra); independe da conversa aberta em "Conversas". */
  const [captureId, setCaptureId] = useState<string | null>(null);
  const [capture, setCapture] = useState<CaptureState>(idleCapture);
  const [liveSegments, setLiveSegments] = useState<Segment[]>([]);
  const [micOnly, setMicOnly] = useState(false);
  const [captureMode, setCaptureMode] = useState<CaptureMode>("meeting");
  const [loopbackId, setLoopbackId] = useState("");
  const [participantIds, setParticipantIds] = useState<string[]>([]);
  const [language, setLanguage] = useState<CaptureLanguage>("pt");
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
  const [asrQueued, setAsrQueued] = useState(0);
  const [speakersBusy, setSpeakersBusy] = useState(false);
  const [socketLive, setSocketLive] = useState(false);
  const [lastMonitorAt, setLastMonitorAt] = useState<number | null>(null);
  const [monitorStale, setMonitorStale] = useState(false);
  const [socketGeneration, setSocketGeneration] = useState(0);
  const staleReconnectTriggered = useRef(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [bootAttempt, setBootAttempt] = useState(0);
  const [chatFocus, setChatFocus] = useState<ChatFocus | null>(null);
  const [voicesRevision, setVoicesRevision] = useState(0);
  const [voiceReady, setVoiceReady] = useState<boolean | null>(null);
  const [voiceDownloading, setVoiceDownloading] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sessionSeek, setSessionSeek] = useState<number | null>(null);
  const [templates, setTemplates] = useState<NoteTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [meetingNotice, setMeetingNotice] = useState<MeetingNotice | null>(null);
  const [notesRevision, setNotesRevision] = useState(0);
  const [tasksRevision, setTasksRevision] = useState(0);
  const [openTasks, setOpenTasks] = useState(0);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("transcription");
  const [navCollapsed, toggleNav] = useFlag("droidnote.navCollapsed");
  const [summaryBusy, setSummaryBusy] = useState<string | null>(null);
  const [summaryRevision, setSummaryRevision] = useState(0);
  const [memoryRevision, setMemoryRevision] = useState(0);
  // O socket é criado uma vez; a reação à ata automática lê sempre o estado atual por aqui.
  const onSummaryEvent = useRef<(event: Record<string, unknown>) => void>(() => undefined);
  const recordingRef = useRef(false);
  const loadTemplates = useCallback(async () => {
    try {
      setTemplates(await api.templates());
    } catch {
      setTemplates([]);
    }
  }, []);
  const [engineInfo, setEngineInfo] = useState({ asr: "—", note: "—" });
  const captureIdRef = useRef<string | null>(null);
  captureIdRef.current = captureId;
  useUpdateNotice(ready && !needsWizard && !bootError);

  const openChat = useCallback((focus?: ChatFocus) => {
    setChatFocus(focus ?? null);
    setView("chat");
  }, []);

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
    const cloud = settings.provider === "openai";
    setAsrProvider(cloud ? "openai" : "neste_pc");
    setHasApiKey(Boolean(settings.has_api_key));
    setOpenaiDisclaimer(Boolean(settings.openai_disclaimer_accepted));
    setEngineInfo({
      asr: cloud
        ? settings.asr_cloud_model ?? "OpenAI"
        : `Whisper ${settings.whisper_model}${settings.whisper_device && settings.whisper_device !== "auto" ? ` · ${settings.whisper_device}` : ""}`,
      note: cloud ? settings.llm_cloud_model ?? "OpenAI" : settings.ollama_model,
    });
  }, []);

  const watchVoiceEngine = useCallback(async () => {
    for (let attempt = 0; attempt < 240; attempt += 1) {
      try {
        const status = await api.setupStatus();
        const voice = status.voice;
        if (!voice) {
          setVoiceReady(false);
          setVoiceDownloading(false);
          return;
        }
        if (voice.status === "ready") {
          setVoiceReady(true);
          setVoiceDownloading(false);
          return;
        }
        setVoiceReady(false);
        if (voice.status === "error" || voice.status === "missing") {
          setVoiceDownloading(false);
          return;
        }
        setVoiceDownloading(true);
      } catch {
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
    }
  }, []);

  const downloadVoice = useCallback(async () => {
    setVoiceDownloading(true);
    try {
      await api.downloadVoice();
    } catch (err) {
      setVoiceDownloading(false);
      toast.push({ tone: "error", title: err instanceof Error ? err.message : t("voices.download") });
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 600));
    await watchVoiceEngine();
  }, [toast, t, watchVoiceEngine]);

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
      title: t("engine.preparingTitle"),
      description: t("engine.preparingBody"),
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
          title: t("engine.readyTitle"),
          description: t("engine.readyBody"),
        });
        return;
      }
      if (status.whisper.status === "error") {
        setCaptureError(status.whisper.message);
        toast.push({
          tone: "error",
          title: t("engine.loadFailTitle"),
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
  }, [t, toast]);

  const switchProvider = useCallback(
    async (next: Provider) => {
      if (next === asrProvider || providerBusy) return;
      if (next === "openai" && !hasApiKey) {
        toast.push({
          tone: "info",
          title: t("engine.missingKeyTitle"),
          description: t("engine.missingKeyBody"),
        });
        setView("settings");
        return;
      }
      if (next === "openai" && !openaiDisclaimer) {
        const ok = await confirm({
          title: t("engine.useOpenaiTitle"),
          description: t("engine.useOpenaiBody"),
          confirmLabel: t("engine.useOpenaiConfirm"),
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
          title: t("engine.switchFailTitle"),
          description: err instanceof Error ? err.message : t("engine.switchFailBody"),
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
      t,
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
        // O motor local pode levar alguns segundos a mais para abrir a porta
        // (antivírus, banco grande): erro de rede no início vira nova tentativa.
        const status = await untilBackendAnswers(() => api.setupStatus(), () => cancelled);
        const settings = await api.getSettings();
        if (!cancelled) {
          if (isUiLanguage(settings.ui_language)) setLocale(settings.ui_language);
          setMicOnly(settings.mic_only_default);
          setLanguage(isCaptureLanguage(settings.language) ? settings.language : "pt");
          applyEngineSettings(settings);
          const wizard = !status.disclaimer_accepted || !status.setup_complete;
          setNeedsWizard(wizard);
          setVoiceReady(status.voice ? status.voice.status === "ready" : false);
          if (status.voice?.status === "downloading") {
            setVoiceDownloading(true);
            void watchVoiceEngine();
          }
          if (!status.audio_ok) {
            setCaptureError(
              status.audio_message || t("engine.noMic"),
            );
          } else if (!status.capture_ready) {
            setCaptureError(status.whisper.message || t("engine.asrNotReady"));
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
          if (state.session_id) setCaptureId(state.session_id);
        }
      } catch (err) {
        if (!cancelled) {
          setBootError(
            err instanceof Error && !isNetworkError(err)
              ? err.message
              : t("boot.backendFailed"),
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
          if (typeof event.session_id === "string") setCaptureId(event.session_id);
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
            if (queued === 0) setAsrBusy(false);
          }
        }
        if (event.type === "speakers") {
          setSpeakersBusy(event.status === "start");
        }
        if (event.type === "meeting") {
          const app = typeof event.app === "string" ? event.app : "";
          if (event.status === "detected" || event.status === "auto-started") {
            setMeetingNotice({ status: event.status, app, browser: Boolean(event.browser) });
            if (event.status === "detected") void requestAttention();
          } else if (event.status === "ended") {
            setMeetingNotice(event.recording ? { status: "ended", app, browser: false } : null);
          } else if (event.status === "dismissed") {
            setMeetingNotice(null);
          }
        }
        if (event.type === "note") {
          setNotesRevision((value) => value + 1);
        }
        if (event.type === "tasks") {
          setTasksRevision((value) => value + 1);
        }
        if (event.type === "summary") {
          onSummaryEvent.current(event);
        }
        if (event.type === "memory" && event.status === "done") {
          setMemoryRevision((value) => value + 1);
        }
        if (event.type === "voices") {
          setVoicesRevision((value) => value + 1);
          const current = captureIdRef.current;
          if (current && event.session_id === current) {
            void api
              .session(current)
              .then((detail) => setLiveSegments((list) => mergeSegmentLists(list, detail.segments)))
              .catch(() => undefined);
          }
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
    if (!capture.recording || !captureId) return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const detail = await api.session(captureId);
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
  }, [capture.recording, captureId]);

  const toggle = useCallback(async (override?: { mode?: CaptureMode; title?: string }) => {
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
      staleReconnectTriggered.current = false;
      const mode = override?.mode ?? captureMode;
      const state = await api.startCapture({
        mic_only: mode === "dictation" ? true : micOnly,
        loopback_id: loopbackId || undefined,
        participant_ids: participantIds,
        capture_mode: mode,
        title: override?.title,
        template_id: templateId,
      });
      setCapture(state);
      setLastMonitorAt(Date.now());
      setLiveSegments([]);
      if (state.session_id) setCaptureId(state.session_id);
      setView("live");
      await loadSessions();
    } catch (error) {
      setCapture(previous);
      setCaptureError(error instanceof Error ? error.message : t("engine.captureFail"));
      try {
        setCapture(await api.captureState());
      } catch {
        /* keep previous */
      }
    } finally {
      setPending(null);
      setBusy(false);
    }
  }, [busy, capture, loadSessions, micOnly, loopbackId, participantIds, captureMode, templateId, t]);

  // Mini console abre sozinho quando a gravação começa (preferência deste PC).
  useEffect(() => {
    const was = recordingRef.current;
    recordingRef.current = capture.recording;
    if (!was && capture.recording && "__TAURI_INTERNALS__" in window) {
      let auto = true;
      try {
        auto = window.localStorage.getItem("droidnote.miniAuto") !== "0";
      } catch {
        /* padrão: abre */
      }
      if (auto) void openMiniWindow();
    }
    if (was && !capture.recording) setNotesRevision((value) => value + 1);
  }, [capture.recording]);

  useEffect(() => {
    if (!ready || needsWizard) return;
    void api
      .tasks("open")
      .then((items) => setOpenTasks(items.length))
      .catch(() => undefined);
  }, [ready, needsWizard, tasksRevision]);

  const consent = useCallback(() => {
    void copyConsent(t).then((ok) =>
      toast.push({
        tone: ok ? "success" : "error",
        title: ok ? t("consent.copied") : t("consent.copyFail"),
        description: ok ? t("consent.copiedHint") : undefined,
      }),
    );
  }, [t, toast]);

  const openSettings = (tab: SettingsTab = "transcription") => {
    setSettingsTab(tab);
    setView("settings");
  };

  onSummaryEvent.current = (event) => {
    const sessionId = typeof event.session_id === "string" ? event.session_id : null;
    if (!sessionId) return;
    const title = sessions.find((item) => item.id === sessionId)?.title ?? "";
    if (event.status === "start") {
      setSummaryBusy(sessionId);
      return;
    }
    setSummaryBusy((current) => (current === sessionId ? null : current));
    setSummaryRevision((value) => value + 1);
    if (event.status === "done") {
      toast.push({
        tone: "success",
        title: t("doc.readyTitle"),
        description: title || undefined,
        action: { label: t("doc.readyOpen"), onClick: () => openSession(sessionId) },
      });
    } else if (event.status === "skipped") {
      toast.push({ tone: "info", title: t("engine.offTitle"), description: t("doc.skipped") });
    } else if (event.status === "error") {
      toast.push({ tone: "error", title: t("doc.failed") });
    }
  };

  useEffect(() => {
    if (!ready || needsWizard) return;
    void loadTemplates();
    void api
      .meeting()
      .then((status) => {
        if (status.active && !status.dismissed && status.app) {
          setMeetingNotice({ status: "detected", app: status.app, browser: Boolean(status.browser) });
        }
      })
      .catch(() => undefined);
  }, [ready, needsWizard, loadTemplates]);

  useEffect(() => {
    if (!ready || needsWizard) return undefined;
    const onKey = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && key === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      } else if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === "r") {
        event.preventDefault();
        void toggle();
      } else if ((event.ctrlKey || event.metaKey) && !event.shiftKey && key === "b") {
        event.preventDefault();
        toggleNav();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ready, needsWizard, toggle, toggleNav]);

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
    return <BootScreen message={t("boot.loading")} />;
  }

  if (bootError) {
    return (
      <BootScreen
        message={t("boot.loading")}
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

  const recentSessions = sessions.slice(0, RECENT_LIMIT);

  const moveSessionToFolder = async (sessionId: string, folderId: string | null) => {
    const assigned = await api.setSessionTags(sessionId, folderId ? [folderId] : []);
    setSessions((current) =>
      current.map((session) => session.id === sessionId ? { ...session, tags: assigned } : session),
    );
  };

  const openSession = (sessionId: string, atMs?: number) => {
    setActiveId(sessionId);
    setSessionSeek(atMs ?? null);
    setView("session");
  };

  const groups = groupByDay(recentSessions, t);

  return (
    <div className={["shell", capture.recording ? "is-recording" : "", navCollapsed ? "is-nav-collapsed" : ""].filter(Boolean).join(" ")}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <BrandLockup size="sidebar" />
          <button
            type="button"
            className="sidebar-toggle"
            onClick={toggleNav}
            title={`${navCollapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")} (Ctrl+B)`}
            aria-label={navCollapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
            aria-expanded={!navCollapsed}
          >
            <Icon name="rail" size={16} />
          </button>
        </div>
        <nav className="nav" aria-label={t("nav.primary")}>
          <NavButton icon="console" label={t("nav.live")} active={view === "live"} onClick={() => setView("live")} badge={capture.recording ? "rec" : undefined} />
          <NavButton icon="folder" label={t("nav.library")} active={view === "library"} onClick={() => setView("library")} />
          <NavButton icon="tasks" label={t("nav.tasks")} active={view === "tasks"} onClick={() => setView("tasks")} badge={openTasks ? String(openTasks) : undefined} />
          <NavButton icon="chat" label={t("nav.chat")} active={view === "chat"} onClick={() => openChat()} badge={t("common.beta")} />
          <NavButton icon="settings" label={t("nav.settings")} active={view === "settings"} onClick={() => openSettings()} />
        </nav>
        <div className="sidebar-section">
          <div className="sidebar-heading">
            <span>{t("nav.recent")}</span>
          </div>
          <div className="session-list">
            {recentSessions.length === 0 ? (
              <div className="empty-block">{t("nav.emptySessions")}</div>
            ) : (
              groups.map((group) => (
                <div className="session-group" key={group.label}>
                  <span className="session-group-label">{group.label}</span>
                  {group.items.map((session) => (
                    <SessionSidebarItem
                      key={session.id}
                      session={session}
                      folders={tags}
                      live={capture.recording && capture.session_id === session.id}
                      active={session.id === activeId && view === "session"}
                      onOpen={() => openSession(session.id)}
                      onMove={moveSessionToFolder}
                    />
                  ))}
                </div>
              ))
            )}
            {sessions.length > recentSessions.length ? (
              <button type="button" className="sidebar-all" onClick={() => setView("library")}>
                {t("nav.seeAll", { count: sessions.length })}
                <Icon name="arrow" size={13} />
              </button>
            ) : null}
          </div>
        </div>
        <div className="sidebar-footer">
          <EngineSwitch
            value={asrProvider}
            disabled={providerBusy || capture.recording || pending !== null}
            onChange={(next) => void switchProvider(next)}
          />
          <div className="sidebar-credit-row">
            <SiteCredit className="sidebar-credit" />
            <AppVersion />
          </div>
        </div>
      </aside>
      <main className="main">
        <StatusStrip
          recording={capture.recording}
          socketLive={socketLive}
          provider={asrProvider}
          asrLabel={engineInfo.asr}
          noteLabel={engineInfo.note}
          voiceReady={voiceReady}
          onOpenPalette={() => setPaletteOpen(true)}
        />
        <div className="main-scroll">
          {meetingNotice ? (
            <MeetingBanner
              notice={meetingNotice}
              recording={capture.recording}
              busy={busy}
              onRecord={() => {
                const app = meetingNotice.app;
                setMeetingNotice(null);
                setCaptureMode("meeting");
                setMicOnly(false);
                void toggle({ mode: "meeting", title: `${app} · ${new Date().toLocaleString(document.documentElement.lang || undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}` });
              }}
              onStop={() => {
                setMeetingNotice(null);
                void toggle();
              }}
              onDismiss={() => {
                setMeetingNotice(null);
                void api.dismissMeeting().catch(() => undefined);
              }}
              onCopyConsent={consent}
            />
          ) : null}
          {view !== "live" && (capture.recording || asrBusy || speakersBusy) ? (
            <button type="button" className="live-banner" onClick={() => setView("live")}>
              <span className="state-led" aria-hidden />
              {t("nav.activeTranscript")}
              <Icon name="arrow" size={14} />
            </button>
          ) : null}
          {view === "live" ? (
            <LivePage
              capture={capture}
              sessionId={captureId}
              liveSegments={liveSegments}
              busy={busy}
              error={captureError}
              pending={pending}
              micOnly={micOnly}
              monitor={monitor}
              asrBusy={asrBusy}
              asrQueued={asrQueued}
              speakersBusy={speakersBusy}
              socketLive={socketLive}
              monitorStale={monitorStale}
              loopbackId={loopbackId}
              devices={devices}
              voicesRevision={voicesRevision}
              voiceReady={Boolean(voiceReady)}
              voiceDownloading={voiceDownloading}
              onDownloadVoice={() => void downloadVoice()}
              onMicOnlyChange={setMicOnly}
              onLoopbackChange={setLoopbackId}
              onToggle={() => void toggle()}
              onTitleChange={async (title) => {
                if (!captureId) return;
                const updated = await api.renameSession(captureId, title);
                setSessions((current) => current.map((item) => (item.id === updated.id ? updated : item)));
              }}
              participantIds={participantIds}
              onParticipantIdsChange={setParticipantIds}
              languageLocked={language !== "auto"}
              captureLanguage={language}
              captureMode={captureMode}
              templates={templates}
              templateId={templateId}
              onTemplateChange={setTemplateId}
              notesRevision={notesRevision}
              onOpenMini={() => void openMiniWindow()}
              onCopyConsent={consent}
              tasksRevision={tasksRevision}
              onTasksChanged={() => setTasksRevision((value) => value + 1)}
              onOpenSession={(sessionId) => openSession(sessionId)}
              onConnectCalendar={() => openSettings("meetings")}
              summaryBusySessionId={summaryBusy}
              summaryRevision={summaryRevision}
              memoryRevision={memoryRevision}
              onOpenSettings={() => openSettings("transcription")}
              onRecordEvent={(event) => {
                setCaptureMode("meeting");
                setMicOnly(false);
                void toggle({ mode: "meeting", title: event.title || undefined });
              }}
              engineProvider={asrProvider}
              onCaptureModeChange={(mode) => {
                setCaptureMode(mode);
                if (mode === "dictation") setMicOnly(true);
                if (mode === "lecture" || mode === "meeting") setMicOnly(false);
              }}
              onCaptureLanguageChange={(id) => {
                setLanguage(id);
                void api.saveSettings({ language: id }).catch(() => {
                  toast.push({ tone: "error", title: t("settings.saveFail") });
                });
              }}
              onAsk={openChat}
            />
          ) : null}
          {view === "session" && activeId ? (
            <SessionPage
              sessionId={activeId}
              summaryBusySessionId={summaryBusy}
              summaryRevision={summaryRevision}
              memoryRevision={memoryRevision}
              tasksRevision={tasksRevision}
              onOpenSession={(sessionId) => openSession(sessionId)}
              seekTo={sessionSeek}
              templates={templates}
              notesRevision={notesRevision}
              voicesRevision={voicesRevision}
              voiceReady={Boolean(voiceReady)}
              voiceDownloading={voiceDownloading}
              onDownloadVoice={() => void downloadVoice()}
              onDeleted={() => {
                if (captureId === activeId) setCaptureId(null);
                setActiveId(null);
                setView("live");
                void loadSessions();
              }}
              onRenamed={(title) => {
                if (!activeId) return;
                setSessions((current) => current.map((item) => (item.id === activeId ? { ...item, title } : item)));
              }}
              onTagsChanged={() => void loadSessions()}
              languageLocked={language !== "auto"}
              onAsk={openChat}
            />
          ) : null}
          {view === "library" ? (
            <LibraryPage
              sessions={sessions}
              folders={tags}
              liveSessionId={capture.recording ? capture.session_id : null}
              onOpenSession={(sessionId) => openSession(sessionId)}
              onChanged={loadSessions}
            />
          ) : null}
          {view === "tasks" ? (
            <TasksPage
              revision={tasksRevision}
              onOpenSession={(sessionId) => openSession(sessionId)}
              onChanged={() => setTasksRevision((value) => value + 1)}
            />
          ) : null}
          {view === "chat" ? (
            <ChatPage
              recipes={templates.filter((item) => item.kind === "recipe")}
              focus={chatFocus}
              onFocusConsumed={() => setChatFocus(null)}
              onOpenSession={(sessionId, atMs) => openSession(sessionId, atMs)}
              onOpenSettings={() => openSettings("transcription")}
            />
          ) : null}
          {view === "settings" ? (
            <SettingsPage
              key={settingsTab}
              initialTab={settingsTab}
              engineProvider={asrProvider}
              voiceReady={Boolean(voiceReady)}
              voiceDownloading={voiceDownloading}
              onDownloadVoice={() => void downloadVoice()}
              onTemplatesChanged={() => void loadTemplates()}
              onSaved={(next) => {
                setMicOnly(next.mic_only_default);
                setLanguage(isCaptureLanguage(next.language) ? next.language : "pt");
                applyEngineSettings(next);
                if (isUiLanguage(next.ui_language)) setLocale(next.ui_language);
              }}
            />
          ) : null}
        </div>
      </main>
      <CommandPalette
        open={paletteOpen}
        sessions={sessions}
        recording={capture.recording}
        onClose={() => setPaletteOpen(false)}
        onOpenSession={openSession}
        onToggleCapture={() => void toggle()}
        onOpenChat={() => openChat()}
        onOpenSettings={() => openSettings()}
        onOpenLive={() => setView("live")}
        onOpenTasks={() => setView("tasks")}
      />
    </div>
  );
}

const BOOT_RETRY_MS = 25_000;

/** "Failed to fetch" do WebView: porta fechada, motor ainda subindo ou caído. */
function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError || (err instanceof Error && /failed to fetch|networkerror|load failed/i.test(err.message));
}

async function untilBackendAnswers<T>(call: () => Promise<T>, cancelled: () => boolean): Promise<T> {
  const started = Date.now();
  let delay = 250;
  for (;;) {
    try {
      return await call();
    } catch (err) {
      if (!isNetworkError(err) || cancelled() || Date.now() - started > BOOT_RETRY_MS) throw err;
      await new Promise((resolve) => window.setTimeout(resolve, delay));
      delay = Math.min(delay * 2, 2_000);
    }
  }
}

function NavButton({
  icon,
  label,
  active,
  onClick,
  badge,
}: {
  icon: IconName;
  label: string;
  active: boolean;
  onClick: () => void;
  badge?: string;
}) {
  return (
    <button className={active ? "nav-item is-active" : "nav-item"} aria-current={active ? "page" : undefined} onClick={onClick} type="button" title={label}>
      <Icon name={icon} size={18} />
      <span>{label}</span>
      {badge === "rec" ? <span className="nav-rec" aria-hidden /> : badge ? <span className={/^\d+$/.test(badge) ? "nav-badge is-count" : "nav-badge"}>{badge}</span> : null}
    </button>
  );
}

function groupByDay(items: Session[], t: (key: string) => string): { label: string; items: Session[] }[] {
  const groups: { label: string; items: Session[] }[] = [];
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const day = 86_400_000;
  for (const session of items) {
    const started = new Date(session.started_at);
    const stamp = new Date(started.getFullYear(), started.getMonth(), started.getDate()).getTime();
    const label =
      stamp === startOfToday
        ? t("days.today")
        : stamp === startOfToday - day
          ? t("days.yesterday")
          : started.toLocaleDateString(document.documentElement.lang || undefined, { day: "2-digit", month: "short", year: started.getFullYear() === today.getFullYear() ? undefined : "numeric" });
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(session);
    else groups.push({ label, items: [session] });
  }
  return groups;
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
    channels: isRecord(value.channels)
      ? {
          mic: toChannel(value.channels.mic) ?? { rms: 0, speech: false },
          system: toChannel(value.channels.system),
        }
      : null,
    voice:
      // Uma voz da sessão (cluster) ou uma pessoa conhecida pela impressão vocal (só person_id).
      isRecord(value.voice) && (typeof value.voice.cluster === "string" || typeof value.voice.person_id === "string")
        ? {
            cluster: typeof value.voice.cluster === "string" ? value.voice.cluster : null,
            person_id: typeof value.voice.person_id === "string" ? value.voice.person_id : null,
            name: typeof value.voice.name === "string" ? value.voice.name : null,
            source: typeof value.voice.source === "string" ? value.voice.source : null,
            at_ms: typeof value.voice.at_ms === "number" ? value.voice.at_ms : 0,
          }
        : null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function toChannel(value: unknown): { rms: number; speech: boolean; echo?: number } | null {
  if (!isRecord(value)) return null;
  return {
    rms: typeof value.rms === "number" ? value.rms : 0,
    speech: Boolean(value.speech),
    echo: typeof value.echo === "number" ? value.echo : undefined,
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
