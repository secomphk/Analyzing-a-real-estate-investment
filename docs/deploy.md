# 배포 가이드 — Railway (백엔드) + Vercel (프론트)

이 문서는 **GitHub 리포지토리가 만들어진 직후** 부터 staging URL이
공개되기까지를 한 번에 따라갈 수 있게 정리한 것입니다. 모든 키는 이미
로컬 `.env`에서 검증된 값을 그대로 옮기면 됩니다.

## 0. GitHub repo

```bash
# 옵션 A — gh CLI (권장)
winget install GitHub.cli   # Windows
gh auth login
gh repo create realestate-analyzer --private --source=. --remote=origin --push

# 옵션 B — 웹 UI
# 1) https://github.com/new 에서 빈 private repo 생성 (README/.gitignore 체크 해제)
# 2) 로컬에서:
git remote add origin https://github.com/<user>/realestate-analyzer.git
git push -u origin main
```

## 1. Railway — 백엔드 + Postgres + Redis

`railway.json` (repo 루트)이 이미 백엔드 Dockerfile을 가리키고 있어서
**Connect repo → Detect Dockerfile** 만 하면 빌드가 시작됩니다.

1. <https://railway.app/new> → "Deploy from GitHub repo" → 방금 만든 리포 선택
2. Service → **Variables** 에 다음 등록:

   | Key | Value |
   |---|---|
   | `MIGRATE_ON_BOOT` | `true` |
   | `UVICORN_WORKERS` | `2` |
   | `MOLIT_API_KEY` | (`.env`의 Decoding key) |
   | `ADMIN_POPULATION_API_KEY` | (MOLIT과 동일) |
   | `REALTY_PRICE_API_KEY` | (V-World key) |
   | `KAKAO_API_KEY` | (선택) |
   | `CORS_ORIGINS` | `https://<vercel-domain>` (배포 후 갱신) |

3. **+ Add → Database → Postgres** 추가. Railway가 자동으로
   `DATABASE_URL` 변수를 만들어 백엔드에 주입합니다. 단,
   `postgresql://` → `postgresql+asyncpg://` 로 prefix만 바꿔야 SQLAlchemy
   async 드라이버가 잡힙니다. **Variable References** 로:

   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```

   대신 다음과 같이 두 줄로 풀어 쓰는 것이 깔끔합니다:

   ```
   DB_HOST=${{Postgres.PGHOST}}
   DB_PORT=${{Postgres.PGPORT}}
   DB_USER=${{Postgres.PGUSER}}
   DB_PASS=${{Postgres.PGPASSWORD}}
   DB_NAME=${{Postgres.PGDATABASE}}
   DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME
   ```

4. **+ Add → Database → Redis** 추가 후
   `REDIS_URL=${{Redis.REDIS_URL}}` 로 references.
5. **Deploy**. 첫 배포에서 `MIGRATE_ON_BOOT=true` 가 `alembic upgrade
   head` 를 실행해 17개 테이블을 만들어 줍니다.
6. Railway 가 발급한 public URL (예: `re-analyzer.up.railway.app`)을
   복사해 둡니다 — 다음 단계에서 사용.

### 시드 + ETL 1회 실행 (선택)

대시보드를 빈 상태로 띄우고 싶지 않다면 Railway 의 **Run Command**
탭에서 다음을 실행:

```bash
python -m src.scripts.seed --scenario all
python -m scripts.run_admin_population_2024
python -m src.etl.molit_real_estate --sigungu 41220 --month 2024-01
```

## 2. Vercel — 프론트

1. <https://vercel.com/new> → 같은 GitHub 리포 import
2. **Root Directory** 를 `frontend/` 로 지정
3. Framework preset: **Vite** (자동 감지)
4. Environment variables:

   | Key | Value |
   |---|---|
   | `VITE_API_URL` | `https://<railway-url>` |
   | `VITE_KAKAO_MAP_KEY` | 카카오 JS SDK key |

5. Deploy → Vercel URL 복사
6. `frontend/vercel.json` 의 `YOUR-RAILWAY-URL` 부분을 실제 URL로
   교체 후 push (Vercel 의 `/api/*` rewrite 가 작동하도록)
7. Railway 의 `CORS_ORIGINS` 변수에 Vercel URL 추가 → 백엔드 재시작

## 3. 동작 확인

```bash
curl https://<railway-url>/health
# → {"data":{"status":"ok",...}}

curl -X POST https://<railway-url>/api/v1/analysis/scenario-b \
  -H "Content-Type: application/json" \
  -d '{"road_id": 3}'
```

브라우저에서 Vercel URL 을 열면 OverviewPage 가 시드된 데이터 (또는
ETL 으로 적재된 평택 통계)를 보여줘야 합니다.

## 4. CI/CD

* Vercel: `main` push 마다 자동 배포 (PR 미리보기 포함).
* Railway: 같은 동작. 환경변수 변경 시 자동 재배포.
* 둘 다 **롤백** 은 web UI 한 클릭. 데이터베이스 마이그레이션은
  Alembic이 멱등이므로 동일 commit 재배포는 NOOP.

## 5. 보안 메모

* `.env*` 는 git ignore — 키는 Railway/Vercel UI 에만 등록.
* `realty_price` 류 key 는 일일 호출량이 1,000–10,000 사이라
  무한루프 ETL 이 돌지 않게 `--month` / `--sigungu` 를 제한해서
  돌립니다 (`docs/data-sources.md` 참조).
* 비용: Postgres + Redis + 백엔드 = 월 약 $5–15 (Railway pro). Vercel
  Hobby tier 는 트래픽 100GB/월 까지 무료.
