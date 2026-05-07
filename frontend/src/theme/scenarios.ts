// Scenario-level palette + label tokens. Components import from here so
// the gradient stops, accent colors, and Korean labels stay in one place.

export const SCENARIO_THEME = {
  a: {
    label: "시나리오 A",
    subtitle: "보상금 영향 분석",
    gradient: "from-orange-400 to-rose-500",
    accent: "#f43f5e",
    soft: "bg-orange-50 text-orange-700 border-orange-200",
  },
  b: {
    label: "시나리오 B",
    subtitle: "도로 × 인구 × 통행량",
    gradient: "from-violet-500 to-indigo-500",
    accent: "#6366f1",
    soft: "bg-violet-50 text-violet-700 border-violet-200",
  },
  c: {
    label: "시나리오 C",
    subtitle: "DT/DI 매장 입지 예측",
    gradient: "from-emerald-500 to-teal-500",
    accent: "#14b8a6",
    soft: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
} as const;

export type ScenarioKey = keyof typeof SCENARIO_THEME;

export const BRAND_COLORS: Record<string, string> = {
  스타벅스: "#00704A",
  맥도날드: "#FFC72C",
  버거킹: "#D62300",
  메가커피: "#FFE600",
  투썸플레이스: "#7B2D26",
  Starbucks: "#00704A",
  "McDonald's": "#FFC72C",
  "Burger King": "#D62300",
};
