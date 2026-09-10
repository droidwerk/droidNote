import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../shared/api/client";
import type { ModelOption, SetupPlan, SetupStatus } from "../../shared/api/types";
import { LanguagePicker, useI18n } from "../../shared/i18n";
import type { TranslateFn } from "../../shared/i18n/I18nProvider";
import { openExternal } from "../../shared/lib/openExternal";
import { AppVersion, BrandLockup, SiteCredit } from "../../shared/ui/Brand";
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
  const { locale, t } = useI18n();
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
      setError(err instanceof Error ? err.message : t("wizard.planFail"));
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
        setError(err instanceof Error ? err.message : t("wizard.backendDown"));
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

  const persistLanguages = async () => {
    await api.saveSettings({ ui_language: locale, language: locale });
  };

  const startLocalInstall = async () => {
    setError(null);
    bootstrapStarted.current = true;
    await persistLanguages();
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
      ui_language: locale,
      language: locale,
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
    ? [t("wizard.stepWelcome"), t("wizard.stepPath"), t("wizard.stepKey"), t("wizard.stepConsent")]
    : [t("wizard.stepWelcome"), t("wizard.stepPath"), t("wizard.stepInventory"), t("wizard.stepConsent")];
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
        <h1>{t("wizard.title")}</h1>
        <p className="muted">{t("wizard.subtitle")}</p>
        {step !== "install" && step !== "ready" ? (
          <div className="wizard-steps wizard-steps-4" aria-label={t("wizard.stepOf", { current: stepIndex + 1 })}>
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
          <h2>{t("languages.uiLabel")}</h2>
          <p className="muted">{t("languages.uiHelp")}</p>
          <LanguagePicker compact />
          <h2>{t("wizard.beforeTitle")}</h2>
          <ul className="wizard-checklist">
            <li>{t("wizard.check1")}</li>
            <li>{t("wizard.check2")}</li>
            <li>{t("wizard.check3")}</li>
          </ul>
          <div className="row">
            <Button variant="primary" onClick={() => setStep("path")}>{t("wizard.start")}</Button>
          </div>
        </Card>
      ) : null}

      {step === "path" ? (
        <Card className="wizard-card">
          <h2>{t("wizard.whereTitle")}</h2>
          <div className="wizard-choice-grid">
            <button
              type="button"
              className={provider === "neste_pc" ? "wizard-choice is-selected" : "wizard-choice"}
              onClick={() => setProvider("neste_pc")}
            >
              <span className="choice-label">{t("common.recommended")}</span>
              <strong>{t("wizard.localTitle")}</strong>
              <p>{t("wizard.localBody")}</p>
            </button>
            <button
              type="button"
              className={provider === "openai" ? "wizard-choice is-selected" : "wizard-choice"}
              onClick={() => setProvider("openai")}
            >
              <span className="choice-label">{t("wizard.openaiBadge")}</span>
              <strong>{t("wizard.openaiTitle")}</strong>
              <p>{t("wizard.openaiBody")}</p>
            </button>
          </div>
          <div className="row">
            <Button onClick={() => setStep("welcome")}>{t("common.back")}</Button>
            <Button
              variant="primary"
              onClick={() => setStep(provider === "openai" ? "apikey" : "inventory")}
            >
              {t("common.continue")}
            </Button>
          </div>
        </Card>
      ) : null}

      {step === "inventory" && !plan ? (
        <Card className="wizard-card">
          <p className="muted">{t("wizard.readingPlan")}</p>
        </Card>
      ) : null}

      {step === "inventory" && plan ? (
        <Card className="wizard-card">
          <h2>{t("wizard.localInstall")}</h2>
          <InstallBill
            plan={plan}
            provider="neste_pc"
            noteModel={noteModel}
            whisperModel={whisperModel}
            t={t}
          />
          <p className="wizard-ram">
            {t("wizard.ramDetected")}{" "}
            <strong>{plan.ram_gb > 0 ? t("wizard.ramFree", { gb: plan.ram_gb.toFixed(0) }) : t("wizard.ramUnknown")}</strong>
            {plan.vram_gb && plan.vram_gb > 0 ? <> · {t("wizard.gpuWith", { gb: plan.vram_gb.toFixed(1) })}</> : null}.
            {t("wizard.recommend", {
              note: humanModel(plan.suggested_note_model, t),
              whisper: humanWhisper(plan.suggested_whisper_model, t),
            })}
          </p>

          <ModelDecision
            title={t("wizard.notesEngine")}
            installed={installedNotes}
            recommended={recommendedNote}
            selectedId={noteModel}
            onSelect={setNoteModel}
            options={plan.ollama}
            missingCopy={t("wizard.missingNote", { model: humanModel(plan.suggested_note_model, t) })}
            foundCopy={t("wizard.foundNotes")}
            t={t}
          />

          <ModelDecision
            title={t("wizard.asrEngine")}
            installed={installedWhisper}
            recommended={recommendedWhisper}
            selectedId={whisperModel}
            onSelect={setWhisperModel}
            options={plan.whisper}
            missingCopy={t("wizard.missingWhisper", { model: humanWhisper(plan.suggested_whisper_model, t) })}
            foundCopy={t("wizard.foundWhisper")}
            t={t}
          />

          {!plan.ollama_binary ? (
            <p className="legal">
              {t("wizard.installOllama")}{" "}
              <button type="button" className="text-link" onClick={() => void openExternal("https://ollama.com")}>
                {t("common.learnMore")}
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
              <strong>{t("wizard.saveWavTitle")}</strong>
              <small>{t("wizard.saveWavHint")}</small>
            </span>
          </label>

          <p className="muted">
            {t("wizard.selectedNow")} {humanModel(selectedNote?.id || noteModel, t)}
            {selectedNote?.installed ? ` ${t("wizard.alreadyHere")}` : ` ${t("wizard.willBeDownloaded")}`} ·{" "}
            {humanWhisper(selectedWhisper?.id || whisperModel, t)}
            {selectedWhisper?.installed ? ` ${t("wizard.alreadyHere")}` : ` ${t("wizard.willBeDownloaded")}`}.
            {neededGb > 0 ? ` ${t("wizard.estimatedDownload", { gb: neededGb.toFixed(1) })}` : ""}
            {plan.free_disk_gb && plan.free_disk_gb > 0 ? ` · ${t("wizard.freeDisk", { gb: plan.free_disk_gb.toFixed(1) })}` : ""}.
          </p>
          {diskBlocked ? (
            <p className="warning">
              {t("wizard.diskBlocked", {
                gb: Math.max(0, (neededGb * (plan.disk_margin ?? 1.2)) - (plan.free_disk_gb ?? 0)).toFixed(1),
              })}
            </p>
          ) : null}
          <div className="row">
            <Button onClick={() => setStep("path")}>{t("common.back")}</Button>
            <Button variant="primary" disabled={diskBlocked} onClick={() => setStep("consent")}>{t("common.continue")}</Button>
          </div>
        </Card>
      ) : null}

      {step === "apikey" ? (
        <Card className="wizard-card">
          <h2>{t("wizard.apiTitle")}</h2>
          <p className="muted">
            {t("wizard.apiHint")}
          </p>
          <label>
            {t("wizard.apiKey")}
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
              {t("wizard.howToCreateKey")}
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
              {t("wizard.testKey")}
            </Button>
          </div>
          {keyMessage ? <p className="muted">{keyMessage}</p> : null}
          <p className="muted">
            {t("wizard.nextConsent")}
          </p>
          <label className="check-control">
            <input
              type="checkbox"
              checked={saveRecordings}
              onChange={(event) => setSaveRecordings(event.target.checked)}
            />
            <span className="check-box" aria-hidden />
            <span>
              <strong>{t("wizard.saveWavCloudTitle")}</strong>
              <small>{t("wizard.saveWavCloudHint")}</small>
            </span>
          </label>
          <div className="row">
            <Button onClick={() => setStep("path")}>{t("common.back")}</Button>
            <Button variant="primary" disabled={!apiKey.trim()} onClick={() => setStep("consent")}>
              {t("common.continue")}
            </Button>
          </div>
        </Card>
      ) : null}

      {step === "consent" ? (
        <Card className="wizard-card">
          <h2>{t("wizard.privacyTitle")}</h2>
          <PrivacyPolicy compact />
          {plan ? (
            <InstallBill
              plan={plan}
              provider={provider}
              noteModel={noteModel}
              whisperModel={whisperModel}
              t={t}
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
                <strong>{t("wizard.consentTitle")}</strong>
                <small>{t("wizard.consentHint")}</small>
              </span>
            </label>
          ) : (
            <p className="muted">
              {t("wizard.nextDownload")}
              {neededGb > 0 ? ` ${t("wizard.aboutGb", { gb: neededGb.toFixed(1) })}` : ""}.
            </p>
          )}
          {diskBlocked ? (
            <p className="warning">
              {t("wizard.diskBlockedShort")}
            </p>
          ) : null}
          <div className="row">
            <Button onClick={() => setStep(provider === "openai" ? "apikey" : "inventory")}>{t("common.back")}</Button>
            <Button
              variant="primary"
              disabled={(provider === "openai" && !consent) || diskBlocked}
              onClick={() => void acceptAndContinue()}
            >
              {t("wizard.install")}
            </Button>
          </div>
        </Card>
      ) : null}

      {step === "install" ? (
        <Card className="wizard-card">
          <h2>{provider === "openai" ? t("wizard.connectingApi") : t("wizard.preparingMachine")}</h2>
          <div className="setup-progress-item">
            <div><strong>{t("wizard.transcription")}</strong><span>{status?.whisper.message || t("common.preparing")}</span></div>
            <ProgressBar value={status?.whisper.progress ?? 0} />
          </div>
          <div className="setup-progress-item">
            <div><strong>{t("wizard.notes")}</strong><span>{status?.llm.message || t("common.preparing")}</span></div>
            <ProgressBar value={status?.llm.progress ?? 0} />
          </div>
          {status?.whisper.status === "error" || status?.llm.status === "error" ? (
            <div className="row">
              <p className="warning">{status.whisper.status === "error" ? status.whisper.message : status.llm.message}</p>
              <Button variant="primary" onClick={() => void acceptAndContinue()}>{t("common.retry")}</Button>
            </div>
          ) : null}
          {status && !status.audio_ok ? (
            <p className="warning">{status.audio_message || t("wizard.noMic")}</p>
          ) : null}
        </Card>
      ) : null}

      {step === "ready" ? (
        <Card className="wizard-card wizard-success">
          <h2>{t("wizard.readyTitle")}</h2>
          <p>
            {status?.audio_ok
              ? t("wizard.readyMic")
              : status?.audio_message || t("wizard.checkMic")}
          </p>
          <Button
            variant="primary"
            disabled={!status?.capture_ready || !status?.summarize_ready}
            onClick={onDone}
          >
            {t("wizard.startUsing")}
          </Button>
        </Card>
      ) : null}

      {error ? <p className="warning">{error}</p> : null}
      <div className="wizard-footer">
        <AppVersion />
        <SiteCredit className="wizard-credit" />
      </div>
    </main>
  );
}

function InstallBill({
  plan,
  provider,
  noteModel,
  whisperModel,
  t,
}: {
  plan: SetupPlan;
  provider: ProviderChoice;
  noteModel: string;
  whisperModel: string;
  t: TranslateFn;
}) {
  const note = plan.ollama.find((item) => item.id === noteModel);
  const whisper = plan.whisper.find((item) => item.id === whisperModel);
  const local = provider === "neste_pc";
  return (
    <ul className="wizard-bom">
      <li>
        <strong>DroidNote</strong>
        <span>{t("wizard.billApp")}</span>
      </li>
      <li>
        <strong>WebView2</strong>
        <span>{t("wizard.billWebview")}</span>
      </li>
      {local ? (
        <>
          <li>
            <strong>Ollama</strong>
            <span>{plan.ollama_binary ? t("common.alreadyOnPc") : t("wizard.billOllamaMissing")}</span>
          </li>
          <li>
            <strong>{t("wizard.notesEngine")}</strong>
            <span>
              {humanModel(note?.id || noteModel, t)}
              {note?.installed ? ` — ${t("common.onThisPc")}` : ` — ${t("common.willDownload")}`}
            </span>
          </li>
          <li>
            <strong>{t("wizard.asrEngine")}</strong>
            <span>
              {humanWhisper(whisper?.id || whisperModel, t)}
              {whisper?.installed ? ` — ${t("common.onThisPc")}` : ` — ${t("wizard.billWhisperDownload")}`}
            </span>
          </li>
          <li>
            <strong>{t("wizard.internet")}</strong>
            <span>{t("wizard.billInternetFirst")}</span>
          </li>
        </>
      ) : (
        <>
          <li>
            <strong>{t("wizard.openaiTitle")}</strong>
            <span>{t("wizard.billOpenai")}</span>
          </li>
          <li>
            <strong>{t("wizard.internet")}</strong>
            <span>{t("wizard.billInternetCloud")}</span>
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
  t,
}: {
  title: string;
  installed: ModelOption[];
  recommended?: ModelOption;
  selectedId: string;
  onSelect: (id: string) => void;
  options: ModelOption[];
  missingCopy: string;
  foundCopy: string;
  t: TranslateFn;
}) {
  const recommendedInstalled = Boolean(recommended?.installed);
  return (
    <section className="wizard-model-block">
      <h3>{title}</h3>
      {installed.length ? (
        <p>{recommendedInstalled ? t("wizard.foundRecommended", { model: recommended?.label ?? selectedId }) : foundCopy}</p>
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
              {item.id === recommended?.id ? t("wizard.modelStatusRecommended") : item.installed ? t("common.onThisPc") : t("common.download")}
            </small>
          </button>
        ))}
      </div>
      {recommended?.learn_more ? (
        <button type="button" className="text-link" onClick={() => void openExternal(recommended.learn_more ?? "")}>
          {t("wizard.learnModel")}
        </button>
      ) : null}
    </section>
  );
}

function humanModel(id: string, t: TranslateFn): string {
  if (!id) return t("wizard.defaultNoteModel");
  return id;
}

function humanWhisper(id: string, t: TranslateFn): string {
  if (!id) return t("wizard.defaultWhisperModel");
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
