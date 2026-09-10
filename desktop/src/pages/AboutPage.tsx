import { useEffect, useState } from "react";

import { useT } from "../shared/i18n";
import { Card } from "../shared/ui/primitives";
import { PrivacyLink } from "../shared/ui/PrivacyPolicy";
import { SiteCredit } from "../shared/ui/Brand";

interface AboutPageProps {
  onOpenPrivacy?: () => void;
}

export function AboutPage({ onOpenPrivacy }: AboutPageProps) {
  const t = useT();
  const [version, setVersion] = useState("2.1.0");

  useEffect(() => {
    void import("@tauri-apps/api/app")
      .then(({ getVersion }) => getVersion())
      .then(setVersion)
      .catch(() => undefined);
  }, []);

  return (
    <div className="about-embed">
      <Card className="about-hero">
        <div>
          <h2>{t("about.controlTitle")}</h2>
          <p>{t("about.controlBody")}</p>
          <p className="muted">
            {t("about.controlHint")}{" "}
            {onOpenPrivacy ? <PrivacyLink onOpen={onOpenPrivacy} /> : null}
          </p>
        </div>
      </Card>
      <Card className="about-footer" tone="quiet">
        <div>
          <h2>{t("about.updatesTitle")}</h2>
          <p>
            {t("about.updatesBody")}
          </p>
          <p className="muted">DroidNote {version}</p>
        </div>
        <div className="about-product">
          <span className="muted">{t("about.product")}</span>
          <SiteCredit />
        </div>
      </Card>
    </div>
  );
}
