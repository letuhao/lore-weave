#!/usr/bin/env bash
# `A4` — a reality that ALREADY EXISTS on this shard gets a world, an actor
# sited in it, and a browser showing where that actor is.
#
# THE DIFFERENCE FROM `kernel-state-demo.sh`, WHICH IS THE WHOLE POINT
# --------------------------------------------------------------------
# That script proves the chain on TWO THROWAWAY DATABASES it creates and drops,
# and it seeds the world with direct `INSERT`s under a comment saying so. Both
# choices were right for it: it had no authorisation to touch a real reality,
# and the seeder was reachable only through provisioning.
#
# This script is the substitution the board kept open. It:
#
#   * NEVER creates or drops a database. It refuses if the reality is not
#     already in the real registry.
#   * writes ONLY through the service's own endpoints — `/world/seed`,
#     `/actors`, `/actor-control/grant`. Not one `INSERT` in this file.
#     A demo that reaches past the API proves the database, not the system.
#   * REFUSES a reality that is behind the manifest, naming what is missing,
#     rather than failing four steps later inside the seeder.
#
# WHY THE SEED ENDPOINT HAD TO EXIST FIRST
# ----------------------------------------
# `seed_world`'s only production caller was the provisioner's
# `seed_world_structure` step, which runs at provision time and only then. Every
# reality here was provisioned before that step existed, so the producer was
# UNREACHABLE for all of them — which reads exactly like reachable until someone
# tries. `POST /internal/v1/world/seed` is that missing caller.
#
#   bash scripts/smoke/world-in-a-running-reality.sh --reality <uuid>
#   bash scripts/smoke/world-in-a-running-reality.sh --reality <uuid> --driver <user_id>
#   bash scripts/smoke/world-in-a-running-reality.sh --down
#
# `--seed-only` stops after the production writes and the `where-is` check, which
# is the half that needs no browser.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
REPO="$(pwd)"

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PGHOSTPORT="${PGHOSTPORT:-localhost:5555}"
PGUSER="${PGUSER:-loreweave}"
PGPASSWORD="${PGPASSWORD:-loreweave_dev}"
META_DB="${META_DB:-loreweave_meta}"
TOKEN="${LOREWEAVE_INTERNAL_TOKEN:-running_reality_token}"
WORLD_PORT="${WORLD_PORT:-7150}"
GAME_PORT="${GAME_PORT:-2577}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6399/0}"
# The meta-bridge is REACHED here, not stubbed, because `/actor-control/grant`
# writes `actor_control_binding` THROUGH it. `kernel-state-demo` never needed a
# real token because it INSERTed that row straight into its own throwaway meta --
# exactly the shortcut this script exists not to take. A placeholder answers
# `grant: 401 unauthorized`, five steps in.
BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8090}"
BRIDGE_TOKEN="${METAWORKER_BRIDGE_TOKEN:-loreweave_local_dev_bridge_token}"

RUN=/tmp/running-reality
mkdir -p "$RUN"
# `curl` and `world-service.exe` are WINDOWS binaries: handed `/tmp/x` they
# resolve it against the current drive (`D:\tmp\x`), while bash's `/tmp` is
# somewhere under AppData. Every write went to one path and every read to the
# other, so the script reported `No such file or directory` for a response it
# had just received. Bash-side redirections use `$RUN`; anything passed TO an
# exe uses `$RUNW` -- `cygpath -m`, the forward-slash Windows form, which is the
# one spelling curl, python and bash all read. `-w` gives backslashes, and a
# backslash inside a python string literal is an escape sequence.
RUNW="$(cygpath -m "$RUN" 2>/dev/null || echo "$RUN")"
stop_all() {
  for f in "$RUN"/*.pid; do
    [ -f "$f" ] || continue
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
}
# Handled BEFORE any argument that could start something, for the reason
# `kernel-state-demo` records: a teardown flag that has to get past the setup is
# not a teardown flag.
[ "${1:-}" = "--down" ] && { stop_all; echo "stopped."; exit 0; }

REALITY=""
DRIVER=""
SEED_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --reality)   REALITY="${2:-}"; shift 2 ;;
    --driver)    DRIVER="${2:-}"; shift 2 ;;
    --seed-only) SEED_ONLY=1; shift ;;
    *) echo "unknown flag $1" >&2; exit 2 ;;
  esac
done
[ -n "$REALITY" ] || { echo "ERROR: --reality <uuid> is required. This script acts on ONE existing reality and creates none." >&2; exit 2; }
DRIVER="${DRIVER:-33333333-2222-4333-8444-000000000003}"

q() { docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d "$1" -tAc "$2" 2>/dev/null | tr -d '\r'; }

# ── PRECONDITIONS. Both are REFUSALS, not warnings ──────────────────────────
DBNAME="$(q "$META_DB" "SELECT db_name FROM reality_registry WHERE reality_id='$REALITY'")"
[ -n "$DBNAME" ] || { echo "ERROR: reality $REALITY is not in $META_DB.reality_registry. This script does not create realities." >&2; exit 2; }

# A reality behind the manifest has no `place` or `entity_binding` table, and the
# seeder would fail inside a transaction four steps from here. Checked at the
# ledger, which `A2` made trustworthy by giving it a writer.
HEAD="$(q "$DBNAME" "SELECT max(id) FROM schema_migrations")"
WANT="$(python -c "
import yaml
m = yaml.safe_load(open('contracts/migrations/manifest.yaml', encoding='utf-8'))
migs = m['migrations'] if isinstance(m, dict) and 'migrations' in m else m
print(sorted(migs, key=lambda r: r['version'])[-1]['id'])
" | tr -d '\r')"
if [ "$HEAD" != "$WANT" ]; then
  echo "ERROR: $DBNAME is at '$HEAD', the manifest head is '$WANT'." >&2
  echo "       Bring it forward first:  bash scripts/bring-reality-forward.sh --reality $REALITY ..." >&2
  exit 2
fi
echo "== reality $REALITY -> $DBNAME (at $HEAD)"

# ── world-service, against the REAL meta ────────────────────────────────────
stop_all
BASE="postgres://$PGUSER:$PGPASSWORD@$PGHOSTPORT"
echo "== building world-service =="
cargo build -q -p world-service
echo "== world-service :$WORLD_PORT =="
WORLD_HTTP_BIND="127.0.0.1:$WORLD_PORT" \
LOREWEAVE_INTERNAL_TOKEN="$TOKEN" \
PROVISION_META_DSN="$BASE/$META_DB?sslmode=disable" \
PROVISION_SHARD_ADMIN_DSN="$BASE/postgres?sslmode=disable" \
PROVISION_BRIDGE_URL="$BRIDGE_URL" \
PROVISION_BRIDGE_TOKEN="$BRIDGE_TOKEN" \
PROVISION_SHARD_HOSTPORT="$PGHOSTPORT" \
PROVISION_PG_USER="$PGUSER" \
PROVISION_PG_PASSWORD="$PGPASSWORD" \
  ./target/debug/world-service.exe >"$RUN/world.log" 2>&1 &
echo $! > "$RUN/world.pid"

for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$WORLD_PORT/livez" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://127.0.0.1:$WORLD_PORT/livez" >/dev/null || { echo "world-service did not come up:"; tail -20 "$RUN/world.log"; exit 1; }

api() {
  local path="$1" body="$2"
  curl -s -o "$RUNW/resp.json" -w '%{http_code}' -X POST "http://127.0.0.1:$WORLD_PORT$path" \
    -H 'content-type: application/json' -H "X-Internal-Token: $TOKEN" -d "$body"
}
# Every call's status is CHECKED. `curl` without --fail exits 0 on a 400, and a
# demo that reads a ProblemDetails body as success is the shape this whole board
# keeps finding.
#
# 200 AND 201, because `/actors` CREATES and says so. Insisting on 200 turned a
# successful creation into `!! actors -> HTTP 201` — a check that fails on the
# thing it is checking for is as broken as one that cannot fail, and this is the
# second of that shape in this session.
expect_ok() {
  local what="$1" code="$2"
  case "$code" in
    200|201) ;;
    *) echo "!! $what -> HTTP $code"; cat "$RUN/resp.json"; echo; exit 1 ;;
  esac
}

# ── 1. THE WORLD, through the endpoint ──────────────────────────────────────
echo "== seeding the authored world (contracts/world/demo_v1.json) =="
WORLD_JSON="$(python -c "
import json
print(json.dumps({'reality_id': '$REALITY', 'world': json.load(open('contracts/world/demo_v1.json', encoding='utf-8'))}))
")"
expect_ok "world/seed" "$(api /internal/v1/world/seed "$WORLD_JSON")"
echo "   $(cat "$RUN/resp.json")"

# WHERE the actor goes: the node the declaration itself marks as a domain with a
# place. Read FROM the file, never hardcoded — a second copy of the id here would
# silently site the actor in the wrong room the first time the world was edited.
SITE_NODE="$(python -c "
import json
d = json.load(open('contracts/world/demo_v1.json', encoding='utf-8'))
print(next(n['id'] for n in d if n.get('place')))
" | tr -d '\r')"
SITE_NAME="$(python -c "
import json
d = json.load(open('contracts/world/demo_v1.json', encoding='utf-8'))
print(next(n['place']['name_vi'] for n in d if n.get('place')))
" | tr -d '\r')"
echo "   siting node: $SITE_NODE ($SITE_NAME)"

# ── 2. THE ACTOR — ASK BEFORE CREATING ──────────────────────────────────────
#
# `world/seed` is idempotent and `/actors` is NOT: `adopt_actor` INSERTs
# unconditionally and `site_in_cell` treats re-siting as an error rather than a
# silent move — both correct, and both meaning a naive re-run ACCUMULATES
# actors. Three partial runs of this script left three of them sited in the same
# tavern before this block existed. A demo that grows the world every time it is
# run is not re-runnable in `G2`'s sense; it is merely repeatable.
#
# So the driver's OWN subject is the idempotence key, read through the API like
# everything else here. `self: null` means this user drives nobody yet, which is
# a first run; a body means the actor already exists and is reused.
echo "== who does $DRIVER already drive? =="
expect_ok "actor-control/subject" "$(api /internal/v1/actor-control/subject \
  "{\"reality_id\":\"$REALITY\",\"user_ref_id\":\"$DRIVER\"}")"
cp "$RUN/resp.json" "$RUN/subject.json"
ACTOR="$(python -c "import json;s=json.load(open('$RUNW/subject.json'))['self'];print(s['actor_id'] if s else '')" | tr -d '\r')"
ENTITY="$(python -c "import json;s=json.load(open('$RUNW/subject.json'))['self'];print(s['entity_id'] if s else '')" | tr -d '\r')"

if [ -n "$ACTOR" ]; then
  echo "   already drives actor $ACTOR (entity $ENTITY) — reusing, creating nothing"
else
  echo "== creating an actor sited in node $SITE_NODE =="
  expect_ok "actors" "$(api /internal/v1/actors \
    "{\"reality_id\":\"$REALITY\",\"siting\":{\"node\":$SITE_NODE,\"entity_type\":\"pc\",\"lifecycle_state\":0}}")"
  cp "$RUN/resp.json" "$RUN/actor.json"
  echo "   $(cat "$RUN/actor.json")"
  ACTOR="$(python -c "import json;print(json.load(open('$RUNW/actor.json'))['actor_id'])" | tr -d '\r')"
  ENTITY="$(python -c "import json;print(json.load(open('$RUNW/actor.json'))['entity_id'])" | tr -d '\r')"

  # ── 3. WHO DRIVES IT, through the endpoint ────────────────────────────────
  # Inside the branch: granting to a driver who already holds a binding is a
  # conflict, not a no-op, and the read above is what makes that unreachable.
  echo "== granting control to $DRIVER =="
  expect_ok "actor-control/grant" "$(api /internal/v1/actor-control/grant \
    "{\"user_ref_id\":\"$DRIVER\",\"reality_id\":\"$REALITY\",\"actor_id\":\"$ACTOR\",\"reason\":\"A4 running-reality demo\"}")"
fi

# ── 4. THE ASSERTION world-service itself can make ──────────────────────────
echo "== where is entity $ENTITY? =="
expect_ok "space/where-is" "$(api /internal/v1/space/where-is \
  "{\"reality_id\":\"$REALITY\",\"entity_id\":$ENTITY}")"
cat "$RUN/resp.json"; echo
python - "$RUNW/resp.json" "$SITE_NODE" "$SITE_NAME" <<'PY'
import json, sys
w = json.load(open(sys.argv[1]))["whereabouts"]
node, name = int(sys.argv[2]), sys.argv[3]
# Three checks and not one, because `kind` alone would pass for the WRONG room.
assert w["kind"] == "in_cell", f'expected in_cell, got {w["kind"]}'
assert w["node"] == node, f'expected node {node}, got {w["node"]}'
assert w["place_name"] == name, f'expected place {name!r}, got {w["place_name"]!r}'
print(f'   OK: entity is in_cell at node {node} ({name}), level {w["level_name"]}')
PY

if [ "$SEED_ONLY" = "1" ]; then
  echo
  echo "== --seed-only: the production writes are done and verified. Stopping. =="
  stop_all
  exit 0
fi

# ── 5. THE BROWSER HALF ─────────────────────────────────────────────────────
# The room joins the world ROOT — the node with no parent, read from the same
# file for the same reason `SITE_NODE` is.
ROOM="$(python -c "
import json
d = json.load(open('contracts/world/demo_v1.json', encoding='utf-8'))
print(next(n['id'] for n in d if n.get('parent') is None))
" | tr -d '\r')"
echo "== game-server :$GAME_PORT (reality $REALITY, channel $ROOM) =="
[ -f services/game-server/dist/index.js ] || (cd services/game-server && npm run -s build)
PORT="$GAME_PORT" \
LOREWEAVE_INTERNAL_TOKEN="$TOKEN" \
LOREWEAVE_CORS_ORIGINS="http://localhost:5199" \
LW_WS_DEV_ALLOW_STATIC=1 \
LW_WS_DEV_USER_REF_ID="$DRIVER" \
LW_WORLD_SERVICE_URL="http://127.0.0.1:$WORLD_PORT" \
LW_CHANNEL_REALITY_ID="$REALITY" \
LW_CHANNEL_ID="$ROOM" \
LW_CHANNEL_REDIS_URL="$REDIS_URL" \
  node services/game-server/dist/index.js >"$RUN/gs.log" 2>&1 &
echo $! > "$RUN/gs.pid"
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$GAME_PORT/livez" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://127.0.0.1:$GAME_PORT/livez" >/dev/null || { echo "game-server did not come up:"; tail -20 "$RUN/gs.log"; exit 1; }

cat <<EOF

== the stack is up, against a REAL reality ==
   reality   $REALITY  ($DBNAME)
   actor     $ACTOR  (entity $ENTITY)
   sited in  node $SITE_NODE — $SITE_NAME
   room      channel $ROOM
   driver    $DRIVER

== the app ==
  cd frontend-game && VITE_GAME_SERVER_URL=ws://localhost:$GAME_PORT \\
    VITE_INTERNAL_TOKEN=$TOKEN npx vite --port 5199 --strictPort

== the suite (--project=chromium; without it playwright also launches firefox
   and webkit, and a MISSING BROWSER BINARY reads exactly like a failed assert) ==
  LOREWEAVE_E2E_FULL=1 RUNNING_REALITY_PLACE='$SITE_NAME' \\
    KERNEL_STATE_BASE=http://localhost:5199 \\
    KERNEL_STATE_ACCESS_TOKEN=<access_token> KERNEL_STATE_USER_ID=$DRIVER \\
    npx playwright test running-reality --project=chromium

  bash scripts/smoke/world-in-a-running-reality.sh --down   # when finished
EOF
