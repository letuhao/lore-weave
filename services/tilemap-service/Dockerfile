# Multi-stage Rust build for tilemap-service.
# - Builder stage compiles a release binary with cached dependencies from
#   the LOREWEAVE Cargo workspace (sdks/rust/loreweave_llm + this service).
# - Runtime stage is debian:bookworm-slim + wget for docker healthcheck —
#   consistent with auth-service / book-service pattern (alpine + wget).
#
# Build context is the REPO ROOT (workspace root has the master Cargo.toml).
# From the repo root:
#   docker build -t loreweave/tilemap-service:0.1.0-phase0a \
#     -f services/tilemap-service/Dockerfile .
#
# Run:
#   docker run --rm -p 7100:7100 \
#     -e LOREWEAVE_INTERNAL_TOKEN=dev_token \
#     loreweave/tilemap-service:0.1.0-phase0a serve

# ─── Builder ──────────────────────────────────────────────────────────
FROM rust:1.89-slim-bookworm AS builder

WORKDIR /build

# Stage 1 — cache dependency compilation by copying only Cargo manifests
# first and stubbing out the source. Workspace deps (loreweave_llm) AND
# member deps (tilemap-service) both need stubs because cargo resolves
# the whole workspace before any build.
COPY Cargo.toml Cargo.lock ./
COPY sdks/rust/loreweave_llm/Cargo.toml ./sdks/rust/loreweave_llm/Cargo.toml
COPY services/tilemap-service/Cargo.toml ./services/tilemap-service/Cargo.toml

RUN mkdir -p sdks/rust/loreweave_llm/src \
            services/tilemap-service/src \
            services/tilemap-service/config \
 && echo "" > sdks/rust/loreweave_llm/src/lib.rs \
 && echo "fn main() {}" > services/tilemap-service/src/main.rs \
 && echo "" > services/tilemap-service/src/lib.rs \
 && touch services/tilemap-service/config/biome_bridge.toml \
 && cargo build --release -p tilemap-service --bin tilemap-service \
 && rm -rf sdks/rust/loreweave_llm/src \
           services/tilemap-service/src \
           services/tilemap-service/config \
           target/release/deps/tilemap_service* \
           target/release/deps/loreweave_llm* \
           target/release/tilemap-service*

# Stage 2 — real sources. Includes config/biome_bridge.toml because
# `BiomeBridge::load_default` reads it via `include_str!` at compile time.
COPY sdks/rust/loreweave_llm/src ./sdks/rust/loreweave_llm/src
COPY services/tilemap-service/src ./services/tilemap-service/src
COPY services/tilemap-service/config ./services/tilemap-service/config

RUN cargo build --release -p tilemap-service --bin tilemap-service

# ─── Runtime ──────────────────────────────────────────────────────────
# debian:bookworm-slim + wget (consistent with auth-service alpine+wget).
# Distroless would be ~25 MB but lacks wget/curl needed for docker
# healthcheck — switching base avoids the healthcheck-from-binary hack.
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/target/release/tilemap-service /app/tilemap-service

# Env consumed at runtime (CLAUDE.md "no hardcoded secrets" — server
# refuses to start if LOREWEAVE_INTERNAL_TOKEN is unset on the `serve`
# subcommand):
#   LOREWEAVE_INTERNAL_TOKEN  — REQUIRED for `serve`; Bearer for /internal/v1/*
#   TILEMAP_HTTP_BIND         — optional, default 0.0.0.0:7100
#   LOREWEAVE_GATEWAY_URL     — optional, default http://provider-registry-service:8085
#   LMSTUDIO_MODEL_REF        — REQUIRED for `classify` / `bootstrap` only
#   HARNESS_USER_ID           — REQUIRED for `classify` / `bootstrap` only
#   RUST_LOG                  — optional, default info,tilemap_service=debug
ENV RUST_LOG=info,tilemap_service=debug

USER nobody:nogroup

EXPOSE 7100

ENTRYPOINT ["/app/tilemap-service"]
CMD ["serve"]
