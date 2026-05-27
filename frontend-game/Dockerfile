# Multi-stage Node + nginx build for frontend-game.
#
# - Builder stage: node:20-alpine + pnpm builds the workspace and
#   produces dist/ via `pnpm --filter frontend-game build`.
# - Runtime stage: nginx:alpine + dist/ + custom nginx.conf with SPA
#   fallback. Tiny image (~25 MB).
#
# Build context = repo root (workspace root has pnpm-workspace.yaml).
# From the repo root:
#   docker build -t loreweave/frontend-game:0.0.0 \
#     -f frontend-game/Dockerfile .
#
# Run:
#   docker run --rm -p 5174:5174 loreweave/frontend-game:0.0.0
#
# Via compose (preferred — boots tilemap-service + game-server alongside):
#   docker compose --profile full up

# ─── Builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

# git: at least one workspace dep (colyseus.js → colyseus → @colyseus/schema)
# may pull from git URL. Same lesson as services/game-server/Dockerfile —
# alpine doesn't ship git by default. (See memory: alpine-npm-git-deps.)
RUN apk add --no-cache git

# Pin pnpm version to match root package.json packageManager field.
RUN npm install -g pnpm@9.15.9

WORKDIR /build

# Copy workspace manifest + lockfile + scope-pin config first so layer
# cache is granular: changes to source files don't invalidate the deps
# install layer.
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml .npmrc ./

# Copy the workspace packages (skeletons for now; will fill in V0+1+).
# These are direct deps of frontend-game per its package.json.
COPY packages ./packages

# Copy frontend-game manifest before src so deps install layer caches.
COPY frontend-game/package.json ./frontend-game/package.json

# Install ALL workspace deps (frozen lockfile = reproducible builds).
RUN pnpm install --frozen-lockfile

# Now copy the actual frontend-game source and build.
COPY frontend-game ./frontend-game

RUN pnpm --filter frontend-game build

# ─── Runtime ──────────────────────────────────────────────────────────
FROM nginx:alpine

# wget for docker compose healthcheck (`wget -qO- http://.../livez`).
# nginx:alpine doesn't ship wget by default.
RUN apk add --no-cache wget

# Drop default nginx config — our SPA config (port 5174, gzip, /livez,
# SPA fallback) replaces it.
RUN rm /etc/nginx/conf.d/default.conf
COPY frontend-game/nginx.conf /etc/nginx/conf.d/default.conf

# Drop the built SPA bundle into nginx's html root.
COPY --from=builder /build/frontend-game/dist /usr/share/nginx/html

EXPOSE 5174

# Default nginx ENTRYPOINT runs the foreground daemon — keeps container
# alive until docker stop / SIGTERM.
