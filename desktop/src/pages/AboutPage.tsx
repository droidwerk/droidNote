import { useEffect, useState } from "react";

import { Card } from "../shared/ui/primitives";
import { PrivacyLink } from "../shared/ui/PrivacyPolicy";
import { SiteCredit } from "../shared/ui/Brand";

interface AboutPageProps {
  onOpenPrivacy?: () => void;
}

export function AboutPage({ onOpenPrivacy }: AboutPageProps) {
  const [version, setVersion] = useState("1.0.0");

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
          <h2>Processamento sob seu controle</h2>
          <p>Sem conta obrigatória, sem bot convidado no Meet, Teams ou Zoom.</p>
          <p className="muted">
            No modo Modelos locais, áudio e texto não deixam a máquina. Com a API OpenAI ligada,
            trechos de áudio e texto são enviados para processamento, mesmo sem salvar o WAV.{" "}
            {onOpenPrivacy ? <PrivacyLink onOpen={onOpenPrivacy} /> : null}
          </p>
        </div>
      </Card>
      <Card className="about-footer" tone="quiet">
        <div>
          <h2>Atualizações e dados</h2>
          <p>
            Instale uma versão nova por cima da atual. Notas, gravações e modelos ficam em
            %APPDATA%\DroidNote. Esta versão não atualiza automaticamente.
          </p>
          <p className="muted">DroidNote {version}</p>
        </div>
        <div className="about-product">
          <span className="muted">Produto DroidWerk</span>
          <SiteCredit />
        </div>
      </Card>
    </div>
  );
}
