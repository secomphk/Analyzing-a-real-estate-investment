import { useMemo } from "react";
import { CustomOverlayMap, MarkerClusterer } from "react-kakao-maps-sdk";

import KakaoMap from "./KakaoMap";
import type { StoreSummary } from "@/api/schemas";
import { BRAND_COLORS } from "@/theme/scenarios";

interface Props {
  stores: StoreSummary[];
  storeLatLng: Map<number, { lat: number; lng: number }>;
  selectedId?: number | null;
  onSelect?: (storeId: number) => void;
  center?: { lat: number; lng: number };
}

/** Brand-colored store markers + clusterer on zoom-out. */
export default function StoreMap({
  stores,
  storeLatLng,
  selectedId,
  onSelect,
  center,
}: Props) {
  const fallbackCenter = useMemo(() => {
    const fromSelection =
      selectedId != null ? storeLatLng.get(selectedId) : undefined;
    if (fromSelection) return fromSelection;
    if (stores.length > 0) {
      const first = storeLatLng.get(stores[0].id);
      if (first) return first;
    }
    return { lat: 37.5665, lng: 126.978 }; // Seoul fallback
  }, [stores, storeLatLng, selectedId]);

  const renderMarker = (s: StoreSummary) => {
    const pos = storeLatLng.get(s.id);
    if (!pos) return null;
    const color = BRAND_COLORS[s.brand_name] ?? "#475569";
    const isSelected = selectedId === s.id;
    return (
      <CustomOverlayMap
        key={s.id}
        position={pos}
        xAnchor={0.5}
        yAnchor={1}
        clickable
      >
        <button
          type="button"
          onClick={() => onSelect?.(s.id)}
          aria-label={`${s.brand_name} ${s.name}`}
          className="group cursor-pointer focus:outline-none"
          style={{ filter: isSelected ? "drop-shadow(0 4px 6px rgba(0,0,0,0.25))" : undefined }}
        >
          <span
            className={
              "block whitespace-nowrap rounded-full border-2 border-white px-2 py-0.5 text-[11px] font-semibold text-white shadow"
            }
            style={{
              backgroundColor: color,
              transform: isSelected ? "scale(1.15)" : "scale(1)",
              transition: "transform 120ms",
            }}
          >
            {s.brand_name}
            <span className="ml-1 opacity-80">{s.store_type}</span>
          </span>
        </button>
      </CustomOverlayMap>
    );
  };

  return (
    <KakaoMap
      center={center ?? fallbackCenter}
      level={9}
      ariaLabel="매장 지도"
    >
      <MarkerClusterer
        averageCenter
        minLevel={9}
        gridSize={60}
        styles={[
          {
            width: "32px",
            height: "32px",
            background: "rgba(15, 23, 42, 0.85)",
            color: "#fff",
            textAlign: "center",
            fontWeight: "600",
            lineHeight: "32px",
            borderRadius: "9999px",
            border: "2px solid white",
          },
        ]}
      >
        {stores.map(renderMarker)}
      </MarkerClusterer>
    </KakaoMap>
  );
}
