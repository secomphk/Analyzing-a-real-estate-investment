import { useEffect, useState } from "react";

const SDK_BASE = "https://dapi.kakao.com/v2/maps/sdk.js";

let sdkPromise: Promise<void> | null = null;

function loadSdk(appKey: string): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.kakao?.maps) return Promise.resolve();
  if (sdkPromise) return sdkPromise;

  sdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.async = true;
    script.src = `${SDK_BASE}?appkey=${appKey}&autoload=false&libraries=services,clusterer`;
    script.onload = () => {
      window.kakao!.maps.load(() => resolve());
    };
    script.onerror = () => reject(new Error("Kakao SDK load failed"));
    document.head.appendChild(script);
  });

  return sdkPromise;
}

export interface KakaoLoaderState {
  ready: boolean;
  error: string | null;
}

/** Lazily injects the Kakao Maps SDK and resolves with ``ready=true``.
 *
 *  When ``VITE_KAKAO_MAP_KEY`` is missing the hook stays in
 *  ``ready=false`` with a helpful error so map components can render a
 *  graceful fallback instead of a blank rectangle. */
export function useKakaoLoader(): KakaoLoaderState {
  const appKey = (import.meta.env.VITE_KAKAO_MAP_KEY as string | undefined) ?? "";
  const [state, setState] = useState<KakaoLoaderState>({
    ready: !!window.kakao?.maps,
    error: appKey ? null : "VITE_KAKAO_MAP_KEY not set",
  });

  useEffect(() => {
    if (!appKey) return;
    if (window.kakao?.maps) {
      setState({ ready: true, error: null });
      return;
    }
    let cancelled = false;
    loadSdk(appKey)
      .then(() => {
        if (!cancelled) setState({ ready: true, error: null });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ ready: false, error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [appKey]);

  return state;
}

declare global {
  interface Window {
    kakao?: {
      maps: {
        load: (cb: () => void) => void;
        // The full SDK surface lives on react-kakao-maps-sdk's types — we
        // only depend on the loader gate here.
        [key: string]: unknown;
      };
    };
  }
}
