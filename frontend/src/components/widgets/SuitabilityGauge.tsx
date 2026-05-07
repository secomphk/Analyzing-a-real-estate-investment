interface Props {
  score: number; // 0..100
  label: string; // "DT" / "DI"
  sublabel?: string;
}

/** 0–100 gauge with a sweeping color gradient.
 *
 *  Pure SVG — no chart-lib dependency. The arc spans 270° so the score
 *  needle is unambiguous at the extremes. */
export function SuitabilityGauge({ score, label, sublabel }: Props) {
  const clamped = Math.max(0, Math.min(100, score));
  const radius = 60;
  const cx = 80;
  const cy = 88;
  const start = 135; // degrees
  const end = 405;
  const angle = start + ((end - start) * clamped) / 100;
  const big = clamped > 50 ? 1 : 0;

  const startPos = polar(cx, cy, radius, start);
  const endPos = polar(cx, cy, radius, angle);
  const trailEnd = polar(cx, cy, radius, end);

  const color =
    clamped >= 66 ? "#10b981" : clamped >= 33 ? "#f59e0b" : "#ef4444";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {label} 적합도
          </p>
          {sublabel && <p className="text-xs text-slate-400">{sublabel}</p>}
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-[11px] font-semibold text-white"
          style={{ background: color }}
        >
          {clamped >= 66 ? "HIGH" : clamped >= 33 ? "MEDIUM" : "LOW"}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-4">
        <svg width={160} height={120} viewBox="0 0 160 120" aria-label={`${label} 적합도 ${clamped}`}>
          <path
            d={`M ${startPos.x} ${startPos.y} A ${radius} ${radius} 0 1 1 ${trailEnd.x} ${trailEnd.y}`}
            fill="none"
            stroke="#e2e8f0"
            strokeWidth={12}
            strokeLinecap="round"
          />
          <path
            d={`M ${startPos.x} ${startPos.y} A ${radius} ${radius} 0 ${big} 1 ${endPos.x} ${endPos.y}`}
            fill="none"
            stroke={color}
            strokeWidth={12}
            strokeLinecap="round"
          />
          <text
            x={cx}
            y={cy + 6}
            textAnchor="middle"
            className="fill-slate-900"
            style={{ fontSize: 28, fontWeight: 700 }}
          >
            {clamped}
          </text>
          <text
            x={cx}
            y={cy + 26}
            textAnchor="middle"
            style={{ fontSize: 11, fill: "#64748b" }}
          >
            / 100
          </text>
        </svg>
      </div>
    </div>
  );
}

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}
