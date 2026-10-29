import type { SetupPlan } from "../../shared/api/types";
import { useT } from "../../shared/i18n";
import { Icon } from "../../shared/ui/Icon";

interface PcAnalysisProps {
  plan: SetupPlan;
  noteLabel: string;
  whisperLabel: string;
}

/** O que o app encontrou nesta máquina e por que escolheu estes modelos. */
export function PcAnalysis({ plan, noteLabel, whisperLabel }: PcAnalysisProps) {
  const t = useT();
  const total = plan.total_ram_gb ?? 0;
  const free = plan.free_ram_gb ?? 0;
  const vram = plan.vram_gb ?? 0;
  const gpu = plan.gpu_name?.trim() ?? "";
  const tier = ramTier(plan.ram_gb);
  const whisperWhy = vram >= 6 ? t("pc.whyTurbo") : gpu ? t("pc.whySmallGpu") : t("pc.whySmallCpu");
  return (
    <section className="pc-analysis" aria-label={t("pc.title")}>
      <header>
        <Icon name="chip" size={15} />
        <strong>{t("pc.title")}</strong>
      </header>
      <dl>
        <div>
          <dt>{t("pc.ram")}</dt>
          <dd>{total > 0 ? t("pc.ramValue", { total: total.toFixed(0), free: free.toFixed(0) }) : t("wizard.ramUnknown")}</dd>
        </div>
        <div>
          <dt>{t("pc.gpu")}</dt>
          <dd>{gpu ? t("pc.gpuValue", { name: gpu, gb: vram.toFixed(0) }) : t("pc.noGpu")}</dd>
        </div>
        <div>
          <dt>{t("pc.disk")}</dt>
          <dd>{plan.free_disk_gb && plan.free_disk_gb > 0 ? t("pc.diskValue", { gb: plan.free_disk_gb.toFixed(0) }) : "—"}</dd>
        </div>
      </dl>
      <ul className="pc-picks">
        <li>
          <span className="pc-pick-label">{t("wizard.notesEngine")}</span>
          <strong>{noteLabel}</strong>
          <small>{t(`pc.whyNote_${tier}` as never)}</small>
        </li>
        <li>
          <span className="pc-pick-label">{t("wizard.asrEngine")}</span>
          <strong>{whisperLabel}</strong>
          <small>{whisperWhy}</small>
        </li>
      </ul>
    </section>
  );
}

function ramTier(ram: number): "xl" | "l" | "m" | "s" | "xs" {
  if (ram >= 32) return "xl";
  if (ram >= 24) return "l";
  if (ram >= 16) return "m";
  if (ram >= 8) return "s";
  return "xs";
}
