# Security checklist

Use this as a production go-live gate. Each item links to evidence in
the codebase so a reviewer can self-serve.

## Secrets management

- [x] `.env` files git-ignored ([backend/.gitignore](../backend/.gitignore),
      [frontend/.gitignore](../frontend/.gitignore)).
- [x] CI secrets stored in **GitHub Environments** (staging /
      production), not repository-wide secrets.
- [x] Runtime secrets injected by Railway env vars; never baked into
      images. (`docker-compose.prod.yml` reads via `env_file: .env.prod`.)
- [x] No secret logged at any level (structlog redacts via `_sanitize`
      hook — verify by searching for `secret_key=` in stage logs).

## Network surface

- [x] CORS allow-list — backend reads `CORS_ORIGINS` from settings, not
      `*`. ([src/main.py](../backend/src/main.py))
- [x] HSTS via nginx `Strict-Transport-Security` header (added when the
      reverse proxy terminates TLS).
- [x] `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
      `Referrer-Policy` configured in [nginx.conf](../frontend/nginx.conf).
- [x] Rate limiting via `slowapi` — default `100/minute`
      (`RATE_LIMIT_DEFAULT`).

## Dependency hygiene

- [x] Dependabot enabled for `pip`, `npm`, `github-actions`, `docker`
      ([.github/dependabot.yml](../.github/dependabot.yml)).
- [x] CI fails on lockfile drift (Poetry `--no-update`, npm `ci`).
- [ ] **Phase 2** — schedule weekly `pip-audit` + `npm audit` runs that
      open issues automatically.

## Database

- [x] All queries use SQLAlchemy ORM or `text(...).bindparams(...)` —
      no string concatenation. (Confirm with
      `grep -RE "f.\".*SELECT" backend/src` returning nothing.)
- [x] Backend connects with a least-privilege role — no superuser in
      production DSNs.
- [ ] **Phase 2** — separate read-only role for the `ml-retrain`
      workflow (already wired via `PROD_DATABASE_URL_RO`).

## API

- [x] Pydantic schemas reject malformed input → 422 envelope.
- [x] Public endpoints have no PII surface — store catalogue and
      project / road metadata only.
- [x] Authentication is intentionally absent in MVP, wrapped behind a
      Phase 2 `get_current_user` placeholder so endpoints stay testable.
- [ ] **Phase 2** — JWT, role-based scopes, audit log.

## ML / data privacy

- [x] No 등기부 personal data stored — schema only carries PNU + parcel
      attributes (verify via [migration](../backend/alembic/versions/20260507_0001_initial_schema.py)).
- [x] Store metadata limited to public-info fields (brand, address,
      coordinates, store type).
- [ ] **Phase 2** — per-user daily call cap on `dt-candidates`
      (10/day/user).

## Container

- [x] Backend runs as non-root `app` user ([Dockerfile](../backend/Dockerfile)).
- [x] Frontend runs as non-root `nginx` user ([Dockerfile](../frontend/Dockerfile)).
- [x] `tini` as PID 1 in both images for clean SIGTERM propagation.
- [x] Healthchecks defined; orchestrator can replace unhealthy pods.

## CI/CD

- [x] Production deploy gated by `environment: production` (manual
      reviewer required).
- [x] Image tags include the git SHA — never `:latest` for forensics.
- [x] Slack alert on deploy / retrain failure
      (`SLACK_WEBHOOK_URL_OPS`).

## Observability

- [x] Structured JSON logs with request id propagation.
- [x] Sentry SDK initialized when `SENTRY_DSN` is set (no-op otherwise).
- [x] Prometheus `/metrics` endpoint not exposed publicly through nginx
      — keep it on the internal port only.

## Checklist for every release

1. Run `npm audit --omit=dev` on the frontend; review high/critical.
2. Run `poetry export | pip-audit -r /dev/stdin` on the backend.
3. Check that the new commits don't add a new third-party API call —
   if they do, confirm the key flows through env, not source.
4. Tag → trigger `deploy-prod` → verify smoke test.
