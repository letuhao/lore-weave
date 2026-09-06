# Postgres 18 + pgvector, built against THIS image's own server.
#
# WHY NOT `pgvector/pgvector:pg18`
# -------------------------------
# The official pgvector images are Debian/glibc. The running stack is
# `postgres:18-alpine` — `PostgreSQL 18.1 on x86_64-pc-linux-musl` — and its data
# directory is a persistent named volume (`loreweave_pg`) holding **139
# databases**. Postgres resolves text collation through libc, so moving that data
# directory from a musl build to a glibc build changes the sort order behind
# every text index without changing the data. The indexes do not raise an error;
# they silently stop matching. Swapping to the Debian image would mean reindexing 139
# databases to avoid a corruption class that is hard to notice and harder to
# attribute. Keeping musl removes the question.
#
# WHY NOT `apk add postgresql-pgvector`
# ------------------------------------
# Alpine does package it (0.8.1-r0), and it installs to `/usr/lib/postgresql18/`
# + `/usr/share/postgresql18/`. This image's server reports
# `pg_config --pkglibdir = /usr/local/lib/postgresql`, because the official
# images build Postgres from source into `/usr/local` rather than using Alpine's
# package. So the extension would land where the server never looks — and it is
# compiled against Alpine's own Postgres build, which is a second, quieter ABI
# risk. Verified both paths before choosing this one.
#
# WHAT THIS DOES
# --------------
# Compiles pgvector against the image's own `pg_config`, so the ABI matches by
# construction and the files land where the server already looks. Same base
# image, same libc, same data directory semantics — the ONLY change is that
# `CREATE EXTENSION vector` now works.
#
# `0008_pgvector_setup` was unregistered from `contracts/migrations/manifest.yaml`
# while this was unbuilt (`1b14-05`). It was RE-REGISTERED the same day this file
# was written, and the exclusion in `scripts/migration-manifest-gate.py` deleted
# with it — so the sentence that used to stand here (describing the migration as
# still unregistered) was stale from the hour it was committed.
#
# BUILDING THE IMAGE IS NOT RUNNING IT. Corrected 2026-08-11: the image existed
# and `docker-compose.yml` named it, but the running container was still
# `postgres:18-alpine` for three days, so every provision died at `0006` on
# `could not access file "vector"` and the compose file said otherwise. Nothing
# compares a declared image against a running one. `docker compose up -d postgres`
# is the whole fix; the named volume `loreweave_pg` survives it (161 databases,
# verified). See `WSD-3` in `docs/plans/2026-08-13-world-service-server-RUN-STATE.md`.

ARG PG_IMAGE=postgres:18-alpine
ARG PGVECTOR_VERSION=v0.8.1

FROM ${PG_IMAGE} AS build
ARG PGVECTOR_VERSION
RUN apk add --no-cache build-base clang19 llvm19-dev llvm19 git \
 && git clone --branch "${PGVECTOR_VERSION}" --depth 1 \
      https://github.com/pgvector/pgvector.git /tmp/pgvector \
 && cd /tmp/pgvector \
 # OPTFLAGS="" per pgvector's own README: -march=native breaks portability of the
 # built object across CPUs, which matters the moment this image runs anywhere
 # other than the machine that built it.
 && make OPTFLAGS="" \
 && make install

FROM ${PG_IMAGE}
COPY --from=build /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/
COPY --from=build /usr/local/share/postgresql/extension/vector* \
                  /usr/local/share/postgresql/extension/
