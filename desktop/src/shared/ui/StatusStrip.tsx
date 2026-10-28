import { useT } from "../i18n";
import { Icon } from "./Icon";

interface StatusStripProps {
  recording: boolean;
  socketLive: boolean;
  provider: "neste_pc" | "openai";
  asrLabel: string;
  noteLabel: string;
  voiceReady: boolean | null;
  onOpenPalette: () => void;
}

/** Topo: estado da captura e onde o áudio é processado. Os modelos ficam no tooltip. */
export function StatusStrip({
  recording,
  socketLive,
  provider,
  asrLabel,
  noteLabel,
  voiceReady,
  onOpenPalette,
}: StatusStripProps) {
  const t = useT();
  const cloud = provider === "openai";
  const engines = [
    `${t("status.asr")}: ${asrLabel}`,
    `${t("status.voice")}: ${voiceReady === null ? "…" : voiceReady ? "ResNet34 · " + t("status.local") : t("status.off")}`,
    `${t("status.llm")}: ${noteLabel}`,
  ].join("\n");
  return (
    <div className="strip">
      <span className={recording ? "strip-cell strip-rec is-live" : "strip-cell strip-rec"}>
        <span className="state-led" aria-hidden />
        {recording ? t("status.live") : t("status.standby")}
      </span>
      {!socketLive ? <span className="strip-cell is-warn">{t("status.offline")}</span> : null}
      <span className="strip-cell strip-engine" title={engines}>
        <Icon name={cloud ? "cloud" : "lock"} size={13} />
        {cloud ? t("console.privacyCloud") : t("console.privacyLocal")}
      </span>
      <button type="button" className="strip-search" onClick={onOpenPalette}>
        <Icon name="search" size={14} />
        <span>{t("palette.open")}</span>
        <kbd>Ctrl K</kbd>
      </button>
    </div>
  );
}
