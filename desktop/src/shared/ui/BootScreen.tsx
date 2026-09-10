import { useT } from "../i18n";
import { BrandLockup, SiteCredit } from "./Brand";
import { Button } from "./primitives";

interface BootScreenProps {
  message: string;
  error?: string | null;
  onRetry?: () => void;
}

export function BootScreen({ message, error, onRetry }: BootScreenProps) {
  const t = useT();
  return (
    <main className="boot">
      <section className="boot-panel">
        <BrandLockup size="splash" />
        {error ? (
          <div className="boot-actions">
            <p className="boot-error">{error}</p>
            {onRetry ? (
              <Button variant="primary" onClick={onRetry}>
                {t("common.retry")}
              </Button>
            ) : null}
          </div>
        ) : (
          <>
            <div className="boot-loading">
              <div className="boot-track" aria-hidden>
                <span />
              </div>
              <p className="boot-status">
                <span aria-hidden />
                {message}
              </p>
            </div>
          </>
        )}
      </section>
      <SiteCredit className="boot-credit" />
    </main>
  );
}
