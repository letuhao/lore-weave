# LoreWeave — Module 01 monorepo

This repository **is** the monorepo root (`contracts/`, `services/`, `frontend/`, `infra/`). Clone it and run commands from the repo root, not from a nested `novel_analyzer/` folder.

Polyglot monorepo for **Identity** (register, session, profile, verify, reset).

| Path | Stack | Role |
|------|-------|------|
| `contracts/api/identity/v1/` | OpenAPI | Contract-first API |
| `services/auth-service/` | Go | Domain + persistence |
| `services/api-gateway-bff/` | NestJS | Client-facing proxy (no direct auth from browser) |
| `frontend/` | Vite + React + TS | Identity UI (visual refresh: **Tailwind + shadcn/ui** per [`23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md`](docs/03_planning/23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md)) |
| `infra/` | Docker Compose | Postgres, Mailhog, optional **full stack** (auth + gateway + FE) |

## Quick start (local)

**Option A — everything in Docker** (from `infra/`):

```bash
cd infra
docker compose up --build
```

Then open http://localhost:5173 (see [`docs/implementation/MODULE01_LOCAL_DEV.md`](docs/implementation/MODULE01_LOCAL_DEV.md) for ports and env).

**Option B — hybrid** (DB in Docker, apps on host):

1. **Postgres + Mailhog**

   ```bash
   cd infra
   docker compose up -d postgres mailhog
   ```

2. **Auth service** (listens `:8081`)

   ```bash
   cd services/auth-service
   cp .env.example .env
   go run ./cmd/auth-service
   ```

3. **API Gateway** (listens `:3000`, proxies `/v1` → auth)

   ```bash
   cd services/api-gateway-bff
   cp .env.example .env
   npm install
   npm run start:dev
   ```

4. **Frontend** (listens `:5173`, talks to gateway)

   ```bash
   cd frontend
   cp .env.example .env.development
   npm install
   npm run dev
   ```

Detailed ports and env: [`docs/implementation/MODULE01_LOCAL_DEV.md`](docs/implementation/MODULE01_LOCAL_DEV.md).

Token / crypto decisions: [`docs/implementation/ADR-001-module01-identity-tokens.md`](docs/implementation/ADR-001-module01-identity-tokens.md).

Optional smoke (PowerShell, gateway on `:3000`): `scripts/smoke-module01.ps1`.

Planning / governance docs live in [`docs/`](docs/). Approved Module 01 UI stack (LW-M01-23): Tailwind CSS, shadcn/ui (Radix), lucide-react, react-hook-form, zod.
