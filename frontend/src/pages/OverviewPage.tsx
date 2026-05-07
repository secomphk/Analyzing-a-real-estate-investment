import { Link } from "react-router-dom";
import {
  Building2,
  ChevronRight,
  MapPinned,
  Network,
  Sparkles,
  Store,
} from "lucide-react";

import { SCENARIO_THEME, type ScenarioKey } from "@/theme/scenarios";
import { useProjectList } from "@/hooks/useProjects";
import { useRoadList } from "@/hooks/useRoads";
import { useStoreList } from "@/hooks/useStores";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { cn } from "@/lib/cn";

const TILES: Array<{
  to: string;
  scenario: ScenarioKey;
  Icon: typeof Building2;
  desc: string;
}> = [
  {
    to: "/scenario-a",
    scenario: "a",
    Icon: Building2,
    desc: "공공주택지구·도시개발 보상금이 인근 토지가에 미치는 영향을 거리·시간 두 축으로 회귀합니다.",
  },
  {
    to: "/scenario-b",
    scenario: "b",
    Icon: MapPinned,
    desc: "도로 확장 단계 × 주변 인구 × 통행량의 3변수 패턴을 시계열로 분석합니다.",
  },
  {
    to: "/scenario-c",
    scenario: "c",
    Icon: Store,
    desc: "DT/DI 매장 입지 적합도, 유사 매장, 후보 토지를 한 화면에서 평가합니다.",
  },
];

export default function OverviewPage() {
  return (
    <div className="space-y-8">
      <Hero />
      <SummaryCards />
      <SynergyDiagram />
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden rounded-2xl bg-slate-900 p-8 text-white sm:p-10">
      <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-emerald-500/30 blur-3xl" />
      <div className="absolute -left-12 bottom-0 h-48 w-48 rounded-full bg-violet-500/30 blur-3xl" />
      <div className="relative">
        <p className="text-sm font-medium text-emerald-300">Stage 4 — 통합 대시보드</p>
        <h1 className="mt-2 text-3xl font-bold sm:text-4xl">
          호재·도로·매장을 한 시야에서 분석
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-slate-300 sm:text-base">
          시나리오 A·B·C가 하나의 데이터 모델 위에서 동작합니다. 좌측 메뉴에서
          분석을 선택하거나 아래 카드로 바로 진입하세요.
        </p>
      </div>
    </section>
  );
}

function SummaryCards() {
  return (
    <section aria-label="시나리오 진입" className="grid gap-4 md:grid-cols-3">
      {TILES.map(({ to, scenario, Icon, desc }) => {
        const t = SCENARIO_THEME[scenario];
        return (
          <Link
            key={scenario}
            to={to}
            className="group block rounded-xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"
          >
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  "grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br text-white",
                  t.gradient,
                )}
              >
                <Icon className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {t.label}
                </p>
                <h3 className="text-base font-semibold text-slate-900">
                  {t.subtitle}
                </h3>
              </div>
            </div>
            <p className="mt-3 text-sm text-slate-600">{desc}</p>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-slate-700 group-hover:text-slate-900">
              살펴보기 <ChevronRight className="h-4 w-4" />
            </span>
          </Link>
        );
      })}
    </section>
  );
}

function SynergyDiagram() {
  const projects = useProjectList({ limit: 5 });
  const roads = useRoadList({ limit: 5 });
  const stores = useStoreList({ limit: 5 });

  return (
    <section className="grid gap-6 md:grid-cols-3">
      <DataCard
        title="추적 중인 호재"
        scenario="a"
        Icon={Building2}
        loading={projects.isLoading}
        error={projects.error}
        onRetry={() => projects.refetch()}
        items={(projects.data?.data ?? []).map(
          (p) => `${p.name} · ${p.project_type}`,
        )}
      />
      <DataCard
        title="추적 중인 도로"
        scenario="b"
        Icon={MapPinned}
        loading={roads.isLoading}
        error={roads.error}
        onRetry={() => roads.refetch()}
        items={(roads.data?.data ?? []).map(
          (r) => `${r.name}${r.route_no ? ` · ${r.route_no}` : ""}`,
        )}
      />
      <DataCard
        title="등록된 매장"
        scenario="c"
        Icon={Store}
        loading={stores.isLoading}
        error={stores.error}
        onRetry={() => stores.refetch()}
        items={(stores.data?.data ?? []).map(
          (s) => `${s.brand_name} · ${s.name} (${s.store_type})`,
        )}
      />
      <div className="md:col-span-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex items-start gap-3">
            <Network className="mt-0.5 h-5 w-5 text-slate-500" />
            <div>
              <h3 className="text-sm font-semibold text-slate-900">시너지 흐름</h3>
              <p className="mt-1 text-sm text-slate-600">
                <span className="font-medium text-orange-600">A</span>의 보상금
                지구 발표 → <span className="font-medium text-violet-600">B</span>의
                도로 확장 → <span className="font-medium text-emerald-600">C</span>의
                매장 진출 가능성으로 이어지는 가치 흐름을 추적합니다.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

interface DataCardProps {
  title: string;
  scenario: ScenarioKey;
  Icon: typeof Building2;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  items: string[];
}

function DataCard({ title, scenario, Icon, loading, error, onRetry, items }: DataCardProps) {
  const t = SCENARIO_THEME[scenario];
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Icon className={cn("h-4 w-4")} style={{ color: t.accent }} />
          {title}
        </h3>
        <Sparkles className="h-3.5 w-3.5 text-slate-300" />
      </div>
      <div className="mt-3 text-sm text-slate-600">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/6" />
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={onRetry} />
        ) : items.length ? (
          <ul className="space-y-1.5">
            {items.slice(0, 5).map((item, i) => (
              <li key={i} className="truncate">
                · {item}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-400">데이터가 없습니다.</p>
        )}
      </div>
    </div>
  );
}
