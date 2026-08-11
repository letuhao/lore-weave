#!/usr/bin/env bash
# postgres-knowledge-image-smoke.sh — prove the published Postgres image actually works.
#
# Plan T22. The image bundles three version-pinned parts (PG + pgvector + pgvectorscale),
# and the failure mode that matters is SILENT: a release whose artifact layout changed
# installs nothing, the build still succeeds, and `CREATE EXTENSION` fails in production
# instead of in CI. That already happened once here — the first Dockerfile assumed loose
# `.so` files where the release ships `.deb` packages.
#
# So this does not check that files exist. It starts the image and USES it:
#   1. the extensions load,
#   2. a 3072-dim StreamingDiskANN index builds over real rows,
#   3. the planner CHOOSES that index,
#   4. the nearest neighbour of a known row is that row.
#
# (4) is the one that makes the rest mean something. An index that builds and is chosen but
# returns wrong neighbours is worse than one that fails to build, because nothing complains.
#
# Run after every image build, and on every version bump — the pins are the point.
#
#   bash scripts/postgres-knowledge-image-smoke.sh [image-tag]
#
# Exit 0 = green; 1 = an assertion failed; 2 = setup could not run.
#
# db-safety-gate: file-ok -- this starts its OWN throwaway container on a random-ish port
# and removes it on exit. It never connects to a service database.

set -uo pipefail

IMAGE="${1:-loreweave/postgres-knowledge:18}"
NAME="lw-pgk-smoke-$$"
PORT="${SMOKE_PG_PORT:-7996}"
PGPASS="smoke"

pass=0; fail=0
log()  { printf '[pgk-smoke] %s\n' "$*"; }
ok()   { pass=$((pass+1)); printf '[pgk-smoke] PASS  %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '[pgk-smoke] FAIL  %s\n' "$*"; }
die()  { printf '[pgk-smoke] FAIL(setup): %s\n' "$*"; exit 2; }

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || die "image $IMAGE not found — build it first: docker build -t $IMAGE infra/postgres-knowledge"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1; }
trap cleanup EXIT

docker run -d --name "$NAME" -e POSTGRES_PASSWORD="$PGPASS" -p "${PORT}:5432" "$IMAGE" >/dev/null 2>&1 \
  || die "could not start $IMAGE"
for _ in $(seq 1 60); do
  docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 || die "container never became ready"

q() { docker exec "$NAME" psql -U postgres -tAc "$1" 2>&1 | tr -d '\r'; }
run() { docker exec "$NAME" psql -U postgres -q -v ON_ERROR_STOP=1 -c "SET client_min_messages TO warning;" "$@" >/dev/null 2>&1; }

# ── 1. the extensions load ───────────────────────────────────────────
run -c "CREATE EXTENSION IF NOT EXISTS vector;" -c "CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;" \
  && ok "extensions create" || bad "CREATE EXTENSION failed — the image ships an unusable extension"

PGV="$(q "SELECT extversion FROM pg_extension WHERE extname='vector';")"
VSV="$(q "SELECT extversion FROM pg_extension WHERE extname='vectorscale';")"
PGMAJ="$(q "SHOW server_version_num;" | cut -c1-2)"
log "server=PG${PGMAJ}  pgvector=${PGV:-<none>}  pgvectorscale=${VSV:-<none>}"
[ -n "$PGV" ] && [ -n "$VSV" ] && ok "both extensions report a version" \
  || bad "an extension is missing from pg_extension after CREATE"

# ── 2. every supported dim indexes ───────────────────────────────────
# The closed set from SUPPORTED_PASSAGE_DIMS. 2560 and 3072 are the ones pgvector's own
# HNSW refuses, and therefore the ones worth re-checking on every version bump.
dims_ok=1
for d in 384 1024 1536 2560 3072; do
  run -c "DROP TABLE IF EXISTS s_$d;" \
      -c "CREATE TABLE s_$d (id int, emb vector($d));" \
      -c "CREATE INDEX ON s_$d USING diskann (emb vector_cosine_ops);" || { dims_ok=0; bad "dim $d does not index"; }
done
[ "$dims_ok" = "1" ] && ok "all SUPPORTED_PASSAGE_DIMS index with diskann (incl. 2560/3072)"

# ── 3+4. a 3072 index over real rows is USED and CORRECT ─────────────
run -c "DROP TABLE IF EXISTS smoke3072;" \
    -c "CREATE TABLE smoke3072 (id int primary key, emb vector(3072));" \
    -c "INSERT INTO smoke3072 SELECT g, (SELECT array_agg(CASE WHEN i = (g % 3072) THEN 1.0 ELSE random()*0.01 END)::vector(3072) FROM generate_series(0,3071) i) FROM generate_series(1,500) g;" \
    -c "CREATE INDEX smoke3072_dann ON smoke3072 USING diskann (emb vector_cosine_ops);" \
    -c "ANALYZE smoke3072;" \
  || bad "could not build a 3072-dim index over real rows"

PLAN="$(q "EXPLAIN (COSTS OFF) SELECT id FROM smoke3072 ORDER BY emb <=> (SELECT emb FROM smoke3072 WHERE id = 42) LIMIT 5;")"
case "$PLAN" in
  *smoke3072_dann*) ok "the planner CHOOSES the diskann index" ;;
  *) bad "the planner ignored the index — it builds but does not serve: $(echo "$PLAN" | tr '\n' ' ' | cut -c1-90)" ;;
esac

NEAREST="$(q "SELECT id FROM smoke3072 ORDER BY emb <=> (SELECT emb FROM smoke3072 WHERE id = 42) LIMIT 1;")"
[ "$NEAREST" = "42" ] \
  && ok "nearest neighbour of row 42 is row 42 (the index returns CORRECT results)" \
  || bad "nearest neighbour of row 42 came back as '$NEAREST' — the index is wrong, which is worse than absent"

# ── 5. Apache AGE — the graph half of the matrix (T42b) ──────────────
# Same standard as the vector half: not "the file is there", but the extension LOADS and
# the one construct the engine decision turns on actually runs.
#
# The bookworm attempt copied AGE's artifacts in cleanly and failed only here, with
# `GLIBC_2.38 not found` — a file-existence check passes that, this does not.
run -c "CREATE EXTENSION IF NOT EXISTS age;" \
  && ok "AGE extension creates" || bad "CREATE EXTENSION age failed — the image ships an unusable AGE"

AGEV="$(q "SELECT extversion FROM pg_extension WHERE extname='age';")"
log "apache age=${AGEV:-<none>}"
[ -n "$AGEV" ] && ok "AGE reports a version" || bad "AGE missing from pg_extension after CREATE"

# A graph is created and written through AGE's own dialect. NOTE: `LOAD 'age'` and the
# search_path are per-SESSION, so every statement below carries them — a graph created in
# one psql -c and queried in another WILL fail without them, which is the first thing that
# bites anyone wiring an adapter (T42c owns that bootstrap).
AGE_SQL="LOAD 'age'; SET search_path = ag_catalog, \"\$user\", public;"
# ⚠️ single-character graph names are rejected by AGE ("graph name is invalid") — measured.
run -c "$AGE_SQL SELECT create_graph('smokegraph');" \
  && ok "create_graph succeeds" || bad "create_graph failed — AGE loads but cannot hold a graph"

# THE construct the engine choice turns on. AGE has no `ON CREATE SET` / `ON MATCH SET`;
# the equivalent is `SET x = coalesce(x, v)`, and this asserts the SEMANTICS rather than the
# syntax: run the same MERGE twice, the create-only field must SURVIVE the second run.
run -c "$AGE_SQL SELECT * FROM cypher('smokegraph', \$\$ MERGE (e:Entity {id:'a'}) SET e.born = coalesce(e.born, 1), e.seen = 2 RETURN e \$\$) as (v agtype);"
run -c "$AGE_SQL SELECT * FROM cypher('smokegraph', \$\$ MERGE (e:Entity {id:'a'}) SET e.born = coalesce(e.born, 99), e.seen = 3 RETURN e \$\$) as (v agtype);"
# `tail -1`: psql echoes a status line per statement, and this query needs THREE (LOAD, SET,
# then the cypher call) because AGE's search_path is per-session. Without it the comparison
# reads "LOAD\nSET\n1" and reports a wrong-value failure for a correct result — which is what
# it did on the first run here.
BORN="$(q "$AGE_SQL SELECT * FROM cypher('smokegraph', \$\$ MATCH (e:Entity {id:'a'}) RETURN e.born \$\$) as (v agtype);" | tail -1)"
SEEN="$(q "$AGE_SQL SELECT * FROM cypher('smokegraph', \$\$ MATCH (e:Entity {id:'a'}) RETURN e.seen \$\$) as (v agtype);" | tail -1)"
if [ "$BORN" = "1" ] && [ "$SEEN" = "3" ]; then
  ok "AGE reproduces ON CREATE/ON MATCH semantics via coalesce (born stayed 1, seen advanced to 3)"
else
  bad "AGE upsert semantics wrong: born='$BORN' (want 1, i.e. create-only survived) seen='$SEEN' (want 3)"
fi

log "-----------------------------------------------------------------"
log "image=$IMAGE  passed=$pass failed=$fail"
[ "$fail" -eq 0 ] || exit 1
