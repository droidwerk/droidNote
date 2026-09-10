import { useEffect, useRef, useState } from "react";

import { api, askChat } from "../shared/api/client";
import type { ChatCitation, ChatFocus, ChatMessage, ChatThread, Session } from "../shared/api/types";
import { useI18n, useT } from "../shared/i18n";
import { copyToClipboard, formatClock, formatDate } from "../shared/lib/format";
import { Button } from "../shared/ui/primitives";

const CONTEXT_LIMIT = 6;

interface ChatPageProps {
  focus: ChatFocus | null;
  onOpenSession: (sessionId: string) => void;
  onFocusConsumed: () => void;
}

interface SourceRow {
  session_id: string;
  session_title: string;
  start_ms: number;
  excerpt: string;
  count: number;
}

export function ChatPage({ focus, onOpenSession, onFocusConsumed }: ChatPageProps) {
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
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

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
  };

  const startNew = () => {
    setActiveId(null);
    setMessages([]);
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

  const placeholder = pendingFocus?.excerpt
    ? t("chat.placeholderFocus")
    : pendingFocus?.sessionTitle
      ? t("chat.placeholderSession", { title: pendingFocus.sessionTitle })
      : t("chat.placeholder");

  return (
    <div className="chat-page">
      <aside className="chat-rail" aria-label={t("chat.threads")}>
        <div className="chat-rail-head">
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
      <section className="chat-main">
        {empty ? (
          <div className="chat-empty">
            <h1>{t("chat.askAnything")}</h1>
            <p>{t("chat.intro")}</p>
            {pendingFocus?.excerpt ? (
              <div className="chat-focus">
                <small>{pendingFocus.sessionTitle ?? t("chat.selectedExcerpt")}</small>
                <p>{pendingFocus.excerpt}</p>
              </div>
            ) : null}
            {recent.length > 0 && !pendingFocus?.excerpt ? (
              <div className="chat-context">
                <p className="chat-context-label">{t("chat.contextLabel")}</p>
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
                <p className="chat-context-hint">
                  {focusedSession ? t("chat.contextHintFocused") : t("chat.contextHint")}
                </p>
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
                <p>{item.content || (busy && item.role === "assistant" ? "…" : "")}</p>
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
        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send(draft);
          }}
        >
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
  const sources = groupSources(citations);
  return (
    <div className="chat-sources">
      <p className="chat-sources-label">{t("chat.sources")}</p>
      <ol>
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
