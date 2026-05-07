import { AlertTriangle, RefreshCw } from "lucide-react";

import { ApiError } from "@/api/client";

interface Props {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}

/** Friendly error card with optional retry. */
export function ErrorState({ error, onRetry, title = "데이터를 불러오지 못했습니다" }: Props) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : String(error ?? "알 수 없는 오류");
  const code = error instanceof ApiError ? error.code : undefined;
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-6 text-rose-900">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-rose-500" />
        <div className="flex-1">
          <h3 className="text-base font-semibold">{title}</h3>
          <p className="mt-1 text-sm text-rose-800/80">{message}</p>
          {code && <p className="mt-0.5 text-xs text-rose-700/60">code: {code}</p>}
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-700"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              다시 시도
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
