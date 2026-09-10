import { useT } from "../i18n";
import { openExternal } from "../lib/openExternal";

const OPENAI_PRIVACY = "https://openai.com/policies/privacy-policy";
const OPENAI_KEYS = "https://platform.openai.com/api-keys";

interface PrivacyPolicyProps {
  compact?: boolean;
}

export function PrivacyPolicy({ compact = false }: PrivacyPolicyProps) {
  const t = useT();
  return (
    <div className={compact ? "privacy-body is-compact" : "privacy-body"}>
      <section>
        <h3>{t("privacy.whatTitle")}</h3>
        <p>
          {t("privacy.whatBody")}
        </p>
      </section>
      <section>
        <h3>{t("privacy.localTitle")}</h3>
        <p>
          {t("privacy.localBody")}
        </p>
      </section>
      <section>
        <h3>{t("privacy.openaiTitle")}</h3>
        <p>
          {t("privacy.openaiBody")}
        </p>
        <p>
          <button type="button" className="text-link" onClick={() => void openExternal(OPENAI_KEYS)}>
            {t("privacy.createKey")}
          </button>
          {" · "}
          <button type="button" className="text-link" onClick={() => void openExternal(OPENAI_PRIVACY)}>
            {t("privacy.openaiPrivacy")}
          </button>
        </p>
      </section>
      <section>
        <h3>{t("privacy.thirdTitle")}</h3>
        <p>
          {t("privacy.thirdBody")}
        </p>
      </section>
    </div>
  );
}

export function PrivacyLink({ onOpen }: { onOpen: () => void }) {
  const t = useT();
  return (
    <button type="button" className="text-link" onClick={onOpen}>
      {t("privacy.link")}
    </button>
  );
}
