import { useState } from "react";
import { Search, Wand2 } from "lucide-react";

import { useLandSuitability } from "@/hooks/useScenarioC";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { EmptyState } from "@/components/states/EmptyState";
import { CacheBadge } from "@/components/states/CacheBadge";
import { SuitabilityGauge } from "@/components/widgets/SuitabilityGauge";
import { FeatureContribution } from "@/components/widgets/FeatureContribution";
import { RationaleList } from "@/components/widgets/RationaleList";
import { TimelineChart } from "@/components/widgets/TimelineChart";
import { useUrlParam } from "@/hooks/useUrlParam";

/** Mode 2: enter PNU → run both DT and DI suitability + value forecast. */
export default function LandSuitabilityMode() {
  const [pnu, setPnu] = useUrlParam("pnu");
  const [draft, setDraft] = useState(pnu ?? "");

  const dtQ = useLandSuitability(pnu ? { pnu, target: "DT" } : null);
  const diQ = useLandSuitability(pnu ? { pnu, target: "DI" } : null);

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setPnu(draft.trim().replace(/-/g, "") || undefined);
        }}
        className="rounded-xl border border-slate-200 bg-white p-4"
      >
        <label htmlFor="pnu" className="text-xs font-semibold text-slate-500">
          분석할 토지 PNU
        </label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              id="pnu"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="19자리 PNU (예: 4128010500-1-0001-0000)"
              className="w-full rounded-md border border-slate-200 py-2 pl-9 pr-3 text-sm focus:border-emerald-400 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-gradient-to-br from-emerald-500 to-teal-500 px-4 py-2 text-sm font-medium text-white"
          >
            <Wand2 className="h-4 w-4" />
            분석 실행
          </button>
        </div>
        <p className="mt-1.5 text-xs text-slate-400">
          하이픈은 자동으로 제거됩니다.
        </p>
      </form>

      {!pnu ? (
        <EmptyState
          title="PNU를 입력하세요"
          detail="시나리오 C 모드 3에서 후보 토지를 선택해도 자동으로 채워집니다."
        />
      ) : (
        <Results pnu={pnu} dtQ={dtQ} diQ={diQ} />
      )}
    </div>
  );
}

function Results({
  pnu,
  dtQ,
  diQ,
}: {
  pnu: string;
  dtQ: ReturnType<typeof useLandSuitability>;
  diQ: ReturnType<typeof useLandSuitability>;
}) {
  const isLoading = dtQ.isLoading || diQ.isLoading;
  const error = dtQ.error ?? diQ.error;
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-72 w-full md:col-span-2" />
      </div>
    );
  }
  if (error) {
    return <ErrorState error={error} onRetry={() => dtQ.refetch()} />;
  }
  const dt = dtQ.data?.data;
  const di = diQ.data?.data;
  if (!dt || !di) return null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">
          PNU: <span className="font-mono text-slate-700">{pnu}</span>
        </p>
        <div className="flex items-center gap-2">
          <CacheBadge meta={dtQ.data?.meta} />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <SuitabilityGauge score={dt.score_100} label="DT" sublabel="Drive-Thru" />
        <SuitabilityGauge score={di.score_100} label="DI" sublabel="Drive-In" />
      </div>

      <FeatureContribution factors={(dtQ.data?.meta.top_factors ?? []) as never} />

      <div className="grid gap-4 md:grid-cols-2">
        <RationaleList rationales={dt.rationales} title="DT 추천 사유" />
        <TimelineChart forecast={dt.value_forecast ?? null} />
      </div>
    </div>
  );
}
