import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import { api, askChat } from "../shared/api/client";
import type {
  ChatCitation,
  ChatDocument,
  ChatFocus,
  ChatImageDraft,
  ChatMessage,
  ChatStyle,
  ChatThread,
  NoteTemplate,
  Session,
  SolveTarget,
} from "../shared/api/types";
import { DOCUMENT_ACCEPT, DocumentTray, hasFiles } from "../features/chat/DocumentTray";
import { ChatTune, readSolveTarget, readStyle } from "../features/chat/ChatTune";
import { ContextBar, MAX_CONTEXT, pickOf, type PickedSession } from "../features/chat/ContextBar";
import { IMAGE_ACCEPT, MAX_IMAGES, isImageFile, prepareImage } from "../features/chat/images";
import { EngineBanner } from "../features/document/EngineBanner";
import { stampToMs } from "../features/summary/NoteEditor";
import { AiThinking } from "../shared/ui/AiThinking";
import { Icon } from "../shared/ui/Icon";
import { Markdown } from "../shared/ui/Markdown";
import { useToast } from "../shared/ui/Toast";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { templateName } from "../shared/lib/templates";
import { bcp47, useI18n, useT } from "../shared/i18n";
import { copyToClipboard, formatClock, withoutTrailingDate } from "../shared/lib/format";
import { saveBlob } from "../shared/lib/saveFile";
import { useFlag } from "../shared/lib/useFlag";
import { Button } from "../shared/ui/primitives";
import { TourButton } from "../features/onboarding/Tour";

const THREAD_SEARCH_MIN = 15;
const DAY = 86_400_000;
const MAX_TASKS = 20;
const MAX_NOTE_CHARS = 4000;

/** Comandos com "/" e materiais de estudo: ids fixos, rótulos e perguntas traduzidos. */
const COMMANDS = ["summary", "tasks", "decisions", "glossary", "flashcards", "exercises", "onepage", "exam"] as const;
type CommandId = (typeof COMMANDS)[number];
/** Item do menu "/": comando fixo ou pergunta salva. */
type SlashItem = { kind: "cmd"; id: CommandId } | { kind: "recipe"; item: NoteTemplate };
const SUGGESTIONS = ["suggest_1", "suggest_2", "suggest_3"] as const;
const DOC_SUGGESTIONS = ["summary", "numbers", "compare"] as const;

/** Turno que não terminou: o motivo e o que reenviar. */
interface TurnFailure {
  reason: string;
  question: string;
  images: ChatImageDraft[];
}

interface ChatPageProps {
  recipes?: NoteTemplate[];
  focus: ChatFocus | null;
  onOpenSession: (sessionId: string, atMs?: number) => void;
  onFocusConsumed: () => void;
  onOpenSettings?: () => void;
}

export function ChatPage({ recipes = [], focus, onOpenSession, onFocusConsumed, onOpenSettings }: ChatPageProps) {
  const { locale, t } = useI18n();
  const toast = useToast();
  const confirm = useConfirm();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [allSessions, setAllSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<PickedSession[]>([]);
  const [failures, setFailures] = useState<Record<string, TurnFailure>>({});
  const [interrupted, setInterrupted] = useState<Set<string>>(() => new Set());
  const [threadQuery, setThreadQuery] = useState("");
  const [threadMenu, setThreadMenu] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; draft: string } | null>(null);
  // Esc cancela antes do blur: o blur lê daqui e não grava.
  const renameRef = useRef(renaming);
  renameRef.current = renaming;
  const abortRef = useRef<AbortController | null>(null);
  const pinRef = useRef<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeThread, setActiveThread] = useState<ChatThread | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFocus, setPendingFocus] = useState<ChatFocus | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [stickBottom, setStickBottom] = useState(true);
  const [docs, setDocs] = useState<ChatDocument[]>([]);
  const [images, setImages] = useState<ChatImageDraft[]>([]);
  const [localPreviews, setLocalPreviews] = useState<Record<string, string[]>>({});
  const [style, setStyle] = useState<ChatStyle>(readStyle);
  const [solveTarget, setSolveTarget] = useState<SolveTarget>(readSolveTarget);
  const [grounded, setGrounded] = useState(false);
  const [attachOpen, setAttachOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [link, setLink] = useState("");
  const attachRef = useRef<HTMLDivElement>(null);
  const linkInput = useRef<HTMLInputElement>(null);
  const [railCollapsed, toggleRail] = useFlag("droidnote.chatRailCollapsed");
  const [uploading, setUploading] = useState<string[]>([]);
  const [dropping, setDropping] = useState(false);
  const [commandIndex, setCommandIndex] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  const addFiles = async (files: FileList | File[]) => {
    for (const file of [...files]) {
      if (isImageFile(file)) {
        if (images.length >= MAX_IMAGES) {
          setError(t("chat.imageLimit", { count: MAX_IMAGES }));
          continue;
        }
        try {
          const prepared = await prepareImage(file);
          setImages((current) => (current.length >= MAX_IMAGES ? current : [...current, prepared]));
        } catch {
          setError(`${file.name}: ${t("chat.docErr_unreadable")}`);
        }
        continue;
      }
      setUploading((current) => [...current, file.name]);
      try {
        const doc = await api.uploadDocument(file, activeId);
        setDocs((current) => [...current, doc]);
      } catch (err) {
        const code = err instanceof Error ? err.message : "";
        const key = `chat.docErr_${code}`;
        const message = t(key);
        setError(`${file.name}: ${message === key ? t("chat.docErr_unreadable") : message}`);
      } finally {
        setUploading((current) => {
          const index = current.indexOf(file.name);
          return index < 0 ? current : [...current.slice(0, index), ...current.slice(index + 1)];
        });
      }
    }
    input.current?.focus();
  };

  const removeDoc = async (doc: ChatDocument) => {
    setDocs((current) => current.filter((item) => item.id !== doc.id));
    try {
      await api.deleteDocument(doc.id);
    } catch {
      /* já saiu da lista; some de vez quando o chat for apagado */
    }
  };

  const loadThreads = async () => {
    setThreads(await api.chats());
  };

  const loadSessions = () =>
    api
      .sessions()
      .then((items) => {
        setAllSessions(items);
        return items;
      })
      .catch(() => [] as Session[]);

  useEffect(() => {
    void loadThreads();
    void loadSessions();
  }, []);

  useEffect(() => {
    if (!focus) return;
    // A conversa em foco vira o único chip; o trecho, quando há, fica como item extra.
    setPendingFocus(focus.excerpt ? focus : null);
    setSelected(
      focus.sessionId ? [{ sessionId: focus.sessionId, title: focus.sessionTitle ?? "", date: "" }] : [],
    );
    setActiveId(null);
    setActiveThread(null);
    setMessages([]);
    setDocs([]);
    setImages([]);
    if (focus.prompt) setDraft(focus.prompt);
    onFocusConsumed();
    window.setTimeout(() => input.current?.focus(), 40);
  }, [focus, onFocusConsumed]);

  // Data do chip vinda de fora (Conversa aberta) chega depois que a lista carrega.
  useEffect(() => {
    if (!allSessions.length) return;
    setSelected((current) =>
      current.some((item) => !item.date)
        ? current.map((item) => {
            const found = allSessions.find((session) => session.id === item.sessionId);
            return item.date || !found ? item : pickOf(found);
          })
        : current,
    );
  }, [allSessions]);

  useEffect(() => {
    const node = scroller.current;
    if (!node) return;
    // Ao enviar, a pergunta sobe para o topo; a resposta corre abaixo dela.
    if (pinRef.current) {
      const question = node.querySelector<HTMLElement>(`[data-msg="${pinRef.current}"]`);
      pinRef.current = null;
      if (question) {
        node.scrollTop = question.offsetTop - node.offsetTop - 16;
        return;
      }
    }
    if (stickBottom) node.scrollTop = node.scrollHeight;
  }, [messages, busy, stickBottom]);

  useEffect(() => {
    const node = input.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 160)}px`;
  }, [draft]);

  useEffect(() => {
    try {
      window.localStorage.setItem("droidnote.chatStyle", style);
      window.localStorage.setItem("droidnote.chatSolveTarget", solveTarget);
    } catch {
      /* só conveniência */
    }
  }, [style, solveTarget]);

  useEffect(() => {
    if (!attachOpen) return undefined;
    const close = (event: MouseEvent) => {
      if (attachRef.current && !attachRef.current.contains(event.target as Node)) setAttachOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [attachOpen]);

  useEffect(() => {
    if (linkOpen) window.setTimeout(() => linkInput.current?.focus(), 30);
  }, [linkOpen]);

  /** Página ou vídeo do YouTube como fonte: o backend lê o texto (ou as legendas) e guarda como documento. */
  const addLink = async (raw: string) => {
    const url = raw.trim();
    if (!url) return;
    setLinkOpen(false);
    setLink("");
    setUploading((current) => [...current, url]);
    try {
      const doc = await api.attachUrl(url, activeId);
      setDocs((current) => [...current, doc]);
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      const key = `chat.docErr_${code}`;
      const message = t(key);
      setError(`${url}: ${message === key ? t("chat.docErr_url_unreachable") : message}`);
    } finally {
      setUploading((current) => current.filter((item) => item !== url));
    }
    input.current?.focus();
  };

  const openThread = async (id: string) => {
    const detail = await api.chat(id);
    setActiveId(detail.chat.id);
    setActiveThread(detail.chat);
    setMessages(detail.messages);
    setPendingFocus(null);
    setFailures({});
    // Os chips da última pergunta voltam todos. Conversa apagada some da lista.
    const sessions = allSessions.length ? allSessions : await loadSessions();
    const byId = new Map(sessions.map((session) => [session.id, session]));
    setSelected(
      (detail.chat.scope_session_ids ?? []).flatMap((sid) => {
        const found = byId.get(sid);
        return found ? [pickOf(found)] : [];
      }),
    );
    setImages([]);
    setError(null);
    setStickBottom(true);
    setDocs(await api.documents(detail.chat.id).catch(() => []));
  };

  const startNew = () => {
    setActiveId(null);
    setActiveThread(null);
    setMessages([]);
    setDocs([]);
    setImages([]);
    setPendingFocus(null);
    setSelected([]);
    setFailures({});
    setError(null);
    input.current?.focus();
    void loadSessions();
  };

  const focusSessionId = pendingFocus?.sessionId ?? (selected.length === 1 ? selected[0]!.sessionId : null);

  const send = async (text: string, attached: ChatImageDraft[] = images, retry = false) => {
    const cleaned = text.trim();
    if (!cleaned || busy) return;
    setDraft("");
    setImages([]);
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const optimistic: ChatMessage = {
      id: `local-${Date.now()}`,
      chat_id: activeId ?? "pending",
      role: "user",
      content: cleaned,
      created_at: new Date().toISOString(),
      citations: [],
      images: attached.map((item, index) => ({ id: `local-${index}`, name: item.name, mime: item.mime, size: 0 })),
    };
    if (attached.length) setLocalPreviews((current) => ({ ...current, [optimistic.id]: attached.map((item) => item.preview) }));
    const streaming: ChatMessage = {
      id: `stream-${Date.now()}`,
      chat_id: activeId ?? "pending",
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      citations: [],
    };
    pinRef.current = optimistic.id;
    setMessages((current) => [...current, optimistic, streaming]);
    const ids = selected.map((item) => item.sessionId).slice(0, MAX_CONTEXT);
    let streamedChatId: string | null = null;
    try {
      const result = await askChat(
        {
          message: cleaned,
          chat_id: activeId,
          session_id: pendingFocus?.sessionId ?? ids[0] ?? null,
          segment_ids: pendingFocus?.segmentId ? [pendingFocus.segmentId] : [],
          document_ids: docs.map((item) => item.id),
          ui_language: locale,
          style,
          grounded,
          solve_target: solveTarget,
          // Chips = o que a resposta usa. Sem chips, null: busca em todas.
          scope: ids.length ? { session_ids: ids } : null,
          images: attached.map((item) => ({ name: item.name, mime: item.mime, data: item.data })),
          retry,
        },
        (token) => {
          setMessages((current) =>
            current.map((item) =>
              item.id === streaming.id ? { ...item, content: item.content + token } : item,
            ),
          );
        },
        controller.signal,
        (chatId) => {
          streamedChatId = chatId;
        },
      );
      setActiveId(result.chat.id);
      setActiveThread(result.chat);
      setPendingFocus(null);
      const detail = await api.chat(result.chat.id);
      setMessages(detail.messages);
      setDocs(await api.documents(result.chat.id).catch(() => docs));
      await loadThreads();
    } catch (err) {
      // O texto parcial fica na tela. Parar marca "interrompida"; erro vira cartão no turno.
      if (controller.signal.aborted) {
        setInterrupted((current) => new Set(current).add(streaming.id));
      } else {
        const reason =
          err instanceof TypeError
            ? t("chat.errOffline")
            : err instanceof Error && err.message
              ? err.message
              : t("chat.fail");
        setFailures((current) => ({ ...current, [streaming.id]: { reason, question: cleaned, images: attached } }));
      }
      // Chat novo: adota pelo id do primeiro evento. Parado antes de gravar a pergunta, o id dá 404 e fica de fora.
      if (!activeId && streamedChatId) {
        const adopted = await api.chat(streamedChatId).catch(() => null);
        if (adopted) {
          setActiveId(adopted.chat.id);
          setActiveThread(adopted.chat);
        }
      }
      const list = await api.chats().catch(() => null);
      if (list) setThreads(list);
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  };

  const stop = () => abortRef.current?.abort();

  const retry = (failedId: string) => {
    const failure = failures[failedId];
    if (!failure || busy) return;
    setFailures(({ [failedId]: _drop, ...rest }) => rest);
    // Tira a pergunta e a resposta que falharam; o reenvio monta o turno de novo.
    setMessages((current) => {
      const index = current.findIndex((item) => item.id === failedId);
      return index < 0 ? current : current.filter((_, i) => i !== index && i !== index - 1);
    });
    void send(failure.question, failure.images, true);
  };

  const lastQuestion = [...messages].reverse().find((item) => item.role === "user")?.content ?? "";
  const lastAnswerId = [...messages].reverse().find((item) => item.role === "assistant")?.id ?? null;

  const adoptSources = (citations: ChatCitation[]) => {
    const ids = [
      ...new Set(citations.filter((item) => !item.document_id && item.session_id).map((item) => item.session_id)),
    ];
    setSelected(
      ids.slice(0, MAX_CONTEXT).map((id) => {
        const found = allSessions.find((session) => session.id === id);
        return found
          ? pickOf(found)
          : { sessionId: id, title: citations.find((item) => item.session_id === id)?.session_title ?? "", date: "" };
      }),
    );
    input.current?.focus();
  };

  const commitRename = async (thread: ChatThread) => {
    const title = renameRef.current?.draft.trim().slice(0, 120) ?? "";
    renameRef.current = null;
    setRenaming(null);
    if (!title || title === thread.title) return;
    try {
      const saved = await api.renameChat(thread.id, title);
      setThreads((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      if (saved.id === activeId) setActiveThread(saved);
      toast.push({ tone: "success", title: t("chat.threadRenamed") });
    } catch (err) {
      toast.push({
        tone: "error",
        title: t("chat.threadRenameFail"),
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const removeThread = async (thread: ChatThread) => {
    setThreadMenu(null);
    const ok = await confirm({
      title: t("chat.threadDeleteTitle", { title: thread.title }),
      description: t("chat.threadDeleteBody"),
      confirmLabel: t("chat.threadDelete"),
      tone: "danger",
    });
    if (!ok) return;
    try {
      await api.deleteChat(thread.id);
      if (thread.id === activeId) startNew();
      await loadThreads();
    } catch (err) {
      toast.push({
        tone: "error",
        title: t("chat.threadDeleteFail"),
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const copyAnswer = async (message: ChatMessage) => {
    const ok = await copyToClipboard(message.content);
    if (ok) {
      setCopiedId(message.id);
      window.setTimeout(() => setCopiedId((current) => (current === message.id ? null : current)), 1600);
    }
  };

  /** Modo Resolver: copia o bloco ```prompt; sem o bloco, a resposta inteira serve de prompt. */
  const copyPrompt = async (message: ChatMessage) => {
    const ok = await copyToClipboard(promptOf(message.content));
    if (ok) {
      setCopiedId(`prompt-${message.id}`);
      window.setTimeout(() => setCopiedId((current) => (current === `prompt-${message.id}` ? null : current)), 1600);
    }
  };

  /** Sessão onde a resposta pode virar nota: a em foco, a do chat ou a única citada. */
  const noteTarget = (message: ChatMessage): string | null => focusSessionId ?? citedSession(message.citations);

  const saveAsNote = async (message: ChatMessage) => {
    const sessionId = noteTarget(message);
    if (!sessionId) return;
    try {
      await api.addNote(sessionId, message.content.slice(0, MAX_NOTE_CHARS));
      toast.push({ tone: "success", title: t("chat.savedNote") });
    } catch (err) {
      toast.push({ tone: "error", title: t("chat.saveFail"), description: err instanceof Error ? err.message : undefined });
    }
  };

  const sendTasks = async (message: ChatMessage) => {
    const items = listItems(message.content);
    if (!items.length) {
      toast.push({ tone: "info", title: t("chat.saveTasksNone") });
      return;
    }
    const sessionId = noteTarget(message);
    try {
      for (const text of items) await api.createTask({ text, session_id: sessionId });
      toast.push({ tone: "success", title: t("chat.savedTasks", { count: items.length }) });
    } catch (err) {
      toast.push({ tone: "error", title: t("chat.saveFail"), description: err instanceof Error ? err.message : undefined });
    }
  };

  const exportAnswer = async (message: ChatMessage, format: "pdf" | "docx" | "markdown") => {
    if (!activeId) return;
    const ext = format === "markdown" ? "md" : format;
    const question = [...messages].reverse().find((item) => item.role === "user" && item.created_at <= message.created_at);
    const title = (question?.content.split("\n")[0] ?? activeThread?.title ?? "resposta").slice(0, 60);
    try {
      const blob = await api.exportChatMessage(activeId, message.id, format);
      const result = await saveBlob(blob, `${title}.${ext}`, [{ name: ext.toUpperCase(), extensions: [ext] }]);
      if (result.status === "error") toast.push({ tone: "error", title: t("chat.saveFail"), description: result.message });
      else if (result.status === "saved") toast.push({ tone: "success", title: t("session.fileSaved"), description: `${title}.${ext}` });
    } catch (err) {
      toast.push({ tone: "error", title: t("chat.saveFail"), description: err instanceof Error ? err.message : undefined });
    }
  };

  const empty = messages.length === 0;

  useEffect(() => {
    if (!threadMenu) return undefined;
    const close = (event: MouseEvent) => {
      if (!(event.target as Element).closest?.(".chat-thread-more-wrap")) setThreadMenu(null);
    };
    const onKey = (event: globalThis.KeyboardEvent) => event.key === "Escape" && setThreadMenu(null);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [threadMenu]);

  const commandLabel = (id: CommandId) => t(`chat.cmd_${id}`);
  const runCommand = (id: CommandId) => {
    setDraft("");
    void send(t(`chat.cmdAsk_${id}`));
  };
  const runSlash = (entry: SlashItem) => {
    if (entry.kind === "cmd") {
      runCommand(entry.id);
      return;
    }
    setDraft(entry.item.body);
    input.current?.focus();
  };
  // Menu "/": comandos (estudo incluído) e perguntas salvas. Abre quando a pergunta começa com "/" numa linha só.
  const slashQuery = draft.startsWith("/") && !draft.includes("\n") ? draft.slice(1).toLowerCase() : null;
  const commandMatches = useMemo<SlashItem[]>(
    () =>
      slashQuery === null
        ? []
        : [
            ...COMMANDS.filter(
              (id) => commandLabel(id).slice(1).toLowerCase().startsWith(slashQuery) || id.startsWith(slashQuery),
            ).map((id) => ({ kind: "cmd" as const, id })),
            ...recipes
              .filter((item) => templateName(item).toLowerCase().includes(slashQuery))
              .map((item) => ({ kind: "recipe" as const, item })),
          ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [slashQuery, locale, recipes],
  );
  useEffect(() => setCommandIndex(0), [slashQuery]);

  const placeholder = docs.length
    ? t("chat.placeholderDocs")
    : pendingFocus?.excerpt
      ? t("chat.placeholderFocus")
      : t("chat.placeholder");

  const lang = bcp47(locale);
  const needle = threadQuery.trim().toLowerCase();
  const shownThreads = needle ? threads.filter((thread) => thread.title.toLowerCase().includes(needle)) : threads;
  const threadGroups = groupThreads(shownThreads);

  const fill = (text: string) => {
    setDraft(text);
    input.current?.focus();
  };

  return (
    <div className={railCollapsed ? "chat-page is-rail-collapsed" : "chat-page"}>
      <aside data-tour="chat-rail" className="chat-rail" aria-label={t("chat.threads")}>
        <div className="chat-rail-head">
          <button
            type="button"
            className="rail-toggle"
            onClick={toggleRail}
            title={railCollapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
            aria-label={railCollapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar")}
            aria-expanded={!railCollapsed}
          >
            <Icon name="rail" size={15} />
          </button>
          {/* O título só para leitor de tela: os grupos Hoje/Ontem já dizem que é o histórico e o espaço vai para os botões. */}
          <strong className="sr-only">{t("chat.threads")}</strong>
          <Button data-tour="chat-new" size="sm" variant="quiet" className="chat-new" onClick={startNew}>
            <PlusGlyph />
            <span>{t("chat.new")}</span>
          </Button>
          <TourButton chapter="chat" />
        </div>
        {threads.length > THREAD_SEARCH_MIN ? (
          <input
            type="search"
            className="chat-thread-search"
            value={threadQuery}
            placeholder={t("chat.threadSearch")}
            aria-label={t("chat.threadSearch")}
            onChange={(event) => setThreadQuery(event.target.value)}
          />
        ) : null}
        <div className="chat-thread-list">
          {threads.length === 0 ? (
            <p className="chat-rail-empty">{t("chat.emptyThreads")}</p>
          ) : (
            threadGroups.map((group) => (
              <section key={group.key} className="chat-thread-group" aria-label={t(`chat.group_${group.key}`)}>
                <h2>{t(`chat.group_${group.key}`)}</h2>
                {group.items.map((thread) => (
                  <div key={thread.id} className={thread.id === activeId ? "chat-thread-row is-active" : "chat-thread-row"}>
                    {renaming?.id === thread.id ? (
                      <input
                        className="chat-thread-rename"
                        value={renaming.draft}
                        maxLength={120}
                        autoFocus
                        aria-label={t("chat.threadRenameAria")}
                        onChange={(event) => setRenaming({ id: thread.id, draft: event.target.value })}
                        onFocus={(event) => event.currentTarget.select()}
                        onBlur={() => void commitRename(thread)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") event.currentTarget.blur();
                          if (event.key === "Escape") {
                            event.stopPropagation();
                            renameRef.current = null;
                            setRenaming(null);
                          }
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        className="chat-thread"
                        aria-current={thread.id === activeId ? "true" : undefined}
                        onClick={() => void openThread(thread.id)}
                      >
                        <span className="chat-thread-title">{thread.title}</span>
                        <small>{relativeTime(thread.updated_at, lang)}</small>
                      </button>
                    )}
                    <div className="chat-thread-more-wrap">
                      <button
                        type="button"
                        className="chat-thread-more"
                        aria-label={t("chat.threadOptions", { title: thread.title })}
                        aria-haspopup="menu"
                        aria-expanded={threadMenu === thread.id}
                        onClick={() => setThreadMenu((current) => (current === thread.id ? null : thread.id))}
                      >
                        <Icon name="more" size={15} />
                      </button>
                      {threadMenu === thread.id ? (
                        <div className="chat-save-menu chat-thread-menu" role="menu">
                          <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                              setThreadMenu(null);
                              setRenaming({ id: thread.id, draft: thread.title });
                            }}
                          >
                            {t("chat.threadRename")}
                          </button>
                          <button type="button" role="menuitem" className="is-danger" onClick={() => void removeThread(thread)}>
                            {t("chat.threadDelete")}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </section>
            ))
          )}
        </div>
      </aside>
      <section
        className={dropping ? "chat-main is-dropping" : "chat-main"}
        onDragOver={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          setDropping(true);
        }}
        onDragLeave={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setDropping(false);
        }}
        onDrop={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          setDropping(false);
          void addFiles(event.dataTransfer.files);
        }}
      >
        {dropping ? (
          <div className="chat-drop" aria-hidden>
            <Icon name="export" size={22} />
            <strong>{t("chat.dropTitle")}</strong>
            <small>{t("chat.docTypes")}</small>
          </div>
        ) : null}
        {empty ? (
          <div className="chat-empty">
            <h1>{t("chat.askAnything")}</h1>
            <div className="chips">
              {docs.length
                ? DOC_SUGGESTIONS.map((id) => (
                    <button key={id} type="button" className="chip" onClick={() => fill(t(`chat.docAsk_${id}`))}>
                      {t(`chat.docAskLabel_${id}`)}
                    </button>
                  ))
                : SUGGESTIONS.map((id) => (
                    <button key={id} type="button" className="chip" onClick={() => fill(t(`chat.${id}`))}>
                      {t(`chat.${id}`)}
                    </button>
                  ))}
            </div>
          </div>
        ) : (
          <div
            className="chat-log"
            ref={scroller}
            onScroll={(event) => {
              const node = event.currentTarget;
              const remaining = node.scrollHeight - node.scrollTop - node.clientHeight;
              setStickBottom(remaining < 80);
            }}
          >
            {messages.map((item) => {
              const failure = failures[item.id];
              return (
                <article
                  key={item.id}
                  data-msg={item.id}
                  className={item.role === "user" ? "chat-turn is-user" : "chat-turn"}
                  aria-live={item.role === "assistant" && busy && item.id.startsWith("stream-") ? "polite" : undefined}
                >
                  {!item.content && busy && item.role === "assistant" && !failure ? (
                    <AiThinking
                      compact
                      lines={3}
                      steps={docs.length ? [t("ai.readDocs"), t("ai.searchMemory"), t("ai.answer")] : [t("ai.searchMemory"), t("ai.answer")]}
                    />
                  ) : item.role === "assistant" ? (
                    item.content ? (
                      <Markdown
                        text={item.content}
                        renderStamp={stampRenderer(item.citations, onOpenSession, t("chat.stampNoSource"))}
                        renderCite={citeRenderer(item.citations, onOpenSession, t)}
                        chartTableLabel={t("chat.chartTable")}
                        promptLabels={{ title: t("chat.promptReady"), copy: t("chat.promptCopy"), copied: t("common.copied") }}
                      />
                    ) : null
                  ) : (
                    <>
                      {item.images?.length ? (
                        <div className="chat-turn-images">
                          {item.images.map((image, index) => (
                            <ChatImageThumb key={image.id} id={image.id} name={image.name} preview={localPreviews[item.id]?.[index]} />
                          ))}
                        </div>
                      ) : null}
                      <p>{item.content}</p>
                    </>
                  )}
                  {interrupted.has(item.id) || item.interrupted ? (
                    <p className="chat-turn-note">
                      <span>{t("chat.interrupted")}</span>
                      {item.id === lastAnswerId && !busy && lastQuestion ? (
                        <span className="chat-turn-actions">
                          <button type="button" onClick={() => void send(t("chat.continueAsk"), [])}>
                            {t("chat.continue")}
                          </button>
                          {item.id.startsWith("stream-") ? (
                            <button type="button" onClick={() => void send(lastQuestion, [])}>
                              {t("chat.regenerate")}
                            </button>
                          ) : null}
                        </span>
                      ) : null}
                    </p>
                  ) : null}
                  {failure ? (
                    <div className="chat-turn-error" role="alert">
                      <strong>{t("chat.fail")}</strong>
                      <p>{failure.reason}</p>
                      <div>
                        <Button size="sm" variant="primary" disabled={busy} onClick={() => retry(item.id)}>
                          {t("common.retry")}
                        </Button>
                        {onOpenSettings ? (
                          <Button size="sm" variant="quiet" onClick={onOpenSettings}>
                            {t("chat.openSettings")}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  {item.role === "assistant" && item.content && !item.id.startsWith("stream-") ? (
                    <AnswerActions
                      copied={copiedId === item.id}
                      promptCopied={copiedId === `prompt-${item.id}`}
                      canNote={Boolean(noteTarget(item))}
                      canExport={Boolean(activeId)}
                      onCopy={() => void copyAnswer(item)}
                      onCopyPrompt={item.style === "solve" ? () => void copyPrompt(item) : undefined}
                      onNote={() => void saveAsNote(item)}
                      onTasks={() => void sendTasks(item)}
                      onExport={(format) => void exportAnswer(item, format)}
                      onRegenerate={item.id === lastAnswerId && !busy && lastQuestion ? () => void send(lastQuestion, []) : undefined}
                    />
                  ) : null}
                  {item.citations.length > 0 ? (
                    <ChatSources
                      citations={item.citations}
                      content={item.content}
                      onOpenSession={onOpenSession}
                      onUse={
                        busy || item.id !== lastAnswerId || sameSessions(item.citations, selected)
                          ? undefined
                          : () => adoptSources(item.citations)
                      }
                    />
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
        {busy && !stickBottom && !empty ? (
          <button type="button" className="chat-jump" onClick={() => setStickBottom(true)}>
            <Icon name="expand" size={14} />
            {t("chat.newAnswer")}
          </button>
        ) : null}
        {error ? <p className="chat-error">{error}</p> : null}
        <div className="chat-engine">
          <EngineBanner revision={messages.length} onOpenSettings={onOpenSettings} />
        </div>
        <DocumentTray
          documents={docs}
          uploading={uploading}
          images={images}
          disabled={busy}
          onRemove={(doc) => void removeDoc(doc)}
          onRemoveImage={(index) => setImages((current) => current.filter((_, i) => i !== index))}
        />
        <div className="chat-composer-wrap">
          <ContextBar
            sessions={allSessions}
            selected={selected}
            excerpt={pendingFocus?.excerpt ? { title: pendingFocus.sessionTitle, text: pendingFocus.excerpt } : null}
            disabled={busy}
            onChange={setSelected}
            onClearExcerpt={() => setPendingFocus(null)}
          />
          {linkOpen ? (
            <form
              className="chat-link-row"
              onSubmit={(event) => {
                event.preventDefault();
                void addLink(link);
              }}
            >
              <Icon name="link" size={14} />
              <input
                ref={linkInput}
                type="url"
                value={link}
                placeholder={t("chat.linkPlaceholder")}
                onChange={(event) => setLink(event.target.value)}
                onKeyDown={(event) => event.key === "Escape" && setLinkOpen(false)}
              />
              <button type="submit" disabled={!link.trim()}>
                {t("chat.linkAdd")}
              </button>
              <button type="button" className="is-quiet" onClick={() => setLinkOpen(false)} aria-label={t("common.cancel")}>
                <Icon name="close" size={13} />
              </button>
            </form>
          ) : null}
          {commandMatches.length ? (
            <ul className="chat-commands" role="listbox" aria-label={t("chat.commands")}>
              {commandMatches.map((entry, index) => (
                <li key={entry.kind === "cmd" ? entry.id : `recipe-${entry.item.id}`}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === commandIndex}
                    className={index === commandIndex ? "is-active" : ""}
                    onMouseEnter={() => setCommandIndex(index)}
                    onClick={() => runSlash(entry)}
                  >
                    {entry.kind === "cmd" ? (
                      <>
                        <strong>{commandLabel(entry.id)}</strong>
                        <span>{t(`chat.cmdHint_${entry.id}`)}</span>
                      </>
                    ) : (
                      <>
                        <strong>{templateName(entry.item)}</strong>
                        <span>{entry.item.body.slice(0, 90)}</span>
                      </>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <form
            data-tour="chat-study"
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              if (commandMatches.length) runSlash(commandMatches[commandIndex] ?? commandMatches[0]!);
              else void send(draft);
            }}
          >
            <input
              ref={picker}
              type="file"
              accept={`${DOCUMENT_ACCEPT},${IMAGE_ACCEPT}`}
              multiple
              hidden
              onChange={(event) => {
                if (event.target.files?.length) void addFiles(event.target.files);
                event.target.value = "";
              }}
            />
            <div data-tour="chat-attach" className="chat-attach-wrap" ref={attachRef}>
              <button
                type="button"
                className="chat-attach"
                disabled={busy}
                aria-label={t("chat.attach")}
                aria-haspopup="menu"
                aria-expanded={attachOpen}
                title={`${t("chat.attach")} (${t("chat.docTypes")})`}
                onClick={() => setAttachOpen((value) => !value)}
              >
                <Icon name="attach" size={17} />
              </button>
              {attachOpen ? (
                <div className="chat-attach-menu" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setAttachOpen(false);
                      picker.current?.click();
                    }}
                  >
                    <Icon name="attach" size={14} />
                    <span>
                      {t("chat.attachFile")}
                      <small>{t("chat.docTypes")}</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setAttachOpen(false);
                      setLinkOpen(true);
                    }}
                  >
                    <Icon name="link" size={14} />
                    <span>
                      {t("chat.attachLink")}
                      <small>{t("chat.attachLinkHint")}</small>
                    </span>
                  </button>
                </div>
              ) : null}
            </div>
            <textarea
              ref={input}
              value={draft}
              rows={1}
              placeholder={placeholder}
              aria-label={t("chat.askAnything")}
              onChange={(event) => setDraft(event.target.value)}
              onPaste={(event) => {
                const files = [...event.clipboardData.files].filter(isImageFile);
                if (files.length) {
                  event.preventDefault();
                  void addFiles(files);
                  return;
                }
                // Link colado sozinho no campo vazio vira fonte, não pergunta.
                const pasted = event.clipboardData.getData("text").trim();
                if (!draft.trim() && /^https?:\/\/\S+$/i.test(pasted)) {
                  event.preventDefault();
                  void addLink(pasted);
                }
              }}
              onKeyDown={(event) => {
                if (commandMatches.length) {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setCommandIndex((value) => (value + 1) % commandMatches.length);
                    return;
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setCommandIndex((value) => (value - 1 + commandMatches.length) % commandMatches.length);
                    return;
                  }
                  if (event.key === "Escape") {
                    setDraft("");
                    return;
                  }
                }
                // Seta para cima no campo vazio traz a última pergunta para editar.
                if (event.key === "ArrowUp" && !draft && lastQuestion) {
                  event.preventDefault();
                  setDraft(lastQuestion);
                  return;
                }
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (commandMatches.length) runSlash(commandMatches[commandIndex] ?? commandMatches[0]!);
                  else void send(draft);
                }
              }}
            />
            <ChatTune
              style={style}
              grounded={grounded}
              solveTarget={solveTarget}
              disabled={busy}
              onStyle={setStyle}
              onGrounded={setGrounded}
              onSolveTarget={setSolveTarget}
            />
            {busy ? (
              <Button variant="primary" className="chat-stop" onClick={stop} aria-label={t("chat.stop")} title={t("chat.stop")}>
                <StopGlyph />
              </Button>
            ) : (
              <Button type="submit" variant="primary" disabled={!draft.trim()} aria-label={t("chat.send")} title={t("chat.send")}>
                <SendGlyph />
              </Button>
            )}
          </form>
        </div>
      </section>
    </div>
  );
}

const GROUPS = ["today", "yesterday", "week", "older"] as const;
type GroupKey = (typeof GROUPS)[number];

function dayGroup(iso: string): GroupKey {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const at = new Date(iso).getTime();
  return at >= today ? "today" : at >= today - DAY ? "yesterday" : at >= today - 6 * DAY ? "week" : "older";
}

/** Histórico em grupos: hoje, ontem, últimos 7 dias, antes. */
function groupThreads(threads: ChatThread[]): { key: GroupKey; items: ChatThread[] }[] {
  const groups: Record<GroupKey, ChatThread[]> = { today: [], yesterday: [], week: [], older: [] };
  for (const thread of threads) groups[dayGroup(thread.updated_at)].push(thread);
  return GROUPS.filter((key) => groups[key].length).map((key) => ({ key, items: groups[key] }));
}

/** Hoje e ontem: a hora. Na semana: o dia por extenso. Antes: dia e mês por extenso. */
function relativeTime(iso: string, lang: string): string {
  const date = new Date(iso);
  const group = dayGroup(iso);
  if (group === "today" || group === "yesterday") return date.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  if (group === "week") return date.toLocaleDateString(lang, { weekday: "long" });
  return date.toLocaleDateString(lang, { day: "numeric", month: "long" });
}

/** Copiar, "Salvar" (nota da conversa, tarefas, PDF, Word, Markdown. */
function AnswerActions({
  copied,
  promptCopied = false,
  canNote,
  canExport,
  onCopy,
  onCopyPrompt,
  onNote,
  onTasks,
  onExport,
  onRegenerate,
}: {
  copied: boolean;
  promptCopied?: boolean;
  canNote: boolean;
  canExport: boolean;
  onCopy: () => void;
  onCopyPrompt?: () => void;
  onNote: () => void;
  onTasks: () => void;
  onExport: (format: "pdf" | "docx" | "markdown") => void;
  onRegenerate?: () => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  const pick = (action: () => void) => {
    setOpen(false);
    action();
  };
  return (
    <div className="chat-turn-actions" ref={ref}>
      {onCopyPrompt ? (
        <button type="button" className="is-accent" onClick={onCopyPrompt}>
          {promptCopied ? t("common.copied") : t("chat.promptCopy")}
        </button>
      ) : null}
      <button type="button" onClick={onCopy}>
        {copied ? t("common.copied") : t("chat.copyAnswer")}
      </button>
      {canExport ? (
        <>
          <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
            {t("chat.save")}
            <Icon name="expand" size={12} />
          </button>
          {open ? (
            <div className="chat-save-menu" role="menu">
              {canNote ? (
                <button type="button" role="menuitem" onClick={() => pick(onNote)}>
                  {t("chat.saveNote")}
                </button>
              ) : null}
              <button type="button" role="menuitem" onClick={() => pick(onTasks)}>
                {t("chat.saveTasks")}
              </button>
              <hr />
              <button type="button" role="menuitem" onClick={() => pick(() => onExport("pdf"))}>
                PDF
              </button>
              <button type="button" role="menuitem" onClick={() => pick(() => onExport("docx"))}>
                Word
              </button>
              <button type="button" role="menuitem" onClick={() => pick(() => onExport("markdown"))}>
                Markdown
              </button>
            </div>
          ) : null}
        </>
      ) : null}
      {onRegenerate ? (
        <button type="button" onClick={onRegenerate}>
          {t("chat.regenerate")}
        </button>
      ) : null}
    </div>
  );
}

/** Miniatura da imagem enviada com a pergunta (busca com o token; `preview` é o rascunho local). */
function ChatImageThumb({ id, name, preview }: { id: string; name: string; preview?: string }) {
  const [url, setUrl] = useState<string | null>(preview ?? null);
  useEffect(() => {
    if (preview || id.startsWith("local-")) return undefined;
    let alive = true;
    let object: string | null = null;
    void api
      .chatImage(id)
      .then((blob) => {
        if (!alive) return;
        object = URL.createObjectURL(blob);
        setUrl(object);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (object) URL.revokeObjectURL(object);
    };
  }, [id, preview]);
  if (!url) return <span className="chat-turn-image is-empty" title={name} />;
  return <img className="chat-turn-image" src={url} alt={name} title={name} />;
}

function ChatSources({
  citations,
  content,
  onOpenSession,
  onUse,
}: {
  citations: ChatCitation[];
  content: string;
  onOpenSession: (sessionId: string, atMs?: number) => void;
  onUse?: () => void;
}) {
  const t = useT();
  // Uma entrada por gravação (ou documento), não por trecho. Os números [n] da
  // resposta continuam abrindo o instante exato; aqui vai o lugar de onde veio.
  const cited = new Set([...content.matchAll(/\[(\d{1,2})\]/g)].map((match) => Number(match[1])));
  const groups = new Map<string, { key: string; title: string; detail: string; sessionId: string | null; startMs: number; count: number; cited: boolean; excerpt: string; page?: number | null }>();
  citations.forEach((citation, index) => {
    const key = citation.document_id ? `doc:${citation.document_id}` : `s:${citation.session_id}`;
    const isCited = cited.has(index + 1);
    const current = groups.get(key);
    if (current) {
      current.count += 1;
      if (isCited && (!current.cited || citation.start_ms < current.startMs)) {
        current.startMs = citation.start_ms;
        current.excerpt = citation.excerpt;
        current.page = citation.page;
      }
      current.cited = current.cited || isCited;
      return;
    }
    groups.set(key, {
      key,
      title: citation.document_id ? citation.document_name ?? "" : citation.session_title,
      detail: citation.document_id ? t("chat.docWhole") : "",
      sessionId: citation.document_id ? null : citation.session_id,
      startMs: citation.start_ms,
      count: 1,
      cited: isCited,
      excerpt: citation.excerpt,
      page: citation.page,
    });
  });
  const rows = [...groups.values()].sort((a, b) => Number(b.cited) - Number(a.cited));
  const hasSessions = rows.some((row) => row.sessionId);
  return (
    <div className="chat-sources">
      <div className="chat-sources-head">
        <p className="chat-sources-label">{t("chat.sources")}</p>
        {onUse && hasSessions ? (
          <button type="button" className="chat-sources-use" onClick={onUse}>
            {t("chat.useSources")}
          </button>
        ) : null}
      </div>
      <ol>
        {rows.map((row) => (
          <li key={row.key}>
            {row.sessionId ? (
              <button
                type="button"
                title={row.excerpt}
                aria-label={t("chat.sourceOpenAt", { title: row.title, time: formatClock(row.startMs) })}
                onClick={() => onOpenSession(row.sessionId as string, row.startMs)}
              >
                <span className="chat-source-index">
                  <Icon name="mic" size={11} />
                </span>
                <span className="chat-source-copy">
                  <strong>{row.title}</strong>
                  <small>
                    {formatClock(row.startMs)}
                    {row.count > 1 ? ` · ${t("chat.sourceExcerpts", { count: row.count })}` : ""}
                  </small>
                </span>
              </button>
            ) : (
              <Peek label={`${row.title}${row.page ? ` · ${t("chat.docPages", { pages: row.page })}` : ""}`} excerpt={row.excerpt}>
                <span className="chat-source-index">
                  <Icon name="attach" size={11} />
                </span>
                <span className="chat-source-copy">
                  <strong>{row.title}</strong>
                  <small>
                    {row.page ? `${t("chat.docPages", { pages: row.page })} · ` : ""}
                    {row.count > 1 ? t("chat.sourceExcerpts", { count: row.count }) : row.detail}
                  </small>
                </span>
              </Peek>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** As conversas citadas são as mesmas dos chips: "Usar estas conversas" não mudaria nada. */
function sameSessions(citations: ChatCitation[], selected: PickedSession[]): boolean {
  const ids = new Set(citations.filter((item) => !item.document_id && item.session_id).map((item) => item.session_id));
  return ids.size === selected.length && selected.every((item) => ids.has(item.sessionId));
}

/** A sessão citada na resposta, quando há uma só. */
function citedSession(citations: ChatCitation[]): string | null {
  const ids = new Set(citations.filter((item) => !item.document_id && item.session_id).map((item) => item.session_id));
  return ids.size === 1 ? [...ids][0] ?? null : null;
}

const STAMP_SLACK_MS = 60_000;

/**
 * Marca de tempo da resposta vira botão que abre a conversa citada naquele momento.
 * Uma conversa só: abre nela. Várias: a citação de tempo mais perto; se outra conversa
 * também cabe, o título curto vai junto para dizer qual.
 */
function stampRenderer(citations: ChatCitation[], open: (sessionId: string, atMs?: number) => void, noSource: string) {
  const spoken = citations.filter((item) => !item.document_id && item.session_id);
  const only = citedSession(citations);
  const muted = (stamp: string) => (
    <span className="chat-stamp is-muted" title={noSource}>
      {stamp}
    </span>
  );
  return (stamp: string): ReactNode => {
    const ms = stampToMs(stamp);
    if (ms === null) return muted(stamp);
    const near = spoken
      .map((item) => ({ item, gap: Math.abs(item.start_ms - ms) }))
      .filter((entry) => entry.gap <= STAMP_SLACK_MS)
      .sort((a, b) => a.gap - b.gap);
    const target = near[0]?.item.session_id;
    if (!target) return muted(stamp);
    const ambiguous = !only && new Set(near.map((entry) => entry.item.session_id)).size > 1;
    const title = ambiguous ? near[0]!.item.session_title : "";
    const bare = withoutTrailingDate(title);
    const short = bare.length > 18 ? `${bare.slice(0, 17)}…` : bare;
    return (
      <button type="button" className="chat-stamp" title={title || undefined} onClick={() => open(target, ms)}>
        {short ? `${stamp} · ${short}` : stamp}
      </button>
    );
  };
}

/** "[3]" na resposta vira a fonte 3: clique abre a gravação no instante da fala. */
function citeRenderer(
  citations: ChatCitation[],
  open: (sessionId: string, atMs?: number) => void,
  t: (key: string, vars?: Record<string, string | number>) => string,
) {
  if (!citations.length) return undefined;
  return (index: number): ReactNode => {
    const citation = citations[index - 1];
    if (!citation) return `[${index}]`;
    const label = citation.document_id
      ? `${citation.document_name}${citation.page ? ` · ${t("chat.docPages", { pages: citation.page })}` : ""}`
      : `${citation.session_title} · ${formatClock(citation.start_ms)}`;
    return (
      <Peek
        className="chat-cite"
        label={label}
        excerpt={citation.excerpt}
        ariaLabel={citation.document_id ? undefined : t("chat.citeOpen", { n: index })}
        onClick={citation.document_id ? undefined : () => open(citation.session_id, citation.start_ms)}
      >
        {index}
      </Peek>
    );
  };
}

/** O bloco ```prompt da resposta (modo Resolver); sem ele, a resposta inteira. */
export function promptOf(markdown: string): string {
  const match = /```(?:prompt|text|txt|markdown|md)?\s*\n([\s\S]*?)```/i.exec(markdown);
  const fenced = match?.[1]?.trim();
  return fenced && fenced.length > 120 ? fenced : markdown.trim();
}

/** Itens de lista de primeiro nível da resposta, limpos de Markdown, para virar tarefas. */
export function listItems(markdown: string): string[] {
  const out: string[] = [];
  for (const raw of markdown.replace(/\r\n?/g, "\n").split("\n")) {
    const match = /^(?:[-*•]|\d+[.)])\s+(.*)$/.exec(raw);
    if (!match) continue;
    let text = (match[1] ?? "").replace(/^\[[ xX]\]\s*/, "").replace(/\*\*|__|`/g, "").replace(/\[(\d{1,2})\]/g, "").trim();
    if (text.length > 500) text = `${text.slice(0, 497)}…`;
    if (text) out.push(text);
    if (out.length >= MAX_TASKS) break;
  }
  return out;
}

/** Botão focável com o trecho da fonte num balão (passar o mouse ou focar pelo teclado). */
function Peek({
  className,
  label,
  excerpt,
  ariaLabel,
  onClick,
  children,
}: {
  className?: string;
  label: string;
  excerpt: string;
  ariaLabel?: string;
  onClick?: () => void;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <span className="chat-peek">
      <button type="button" className={className} aria-label={ariaLabel} aria-describedby={id} onClick={onClick}>
        {children}
      </button>
      <span role="tooltip" id={id} className="chat-peek-pop">
        <strong>{label}</strong>
        {excerpt ? <span>{excerpt}</span> : null}
      </span>
    </span>
  );
}

function StopGlyph() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden>
      <rect x="4" y="4" width="8" height="8" rx="1.5" fill="currentColor" />
    </svg>
  );
}

function PlusGlyph() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M8 3.2v10M3.2 8h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function SendGlyph() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3 8h9M8.2 3.6 13 8l-4.8 4.4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
