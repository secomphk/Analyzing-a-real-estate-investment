import { Database, Zap } from "lucide-react";

interface Props {
  meta?: { cache_hit?: boolean; computation_time_ms?: number };
}

/** Tiny badge shown in card headers — surfaces cache hits + timing. */
export function CacheBadge({ meta }: Props) {
  if (!meta) return null;
  const ms = meta.computation_time_ms;
  if (meta.cache_hit) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
        <Database className="h-3 w-3" />
        캐시됨
        {ms != null && <span className="text-slate-400">· {ms.toFixed(0)}ms</span>}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
      <Zap className="h-3 w-3" />
      실시간
      {ms != null && <span className="text-emerald-500">· {ms.toFixed(0)}ms</span>}
    </span>
  );
}
