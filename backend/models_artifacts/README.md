# models_artifacts/

Trained model files live here. Naming convention:

```
{name}_{version}.{ext}
```

Examples:

- `suitability_dt_v1.pkl`   — XGBoost suitability model for drive-thru.
- `suitability_di_v1.pkl`   — XGBoost suitability model for drive-in.
- `faiss_index_v1.bin`      — FAISS similarity index over store embeddings.

`.pkl` / `.joblib` files are loaded with `joblib.load`.
`.bin` files are loaded with `faiss.read_index`.

The directory is mounted into the container by `docker-compose.yml`. Files
with the extensions above are git-ignored — publish them through MLflow or
your object store, not the repo.
