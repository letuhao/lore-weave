# world-service — the HTTP surface, packaged so the compose stack can reach it.
#
# WHY THIS EXISTS
# ---------------
# `F2`. world-service had no Dockerfile for its own binary — only
# `Dockerfile.orphan-scanner` — and no entry in `infra/docker-compose.yml`. So
# the one service that answers *"which actor does this user drive"* could not be
# reached by anything in the stack, and both of the player-edge phase's live
# proofs started it from source. A control-plane route nothing in the stack can
# call is reachable only by whoever remembers the incantation.
#
# WHY THE WHOLE WORKSPACE IS COPIED
# ---------------------------------
# Same trade `Dockerfile.orphan-scanner` states and for the same reason:
# world-service has eight workspace dependencies (meta-rs, rebuilder, dp-kernel,
# projections-canon, dp, service-http, …), and the tilemap-service shape — stub
# each member's sources to cache dependency compilation — needs a stub list that
# drifts from the manifest and fails mid-build as a confusing "could not find
# module". Copying once is slower and cannot drift.
#
# WHY `contracts/` IS IN THE RUNTIME IMAGE
# ----------------------------------------
# Two config values default to paths RELATIVE TO THE WORKING DIRECTORY:
# `PROVISION_SQL_DIR` (contracts/migrations/per_reality) and
# `PROVISION_META_ALLOWLIST` (contracts/meta/events_allowlist.yaml). This is not
# a detail — during `E5` the same relative default made the control-plane bind
# work from a shell and fail under `cargo test`, surfacing as a generic
# `500 actor-control write failed` because the handler's wildcard arm hides the
# cause. In a container the failure would look identical. So the contracts ship
# WITH the binary and `WORKDIR /app` is the directory they are relative to.
#
# Build context is the REPO ROOT (the workspace Cargo.toml lives there):
#   docker build -f services/world-service/Dockerfile -t loreweave/world-service .

FROM rust:1.89-slim-bookworm AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends pkg-config libssl-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY . .

# One binary. The rebuilder, the embedding worker, the drills and the
# actor-control worker are separate entry points with separate lifecycles.
RUN cargo build --release -p world-service --bin world-service

FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates wget \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /build/target/release/world-service /app/world-service
# The two relative defaults above. Copied as directories rather than named
# files so a new migration does not need a new COPY line — the failure mode
# that shape prevents is a migration that exists in the repo and not in the
# image, which reads as a missing table at runtime.
COPY contracts/migrations/per_reality /app/contracts/migrations/per_reality
COPY contracts/meta /app/contracts/meta

# Required at runtime; `Config::from_lookup` refuses to start without them and
# names every missing one at once:
#   LOREWEAVE_INTERNAL_TOKEN
#   PROVISION_META_DSN, PROVISION_SHARD_ADMIN_DSN
#   PROVISION_BRIDGE_URL, PROVISION_BRIDGE_TOKEN
#   PROVISION_SHARD_HOSTPORT, PROVISION_PG_USER
# Optional: PROVISION_PG_PASSWORD, PROVISION_SQL_DIR, PROVISION_META_ALLOWLIST,
#           WORLD_HTTP_BIND (default 0.0.0.0:7120)
EXPOSE 7120

USER nobody:nogroup

ENTRYPOINT ["/app/world-service"]
