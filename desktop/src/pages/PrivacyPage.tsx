import { Card, PageHeader } from "../shared/ui/primitives";
import { PrivacyPolicy } from "../shared/ui/PrivacyPolicy";

export function PrivacyPage() {
  return (
    <div className="container about-page">
      <PageHeader
        eyebrow="Uso e privacidade"
        title={<h1>Política de uso e privacidade</h1>}
        description="Um único aviso para o que fica neste PC, o que pode ir para a OpenAI e o que você precisa autorizar."
      />
      <Card className="privacy-card">
        <PrivacyPolicy />
      </Card>
    </div>
  );
}
