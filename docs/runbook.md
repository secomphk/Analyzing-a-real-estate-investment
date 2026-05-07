# On-call runbook

When a page fires, reach for this doc first. Each section is structured
**Symptoms → Diagnose → Fix → Verify** so you can move quickly.

## 5xx error rate spike

**Symptoms** — Datadog/Better Stack monitor "5xx > 1% for 5 min".

**Diagnose**
1. `railway logs --service backend-prod | grep -E "ERROR|Traceback"` — last 5 min.
2. Check `/health` — if `redis_ok=false` see [Redis down](#redis-connection-failure).
3. Check Postgres status on Railway dashboard — if degraded, see [DB outage](#postgres-outage).
4. Look for a recent deploy in `#deploys` Slack — most spikes correlate
   with the most recent rollout.

**Fix**
- Recent deploy correlation → roll back: in Railway, redeploy the
  previous image tag, OR push the previous tag to `latest` from GHCR.
- Specific endpoint failing → grep logs by `path=`; if it's an analysis
  endpoint, the underlying model load may be the cause —
  see [Model load failure](#model-load-failure).
- Otherwise → page the second on-call.

**Verify** — `curl $API/health` 200 + 5xx rate returns to baseline.

## Postgres outage

**Symptoms** — `pg_isready` failing, app `/health` non-200, ETL workflows
failing across the board.

**Diagnose**
1. Railway dashboard → Postgres add-on → "Health" tab.
2. `select pg_is_in_recovery();` from a psql shell — `t` means a managed
   failover is in progress.

**Fix**
- Managed failover in progress → wait + announce in `#status`.
- DB out of disk → bump volume size on Railway. Verify by inspecting the
  most recent `WriteAhead` errors; vacuum afterwards.
- Index corruption (rare) → restore the most recent automatic backup
  (Railway → "Backups" tab).

**Verify** — `/health` 200, oldest replication lag < 30s.

## Redis connection failure

**Symptoms** — `cache_get_failed` log spam, `redis_ok=false` in `/health`,
P95 latencies climb (cache misses → DB).

**Diagnose**
1. Railway → Redis add-on health.
2. `redis-cli -u $REDIS_URL ping` from anywhere.

**Fix**
- Restart the Redis service on Railway.
- App keeps serving (cache writes fail open). Don't roll back the
  backend; redeploy the Redis service instead.

**Verify** — cache hit rate returns to baseline (Grafana panel "Cache").

## Model load failure

**Symptoms** — `/api/v1/predictions/dt-candidates` returning 503
`model_not_loaded`, `model_artifact_missing` warnings at startup.

**Diagnose**
1. `railway run --service backend-prod ls /app/models_artifacts` — is the
   `.pkl` file present?
2. `aws s3 ls s3://$MODELS_S3_BUCKET/$MODEL_VERSION/` — is the artifact
   uploaded?

**Fix**
- Missing artifact → re-run the `ml-retrain` workflow with the previous
  known-good version, OR `ModelRegistry.rollback("suitability_dt")` via a
  one-shot `python -c "..."` ssh-style invocation.
- S3 unreachable → boot will work once the entrypoint's S3 sync recovers;
  meantime API serves the neutral fallback (50/100 score). No urgent fix.

**Verify** — `/api/v1/predictions/dt-candidates` returns 200, response
`meta.model_version` is the expected `vN`.

## Slow Scenario C / DT candidates

**Symptoms** — P95 > 5s on `/predictions/dt-candidates`.

**Diagnose**
1. Check Grafana panel "Prediction latency" — is it just one model?
2. `EXPLAIN ANALYZE` the candidate-PNU query (in `candidate_finder.py`)
   for the slow region. Suspect missing index on `buildings.use_type`.

**Fix**
- Reduce `top_n` cap on the API side (now 50 — drop to 20 if needed).
- Backfill spatial indexes if a recent migration added rows but skipped
  GIST creation.

**Verify** — P95 panel returns under 5s.

## ETL pipeline failure

**Symptoms** — `etl_records_processed_total{outcome="error"}` jumps; daily
summary alert in `#data-ops`.

**Diagnose**
1. `data/errors/$(date -u +%F).jsonl` on the host — which rows failed?
2. Most likely: upstream API schema changed.

**Fix**
- Patch the normalizer in `src/etl/<pipeline>.py`, ship a hotfix.
- Use `--dry-run` to verify before re-running.

**Verify** — error counter flat for the next run.

## ML retrain regression (AUC drop)

See [`ml-ops.md`](./ml-ops.md) → "Rollback".
