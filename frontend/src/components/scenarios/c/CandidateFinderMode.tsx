import { useMemo, useState } from "react";
import { Filter, Search, Sparkles } from "lucide-react";

import { useDTCandidates } from "@/hooks/useScenarioC";
import { useUrlParam } from "@/hooks/useUrlParam";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { EmptyState } from "@/components/states/EmptyState";
import { CacheBadge } from "@/components/states/CacheBadge";
import HeatmapOverlay, { type HeatmapPoint } from "@/components/maps/HeatmapOverlay";
import { SimilarStoresCard } from "@/components/widgets/SimilarStoresCard";
import { RationaleList } from "@/components/widgets/RationaleList";
import type { Candidate } from "@/api/schemas";

const REGION_PRESETS = [
  { code: "41280", label: "김포시" },
  { code: "41220", label: "평택시" },
  { code: "41131", label: "성남시 분당구" },
];

interface FormState {
  region_code: string;
  target: "DT" | "DI";
  top_n: number;
  min_score: number;
}

/** Mode 3: scan candidates in a 시군구 → heatmap + ranked card list. */
export default function CandidateFinderMode() {
  const [region, setRegion] = useUrlParam("region", "41280");
  const [target, setTarget] = useUrlParam("target", "DT");
  const [topNRaw, setTopN] = useUrlParam("top_n", "10");
  const [, setPnu] = useUrlParam("pnu");
  const [, setMode] = useUrlParam("mode");
  const [minScore, setMinScore] = useState(50);

  const form: FormState = {
    region_code: region ?? "41280",
    target: (target === "DI" ? "DI" : "DT") as "DT" | "DI",
    top_n: Number(topNRaw ?? 10),
    min_score: minScore,
  };

  const candidatesQ = useDTCandidates(
    region
      ? { region_code: form.region_code, target: form.target, top_n: form.top_n }
      : null,
  );

  const filtered = useMemo(() => {
    const all = candidatesQ.data?.data.candidates ?? [];
    return all.filter((c) => c.suitability.score_100 >= form.min_score);
  }, [candidatesQ.data, form.min_score]);

  const heatmapPoints: HeatmapPoint[] = useMemo(
    () =>
      filtered.map((c, i) => ({
        id: c.pnu,
        position: pseudoLatLng(c.pnu, i),
        score: c.suitability.score_100,
        label: c.address ?? c.pnu,
      })),
    [filtered],
  );

  const center = heatmapPoints[0]?.position ?? { lat: 37.6166, lng: 126.7146 };

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {REGION_PRESETS.map((p) => (
              <button
                key={p.code}
                type="button"
                onClick={() => setRegion(p.code)}
                className={
                  "rounded-full px-3 py-1.5 text-sm " +
                  (region === p.code
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200")
                }
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-1.5">
              브랜드 기준
              <select
                value={form.target}
                onChange={(e) => setTarget(e.target.value)}
                className="rounded-md border border-slate-200 px-2 py-1 text-sm"
              >
                <option value="DT">DT</option>
                <option value="DI">DI</option>
              </select>
            </label>
            <label className="flex items-center gap-1.5">
              Top
              <select
                value={form.top_n}
                onChange={(e) => setTopN(e.target.value)}
                className="rounded-md border border-slate-200 px-2 py-1 text-sm"
              >
                <option value="10">10</option>
                <option value="20">20</option>
                <option value="30">30</option>
              </select>
            </label>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Filter className="h-4 w-4 text-slate-400" />
          <input
            type="range"
            min={50}
            max={95}
            step={5}
            value={form.min_score}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="flex-1 accent-emerald-500"
            aria-label="최소 적합도"
          />
          <span className="w-16 text-right text-sm font-medium text-slate-700">
            ≥ {form.min_score}점
          </span>
        </div>
      </header>

      {candidatesQ.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-[420px] w-full" />
          <Skeleton className="h-[420px] w-full" />
        </div>
      ) : candidatesQ.error ? (
        <ErrorState
          error={candidatesQ.error}
          onRetry={() => candidatesQ.refetch()}
          title="후보 분석에 실패했습니다"
        />
      ) : !candidatesQ.data?.data ? (
        <EmptyState title="후보 데이터가 없습니다" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between px-1">
              <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                <Sparkles className="h-4 w-4 text-emerald-500" /> 후보지 히트맵
              </h3>
              <CacheBadge meta={candidatesQ.data.meta} />
            </div>
            <HeatmapOverlay center={center} points={heatmapPoints} />
            {heatmapPoints.length === 0 && (
              <p className="mt-2 px-1 text-xs text-slate-400">
                필터 조건을 만족하는 후보가 없습니다.
              </p>
            )}
          </div>

          <div className="space-y-3">
            {filtered.length === 0 ? (
              <EmptyState
                title="조건을 만족하는 후보가 없습니다"
                detail="최소 적합도 슬라이더를 낮추거나 시군구를 변경하세요."
              />
            ) : (
              filtered.map((c, i) => (
                <CandidateCard
                  key={c.pnu}
                  rank={i + 1}
                  candidate={c}
                  onOpen={() => {
                    setMode("suitability");
                    setPnu(c.pnu);
                  }}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function CandidateCard({
  rank,
  candidate,
  onOpen,
}: {
  rank: number;
  candidate: Candidate;
  onOpen: () => void;
}) {
  const score = candidate.suitability.score_100;
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <span
            className="grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500 text-sm font-bold text-white"
            aria-label={`순위 ${rank}`}
          >
            #{rank}
          </span>
          <div>
            <p className="font-mono text-xs text-slate-400">{candidate.pnu}</p>
            <p className="text-sm font-medium text-slate-900">
              {candidate.address ?? "주소 정보 없음"}
            </p>
          </div>
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-semibold text-white"
          style={{ background: scoreToColor(score) }}
        >
          {score}점
        </span>
      </div>

      {candidate.rationales && candidate.rationales.length > 0 && (
        <div className="mt-3">
          <RationaleList rationales={candidate.rationales.slice(0, 3)} title="핵심 사유" />
        </div>
      )}

      {candidate.similar_stores && candidate.similar_stores.length > 0 && (
        <div className="mt-3">
          <SimilarStoresCard items={candidate.similar_stores} />
        </div>
      )}

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
        >
          <Search className="h-3.5 w-3.5" />
          상세 분석
        </button>
      </div>
    </article>
  );
}

function scoreToColor(s: number): string {
  if (s >= 80) return "#10b981";
  if (s >= 60) return "#f59e0b";
  return "#ef4444";
}

/** Spread heatmap points around the region's centroid using a deterministic
 *  hash of the PNU so re-renders don't rearrange them. */
function pseudoLatLng(pnu: string, idx: number): { lat: number; lng: number } {
  const seed = hashCode(pnu);
  // Region centroid is encoded in the first 5 digits of PNU.
  const regionCode = pnu.slice(0, 5);
  const centroids: Record<string, { lat: number; lng: number }> = {
    "41280": { lat: 37.6166, lng: 126.7146 },
    "41220": { lat: 36.9921, lng: 127.1128 },
    "41131": { lat: 37.352, lng: 127.1086 },
    "11680": { lat: 37.5172, lng: 127.0473 },
  };
  const base = centroids[regionCode] ?? { lat: 37.5665, lng: 126.978 };
  const angle = (seed % 360) * (Math.PI / 180);
  const r = 0.005 + (idx % 8) * 0.0015;
  return {
    lat: base.lat + Math.sin(angle) * r,
    lng: base.lng + Math.cos(angle) * r * 1.2,
  };
}

function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}
