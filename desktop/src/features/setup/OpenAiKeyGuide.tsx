import { useState } from "react";

import { useT } from "../../shared/i18n";
import { openExternal } from "../../shared/lib/openExternal";
import { Icon } from "../../shared/ui/Icon";
import { Button } from "../../shared/ui/primitives";

const PLATFORM = "https://platform.openai.com/";
const BILLING = "https://platform.openai.com/settings/organization/billing/overview";
const KEYS = "https://platform.openai.com/api-keys";

interface OpenAiKeyGuideProps {
  /** Aberto de saída (no assistente de primeira configuração, por exemplo). */
  defaultOpen?: boolean;
}

/** Passo a passo para quem nunca criou uma chave da OpenAI: conta, cobrança, chave, colar e testar. */
export function OpenAiKeyGuide({ defaultOpen = false }: OpenAiKeyGuideProps) {
  const t = useT();
  const [open, setOpen] = useState(defaultOpen);
  const steps = [t("keyGuide.step1"), t("keyGuide.step2"), t("keyGuide.step3"), t("keyGuide.step4"), t("keyGuide.step5")];
  return (
    <div className={open ? "key-guide is-open" : "key-guide"}>
      <button type="button" className="key-guide-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <Icon name={open ? "collapse" : "expand"} size={14} />
        {open ? t("keyGuide.hide") : t("keyGuide.show")}
      </button>
      {open ? (
        <div className="key-guide-body">
          <h4>{t("keyGuide.title")}</h4>
          <p>{t("keyGuide.intro")}</p>
          <ol>
            {steps.map((step, index) => (
              <li key={index}>
                <span className="key-guide-num" aria-hidden>
                  {index + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <div className="row">
            <Button size="sm" onClick={() => void openExternal(PLATFORM)}>
              {t("keyGuide.openPlatform")}
            </Button>
            <Button size="sm" onClick={() => void openExternal(BILLING)}>
              {t("keyGuide.openBilling")}
            </Button>
            <Button size="sm" onClick={() => void openExternal(KEYS)}>
              {t("keyGuide.openKeys")}
            </Button>
          </div>
          <p className="key-guide-note">{t("keyGuide.cost")}</p>
          <p className="key-guide-note">
            <Icon name="shield" size={13} />
            {t("keyGuide.safety")}
          </p>
        </div>
      ) : null}
    </div>
  );
}
