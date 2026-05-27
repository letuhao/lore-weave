# Plan — Session F: frontend-game Dockerfile + docker-compose entry

> **Spec:** `docs/specs/2026-05-24-frontend-game-architecture.md` (§16 Session F, AC-FG-11)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Size:** L (6 files; final V0 milestone)
> **Predecessor:** Session E (commit abdad207) — game-server WS echo working end-to-end

## Goal

Final piece of V0 per spec §16: containerize `frontend-game/` so a
single `docker compose --profile full up` boots tilemap-service +
game-server + frontend-game and the user can open `localhost:5174` for
the complete demo (iso tilemap + click-to-walk Player + HUD reading
TanStack Query `/livez` + WS echo panel).

## Stack decision

Standard React/Vite SPA dockerization:
- **Stage 1 (builder):** node:20-alpine + pnpm + workspace context → build static dist
- **Stage 2 (runtime):** nginx:alpine + COPY dist + nginx.conf with SPA fallback

Rationale:
- nginx is the industry default for serving SPA dist — battle-tested, tiny image, gzip + caching built in
- `serve` (npm package) is fine for dev but lacks production knobs
- Vite preview is for build-verification only, not prod

## Build context decision

Build context = **repo root**, NOT `frontend-game/`. Reason:
- `frontend-game/` depends on 4 `@loreweave/*` workspace packages
- pnpm-workspace.yaml lives at repo root
- pnpm install needs the workspace root + packages/ + frontend-game/ all in context
- Same pattern as `services/tilemap-service/Dockerfile` (build from repo root)

`.dockerignore` excludes `node_modules`, `dist`, `.git`, `target`,
`services/*` (not needed for frontend-game build) to keep context small.

## Files (6)

| # | File | Purpose |
|---|---|---|
| 1 | `frontend-game/Dockerfile` | Multi-stage Node 20 → nginx alpine |
| 2 | `frontend-game/nginx.conf` | SPA fallback to index.html, gzip, /livez |
| 3 | `frontend-game/.dockerignore` | Exclude node_modules / dist / git from build context |
| 4 | `infra/docker-compose.yml` | + frontend-game entry, port 5174, profile [game, full] |
| 5 | `docs/plans/2026-05-24-frontend-game-session-f-docker.md` | This file |
| 6 | `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` | UPDATE — V0 COMPLETE entry |

## Dockerfile sketch

```dockerfile
FROM node:20-alpine AS builder
RUN apk add --no-cache git  # workspace deps may include git URLs (lesson from Session E)
RUN npm install -g pnpm@9.15.9  # match packageManager in root package.json
WORKDIR /build
# Copy workspace root + relevant packages + frontend-game src
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml .npmrc ./
COPY packages ./packages
COPY frontend-game ./frontend-game
RUN pnpm install --frozen-lockfile
RUN pnpm --filter frontend-game build

FROM nginx:alpine
COPY --from=builder /build/frontend-game/dist /usr/share/nginx/html
COPY frontend-game/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5174
HEALTHCHECK CMD wget -qO- http://localhost:5174/livez || exit 1
```

## nginx.conf sketch

```nginx
server {
  listen 5174;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  gzip on;
  gzip_types text/css application/javascript application/json image/svg+xml;
  gzip_min_length 1024;

  # SPA fallback: any unmatched route → index.html so React Router handles it
  location / {
    try_files $uri $uri/ /index.html;
  }

  # Health probe for docker compose
  location = /livez {
    add_header Content-Type application/json;
    return 200 '{"status":"ok","service":"frontend-game"}';
  }
}
```

## Compose entry sketch

```yaml
frontend-game:
  build:
    context: ..
    dockerfile: frontend-game/Dockerfile
  ports:
    - "5174:5174"
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://localhost:5174/livez"]
    interval: 10s
    timeout: 5s
    retries: 3
    start_period: 5s
  restart: on-failure:5
  profiles:
    - game
    - full
```

## V1+ considerations (NOT in scope)

- Env-var injection of service URLs (tilemap-service / game-server) at build time → for now hardcoded `localhost:8220` and `localhost:2567` because compose --profile full exposes those host ports
- CDN deploy (S3 + CloudFront / Vercel / etc) → V2+
- HTTPS / SSL termination → handled by api-gateway-bff or external load balancer
- Cache headers / asset versioning → V1 when first real deploy happens

## Verification (Phase 6 evidence)

1. `docker compose --profile full build frontend-game` → multi-stage build succeeds
2. `docker compose --profile full up -d` → all 3 services healthy (tilemap-service, game-server, frontend-game)
3. `curl http://localhost:5174/livez` → 200 + json
4. Playwright open `http://localhost:5174/play`:
   - Iso tilemap visible
   - HUD shows `tilemap-service: ok`
   - EchoPanel shows `game-server: connected`
   - Type message → echo back
5. `docker compose --profile full down` cleanly tears everything down

## Risk register

| Risk | Mitigation |
|---|---|
| pnpm install with --frozen-lockfile fails because lockfile out-of-date | Run `pnpm install` locally before commit to refresh lockfile |
| pnpm version mismatch (Dockerfile uses 9.15.9, root packageManager says 9.15.9) | Pin both; verified |
| nginx default 80 vs our 5174 | Override listen directive in nginx.conf |
| SPA fallback breaks asset URLs (mime types) | nginx auto-detects mime; only routes WITHOUT file extension fall through to index.html via try_files |
| Healthcheck `wget` not in nginx:alpine | nginx:alpine ships wget; verified by tilemap-service Dockerfile pattern |
| Browser still hits localhost:8220/2567 even when frontend serves from docker | Works because compose exposes those ports to host — browser sees them as separate localhost services |
| Cross-tool .npmrc cascade (Session B lesson) | Repo-root .npmrc only has scope pin; safe for Dockerfile COPY |
