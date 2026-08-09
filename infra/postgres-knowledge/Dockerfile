# LoreWeave knowledge Postgres — PG18 + pgvector + pgvectorscale (plan T22, decision T5).
#
# WHY THIS IMAGE EXISTS, AND WHAT IT COSTS
# ----------------------------------------
# Phase 3 moves the vector layer off Neo4j. The founding argument for that migration is
# OPERABILITY: one database instead of two. That argument inverts the moment a self-hoster
# has to compile Postgres extensions to run the product — which is exactly what the sealed
# design flagged (M4) as the place this migration can defeat its own purpose.
#
# So we publish a prebuilt image, and the cost is stated rather than discovered:
# **we own a Postgres distribution and its CVE cadence.** Three moving parts, pinned
# together, that must be re-pinned and re-tested on every security advisory affecting any
# of them. That is a standing obligation, not a one-off build.
#
# WHAT IS PINNED, AND WHY EACH IS PINNED THAT WAY
# -----------------------------------------------
# * PG 18 (bookworm, glibc). NOT alpine, though the dev compose uses `postgres:18-alpine`:
#   pgvectorscale ships prebuilt glibc binaries, and musl would mean compiling Rust/pgrx —
#   the very thing this image exists to spare people. The divergence from the dev image is
#   deliberate and is the reason it is written down here.
# * pgvector from the PGDG apt repo, version-pinned. It is packaged for PG18, so there is
#   no reason to build it.
# * pgvectorscale from its official release ZIP, version-pinned, arch-aware. 0.9.0 publishes
#   pg18 artifacts for amd64 AND arm64 — verified before choosing this route, because the
#   alternative (pgrx from source) would have added a multi-minute Rust toolchain to every
#   build and a compiler to the shipped layer.
#
# Both versions are ARGs so a security bump is a build argument, not a patch — and the
# CI check that pins them lives beside this file.

ARG PG_MAJOR=18
FROM postgres:${PG_MAJOR}-bookworm

ARG PG_MAJOR=18
# Pinned deliberately. Bumping either is a decision with a test attached (see the
# smoke below), never a silent `latest`.
ARG PGVECTOR_VERSION=0.8.6-1.pgdg12+1
ARG PGVECTORSCALE_VERSION=0.9.0

LABEL org.opencontainers.image.title="loreweave-postgres-knowledge" \
      org.opencontainers.image.description="PostgreSQL ${PG_MAJOR} with pgvector + pgvectorscale for the LoreWeave knowledge vector layer" \
      org.opencontainers.image.source="https://github.com/loreweave/lore-weave-mvp" \
      com.loreweave.pgvector.version="${PGVECTOR_VERSION}" \
      com.loreweave.pgvectorscale.version="${PGVECTORSCALE_VERSION}"

# curl/unzip are build-only: they are removed in the same layer so the shipped image has
# no download tooling in it.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        "postgresql-${PG_MAJOR}-pgvector=${PGVECTOR_VERSION}" \
        ca-certificates curl unzip; \
    \
    # pgvectorscale: official prebuilt release for this PG major + this architecture.
    # `dpkg --print-architecture` rather than uname: it yields Debian's amd64/arm64 names,
    # which are exactly the names the release assets use.
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64|arm64) ;; \
        *) echo "pgvectorscale publishes amd64/arm64 only; this is $arch" >&2; exit 1 ;; \
    esac; \
    asset="pgvectorscale-${PGVECTORSCALE_VERSION}-pg${PG_MAJOR}-${arch}.zip"; \
    curl -fsSL -o /tmp/pgvs.zip \
        "https://github.com/timescale/pgvectorscale/releases/download/${PGVECTORSCALE_VERSION}/${asset}"; \
    unzip -q -d /tmp/pgvs /tmp/pgvs.zip; \
    # The ZIP contains DEBIAN PACKAGES, not loose artifacts — two of them, the extension
    # and its debug symbols. Install the extension package only: shipping dbgsym would
    # roughly double the layer for symbols nobody debugs in production.
    #
    # Located by FINDING rather than by assuming a filename. The first version of this
    # file assumed loose `.so` / `.control` files, matched nothing, and installed nothing —
    # and the verification below is what turned that into a failed build instead of an
    # image that looks fine until someone runs CREATE EXTENSION.
    deb="$(find /tmp/pgvs -name 'pgvectorscale-postgresql-*.deb' ! -name '*dbgsym*' | head -1)"; \
    test -n "$deb"; \
    dpkg -i "$deb"; \
    \
    # BUILD-TIME VERIFICATION. Without this, a release whose layout changed installs
    # nothing at all and the image ships looking fine until someone runs CREATE EXTENSION
    # in production. Checking the files exist is not enough on its own — the runtime smoke
    # (docker-compose.knowledge-pg.yml / the T22 evidence) actually creates the extensions
    # and builds a 3072-dim index.
    test -f "$(pg_config --sharedir)/extension/vectorscale.control"; \
    test -f "$(pg_config --sharedir)/extension/vector.control"; \
    ls "$(pg_config --pkglibdir)"/vectorscale*.so >/dev/null; \
    \
    apt-get purge -y --auto-remove curl unzip; \
    rm -rf /tmp/pgvs /tmp/pgvs.zip /var/lib/apt/lists/*

# `vector` must be loadable before `vectorscale`, and vectorscale's own control file
# declares the dependency — so no shared_preload_libraries entry is needed for either.
# Recorded because the absence of a preload line looks like an omission otherwise.
