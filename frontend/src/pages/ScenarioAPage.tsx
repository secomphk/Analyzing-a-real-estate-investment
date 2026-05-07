import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useProject, useProjectList, useScenarioA } from "@/hooks/useProjects";
import { useNumericUrlParam } from "@/hooks/useUrlParam";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { EmptyState } from "@/components/states/EmptyState";
import { CacheBadge } from "@/components/states/CacheBadge";
import ImpactZoneMap from "@/components/maps/ImpactZoneMap";
import { SCENARIO_THEME } from "@/theme/scenarios";
import { formatPct } from "@/lib/format";

export default function ScenarioAPage() {
  const [projectId, setProjectId] = useNumericUrlParam("project");
  const projectsQ = useProjectList({ limit: 50 });
  const detailQ = useProject(projectId);
  const analysisQ = useScenarioA(projectId ? { project_id: projectId } : null);

  const projects = projectsQ.data?.data ?? [];

  return (
    <div className="space-y-6">
      <Header />

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <ProjectPicker
          projects={projects}
          loading={projectsQ.isLoading}
          error={projectsQ.error}
          onRetry={() => projectsQ.refetch()}
          selectedId={projectId}
          onSelect={(id) => setProjectId(id)}
        />

        {projectId == null ? (
          <EmptyState
            title="분석할 사업을 선택하세요"
            detail="좌측 목록에서 호재 사업을 고르면 영향권과 가격 회귀를 표시합니다."
          />
        ) : (
          <ProjectAnalysis
            detailQ={detailQ}
            analysisQ={analysisQ}
          />
        )}
      </div>
    </div>
  );
}

function Header() {
  const t = SCENARIO_THEME.a;
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-orange-500">
          {t.label}
        </p>
        <h1 className="text-2xl font-bold text-slate-900">{t.subtitle}</h1>
        <p className="mt-1 text-sm text-slate-500">
          공공주택지구 보상 발표가 인근 토지 거래가에 미치는 영향을 거리×시간 두 축으로
          회귀합니다.
        </p>
      </div>
    </div>
  );
}

interface PickerProps {
  projects: Array<{ id: number; name: string; project_type: string; region_code: string | null }>;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}

function ProjectPicker({ projects, loading, error, onRetry, selectedId, onSelect }: PickerProps) {
  return (
    <aside aria-label="사업 선택" className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-700">사업 선택</h2>
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : projects.length === 0 ? (
        <EmptyState
          title="등록된 사업이 없습니다"
          detail="시드 데이터(python -m src.scripts.seed --scenario a)를 먼저 실행해주세요."
        />
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => {
            const active = p.id === selectedId;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => onSelect(active ? null : p.id)}
                  className={
                    "block w-full rounded-lg border p-3 text-left transition " +
                    (active
                      ? "border-orange-300 bg-orange-50 ring-1 ring-orange-200"
                      : "border-slate-200 bg-white hover:border-slate-300")
                  }
                  aria-pressed={active}
                >
                  <p className="text-sm font-semibold text-slate-900">{p.name}</p>
                  <p className="text-xs text-slate-500">
                    {p.project_type}
                    {p.region_code ? ` · ${p.region_code}` : ""}
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

interface AnalysisProps {
  detailQ: ReturnType<typeof useProject>;
  analysisQ: ReturnType<typeof useScenarioA>;
}

function ProjectAnalysis({ detailQ, analysisQ }: AnalysisProps) {
  if (detailQ.isLoading || analysisQ.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-[420px] w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (analysisQ.error) {
    return <ErrorState error={analysisQ.error} onRetry={() => analysisQ.refetch()} />;
  }
  if (!analysisQ.data) {
    return <EmptyState title="분석 결과를 받지 못했습니다" />;
  }
  const detail = detailQ.data?.data;
  const result = analysisQ.data.data;
  const meta = analysisQ.data.meta;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              {detail?.name ?? `프로젝트 ${result.project_id}`}
            </h2>
            <p className="text-sm text-slate-500">
              보상 기준 시점: <span className="font-medium">{result.anchor_date}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <CacheBadge meta={meta} />
            {meta.confidence_score != null && (
              <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[11px] font-medium text-orange-700">
                신뢰도 {(meta.confidence_score * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      </div>

      <ImpactZoneCard result={result} />
      <UpliftLineChart result={result} />
      <RoadsBarChart result={result} />
    </div>
  );
}

function ImpactZoneCard({ result }: { result: NonNullable<ReturnType<typeof useScenarioA>["data"]>["data"] }) {
  // We don't get the project's lat/lng from this endpoint — pick the first
  // close zone as the centroid proxy. ETL adds real centroid in Phase 2.
  const center = useMemo(() => {
    const closest = [...result.zones].sort((a, b) => a.distance_m - b.distance_m)[0];
    if (closest && closest.admin_code) return { lat: 37.6, lng: 126.7 };
    return { lat: 37.5665, lng: 126.978 };
  }, [result.zones]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">영향권 지도</h3>
      <ImpactZoneMap center={center} zones={result.zones} />
      {result.zones.length === 0 && (
        <p className="mt-2 text-xs text-slate-400">
          반경 내 행정구역이 매핑되지 않았습니다.
        </p>
      )}
    </section>
  );
}

function UpliftLineChart({ result }: { result: NonNullable<ReturnType<typeof useScenarioA>["data"]>["data"] }) {
  const data = useMemo(() => {
    if (result.impact_series.length === 0) return [];
    const horizons = result.impact_series[0].points.map((p) => p.months_after_anchor);
    return horizons.map((months) => {
      const row: Record<string, number | string> = { months };
      for (const series of result.impact_series) {
        const point = series.points.find((p) => p.months_after_anchor === months);
        row[`${series.distance_m}m`] = point ? point.expected_uplift_pct : 0;
      }
      return row;
    });
  }, [result.impact_series]);

  if (data.length === 0) {
    return null;
  }
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">
        거리별·시점별 예상 상승률
      </h3>
      <div className="h-72 w-full">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="months" tickFormatter={(m) => `${m}m`} />
            <YAxis tickFormatter={(v) => formatPct(v as number, 0)} />
            <Tooltip
              formatter={(v: number) => formatPct(v)}
              labelFormatter={(l) => `${l}개월 후`}
            />
            <Legend />
            {result.impact_series.map((s, idx) => (
              <Line
                key={s.distance_m}
                dataKey={`${s.distance_m}m`}
                name={`${s.distance_m}m`}
                strokeWidth={2}
                dot={false}
                stroke={LINE_COLORS[idx % LINE_COLORS.length]}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

const LINE_COLORS = ["#f43f5e", "#fb923c", "#f59e0b", "#16a34a", "#0ea5e9", "#8b5cf6"];

function RoadsBarChart({ result }: { result: NonNullable<ReturnType<typeof useScenarioA>["data"]>["data"] }) {
  if (result.roads.length === 0) return null;
  const data = result.roads.slice(0, 8).map((r) => ({
    name: r.name,
    weight: r.weight,
  }));
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">
        인접 도로 영향 가중치
      </h3>
      <div className="h-64 w-full">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="name" interval={0} angle={-15} textAnchor="end" height={60} />
            <YAxis />
            <Tooltip />
            <Bar dataKey="weight" fill="#fb923c" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
