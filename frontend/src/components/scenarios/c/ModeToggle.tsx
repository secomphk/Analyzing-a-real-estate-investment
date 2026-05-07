import { Building2, Search, Store } from "lucide-react";

import { cn } from "@/lib/cn";

export const SCENARIO_C_MODES = ["impact", "suitability", "candidates"] as const;
export type ScenarioCMode = (typeof SCENARIO_C_MODES)[number];

const ITEMS: Array<{ key: ScenarioCMode; label: string; sub: string; Icon: typeof Store }> = [
  { key: "impact", label: "매장 분석", sub: "Halo Effect", Icon: Store },
  { key: "suitability", label: "입지 적합도", sub: "DT/DI 점수", Icon: Building2 },
  { key: "candidates", label: "후보지 발굴", sub: "Top-N 추천", Icon: Search },
];

interface Props {
  mode: ScenarioCMode;
  onChange: (mode: ScenarioCMode) => void;
}

export function ModeToggle({ mode, onChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="시나리오 C 모드"
      className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-white p-1.5 sm:grid-cols-3"
    >
      {ITEMS.map(({ key, label, sub, Icon }) => {
        const active = key === mode;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(key)}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-left transition",
              active
                ? "bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow"
                : "text-slate-700 hover:bg-slate-50",
            )}
          >
            <Icon className="h-5 w-5" />
            <div>
              <p className="text-sm font-semibold">{label}</p>
              <p className={cn("text-xs", active ? "text-emerald-50" : "text-slate-400")}>{sub}</p>
            </div>
          </button>
        );
      })}
    </div>
  );
}
