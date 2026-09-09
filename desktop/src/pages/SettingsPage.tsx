import { useEffect, useState, type KeyboardEvent } from "react";

import { api } from "../shared/api/client";
import type { ModelOption, ModelsCatalog, Person, Settings } from "../shared/api/types";
import { AboutPage } from "./AboutPage";
import { PrivacyPage } from "./PrivacyPage";
import { openLocalPath, saveBlob, parentDirectory } from "../shared/lib/saveFile";
import { useTheme, type Theme } from "../shared/lib/theme";
import { useConfirm } from "../shared/ui/ConfirmDialog";
import { Button, Card, PageHeader, ProgressBar } from "../shared/ui/primitives";
import { ModelSelect, StatusGlyph } from "../shared/ui/ModelSelect";
import { PrivacyLink } from "../shared/ui/PrivacyPolicy";
import { useToast } from "../shared/ui/Toast";

export type SettingsTab =
  | "transcription"
  | "appearance"
  | "people"
  | "files"
  | "privacy"
  | "about";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "transcription", label: "Transcrição" },
  { id: "appearance", label: "Aparência" },
  { id: "people", label: "Pessoas" },
  { id: "files", label: "Arquivos" },
  { id: "privacy", label: "Privacidade" },
  { id: "about", label: "Sobre" },
];

const WHISPER_DEVICE_OPTIONS: ModelOption[] = [
  {
    id: "auto",
    label: "Automático",
    installed: true,
    source: "whisper",
    detail: "GPU se o CUDA estiver completo, senão CPU",
  },
  {
    id: "cpu",
    label: "CPU",
    installed: true,
    source: "whisper",
    detail: "Funciona em qualquer PC Windows",
  },
  {
    id: "cuda",
    label: "GPU NVIDIA",
    installed: true,
    source: "whisper",
    detail: "Só com CUDA 12 / cuBLAS",
  },
];

const THEME_CHOICES: { id: Theme; label: string; blurb: string }[] = [
  { id: "dark", label: "Escuro", blurb: "O padrão do DroidNote." },
  { id: "light", label: "Claro", blurb: "Neutro, para ambientes claros." },
  { id: "paper", label: "Paper white", blurb: "Folha de papel, tinta quente." },
];

interface SettingsPageProps {
  onSaved?: (settings: Settings) => void;
  initialTab?: SettingsTab;
  engineProvider?: Settings["provider"];
}

export function SettingsPage({ onSaved, initialTab = "transcription", engineProvider }: SettingsPageProps) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [baseline, setBaseline] = useState<Settings | null>(null);
  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [newPerson, setNewPerson] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState<{ progress: number; message: string } | null>(
    null,
  );
  const [replacingKey, setReplacingKey] = useState(false);
  const [keyTest, setKeyTest] = useState<string | null>(null);
  const [diagBusy, setDiagBusy] = useState(false);
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  const confirm = useConfirm();
  const toast = useToast();
  const { theme, setTheme } = useTheme();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSettings, nextCatalog, nextPeople] = await Promise.all([
        api.getSettings(),
        api.listModels(),
        api.people(),
      ]);
      setSettings(nextSettings);
      setBaseline(nextSettings);
      setCatalog(nextCatalog);
      setPeople(nextPeople);
      setApiKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao ler preferências");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (engineProvider === "openai") return undefined;
    let cancelled = false;
    const follow = async () => {
      try {
        const first = await api.setupStatus();
        if (cancelled) return;
        const downloading =
          first.whisper.status === "downloading" || first.llm.status === "downloading";
        if (!downloading) return;
        setDownloading(true);
        setDownloadStatus({
          progress:
            first.whisper.status === "downloading" ? first.whisper.progress : first.llm.progress,
          message:
            first.whisper.status === "downloading" ? first.whisper.message : first.llm.message,
        });
        for (;;) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          const status = await api.setupStatus();
          if (cancelled) return;
          const step =
            status.whisper.status === "downloading" || status.whisper.status !== "ready"
              ? status.whisper
              : status.llm;
          setDownloadStatus({ progress: step.progress, message: step.message });
          if (status.whisper.status === "error") {
            setError(status.whisper.message);
            setDownloading(false);
            return;
          }
          if (status.llm.status === "error") {
            setError(status.llm.message);
            setDownloading(false);
            return;
          }
          if (status.whisper.status === "ready" && status.llm.status === "ready") {
            setDownloading(false);
            await load();
            return;
          }
        }
      } catch {
        if (!cancelled) setDownloading(false);
      }
    };
    void follow();
    return () => {
      cancelled = true;
    };
  }, [engineProvider]);

  useEffect(() => {
    if (!engineProvider) return;
    setSettings((current) =>
      current && current.provider !== engineProvider ? { ...current, provider: engineProvider } : current,
    );
    setBaseline((current) =>
      current && current.provider !== engineProvider ? { ...current, provider: engineProvider } : current,
    );
  }, [engineProvider]);

  if (!settings) {
    return (
      <div className="empty-block">
        {error ?? "Carregando preferências…"}
      </div>
    );
  }

  const cloud = settings.provider === "openai";
  const showActions = tab === "transcription" || tab === "people" || tab === "files";

  const persist = async (payload: Partial<Settings> & { asr_api_key?: string }) => {
    const next = await api.saveSettings(payload);
    setSettings(next);
    setBaseline(next);
    setApiKey("");
    setReplacingKey(false);
    setSaved(true);
    onSaved?.(next);
    return next;
  };

  const save = async () => {
    setError(null);
    try {
      if (cloud && !settings.openai_disclaimer_accepted) {
        setError("Confirme o aviso da API OpenAI antes de salvar.");
        return;
      }
      const payload = diffSettings(baseline, settings);
      if (replacingKey || apiKey.trim()) payload.asr_api_key = apiKey.trim();
      await persist(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar");
    }
  };

  const clearKey = async () => {
    setError(null);
    setKeyTest(null);
    try {
      await persist({ asr_api_key: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao remover a chave");
    }
  };

  const testKey = async () => {
    setError(null);
    try {
      const result = await api.testApiKey(apiKey.trim() || undefined);
      setKeyTest(result.ok ? result.message : result.message);
      if (!result.ok) setError(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao testar a chave");
    }
  };

  const downloadModel = async () => {
    setDownloading(true);
    setError(null);
    setDownloadStatus({ progress: 1, message: "Iniciando download…" });
    try {
      await save();
      await api.bootstrap();
      for (;;) {
        const status = await api.setupStatus();
        const step = status.whisper.status === "ready" ? status.llm : status.whisper;
        setDownloadStatus({ progress: step.progress, message: step.message });
        if (status.whisper.status === "error") throw new Error(status.whisper.message);
        if (status.llm.status === "error") throw new Error(status.llm.message);
        if (status.whisper.status === "ready" && status.llm.status === "ready") break;
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao baixar o modelo");
    } finally {
      setDownloading(false);
    }
  };

  const exportDiagnostics = async () => {
    setError(null);
    setDiagBusy(true);
    try {
      const blob = await api.exportDiagnostics();
      const result = await saveBlob(blob, "DroidNote-diagnostico.zip", [
        { name: "Zip", extensions: ["zip"] },
      ]);
      if (result.status === "cancelled") return;
      if (result.status === "error") {
        toast.push({ tone: "error", title: "Falha no diagnóstico", description: result.message });
        return;
      }
      toast.push({
        tone: "success",
        title: "Diagnóstico gravado",
        description: "DroidNote-diagnostico.zip",
        action: result.path
          ? {
              label: "Abrir pasta",
              onClick: () => void openLocalPath(parentDirectory(result.path ?? "")),
            }
          : undefined,
      });
    } catch (err) {
      toast.push({
        tone: "error",
        title: "Falha no diagnóstico",
        description:
          err instanceof Error
            ? err.message
            : "Não deu para exportar o diagnóstico. Tente de novo em Preferências.",
      });
    } finally {
      setDiagBusy(false);
    }
  };

  const addPerson = async () => {
    const name = newPerson.trim();
    if (!name) return;
    const person = await api.createPerson(name);
    setPeople((current) =>
      current.some((item) => item.id === person.id) ? current : [...current, person],
    );
    setNewPerson("");
  };

  const removePerson = async (id: string) => {
    const person = people.find((item) => item.id === id);
    const ok = await confirm({
      title: `Apagar ${person?.name ?? "esta pessoa"}?`,
      confirmLabel: "Apagar",
      tone: "danger",
    });
    if (!ok) return;
    await api.deletePerson(id);
    setPeople((current) => current.filter((item) => item.id !== id));
  };

  const onTabKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = TABS.findIndex((item) => item.id === tab);
    if (index < 0) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setTab(TABS[(index + 1) % TABS.length]?.id ?? tab);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      setTab(TABS[(index - 1 + TABS.length) % TABS.length]?.id ?? tab);
    } else if (event.key === "Home") {
      event.preventDefault();
      setTab(TABS[0]?.id ?? tab);
    } else if (event.key === "End") {
      event.preventDefault();
      setTab(TABS[TABS.length - 1]?.id ?? tab);
    }
  };

  const openPrivacy = () => setTab("privacy");

  return (
    <div className="container settings-page">
      <PageHeader
        title={<h1>Preferências</h1>}
        description="Ajuste captura, inteligência e armazenamento deste computador."
      />
      {error ? <p className="banner">{error}</p> : null}

      <div
        className="settings-tabs"
        role="tablist"
        aria-label="Seções das preferências"
        onKeyDown={onTabKey}
      >
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`settings-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`settings-panel-${item.id}`}
            tabIndex={tab === item.id ? 0 : -1}
            className={tab === item.id ? "on" : ""}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div
        className="settings-stack"
        role="tabpanel"
        id={`settings-panel-${tab}`}
        aria-labelledby={`settings-tab-${tab}`}
      >
        {tab === "transcription" ? (
          <>
            <Card className="settings-card settings-card-wide">
              <h2>Motor</h2>
              <p className="muted">
                A escolha vale para tudo: transcrição e nota saem do mesmo motor, com o mesmo
                prompt. Trocar de motor não troca o formato da nota.
              </p>
              <div className="segmented" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={!cloud}
                  className={!cloud ? "on" : ""}
                  onClick={() => setSettings({ ...settings, provider: "neste_pc" })}
                >
                  Modelos locais — privado
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={cloud}
                  className={cloud ? "on" : ""}
                  onClick={() => setSettings({ ...settings, provider: "openai" })}
                >
                  API OpenAI — mais preciso
                </button>
              </div>

              {cloud ? (
                <label className="check-control">
                  <input
                    type="checkbox"
                    checked={Boolean(settings.openai_disclaimer_accepted)}
                    onChange={(event) =>
                      setSettings({ ...settings, openai_disclaimer_accepted: event.target.checked })
                    }
                  />
                  <span className="check-box" aria-hidden />
                  <span>
                    <strong>Li a política de uso e privacidade</strong>
                    <small>
                      <PrivacyLink onOpen={openPrivacy} />
                      {" · "}
                      Áudio e texto desta escuta podem ir para a OpenAI.
                    </small>
                  </span>
                </label>
              ) : (
                <p className="muted">
                  <PrivacyLink onOpen={openPrivacy} />
                  {" — "}
                  No modo Modelos locais o áudio não deixa a máquina.
                </p>
              )}

              {cloud ? (
                <div className="form-grid">
                  <label>
                    Modelo de transcrição
                    <ModelSelect
                      label="Modelo de transcrição"
                      value={settings.asr_cloud_model ?? "gpt-4o-transcribe"}
                      options={optionsFor(
                        catalog?.asr_cloud ?? [],
                        settings.asr_cloud_model ?? "",
                        "openai",
                      )}
                      onChange={(id) => setSettings({ ...settings, asr_cloud_model: id })}
                      showStatus={false}
                    />
                  </label>
                  <label>
                    Modelo da nota
                    <ModelSelect
                      label="Modelo da nota"
                      value={settings.llm_cloud_model ?? "gpt-4o-mini"}
                      options={optionsFor(
                        catalog?.llm_cloud ?? [],
                        settings.llm_cloud_model ?? "",
                        "openai",
                      )}
                      onChange={(id) => setSettings({ ...settings, llm_cloud_model: id })}
                      showStatus={false}
                    />
                  </label>
                  <label>
                    Chave da API
                    {settings.has_api_key && !replacingKey ? (
                      <div className="api-key-status">
                        <p className="muted">
                          Chave salva neste PC · termina em {settings.api_key_hint}
                        </p>
                        <div className="row">
                          <Button onClick={() => setReplacingKey(true)}>Trocar</Button>
                          <Button variant="danger" onClick={() => void clearKey()}>
                            Remover
                          </Button>
                          <Button onClick={() => void testKey()}>Testar chave</Button>
                        </div>
                        {keyTest ? <p className="muted">{keyTest}</p> : null}
                      </div>
                    ) : (
                      <>
                        <input
                          className="search"
                          type="password"
                          autoComplete="off"
                          placeholder={
                            settings.has_api_key
                              ? `Nova chave · a atual termina em ${settings.api_key_hint}`
                              : "sk-…"
                          }
                          value={apiKey}
                          onChange={(event) => setApiKey(event.target.value)}
                        />
                        <div className="row">
                          <Button onClick={() => void testKey()} disabled={!apiKey.trim() && !settings.has_api_key}>
                            Testar chave
                          </Button>
                          {replacingKey ? (
                            <Button
                              onClick={() => {
                                setReplacingKey(false);
                                setApiKey("");
                              }}
                            >
                              Cancelar
                            </Button>
                          ) : null}
                        </div>
                        {keyTest ? <p className="muted">{keyTest}</p> : null}
                      </>
                    )}
                  </label>
                </div>
              ) : (
                <div className="form-grid">
                  <label>
                    Modelo Whisper
                    <ModelSelect
                      label="Modelo Whisper"
                      value={settings.whisper_model}
                      options={optionsFor(catalog?.whisper ?? [], settings.whisper_model, "whisper")}
                      onChange={(id) => setSettings({ ...settings, whisper_model: id })}
                    />
                  </label>
                  <label>
                    Motor Whisper
                    <ModelSelect
                      label="Motor Whisper"
                      value={settings.whisper_device ?? "auto"}
                      options={WHISPER_DEVICE_OPTIONS}
                      onChange={(id) => setSettings({ ...settings, whisper_device: id })}
                      showStatus={false}
                    />
                  </label>
                  <label>
                    Modelo da nota (Ollama)
                    <ModelSelect
                      label="Modelo da nota"
                      value={settings.ollama_model}
                      options={optionsFor(catalog?.ollama ?? [], settings.ollama_model, "ollama")}
                      onChange={(id) => setSettings({ ...settings, ollama_model: id })}
                    />
                  </label>
                  <p className="model-legend">
                    <span>
                      <StatusGlyph installed />
                      já neste PC
                    </span>
                    <span>
                      <StatusGlyph installed={false} />
                      será baixado
                    </span>
                  </p>
                </div>
              )}

              {cloud ? (
                <p className="banner">
                  O áudio desta escuta sai deste computador e vai para a OpenAI. Use só com
                  consentimento de quem está sendo gravado.{" "}
                  <PrivacyLink onOpen={openPrivacy} />
                </p>
              ) : (
                <>
                  <div className="disclaimer">
                    <h3>O que esperar do motor local</h3>
                    <p>
                      Com modelos locais nada sai da máquina, e é isso que se paga: a transcrição erra mais
                      nomes próprios e fala cruzada, e a nota é mais curta que a da OpenAI. O formato
                      da nota é o mesmo — a profundidade, não.
                    </p>
                    <p className="muted">
                      Para chegar perto da OpenAI: Whisper <strong>large-v3-turbo</strong> na GPU
                      ou <strong>small</strong> na CPU, e <strong>qwen3:8b</strong> ou{" "}
                      <strong>gemma3:12b</strong> na nota. <strong>large-v3</strong> na CPU
                      atrasa a transcrição e perde trechos. Abaixo de 8 GB de RAM livre, fique em{" "}
                      <strong>small</strong> + <strong>qwen3:4b</strong> e espere notas mais rasas.
                    </p>
                  </div>
                  <div className="row">
                    <span className={catalog?.ollama_online ? "badge on" : "badge"}>
                      {catalog?.ollama_online ? "Ollama no ar" : "Ollama offline"}
                    </span>
                    <span className="muted">
                      Whisper instalado: {(catalog?.whisper ?? []).filter((item) => item.installed).length}
                    </span>
                  </div>
                  <div className="tutorial">
                    <h3>Baixar os modelos escolhidos</h3>
                    <p className="muted">
                      Itens com a seta de download são baixados agora — Whisper primeiro, depois o
                      modelo da nota. Modelo maior acerta mais e pesa mais na RAM.
                    </p>
                    <Button onClick={() => void downloadModel()} disabled={downloading}>
                      {downloading ? "Baixando…" : "Baixar os modelos selecionados"}
                    </Button>
                    {downloading || downloadStatus ? (
                      <div className="model-progress">
                        <ProgressBar value={downloadStatus?.progress ?? 0} />
                        <p className="muted">{downloadStatus?.message ?? "Preparando…"}</p>
                      </div>
                    ) : null}
                  </div>
                </>
              )}
            </Card>

            <Card className="settings-card">
              <h2>Idioma da transcrição</h2>
              <label>
                Idioma
                <select
                  className="select"
                  value={settings.language ?? "pt"}
                  onChange={(event) => setSettings({ ...settings, language: event.target.value })}
                >
                  <option value="pt">Português</option>
                  <option value="en">Inglês</option>
                  <option value="es">Espanhol</option>
                  <option value="auto">Detectar automaticamente (pode misturar idiomas)</option>
                </select>
              </label>
              <p className="muted">
                Travar o idioma evita o modelo inventar russo, polonês ou inglês no meio da fala.
                Prefira Português; “detectar automaticamente” mistura idiomas.
              </p>
            </Card>
          </>
        ) : null}

        {tab === "appearance" ? (
          <Card className="settings-card settings-card-wide">
            <h2>Aparência</h2>
            <p className="muted">O tema fica neste computador e vale para todas as telas.</p>
            <div className="theme-grid">
              {THEME_CHOICES.map((choice) => (
                <button
                  key={choice.id}
                  type="button"
                  className={theme === choice.id ? "theme-card is-selected" : "theme-card"}
                  aria-pressed={theme === choice.id}
                  onClick={() => setTheme(choice.id)}
                >
                  <span className={`theme-swatch theme-swatch-${choice.id}`} aria-hidden />
                  <strong>{choice.label}</strong>
                  <span>{choice.blurb}</span>
                </button>
              ))}
            </div>
          </Card>
        ) : null}

        {tab === "people" ? (
          <Card className="settings-card settings-card-people settings-card-wide">
            <h2>Pessoas</h2>
            <p className="muted">
              Cadastre quem costuma aparecer. Na escuta, o microfone vira “Você” e o áudio do
              sistema vira “Outros”. Marque abaixo quem é você.
            </p>
            <label>
              Você (microfone)
              <select
                className="select"
                value={settings.self_person_id ?? ""}
                onChange={(event) =>
                  setSettings({ ...settings, self_person_id: event.target.value })
                }
              >
                <option value="">Ainda não definido</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="people-add">
              <input
                className="search"
                placeholder="Nome"
                value={newPerson}
                onChange={(event) => setNewPerson(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void addPerson();
                  }
                }}
              />
              <Button variant="primary" onClick={() => void addPerson()}>
                Cadastrar
              </Button>
            </div>
            <ul className="people-list">
              {people.length === 0 ? <li className="muted">Ninguém cadastrado ainda.</li> : null}
              {people.map((person) => (
                <li key={person.id}>
                  <span>{person.name}</span>
                  <Button onClick={() => void removePerson(person.id)}>Apagar</Button>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        {tab === "files" ? (
          <>
            <Card className="settings-card settings-card-wide">
              <h2>Arquivos neste PC</h2>
              <p className="muted">
                Banco e modelos ficam na pasta de dados. O WAV de cada escuta só é gravado se a opção abaixo estiver ligada.
              </p>
              <label className="check-control">
                <input
                  type="checkbox"
                  checked={settings.save_recordings !== false}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    const previous = settings.save_recordings;
                    setSettings({ ...settings, save_recordings: checked });
                    void persist({ save_recordings: checked }).catch((err: unknown) => {
                      setSettings({ ...settings, save_recordings: previous });
                      setError(err instanceof Error ? err.message : "Falha ao salvar o áudio WAV");
                    });
                  }}
                />
                <span className="check-box" aria-hidden />
                <span>
                  <strong>Guardar o áudio em WAV neste PC</strong>
                  <small>
                    Desligar vale para a próxima captura. Se a API OpenAI estiver ligada, o trecho ainda vai para a OpenAI mesmo sem WAV local.
                  </small>
                </span>
              </label>
              <label>
                Pasta de dados (banco e modelos)
                <input className="search" value={settings.data_dir ?? ""} readOnly />
              </label>
              <div className="people-add">
                <Button onClick={() => void openLocalPath(settings.data_dir ?? "")}>Abrir pasta de dados</Button>
              </div>
              <label>
                Pasta das gravações (WAV)
                <input
                  className="search"
                  value={settings.recordings_dir ?? ""}
                  onChange={(event) => setSettings({ ...settings, recordings_dir: event.target.value })}
                />
              </label>
              <div className="people-add">
                <Button onClick={() => void openLocalPath(settings.recordings_dir ?? "")}>
                  Abrir pasta de gravações
                </Button>
              </div>
            </Card>

            <Card className="settings-card">
              <h2>Captura</h2>
              <label className="check-control">
                <input
                  type="checkbox"
                  checked={settings.mic_only_default}
                  onChange={(event) =>
                    setSettings({ ...settings, mic_only_default: event.target.checked })
                  }
                />
                <span className="check-box" aria-hidden />
                <span>
                  <strong>Só o microfone por padrão</strong>
                  <small>Não capturar o som de outros aplicativos</small>
                </span>
              </label>
            </Card>
          </>
        ) : null}

        {tab === "privacy" ? <PrivacyPage /> : null}

        {tab === "about" ? (
          <>
            <AboutPage onOpenPrivacy={openPrivacy} />
            <Card className="settings-card settings-card-wide">
              <h2>Suporte</h2>
              <p className="muted">
                O zip traz versão, memória, disco e logs. Sem áudio, transcrição, chave da API ou token.
              </p>
              <Button onClick={() => void exportDiagnostics()} disabled={diagBusy}>
                {diagBusy ? "Preparando…" : "Exportar diagnóstico"}
              </Button>
            </Card>
          </>
        ) : null}

        {showActions ? (
          <div className="settings-actions">
            <Button onClick={() => void load()} disabled={loading}>
              {loading ? "Atualizando…" : "Atualizar lista"}
            </Button>
            <Button variant="primary" onClick={() => void save()}>
              Salvar
            </Button>
            {saved ? <p className="muted">Preferências salvas neste computador.</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function optionsFor(
  items: ModelOption[],
  current: string,
  source: ModelOption["source"],
): ModelOption[] {
  if (items.some((item) => item.id === current) || !current) return items;
  return [{ id: current, label: current, installed: false, source, detail: "" }, ...items];
}

const SETTINGS_KEYS: (keyof Settings)[] = [
  "whisper_model",
  "ollama_model",
  "mic_only_default",
  "whisper_device",
  "provider",
  "asr_cloud_model",
  "llm_cloud_model",
  "language",
  "recordings_dir",
  "self_person_id",
  "save_recordings",
  "openai_disclaimer_accepted",
];

function diffSettings(
  baseline: Settings | null,
  next: Settings,
): Partial<Settings> & { asr_api_key?: string } {
  if (!baseline) {
    return { save_recordings: next.save_recordings };
  }
  const payload: Partial<Settings> & { asr_api_key?: string } = {};
  for (const key of SETTINGS_KEYS) {
    if (next[key] !== baseline[key]) {
      (payload as Record<string, unknown>)[key] = next[key];
    }
  }
  return payload;
}
