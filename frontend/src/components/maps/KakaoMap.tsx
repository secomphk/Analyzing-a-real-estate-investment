import { type ReactNode } from "react";
import { Map } from "react-kakao-maps-sdk";
import { MapPinOff } from "lucide-react";

import { useKakaoLoader } from "./useKakaoLoader";

export interface KakaoMapProps {
  center: { lat: number; lng: number };
  level?: number;
  className?: string;
  ariaLabel?: string;
  children?: ReactNode;
  onIdle?: (map: kakao.maps.Map) => void;
}

/** Thin wrapper around `react-kakao-maps-sdk`'s ``Map``.
 *
 *  Renders a fallback when the SDK is not configured / fails to load so the
 *  rest of the page stays usable.
 */
export default function KakaoMap({
  center,
  level = 6,
  className = "h-[420px] w-full rounded-xl border border-slate-200 bg-slate-50",
  ariaLabel = "지도",
  children,
  onIdle,
}: KakaoMapProps) {
  const { ready, error } = useKakaoLoader();

  if (!ready) {
    return (
      <div
        role="status"
        aria-label={ariaLabel}
        className={`${className} grid place-items-center text-center text-sm text-slate-500`}
      >
        <div className="flex flex-col items-center gap-2 px-6">
          <MapPinOff className="h-6 w-6 text-slate-400" />
          <p>지도 SDK를 사용할 수 없습니다.</p>
          {error && <p className="text-xs text-slate-400">{error}</p>}
          <p className="text-xs text-slate-400">
            <code>.env</code>에 <code>VITE_KAKAO_MAP_KEY</code>를 설정하면
            지도 기능이 활성화됩니다.
          </p>
        </div>
      </div>
    );
  }

  return (
    <Map
      center={center}
      level={level}
      className={className}
      aria-label={ariaLabel}
      onIdle={onIdle}
    >
      {children}
    </Map>
  );
}
