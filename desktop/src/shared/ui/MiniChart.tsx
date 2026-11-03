import { useMemo, useState } from "react";

/** Gráfico que a IA pede num bloco ```chart: barras ou linha, até 4 séries, sem dependência externa. */
export interface ChartSpec {
  type: "bar" | "line";
  title?: string;
  labels: string[];
  series: { name: string; values: number[] }[];
}

const MAX_SERIES = 4;
const MAX_POINTS = 24;
const WIDTH = 560;
const HEIGHT = 240;
const PAD = { top: 18, right: 14, bottom: 34, left: 44 };

export function parseChartSpec(source: string): ChartSpec | null {
  try {
    const raw: unknown = JSON.parse(source);
    if (!raw || typeof raw !== "object") return null;
    const spec = raw as Record<string, unknown>;
    const labels = Array.isArray(spec.labels) ? spec.labels.slice(0, MAX_POINTS).map((item) => String(item)) : [];
    const series = Array.isArray(spec.series)
      ? spec.series
          .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
          .slice(0, MAX_SERIES)
          .map((item) => ({
            name: String(item.name ?? ""),
            values: Array.isArray(item.values)
              ? item.values.slice(0, MAX_POINTS).map((value) => (typeof value === "number" && Number.isFinite(value) ? value : Number(value) || 0))
              : [],
          }))
      : [];
    if (!labels.length || !series.length || !series.some((item) => item.values.length)) return null;
    return {
      type: spec.type === "line" ? "line" : "bar",
      title: typeof spec.title === "string" ? spec.title : undefined,
      labels,
      series,
    };
  } catch {
    return null;
  }
}

function niceTicks(max: number, min: number): number[] {
  const span = max - min || 1;
  const rough = span / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((item) => item * power).find((item) => item >= rough) ?? power;
  const ticks: number[] = [];
  for (let value = Math.floor(min / step) * step; value <= max + step / 2; value += step) ticks.push(Number(value.toFixed(6)));
  return ticks;
}

function format(value: number): string {
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function MiniChart({ spec, tableLabel }: { spec: ChartSpec; tableLabel: string }) {
  const [hover, setHover] = useState<{ point: number; series: number } | null>(null);
  const [showTable, setShowTable] = useState(false);
  const model = useMemo(() => {
    const all = spec.series.flatMap((item) => item.values);
    const rawMax = Math.max(0, ...all);
    const rawMin = Math.min(0, ...all);
    const ticks = niceTicks(rawMax, rawMin);
    const max = ticks[ticks.length - 1] ?? rawMax;
    const min = ticks[0] ?? rawMin;
    const innerW = WIDTH - PAD.left - PAD.right;
    const innerH = HEIGHT - PAD.top - PAD.bottom;
    const y = (value: number) => PAD.top + innerH - ((value - min) / (max - min || 1)) * innerH;
    const slot = innerW / spec.labels.length;
    return { ticks, max, min, innerW, innerH, y, slot };
  }, [spec]);

  const { ticks, y, slot, innerH } = model;
  const zero = y(0);
  const groupW = Math.min(slot * 0.6, 44);
  const barW = Math.max(3, (groupW - 2 * (spec.series.length - 1)) / spec.series.length);
  const skip = Math.max(1, Math.ceil(spec.labels.length / 8));

  return (
    <figure className="md-chart">
      {spec.title ? <figcaption>{spec.title}</figcaption> : null}
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={spec.title ?? tableLabel} onMouseLeave={() => setHover(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="md-chart-grid" />
            <text x={PAD.left - 6} y={y(tick) + 3.5} textAnchor="end" className="md-chart-tick">
              {format(tick)}
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={WIDTH - PAD.right} y1={zero} y2={zero} className="md-chart-axis" />
        {spec.labels.map((label, index) => (
          <text
            key={index}
            x={PAD.left + slot * index + slot / 2}
            y={HEIGHT - PAD.bottom + 16}
            textAnchor="middle"
            className="md-chart-label"
            opacity={index % skip === 0 ? 1 : 0}
          >
            {label.length > 12 ? `${label.slice(0, 11)}…` : label}
          </text>
        ))}
        {spec.type === "bar"
          ? spec.series.map((series, s) =>
              spec.labels.map((_, i) => {
                const value = series.values[i];
                if (value === undefined) return null;
                const x = PAD.left + slot * i + (slot - groupW) / 2 + s * (barW + 2);
                const top = Math.min(y(value), zero);
                const height = Math.max(1, Math.abs(y(value) - zero));
                const active = hover && hover.point === i;
                return (
                  <rect
                    key={`${s}-${i}`}
                    x={x}
                    y={top}
                    width={barW}
                    height={height}
                    rx={Math.min(3, barW / 2)}
                    className={`md-chart-mark is-s${s}${active ? " is-active" : ""}`}
                    onMouseEnter={() => setHover({ point: i, series: s })}
                  >
                    <title>{`${series.name || spec.labels[i]} · ${spec.labels[i]}: ${format(value)}`}</title>
                  </rect>
                );
              }),
            )
          : spec.series.map((series, s) => {
              const points = series.values
                .slice(0, spec.labels.length)
                .map((value, i) => [PAD.left + slot * i + slot / 2, y(value)] as const);
              const path = points.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
              return (
                <g key={s} className={`md-chart-series is-s${s}`}>
                  <path d={path} className="md-chart-line" />
                  {points.map(([px, py], i) => (
                    <circle
                      key={i}
                      cx={px}
                      cy={py}
                      r={hover && hover.point === i ? 5 : 3.5}
                      className="md-chart-dot"
                      onMouseEnter={() => setHover({ point: i, series: s })}
                    >
                      <title>{`${series.name} · ${spec.labels[i]}: ${format(series.values[i] ?? 0)}`}</title>
                    </circle>
                  ))}
                </g>
              );
            })}
        {hover ? (
          <g className="md-chart-hover" transform={`translate(${PAD.left + slot * hover.point + slot / 2}, ${PAD.top})`}>
            <line y1={0} y2={innerH} className="md-chart-crosshair" />
          </g>
        ) : null}
      </svg>
      {spec.series.length > 1 ? (
        <ul className="md-chart-legend">
          {spec.series.map((series, s) => (
            <li key={s}>
              <i className={`is-s${s}`} />
              {series.name}
              {hover ? <small>{format(series.values[hover.point] ?? 0)}</small> : null}
            </li>
          ))}
        </ul>
      ) : hover ? (
        <p className="md-chart-readout">
          {spec.labels[hover.point]}: {format(spec.series[0]?.values[hover.point] ?? 0)}
        </p>
      ) : null}
      <button type="button" className="md-chart-toggle" onClick={() => setShowTable((value) => !value)} aria-expanded={showTable}>
        {tableLabel}
      </button>
      {showTable ? (
        <div className="md-table">
          <table>
            <thead>
              <tr>
                <th />
                {spec.series.map((series, s) => (
                  <th key={s}>{series.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {spec.labels.map((label, i) => (
                <tr key={i}>
                  <td>{label}</td>
                  {spec.series.map((series, s) => (
                    <td key={s} style={{ textAlign: "right" }}>
                      {format(series.values[i] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </figure>
  );
}
