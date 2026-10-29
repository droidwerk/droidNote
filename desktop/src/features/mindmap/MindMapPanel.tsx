import { useCallback, useEffect, useRef, useState } from "react";
import MindElixir, { type MindElixirData, type MindElixirInstance, type NodeObj, type Theme } from "mind-elixir";
import "mind-elixir/style.css";

import { api } from "../../shared/api/client";
import type { MindMap } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { copyToClipboard } from "../../shared/lib/format";
import { saveBlob } from "../../shared/lib/saveFile";
import { AiThinking } from "../../shared/ui/AiThinking";
import { Icon } from "../../shared/ui/Icon";
import { InfoTip } from "../../shared/ui/InfoTip";
import { Button } from "../../shared/ui/primitives";
import { useToast } from "../../shared/ui/Toast";

interface MindMapPanelProps {
  sessionId: string;
  title: string;
  /** Sem ata ainda o mapa fica vazio; o botão de gerar a ata está na aba Documento. */
  hasSummary: boolean;
  revision?: number;
  onCite?: (ms: number) => void;
}

interface NodeMeta {
  kind?: string;
  at_ms?: number;
  task_id?: string;
  done?: boolean;
}

const SAVE_DELAY_MS = 900;
const PALETTE = ["#ff6a2b", "#38bdf8", "#a3e635", "#c084fc", "#fbbf24", "#f472b6", "#2dd4bf", "#f87171"];

/** Mapa mental da conversa: nasce da ata, cada folha leva à fala, e a pessoa edita à vontade. */
export function MindMapPanel({ sessionId, title, hasSummary, revision = 0, onCite }: MindMapPanelProps) {
  const t = useT();
  const toast = useToast();
  const host = useRef<HTMLDivElement>(null);
  const mind = useRef<MindElixirInstance | null>(null);
  const saveTimer = useRef<number | null>(null);
  const [record, setRecord] = useState<MindMap | null>(null);
  const [busy, setBusy] = useState<"load" | "refine" | "reset" | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setBusy("load");
    setError(null);
    try {
      setRecord(await api.mindmap(sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("mindmap.failed"));
      setRecord(null);
    } finally {
      setBusy(null);
    }
  }, [sessionId, t]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  const persist = useCallback(
    (data: MindElixirData) => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => {
        void api
          .saveMindMap(sessionId, data)
          .then((next) => {
            setRecord((current) => (current ? { ...current, origin: next.origin, updated_at: next.updated_at } : next));
            setSaved(true);
            window.setTimeout(() => setSaved(false), 1400);
          })
          .catch(() => toast.push({ tone: "error", title: t("mindmap.saveFail") }));
      }, SAVE_DELAY_MS);
    },
    [sessionId, toast, t],
  );

  // Monta (ou remonta) o editor quando o mapa muda de origem: ata nova, reset ou reorganização.
  useEffect(() => {
    const el = host.current;
    if (!el || !record || !hasNodes(record)) return undefined;
    const instance = new MindElixir({
      el,
      direction: (record.data.direction as 0 | 1 | 2 | 3 | undefined) ?? MindElixir.SIDE,
      editable: true,
      contextMenu: true,
      toolBar: false,
      keypress: true,
      allowUndo: true,
      overflowHidden: false,
      theme: themeFromTokens(),
      newTopicName: t("mindmap.newTopic"),
    });
    instance.init({ nodeData: record.data.nodeData as NodeObj, direction: record.data.direction as 0 | 1 | 2 | 3 | undefined });
    instance.bus.addListener("operation", () => persist(instance.getData()));
    instance.bus.addListener("selectNodes", (nodes: NodeObj[]) => {
      const meta = (nodes[0]?.metadata ?? {}) as NodeMeta;
      if (nodes.length === 1 && typeof meta.at_ms === "number" && onCite) onCite(meta.at_ms);
    });
    mind.current = instance;
    window.requestAnimationFrame(() => {
      instance.scale(0.72);
      instance.toCenter();
    });
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      instance.destroy();
      mind.current = null;
    };
    // O editor só remonta quando o registro muda de verdade (origem/ata), não a cada salvamento.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record?.session_id, record?.summary_id, record?.origin === "auto", record?.origin === "ai", hasNodes(record)]);

  const refine = async () => {
    setBusy("refine");
    setError(null);
    try {
      setRecord(await api.refineMindMap(sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("mindmap.failed"));
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    setBusy("reset");
    setError(null);
    try {
      setRecord(await api.resetMindMap(sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("mindmap.failed"));
    } finally {
      setBusy(null);
    }
  };

  const copyOutline = async () => {
    if (!record?.markdown) return;
    if (await copyToClipboard(record.markdown)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    }
  };

  const downloadPng = async () => {
    const instance = mind.current;
    if (!instance) return;
    const blob = await instance.exportPng(false);
    if (!blob) {
      toast.push({ tone: "error", title: t("session.exportFail") });
      return;
    }
    const name = `${title} — ${t("mindmap.title")}.png`;
    const result = await saveBlob(blob, name, [{ name: "PNG", extensions: ["png"] }]);
    if (result.status === "error") toast.push({ tone: "error", title: t("session.exportFail"), description: result.message });
    else if (result.status === "saved") toast.push({ tone: "success", title: t("session.fileSaved"), description: name });
  };

  const ready = record !== null && hasNodes(record);

  return (
    <section className="card mindmap-panel">
      <div className="summary-head">
        <h2 className="with-tip">
          {t("mindmap.title")}
          <InfoTip text={t("mindmap.hint")} />
        </h2>
        <div className="summary-actions">
          {ready ? (
            <>
              <Button size="sm" variant="quiet" onClick={() => mind.current?.toCenter()} title={t("mindmap.center")}>
                <Icon name="search" size={14} />
              </Button>
              <Button size="sm" variant="quiet" onClick={() => void copyOutline()} title={t("mindmap.copyHint")} aria-label={t("mindmap.copy")}>
                {copied ? <Icon name="check" size={14} /> : <Icon name="attach" size={14} />}
              </Button>
              <Button size="sm" variant="quiet" onClick={() => void downloadPng()} title={t("mindmap.png")} aria-label={t("mindmap.png")}>
                <Icon name="export" size={14} />
              </Button>
              <Button size="sm" variant="quiet" disabled={busy !== null} onClick={() => void reset()} title={t("mindmap.resetHint")}>
                {t("mindmap.reset")}
              </Button>
            </>
          ) : null}
          <Button size="sm" variant="primary" disabled={!ready || busy !== null} onClick={() => void refine()} title={t("mindmap.refineHint")}>
            <Icon name="spark" size={14} />
            {busy === "refine" ? t("mindmap.refining") : t("mindmap.refine")}
          </Button>
        </div>
      </div>
      {error ? <p className="banner">{error}</p> : null}
      {busy === "refine" ? (
        <AiThinking lines={5} steps={[t("mindmap.stepRead"), t("mindmap.stepGroup"), t("mindmap.stepDraw")]} />
      ) : busy === "load" && !record ? (
        <p className="dg-hint">{t("common.loading")}</p>
      ) : !ready ? (
        <div className="note-empty">
          <div>
            <strong>{t("mindmap.emptyTitle")}</strong>
            <p>{hasSummary ? t("mindmap.emptyBodyNoItems") : t("mindmap.emptyBody")}</p>
          </div>
        </div>
      ) : (
        <>
          <div className="mindmap-host" ref={host} />
          <p className="mindmap-foot">
            <span>{t("mindmap.selectHint")}</span>
            <em>
              {saved ? t("mindmap.saved") : record?.origin === "edited" ? t("mindmap.edited") : record?.origin === "ai" ? t("mindmap.byAi") : t("mindmap.fromMinutes")}
            </em>
          </p>
        </>
      )}
    </section>
  );
}

function hasNodes(record: MindMap | null): boolean {
  const root = record?.data.nodeData as NodeObj | undefined;
  return Boolean(root && root.children && root.children.length);
}

/** Tema do editor a partir das cores do DroidNote (escuro, claro ou papel). */
function themeFromTokens(): Theme {
  const css = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  const dark = (document.documentElement.dataset.theme ?? "dark") === "dark";
  return {
    name: "droidnote",
    type: dark ? "dark" : "light",
    palette: PALETTE,
    cssVar: {
      "--main-color": read("--text", dark ? "#f4f4f5" : "#0c0c0e"),
      "--main-bgcolor": read("--surface-2", dark ? "#111114" : "#f8f8f6"),
      "--color": read("--text-soft", dark ? "#cfcfd4" : "#34343a"),
      "--bgcolor": read("--surface", dark ? "#0b0b0d" : "#ffffff"),
      "--selected": read("--accent-hi", "#ff6a2b"),
      "--accent-color": read("--accent", "#ff4400"),
      "--root-color": read("--accent-ink", "#ffffff"),
      "--root-bgcolor": read("--accent", "#ff4400"),
      "--root-border-color": read("--accent-line", "rgba(255, 68, 0, 0.38)"),
      "--root-radius": "12px",
      "--main-radius": "8px",
      "--topic-padding": "4px 8px",
      "--panel-color": read("--text", "#f4f4f5"),
      "--panel-bgcolor": read("--surface-3", "#18181c"),
      "--panel-border-color": read("--line-strong", "rgba(255,255,255,0.12)"),
      "--map-padding": "40px",
    },
  };
}
