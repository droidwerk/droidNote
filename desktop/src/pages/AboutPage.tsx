import { Card, PageHeader } from "../shared/ui/primitives";
import { PrivacyLink } from "../shared/ui/PrivacyPolicy";
import { SiteCredit } from "../shared/ui/Brand";

interface AboutPageProps {
  onOpenPrivacy?: () => void;
}

export function AboutPage({ onOpenPrivacy }: AboutPageProps) {
  return (
    <div className="container about-page">
      <PageHeader
        eyebrow="DroidNote"
        title={<h1>Conversas viram clareza.</h1>}
        description="Um espaço privado para capturar, transcrever e transformar o que foi dito em notas úteis."
      />
      <Card className="about-hero">
        <span className="about-icon" aria-hidden>
          ◎
        </span>
        <div>
          <p className="pretitle">Privacidade por padrão</p>
          <h2>Suas gravações ficam neste PC</h2>
          <p>Sem conta obrigatória, sem bot convidado no Meet, Teams ou Zoom.</p>
          <p className="muted">
            O WAV local é opcional e pode ser desligado em Preferências. Se a API OpenAI estiver ligada,
            o trecho ainda pode ir para a OpenAI mesmo sem WAV local.{" "}
            {onOpenPrivacy ? <PrivacyLink onOpen={onOpenPrivacy} /> : null}
          </p>
        </div>
      </Card>
      <div className="about-grid">
        <Card tone="quiet">
          <span className="about-number">01</span>
          <h3>Capture</h3>
          <p className="muted">Ditado, aula ou reunião — microfone e áudio do sistema no formato certo.</p>
        </Card>
        <Card tone="quiet">
          <span className="about-number">02</span>
          <h3>Revise</h3>
          <p className="muted">Falantes, trechos e a nota gerada sempre editáveis.</p>
        </Card>
        <Card tone="quiet">
          <span className="about-number">03</span>
          <h3>Exporte</h3>
          <p className="muted">PDF, DOCX ou Markdown da nota e da transcrição.</p>
        </Card>
      </div>
      <Card className="about-footer" tone="quiet">
        <span className="muted">Atualizar o DroidNote</span>
        <p>
          Instale o Setup novo por cima do atual, sem desinstalar. Notas, gravações e modelos ficam em
          %APPDATA%\DroidNote. Não há atualização automática nesta versão.
        </p>
        <span className="muted">Um produto</span>
        <SiteCredit />
      </Card>
    </div>
  );
}
