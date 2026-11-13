import { useId } from "react";

import { useI18n } from "../../shared/i18n";
import { openExternal } from "../../shared/lib/openExternal";
import { RELEASES_PAGE, siteUrl, whatsNewFor } from "../../shared/lib/whatsNew";
import { Icon, type IconName } from "../../shared/ui/Icon";
import { Modal } from "../../shared/ui/Modal";
import { Button } from "../../shared/ui/primitives";

const STEPS: { icon: IconName; key: "record" | "read" | "ask" }[] = [
  { icon: "mic", key: "record" },
  { icon: "spark", key: "read" },
  { icon: "chat", key: "ask" },
];

function ExternalLink({ href, children }: { href: string; children: string }) {
  return (
    <button type="button" className="text-link" onClick={() => void openExternal(href)}>
      {children}
    </button>
  );
}

export function WelcomeModal({
  local,
  onClose,
  onTour,
  onHelp,
}: {
  /** Só com os motores locais dá para prometer "tudo neste PC". */
  local: boolean;
  onClose: () => void;
  onTour: () => void;
  onHelp: () => void;
}) {
  const { t, locale } = useI18n();
  const titleId = useId();
  const bodyId = useId();
  return (
    <Modal onClose={onClose} labelledBy={titleId} describedBy={bodyId} className="welcome-dialog" initialFocus=".welcome-start">
      <div className="confirm-copy">
        <h2 id={titleId}>{t("onboarding.welcomeTitle")}</h2>
        <p id={bodyId}>{t(local ? "onboarding.welcomeBodyLocal" : "onboarding.welcomeBody")}</p>
      </div>
      <ol className="welcome-steps">
        {STEPS.map((step) => (
          <li key={step.key}>
            <span className="welcome-icon" aria-hidden>
              <Icon name={step.icon} size={16} />
            </span>
            <span>
              <strong>{t(`onboarding.step.${step.key}Title`)}</strong>
              <span className="muted">{t(`onboarding.step.${step.key}Body`)}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className="confirm-actions">
        <Button onClick={onTour}>{t("onboarding.takeTour")}</Button>
        <Button variant="primary" className="welcome-start" onClick={onClose}>
          {t("onboarding.start")}
        </Button>
      </div>
      <nav className="welcome-links" aria-label={t("onboarding.linksLabel")}>
        <ExternalLink href={siteUrl(locale, "droidnote")}>{t("onboarding.productPage")}</ExternalLink>
        <button type="button" className="text-link" onClick={onHelp}>
          {t("onboarding.help")}
        </button>
      </nav>
      <p className="welcome-company muted">
        <ExternalLink href={siteUrl(locale, "products")}>{t("onboarding.products")}</ExternalLink>
        <span aria-hidden> · </span>
        <ExternalLink href={siteUrl(locale, "about")}>{t("onboarding.aboutCompany")}</ExternalLink>
      </p>
    </Modal>
  );
}

export function WhatsNewModal({ version, onClose }: { version: string; onClose: () => void }) {
  const { t } = useI18n();
  const titleId = useId();
  return (
    <Modal onClose={onClose} labelledBy={titleId} className="welcome-dialog" initialFocus=".welcome-start">
      <div className="confirm-copy">
        <h2 id={titleId}>{t("whatsNew.title", { version })}</h2>
      </div>
      <ul className="whats-new-list">
        {whatsNewFor(version).map((id) => (
          <li key={id}>{t(`whatsNew.items.${id}`)}</li>
        ))}
      </ul>
      <div className="confirm-actions">
        <Button onClick={() => void openExternal(RELEASES_PAGE)}>{t("whatsNew.allNotes")}</Button>
        <Button variant="primary" className="welcome-start" onClick={onClose}>
          {t("whatsNew.close")}
        </Button>
      </div>
    </Modal>
  );
}

