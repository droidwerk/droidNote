import type { ChatDocument, ChatImageDraft } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

export const DOCUMENT_ACCEPT = ".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md";

const KIND_LABEL: Record<string, string> = {
  pdf: "PDF",
  word: "DOCX",
  excel: "XLSX",
  csv: "CSV",
  text: "TXT",
  web: "WEB",
  youtube: "YT",
};

interface DocumentTrayProps {
  documents: ChatDocument[];
  uploading: string[];
  images?: ChatImageDraft[];
  disabled?: boolean;
  onRemove: (document: ChatDocument) => void;
  onRemoveImage?: (index: number) => void;
}

/** Documentos e imagens anexados ao chat, logo acima do campo de pergunta. */
export function DocumentTray({ documents, uploading, images = [], disabled = false, onRemove, onRemoveImage }: DocumentTrayProps) {
  const t = useT();
  if (!documents.length && !uploading.length && !images.length) return null;
  return (
    <ul className="doc-tray" aria-label={t("chat.docsAttached")}>
      {documents.map((doc) => (
        <li key={doc.id} className={`doc-chip doc-${doc.kind}`} title={t("chat.docMeta", { pages: doc.pages, chunks: doc.chunks })}>
          <span className="doc-kind">{KIND_LABEL[doc.kind] ?? doc.kind.toUpperCase()}</span>
          <span className="doc-name">{doc.name}</span>
          <small>{formatSize(doc.size)}</small>
          <button
            type="button"
            disabled={disabled}
            aria-label={t("chat.docRemove", { name: doc.name })}
            title={t("chat.docRemove", { name: doc.name })}
            onClick={() => onRemove(doc)}
          >
            <Icon name="close" size={12} />
          </button>
        </li>
      ))}
      {images.map((image, index) => (
        <li key={`img-${index}`} className="doc-chip doc-image" title={t("chat.imageHint")}>
          <img src={image.preview} alt="" />
          <span className="doc-name">{image.name}</span>
          <button
            type="button"
            disabled={disabled}
            aria-label={t("chat.docRemove", { name: image.name })}
            title={t("chat.docRemove", { name: image.name })}
            onClick={() => onRemoveImage?.(index)}
          >
            <Icon name="close" size={12} />
          </button>
        </li>
      ))}
      {uploading.map((name) => (
        <li key={`up-${name}`} className="doc-chip is-loading">
          <span className="doc-kind">…</span>
          <span className="doc-name">{name}</span>
          <small>{t("chat.docReading")}</small>
        </li>
      ))}
    </ul>
  );
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function hasFiles(event: { dataTransfer: DataTransfer | null }): boolean {
  return Boolean(event.dataTransfer && [...event.dataTransfer.types].includes("Files"));
}
