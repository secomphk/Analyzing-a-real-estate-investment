import { CheckCircle2, MinusCircle, XCircle } from "lucide-react";

import type { Rationale } from "@/api/schemas";
import { cn } from "@/lib/cn";

const CATEGORY_LABEL: Record<Rationale["category"], string> = {
  property: "부동산",
  surroundings: "주변 환경",
  traffic: "교통",
  catalyst: "호재",
};

const IMPACT_TONE: Record<Rationale["impact"], string> = {
  positive: "border-emerald-200 bg-emerald-50 text-emerald-900",
  negative: "border-rose-200 bg-rose-50 text-rose-900",
  neutral: "border-slate-200 bg-slate-50 text-slate-700",
};

export function RationaleList({
  rationales,
  title = "추천 사유",
}: {
  rationales: Rationale[];
  title?: string;
}) {
  if (rationales.length === 0) return null;
  // Group by category so the UI mirrors the backend's mental model.
  const grouped: Record<Rationale["category"], Rationale[]> = {
    property: [],
    surroundings: [],
    traffic: [],
    catalyst: [],
  };
  for (const r of rationales) grouped[r.category].push(r);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      <div className="mt-3 space-y-4">
        {(Object.keys(grouped) as Rationale["category"][]).map((cat) =>
          grouped[cat].length === 0 ? null : (
            <div key={cat}>
              <p className="mb-1.5 text-xs font-semibold text-slate-500">
                {CATEGORY_LABEL[cat]}
              </p>
              <ul className="space-y-1.5">
                {grouped[cat].map((r, i) => (
                  <li
                    key={i}
                    className={cn(
                      "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                      IMPACT_TONE[r.impact],
                    )}
                  >
                    <ImpactIcon impact={r.impact} />
                    <span>{r.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>
    </section>
  );
}

function ImpactIcon({ impact }: { impact: Rationale["impact"] }) {
  if (impact === "positive")
    return <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-500" />;
  if (impact === "negative")
    return <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-500" />;
  return <MinusCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-400" />;
}
