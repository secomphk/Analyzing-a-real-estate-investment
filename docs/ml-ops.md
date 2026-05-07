# ML Ops

## Lifecycle

```
       data prep (ETL)
            │
            ▼
   train_suitability  ──┐
   build_faiss_index   ─┤   weekly via .github/workflows/ml-retrain.yml
   train_value_pred    ─┘   or manual workflow_dispatch
            │
            ▼
   MLflow registry  (Staging)
            │
            ├─ AUC gate ≥ 0.80 ──► promote ──► MLflow (Production)
            │                                       │
            ▼                                       ▼
   archive prior version              Backend lifespan calls
                                      ModelRegistry.load_production
```

## Components

| Concern               | Where                                     |
| --------------------- | ----------------------------------------- |
| Experiment tracking   | MLflow tracking server (Railway)          |
| Model registry        | MLflow registry — stages: Staging / Production / Archived |
| Artifacts             | S3 bucket `$MODELS_S3_BUCKET`, versioned  |
| Promotion             | `ModelRegistry.promote_to_production`     |
| Rollback              | `ModelRegistry.rollback`                  |
| Prediction monitoring | Prometheus counters + Grafana             |

## Training data sources

- **Positives** (suitability) — rows in `stores` matching the target
  (`store_type='DT'` or `'DI'`).
- **Negatives** — random parcels in the same 시군구 not within 200 m of
  any positive, ratio 1:3.
- **Features** — `FeatureExtractor.extract_for_store` enriched with the
  Scenario A/B catalyst variables read from the precomputed views.

## Promotion workflow

The `ml-retrain` GitHub Action runs the canonical flow:

1. Train DT + DI suitability classifiers (5-fold CV on the positives).
2. Build the FAISS store-similarity index over the same feature space.
3. Evaluate the Phase-1 value predictor (MAPE per horizon).
4. Upload the resulting `.pkl` / `.bin` files to S3 under the version
   prefix.
5. Promote the latest **Staging** versions of the suitability models to
   **Production** in MLflow (auto-archives the previous Production).
6. Trigger a `railway redeploy` so the backend lifespan reloads the
   promoted models on the next pod start.

## Promotion gate

The retrain workflow blocks promotion if any of:

- AUC `< 0.80` on the held-out fold.
- Sample size collapsed below 5 positives per region (data drift).
- The trained model can't load round-trip via `joblib.load`.

The check fails the workflow with a Slack alert; nothing is promoted.

## Rollback

When a freshly-promoted model regresses (post-deploy AUC monitor or a
manual review), one-shot via the Railway shell:

```bash
railway run --service backend-prod \
  python -c "from src.ml.registry import build_registry; \
             print(build_registry().rollback('suitability_dt'))"
```

This promotes the most-recent **Archived** version back to Production.
The same call also fires the `model_rolled_back` log line, which the
Better Stack monitor watches for.

For an end-to-end rollback (artifact + container together):

1. `railway redeploy --service backend-prod --image <previous-tag>`.
2. Then run the rollback above so MLflow registry stays consistent.

## Model performance monitoring

- **Realtime** — `model_predictions_total` + `model_prediction_duration_seconds`
  Prometheus metrics, panels in Grafana per `(model, version)`.
- **Drift** — daily batch (Phase 2) compares the live score distribution
  to the training-set distribution; alerts on KS statistic > 0.10.
- **Outcomes** (Phase 2) — when actual store-open events arrive in the
  DB, a nightly job re-computes AUC against the most recent 90 days of
  predictions.

## Local debugging

Reload a specific model in a Python REPL:

```python
from src.ml.registry import build_registry

reg = build_registry()
model = reg.load_model("suitability_dt", "v3")  # local file
prod  = reg.load_production("suitability_dt")   # MLflow
```

Predictions come back as `Suitability` dataclasses (see
`src/analysis/scenario_c/suitability_model.py`).

## Phase 2 priorities

1. Replace the log-linear value predictor with Prophet (drop-in via the
   existing `LandValuePredictor` interface).
2. Add an XGBoost residual regressor on top of Prophet to capture
   catalyst-driven non-linearities.
3. Wire prediction outcomes back into the training set (closing the
   feedback loop).
