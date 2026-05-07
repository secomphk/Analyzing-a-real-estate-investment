import { Circle } from "react-kakao-maps-sdk";

import KakaoMap from "./KakaoMap";

export interface HeatmapPoint {
  id: string;
  position: { lat: number; lng: number };
  score: number; // 0..100
  label?: string;
}

interface Props {
  center: { lat: number; lng: number };
  points: HeatmapPoint[];
}

/** Stage 1 "heatmap" — colored circles per candidate. Phase 2 swaps in
 *  the real Kakao heatmap WebGL layer once we have ≥1k candidates. */
export default function HeatmapOverlay({ center, points }: Props) {
  return (
    <KakaoMap center={center} level={6} ariaLabel="후보지 히트맵">
      {points.map((p) => (
        <Circle
          key={p.id}
          center={p.position}
          radius={140}
          strokeWeight={1}
          strokeColor="#1e293b"
          strokeOpacity={0.45}
          fillColor={scoreToColor(p.score)}
          fillOpacity={0.55}
        />
      ))}
    </KakaoMap>
  );
}

/** Linear gradient grey → blue → green → yellow → red. */
function scoreToColor(score: number): string {
  const stops = [
    [0, [148, 163, 184]],   // slate-400
    [25, [56, 189, 248]],   // sky-400
    [50, [16, 185, 129]],   // emerald-500
    [75, [234, 179, 8]],    // yellow-500
    [100, [239, 68, 68]],   // red-500
  ] as const;
  const s = Math.max(0, Math.min(100, score));
  for (let i = 0; i < stops.length - 1; i++) {
    const [a, ca] = stops[i];
    const [b, cb] = stops[i + 1];
    if (s >= a && s <= b) {
      const t = (s - a) / (b - a || 1);
      const rgb = ca.map((v, k) => Math.round(v + t * (cb[k] - v)));
      return `rgb(${rgb.join(",")})`;
    }
  }
  return "#475569";
}
