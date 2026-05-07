import { Link } from "react-router-dom";
import { Store } from "lucide-react";

import { useStore } from "@/hooks/useStores";
import { Skeleton } from "@/components/states/Loading";
import { BRAND_COLORS } from "@/theme/scenarios";

interface Item {
  store_id: number;
  score: number;
  rank: number;
}

export function SimilarStoresCard({ items }: { items: Item[] }) {
  if (!items || items.length === 0) return null;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-sm font-semibold text-slate-700">유사 매장 Top {items.length}</h3>
      <ul className="mt-3 space-y-2">
        {items.slice(0, 5).map((it) => (
          <SimilarStoreRow key={it.store_id} item={it} />
        ))}
      </ul>
    </section>
  );
}

function SimilarStoreRow({ item }: { item: Item }) {
  const q = useStore(item.store_id);
  const store = q.data?.data;
  const accent = store ? BRAND_COLORS[store.brand_name] ?? "#475569" : "#475569";
  return (
    <li className="flex items-center gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <span
        className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full text-xs font-bold text-white"
        style={{ backgroundColor: accent }}
      >
        #{item.rank}
      </span>
      <div className="min-w-0 flex-1">
        {q.isLoading ? (
          <>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="mt-1 h-3 w-1/2" />
          </>
        ) : store ? (
          <>
            <p className="truncate text-sm font-medium text-slate-900">
              {store.brand_name} · {store.name}
            </p>
            <p className="truncate text-xs text-slate-500">
              {store.store_type} · {store.address ?? "주소 정보 없음"}
            </p>
          </>
        ) : (
          <p className="text-sm text-slate-400">매장 #{item.store_id}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">
          {(item.score * 100).toFixed(0)}
        </span>
        <Link
          to={`/scenario-c?mode=impact&store=${item.store_id}`}
          className="rounded-md bg-white p-1.5 text-slate-400 ring-1 ring-slate-200 hover:text-slate-600"
          aria-label="매장 분석으로 열기"
        >
          <Store className="h-3.5 w-3.5" />
        </Link>
      </div>
    </li>
  );
}
