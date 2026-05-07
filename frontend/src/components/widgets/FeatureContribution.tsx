import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Factor {
  factor: string;
  value: unknown;
  impact?: "positive" | "negative" | "neutral";
  shap?: number | null;
}

interface Props {
  factors: Factor[];
  title?: string;
}

/** SHAP-style bar chart. Negative contributions stay red; positive are green.
 *  Falls back to the raw `value` when `shap` is missing. */
export function FeatureContribution({ factors, title = "변수 기여도" }: Props) {
  const data = factors
    .map((f) => ({
      factor: f.factor,
      value:
        typeof f.shap === "number"
          ? f.shap
          : typeof f.value === "number"
            ? f.value
            : 0,
      impact: f.impact ?? "neutral",
    }))
    .slice(0, 10)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  if (data.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      <div className="mt-3 h-72 w-full">
        <ResponsiveContainer>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 10, right: 16, left: 0, bottom: 0 }}
          >
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="factor"
              width={150}
              tick={{ fontSize: 11 }}
            />
            <Tooltip />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((d, i) => (
                <Cell
                  key={i}
                  fill={
                    d.impact === "positive"
                      ? "#10b981"
                      : d.impact === "negative"
                        ? "#ef4444"
                        : "#94a3b8"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
