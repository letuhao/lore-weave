# Module 01 — local development runbook

## Ports

| Service | Port | Notes |
|---------|------|--------|
| Postgres (host) | 5555 | Docker Compose (`infra/docker-compose.yml`) |
| Mailhog UI (host) | 8148 | Optional |
| Mailhog SMTP (host) | 1148 | Optional |
| `api-gateway-bff` (host) | 3123 | Container listens on :3000 |
| `frontend` Docker nginx (host) | 5174 | Static prod build |
| `frontend` Vite dev | 5174 | Proxies `/v1` → gateway :3123 |
| On-prem prod overlay | 5296 | Single public port — see `infra/ON_PREM_DEPLOY.md` |

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

Open **http://localhost:5174** (UI). Gateway **http://localhost:3123**. Mailhog UI **http://localhost:8148**.

- Default `JWT_SECRET` is suitable for local dev only; override with env `JWT_SECRET` (≥ 32 chars) or `infra/.env` (see `infra/.env.example`).
- Dev frontend uses **relative `/v1`** via Vite proxy → `:3123`. Prod/on-prem uses `docker-compose.prod.yml` — see `infra/ON_PREM_DEPLOY.md`.

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

Open `http://localhost:5174`. API calls use relative `/v1` (Vite proxy → gateway :3123).

**UI stack:** The Vite app uses **Tailwind CSS**, **shadcn/ui** (Radix), **lucide-react**, **react-hook-form**, and **zod** — see `docs/03_planning/23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md`. Global styles live in `src/index.css`. After pulling dependency changes, run **`npm ci`** in `frontend/` so the lockfile matches `package.json`.

## Email (Mailhog + SMTP)

**Docker full stack** (`docker compose up` from `infra/`): Mailhog runs on **SMTP `:1025`**, web UI **http://localhost:8025**. `auth-service` is configured to send verification and password-reset messages there. On **register**, a verification email is sent when `SMTP_HOST` is set. **Mailhog only captures mail** — nothing is delivered to Gmail or the public internet.

**Hybrid (auth on host, Mailhog in Docker):** `docker compose up -d mailhog` then in `services/auth-service/.env` set:

```env
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_FROM=LoreWeave <noreply@loreweave.local>
PUBLIC_APP_URL=http://localhost:5174
```

**Without SMTP** (`SMTP_HOST` empty): no email is sent. Set `DEV_LOG_EMAIL_TOKENS=1` in `infra/.env` only when you need verify/reset tokens printed to **auth-service stdout** (default is off for security). **Never** enable this in prod overlay.

## Module 02 prep (object storage — planning)

Module 02 will store book **covers** and chapter **`.txt`** files in **S3-compatible** object storage. **Dev** is expected to use **MinIO** (see `docs/01_foundation/04_TECHSTACK_SERVICE_MATRIX.md` and `docs/03_planning/30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`). Typical MinIO ports are API **9000** and console **9001**; **verify against `infra/docker-compose.yml`** when MinIO is added to Compose. `book-service` should read `BOOKS_STORAGE_BUCKET`, endpoint, and credentials from env **inside the private network** only (never exposed to the browser).

## Contract lint

```bash
cd contracts
npx @stoplight/spectral-cli lint api/identity/v1/openapi.yaml api/books/v1/openapi.yaml api/sharing/v1/openapi.yaml api/catalog/v1/openapi.yaml
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

**Status (2026-03-21):** A **lightweight smoke** of the above was run on **dev/local** after the Tailwind + shadcn/ui UI rollout (navigation, register/login, profile). This does **not** replace the full acceptance matrix.

## Acceptance mapping

Critical scenarios **M01-AT-01 … M01-AT-10** can be exercised through the UI plus browser devtools network captures as evidence (see planning doc `14_MODULE01_ACCEPTANCE_TEST_PLAN.md`). **Formal execution** of that matrix with evidence artifacts is **deferred**; see `docs/implementation/MODULE01_DEFERRED_FOLLOWUPS.md` (LW-IMPL-M01-01).
