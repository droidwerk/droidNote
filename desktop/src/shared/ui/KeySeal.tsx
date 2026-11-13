import { useT } from "../i18n";
import { openExternal } from "../lib/openExternal";
import { SECRETS_SOURCE } from "../lib/whatsNew";
import { Icon } from "./Icon";

/** A cifra DPAPI só existe no Windows; fora dele o selo seria falso. */
const ON_WINDOWS = typeof navigator !== "undefined" && /Windows/i.test(navigator.userAgent);

/** Selo da chave da OpenAI: onde ela fica e para onde vai. Texto conferido com backend/app/core/secrets.py. */
export function KeySeal() {
  const t = useT();
  if (!ON_WINDOWS) return null;
  return (
    <div className="key-seal">
      <Icon name="shield" size={18} />
      <p>
        {t("keySeal.text")}{" "}
        <button type="button" className="text-link" onClick={() => void openExternal(SECRETS_SOURCE)}>
          {t("keySeal.link")}
        </button>
      </p>
    </div>
  );
}
