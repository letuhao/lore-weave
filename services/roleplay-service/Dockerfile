# Multi-stage Rust build for roleplay-service.
# - Builder compiles a release binary with cached deps from the LoreWeave
#   Cargo workspace (crates/service-http + this service).
# - Runtime is debian:bookworm-slim + wget for the docker healthcheck —
#   consistent with tilemap-service / auth-service.
#
# Build context is the REPO ROOT (the workspace root has the master Cargo.toml).
# From the repo root:
#   docker build -t loreweave/roleplay-service:0.1.0-v1 \
#     -f services/roleplay-service/Dockerfile .

# ─── Builder ──────────────────────────────────────────────────────────
FROM rust:1.89-slim-bookworm AS builder

WORKDIR /build

# The LoreWeave Rust workspace has 24 members; cargo must load EVERY member's
# manifest before it can build any one package (`-p`). Stub-caching all 24 (the
# old tilemap pattern) is brittle and breaks each time a member is added — so we
# copy the whole workspace source in one layer (the repo-root .dockerignore
# already strips target/, node_modules/, .git/, docs/). `cargo build -p` then
# compiles only roleplay-service + its dep graph (service-http + crates), not
# the other members. migrations/ is included — sqlx::migrate! embeds it at
# compile time.
COPY . .

RUN cargo build --release -p roleplay-service --bin roleplay-service

# ─── Runtime ──────────────────────────────────────────────────────────
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/target/release/roleplay-service /app/roleplay-service

# Env consumed at runtime (CLAUDE.md "no hardcoded secrets" — the binary
# refuses to start if any REQUIRED secret is unset):
#   DATABASE_URL              — REQUIRED (postgres://…/loreweave_roleplay)
#   JWT_SECRET                — REQUIRED (HS256 user-JWT validation)
#   LOREWEAVE_INTERNAL_TOKEN  — REQUIRED (X-Internal-Token; chat-service call)
#   CHAT_SERVICE_URL          — REQUIRED (start-orchestration target, R1)
#   ROLEPLAY_HTTP_BIND        — optional, default 0.0.0.0:7110
#   LOREWEAVE_CORS_ORIGINS    — optional, default http://localhost:5174
#   RUST_LOG                  — optional, default info
ENV RUST_LOG=info

USER nobody:nogroup

EXPOSE 7110

ENTRYPOINT ["/app/roleplay-service"]
