# RealEstate Analyzer — Backend

Real Estate Investment Analysis Platform. Three scenarios:

- **Scenario A — 보상금 영향 분석**: regression of compensation payouts on
  surrounding housing prices (공공주택지구).
- **Scenario B — 도로확장 패턴**: 3-variable analysis of road expansion ×
  resident population × traffic volume.
- **Scenario C — DT/DI 매장 입지 예측**: XGBoost suitability + FAISS
  similarity + Prophet revenue forecast for drive-thru / drive-in stores.

This repo holds the FastAPI backend, ML infrastructure (model registry,
Redis-backed feature store, MLflow), and PostgreSQL + PostGIS persistence.
Stage 1 ships the skeleton — routers return dummy responses; concrete
ETL/analysis lands in Stage 2 / Stage 3.

---

## Prerequisites

- Docker + Docker Compose v2
- (Local dev only) Python 3.11 and [Poetry](https://python-poetry.org/) ≥ 1.8

---

## Setup (5 steps)

```bash
# 1. Clone and enter the backend directory
cd backend

# 2. Copy env template and fill in API keys you have
cp .env.example .env

# 3. Build and start postgres, redis, mlflow, backend
docker compose up -d --build

# 4. Wait for healthchecks (about 30s on first boot)
docker compose ps

# 5. Verify
curl http://localhost:8000/health
open http://localhost:8000/docs
```

---

## Running commands

| Goal                 | Command                                             |
| -------------------- | --------------------------------------------------- |
| Bring up dev stack   | `docker compose up -d --build`                      |
| Tail logs            | `docker compose logs -f backend`                    |
| Run tests inside box | `docker compose exec backend pytest`                |
| Lint                 | `docker compose exec backend ruff check src/`       |
| Type-check           | `docker compose exec backend mypy src/`             |
| Generate migration   | `docker compose exec backend alembic revision --autogenerate -m "msg"` |
| Apply migrations     | `docker compose exec backend alembic upgrade head`  |
| Tear down            | `docker compose down`                               |
| Tear down + wipe data| `docker compose down -v`                            |

### Local (non-Docker) dev

```bash
poetry install
poetry run pre-commit install
poetry run uvicorn src.main:app --reload
poetry run pytest
poetry run ruff check src/
poetry run mypy src/
```

---

## Environment variables

| Variable                    | Required | Default                                   | Notes                                         |
| --------------------------- | -------- | ----------------------------------------- | --------------------------------------------- |
| `ENVIRONMENT`               | no       | `development`                             | one of `development|staging|production|test` |
| `LOG_LEVEL`                 | no       | `INFO`                                    | `DEBUG`/`INFO`/`WARNING`/...                  |
| `DATABASE_URL`              | yes      | postgres-asyncpg URL                      | async DSN used by SQLAlchemy                  |
| `DATABASE_URL_SYNC`         | yes      | postgres URL                              | sync DSN used by Alembic                      |
| `REDIS_URL`                 | yes      | `redis://redis:6379/0`                    | feature store + cache                         |
| `MOLIT_API_KEY`             | (Stage 2)| —                                         | 국토교통부 실거래가                           |
| `ADMIN_POPULATION_API_KEY`  | (Stage 2)| —                                         | 행정안전부 정주인구                           |
| `REALTY_PRICE_API_KEY`      | (Stage 2)| —                                         | 공시지가                                      |
| `KAKAO_API_KEY`             | (Stage 2)| —                                         | 지오코딩 보조                                 |
| `MLFLOW_TRACKING_URI`       | no       | `http://mlflow:5000`                      | MLflow tracking server                        |
| `MODELS_DIR`                | no       | `./models_artifacts`                      | local model artifacts directory               |
| `SENTRY_DSN`                | no       | empty (disables Sentry)                   | only initialized if set                       |
| `CORS_ORIGINS`              | no       | `http://localhost:3000`                   | comma-separated list                          |
| `RATE_LIMIT_DEFAULT`        | no       | `100/minute`                              | slowapi default                               |
| `SECRET_KEY`                | yes (prod)| placeholder                              | used in Phase 2 auth                          |

See [`.env.example`](.env.example) for the full set.

---

## Directory layout

```
backend/
├── pyproject.toml          # Poetry deps, ruff, mypy, pytest config
├── docker-compose.yml      # postgres + redis + mlflow + backend
├── docker-compose.prod.yml # production overrides
├── Dockerfile              # multi-stage build
├── alembic.ini             # migration config (URL via settings)
├── alembic/                # migration scripts
├── scripts/                # init_postgis.sql etc.
├── src/
│   ├── main.py             # FastAPI app, lifespan, middleware
│   ├── core/               # config, db, redis, logging, security, exceptions
│   ├── api/v1/             # routers (one per scenario)
│   ├── models/             # SQLAlchemy ORM (Stage 2)
│   ├── schemas/            # Pydantic v2 schemas
│   ├── repositories/       # DB access (Stage 2)
│   ├── services/           # business logic (Stage 2/3)
│   ├── analysis/           # scenario_a, scenario_b, scenario_c, similarity, common
│   ├── etl/                # MOLIT, 정주인구, 세움터, 공시지가, store_scraper/
│   └── ml/                 # registry, feature_store, monitoring
├── models_artifacts/       # *.pkl, *.bin (gitignored)
├── notebooks/              # exploratory notebooks (gitignored)
└── tests/
    ├── conftest.py
    ├── test_api/
    ├── test_models/
    ├── test_analysis/
    └── test_etl/
```

---

## Stage 2 (data infrastructure) — operational commands

```bash
# Apply schema (PostGIS extensions + 17 tables + 3 views)
docker compose exec backend alembic upgrade head

# Seed validation cases (4 projects, 2 roads, 30 stores + price/traffic/pop series)
docker compose exec backend python -m src.scripts.seed --scenario all

# One scenario at a time
docker compose exec backend python -m src.scripts.seed --scenario c
docker compose exec backend python -m src.scripts.seed --scenario a --reset
docker compose exec backend python -m src.scripts.seed --dry-run

# ETL — every pipeline supports --dry-run
docker compose exec backend python -m src.etl.molit_real_estate --sigungu 41280 --month 2024-01
docker compose exec backend python -m src.etl.admin_population --month 2024-01
docker compose exec backend python -m src.etl.land_price --year 2024 --pnu-list pnus.txt
docker compose exec backend python -m src.etl.store_scraper.run --brand all
docker compose exec backend python -m src.etl.building_registry --pnu-list pnus.txt --csv-out manual.csv

# Operator kill switch — stops every ETL run instantly
ETL_KILL_SWITCH=1 docker compose exec backend python -m src.etl.molit_real_estate ...
```

### Schema overview

| Table                       | Scenario | Notes                                                  |
| --------------------------- | -------- | ------------------------------------------------------ |
| `admin_areas`               | shared   | 시·도/시·군·구/읍·면·동, self-FK, GIST index               |
| `projects` / `project_stages` | A      | 호재 사업 + 단계 이력 (announced→completion)            |
| `land_transactions`         | A·B·C    | MOLIT 실거래가 (UNIQUE on `source_id`)                 |
| `road_segments` / `road_expansion_stages` | B | 도로 + 확장 단계                          |
| `traffic_volumes`           | B        | 월별 AADT (FK → road_segments)                         |
| `population_stats`          | B        | 월별 인구 (FK → admin_areas)                           |
| `store_brands` / `stores`   | C        | 브랜드 + 매장 (DT/DI/standard)                         |
| `buildings`                 | C        | 건축물대장 (PK = PNU)                                  |
| `official_land_prices`      | C        | 개별공시지가 연도별 (UNIQUE on `pnu, year`)            |
| `store_features`            | C        | 매장 시점별 피처 벡터 (XGBoost 학습 입력)             |
| `candidate_lands`           | C        | 적합도 모델 결과                                       |
| `store_impact_analysis`     | C        | Halo 효과 (distance band별)                            |
| `analysis_results`          | shared   | 분석 결과 캐시 (UUID PK, params_hash UNIQUE)           |
| `recommendations`           | shared   | 유사 지역/매장 추천 (rank별)                           |

### Views

* **`v_project_nearby_transactions`** — 사업 ↔ 5 km 반경 거래 + 거리.
  Scenario A regression input.
* **`v_road_yearly_metrics`** — 연도 단위 AADT × 인구 rollup. Scenario B.
* **`v_store_full_profile`** — 매장 + 브랜드 + 건축물 + 5년 공시지가
  시계열 + `price_change_pct`. Scenario C 학습 입력.

## What's next (Stage 3)

- Scenario A regression (price ~ distance × time × controls) →
  `src/analysis/scenario_a/`
- Scenario B 3-variable correlation + clustering →
  `src/analysis/scenario_b/`
- Scenario C XGBoost suitability + Prophet revenue + FAISS similarity →
  `src/analysis/scenario_c/`, `src/analysis/similarity/`
- SHAP explanations + MLflow registry integration
- Pydantic v2 request/response schemas for every v1 route
