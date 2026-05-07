import { useUrlParam } from "@/hooks/useUrlParam";
import { ModeToggle, SCENARIO_C_MODES, type ScenarioCMode } from "@/components/scenarios/c/ModeToggle";
import StoreImpactMode from "@/components/scenarios/c/StoreImpactMode";
import LandSuitabilityMode from "@/components/scenarios/c/LandSuitabilityMode";
import CandidateFinderMode from "@/components/scenarios/c/CandidateFinderMode";
import { SCENARIO_THEME } from "@/theme/scenarios";

export default function ScenarioCPage() {
  const [modeRaw, setMode] = useUrlParam("mode", "impact");
  const mode: ScenarioCMode = (SCENARIO_C_MODES as readonly string[]).includes(modeRaw ?? "")
    ? (modeRaw as ScenarioCMode)
    : "impact";

  return (
    <div className="space-y-5">
      <Header />
      <ModeToggle mode={mode} onChange={(m) => setMode(m)} />
      {mode === "impact" && <StoreImpactMode />}
      {mode === "suitability" && <LandSuitabilityMode />}
      {mode === "candidates" && <CandidateFinderMode />}
    </div>
  );
}

function Header() {
  const t = SCENARIO_THEME.c;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">
        {t.label}
      </p>
      <h1 className="text-2xl font-bold text-slate-900">{t.subtitle}</h1>
      <p className="mt-1 text-sm text-slate-500">
        매장 입점 효과 측정, 단일 토지 적합도 평가, 시군구 단위 후보지 발굴까지
        세 모드를 한 화면에서 전환합니다.
      </p>
    </div>
  );
}
