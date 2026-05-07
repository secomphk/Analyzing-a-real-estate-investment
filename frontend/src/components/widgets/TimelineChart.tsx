import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatPct } from "@/lib/format";

interface Props {
  forecast: Record<string, number> | null | undefined;
  title?: string;
}

/** 1y/3y/5y forecast as a smoothed area chart with a faint confidence band.
 *  The band is a heuristic ±25% of the central estimate — Phase 2 swaps in
 *  the predictor's own intervals. */
export function TimelineChart({ forecast, title = "5년 가치 변화 예측" }: Props) {
  if (!forecast || Object.keys(forecast).length === 0) return null;

  const data = Object.entries(forecast)
    .map(([k, v]) => ({
      horizon: k,
      forecast: v,
      hi: v * 1.25,
      lo: v * 0.75,
    }))
    .sort((a, b) => parseInt(a.horizon) - parseInt(b.horizon));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      <div className="mt-3 h-56 w-full">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="horizon" />
            <YAxis tickFormatter={(v) => formatPct(v as number, 0)} />
            <Tooltip
              formatter={(v: number) => formatPct(v)}
              labelFormatter={(l) => `${l} 후`}
            />
            <Area
              type="monotone"
              dataKey="hi"
              stroke="none"
              fill="#10b98133"
            />
            <Area
              type="monotone"
              dataKey="lo"
              stroke="none"
              fill="#ffffff"
            />
            <Area
              type="monotone"
              dataKey="forecast"
              stroke="#10b981"
              strokeWidth={2}
              fill="#10b98166"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
