import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useStoreList } from "@/hooks/useStores";
import { useStoreImpact } from "@/hooks/useScenarioC";
import StoreMap from "@/components/maps/StoreMap";
import { Skeleton } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/ErrorState";
import { EmptyState } from "@/components/states/EmptyState";
import { CacheBadge } from "@/components/states/CacheBadge";
import { useNumericUrlParam, useUrlParam } from "@/hooks/useUrlParam";
import { formatPct } from "@/lib/format";
import type { StoreSummary } from "@/api/schemas";

const BRANDS = ["스타벅스", "맥도날드", "버거킹", "메가커피", "투썸플레이스"];

/** Mode 1: store catalog map → click marker → halo-effect detail. */
export default function StoreImpactMode() {
  const [storeId, setStoreId] = useNumericUrlParam("store");
  const [brandFilter, setBrandFilter] = useUrlParam("brand");
  const [, setRegionFilter] = useUrlParam("region");
  const region = useUrlParam("region")[0];

  const storeQ = useStoreList({
    brand: brandFilter || undefined,
    region_code: region || undefined,
    limit: 200,
  });
  const stores = storeQ.data?.data ?? [];
  // Stage 1: stores list endpoint doesn't include lat/lng. We synthesise a
  // tiny scatter so the marker positions stay stable across renders. The
  // /stores/{id} endpoint returns real coordinates which we use below.
  const latLngs = useFakeLatLngs(stores);

  const impactQ = useStoreImpact(storeId ? { store_id: storeId } : null);

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr_360px]">
      <aside className="space-y-3">
        <Filter title="브랜드">
          <div className="flex flex-wrap gap-1.5">
            <FilterPill label="전체" active={!brandFilter} onClick={() => setBrandFilter(undefined)} />
            {BRANDS.map((b) => (
              <FilterPill
                key={b}
                label={b}
                active={brandFilter === b}
                onClick={() => setBrandFilter(brandFilter === b ? undefined : b)}
              />
            ))}
          </div>
        </Filter>
        <Filter title="시군구">
          <input
            type="text"
            placeholder="예: 41280"
            defaultValue={region ?? ""}
            onBlur={(e) => setRegionFilter(e.target.value || undefined)}
            className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm focus:border-emerald-400 focus:outline-none"
          />
        </Filter>
        <p className="text-xs text-slate-500">
          매장 {stores.length.toLocaleString()}개 표시 중
        </p>
      </aside>

      <section className="rounded-xl border border-slate-200 bg-white p-2">
        {storeQ.isLoading ? (
          <Skeleton className="h-[420px] w-full" />
        ) : storeQ.error ? (
          <ErrorState error={storeQ.error} onRetry={() => storeQ.refetch()} />
        ) : (
          <StoreMap
            stores={stores}
            storeLatLng={latLngs}
            selectedId={storeId}
            onSelect={(id) => setStoreId(id)}
          />
        )}
      </section>

      <aside aria-label="매장 상세">
        {storeId == null ? (
          <EmptyState title="매장을 선택하세요" detail="지도에서 마커를 클릭하면 상세 분석을 표시합니다." />
        ) : impactQ.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : impactQ.error ? (
          <ErrorState error={impactQ.error} onRetry={() => impactQ.refetch()} />
        ) : impactQ.data ? (
          <ImpactDetail data={impactQ.data.data} meta={impactQ.data.meta} />
        ) : null}
      </aside>
    </div>
  );
}

function ImpactDetail({
  data,
  meta,
}: {
  data: NonNullable<ReturnType<typeof useStoreImpact>["data"]>["data"];
  meta: NonNullable<ReturnType<typeof useStoreImpact>["data"]>["meta"];
}) {
  const chartData = useMemo(() => {
    return data.bands
      .filter((b) => b.horizon === "+1y")
      .map((b) => ({
        band: `${b.band_m}m`,
        halo: b.halo_pct ?? 0,
        baseline: b.baseline_pct ?? 0,
      }));
  }, [data.bands]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Halo Effect</h3>
        <CacheBadge meta={meta} />
      </div>
      <p className="text-xs text-slate-500">
        개점일: <span className="font-medium text-slate-700">{data.open_date}</span>
      </p>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <p className="mb-2 text-xs font-medium text-slate-500">+1년 거리대 변화</p>
        <div className="h-56 w-full">
          <ResponsiveContainer>
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis dataKey="band" />
              <YAxis tickFormatter={(v) => formatPct(v as number, 0)} />
              <Tooltip formatter={(v: number) => formatPct(v)} />
              <Legend />
              <Bar dataKey="halo" name="Halo">
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.halo >= 0 ? "#10b981" : "#ef4444"} />
                ))}
              </Bar>
              <Bar dataKey="baseline" name="Baseline" fill="#94a3b8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <p className="mb-2 text-xs font-medium text-slate-500">전체 거리대·시점 매트릭스</p>
        <table className="w-full text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1.5 text-left">거리</th>
              {(["+1y", "+3y", "+5y"] as const).map((h) => (
                <th key={h} className="py-1.5 text-right">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from(new Set(data.bands.map((b) => b.band_m))).map((band) => (
              <tr key={band} className="border-t border-slate-100">
                <td className="py-1.5 text-slate-700">{band}m</td>
                {(["+1y", "+3y", "+5y"] as const).map((h) => {
                  const cell = data.bands.find((b) => b.band_m === band && b.horizon === h);
                  return (
                    <td
                      key={h}
                      className="py-1.5 text-right font-medium"
                      style={{ color: cell?.halo_pct == null ? "#94a3b8" : cell.halo_pct >= 0 ? "#10b981" : "#ef4444" }}
                    >
                      {cell?.halo_pct == null ? "—" : formatPct(cell.halo_pct)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Filter({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs font-semibold text-slate-500">{title}</p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "rounded-full px-2.5 py-1 text-xs font-medium " +
        (active ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200")
      }
    >
      {label}
    </button>
  );
}

/** Synthesise stable lat/lng for stores that didn't ship coordinates in the
 *  list endpoint. Real coords arrive from /stores/{id}; this only matters
 *  for the marker layout in the catalogue map. */
function useFakeLatLngs(stores: StoreSummary[]): Map<number, { lat: number; lng: number }> {
  return useMemo(() => {
    const m = new Map<number, { lat: number; lng: number }>();
    // Approximate centroids for the seed regions.
    const centroids: Record<string, { lat: number; lng: number }> = {
      "4128010100": { lat: 37.6166, lng: 126.7146 },
      "4128010300": { lat: 37.6062, lng: 126.7341 },
      "4128010400": { lat: 37.628, lng: 126.6699 },
      "4128010500": { lat: 37.6517, lng: 126.6534 },
      "4128025000": { lat: 37.6138, lng: 126.7674 },
      "4128025500": { lat: 37.6643, lng: 126.6234 },
      "4122010100": { lat: 36.9921, lng: 127.1128 },
      "4122010200": { lat: 36.9803, lng: 127.0823 },
      "4122010300": { lat: 36.982, lng: 127.0997 },
      "4122010400": { lat: 37.0099, lng: 127.0644 },
      "4122010500": { lat: 36.989, lng: 127.0846 },
      "4122025000": { lat: 37.0327, lng: 127.0438 },
      "41131": { lat: 37.352, lng: 127.1086 },
      "11680": { lat: 37.5172, lng: 127.0473 },
    };
    for (const s of stores) {
      const base = centroids[s.region_code ?? ""] ?? { lat: 37.5665, lng: 126.978 };
      // Stable jitter from the store id.
      const j = ((s.id * 9301 + 49297) % 233280) / 233280;
      m.set(s.id, {
        lat: base.lat + (j - 0.5) * 0.01,
        lng: base.lng + (((s.id * 49297) % 233280) / 233280 - 0.5) * 0.01,
      });
    }
    return m;
  }, [stores]);
}
