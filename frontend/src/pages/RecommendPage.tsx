import { Link } from "react-router-dom";

import { useUrlParam } from "@/hooks/useUrlParam";
import { useRecommendations } from "@/hooks/useRecommendations";
import { useStoreList } from "@/hooks/useStores";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { EmptyState } from "@/components/states/EmptyState";
import { CacheBadge } from "@/components/states/CacheBadge";
import { cn } from "@/lib/cn";

const TABS = [
  { key: "a", label: "R-A · 호재 지역", help: "입력한 시군구와 유사한 호재 지역" },
  { key: "b", label: "R-B · 도로 패턴", help: "입력한 시군구와 비슷한 도로 시계열을 보이는 곳" },
  { key: "c", label: "R-C · 매장 유사도", help: "입력한 매장과 유사한 매장 (FAISS)" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function RecommendPage() {
  const [tabRaw, setTab] = useUrlParam("tab", "b");
  const tab: TabKey = (TABS.map((t) => t.key) as readonly string[]).includes(tabRaw ?? "")
    ? (tabRaw as TabKey)
    : "b";

  return (
    <div className="space-y-5">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          추천 엔진
        </p>
        <h1 className="text-2xl font-bold text-slate-900">유사 지역·매장 추천</h1>
        <p className="mt-1 text-sm text-slate-500">
          시나리오별 가중 코사인 유사도와 FAISS 인덱스를 모두 활용합니다.
        </p>
      </header>

      <div role="tablist" className="flex flex-wrap gap-2">
        {TABS.map(({ key, label, help }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm font-medium transition",
              tab === key
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-slate-300",
            )}
            title={help}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "a" && <RegionTab placeholder="예: 41280 (김포시)" hint="A" />}
      {tab === "b" && <RegionTab placeholder="예: 41220 (평택시)" hint="B" />}
      {tab === "c" && <StoreTab />}
    </div>
  );
}

function RegionTab({ placeholder, hint }: { placeholder: string; hint: string }) {
  const [code, setCode] = useUrlParam("base");
  const recs = useRecommendations(
    code ? { source_entity_type: "region", source_entity_id: code, top_n: 10 } : null,
  );
  return (
    <div className="space-y-3">
      <input
        type="text"
        defaultValue={code ?? ""}
        onBlur={(e) => setCode(e.target.value || undefined)}
        placeholder={placeholder}
        className="w-full max-w-md rounded-md border border-slate-200 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
      />
      {!code ? (
        <EmptyState title="기준 시군구를 입력하세요" detail={`R-${hint} 추천을 표시합니다.`} />
      ) : recs.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : recs.error ? (
        <ErrorState error={recs.error} onRetry={() => recs.refetch()} />
      ) : recs.data ? (
        <RecGrid
          items={recs.data.data.items}
          meta={recs.data.meta}
          formatHref={(it) =>
            `/scenario-${hint.toLowerCase()}?project=${it.target_entity_id}`
          }
        />
      ) : null}
    </div>
  );
}

function StoreTab() {
  const [storeIdRaw, setStoreIdRaw] = useUrlParam("base");
  const stores = useStoreList({ limit: 50 });
  const recs = useRecommendations(
    storeIdRaw
      ? { source_entity_type: "store", source_entity_id: storeIdRaw, top_n: 10 }
      : null,
  );
  return (
    <div className="space-y-3">
      <select
        value={storeIdRaw ?? ""}
        onChange={(e) => setStoreIdRaw(e.target.value || undefined)}
        className="w-full max-w-md rounded-md border border-slate-200 px-3 py-2 text-sm"
      >
        <option value="">매장을 선택하세요</option>
        {(stores.data?.data ?? []).map((s) => (
          <option key={s.id} value={s.id}>
            {s.brand_name} · {s.name}
          </option>
        ))}
      </select>
      {!storeIdRaw ? (
        <EmptyState title="기준 매장을 선택하세요" />
      ) : recs.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : recs.error ? (
        <ErrorState error={recs.error} onRetry={() => recs.refetch()} />
      ) : recs.data ? (
        <RecGrid
          items={recs.data.data.items}
          meta={recs.data.meta}
          formatHref={(it) => `/scenario-c?mode=impact&store=${it.target_entity_id}`}
        />
      ) : null}
    </div>
  );
}

function RecGrid({
  items,
  meta,
  formatHref,
}: {
  items: Array<{
    target_entity_type: string;
    target_entity_id: string;
    target_label?: string | null;
    score: number;
    rank: number;
  }>;
  meta: { cache_hit?: boolean; computation_time_ms?: number };
  formatHref: (item: { target_entity_id: string }) => string;
}) {
  if (items.length === 0) {
    return <EmptyState title="추천이 없습니다" detail="기준을 변경해보세요." />;
  }
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <CacheBadge meta={meta} />
      </div>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((it) => (
          <li key={`${it.target_entity_type}-${it.target_entity_id}`}>
            <Link
              to={formatHref(it)}
              className="block rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-slate-900 text-xs font-bold text-white">
                  #{it.rank}
                </span>
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                  {(it.score * 100).toFixed(0)}점
                </span>
              </div>
              <p className="mt-3 text-sm font-semibold text-slate-900">
                {it.target_label ?? it.target_entity_id}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {it.target_entity_type} · {it.target_entity_id}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
