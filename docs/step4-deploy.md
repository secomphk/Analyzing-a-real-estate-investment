# Step 4 — First production deploy (Vercel + Railway + GHCR)

Concrete checklist for getting RealEstate Analyzer onto live URLs. The
[deployment.md](./deployment.md) doc covers steady-state ops; this one is
the one-time setup walkthrough.

> **Prereq**: GitHub account, Vercel account, Railway account. Card on
> file (Railway has a free-tier trial that needs a card; Vercel has a
> hobby tier that doesn't).

---

## 0. Pre-flight — already done

Stage 5 generated all the artifacts. Just confirming what's ready:

- ✅ [`backend/Dockerfile`](../backend/Dockerfile) (multi-stage, non-root, tini, healthcheck)
- ✅ [`frontend/Dockerfile`](../frontend/Dockerfile) (vite build → nginx, non-root)
- ✅ [`backend/scripts/entrypoint.sh`](../backend/scripts/entrypoint.sh) (handles `MIGRATE_ON_BOOT`, S3 model sync)
- ✅ [`backend/docker-compose.prod.yml`](../backend/docker-compose.prod.yml) (single-host fallback)
- ✅ [`backend/.env.prod.example`](../backend/.env.prod.example) (all vars Railway needs)
- ✅ 5 GitHub Actions workflows in [`.github/workflows/`](../.github/workflows/)
- ✅ Static validation passed: workflow YAMLs parse, every referenced file exists

---

## 1. Push the repo to GitHub

```bash
cd "E:/Agent/Real Estate Analyzer"

# If not already inside a git repo:
git init -b main
git add .
git status                         # eyeball — confirm no .env, no node_modules
git commit -m "Initial commit (Stages 1–5)"

# Create the repo on github.com (private), then:
git remote add origin https://github.com/<your-user>/realestate-analyzer.git
git push -u origin main
```

That push **doesn't** trigger a deploy yet — workflows need secrets.

---

## 2. GitHub Environments + Secrets

Settings → Environments → create two:

### `staging`
No reviewer — deploys auto-trigger on every push to `main`.

### `production`
**Required reviewers**: yourself (so tag pushes pause for approval).

### Secrets to add

These go on each Environment (so staging and production have *different*
values), **not** on the repo level:

| Secret | Where it comes from | Used by |
| --- | --- | --- |
| `RAILWAY_TOKEN` | Railway → Account Settings → Tokens | deploy-staging, deploy-prod, ml-retrain |
| `STAGING_DATABASE_URL` | Railway Postgres add-on (asyncpg DSN) | deploy-staging |
| `STAGING_DATABASE_URL_SYNC` | same add-on, sync DSN | deploy-staging |
| `PROD_DATABASE_URL` | Railway prod Postgres | deploy-prod |
| `PROD_DATABASE_URL_SYNC` | same, sync DSN | deploy-prod |
| `PROD_DATABASE_URL_RO` | RO replica DSN (or repeat prod) | ml-retrain |
| `PROD_DATABASE_URL_RO_SYNC` | same, sync | ml-retrain |
| `MLFLOW_TRACKING_URI` | self-hosted MLflow URL or Databricks | ml-retrain |
| `MLFLOW_TRACKING_USERNAME` | basic auth, optional | ml-retrain |
| `MLFLOW_TRACKING_PASSWORD` | basic auth, optional | ml-retrain |
| `AWS_ACCESS_KEY_ID` | IAM user with `s3:Put` on the model bucket | ml-retrain |
| `AWS_SECRET_ACCESS_KEY` | same | ml-retrain |
| `VITE_KAKAO_MAP_KEY_STAGING` | Kakao Developers → JS key | deploy-staging frontend build |
| `VITE_KAKAO_MAP_KEY_PROD` | same Kakao app or a separate one | deploy-prod frontend build |
| `SLACK_WEBHOOK_URL_OPS` | Slack incoming webhook (optional) | deploy-prod, ml-retrain |

### Variables (non-secret)

Settings → Environments → Variables (per environment):

| Variable | Example | Used by |
| --- | --- | --- |
| `STAGING_API_URL` | `https://backend-staging.up.railway.app` | smoke test |
| `PROD_API_URL` | `https://api.example.com` | smoke test |
| `VITE_API_URL_STAGING` | `https://backend-staging.up.railway.app` | frontend build |
| `VITE_API_URL_PROD` | `https://api.example.com` | frontend build |
| `MODELS_S3_BUCKET` | `realestate-models-prod` | ml-retrain |
| `AWS_REGION` | `ap-northeast-2` | ml-retrain |

> If any of these are missing, the corresponding workflow fails fast with
> a clear error — no half-deploys.

---

## 3. Railway services

Railway has the simplest path: one project, four services + two add-ons.

### 3a. Create the project

Railway dashboard → **New Project** → **Empty Project** → name it
`realestate-analyzer-staging` (we'll mirror this for production).

### 3b. Add Postgres + Redis add-ons

Inside the project: **+ New** → **Database** → **PostgreSQL** (and again
for **Redis**).

Once provisioned, click each → **Variables** tab → copy:
- Postgres: `DATABASE_URL` (Railway gives you a `postgresql://…` URL —
  copy this as `STAGING_DATABASE_URL_SYNC`; replace `postgresql://`
  with `postgresql+asyncpg://` for the async version).
- Redis: `REDIS_URL`.

### 3c. Backend service

**+ New** → **GitHub Repo** → pick this repo → set:
- **Service name**: `backend-staging`
- **Root directory**: `backend`
- **Build**: Dockerfile (Railway autodetects)
- **Variables**: paste from `backend/.env.prod.example`. Required at
  minimum:
  - `ENVIRONMENT=staging`
  - `DATABASE_URL` / `DATABASE_URL_SYNC` (from add-on, async + sync)
  - `REDIS_URL` (from add-on)
  - `MOLIT_API_KEY`, `ADMIN_POPULATION_API_KEY`, `REALTY_PRICE_API_KEY`,
    `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (copy from `.env.local`)
  - `SECRET_KEY` (fresh per environment)
  - `MIGRATE_ON_BOOT=true`
  - `UVICORN_WORKERS=2`
- **Public networking**: enable HTTPS → note the assigned URL
  (e.g. `backend-staging.up.railway.app`). Paste this URL into the
  GitHub variables `STAGING_API_URL` and `VITE_API_URL_STAGING` from
  step 2.

### 3d. Frontend service (option 1 — Railway)

If you want both backend and frontend on Railway (single bill):

**+ New** → **GitHub Repo** → same repo:
- **Service name**: `frontend-staging`
- **Root directory**: `frontend`
- **Build**: Dockerfile
- **Build args**:
  - `VITE_API_URL` = backend public URL from 3c
  - `VITE_KAKAO_MAP_KEY` = the Kakao JS SDK key
- **Variables**: `BACKEND_UPSTREAM=backend-staging.railway.internal:8000`
  (uses Railway's internal DNS so /api proxy stays inside the network).

### 3d. Frontend service (option 2 — Vercel)

If you prefer Vercel for the SPA (better global CDN):

Vercel → **New Project** → import this repo → set:
- **Root Directory**: `frontend`
- **Framework Preset**: Vite
- **Environment Variables**:
  - `VITE_API_URL` = backend Railway URL
  - `VITE_KAKAO_MAP_KEY` = JS SDK key

Then click **Deploy**.

> Pick **one** of 3d-1 / 3d-2; the rest of the doc assumes whichever you
> chose. Vercel is recommended for production; Railway-frontend works
> fine for staging if you want one bill.

### 3e. Production project

Repeat 3a–3d with names `…-prod`. Use a **different** Postgres add-on
(don't share staging and prod data). Update the prod-specific GitHub
secrets / variables to point at it.

---

## 4. First deploy (staging)

Already pushed `main` in step 1. To trigger:

```bash
git commit --allow-empty -m "Trigger staging deploy"
git push
```

Watch GitHub Actions → `Deploy → staging` workflow:
1. **build-and-push** (≈ 3–5 min) — builds backend + frontend images,
   pushes to GHCR.
2. **migrate** — applies Alembic migrations against staging Postgres.
3. **deploy** — `railway redeploy` then 5x retry on `/health`.

If any step fails, the workflow surfaces the exact error. Common first-
deploy gotchas:
- Postgres connection refused → DSN missing `+asyncpg`.
- 500s right after deploy → forgot to seed; run
  `railway run --service backend-staging python -m src.scripts.seed --scenario all`.
- Frontend build fails for missing `VITE_KAKAO_MAP_KEY` → set the var
  on the GitHub Environment, retrigger.

---

## 5. Smoke checklist (manual)

After the workflow goes green:

- [ ] `curl $STAGING_API_URL/health` → 200, `data.redis_ok=true`.
- [ ] Visit the frontend URL (Vercel or Railway frontend).
- [ ] Click each of the 5 nav routes — no console errors.
- [ ] Open `/scenario-c?mode=impact` — store map renders.
- [ ] Re-issue any of the analysis routes; second call should show
  `meta.cache_hit=true`.

---

## 6. Production cut-over

Once staging is happy:

```bash
git tag v0.1.0
git push origin v0.1.0
```

`Deploy → production` workflow runs, pauses for your approval at the
`production` environment gate, then:
1. Builds tagged images.
2. Backs up the prod schema (best-effort, won't block).
3. Applies migrations.
4. `railway redeploy --service backend-prod` + frontend.
5. Smoke test (10x retry on /health).

If smoke fails: workflow reports + Slack notify; rollback by
re-deploying the previous tag from Railway UI (or `railway redeploy
--image ghcr.io/.../backend:vPREV`).

---

## 7. After this guide

The flow becomes:

| Action | Result |
| --- | --- |
| Open PR | `backend-ci` + `frontend-ci` run (lint/type/test) |
| Merge to `main` | `Deploy → staging` (auto) |
| Tag `vX.Y.Z` + approve | `Deploy → production` |
| Sat 18:00 UTC | `ml-retrain` runs (after first model is in S3) |

The runbook in [`runbook.md`](./runbook.md) covers what to do when an
alert fires.
