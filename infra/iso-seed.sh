#!/usr/bin/env bash
# iso-seed.sh — copy data from the SHARED stack into the ISOLATED one.
#
# The isolated stack has its own volumes, so it comes up empty: every service migrates its
# schema on boot and then sits there with no books, no glossary, no graph. That is correct
# and it is also useless for a live smoke, which is the whole reason the isolated stack
# exists. This clones the data across.
#
#     ./iso-seed.sh --pg                    # clone the default database set
#     ./iso-seed.sh --pg loreweave_book     # clone specific databases
#     ./iso-seed.sh --list                  # what would be cloned, and how big
#     ./iso-seed.sh --neo4j                 # ⚠️ BRIEFLY STOPS THE SHARED NEO4J — read below
#
# DIRECTION IS ONE-WAY AND ENFORCED: shared -> isolated. There is no flag to push the
# other way. A seed script that can run backwards is one typo away from overwriting the
# branch you were trying to protect.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${LW_ISO_PROJECT:-lw-iso}"

SRC_PG="${LW_SRC_PG_CONTAINER:-infra-postgres-1}"
DST_PG="${PROJECT}-postgres-1"
SRC_NEO="${LW_SRC_NEO_CONTAINER:-infra-neo4j-1}"

PGUSER_="loreweave"

# The databases a knowledge/glossary live smoke actually reads. Not every database in the
# stack: `loreweave_glossary` alone is ~1.9 GB and the point is to be able to re-seed often.
DEFAULT_DBS=(
    loreweave_auth          # the owning user
    loreweave_book          # books + chapters (the reading axis)
    loreweave_glossary      # the SSOT
    loreweave_knowledge     # projects + the mirror's Postgres side
    loreweave_composition   # plans + drafts (QC-5)
)

die() { echo "iso-seed: $*" >&2; exit 1; }

require_container() {
    docker inspect "$1" >/dev/null 2>&1 || die "container '$1' is not running.
  Source stack:   docker compose -f ${HERE}/docker-compose.yml up -d postgres
  Isolated stack: ${HERE}/iso.sh up -d postgres"
}

cmd_list() {
    require_container "$SRC_PG"
    echo "source: $SRC_PG   ->   target: $DST_PG"
    echo ""
    for db in "${DEFAULT_DBS[@]}"; do
        size=$(docker exec -i "$SRC_PG" psql -U "$PGUSER_" -d postgres -tAc \
            "SELECT pg_size_pretty(pg_database_size('${db}'))" 2>/dev/null || echo "ABSENT")
        printf '  %-24s %s\n' "$db" "$size"
    done
}

cmd_pg() {
    local dbs=("$@")
    [ "${#dbs[@]}" -eq 0 ] && dbs=("${DEFAULT_DBS[@]}")
    require_container "$SRC_PG"
    require_container "$DST_PG"

    # Refuse to run if source and target resolve to the same container. Cloning a database
    # onto itself would drop it first, and the DROP is the part that is not recoverable.
    [ "$SRC_PG" = "$DST_PG" ] && die "source and target are the same container ($SRC_PG)"

    for db in "${dbs[@]}"; do
        echo "==> ${db}"
        # DROP + CREATE rather than restoring over the top: a restore into a database the
        # isolated services already migrated collides on every existing object, and the
        # errors scroll past looking like noise while leaving a half-merged schema.
        docker exec -i "$DST_PG" psql -U "$PGUSER_" -d postgres -v ON_ERROR_STOP=1 \
            -c "DROP DATABASE IF EXISTS ${db} WITH (FORCE);" \
            -c "CREATE DATABASE ${db};" >/dev/null
        docker exec -i "$SRC_PG" pg_dump -U "$PGUSER_" -d "${db}" --no-owner --no-acl \
            | docker exec -i "$DST_PG" psql -U "$PGUSER_" -d "${db}" -q -v ON_ERROR_STOP=1 \
              >/dev/null
        local n
        n=$(docker exec -i "$DST_PG" psql -U "$PGUSER_" -d "${db}" -tAc \
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        echo "    ${n} table(s) in the isolated copy"
    done
    echo ""
    echo "Restart the isolated services so they reconnect to the reseeded databases:"
    echo "    ${HERE}/iso.sh restart glossary-service knowledge-service book-service"
}

cmd_neo4j() {
    require_container "$SRC_NEO"
    cat <<'WARN'
⚠️  Neo4j Community has no online backup. A consistent copy requires the SOURCE database
    to be stopped, and the source is the stack the OTHER BRANCH is using.

    This will:
      1. stop  infra-neo4j-1            (the shared graph goes down)
      2. copy  its data volume into the isolated project's volume
      3. start infra-neo4j-1            (back up, typically ~30s total)

    Tell whoever is on the other branch first. If you would rather not stop it, the
    entity layer can be rebuilt in the isolated stack WITHOUT touching the shared one,
    because the glossary is the SSOT and the repairer already exists:

        curl -X POST "http://localhost:28216/internal/projects/<project_id>/glossary-mirror-repair" \
             -H "X-Internal-Token: dev_internal_token"

    That reconstructs every :Entity from the cloned glossary. It does NOT reconstruct
    relations or events — those are extraction-derived and are not in the glossary, so a
    graph seeded that way is entity-complete and edge-empty. Know which one you need.
WARN
    read -r -p "Stop the shared Neo4j and copy? [y/N] " answer
    [ "${answer:-N}" = "y" ] || die "aborted — nothing was stopped"

    local src_vol dst_vol
    src_vol=$(docker inspect "$SRC_NEO" \
        --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}')
    dst_vol="${PROJECT}_loreweave_neo4j_data"
    [ -n "$src_vol" ] || die "could not resolve the source /data volume"

    echo "==> stopping ${SRC_NEO}"
    docker stop "$SRC_NEO" >/dev/null
    # `docker stop` on the isolated one too: copying into a volume a running Neo4j has
    # open produces a store that starts and then fails recovery, which surfaces hours
    # later as "some nodes are missing" rather than as a crash.
    docker stop "${PROJECT}-neo4j-1" >/dev/null 2>&1 || true
    echo "==> copying ${src_vol} -> ${dst_vol}"
    docker run --rm -v "${src_vol}:/from:ro" -v "${dst_vol}:/to" alpine:3.20 \
        sh -c 'rm -rf /to/* && cp -a /from/. /to/'
    echo "==> restarting ${SRC_NEO}"
    docker start "$SRC_NEO" >/dev/null
    echo "done. Start the isolated graph with: ${HERE}/iso.sh up -d neo4j"
}

case "${1:-}" in
    --list)  cmd_list ;;
    --pg)    shift; cmd_pg "$@" ;;
    --neo4j) cmd_neo4j ;;
    *)       sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
