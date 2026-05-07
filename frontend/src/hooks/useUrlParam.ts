import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Read a single search param + a setter that preserves all other params.
 *
 *  ``setValue(undefined)`` removes the key. The hook keeps ``replace: true``
 *  by default so back/forward history isn't polluted on every keystroke.
 */
export function useUrlParam(key: string, fallback?: string) {
  const [searchParams, setSearchParams] = useSearchParams();
  const value = searchParams.get(key) ?? fallback;

  const setValue = useCallback(
    (next: string | undefined) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next === undefined || next === "") {
            params.delete(key);
          } else {
            params.set(key, next);
          }
          return params;
        },
        { replace: true },
      );
    },
    [key, setSearchParams],
  );

  return [value, setValue] as const;
}

/** Read a numeric param. Returns ``null`` if missing or not a number. */
export function useNumericUrlParam(key: string) {
  const [raw, setRaw] = useUrlParam(key);
  const num = raw && /^-?\d+$/.test(raw) ? Number(raw) : null;
  const setNum = (n: number | null | undefined) =>
    setRaw(n == null ? undefined : String(n));
  return [num, setNum] as const;
}
