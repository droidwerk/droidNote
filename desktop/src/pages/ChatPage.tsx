import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

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
import { ChatTune, readSolveTarget, readStyle, scopePayload, type ScopeChoice } from "../features/chat/ChatTune";
import { IMAGE_ACCEPT, MAX_IMAGES, isImageFile, prepareImage } from "../features/chat/images";
import { EngineBanner } from "../features/document/EngineBanner";
import { stampToMs } from "../features/summary/NoteEditor";
import { AiThinking } from "../shared/ui/AiThinking";
import { InfoTip } from "../shared/ui/InfoTip";
import { Icon } from "../shared/ui/Icon";
import { Markdown } from "../shared/ui/Markdown";
import { useToast } from "../shared/ui/Toast";
import { templateName } from "../shared/lib/templates";
import { useI18n, useT } from "../shared/i18n";
import { copyToClipboard, formatClock, formatDate } from "../shared/lib/format";
import { saveBlob } from "../shared/lib/saveFile";
import { useFlag } from "../shared/lib/useFlag";
import { Button } from "../shared/ui/primitives";

const CONTEXT_LIMIT = 6;
const MAX_TASKS = 20;
const MAX_NOTE_CHARS = 4000;

/** Comandos com "/" e materiais de estudo: ids fixos, rótulos e perguntas traduzidos. */
const COMMANDS = ["summary", "tasks", "decisions", "glossary", "flashcards", "exercises", "onepage", "exam"] as const;
type CommandId = (typeof COMMANDS)[number];
const STUDY: CommandId[] = ["flashcards", "exercises", "onepage", "exam"];

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
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [recent, setRecent] = useState<Session[]>([]);
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
  const [scope, setScope] = useState<ScopeChoice>({ kind: "auto" });
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

  useEffect(() => {
    void loadThreads();
    // As aulas reais viram o contexto oferecido: nada de pergunta pronta que
    // não tem relação com o que foi capturado.
    void api
      .sessions()
      .then((items) => setRecent(items.slice(0, CONTEXT_LIMIT)))
      .catch(() => setRecent([]));
  }, []);

  useEffect(() => {
    if (!focus) return;
    setPendingFocus(focus);
    setActiveId(null);
    setActiveThread(null);
    setMessages([]);
    setDocs([]);
    setImages([]);
    if (focus.prompt) setDraft(focus.prompt);
    onFocusConsumed();
    window.setTimeout(() => input.current?.focus(), 40);
  }, [focus, onFocusConsumed]);

  useEffect(() => {
    const node = scroller.current;
    if (!node || !stickBottom) return;
    node.scrollTop = node.scrollHeight;
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
    setError(null);
    input.current?.focus();
    void api
      .sessions()
      .then((items) => setRecent(items.slice(0, CONTEXT_LIMIT)))
      .catch(() => undefined);
  };

  const focusSessionId = pendingFocus?.sessionId ?? activeThread?.focus_session_id ?? null;

  const send = async (text: string) => {
    const cleaned = text.trim();
    if (!cleaned || busy) return;
    const attached = images;
    setDraft("");
    setImages([]);
    setBusy(true);
    setError(null);
    setStickBottom(true);
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
    setMessages((current) => [...current, optimistic, streaming]);
    try {
      const result = await askChat(
        {
          message: cleaned,
          chat_id: activeId,
          session_id: pendingFocus?.sessionId,
          segment_ids: pendingFocus?.segmentId ? [pendingFocus.segmentId] : [],
          document_ids: docs.map((item) => item.id),
          ui_language: locale,
          style,
          grounded,
          solve_target: solveTarget,
          scope: scopePayload(scope, focusSessionId),
          images: attached.map((item) => ({ name: item.name, mime: item.mime, data: item.data })),
        },
        (token) => {
          setMessages((current) =>
            current.map((item) =>
              item.id === streaming.id ? { ...item, content: item.content + token } : item,
            ),
          );
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
      setMessages((current) => current.filter((item) => item.id !== streaming.id));
      setImages(attached);
      setError(err instanceof Error ? err.message : t("chat.fail"));
    } finally {
      setBusy(false);
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
  const focusedSession = pendingFocus?.sessionId ?? null;

  const focusSession = (session: Session) => {
    setPendingFocus(
      focusedSession === session.id
        ? null
        : { sessionId: session.id, sessionTitle: session.title },
    );
    input.current?.focus();
  };

  const commandLabel = (id: CommandId) => t(`chat.cmd_${id}`);
  const runCommand = (id: CommandId) => {
    setDraft("");
    void send(t(`chat.cmdAsk_${id}`));
  };
  // Menu de comandos: abre quando a pergunta começa com "/" e ainda está numa linha.
  const slashQuery = draft.startsWith("/") && !draft.includes("\n") ? draft.slice(1).toLowerCase() : null;
  const commandMatches = useMemo(
    () =>
      slashQuery === null
        ? []
        : COMMANDS.filter((id) => commandLabel(id).slice(1).toLowerCase().startsWith(slashQuery) || id.startsWith(slashQuery)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [slashQuery, locale],
  );
  useEffect(() => setCommandIndex(0), [slashQuery]);

  const placeholder = docs.length
    ? t("chat.placeholderDocs")
    : pendingFocus?.excerpt
    ? t("chat.placeholderFocus")
    : pendingFocus?.sessionTitle
      ? t("chat.placeholderSession", { title: pendingFocus.sessionTitle })
      : t("chat.placeholder");

  return (
    <div className={railCollapsed ? "chat-page is-rail-collapsed" : "chat-page"}>
      <aside className="chat-rail" aria-label={t("chat.threads")}>
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
          <strong>{t("chat.threads")}</strong>
          <Button size="sm" variant="quiet" aria-label={t("chat.new")} title={t("chat.new")} onClick={startNew}>
            <PlusGlyph />
          </Button>
        </div>
        <div className="chat-thread-list">
          {threads.length === 0 ? (
            <p className="chat-rail-empty">{t("chat.emptyThreads")}</p>
          ) : (
            threads.map((thread) => (
              <button
                key={thread.id}
                type="button"
                className={thread.id === activeId ? "chat-thread is-active" : "chat-thread"}
                onClick={() => void openThread(thread.id)}
              >
                <span className="chat-thread-title">{thread.title}</span>
              </button>
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
            <h1 className="with-tip">
              {t("chat.askAnything")}
              <InfoTip text={t("chat.intro")} />
            </h1>
            {docs.length ? (
              <div className="chat-context">
                <p className="chat-context-label">{t("chat.docAsksLabel")}</p>
                <div className="chips">
                  {(["summary", "numbers", "compare", "risks"] as const).map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="chip"
                      onClick={() => {
                        setDraft(t(`chat.docAsk_${id}`));
                        input.current?.focus();
                      }}
                    >
                      {t(`chat.docAskLabel_${id}`)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {pendingFocus?.excerpt ? (
              <div className="chat-focus">
                <small>{pendingFocus.sessionTitle ?? t("chat.selectedExcerpt")}</small>
                <p>{pendingFocus.excerpt}</p>
              </div>
            ) : null}
            {recent.length > 0 && !pendingFocus?.excerpt ? (
              <div className="chat-context">
                <p className="chat-context-label with-tip">
                  {t("chat.contextLabel")}
                  <InfoTip text={focusedSession ? t("chat.contextHintFocused") : t("chat.contextHint")} />
                </p>
                <div className="chat-context-list" role="group" aria-label={t("chat.contextLabel")}>
                  {recent.map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      aria-pressed={focusedSession === session.id}
                      className={
                        focusedSession === session.id
                          ? "chat-context-chip is-active"
                          : "chat-context-chip"
                      }
                      onClick={() => focusSession(session)}
                    >
                      <strong>{session.title}</strong>
                      <small>{formatDate(session.started_at)}</small>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {focusedSession ? (
              <div className="chat-context">
                <p className="chat-context-label with-tip">
                  {t("chat.studyLabel")}
                  <InfoTip text={t("chat.studyHint")} />
                </p>
                <div className="chips">
                  {STUDY.map((id) => (
                    <button key={id} type="button" className="chip" title={t(`chat.cmdHint_${id}`)} onClick={() => runCommand(id)}>
                      {t(`chat.cmdTitle_${id}`)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {recipes.length ? (
              <div className="chat-context">
                <p className="chat-context-label with-tip">
                  {t("recipes.title")}
                  <InfoTip text={t("recipes.hint")} />
                </p>
                <div className="chips">
                  {recipes.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="chip"
                      title={item.body}
                      onClick={() => {
                        setDraft(item.body);
                        input.current?.focus();
                      }}
                    >
                      {templateName(item)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
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
            {messages.map((item) => (
              <article
                key={item.id}
                className={item.role === "user" ? "chat-turn is-user" : "chat-turn"}
                aria-live={item.role === "assistant" && busy && item.id.startsWith("stream-") ? "polite" : undefined}
              >
                {!item.content && busy && item.role === "assistant" ? (
                  <AiThinking
                    compact
                    lines={3}
                    steps={docs.length ? [t("ai.readDocs"), t("ai.searchMemory"), t("ai.answer")] : [t("ai.searchMemory"), t("ai.answer")]}
                  />
                ) : (
                  item.role === "assistant" ? (
                    <Markdown
                      text={item.content}
                      renderStamp={stampRenderer(citedSession(item.citations), onOpenSession)}
                      renderCite={citeRenderer(item.citations, onOpenSession, t)}
                      chartTableLabel={t("chat.chartTable")}
                      promptLabels={{ title: t("chat.promptReady"), copy: t("chat.promptCopy"), copied: t("common.copied") }}
                    />
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
                  )
                )}
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
                  />
                ) : null}
                {item.citations.length > 0 ? (
                  <ChatSources citations={item.citations} content={item.content} onOpenSession={onOpenSession} />
                ) : null}
              </article>
            ))}
          </div>
        )}
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
              {commandMatches.map((id, index) => (
                <li key={id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === commandIndex}
                    className={index === commandIndex ? "is-active" : ""}
                    onMouseEnter={() => setCommandIndex(index)}
                    onClick={() => runCommand(id)}
                  >
                    <strong>{commandLabel(id)}</strong>
                    <span>{t(`chat.cmdHint_${id}`)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              if (commandMatches.length) runCommand(commandMatches[commandIndex] ?? commandMatches[0]!);
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
            <div className="chat-attach-wrap" ref={attachRef}>
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
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (commandMatches.length) runCommand(commandMatches[commandIndex] ?? commandMatches[0]!);
                  else void send(draft);
                }
              }}
            />
            <ChatTune
              style={style}
              scope={scope}
              grounded={grounded}
              solveTarget={solveTarget}
              hasFocus={Boolean(focusSessionId)}
              disabled={busy}
              onStyle={setStyle}
              onScope={setScope}
              onGrounded={setGrounded}
              onSolveTarget={setSolveTarget}
            />
            <Button
              type="submit"
              variant="primary"
              disabled={busy || !draft.trim()}
              aria-label={t("chat.send")}
              title={t("chat.send")}
            >
              <SendGlyph />
            </Button>
          </form>
        </div>
      </section>
    </div>
  );
}

/** Copiar e um menu "Salvar": nota da gravação, tarefas, PDF, Word, Markdown. */
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
            {t("chat.save")} ▾
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
}: {
  citations: ChatCitation[];
  content: string;
  onOpenSession: (sessionId: string, atMs?: number) => void;
}) {
  const t = useT();
  // Uma entrada por gravação (ou documento), não por trecho. Os números [n] da
  // resposta continuam abrindo o instante exato; aqui vai o lugar de onde veio.
  const cited = new Set([...content.matchAll(/\[(\d{1,2})\]/g)].map((match) => Number(match[1])));
  const groups = new Map<string, { key: string; title: string; detail: string; sessionId: string | null; startMs: number; count: number; cited: boolean; excerpt: string }>();
  citations.forEach((citation, index) => {
    const key = citation.document_id ? `doc:${citation.document_id}` : `s:${citation.session_id}`;
    const isCited = cited.has(index + 1);
    const current = groups.get(key);
    if (current) {
      current.count += 1;
      if (isCited && (!current.cited || citation.start_ms < current.startMs)) {
        current.startMs = citation.start_ms;
        current.excerpt = citation.excerpt;
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
    });
  });
  const rows = [...groups.values()].sort((a, b) => Number(b.cited) - Number(a.cited));
  return (
    <div className="chat-sources">
      <p className="chat-sources-label">{t("chat.sources")}</p>
      <ol>
        {rows.map((row) => (
          <li key={row.key}>
            {row.sessionId ? (
              <button
                type="button"
                title={row.excerpt}
                aria-label={t("chat.sourceOpen")}
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
              <span className="chat-source-doc" title={row.excerpt}>
                <span className="chat-source-index">
                  <Icon name="attach" size={11} />
                </span>
                <span className="chat-source-copy">
                  <strong>{row.title}</strong>
                  <small>{row.count > 1 ? t("chat.sourceExcerpts", { count: row.count }) : row.detail}</small>
                </span>
              </span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** A sessão citada na resposta, quando há uma só: aí `12:40` no texto pode levar à fala. */
function citedSession(citations: ChatCitation[]): string | null {
  const ids = new Set(citations.filter((item) => !item.document_id && item.session_id).map((item) => item.session_id));
  return ids.size === 1 ? [...ids][0] ?? null : null;
}

/** Marca de tempo da resposta vira botão que abre a conversa citada naquele momento. */
function stampRenderer(sessionId: string | null, open: (sessionId: string, atMs?: number) => void) {
  if (!sessionId) return undefined;
  return (stamp: string): ReactNode => {
    const ms = stampToMs(stamp);
    if (ms === null) return stamp;
    return (
      <button type="button" className="chat-stamp" onClick={() => open(sessionId, ms)}>
        {stamp}
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
      ? `${citation.document_name}${citation.page ? ` · p. ${citation.page}` : ""}`
      : `${citation.session_title} · ${formatClock(citation.start_ms)}`;
    if (citation.document_id) {
      return (
        <span className="chat-cite" title={`${label}\n${citation.excerpt}`}>
          {index}
        </span>
      );
    }
    return (
      <button
        type="button"
        className="chat-cite"
        title={`${t("chat.citeOpen", { n: index })}: ${label}\n${citation.excerpt}`}
        onClick={() => open(citation.session_id, citation.start_ms)}
      >
        {index}
      </button>
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
