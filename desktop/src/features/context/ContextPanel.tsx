import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import { api } from "../../shared/api/client";
import type { ChatDocument } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";
import { Button } from "../../shared/ui/primitives";
import { DOCUMENT_ACCEPT, DocumentTray } from "../chat/DocumentTray";

interface ContextPanelProps {
  sessionId: string;
  revision?: number;
}

/** Material de apoio da conversa: pauta, slides, contrato. A ata e o chat passam a usá-lo. */
export function ContextPanel({ sessionId, revision = 0 }: ContextPanelProps) {
  const t = useT();
  const [docs, setDocs] = useState<ChatDocument[] | null>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dropping, setDropping] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setDocs(await api.sessionDocuments(sessionId));
    } catch {
      setDocs([]);
    }
  }, [sessionId]);

  useEffect(() => {
    setDocs(null);
    void load();
  }, [load, revision]);

  const addFiles = async (files: FileList | File[]) => {
    setError(null);
    for (const file of [...files]) {
      setUploading((current) => [...current, file.name]);
      try {
        const doc = await api.uploadSessionDocument(sessionId, file);
        setDocs((current) => [...(current ?? []), doc]);
      } catch (err) {
        const code = err instanceof Error ? err.message : "";
        const key = `chat.docErr_${code}`;
        const message = t(key as never);
        setError(`${file.name}: ${message === key ? t("chat.docErr_unreadable") : message}`);
      } finally {
        setUploading((current) => current.filter((name) => name !== file.name));
      }
    }
  };

  const remove = async (doc: ChatDocument) => {
    setDocs((current) => (current ?? []).filter((item) => item.id !== doc.id));
    try {
      await api.deleteDocument(doc.id);
    } catch {
      void load();
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDropping(false);
    if (event.dataTransfer.files.length) void addFiles(event.dataTransfer.files);
  };

  return (
    <section className="context-panel">
      <div
        className={dropping ? "context-drop is-over" : "context-drop"}
        onDragOver={(event) => {
          if (!event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          setDropping(true);
        }}
        onDragLeave={() => setDropping(false)}
        onDrop={onDrop}
      >
        <Icon name="attach" size={18} />
        <strong>{t("context.title")}</strong>
        <p>{t("context.hint")}</p>
        <Button size="sm" variant="primary" onClick={() => picker.current?.click()}>
          {t("context.add")}
        </Button>
        <input
          ref={picker}
          type="file"
          hidden
          multiple
          accept={DOCUMENT_ACCEPT}
          onChange={(event) => {
            if (event.target.files?.length) void addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {error ? <p className="banner">{error}</p> : null}
      {docs === null ? (
        <p className="dg-hint">{t("common.loading")}</p>
      ) : docs.length || uploading.length ? (
        <DocumentTray documents={docs} uploading={uploading} onRemove={(doc) => void remove(doc)} />
      ) : (
        <p className="dg-hint">{t("context.empty")}</p>
      )}
    </section>
  );
}
