import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

export interface MeetingNotice {
  status: "detected" | "ended" | "auto-started";
  app: string;
  browser: boolean;
}

interface MeetingBannerProps {
  notice: MeetingNotice;
  recording: boolean;
  busy: boolean;
  onRecord: () => void;
  onStop: () => void;
  onDismiss: () => void;
  onCopyConsent?: () => void;
}

/** Aviso de reunião detectada pelo microfone: gravar, ou parar quando ela termina. */
export function MeetingBanner({ notice, recording, busy, onRecord, onStop, onDismiss, onCopyConsent }: MeetingBannerProps) {
  const t = useT();
  const ended = notice.status === "ended";
  const auto = notice.status === "auto-started";
  const title = ended
    ? t("meeting.ended", { app: notice.app })
    : auto
      ? t("meeting.autoStarted", { app: notice.app })
      : notice.browser
        ? t("meeting.detectedBrowser", { app: notice.app })
        : t("meeting.detected", { app: notice.app });
  return (
    <div className={ended ? "meeting-banner is-ended" : "meeting-banner"} role="status">
      <span className="meeting-banner-icon" aria-hidden>
        <Icon name="meeting" size={18} />
      </span>
      <div className="meeting-banner-copy">
        <strong>{title}</strong>
        <small>{ended ? t("meeting.endedHint") : auto ? t("meeting.autoHint") : t("meeting.detectedHint")}</small>
      </div>
      <div className="meeting-banner-actions">
        {ended && recording ? (
          <button type="button" className="button button-primary button-sm" disabled={busy} onClick={onStop}>
            {t("live.stop")}
          </button>
        ) : null}
        {!ended && !recording ? (
          <button type="button" className="button button-primary button-sm" disabled={busy} onClick={onRecord}>
            <span className="dot" />
            {t("meeting.record")}
          </button>
        ) : null}
        {!ended && onCopyConsent ? (
          <button type="button" className="button button-ghost button-sm" onClick={onCopyConsent} title={t("consent.copyHint")}>
            <Icon name="shield" size={14} />
            {t("consent.short")}
          </button>
        ) : null}
        <button type="button" className="button button-quiet button-sm" onClick={onDismiss}>
          {ended && recording ? t("meeting.keep") : t("meeting.dismiss")}
        </button>
      </div>
    </div>
  );
}

interface CaptureAlertBannerProps {
  /** Pergunta "a reunião ainda está acontecendo?" pendente; null = só pausado. */
  alert: "silence" | "music" | null;
  busy: boolean;
  onContinue: () => void;
  onEnd: () => void;
  onResume: () => void;
}

/** Aviso dentro da janela: pergunta de silêncio (dois botões) ou gravação pausada (Continuar). */
export function CaptureAlertBanner({ alert, busy, onContinue, onEnd, onResume }: CaptureAlertBannerProps) {
  const t = useT();
  return (
    <div className="meeting-banner is-ask" role="status">
      <span className="meeting-banner-icon" aria-hidden>
        <Icon name={alert ? "help" : "pause"} size={18} />
      </span>
      <div className="meeting-banner-copy">
        <strong>{alert ? t("mini.alertTitle") : t("mini.paused")}</strong>
        <small>{alert === "music" ? t("mini.alertMusic") : alert ? t("mini.alertSilence") : t("mini.alertPaused")}</small>
      </div>
      <div className="meeting-banner-actions">
        {alert ? (
          <>
            <button type="button" className="button button-ghost button-sm" disabled={busy} onClick={onContinue}>
              {t("mini.alertContinue")}
            </button>
            <button type="button" className="button button-primary button-sm" disabled={busy} onClick={onEnd}>
              {t("mini.alertEnd")}
            </button>
          </>
        ) : (
          <button type="button" className="button button-primary button-sm" disabled={busy} onClick={onResume}>
            {t("mini.resume")}
          </button>
        )}
      </div>
    </div>
  );
}
