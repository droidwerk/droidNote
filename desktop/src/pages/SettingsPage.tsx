import { useEffect, useState, type KeyboardEvent } from "react";

import { api } from "../shared/api/client";
import type { ModelOption, ModelsCatalog, Person, Settings } from "../shared/api/types";
import { CaptureLanguagePicker, isCaptureLanguage, LanguagePicker, useI18n } from "../shared/i18n";
import type { TranslateFn } from "../shared/i18n/I18nProvider";
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
  | "language"
  | "appearance"
  | "people"
  | "files"
  | "privacy"
  | "about";

interface SettingsPageProps {
  onSaved?: (settings: Settings) => void;
  initialTab?: SettingsTab;
  engineProvider?: Settings["provider"];
}

export function SettingsPage({ onSaved, initialTab = "transcription", engineProvider }: SettingsPageProps) {
  const { t } = useI18n();
  const tabs: { id: SettingsTab; label: string }[] = [
    { id: "transcription", label: t("settings.tabTranscription") },
    { id: "language", label: t("settings.tabLanguage") },
    { id: "appearance", label: t("settings.tabAppearance") },
    { id: "people", label: t("settings.tabPeople") },
    { id: "files", label: t("settings.tabFiles") },
    { id: "privacy", label: t("settings.tabPrivacy") },
    { id: "about", label: t("settings.tabAbout") },
  ];
  const whisperDevices: ModelOption[] = [
    {
      id: "auto",
      label: t("settings.deviceAuto"),
      installed: true,
      source: "whisper",
      detail: t("settings.deviceAutoDetail"),
    },
    {
      id: "cpu",
      label: t("settings.deviceCpu"),
      installed: true,
      source: "whisper",
      detail: t("settings.deviceCpuDetail"),
    },
    {
      id: "cuda",
      label: t("settings.deviceCuda"),
      installed: true,
      source: "whisper",
      detail: t("settings.deviceCudaDetail"),
    },
  ];
  const themeChoices: { id: Theme; label: string; blurb: string }[] = [
    { id: "dark", label: t("settings.themeDark"), blurb: t("settings.themeDarkBlurb") },
    { id: "light", label: t("settings.themeLight"), blurb: t("settings.themeLightBlurb") },
    { id: "paper", label: t("settings.themePaper"), blurb: t("settings.themePaperBlurb") },
  ];
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
      setError(err instanceof Error ? err.message : t("settings.loadFail"));
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
        {error ?? t("settings.loadingPrefs")}
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
        setError(t("settings.confirmOpenai"));
        return;
      }
      const payload = diffSettings(baseline, settings);
      if (replacingKey || apiKey.trim()) payload.asr_api_key = apiKey.trim();
      await persist(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("settings.saveFail"));
    }
  };

  const clearKey = async () => {
    setError(null);
    setKeyTest(null);
    try {
      await persist({ asr_api_key: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("settings.removeKeyFail"));
    }
  };

  const testKey = async () => {
    setError(null);
    try {
      const result = await api.testApiKey(apiKey.trim() || undefined);
      setKeyTest(result.ok ? result.message : result.message);
      if (!result.ok) setError(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("settings.testKeyFail"));
    }
  };

  const downloadModel = async () => {
    setDownloading(true);
    setError(null);
    setDownloadStatus({ progress: 1, message: t("settings.startingDownload") });
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
      setError(err instanceof Error ? err.message : t("settings.downloadFail"));
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
        toast.push({ tone: "error", title: t("settings.diagFail"), description: result.message });
        return;
      }
      toast.push({
        tone: "success",
        title: t("settings.diagSaved"),
        description: "DroidNote-diagnostico.zip",
        action: result.path
          ? {
              label: t("settings.openFolder"),
              onClick: () => void openLocalPath(parentDirectory(result.path ?? "")),
            }
          : undefined,
      });
    } catch (err) {
      toast.push({
        tone: "error",
        title: t("settings.diagFail"),
        description:
          err instanceof Error
            ? err.message
            : t("settings.diagFailBody"),
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
      title: t("settings.deletePerson", { name: person?.name ?? t("settings.thisPerson") }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    await api.deletePerson(id);
    setPeople((current) => current.filter((item) => item.id !== id));
  };

  const onTabKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((item) => item.id === tab);
    if (index < 0) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setTab(tabs[(index + 1) % tabs.length]?.id ?? tab);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      setTab(tabs[(index - 1 + tabs.length) % tabs.length]?.id ?? tab);
    } else if (event.key === "Home") {
      event.preventDefault();
      setTab(tabs[0]?.id ?? tab);
    } else if (event.key === "End") {
      event.preventDefault();
      setTab(tabs[tabs.length - 1]?.id ?? tab);
    }
  };

  const openPrivacy = () => setTab("privacy");

  return (
    <div className="container settings-page">
      <PageHeader
        title={<h1>{t("settings.title")}</h1>}
        description={t("settings.description")}
      />
      {error ? <p className="banner">{error}</p> : null}

      <div
        className="settings-tabs"
        role="tablist"
        aria-label={t("settings.tabsAria")}
        onKeyDown={onTabKey}
      >
        {tabs.map((item) => (
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
              <h2>{t("settings.engineTitle")}</h2>
              <p className="muted">
                {t("settings.engineHelp")}
              </p>
              <div className="segmented" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={!cloud}
                  className={!cloud ? "on" : ""}
                  onClick={() => setSettings({ ...settings, provider: "neste_pc" })}
                >
                  {t("engine.localPrivate")}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={cloud}
                  className={cloud ? "on" : ""}
                  onClick={() => setSettings({ ...settings, provider: "openai" })}
                >
                  {t("engine.openaiAccurate")}
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
                    <strong>{t("settings.consentStrong")}</strong>
                    <small>
                      <PrivacyLink onOpen={openPrivacy} />
                      {" · "}
                      {t("settings.consentCloud")}
                    </small>
                  </span>
                </label>
              ) : (
                <p className="muted">
                  <PrivacyLink onOpen={openPrivacy} />
                  {" — "}
                  {t("settings.localStays")}
                </p>
              )}

              {cloud ? (
                <div className="form-grid">
                  <label>
                    {t("settings.asrModel")}
                    <ModelSelect
                      label={t("settings.asrModel")}
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
                    {t("settings.noteModel")}
                    <ModelSelect
                      label={t("settings.noteModel")}
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
                    {t("settings.apiKey")}
                    {settings.has_api_key && !replacingKey ? (
                      <div className="api-key-status">
                        <p className="muted">
                          {t("settings.keySaved", { hint: settings.api_key_hint ?? "" })}
                        </p>
                        <div className="row">
                          <Button onClick={() => setReplacingKey(true)}>{t("settings.replace")}</Button>
                          <Button variant="danger" onClick={() => void clearKey()}>
                            {t("settings.remove")}
                          </Button>
                          <Button onClick={() => void testKey()}>{t("settings.testKey")}</Button>
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
                              ? t("settings.newKeyPlaceholder", { hint: settings.api_key_hint ?? "" })
                              : "sk-…"
                          }
                          value={apiKey}
                          onChange={(event) => setApiKey(event.target.value)}
                        />
                        <div className="row">
                          <Button onClick={() => void testKey()} disabled={!apiKey.trim() && !settings.has_api_key}>
                            {t("settings.testKey")}
                          </Button>
                          {replacingKey ? (
                            <Button
                              onClick={() => {
                                setReplacingKey(false);
                                setApiKey("");
                              }}
                            >
                              {t("common.cancel")}
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
                    {t("settings.whisperModel")}
                    <ModelSelect
                      label={t("settings.whisperModel")}
                      value={settings.whisper_model}
                      options={localizeModels(optionsFor(catalog?.whisper ?? [], settings.whisper_model, "whisper"), t)}
                      onChange={(id) => setSettings({ ...settings, whisper_model: id })}
                    />
                  </label>
                  <label>
                    {t("settings.whisperDevice")}
                    <ModelSelect
                      label={t("settings.whisperDevice")}
                      value={settings.whisper_device ?? "auto"}
                      options={whisperDevices}
                      onChange={(id) => setSettings({ ...settings, whisper_device: id })}
                      showStatus={false}
                    />
                  </label>
                  <label>
                    {t("settings.noteModelOllama")}
                    <ModelSelect
                      label={t("settings.noteModel")}
                      value={settings.ollama_model}
                      options={localizeModels(optionsFor(catalog?.ollama ?? [], settings.ollama_model, "ollama"), t)}
                      onChange={(id) => setSettings({ ...settings, ollama_model: id })}
                    />
                  </label>
                  <p className="model-legend">
                    <span>
                      <StatusGlyph installed />
                      {t("settings.alreadyHere")}
                    </span>
                    <span>
                      <StatusGlyph installed={false} />
                      {t("settings.willDownload")}
                    </span>
                  </p>
                </div>
              )}

              {cloud ? (
                <p className="banner">
                  {t("settings.cloudBanner")}{" "}
                  <PrivacyLink onOpen={openPrivacy} />
                </p>
              ) : (
                <>
                  <div className="disclaimer">
                    <h3>{t("settings.localExpectTitle")}</h3>
                    <p>
                      {t("settings.localExpectBody")}
                    </p>
                    <p className="muted">
                      {t("settings.localExpectHint")}
                    </p>
                  </div>
                  <div className="row">
                    <span className={catalog?.ollama_online ? "badge on" : "badge"}>
                      {catalog?.ollama_online ? t("settings.ollamaOnline") : t("settings.ollamaOffline")}
                    </span>
                    <span className="muted">
                      {t("settings.whisperInstalled", {
                        count: (catalog?.whisper ?? []).filter((item) => item.installed).length,
                      })}
                    </span>
                  </div>
                  <div className="tutorial">
                    <h3>{t("settings.downloadTitle")}</h3>
                    <p className="muted">
                      {t("settings.downloadHint")}
                    </p>
                    <Button onClick={() => void downloadModel()} disabled={downloading}>
                      {downloading ? t("settings.downloading") : t("settings.downloadSelected")}
                    </Button>
                    {downloading || downloadStatus ? (
                      <div className="model-progress">
                        <ProgressBar value={downloadStatus?.progress ?? 0} />
                        <p className="muted">{downloadStatus?.message ?? t("common.preparing")}</p>
                      </div>
                    ) : null}
                  </div>
                </>
              )}
            </Card>
          </>
        ) : null}

        {tab === "language" ? (
          <>
            <p className="muted settings-card-wide">{t("languages.independentHelp")}</p>
            <Card className="settings-card settings-card-wide">
              <h2>{t("languages.uiLabel")}</h2>
              <p className="muted">{t("languages.uiHelp")}</p>
              <LanguagePicker
                onPicked={(id) => {
                  setSettings({ ...settings, ui_language: id });
                  void persist({ ui_language: id });
                }}
              />
            </Card>
            <Card className="settings-card settings-card-wide">
              <h2>{t("languages.captureLabel")}</h2>
              <p className="muted">{t("languages.captureHelp")}</p>
              <CaptureLanguagePicker
                value={isCaptureLanguage(settings.language) ? settings.language : "pt"}
                onPicked={(id) => {
                  setSettings({ ...settings, language: id });
                  void persist({ language: id });
                }}
              />
            </Card>
          </>
        ) : null}

        {tab === "appearance" ? (
          <>
            <Card className="settings-card settings-card-wide">
              <h2>{t("settings.appearanceTitle")}</h2>
              <p className="muted">{t("settings.appearanceHelp")}</p>
              <div className="theme-grid">
                {themeChoices.map((choice) => (
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
          </>
        ) : null}

        {tab === "people" ? (
          <Card className="settings-card settings-card-people settings-card-wide">
            <h2>{t("settings.peopleTitle")}</h2>
            <p className="muted">
              {t("settings.peopleHelp")}
            </p>
            <label>
              {t("settings.youMic")}
              <select
                className="select"
                value={settings.self_person_id ?? ""}
                onChange={(event) =>
                  setSettings({ ...settings, self_person_id: event.target.value })
                }
              >
                <option value="">{t("settings.notSet")}</option>
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
                placeholder={t("common.name")}
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
                {t("settings.register")}
              </Button>
            </div>
            <ul className="people-list">
              {people.length === 0 ? <li className="muted">{t("settings.nobody")}</li> : null}
              {people.map((person) => (
                <li key={person.id}>
                  <span>{person.name}</span>
                  <Button onClick={() => void removePerson(person.id)}>{t("common.delete")}</Button>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        {tab === "files" ? (
          <>
            <Card className="settings-card settings-card-wide">
              <h2>{t("settings.filesTitle")}</h2>
              <p className="muted">
                {t("settings.filesHelp")}
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
                      setError(err instanceof Error ? err.message : t("settings.wavSaveFail"));
                    });
                  }}
                />
                <span className="check-box" aria-hidden />
                <span>
                  <strong>{t("settings.saveWavTitle")}</strong>
                  <small>
                    {t("settings.saveWavHint")}
                  </small>
                </span>
              </label>
              <label>
                {t("settings.dataFolder")}
                <input className="search" value={settings.data_dir ?? ""} readOnly />
              </label>
              <div className="people-add">
                <Button onClick={() => void openLocalPath(settings.data_dir ?? "")}>{t("settings.openData")}</Button>
              </div>
              <label>
                {t("settings.recordingsFolder")}
                <input
                  className="search"
                  value={settings.recordings_dir ?? ""}
                  onChange={(event) => setSettings({ ...settings, recordings_dir: event.target.value })}
                />
              </label>
              <div className="people-add">
                <Button onClick={() => void openLocalPath(settings.recordings_dir ?? "")}>
                  {t("settings.openRecordings")}
                </Button>
              </div>
            </Card>

            <Card className="settings-card">
              <h2>{t("settings.captureTitle")}</h2>
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
                  <strong>{t("settings.micOnlyTitle")}</strong>
                  <small>{t("settings.micOnlyHint")}</small>
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
              <h2>{t("settings.supportTitle")}</h2>
              <p className="muted">
                {t("settings.supportHelp")}
              </p>
              <Button onClick={() => void exportDiagnostics()} disabled={diagBusy}>
                {diagBusy ? t("settings.preparingDiag") : t("settings.exportDiag")}
              </Button>
            </Card>
          </>
        ) : null}

        {showActions ? (
          <div className="settings-actions">
            <Button onClick={() => void load()} disabled={loading}>
              {loading ? t("settings.updating") : t("settings.refresh")}
            </Button>
            <Button variant="primary" onClick={() => void save()}>
              {t("common.save")}
            </Button>
            {saved ? <p className="muted">{t("settings.savedHere")}</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function localizeModels(items: ModelOption[], t: TranslateFn): ModelOption[] {
  return items.map((item) => {
    const key = `models.${item.id}`;
    const label = t(key);
    return label === key ? item : { ...item, label };
  });
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
  "ui_language",
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
