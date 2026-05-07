# Architecture

## System diagram

```
                 ┌────────────────────┐
   Browser ─────►│  Vercel (Frontend) │
                 │   Vite + React     │
                 └─────────┬──────────┘
                           │ HTTPS  /api/*
                           ▼
                 ┌────────────────────┐         ┌──────────────┐
                 │ Railway: backend   │◄────────│   Railway    │
                 │ FastAPI + Uvicorn  │  redis  │   Redis      │
                 └─────┬────┬─────────┘         └──────────────┘
                       │    │
                  SQL  │    │ MLflow REST
                       ▼    ▼
                 ┌──────────┐  ┌──────────────┐
                 │Postgres  │  │  MLflow      │──► S3 (models_artifacts/)
                 │ + PostGIS│  │  Tracking    │
                 └──────────┘  └──────────────┘

                 (CI/CD)        ┌────────────────┐
                 GitHub Actions ─┤   GHCR images  │
                 - backend-ci    └────────────────┘
                 - frontend-ci
                 - deploy-staging  (push main)
                 - deploy-prod     (tag v*.*.*)
                 - ml-retrain      (cron Sat 18:00 UTC)
```

## Layers

### Frontend (`frontend/`)

- **React 18 + TS + Vite** — SPA bundle served by nginx in production.
- **TanStack Query** — server-state cache, 1h staleTime to match the
  backend's Redis TTL.
- **zod** — every backend response is parsed before reaching components.
- **Kakao Maps** — lazy SDK loader; pages render a friendly fallback
  when the key is missing (CI / preview environments).

### Backend (`backend/src/`)

- **API layer** — FastAPI, async SQLAlchemy 2, Pydantic v2.
  Endpoints versioned under `/api/v1`. All responses follow the
  `{data, meta, error}` envelope so the frontend has one shape to parse.
- **Analysis layer** — pure Python modules per scenario:
  - `scenario_a/` — compensation impact regression (SciPy curve_fit).
  - `scenario_b/` — Pearson + lead-lag classifier.
  - `scenario_c/` — XGBoost suitability + FAISS similarity + log-linear
    value forecast (Phase 2: Prophet swap-in).
  - `similarity/` — region recommender (weighted cosine).
- **ML layer** — `ml/registry.py` is the single point of contact between
  routes and saved models. In dev it reads `models_artifacts/` directly;
  in production it queries MLflow's "Production" stage.
- **ETL layer** — 5 pipelines in `etl/` (MOLIT, 정주인구, 공시지가,
  store scrapers, 건축물대장). Each ships a `--dry-run` mode and an
  operator kill switch (`ETL_KILL_SWITCH=1`).

### Persistence

- **Postgres + PostGIS** — 17 tables; views power the heaviest joins
  (`v_project_nearby_transactions`, `v_road_yearly_metrics`,
  `v_store_full_profile`).
- **Redis** — analysis cache (1h TTL) + feature store (24h TTL).
- **S3** — versioned model artifacts; lifecycle rule moves non-current
  versions to GLACIER after 90 days.

## Cross-cutting

- **Observability** — structlog → Railway → Datadog/Better Stack;
  Prometheus metrics at `/metrics`; Sentry for the SPA.
- **Security** — `slowapi` rate limiting, CORS allow-list, HSTS via
  nginx in front of the SPA, SQL only via the ORM.

## When to migrate to AWS ECS Fargate

Triggers (any one):
1. Sustained **> 200 RPS** on the API for two consecutive weeks.
2. **> 1M model artifacts** in S3 — MLflow registry pagination becomes
   a constraint.
3. **HA Postgres** required (production SLO ≥ 99.9%).
4. **Multi-region** demand (latency SLO < 150 ms outside KR).

The migration plan lives in a separate document; the high-level shape:

- ECS Fargate services per component (frontend, backend, mlflow).
- RDS Postgres Multi-AZ + ElastiCache (Redis cluster mode).
- ALB with WAF; CloudFront in front of the SPA.
- Same GHCR images, just pulled by Fargate task definitions.
- ML model serving stays in-process until throughput requires
  TorchServe / Seldon — re-evaluate at Phase 3.

## What's *not* in the architecture today

- **No queue / worker tier**. Long-running analyses run inline; if any
  endpoint exceeds 10s P95 the next architectural step is a Celery
  worker reading from Redis.
- **No multi-tenant boundary**. All API consumers see all rows; auth
  lands in Phase 2.
- **No CDN in front of the SPA** in MVP — Vercel handles it.
