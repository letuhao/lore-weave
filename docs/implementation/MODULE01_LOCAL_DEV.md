# Module 01 — local development runbook

## Ports

| Service | Port | Notes |
|---------|------|--------|
| Postgres | 5432 | Docker Compose (`infra/docker-compose.yml`) |
| Mailhog UI | 8025 | Optional |
| Mailhog SMTP | 1025 | Optional |
| `auth-service` | 8081 | Go |
| `api-gateway-bff` | 3000 | NestJS reverse proxy to auth |
| `frontend` (Vite) | 5173 | `VITE_API_BASE` → gateway |

## One-time prerequisites

- Docker (for Postgres)
- Go 1.22+
- Node.js 20+

## Start infrastructure

**Postgres only** (run gateway/auth/FE on the host):

```bash
cd infra
docker compose up -d postgres
```

## Full stack (Docker Compose)

Builds and runs Postgres, Mailhog, `auth-service`, `api-gateway-bff`, and the frontend (static build behind nginx). From `infra/`:

```bash
docker compose up --build
```

Open **http://localhost:5173** (UI). Gateway **http://localhost:3000**, auth **http://localhost:8081**, Mailhog UI **http://localhost:8025**.

- Default `JWT_SECRET` is suitable for local dev only; override with env `JWT_SECRET` (≥ 32 chars) or `infra/.env` (see `infra/.env.example`).
- `VITE_API_BASE` is baked in at **image build** time (default `http://localhost:3000`). If the browser must use another host/port, rebuild with e.g. `VITE_API_BASE=http://192.168.1.10:3000 docker compose build frontend`.

## Auth service

```bash
cd services/auth-service
cp .env.example .env
# Edit JWT_SECRET (>= 32 chars) and DATABASE_URL if needed
go run ./cmd/auth-service
```

Migrations run automatically on startup (`internal/migrate`).

## API gateway

```bash
cd services/api-gateway-bff
cp .env.example .env
npm ci
npm run start:dev
```

`bodyParser` is disabled so request bodies stream to auth (required for proxy).

## Frontend

```bash
cd frontend
cp .env.example .env.development   # optional; repo includes dev defaults
npm ci
npm run dev
```

Open `http://localhost:5173`. All API calls go to `VITE_API_BASE` (gateway).

## Email (Mailhog + SMTP)

**Docker full stack** (`docker compose up` from `infra/`): Mailhog runs on **SMTP `:1025`**, web UI **http://localhost:8025**. `auth-service` is configured to send verification and password-reset messages there. On **register**, a verification email is sent when `SMTP_HOST` is set. **Mailhog only captures mail** — nothing is delivered to Gmail or the public internet.

**Hybrid (auth on host, Mailhog in Docker):** `docker compose up -d mailhog` then in `services/auth-service/.env` set:

```env
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_FROM=LoreWeave <noreply@loreweave.local>
PUBLIC_APP_URL=http://localhost:5173
```

**Without SMTP** (`SMTP_HOST` empty): no email is sent; with `DEV_LOG_EMAIL_TOKENS=1` (default), tokens still print to **auth-service stdout** for the Verify and Reset pages.

## Contract lint

```bash
cd contracts
npx @stoplight/spectral-cli lint api/identity/v1/openapi.yaml
```

## Unit tests (no running services required)

From the **repository root** (or `cd` into each path first):

```bash
cd services/auth-service && go test -race ./... && cd ../..
cd services/api-gateway-bff && npm ci && npm test && cd ../..
cd frontend && npm ci && npm test && cd ..
```

On Windows, from repo root: `pwsh -File scripts/test-module01.ps1` (runs the same three suites; run `npm ci` in gateway/frontend once if `node_modules` is missing).

## Smoke checks (manual)

1. Register a user (password: 8+ chars, include a letter and a digit).
2. Login → Profile loads via access token.
3. Refresh: expire access (wait) or delete from localStorage access only — Profile should trigger refresh flow when implemented client-side.
4. Logout → session revoked server-side.

## Acceptance mapping

Critical scenarios **M01-AT-01 … M01-AT-10** can be exercised through the UI plus browser devtools network captures as evidence (see planning doc `14_MODULE01_ACCEPTANCE_TEST_PLAN.md`).
