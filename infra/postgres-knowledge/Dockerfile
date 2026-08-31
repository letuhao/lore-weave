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
# * PG 18 (TRIXIE, glibc). NOT alpine, though the dev compose uses `postgres:18-alpine`:
#   pgvectorscale ships prebuilt glibc binaries, and musl would mean compiling Rust/pgrx —
#   the very thing this image exists to spare people. The divergence from the dev image is
#   deliberate and is the reason it is written down here.
# * pgvector from the PGDG apt repo, version-pinned. It is packaged for PG18, so there is
#   no reason to build it.
# * pgvectorscale from its official release ZIP, version-pinned, arch-aware. 0.9.0 publishes
#   pg18 artifacts for amd64 AND arm64 — verified before choosing this route, because the
#   alternative (pgrx from source) would have added a multi-minute Rust toolchain to every
#   build and a compiler to the shipped layer.
# * Apache AGE, copied from the official `apache/age` image (T42b) — see below.
#
# All versions are ARGs so a security bump is a build argument, not a patch — and the
# CI check that pins them lives beside this file.
#
# ── T42b · WHY THE BASE MOVED bookworm → trixie ──────────────────────────────────────────
# The graph engine becomes a candidate for this same Postgres (decision X3 makes the engine
# layer 1; T1/T2 restore AGE to the candidate set). AGE therefore belongs in this extension
# matrix, which decision T5 already accepted owning.
#
# The obvious route — multi-stage COPY of AGE's artifacts onto the bookworm base — was tried
# and FAILS, measured rather than predicted:
#
#     ERROR: could not load library ".../age.so": /lib/x86_64-linux-gnu/libc.so.6:
#            version `GLIBC_2.38' not found (required by .../age.so)
#
# `apache/age` is built on **trixie** (glibc 2.41); bookworm ships 2.36. **glibc is backward
# compatible, not forward** — a binary built against a newer glibc cannot run on an older
# one. So the base moves UP rather than AGE moving down, and that direction is the safe one:
# pgvectorscale's prebuilt binaries keep working on a NEWER glibc, whereas the reverse is the
# failure above. Moving the base costs one pin (`pgdg12` → `pgdg13` for pgvector); building
# AGE from source instead would have put a C toolchain in the build for an extension that
# already ships a working binary.
#
# The runtime smoke is what makes this safe to change: it creates all three extensions and
# exercises them, so a glibc or packaging regression fails there rather than in production.

ARG PG_MAJOR=18
# ⚠️ AGE's official image is the SOURCE of the age.so this image copies, so its base and this
# one must stay on the same Debian release. Pinned by digest-free tag deliberately: the
# smoke below is what certifies a bump, not the tag.
FROM apache/age:latest AS age
FROM postgres:${PG_MAJOR}-trixie

ARG PG_MAJOR=18
# Pinned deliberately. Bumping any is a decision with a test attached (see the
# smoke below), never a silent `latest`.
# ⚠️ `pgdg13` — Debian 13 (trixie). It was `pgdg12` while this image was bookworm-based; the
# suffix tracks the base's Debian release and is the pin most likely to be missed on a bump.
ARG PGVECTOR_VERSION=0.8.6-1.pgdg13+1
ARG PGVECTORSCALE_VERSION=0.9.0
ARG AGE_VERSION=1.7.0

LABEL org.opencontainers.image.title="loreweave-postgres-knowledge" \
      org.opencontainers.image.description="PostgreSQL ${PG_MAJOR} with pgvector + pgvectorscale + Apache AGE for the LoreWeave knowledge substrate" \
      org.opencontainers.image.source="https://github.com/loreweave/lore-weave-mvp" \
      com.loreweave.pgvector.version="${PGVECTOR_VERSION}" \
      com.loreweave.pgvectorscale.version="${PGVECTORSCALE_VERSION}" \
      com.loreweave.age.version="${AGE_VERSION}"

# Apache AGE — the extension binary + its control/SQL, lifted from the official image.
# Copied rather than built because AGE already publishes a working PG18 artifact, and this
# image's whole premise is not shipping a compiler. The build-time verification below is
# what turns a changed upstream layout into a failed build instead of a broken image.
COPY --from=age /usr/lib/postgresql/${PG_MAJOR}/lib/age.so /usr/lib/postgresql/${PG_MAJOR}/lib/
COPY --from=age /usr/share/postgresql/${PG_MAJOR}/extension/age.control \
                /usr/share/postgresql/${PG_MAJOR}/extension/
COPY --from=age /usr/share/postgresql/${PG_MAJOR}/extension/age--${AGE_VERSION}.sql \
                /usr/share/postgresql/${PG_MAJOR}/extension/

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
    # AGE (T42b), same standard as the other two. The `ldd` line is the one that matters and
    # is not decoration: the bookworm attempt copied cleanly and only failed at CREATE
    # EXTENSION with `GLIBC_2.38 not found`. A file-existence check would have passed it.
    # This makes an ABI mismatch a BUILD failure instead of a runtime one.
    test -f "$(pg_config --sharedir)/extension/age.control"; \
    test -f "$(pg_config --pkglibdir)/age.so"; \
    ldd "$(pg_config --pkglibdir)/age.so" | grep -q 'not found' \
      && { echo "age.so has unresolved libraries — base/AGE glibc mismatch" >&2; exit 1; } \
      || true; \
    \
    apt-get purge -y --auto-remove curl unzip; \
    rm -rf /tmp/pgvs /tmp/pgvs.zip /var/lib/apt/lists/*

# `vector` must be loadable before `vectorscale`, and vectorscale's own control file
# declares the dependency — so no shared_preload_libraries entry is needed for either.
# Recorded because the absence of a preload line looks like an omission otherwise.
