import { Circle, CustomOverlayMap, MapMarker } from "react-kakao-maps-sdk";

import KakaoMap from "./KakaoMap";
import type { ScenarioAZone } from "@/api/schemas";

interface Props {
  center: { lat: number; lng: number };
  zones: ScenarioAZone[];
  rings?: number[]; // metres
}

const COLORS = ["#fb923c", "#f43f5e", "#9333ea"];

/** Concentric impact rings around a project + admin-area markers.
 *  Each marker is colored by which ring it falls into. */
export default function ImpactZoneMap({
  center,
  zones,
  rings = [1_000, 3_000, 5_000],
}: Props) {
  return (
    <KakaoMap center={center} level={7} ariaLabel="영향권 지도">
      {rings.map((radius, i) => (
        <Circle
          key={radius}
          center={center}
          radius={radius}
          strokeWeight={1.5}
          strokeColor={COLORS[i] ?? "#94a3b8"}
          strokeOpacity={0.7}
          strokeStyle="dashed"
          fillColor={COLORS[i] ?? "#94a3b8"}
          fillOpacity={0.05}
        />
      ))}

      <MapMarker
        position={center}
        title="사업지"
        image={{
          src: "data:image/svg+xml;utf-8," +
            encodeURIComponent(`
              <svg xmlns='http://www.w3.org/2000/svg' width='28' height='34' viewBox='0 0 28 34'>
                <path fill='#0f172a' d='M14 0a14 14 0 0 0-14 14c0 9 14 20 14 20s14-11 14-20A14 14 0 0 0 14 0z'/>
                <circle cx='14' cy='14' r='6' fill='#fff'/>
              </svg>`),
          size: { width: 28, height: 34 },
          options: { offset: { x: 14, y: 34 } },
        }}
      />

      {zones.slice(0, 50).map((z) => (
        <CustomOverlayMap
          key={z.admin_code}
          position={impactPos(center, z)}
          xAnchor={0.5}
          yAnchor={1}
        >
          <span
            className="rounded-full border border-white/70 bg-slate-900/80 px-2 py-0.5 text-[11px] font-medium text-white shadow"
            style={{ backgroundColor: pickColor(z.distance_m, rings) }}
          >
            {z.admin_name}
          </span>
        </CustomOverlayMap>
      ))}
    </KakaoMap>
  );
}

function pickColor(distance_m: number, rings: number[]): string {
  for (let i = 0; i < rings.length; i++) {
    if (distance_m <= rings[i]) return `${COLORS[i] ?? "#475569"}cc`;
  }
  return "#475569cc";
}

// Stage 1: zones don't carry their centroid; we approximate by offsetting
// from the project centre using a tiny deterministic spiral so labels don't
// collide. ETL will populate real centroids in Phase 2.
function impactPos(
  center: { lat: number; lng: number },
  z: ScenarioAZone,
): { lat: number; lng: number } {
  const seed = hashCode(z.admin_code);
  const angle = ((seed % 360) * Math.PI) / 180;
  const r = (z.distance_m / 110_000) * 0.95;
  return {
    lat: center.lat + Math.sin(angle) * r,
    lng: center.lng + Math.cos(angle) * r * 1.2,
  };
}

function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}
