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

/** Telemetria do sistema no topo: o que está ligado, onde roda, se está conectado. */
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
  return (
    <div className="strip">
      <span className={recording ? "strip-cell strip-rec is-live" : "strip-cell strip-rec"}>
        <span className="state-led" aria-hidden />
        {recording ? t("status.live") : t("status.standby")}
      </span>
      <span className={socketLive ? "strip-cell" : "strip-cell is-warn"}>
        {socketLive ? t("status.online") : t("status.offline")}
      </span>
      <span className="strip-cell">
        <Icon name={cloud ? "cloud" : "lock"} size={13} />
        {cloud ? t("console.privacyCloud") : t("console.privacyLocal")}
      </span>
      <span className="strip-cell strip-hide-sm">
        <b>{t("status.asr")}</b>
        {asrLabel}
      </span>
      <span className={voiceReady === false ? "strip-cell strip-hide-sm is-dim" : "strip-cell strip-hide-sm"}>
        <b>{t("status.voice")}</b>
        {voiceReady === null ? "…" : voiceReady ? "ResNet34 · " + t("status.local") : t("status.off")}
      </span>
      <span className="strip-cell strip-hide-md">
        <b>{t("status.llm")}</b>
        {noteLabel}
      </span>
      <button type="button" className="strip-search" onClick={onOpenPalette}>
        <Icon name="search" size={14} />
        <span>{t("palette.open")}</span>
        <kbd>Ctrl K</kbd>
      </button>
    </div>
  );
}
