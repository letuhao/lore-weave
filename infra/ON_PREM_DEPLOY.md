# On-Prem Single-Port Deploy (ngrok-first)

Expose LoreWeave through **one host port** (default **5296**). Nginx in the `frontend` container serves the SPA and proxies `/v1`, `/ws`, `/languagetool`, MinIO buckets, and `/health` to internal services. No AWS ALB required for this phase — use **ngrok** as the HTTPS edge.

## Architecture

```
Internet → ngrok HTTPS → host :5296 → frontend nginx :80
                              ├─ /              → SPA
                              ├─ /v1, /ws       → api-gateway-bff
                              ├─ /health        → api-gateway-bff
                              ├─ /languagetool  → languagetool
                              └─ /{bucket}/…    → minio (media same-origin)
```

Later on AWS: replace ngrok with **ALB → frontend:5296**; internal Docker network unchanged.

## Quick start

1. Copy env file:

   ```bash
   cp infra/.env.example infra/.env
   # Edit JWT_SECRET (>= 32 chars)
   ```

2. Deploy:

   ```bash
   # Linux/macOS/Git Bash
   scripts/deploy-onprem.sh

   # Windows PowerShell
   scripts/deploy-onprem.ps1
   ```

3. Tunnel (optional, public HTTPS):

   ```bash
   ngrok http 5296   # or your PUBLIC_HTTP_PORT
   ```

4. Set `PUBLIC_APP_URL=https://….ngrok-free.app` in `infra/.env`, then recreate:

   ```bash
   cd infra
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

5. Smoke:

   ```bash
   infra/smoke-onprem.sh http://localhost:5296
   # After ngrok:
   infra/smoke-onprem.sh https://your-subdomain.ngrok-free.app
   ```

   Windows PowerShell: `.\infra\smoke-onprem.ps1 http://localhost:5296`

6. Real test (auth round-trip + same-origin checks):

   ```bash
   infra/realtest-onprem.sh http://localhost:5296
   # Reuse seeded account:
   REALTEST_EMAIL=claude-test@loreweave.dev REALTEST_PASSWORD='…' \
     infra/realtest-onprem.sh https://your-ngrok-url.ngrok-free.app
   ```

7. Full review (offline + smoke + real when stack is up):

   ```bash
   infra/review-onprem.sh                          # unit tests + compose only
   infra/review-onprem.sh http://localhost:5296    # all layers
   ```

## Security (go-live)

Before exposing via ngrok, complete [SECURITY_GO_LIVE_REVIEW.md](./SECURITY_GO_LIVE_REVIEW.md):

```bash
infra/sec-review-onprem.sh http://localhost:5296
infra/sec-review-idor.sh http://localhost:5296
```

**Do not go live** if dev compose (multi-port) runs alongside prod on the same host, or if any P0 check in the security doc fails.

## Compose files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Full dev stack (many host ports) |
| `docker-compose.prod.yml` | Overlay: single public port, no host binds on backends, prod secrets |

```bash
cd infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Environment variables

| Variable | Required (prod) | Description |
|----------|-----------------|-------------|
| `JWT_SECRET` | Yes (≥32 chars) | Shared JWT for all services + BFF WS/SSE |
| `INTERNAL_SERVICE_TOKEN` | Yes (≥32 chars, ≠ JWT) | Service-to-service `/internal/*` auth |
| `PUBLIC_HTTP_PORT` | No (default `5296`) | Only host port published |
| `PUBLIC_APP_URL` | After ngrok/domain | Browser-visible origin; email links + MinIO URLs |
| `MINIO_EXTERNAL_URL` | No | Defaults to `PUBLIC_APP_URL` in prod overlay |

Frontend prod build uses **`VITE_API_BASE=""`** (same-origin `/v1` via nginx). Do **not** rebuild FE when ngrok URL changes — only update `PUBLIC_APP_URL` and recreate backend services.

## FE ↔ BFF audit (novel app)

All novel UI API calls go through BFF except grammar (nginx → languagetool) and media (nginx → MinIO).

| Service | FE prefix | BFF route |
|---------|-----------|-----------|
| auth-service | `/v1/auth`, `/v1/account`, `/v1/users`, `/v1/me/preferences` | authProxy |
| book-service | `/v1/books/*` | bookProxy |
| sharing-service | `/v1/sharing/*` | sharingProxy |
| catalog-service | `/v1/catalog/*` | catalogProxy |
| provider-registry | `/v1/model-registry/*` (+ STT/TTS proxy paths) | providerRegistryProxy |
| provider-registry | `/v1/llm/*` (scripts/API; FE uses model-registry proxy) | llmProxy |
| usage-billing | `/v1/model-billing/*` | usageBillingProxy |
| translation-service | `/v1/translation/*`, `/v1/extraction/*` | translation + extraction |
| glossary-service | `/v1/glossary/*` | glossaryProxy |
| chat-service | `/v1/chat/*` | chatProxy |
| video-gen-service | `/v1/video-gen/*` | videoGenProxy |
| statistics-service | `/v1/leaderboard/*`, `/v1/stats/*` | statisticsProxy |
| notification-service | `/v1/notifications/*` (CRUD) | notificationProxy |
| notification SSE | `/v1/notifications/stream` | BFF local (RabbitMQ) |
| knowledge-service | `/v1/knowledge/*` | knowledgeProxy |
| lore-enrichment | `/v1/lore-enrichment/*` | loreEnrichmentProxy |
| learning-service | `/v1/learning/*` | learningProxy |
| composition-service | `/v1/composition/*` | compositionProxy |
| WebSocket | `/ws` | BFF local (RabbitMQ) |
| Grammar | `/languagetool/*` | nginx → languagetool |
| Media | `/v1/books/{id}/media/object` (private) or public buckets in dev | book-service / nginx → minio |

**Not behind BFF (by design):** workers, postgres, redis, rabbitmq, neo4j, mailhog, pandoc, optional game/tilemap profiles.

## MinIO / media (prod vs dev)

**Prod overlay** (`nginx.prod.conf`): no anonymous bucket proxy. Book media uses authenticated `/v1/books/{id}/media/object?stream_token=…`.

**Dev** (`nginx.conf`): may proxy buckets (`loreweave-dev-books`, `lw-chat`, etc.) — do **not** expose dev compose on a public host.

`MINIO_EXTERNAL_URL` must equal the browser origin (`PUBLIC_APP_URL` or `http://localhost:5296` for local prod without ngrok).

## NO-GO checklist

- Do not run **dev** compose (`docker-compose.yml` only) on a host reachable from the internet.
- Always deploy prod via `scripts/deploy-onprem.*` (runs `build-stack.sh` + `docker compose … --build`).
- After `git pull`, rebuild — stale images skip P1 flags (registration gate, stream-ticket, prod nginx).
- Set `REALTEST_EMAIL` / `SEC_REVIEW_EMAIL_*` in `infra/.env` when `ALLOW_PUBLIC_REGISTRATION=false`.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| API calls go to `:3123` | Rebuild frontend with prod overlay (`VITE_API_BASE=""`) |
| Media 404 | `PUBLIC_APP_URL` set? nginx bucket location matches bucket name? |
| WS fails | JWT valid? RabbitMQ healthy? |
| Compose fails on JWT | Set `JWT_SECRET` in `infra/.env` |

## Review checklist (mọi môi trường)

Dùng **cùng script**, chỉ đổi `BASE_URL` — localhost, ngrok, hay domain sau này.

| Layer | Khi nào | Lệnh | Pass criteria |
|-------|---------|------|---------------|
| **0 — Offline** | Trước merge / CI | `infra/review-onprem.sh` | BFF 18 tests pass; `docker compose … config` OK |
| **1 — Smoke** | Stack vừa lên | `infra/smoke-onprem.sh $BASE` | `/health` 200; `/v1/books` 401; catalog 200; llm 401 not 404; languagetool 200 |
| **2 — Real** | Sau smoke | `infra/realtest-onprem.sh $BASE` | Login (or register if enabled) → profile + books + notifications; SPA không chứa `localhost:3123` |
| **3 — Browser** | Trước demo/public | Manual | Network tab: mọi `/v1/*` **same origin**; cover upload → URL `{BASE}/loreweave-dev-books/…`; WS `/ws` connects |

### Ma trận theo môi trường

| Môi trường | `BASE_URL` | Sau deploy cần làm thêm |
|------------|------------|-------------------------|
| Local prod overlay | `http://localhost:5296` | Chỉ cần `JWT_SECRET` trong `.env` |
| ngrok | `https://….ngrok-free.app` | Set `PUBLIC_APP_URL` → `docker compose … up -d` (recreate backends) |
| Domain / ALB (sau) | `https://app.example.com` | Cùng flow như ngrok; ALB trỏ `:5296` |

### Playwright (optional, full UI)

Với stack prod đang chạy qua `:5296`:

```bash
cd frontend
PLAYWRIGHT_BASE_URL=http://localhost:5296 npx playwright test tests/e2e/specs/login.spec.ts
```

Điều chỉnh `PLAYWRIGHT_BASE_URL` thành ngrok URL khi test qua tunnel.

### Lệnh nhanh (copy-paste)

```bash
# 1. Deploy
cp infra/.env.example infra/.env   # sửa JWT_SECRET
scripts/deploy-onprem.sh          # hoặc deploy-onprem.ps1

# 2. Review đầy đủ
infra/review-onprem.sh http://localhost:5296

# 3. Sau ngrok
#    PUBLIC_APP_URL=https://….ngrok-free.app trong infra/.env
#    cd infra && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
infra/review-onprem.sh https://YOUR-NGROK-URL.ngrok-free.app
```

## Out of scope (later)

- AWS ALB / ACM / ECS
- Caddy TLS on-prem (when dropping ngrok)
- Game stack via BFF
- Production SMTP (replace Mailhog; use `--profile dev-mail` temporarily without exposing Mailhog UI)
