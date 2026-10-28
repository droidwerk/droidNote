import type { ReactNode } from "react";

import { useT } from "../../shared/i18n";
import { InfoTip } from "../../shared/ui/InfoTip";
import { Icon } from "../../shared/ui/Icon";
import { EngineBanner } from "./EngineBanner";

interface NoteDocumentProps {
  /** Suas anotações (com o contexto que a IA achou em cada uma). */
  notes: ReactNode;
  notesCount?: number;
  /** A ata escrita pela IA. */
  aiNote: ReactNode;
  /** Durante a gravação você escreve primeiro; depois, a ata vem em cima. */
  aiFirst: boolean;
  engineRevision?: number;
  onOpenSettings?: () => void;
}

/** Documento único da sessão: o que você escreveu e o que a IA escreveu, juntos e distinguíveis. */
export function NoteDocument({ notes, notesCount = 0, aiNote, aiFirst, engineRevision = 0, onOpenSettings }: NoteDocumentProps) {
  const t = useT();
  const mine = (
    <section className="doc-section is-mine" key="mine">
      <header className="doc-section-head">
        <span className="doc-author is-you">
          <Icon name="dictation" size={12} />
          {t("doc.you")}
        </span>
        <h3>{t("doc.notesTitle")}</h3>
        {notesCount ? <span className="doc-count">{notesCount}</span> : null}
      </header>
      {notes}
    </section>
  );
  const ai = (
    <section className="doc-section is-ai" key="ai">
      <header className="doc-section-head">
        <span className="doc-author is-ai">
          <Icon name="spark" size={12} />
          {t("doc.ai")}
        </span>
        <InfoTip text={t("doc.aiHint")} />
      </header>
      {aiNote}
    </section>
  );
  return (
    <div className="note-document">
      <EngineBanner revision={engineRevision} onOpenSettings={onOpenSettings} />
      {aiFirst ? [ai, mine] : [mine, ai]}
    </div>
  );
}
