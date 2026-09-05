#!/usr/bin/env bash
# `G2`/`G3` — stand up the whole chain that puts KERNEL STATE on a screen, on
# databases nothing real depends on.
#
# WHY THIS IS A SCRIPT AND NOT A PARAGRAPH IN A PLAN
# --------------------------------------------------
# `F4` proved a browser can render the actor a binding names. It did so across
# six hand-typed shell invocations, which means nobody — including its author a
# week later — can re-run it. That is the same defect `EO-2` opened against
# `E1`, and the same one `world-actor-subject` closed by becoming a registered
# suite. A demo somebody else cannot run is a demo that will be wrong within a
# week and nobody will know.
#
# WHAT IT WRITES, AND WHERE
# -------------------------
# Two throwaway databases whose names carry the `smoke` marker every fixture's
# `guarded()` demands before it will touch a server. Nothing here writes to
# `loreweave_meta` or to any `lw_reality_*` database. That is deliberate and it
# is why this board could proceed where `F4` stopped: `F4` needed a reality with
# both committed events and a live binding, no such reality existed, and making
# one meant writing to the dev meta database.
#
# WHAT "THE REAL PATH" MEANS HERE, AND WHAT IT DOES NOT
# -----------------------------------------------------
# The event is committed by the actual `spine` binary consuming an actual
# proposal off the actual stream `ChannelRoom` writes to — not by an INSERT.
# **Producer identity is NOT enforced in this run**: with no `LW_PRODUCER_KEY_*`
# set, `spine` prints its own warning saying so, and this script does not set
# one because signing a proposal from bash would mean reimplementing the MAC.
# Stated rather than glossed — the commit logic is real, the producer check is
# off, and a demo that quietly skipped a security control while calling itself
# end-to-end would be worse than no demo.
#
#   bash scripts/smoke/kernel-state-demo.sh            # stand it up
#   bash scripts/smoke/kernel-state-demo.sh --seed-only # DBs + event, no servers
#
# Override endpoints with PGHOSTPORT / REDIS_URL / PGUSER / PGPASSWORD.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="$(pwd)"

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PGHOSTPORT="${PGHOSTPORT:-localhost:5555}"
PGUSER="${PGUSER:-loreweave}"
PGPASSWORD="${PGPASSWORD:-loreweave_dev}"
REDIS_CONTAINER="${REDIS_CONTAINER:-infra-redis-1}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6399/0}"

META_DB=loreweave_kernel_state_smoke_meta
CHAN_DB=loreweave_kernel_state_smoke_channel

# Fixed ids so a re-run is the SAME demo rather than a new one each time — a
# demo whose ids move cannot be talked about, and the browser assertion needs to
# know what to expect.
REALITY=11111111-2222-4333-8444-000000000001
ACTOR=22222222-2222-4333-8444-000000000002
# Overridable so the demo can be driven by a REAL logged-in user: point it at
# the `user_id` auth-service issued a token for and the browser's session and
# the game's driver become the same person, which is what production looks like.
# Defaults to a fixed synthetic id so the script needs no auth-service.
DRIVER="${DEMO_DRIVER:-33333333-2222-4333-8444-000000000003}"
CHANNEL=1
ENTITY=1

RUN=/tmp/kernel-state-demo
mkdir -p "$RUN"
stop_all() {
  for f in "$RUN"/*.pid; do
    [ -f "$f" ] || continue
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
}
# HANDLED FIRST, and it was not the first time round. `--down` lived at the
# BOTTOM of this script, beside the code it stops — so asking to stop the
# stack ran the whole provision-and-seed against the databases the running
# services were holding open, failed the DROP, and died on `set -e`. A
# teardown flag that has to get past the setup is not a teardown flag.
[ "${1:-}" = "--down" ] && { stop_all; echo "stopped."; exit 0; }
stop_all   # never leave two publishers on one stream

psql_db() { docker exec -i "$PG_CONTAINER" psql -U "$PGUSER" -d "$1" -v ON_ERROR_STOP=1 -q; }
q() { docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d "$1" -tAc "$2"; }

echo "== provisioning $META_DB + $CHAN_DB on $PG_CONTAINER =="
# Evict first. A previous run's world-service or publisher still holding a
# connection makes DROP DATABASE fail with "there are N other sessions using the
# database"; CREATE then fails with "already exists"; and without ON_ERROR_STOP
# on this call the run would continue against the OLD data, which is the worst
# of the three outcomes. Scoped to these two names — never a blanket terminate.
for db in "$META_DB" "$CHAN_DB"; do
  docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d postgres -q -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$db' AND pid <> pg_backend_pid()" >/dev/null 2>&1 || true
done
docker exec "$PG_CONTAINER" psql -U "$PGUSER" -d postgres -q \
  -c "DROP DATABASE IF EXISTS $META_DB" -c "CREATE DATABASE $META_DB" \
  -c "DROP DATABASE IF EXISTS $CHAN_DB" -c "CREATE DATABASE $CHAN_DB" >/dev/null

# Migrations. A failure is REPORTED, never swallowed: two of them need pgvector
# and are expected to fail on a stock postgres image, and this path touches
# nothing they create — but a NEW failure here would otherwise look exactly like
# a clean setup with a missing table underneath it.
skipped=()
apply() {
  for f in "$2"/*.up.sql; do
    if ! psql_db "$1" < "$f" >/tmp/kernel-demo-migrate.log 2>&1; then
      skipped+=("$(basename "$f"): $(head -1 /tmp/kernel-demo-migrate.log)")
    fi
  done
}
echo "== applying migrations/meta =="
apply "$META_DB" migrations/meta
echo "== applying contracts/migrations/per_reality =="
apply "$CHAN_DB" contracts/migrations/per_reality
if [ ${#skipped[@]} -gt 0 ]; then
  echo "!! ${#skipped[@]} migration(s) did not apply:"
  printf '   %s\n' "${skipped[@]}"
fi

# The tables this chain needs, CHECKED. A half-applied migration set would
# otherwise surface three steps later as a confusing failure inside the spine or
# the publisher, instead of here where the cause is one line.
missing=0
for t in reality_registry actor_control_binding session_registry; do
  [ "$(q "$META_DB" "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='$t'")" = "1" ] \
    || { echo "MISSING $META_DB.$t"; missing=1; }
done
for t in events channels actors channel_writer_state; do
  [ "$(q "$CHAN_DB" "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='$t'")" = "1" ] \
    || { echo "MISSING $CHAN_DB.$t"; missing=1; }
done
[ "$missing" -eq 0 ] || { echo "setup incomplete — refusing to report a demo result"; exit 2; }

# ── SEED ────────────────────────────────────────────────────────────────────
#
# `db_host` is the LOGICAL shard name and a CHECK pins it to
# `pg-shard-N.internal`; nothing dials it. The publisher reaches the real server
# through PUBLISHER_SHARD_HOST_OVERRIDE and world-service through
# PROVISION_SHARD_HOSTPORT. Putting a real hostname here is refused by the
# constraint, which is how `E5` learned this.
echo "== seeding reality $REALITY, actor $ACTOR (entity $ENTITY), driver $DRIVER =="
psql_db "$META_DB" <<SQL
INSERT INTO reality_registry
  (reality_id, db_host, db_name, status, locale,
   session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
VALUES ('$REALITY', 'pg-shard-0.internal', '$CHAN_DB', 'active', 'en-US', 8, 32, 40, 0);
INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id)
VALUES ('$DRIVER', '$REALITY', '$ACTOR');
SQL

psql_db "$CHAN_DB" <<SQL
INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle)
VALUES ('$REALITY', $CHANNEL, NULL, 'reality', 0, 'active');
INSERT INTO actors (reality_id, actor_id, entity_id)
VALUES ('$REALITY', '$ACTOR', $ENTITY);

-- A4 -- A WORLD, AND THE ACTOR IN IT.
--
-- NO BACKTICKS BELOW, and that is not style. This heredoc is UNQUOTED (<<SQL)
-- so the shell expands $REALITY and $ENTITY -- which is why it can seed at all --
-- and it expands backticks too. The first version of this block wrote ordinary
-- prose quoting like A4 and level_name, and the shell tried to RUN them:
--   kernel-state-demo.sh: line 151: A4: command not found
--
-- Channel 1 above is the reality's own root channel (level_name 'reality') and
-- is NOT a map node: nothing ever gave it a kind. The space tree is separate,
-- and an actor is sited in a NODE, not in a channel.
--
-- These rows are the SHAPE of contracts/world/demo_v1.json, applied here rather
-- than through seed_world, because this script seeds a channel database
-- directly while the seeder is reached through provisioning. The authored file
-- itself is proven by world_declarations.rs and world_seed_live; what THIS
-- proves is that the browser can show where an actor is.
--
-- ONE ROOT PER REALITY, and this is where that stopped being abstract.
--
-- The first version added its own root node (parent NULL) for the world. 0019's
-- channels_root_single is a PARTIAL UNIQUE INDEX -- at most one root per reality
-- -- so the insert was refused, ON CONFLICT DO NOTHING swallowed the refusal,
-- and the child then failed on a foreign key that named a row which had never
-- been written:
--   Key (reality_id, parent, parent_depth)=(..., 10, 0) is not present
--
-- Channel 1 IS the root. So the map hangs off it: channel 1 becomes the world
-- node, and the tavern is a Domain beneath it. In a real provision seed_world
-- writes its own root because the reality is empty; here one already exists, and
-- the tree has to acknowledge that rather than fight it.
INSERT INTO map_layout (reality_id, channel_id, kind, pos_x, pos_y)
VALUES ('$REALITY', $CHANNEL, 'world', 500, 500) ON CONFLICT DO NOTHING;
INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle)
VALUES ('$REALITY', 11, $CHANNEL, 'yen-vu-lau', 1, 'active') ON CONFLICT DO NOTHING;
INSERT INTO map_layout (reality_id, channel_id, kind, pos_x, pos_y)
VALUES ('$REALITY', 11, 'domain', 480, 520) ON CONFLICT DO NOTHING;
INSERT INTO place (reality_id, place_id, place_type, canon_ref, name_vi, name_en)
VALUES ('$REALITY', 11, 'tavern', '{"kind":"BookChapter","path":"ch1"}'::jsonb,
        'Yen Vu Lau', 'Misty Rain Pavilion')
ON CONFLICT DO NOTHING;

-- THE SPAWN. Entity 1 is the actor the browser drives, and it is now somewhere.
INSERT INTO entity_binding
  (reality_id, entity_id, entity_type, location_kind, cell_id, lifecycle_state)
VALUES ('$REALITY', $ENTITY, 'pc', 'in_cell', 11, 0)
ON CONFLICT DO NOTHING;

SQL

echo "   reality_registry     : $(q "$META_DB" "SELECT count(*) FROM reality_registry WHERE reality_id='$REALITY'")"
echo "   actor_control_binding: $(q "$META_DB" "SELECT count(*) FROM actor_control_binding WHERE reality_id='$REALITY' AND revoked_at IS NULL")"
echo "   actors               : $(q "$CHAN_DB" "SELECT count(*) FROM actors WHERE reality_id='$REALITY'")"
echo "   map nodes            : $(q "$CHAN_DB" "SELECT count(*) FROM map_layout WHERE reality_id='$REALITY'")"
echo "   sited entities       : $(q "$CHAN_DB" "SELECT count(*) FROM entity_binding WHERE reality_id='$REALITY'")"

# ── G3: a committed event, produced by the real path ────────────────────────
#
# A proposal onto the stream `ChannelRoom.proposalStreamFor()` writes to, then
# the real `spine --drain-once` consuming it. `candidates` is an OFFER the far
# side re-validates against island state (THR-A4), and there is deliberately no
# `actor` field: `SEALED-SUBJECT` removed it so no producer can assert a
# subject, and the spine resolves it from the binding seeded above.
#
# ⚠ THE ACTION IS `strike`, AND THAT IS NOT ARBITRARY.
#
# `turnOutcome.foldEvent` mutates the view for `struck`, `downed`, `fled` and
# `moved`; everything else — INCLUDING `defended` — falls to `default: break`.
# So a `defend` proposal commits a real event, advances the turn, and leaves the
# roster empty: the browser would show `turn 1` and nothing else, which is
# exactly the kind of partial success worth mistaking for the real thing. This
# script's first version used `defend`. `struck` sets `hp` on its target, which
# is the state a human can actually see.
#
# ⚠ THE SPINE IS DRAINED TWICE, AND THE ORDER IS THE WHOLE POINT.
#
# It reads through a consumer GROUP that it creates on startup at `$` — "from
# now on". An entry XADDed before that group exists is behind its start id and
# is never delivered: the first attempt at this script added the proposal first
# and the spine reported `consumed: 0` while `XLEN` said 1 and the group said
# `lag 0`. Nothing was broken; the entry was simply in the past. So the first
# drain EXISTS TO CREATE THE GROUP, the proposal goes on after it, and the
# second drain is the one that commits.
PROPOSAL_STREAM="reality:$REALITY:cell:$CHANNEL:proposals"
BASE="postgres://$PGUSER:$PGPASSWORD@$PGHOSTPORT"

# `--create-reality` goes on the FIRST pass ONLY. Creation happens ONCE
# (`RLS-A3`): a live reality's rules change by epoch switch, which is an ordered
# event, so the second call refuses the flag outright — "already bound to
# <digest> (epoch 1)". Measured, not guessed; the first version passed it twice
# and the second drain died before consuming anything.
drain() { # drain <label> [extra-flags...]
  local label="$1"; shift
  echo "== spine --drain-once ($label) =="
  cargo run -q -p commit-service --bin spine --     --redis-url "$REDIS_URL"     --pg-url "$BASE/$CHAN_DB"     --meta-url "$BASE/$META_DB"     --meta-allowlist "$REPO/contracts/meta/events_allowlist.yaml"     --reality "$REALITY" --channel "$CHANNEL" --drain-once "$@"     2>&1 | grep -E "consumed|admitted|rejected|committed|turn |WARNING|error|Error" | sed 's/^/   /'
}

# The stream lives in Redis and survives DROP DATABASE, so a re-run would
# otherwise inherit the previous run's proposals and its consumer group — and
# the group is what decides which entries are visible at all.
# BOTH streams. Redis outlives DROP DATABASE, so a re-run would otherwise
# inherit the previous run's proposals AND its committed events, and the turn
# number would climb every time the script is run — a demo that is never twice
# the same thing.
#
# Safe to clear the EVENT stream only because the meta database was just
# recreated: `publisher_heartbeats` went with it, so the publisher has no cursor
# and republishes from the beginning. Deleting that stream while a cursor
# survives loses the events for good — measured the hard way.
echo "== clearing both streams (Redis outlives the databases) =="
docker exec "$REDIS_CONTAINER" redis-cli DEL "$PROPOSAL_STREAM" "lw.events.$REALITY" >/dev/null

drain "creating the consumer group" --create-reality

PROPOSAL_ID="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python -c 'import uuid;print(uuid.uuid4())')"
PROPOSAL='{"producer_service":"game-server","proposal_id":"'"$PROPOSAL_ID"'","target_channel":'"$CHANNEL"',"user_ref_id":"'"$DRIVER"'","candidates":[[2,"hostile-2"]],"decision":{"vocabulary":"combat_v1","tool":"strike","params":{"target":"hostile-2"}}}'
echo "== XADD proposal -> $PROPOSAL_STREAM =="
docker exec "$REDIS_CONTAINER" redis-cli XADD "$PROPOSAL_STREAM" '*' proposal "$PROPOSAL" >/dev/null
echo "   proposals on the stream: $(docker exec "$REDIS_CONTAINER" redis-cli XLEN "$PROPOSAL_STREAM")"

drain "committing the proposal"

EVENTS=$(q "$CHAN_DB" "SELECT count(*) FROM events WHERE reality_id='$REALITY'")
echo "== committed events in $CHAN_DB: $EVENTS =="
[ "${EVENTS:-0}" -gt 0 ] || { echo "NO EVENT COMMITTED — the chain has nothing to render; refusing to claim a demo"; exit 1; }

cat <<ENV

== the stack, ready to run against these ==
  REALITY   $REALITY
  DRIVER    $DRIVER      (holds the live binding)
  ACTOR     $ACTOR  -> entity $ENTITY
  META      $BASE/$META_DB
  CHANNEL   $BASE/$CHAN_DB
  EVENTS    $EVENTS committed

ENV
[ "${1:-}" = "--seed-only" ] && { echo "--seed-only: stopping before the servers."; exit 0; }

# ── G4/G5: the three services, pointed at the throwaway pair ────────────────
#
# Started here rather than left to the caller BECAUSE that is the row's point.
# `F4` stood its stack up by hand and could not be re-run; a demo whose setup
# lives in someone's shell history is a demo that will be wrong within a week.
#
# The compose `publisher` service points at the DEV meta and cannot see this
# reality — the registry it polls is a different database. So a second instance
# runs here against the smoke meta. Same binary, different registry.

wait_http() { # wait_http <url> <label>
  for _ in $(seq 1 60); do
    curl -s -m1 -o /dev/null "$1" 2>/dev/null && { echo "   $2 up"; return 0; }
    sleep 1
  done
  echo "   $2 DID NOT COME UP"; return 1
}

echo "== publisher (smoke meta) -> $REDIS_URL =="
# BUILT, then run. `go run` forks a child, and `$!` captures the WRAPPER — so
# `stop_all` killed the wrapper, the compiled publisher kept polling, and the
# next run's DROP DATABASE failed with "1 other session using the database".
# Worse, the eviction added for exactly that case loses the race: terminating
# the backend just makes a live poller reconnect a second later. The fix is to
# hold a PID that is really the process. Third time this shape has bitten today
# (npx wrapper, go run wrapper) — a pid file is only as true as the thing it
# names.
echo "== building the publisher =="
( cd services/publisher && go build -o "$RUN/publisher.exe" ./cmd/publisher )
PUBLISHER_ID=kernel-state-demo SHARD_HOST=pg-shard-0.internal PUBLISHER_SHARD_HOST_OVERRIDE="pg-shard-0.internal=$PGHOSTPORT" META_DB_URL="$BASE/$META_DB?sslmode=disable" REDIS_URL="$REDIS_URL" SHARD_DB_USER="$PGUSER" SHARD_DB_PASSWORD="$PGPASSWORD" SHARD_DB_SSLMODE=disable PUBLISHER_HTTP_ADDR=":8092"   "$RUN/publisher.exe" >"$RUN/publisher.log" 2>&1 &
echo $! > "$RUN/publisher.pid"

echo "== world-service :7150 =="
WORLD_HTTP_BIND=127.0.0.1:7150 LOREWEAVE_INTERNAL_TOKEN=kernel_demo_token PROVISION_META_DSN="$BASE/$META_DB?sslmode=disable" PROVISION_SHARD_ADMIN_DSN="$BASE/postgres?sslmode=disable" PROVISION_BRIDGE_URL="http://127.0.0.1:8090" PROVISION_BRIDGE_TOKEN=unused PROVISION_SHARD_HOSTPORT="$PGHOSTPORT" PROVISION_PG_USER="$PGUSER" PROVISION_PG_PASSWORD="$PGPASSWORD"   ./target/debug/world-service.exe >"$RUN/world.log" 2>&1 &
echo $! > "$RUN/world.pid"
wait_http http://127.0.0.1:7150/livez world-service

echo "== game-server :2577 =="
PORT=2577 LOREWEAVE_INTERNAL_TOKEN=kernel_demo_token LOREWEAVE_CORS_ORIGINS="http://localhost:5199" LW_WS_DEV_ALLOW_STATIC=1 LW_WS_DEV_USER_REF_ID="$DRIVER" LW_WORLD_SERVICE_URL=http://127.0.0.1:7150 LW_CHANNEL_REALITY_ID="$REALITY" LW_CHANNEL_ID="$CHANNEL" LW_CHANNEL_REDIS_URL="$REDIS_URL"   node services/game-server/dist/index.js >"$RUN/gs.log" 2>&1 &
echo $! > "$RUN/gs.pid"
wait_http http://127.0.0.1:2577/livez game-server

sleep 3
echo "== did the event reach the wire? =="
echo "   lw.events.$REALITY  XLEN=$(docker exec "$REDIS_CONTAINER" redis-cli XLEN "lw.events.$REALITY")"

cat <<NEXT

== open it ==
  VITE_GAME_SERVER_URL=ws://localhost:2577 VITE_INTERNAL_TOKEN=kernel_demo_token     npx vite --port 5199 --strictPort      # from frontend-game/
  then http://localhost:5199/play -> "Join channel"

  logs: $RUN/{publisher,world,gs}.log
  stop: bash scripts/smoke/kernel-state-demo.sh --down
NEXT
