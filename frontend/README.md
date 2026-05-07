# RealEstate Analyzer — Frontend

React 18 + TypeScript + Vite + Tailwind, talking to the Stage 3 backend
through TanStack Query and zod.

## Setup

```bash
cd frontend
cp .env.example .env       # set VITE_KAKAO_MAP_KEY for live maps
npm install
npm run dev                # http://localhost:5173, /api proxied to :8000
```

## Pages

| Route             | Page              | Backend endpoints                                  |
| ----------------- | ----------------- | -------------------------------------------------- |
| `/`               | Overview          | GET /projects, /roads, /stores                     |
| `/scenario-a`     | 보상금 영향       | GET /projects, POST /analysis/scenario-a           |
| `/scenario-b`     | 도로×인구×통행량  | GET /roads, POST /analysis/scenario-b              |
| `/scenario-c`     | DT/DI 매장 (3 모드) | GET /stores, POST /analysis/scenario-c/*, /predictions/dt-candidates |
| `/recommend`      | 유사 추천         | POST /recommendations                              |

URL params used to deep-link state:
- `/scenario-a?project=1`
- `/scenario-b?road=1`
- `/scenario-c?mode=impact|suitability|candidates&pnu=...&store=...&region=...`
- `/recommend?tab=a|b|c&base=...`

## Scripts

```bash
npm run dev          # Vite dev server
npm run build        # tsc -b + vite build
npm run typecheck    # tsc --noEmit
npm run test         # vitest run
npm run e2e          # Playwright (requires manual install of browsers)
```

## Layers

```
src/
├── api/            # axios client + zod schemas + per-domain wrappers
├── hooks/          # TanStack Query hooks (useScenarioA/B/C, useStores, ...)
├── components/
│   ├── maps/       # Kakao Maps base + ImpactZone / Store / Heatmap
│   ├── scenarios/c # 3 modes for Scenario C
│   ├── states/     # Loading / Error / Empty / CacheBadge
│   └── widgets/    # SuitabilityGauge, FeatureContribution, RationaleList, …
└── pages/          # 5 route components
```

## Kakao Maps

`react-kakao-maps-sdk` loads the SDK lazily (`useKakaoLoader`). Every map
component renders a graceful fallback when `VITE_KAKAO_MAP_KEY` is missing
so the rest of the page stays usable in environments where the key is not
available (CI, local without an account).
