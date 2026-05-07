# Deployment

MVP runs on the **Vercel + Railway + S3** stack. AWS ECS migration lives in a
separate guide; see [`architecture.md`](./architecture.md) for when to make
that move.

## Components

| Component        | Where it runs                | Config source                      |
| ---------------- | ---------------------------- | ---------------------------------- |
| Frontend (SPA)   | Vercel (`apps/frontend`)     | Vercel project env + GitHub vars   |
| Backend API      | Railway service `backend-*`  | `.env.prod` + Railway dashboard    |
| Postgres + PostGIS | Railway add-on             | Railway-managed credentials        |
| Redis            | Railway add-on               | Railway-managed credentials        |
| Model artifacts  | S3 bucket (versioned)        | `MODELS_S3_URI` env var            |
| MLflow           | Self-hosted (Railway)        | `MLFLOW_TRACKING_URI` secret       |
| Container images | GHCR — `ghcr.io/<org>/...`   | GitHub Actions builds              |

## First-time setup

1. **Create environments on GitHub**
   - Settings → Environments → `staging`, `production`.
   - For `production`, require ≥ 1 reviewer.
2. **Set secrets** (per environment)
   - `RAILWAY_TOKEN`
   - `STAGING_DATABASE_URL`, `STAGING_DATABASE_URL_SYNC`
   - `PROD_DATABASE_URL`, `PROD_DATABASE_URL_SYNC`, `PROD_DATABASE_URL_RO`,
     `PROD_DATABASE_URL_RO_SYNC` (read-only replica for retraining)
   - `MLFLOW_TRACKING_URI` + `MLFLOW_TRACKING_USERNAME` + `MLFLOW_TRACKING_PASSWORD`
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (model upload)
   - `VITE_KAKAO_MAP_KEY_STAGING`, `VITE_KAKAO_MAP_KEY_PROD`
   - `SLACK_WEBHOOK_URL_OPS`
3. **Set vars** (non-secret env)
   - `STAGING_API_URL`, `PROD_API_URL`
   - `MODELS_S3_BUCKET`, `AWS_REGION`
4. **Connect Railway services**
   - `backend-staging`, `backend-prod`, `frontend-staging`, `frontend-prod`
   - Add Postgres + Redis add-ons; copy DSNs into the env vars above.
5. **Provision S3 bucket** with versioning enabled — used for model
   artifacts. Lifecycle rule: transition non-current versions to GLACIER
   after 90 days.

## Deploy flow

| Trigger              | Workflow             | Outcome                                    |
| -------------------- | -------------------- | ------------------------------------------ |
| PR opened            | `backend-ci`, `frontend-ci` | Lint / type / tests must pass     |
| Merge to `main`      | `deploy-staging`     | Build images → migrate → deploy staging   |
| Tag `vX.Y.Z`         | `deploy-prod`        | Manual approval → migrate → deploy prod   |
| Sat 18:00 UTC        | `ml-retrain`         | Train + register + promote DT/DI models   |
| Manual (Actions UI)  | `ml-retrain`         | Same, ad-hoc                               |

## Local-equivalent stack

The compose files in `backend/` reproduce the production topology on a
single host. Useful when you need to repro a production bug without
touching the live system.

```bash
cd backend
cp .env.example .env.prod  # fill in real secrets
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

## Smoke checklist after a deploy

- [ ] `curl $API_URL/health` → 200, `data.redis_ok = true`
- [ ] `curl $API_URL/metrics` → Prometheus output (no auth in MVP)
- [ ] Hit one route per scenario (A / B / C / recommendations)
- [ ] Cache hit on the second call (`meta.cache_hit = true`)
- [ ] Frontend `/` loads, all 5 nav routes render

## Rollback

- Fast: re-deploy the previous image tag from Railway UI.
- Slow (DB schema changed): `alembic downgrade -1` on the affected
  environment, then re-deploy. Avoid by writing additive-only migrations.
- ML model: see [`ml-ops.md`](./ml-ops.md) → "Rollback".
