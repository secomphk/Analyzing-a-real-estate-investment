import { cn } from "@/lib/cn";

interface SkeletonProps {
  className?: string;
}

/** Shimmering placeholder. Pair with explicit width/height utilities. */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-label="로딩 중"
      className={cn("skeleton rounded-md", className)}
    />
  );
}

/** Big spinner for full-page transitions. Rare — prefer skeletons. */
export function FullPageLoader({ label = "불러오는 중…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-500">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-slate-600" />
      <p className="text-sm">{label}</p>
    </div>
  );
}
