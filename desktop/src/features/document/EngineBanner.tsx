import { useCallback, useEffect, useState } from "react";

import { api } from "../../shared/api/client";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

interface EngineBannerProps {
  /** Muda quando algo pode ter alterado o estado do motor (ex.: ata pulada). */
  revision?: number;
  onOpenSettings?: () => void;
}

/** Motor de IA fora do ar: diz o que está acontecendo e oferece ligar, em vez de um erro técnico. */
export function EngineBanner({ revision = 0, onOpenSettings }: EngineBannerProps) {
  const t = useT();
  const [state, setState] = useState<{ ready: boolean; message: string } | null>(null);
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const check = useCallback(async () => {
    try {
      const status = await api.setupStatus();
      setState({ ready: Boolean(status.summarize_ready), message: status.llm?.message ?? "" });
    } catch {
      setState(null);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check, revision]);

  if (!state || state.ready) return null;

  const start = async () => {
    setStarting(true);
    setFailed(null);
    try {
      const status = await api.startLlm();
      setState({ ready: Boolean(status.summarize_ready), message: status.llm?.message ?? "" });
      if (!status.summarize_ready) setFailed(status.llm?.message || t("engine.notReady"));
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      setFailed(code === "not_installed" ? t("engine.notInstalled") : t("engine.noResponse"));
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="engine-banner" role="status">
      <span className="engine-banner-led" aria-hidden />
      <div className="engine-banner-copy">
        <strong>{t("engine.offTitle")}</strong>
        <small>{failed ?? t("engine.offBody")}</small>
      </div>
      <div className="engine-banner-actions">
        <button type="button" className="button button-primary button-sm" disabled={starting} onClick={() => void start()}>
          <Icon name="spark" size={13} />
          {starting ? t("engine.starting") : t("engine.start")}
        </button>
        {onOpenSettings ? (
          <button type="button" className="button button-quiet button-sm" onClick={onOpenSettings}>
            {t("engine.settings")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
