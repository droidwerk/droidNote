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
