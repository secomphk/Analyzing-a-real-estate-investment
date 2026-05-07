import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Lightbulb } from "lucide-react";

import { useNumericUrlParam } from "@/hooks/useUrlParam";
import { useRoadList, useScenarioB } from "@/hooks/useRoads";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { EmptyState } from "@/components/states/EmptyState";
import { CacheBadge } from "@/components/states/CacheBadge";
import { SCENARIO_THEME } from "@/theme/scenarios";
import { formatInt } from "@/lib/format";
import type { Meta, ScenarioBResponse } from "@/api/schemas";

export default function ScenarioBPage() {
  const [roadId, setRoadId] = useNumericUrlParam("road");
  const roadsQ = useRoadList({ limit: 50 });
  const analysisQ = useScenarioB(roadId ? { road_id: roadId } : null);

  const roads = roadsQ.data?.data ?? [];

  return (
    <div className="space-y-6">
      <Header />

      <div className="flex flex-wrap items-center gap-2">
        {roadsQ.isLoading ? (
          <Skeleton className="h-9 w-48" />
        ) : (
          roads.map((r) => {
            const active = r.id === roadId;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => setRoadId(active ? null : r.id)}
                className={
                  "rounded-full px-4 py-1.5 text-sm font-medium transition " +
                  (active
                    ? "bg-violet-600 text-white"
                    : "bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-slate-300")
                }
                aria-pressed={active}
              >
                {r.name}
                {r.route_no ? <span className="ml-1 opacity-60">· {r.route_no}</span> : null}
              </button>
            );
          })
        )}
      </div>

      {roadId == null ? (
        <EmptyState
          title="분석할 도로를 선택하세요"
          detail="위 토글에서 도로 구간을 선택하면 7년치 시계열을 분석합니다."
        />
      ) : analysisQ.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : analysisQ.error ? (
        <ErrorState error={analysisQ.error} onRetry={() => analysisQ.refetch()} />
      ) : analysisQ.data ? (
        <ScenarioBResults data={analysisQ.data.data} meta={analysisQ.data.meta} />
      ) : null}
    </div>
  );
}

function Header() {
  const t = SCENARIO_THEME.b;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-violet-500">{t.label}</p>
      <h1 className="text-2xl font-bold text-slate-900">{t.subtitle}</h1>
      <p className="mt-1 text-sm text-slate-500">
        도로 단계 진행, 인근 행정동 인구, 통행량의 시간별 패턴을 함께 보여줍니다.
      </p>
    </div>
  );
}

function ScenarioBResults({
  data,
  meta,
}: {
  data: ScenarioBResponse;
  meta: Meta;
}) {
  const series = useMemo(
    () =>
      data.time_points.map((p) => ({
        ym: p.year_month,
        progress: Math.round(p.road_progress * 100),
        population: p.population,
        aadt: p.aadt,
      })),
    [data.time_points],
  );

  if (series.length === 0) {
    return (
      <EmptyState
        title="시계열 데이터가 없습니다"
        detail="ETL을 먼저 실행하거나 다른 도로를 선택해주세요."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-700">3변수 시계열</h2>
          <CacheBadge meta={meta} />
        </div>
        <div className="mt-3 h-80 w-full">
          <ResponsiveContainer>
            <ComposedChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis dataKey="ym" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tickFormatter={(v) => formatInt(v as number)} />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                yAxisId="left"
                dataKey="aadt"
                name="통행량(AADT)"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                yAxisId="left"
                dataKey="population"
                name="인구"
                stroke="#8b5cf6"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                yAxisId="right"
                dataKey="progress"
                name="도로 진행률(%)"
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="4 2"
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <CorrelationCard data={data} />
      <InsightsCard data={data} />
    </div>
  );
}

function CorrelationCard({ data }: { data: ScenarioBResponse }) {
  if (data.correlation_variables.length === 0) return null;
  return (
    <section className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-700">상관 행렬</h3>
        <table className="mt-3 w-full text-center text-sm">
          <thead>
            <tr>
              <th className="px-2 py-1.5 text-xs font-medium text-slate-400" />
              {data.correlation_variables.map((v) => (
                <th key={v} className="px-2 py-1.5 text-xs font-medium text-slate-500">
                  {v}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.correlation_matrix.map((row, i) => (
              <tr key={i}>
                <th
                  scope="row"
                  className="px-2 py-1.5 text-xs font-medium text-slate-500"
                >
                  {data.correlation_variables[i]}
                </th>
                {row.map((v, j) => (
                  <td
                    key={j}
                    className="px-2 py-1.5 text-sm font-medium"
                    style={{ background: corrTint(v) }}
                  >
                    {v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-700">선행/후행 관계</h3>
        {data.lead_lag ? (
          <div className="mt-3 space-y-2">
            <p className="text-sm text-slate-700">
              <span className="font-medium">{data.lead_lag.a}</span> ↔{" "}
              <span className="font-medium">{data.lead_lag.b}</span>
            </p>
            <div className="rounded-lg bg-violet-50 p-3 text-sm text-violet-800">
              분류:{" "}
              <span className="font-semibold">{data.lead_lag.classification}</span>{" "}
              · 최적 시차{" "}
              <span className="font-semibold">{data.lead_lag.best_lag_months}개월</span>
              · 상관{" "}
              <span className="font-semibold">{data.lead_lag.best_correlation.toFixed(2)}</span>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-400">선행/후행 결과를 받지 못했습니다.</p>
        )}
      </div>
    </section>
  );
}

function InsightsCard({ data }: { data: ScenarioBResponse }) {
  if (data.insights.length === 0) return null;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
        <Lightbulb className="h-4 w-4 text-amber-500" /> 핵심 인사이트
      </h3>
      <ul className="mt-3 space-y-2.5">
        {data.insights.map((i, idx) => (
          <li
            key={idx}
            className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5"
          >
            <p className="text-sm font-medium text-slate-900">{i.title}</p>
            <p className="text-sm text-slate-600">{i.detail}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function corrTint(v: number): string {
  const clamped = Math.max(-1, Math.min(1, v));
  if (clamped >= 0) {
    const a = Math.round(clamped * 200);
    return `rgba(16, 185, 129, ${(a / 800).toFixed(3)})`;
  }
  const a = Math.round(-clamped * 200);
  return `rgba(244, 63, 94, ${(a / 800).toFixed(3)})`;
}
