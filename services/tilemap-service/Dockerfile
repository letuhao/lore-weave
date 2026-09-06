# Multi-stage Rust build for tilemap-service.
# - Builder stage copies the whole workspace once (see the HOTFIX comment
#   below for why — a per-member manifest cache trick used to live here and
#   silently broke every time a new workspace crate was added) and compiles
#   a release binary.
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

# HOTFIX 2026-09-06 — this used to cache dependency compilation by copying
# only two members' Cargo.toml (loreweave_llm + this service) and stubbing
# their source, on the theory that those were the only workspace members
# tilemap-service's build touches. That was never true: a virtual workspace
# resolves EVERY member listed in the root Cargo.toml before `cargo build -p`
# does anything, lockfile included, so any member not copied breaks the
# build the moment cargo reaches it in the member list — which a `--no-cache`
# rebuild does immediately, cache-masked builds do not. It broke on
# `services/world-service` this time (added well after this Dockerfile was
# written); it would have broken on the next uncopied member after that.
#
# `services/world-service/Dockerfile`'s own header already documents this
# exact failure mode and the fix — *"the tilemap-service shape ... needs a
# stub list that drifts from the manifest and fails mid-build ... copying
# once is slower and cannot drift"* — written when world-service was built,
# never back-applied here. Doing that now: copy the whole context once,
# like world-service and roleplay-service already do, instead of hand-
# maintaining a stub list that silently goes stale every time a crate is
# added to the workspace.
COPY . .

# Includes config/biome_bridge.toml because `BiomeBridge::load_default`
# reads it via `include_str!` at compile time.
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
