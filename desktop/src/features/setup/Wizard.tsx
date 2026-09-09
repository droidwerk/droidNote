import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../shared/api/client";
import type { ModelOption, SetupPlan, SetupStatus } from "../../shared/api/types";
import { openExternal } from "../../shared/lib/openExternal";
import { BrandLockup, SiteCredit } from "../../shared/ui/Brand";
import { PrivacyPolicy } from "../../shared/ui/PrivacyPolicy";
import { Button, Card, ProgressBar } from "../../shared/ui/primitives";
import { StatusGlyph } from "../../shared/ui/ModelSelect";

interface WizardProps {
  onDone: () => void;
}

type Step = "welcome" | "path" | "inventory" | "apikey" | "consent" | "install" | "ready";
type ProviderChoice = "neste_pc" | "openai";

const OPENAI_KEYS = "https://platform.openai.com/api-keys";

export function Wizard({ onDone }: WizardProps) {
  const [step, setStep] = useState<Step>("welcome");
  const [plan, setPlan] = useState<SetupPlan | null>(null);
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [provider, setProvider] = useState<ProviderChoice>("neste_pc");
  const [noteModel, setNoteModel] = useState("");
  const [whisperModel, setWhisperModel] = useState("");
  const [saveRecordings, setSaveRecordings] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [keyMessage, setKeyMessage] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bootstrapStarted = useRef(false);

  useEffect(() => {
    void api.setupPlan().then((next) => {
      setPlan(next);
      setNoteModel(next.suggested_note_model || next.current_note_model);
      setWhisperModel(next.suggested_whisper_model || next.current_whisper_model);
      setSaveRecordings(next.save_recordings);
    }).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Não foi possível ler o plano de instalação");
    });
  }, []);

  useEffect(() => {
    if (step !== "install" && step !== "ready") return undefined;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await api.setupStatus();
        setStatus(next);
        if (next.capture_ready && next.summarize_ready) setStep("ready");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Backend local indisponível");
      }
    };
    void tick();
    timer = window.setInterval(() => void tick(), 1000);
    return () => window.clearInterval(timer);
  }, [step]);

  const installedNotes = useMemo(
    () => (plan?.ollama ?? []).filter((item) => item.installed),
    [plan],
  );
  const installedWhisper = useMemo(
    () => (plan?.whisper ?? []).filter((item) => item.installed),
    [plan],
  );
  const recommendedNote = plan?.ollama.find((item) => item.id === plan.suggested_note_model);
  const recommendedWhisper = plan?.whisper.find((item) => item.id === plan.suggested_whisper_model);
  const selectedNote = plan?.ollama.find((item) => item.id === noteModel);
  const selectedWhisper = plan?.whisper.find((item) => item.id === whisperModel);
  const neededGb = plan
    ? plannedDownloadGb(plan, noteModel, whisperModel, provider === "neste_pc")
    : 0;
  const diskBlocked = plan ? diskBlocks(plan, neededGb) : false;

  const startLocalInstall = async () => {
    setError(null);
    bootstrapStarted.current = true;
    await api.bootstrap({
      provider: "neste_pc",
      ollama_model: noteModel,
      whisper_model: whisperModel,
      save_recordings: saveRecordings,
    });
    setStep("install");
  };

  const startCloud = async () => {
    setError(null);
    const tested = await api.testApiKey(apiKey.trim());
    if (!tested.ok) {
      setKeyMessage(tested.message);
      setError(tested.message);
      return;
    }
    await api.saveSettings({
      provider: "openai",
      asr_api_key: apiKey.trim(),
      save_recordings: saveRecordings,
      openai_disclaimer_accepted: true,
    });
    await api.bootstrap({ provider: "openai", save_recordings: saveRecordings });
    setStep("install");
  };

  const acceptAndContinue = async () => {
    setError(null);
    await api.acceptDisclaimer(provider === "openai" ? "openai" : "local");
    if (provider === "openai") {
      await startCloud();
      return;
    }
    await startLocalInstall();
  };

  const steps = provider === "openai"
    ? ["Bem-vindo", "Caminho", "Chave", "Consentimento"]
    : ["Bem-vindo", "Caminho", "O que instala", "Consentimento"];
  const stepIndex =
    step === "welcome" ? 0
      : step === "path" ? 1
        : step === "inventory" || step === "apikey" ? 2
          : step === "consent" ? 3
            : 3;

  return (
    <main className="wizard">
      <div className="wizard-intro">
        <BrandLockup size="wizard" />
        <h1>Configurar o DroidNote</h1>
        <p className="muted">
          Escolha onde processar áudio e notas. O app mostra cada download antes de instalar.
        </p>
        {step !== "install" && step !== "ready" ? (
          <div className="wizard-steps wizard-steps-4" aria-label={`Etapa ${stepIndex + 1} de 4`}>
            {steps.map((label, index) => (
              <span key={label} className={index <= stepIndex ? "is-active" : ""}>
                {String(index + 1).padStart(2, "0")} <small>{label}</small>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {step === "welcome" ? (
        <Card className="wizard-card">
          <h2>Antes de começar</h2>
          <ul className="wizard-checklist">
            <li>Capture o microfone e, se quiser, o áudio de outros aplicativos.</li>
            <li>Revise a transcrição e identifique os falantes.</li>
            <li>Gere uma nota para ditado, aula ou reunião.</li>
          </ul>
          <div className="row">
            <Button variant="primary" onClick={() => setStep("path")}>Começar</Button>
          </div>
        </Card>
      ) : null}

      {step === "path" ? (
        <Card className="wizard-card">
          <h2>Onde processar</h2>
          <div className="wizard-choice-grid">
            <button
              type="button"
              className={provider === "neste_pc" ? "wizard-choice is-selected" : "wizard-choice"}
              onClick={() => setProvider("neste_pc")}
            >
              <span className="choice-label">Recomendado</span>
              <strong>Modelos locais</strong>
              <p>Áudio e texto ficam aqui. O app pode baixar um motor de transcrição e um motor de notas.</p>
            </button>
            <button
              type="button"
              className={provider === "openai" ? "wizard-choice is-selected" : "wizard-choice"}
              onClick={() => setProvider("openai")}
            >
              <span className="choice-label">Requer chave própria</span>
              <strong>API OpenAI</strong>
              <p>Mais preciso, mas o áudio da transcrição e o texto da nota saem deste PC para a OpenAI.</p>
            </button>
          </div>
          <div className="row">
            <Button onClick={() => setStep("welcome")}>Voltar</Button>
            <Button
              variant="primary"
              onClick={() => setStep(provider === "openai" ? "apikey" : "inventory")}
            >
              Continuar
            </Button>
          </div>
        </Card>
      ) : null}

      {step === "inventory" && !plan ? (
        <Card className="wizard-card">
          <p className="muted">Lendo o que já existe neste computador…</p>
        </Card>
      ) : null}

      {step === "inventory" && plan ? (
        <Card className="wizard-card">
          <h2>Instalação local</h2>
          <InstallBill
            plan={plan}
            provider="neste_pc"
            noteModel={noteModel}
            whisperModel={whisperModel}
          />
          <p className="wizard-ram">
            Memória detectada: <strong>{plan.ram_gb > 0 ? `${plan.ram_gb.toFixed(0)} GB livres` : "não detectada"}</strong>
            {plan.vram_gb && plan.vram_gb > 0 ? <> · GPU com <strong>{plan.vram_gb.toFixed(1)} GB</strong></> : null}.
            Recomendamos <strong>{humanModel(plan.suggested_note_model)}</strong> para notas e{" "}
            <strong>{humanWhisper(plan.suggested_whisper_model)}</strong> para transcrição.
          </p>

          <ModelDecision
            title="Motor de notas"
            installed={installedNotes}
            recommended={recommendedNote}
            selectedId={noteModel}
            onSelect={setNoteModel}
            options={plan.ollama}
            missingCopy={`Não identificamos ${humanModel(plan.suggested_note_model)} neste computador. Você aceita instalar de repositórios confiáveis (Ollama)?`}
            foundCopy="Identificamos que você já tem modelos neste computador. Deseja seguir com um deles ou instalar o recomendado?"
          />

          <ModelDecision
            title="Motor de transcrição"
            installed={installedWhisper}
            recommended={recommendedWhisper}
            selectedId={whisperModel}
            onSelect={setWhisperModel}
            options={plan.whisper}
            missingCopy={`Não identificamos o modelo ${humanWhisper(plan.suggested_whisper_model)} neste computador. Você aceita baixá-lo do Hugging Face (Systran / faster-whisper)?`}
            foundCopy="Identificamos um modelo de transcrição neste computador. Deseja seguir com ele ou baixar o recomendado?"
          />

          {!plan.ollama_binary ? (
            <p className="legal">
              Também vamos instalar o Ollama, o programa que roda o motor de notas neste PC.{" "}
              <button type="button" className="text-link" onClick={() => void openExternal("https://ollama.com")}>
                Saiba mais
              </button>
            </p>
          ) : null}

          <label className="check-control">
            <input
              type="checkbox"
              checked={saveRecordings}
              onChange={(event) => setSaveRecordings(event.target.checked)}
            />
            <span className="check-box" aria-hidden />
            <span>
              <strong>Guardar o áudio em WAV neste PC</strong>
              <small>Você pode desligar isso depois em Preferências. Não muda o envio à OpenAI, se essa opção estiver ligada.</small>
            </span>
          </label>

          <p className="muted">
            Selecionado agora: {humanModel(selectedNote?.id || noteModel)}
            {selectedNote?.installed ? " (já neste PC)" : " (será baixado)"} ·{" "}
            {humanWhisper(selectedWhisper?.id || whisperModel)}
            {selectedWhisper?.installed ? " (já neste PC)" : " (será baixado)"}.
            {neededGb > 0 ? ` Download estimado: ${neededGb.toFixed(1)} GB` : ""}
            {plan.free_disk_gb && plan.free_disk_gb > 0 ? ` · Livres neste disco: ${plan.free_disk_gb.toFixed(1)} GB` : ""}.
          </p>
          {diskBlocked ? (
            <p className="warning">
              Falta espaço em disco. O DroidNote não vai começar o download. Liberar pelo menos{" "}
              {Math.max(0, (neededGb * (plan.disk_margin ?? 1.2)) - (plan.free_disk_gb ?? 0)).toFixed(1)} GB e
              voltar aqui.
            </p>
          ) : null}
          <div className="row">
            <Button onClick={() => setStep("path")}>Voltar</Button>
            <Button variant="primary" disabled={diskBlocked} onClick={() => setStep("consent")}>Continuar</Button>
          </div>
        </Card>
      ) : null}

      {step === "apikey" ? (
        <Card className="wizard-card">
          <h2>Cole a chave da API OpenAI</h2>
          <p className="muted">
            O DroidNote não cria a chave por você. Se você não sabe como gerar a sua, acesse a página oficial da OpenAI.
          </p>
          <label>
            Chave da API
            <input
              className="search"
              type="password"
              value={apiKey}
              autoComplete="off"
              placeholder="sk-..."
              onChange={(event) => setApiKey(event.target.value)}
            />
          </label>
          <div className="row">
            <Button
              onClick={() => void openExternal(OPENAI_KEYS)}
            >
              Como criar a chave
            </Button>
            <Button
              variant="primary"
              disabled={!apiKey.trim()}
              onClick={async () => {
                setError(null);
                const result = await api.testApiKey(apiKey.trim());
                setKeyMessage(result.message);
                if (!result.ok) setError(result.message);
              }}
            >
              Testar chave
            </Button>
          </div>
          {keyMessage ? <p className="muted">{keyMessage}</p> : null}
          <p className="muted">
            No próximo passo você confirma a política de uso e privacidade. Com a API ligada, áudio e
            texto desta escuta saem deste PC.
          </p>
          <label className="check-control">
            <input
              type="checkbox"
              checked={saveRecordings}
              onChange={(event) => setSaveRecordings(event.target.checked)}
            />
            <span className="check-box" aria-hidden />
            <span>
              <strong>Também guardar o WAV neste PC</strong>
              <small>Mesmo desligado, o trecho de áudio ainda é enviado à OpenAI para transcrever.</small>
            </span>
          </label>
          <div className="row">
            <Button onClick={() => setStep("path")}>Voltar</Button>
            <Button variant="primary" disabled={!apiKey.trim()} onClick={() => setStep("consent")}>
              Continuar
            </Button>
          </div>
        </Card>
      ) : null}

      {step === "consent" ? (
        <Card className="wizard-card">
          <h2>Política de uso e privacidade</h2>
          <PrivacyPolicy compact />
          {plan ? (
            <InstallBill
              plan={plan}
              provider={provider}
              noteModel={noteModel}
              whisperModel={whisperModel}
            />
          ) : null}
          {provider === "openai" ? (
            <label className="check-control">
              <input
                type="checkbox"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span className="check-box" aria-hidden />
              <span>
                <strong>Li a política de uso e privacidade</strong>
                <small>Áudio e texto desta escuta podem ir para a OpenAI. Posso revogar a chave depois em Preferências.</small>
              </span>
            </label>
          ) : (
            <p className="muted">
              No próximo passo o app baixa só o que você confirmou
              {neededGb > 0 ? ` (cerca de ${neededGb.toFixed(1)} GB)` : ""}.
            </p>
          )}
          {diskBlocked ? (
            <p className="warning">
              Falta espaço em disco. O DroidNote não vai começar o download. Liberar espaço e tentar de novo.
            </p>
          ) : null}
          <div className="row">
            <Button onClick={() => setStep(provider === "openai" ? "apikey" : "inventory")}>Voltar</Button>
            <Button
              variant="primary"
              disabled={(provider === "openai" && !consent) || diskBlocked}
              onClick={() => void acceptAndContinue()}
            >
              Entendi, instalar
            </Button>
          </div>
        </Card>
      ) : null}

      {step === "install" ? (
        <Card className="wizard-card">
          <h2>{provider === "openai" ? "Conectando a API" : "Preparando a máquina"}</h2>
          <div className="setup-progress-item">
            <div><strong>Transcrição</strong><span>{status?.whisper.message || "Preparando"}</span></div>
            <ProgressBar value={status?.whisper.progress ?? 0} />
          </div>
          <div className="setup-progress-item">
            <div><strong>Notas</strong><span>{status?.llm.message || "Preparando"}</span></div>
            <ProgressBar value={status?.llm.progress ?? 0} />
          </div>
          {status?.whisper.status === "error" || status?.llm.status === "error" ? (
            <div className="row">
              <p className="warning">{status.whisper.status === "error" ? status.whisper.message : status.llm.message}</p>
              <Button variant="primary" onClick={() => void acceptAndContinue()}>Tentar de novo</Button>
            </div>
          ) : null}
          {status && !status.audio_ok ? (
            <p className="warning">{status.audio_message || "Nenhum microfone detectado."}</p>
          ) : null}
        </Card>
      ) : null}

      {step === "ready" ? (
        <Card className="wizard-card wizard-success">
          <h2>DroidNote pronto</h2>
          <p>
            {status?.audio_ok
              ? "Microfone encontrado. Escolha o tipo de captura (ditado, aula ou reunião) na tela ao vivo."
              : status?.audio_message || "Verifique as permissões de microfone do Windows."}
          </p>
          <Button
            variant="primary"
            disabled={!status?.capture_ready || !status?.summarize_ready}
            onClick={onDone}
          >
            Começar a usar
          </Button>
        </Card>
      ) : null}

      {error ? <p className="warning">{error}</p> : null}
      <SiteCredit className="wizard-credit" />
    </main>
  );
}

function InstallBill({
  plan,
  provider,
  noteModel,
  whisperModel,
}: {
  plan: SetupPlan;
  provider: ProviderChoice;
  noteModel: string;
  whisperModel: string;
}) {
  const note = plan.ollama.find((item) => item.id === noteModel);
  const whisper = plan.whisper.find((item) => item.id === whisperModel);
  const local = provider === "neste_pc";
  return (
    <ul className="wizard-bom">
      <li>
        <strong>DroidNote</strong>
        <span>Já neste PC — veio no Setup</span>
      </li>
      <li>
        <strong>WebView2</strong>
        <span>O Setup instala se o Windows ainda não tiver</span>
      </li>
      {local ? (
        <>
          <li>
            <strong>Ollama</strong>
            <span>{plan.ollama_binary ? "Já neste PC" : "Será baixado e instalado (ollama.com)"}</span>
          </li>
          <li>
            <strong>Motor de notas</strong>
            <span>
              {humanModel(note?.id || noteModel)}
              {note?.installed ? " — já neste PC" : " — será baixado"}
            </span>
          </li>
          <li>
            <strong>Motor de transcrição</strong>
            <span>
              {humanWhisper(whisper?.id || whisperModel)}
              {whisper?.installed ? " — já neste PC" : " — será baixado (Hugging Face)"}
            </span>
          </li>
          <li>
            <strong>Internet</strong>
            <span>Precisa nesta primeira configuração para baixar o que falta</span>
          </li>
        </>
      ) : (
        <>
          <li>
            <strong>API OpenAI</strong>
            <span>Sua chave. Sem download de modelos neste PC</span>
          </li>
          <li>
            <strong>Internet</strong>
            <span>Precisa para transcrever e gerar a nota</span>
          </li>
        </>
      )}
    </ul>
  );
}

function ModelDecision({
  title,
  installed,
  recommended,
  selectedId,
  onSelect,
  options,
  missingCopy,
  foundCopy,
}: {
  title: string;
  installed: ModelOption[];
  recommended?: ModelOption;
  selectedId: string;
  onSelect: (id: string) => void;
  options: ModelOption[];
  missingCopy: string;
  foundCopy: string;
}) {
  const recommendedInstalled = Boolean(recommended?.installed);
  return (
    <section className="wizard-model-block">
      <h3>{title}</h3>
      {installed.length ? (
        <p>{recommendedInstalled ? `Identificamos ${recommended?.label ?? selectedId} neste computador.` : foundCopy}</p>
      ) : (
        <p>{missingCopy}</p>
      )}
      <div className="wizard-model-list">
        {options.slice(0, 6).map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === selectedId ? "wizard-model-chip is-selected" : "wizard-model-chip"}
            onClick={() => onSelect(item.id)}
          >
            <strong>{item.label}</strong>
            <small className="wizard-model-status">
              <StatusGlyph installed={item.installed} />
              {item.id === recommended?.id ? "recomendado" : item.installed ? "neste PC" : "baixar"}
            </small>
          </button>
        ))}
      </div>
      {recommended?.learn_more ? (
        <button type="button" className="text-link" onClick={() => void openExternal(recommended.learn_more ?? "")}>
          Saiba mais sobre o modelo
        </button>
      ) : null}
    </section>
  );
}

function humanModel(id: string): string {
  if (!id) return "o modelo de notas";
  return id;
}

function humanWhisper(id: string): string {
  if (!id) return "o modelo de transcrição";
  return `Whisper ${id}`;
}

function plannedDownloadGb(
  plan: SetupPlan,
  noteId: string,
  whisperId: string,
  local: boolean,
): number {
  if (!local) return 0;
  let total = 0;
  if (!plan.ollama_binary) total += plan.ollama_installer_gb ?? 1.5;
  const note = plan.ollama.find((item) => item.id === noteId);
  if (!note?.installed) total += plan.ollama_download_gb?.[noteId] ?? 5;
  const whisper = plan.whisper.find((item) => item.id === whisperId);
  if (!whisper?.installed) total += plan.whisper_download_gb?.[whisperId] ?? 2;
  return total;
}

function diskBlocks(plan: SetupPlan, neededGb: number): boolean {
  const free = plan.free_disk_gb ?? 0;
  if (free <= 0 || neededGb <= 0) return false;
  return free < neededGb * (plan.disk_margin ?? 1.2);
}
