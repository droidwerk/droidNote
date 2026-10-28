import { useEffect, useRef, useState, type ReactNode } from "react";

import { api, askChat } from "../shared/api/client";
import type { ChatCitation, ChatDocument, ChatFocus, ChatMessage, ChatThread, NoteTemplate, Session } from "../shared/api/types";
import { DOCUMENT_ACCEPT, DocumentTray, hasFiles } from "../features/chat/DocumentTray";
import { EngineBanner } from "../features/document/EngineBanner";
import { stampToMs } from "../features/summary/NoteEditor";
import { AiThinking } from "../shared/ui/AiThinking";
import { InfoTip } from "../shared/ui/InfoTip";
import { Icon } from "../shared/ui/Icon";
import { templateName } from "../shared/lib/templates";
import { useI18n, useT } from "../shared/i18n";
import { copyToClipboard, formatClock, formatDate } from "../shared/lib/format";
import { useFlag } from "../shared/lib/useFlag";
import { Button } from "../shared/ui/primitives";

const CONTEXT_LIMIT = 6;

interface ChatPageProps {
  recipes?: NoteTemplate[];
  focus: ChatFocus | null;
  onOpenSession: (sessionId: string, atMs?: number) => void;
  onFocusConsumed: () => void;
  onOpenSettings?: () => void;
}

interface SourceRow {
  session_id: string;
  session_title: string;
  start_ms: number;
  excerpt: string;
  count: number;
}

export function ChatPage({ recipes = [], focus, onOpenSession, onFocusConsumed, onOpenSettings }: ChatPageProps) {
  const { locale, t } = useI18n();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [recent, setRecent] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFocus, setPendingFocus] = useState<ChatFocus | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [stickBottom, setStickBottom] = useState(true);
  const [docs, setDocs] = useState<ChatDocument[]>([]);
  const [railCollapsed, toggleRail] = useFlag("droidnote.chatRailCollapsed");
  const [uploading, setUploading] = useState<string[]>([]);
  const [dropping, setDropping] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  const addFiles = async (files: FileList | File[]) => {
    for (const file of [...files]) {
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
    setMessages([]);
    setDocs([]);
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

  const openThread = async (id: string) => {
    const detail = await api.chat(id);
    setActiveId(detail.chat.id);
    setMessages(detail.messages);
    setPendingFocus(null);
    setError(null);
    setStickBottom(true);
    setDocs(await api.documents(detail.chat.id).catch(() => []));
  };

  const startNew = () => {
    setActiveId(null);
    setMessages([]);
    setDocs([]);
    setPendingFocus(null);
    setError(null);
    input.current?.focus();
    void api
      .sessions()
      .then((items) => setRecent(items.slice(0, CONTEXT_LIMIT)))
      .catch(() => undefined);
  };

  const send = async (text: string) => {
    const cleaned = text.trim();
    if (!cleaned || busy) return;
    setDraft("");
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
    };
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
      setPendingFocus(null);
      const detail = await api.chat(result.chat.id);
      setMessages(detail.messages);
      setDocs(await api.documents(result.chat.id).catch(() => docs));
      await loadThreads();
    } catch (err) {
      setMessages((current) => current.filter((item) => item.id !== streaming.id));
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
                  <p>{item.role === "assistant" ? linkStamps(item.content, citedSession(item.citations), onOpenSession) : item.content}</p>
                )}
                {item.role === "assistant" && item.content ? (
                  <div className="chat-turn-actions">
                    <button
                      type="button"
                      onClick={() => void copyAnswer(item)}
                    >
                      {copiedId === item.id ? t("common.copied") : t("chat.copyAnswer")}
                    </button>
                  </div>
                ) : null}
                {item.citations.length > 0 ? (
                  <ChatSources citations={item.citations} onOpenSession={onOpenSession} />
                ) : null}
              </article>
            ))}
          </div>
        )}
        {error ? <p className="chat-error">{error}</p> : null}
        <div className="chat-engine">
          <EngineBanner revision={messages.length} onOpenSettings={onOpenSettings} />
        </div>
        <DocumentTray documents={docs} uploading={uploading} disabled={busy} onRemove={(doc) => void removeDoc(doc)} />
        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send(draft);
          }}
        >
          <input
            ref={picker}
            type="file"
            accept={DOCUMENT_ACCEPT}
            multiple
            hidden
            onChange={(event) => {
              if (event.target.files?.length) void addFiles(event.target.files);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            className="chat-attach"
            disabled={busy}
            aria-label={t("chat.attach")}
            title={`${t("chat.attach")} (${t("chat.docTypes")})`}
            onClick={() => picker.current?.click()}
          >
            <Icon name="attach" size={17} />
          </button>
          <textarea
            ref={input}
            value={draft}
            rows={1}
            placeholder={placeholder}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(draft);
              }
            }}
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
      </section>
    </div>
  );
}

function ChatSources({
  citations,
  onOpenSession,
}: {
  citations: ChatCitation[];
  onOpenSession: (sessionId: string) => void;
}) {
  const t = useT();
  const sources = groupSources(citations.filter((item) => !item.document_id));
  const documents = groupDocuments(citations.filter((item) => item.document_id));
  return (
    <div className="chat-sources">
      <p className="chat-sources-label">{t("chat.sources")}</p>
      <ol>
        {documents.map((doc) => (
          <li key={doc.id}>
            <span className="chat-source-doc" title={doc.excerpt}>
              <span className="chat-source-index">
                <Icon name="attach" size={11} />
              </span>
              <span className="chat-source-copy">
                <strong>{doc.name}</strong>
                <small>{doc.pages.length ? t("chat.docPages", { pages: doc.pages.join(", ") }) : t("chat.docWhole")}</small>
              </span>
            </span>
          </li>
        ))}
        {sources.map((source, index) => (
          <li key={source.session_id}>
            <button
              type="button"
              title={source.excerpt}
              aria-label={t("chat.sourceOpen")}
              onClick={() => onOpenSession(source.session_id)}
            >
              <span className="chat-source-index">{index + 1}</span>
              <span className="chat-source-copy">
                <strong>{source.session_title}</strong>
                <small>
                  {formatClock(source.start_ms)}
                  {source.count > 1 ? ` · ${source.count}` : ""}
                </small>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

function groupSources(citations: ChatCitation[]): SourceRow[] {
  const rows: SourceRow[] = [];
  const indexBySession = new Map<string, number>();
  for (const citation of citations) {
    const existing = indexBySession.get(citation.session_id);
    if (existing === undefined) {
      indexBySession.set(citation.session_id, rows.length);
      rows.push({
        session_id: citation.session_id,
        session_title: citation.session_title,
        start_ms: citation.start_ms,
        excerpt: citation.excerpt,
        count: 1,
      });
      continue;
    }
    const row = rows[existing];
    if (!row) continue;
    row.count += 1;
    if (citation.start_ms < row.start_ms) row.start_ms = citation.start_ms;
  }
  return rows;
}

/** A sessão citada na resposta, quando há uma só: aí `12:40` no texto pode levar à fala. */
function citedSession(citations: ChatCitation[]): string | null {
  const ids = new Set(citations.filter((item) => !item.document_id && item.session_id).map((item) => item.session_id));
  return ids.size === 1 ? [...ids][0] ?? null : null;
}

const STAMP_IN_TEXT = /\b(\d{1,2}:\d{2}(?::\d{2})?)\b/g;

function linkStamps(text: string, sessionId: string | null, open: (sessionId: string, atMs?: number) => void) {
  if (!sessionId) return text;
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(STAMP_IN_TEXT)) {
    const ms = stampToMs(match[1] ?? "");
    if (ms === null || match.index === undefined) continue;
    parts.push(text.slice(last, match.index));
    parts.push(
      <button key={`${match.index}`} type="button" className="chat-stamp" onClick={() => open(sessionId, ms)}>
        {match[1]}
      </button>,
    );
    last = match.index + match[0].length;
  }
  if (!parts.length) return text;
  parts.push(text.slice(last));
  return parts;
}

function groupDocuments(citations: ChatCitation[]): { id: string; name: string; pages: number[]; excerpt: string }[] {
  const rows = new Map<string, { id: string; name: string; pages: number[]; excerpt: string }>();
  for (const citation of citations) {
    const id = citation.document_id as string;
    const row = rows.get(id) ?? { id, name: citation.document_name ?? "", pages: [], excerpt: citation.excerpt };
    if (citation.page && !row.pages.includes(citation.page)) row.pages.push(citation.page);
    rows.set(id, row);
  }
  return [...rows.values()].map((row) => ({ ...row, pages: row.pages.sort((a, b) => a - b) }));
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
