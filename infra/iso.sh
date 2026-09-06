#!/usr/bin/env bash
# iso.sh — drive the ISOLATED local stack.
#
# Two branches sharing one checkout were also sharing one Compose stack: the same image
# tags, the same containers, the same databases. `docker compose build glossary-service`
# on either branch overwrote the other's, and a live smoke could measure code the other
# branch had just built. This runs a second, complete stack beside it.
#
#     ./iso.sh up -d postgres redis neo4j glossary-service knowledge-service worker-infra
#     ./iso.sh build knowledge-service
#     ./iso.sh ps
#     ./iso.sh logs -f knowledge-service
#     ./iso.sh down                 # containers only; volumes survive
#     ./iso.sh down -v              # ⚠️ destroys the isolated DATA too
#
# Everything after the script name is passed to `docker compose` untouched, so anything
# Compose can do works here.
#
# WHY A WRAPPER AND NOT A DOCUMENTED COMMAND LINE
# -----------------------------------------------
# The full form is:
#
#     docker compose -p lw-iso -f docker-compose.yml -f docker-compose.isolated.yml …
#
# and dropping `-p lw-iso` from it does something much worse than failing: the isolated
# PORT MAP is applied to the SHARED project, so Compose recreates the base stack's
# containers on shifted ports, against the base stack's volumes. The other branch's stack
# appears to vanish and its data is being written by our services. A wrapper that cannot
# be half-typed is the fix.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${LW_ISO_PROJECT:-lw-iso}"

if [ "$#" -eq 0 ]; then
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
fi

# A stale override publishes a NEW service on its base port — a collision that reads as
# "the other stack is broken". Checked on every invocation because the cost is a
# millisecond and the failure costs an afternoon.
if ! python "${HERE}/gen-isolated-compose.py" --check >/dev/null 2>&1; then
    python "${HERE}/gen-isolated-compose.py" --check || true
    echo ""
    echo "iso.sh: refusing to run against a stale port map."
    exit 1
fi

exec docker compose \
    -p "${PROJECT}" \
    -f "${HERE}/docker-compose.yml" \
    -f "${HERE}/docker-compose.isolated.yml" \
    "$@"
