# Multi-stage Rust build for tilemap-service (PoC Phase 0a).
# - Builder stage compiles a release binary with cached dependencies.
# - Runtime stage is distroless for minimal attack surface.
#
# Build:
#   docker build -t loreweave/tilemap-service:0.1.0-phase0a -f services/tilemap-service/Dockerfile services/tilemap-service
#
# Run (Phase 0a — no network call, just prints scaffold info):
#   docker run --rm \
#     -e LOREWEAVE_INTERNAL_TOKEN=dev_token \
#     loreweave/tilemap-service:0.1.0-phase0a

# ─── Builder ──────────────────────────────────────────────────────────
FROM rust:1.89-slim-bookworm AS builder

WORKDIR /build

# Cache dependencies first — invalidates only when Cargo.toml changes.
COPY Cargo.toml ./
RUN mkdir -p src \
 && echo "fn main() {}" > src/main.rs \
 && echo "" > src/lib.rs \
 && cargo build --release \
 && rm -rf src target/release/deps/tilemap_service* target/release/tilemap-service*

# Now bring in real sources + rebuild.
COPY src ./src
COPY tests ./tests
RUN cargo build --release --bin tilemap-service \
 && cargo test --release --no-run

# ─── Runtime ──────────────────────────────────────────────────────────
# Distroless cc image: glibc + CA certs, no shell. ~25MB.
FROM gcr.io/distroless/cc-debian12:nonroot

WORKDIR /app

COPY --from=builder /build/target/release/tilemap-service /app/tilemap-service

# Configurable via env vars (CLAUDE.md "no hardcoded secrets" — fails fast if missing):
#   LOREWEAVE_INTERNAL_TOKEN  — REQUIRED — Bearer for /internal/llm/stream
#   LOREWEAVE_GATEWAY_URL     — optional, defaults to http://provider-registry-service:8085
#   RUST_LOG                  — optional, defaults to info,tilemap_service=debug
ENV RUST_LOG=info,tilemap_service=debug

USER nonroot:nonroot

ENTRYPOINT ["/app/tilemap-service"]
