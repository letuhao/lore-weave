# Multi-stage Node 20 build for game-server.
#
# Stage 1 (builder): install all deps + compile TypeScript → dist/
# Stage 2 (runtime): node 20 alpine + production deps only + dist/
#
# Build from repo root:
#   docker build -t loreweave/game-server:0.0.0 \
#     -f services/game-server/Dockerfile services/game-server
#
# Run:
#   docker run --rm -p 2567:2567 \
#     -e LOREWEAVE_INTERNAL_TOKEN=dev_token \
#     loreweave/game-server:0.0.0

# ─── Builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

# git: at least one Colyseus transitive dep is fetched from a git URL,
# and node:20-alpine doesn't ship git. Without this, `npm install`
# fails with "npm error syscall spawn git ... ENOENT".
RUN apk add --no-cache git

WORKDIR /build

# Install ALL deps (including dev) for TypeScript compile.
COPY package.json ./
RUN npm install --no-audit --no-fund

COPY tsconfig.json ./
COPY src ./src

RUN npm run build

# Prune dev deps so runtime stage gets only what's needed.
RUN npm prune --omit=dev

# ─── Runtime ──────────────────────────────────────────────────────────
FROM node:20-alpine

# wget for docker healthcheck against /matchmake (Colyseus exposes
# this Express endpoint for room discovery; non-200 means not ready).
RUN apk add --no-cache wget

WORKDIR /app

COPY --from=builder /build/node_modules ./node_modules
COPY --from=builder /build/dist ./dist
COPY --from=builder /build/package.json ./

# Env consumed at runtime:
#   PORT                       — listen port (default 2567 per Colyseus convention)
#   LOREWEAVE_INTERNAL_TOKEN   — V0 auth dev token; rooms reject jwt != this value
#   LOREWEAVE_CORS_ORIGINS     — comma-separated allowed origins for matchmaking HTTP
ENV NODE_ENV=production
ENV PORT=2567

USER node

EXPOSE 2567

CMD ["node", "dist/index.js"]
