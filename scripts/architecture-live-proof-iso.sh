#!/usr/bin/env bash
# architecture-live-proof-iso.sh — derive every input the GOAL's proof needs, then run it.
#
# WHY THIS EXISTS
# ───────────────
# `architecture-live-proof.py` is the GOAL's own sentence as one command, and it takes nine
# inputs. Its docstring documents four. Run the documented invocation and five of the seven
# legs SKIP with "inputs not supplied"; run it bare and you get:
#
#     "verdict": "TOO-FEW-LEGS", "ran": 2, "floor": 3
#
# The floor catches that, so the failure is loud rather than a false green. What it does NOT
# do is tell anyone how to produce a real run. The `PROVEN / ran: 7` result recorded in the
# plan was assembled by hand in a shell and never written down: three censuses built from
# ad-hoc SQL, a book and project picked by eye, a stranger JWT minted on the spot. **Nothing
# in the repo could reproduce the plan's own central claim.**
#
# Each gate deliberately refuses to open a database — a gate that needed live credentials
# could not run offline in CI, which is where they have to run. That is correct, and it is
# also why the derivation had no home. This is the home.
#
# WHAT IT REFUSES TO DO
# ─────────────────────
# Every derivation below can fail, and a wrapper that shrugged one off would hand the proof a
# missing input, which the proof turns into a SKIP — a quieter version of exactly the vacuous
# pass the floor exists to stop. So each step either produces its value or exits non-zero
# naming what it could not derive and from where (rule 9). The only thing this script decides
# is HOW to ask; whether the answer is good enough is the proof's and its gates' business.
#
# READ-ONLY. Every statement here is a SELECT, a count, or an env read. It writes nothing to
# any database (rule 6) — the censuses land in a temp directory and are deleted on exit.
#
# Usage
#     bash scripts/architecture-live-proof-iso.sh              # against the lw-iso stack
#     COMPOSE_PROJECT=lw-iso bash scripts/architecture-live-proof-iso.sh
#     bash scripts/architecture-live-proof-iso.sh --selftest   # derivation logic, no stack
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-python}"
PROJ="${COMPOSE_PROJECT:-lw-iso}"

die() { echo "architecture-live-proof-iso: REFUSED — $*" >&2; exit 1; }
say() { echo "  [derive] $*"; }

first_error() { # the ERROR line if there is one, else the first line
  # psql prints LOAD/SET before it fails, so `head -1` names the wrong thing: the first
  # refusal this script produced read `REFUSED — AGE g_shared census failed: LOAD`.
  printf '%s' "$1" | grep -m1 -E "ERROR|could not connect" || printf '%s' "$1" | head -1
}

require_value() { # label value -> die unless the value is usable. Validates ONLY:
  # an earlier version ended with `printf '%s' "$v"`, which echoed whatever it was
  # handed — so a healthy run printed the Neo4j password and the stranger JWT to stdout.
  local label="$1" v="$2"
  [ -n "$v" ] || die "$label came back EMPTY"
  [ "$v" != "NULL" ] || die "$label came back NULL"
  case "$v" in
    *ERROR:*|*"could not connect"*|*"does not exist"*)
      die "$label failed: $(first_error "$v")" ;;
  esac
}

# ── --selftest ───────────────────────────────────────────────────────────────────────────
# The derivation is shell, so its failure mode is a silently empty variable feeding a SKIP.
# These cases drive `require_value` itself, which is the one function every step routes
# through, on inputs a live stack cannot produce on demand (an empty answer, a psql error
# string, a literal NULL). A stack that happens to be healthy cannot exercise any of them.
if [ "${1:-}" = "--selftest" ]; then
  fails=0
  check() { # name value expected_rc
    # The REAL require_value, in a subshell so its die() exit is observable. An earlier
    # version of this selftest defined its own copy that returned codes instead of dying —
    # it passed while the shipped function did not refuse at all (see the bite below).
    ( require_value "$1" "$2" ) >/dev/null 2>&1; got=$?
    if [ "$got" -eq "$3" ]; then echo "  ok   $1"; else
      echo "  FAIL $1 (rc=$got, wanted $3)"; fails=$((fails+1)); fi
  }
  check "a real value is accepted"                 "019fb89f-0aab-75ba-bf99-f21f98d409f4" 0
  check "an empty answer is refused"               ""                                    1
  check "a psql ERROR string is refused"           "ERROR:  relation does not exist"      1
  check "a literal NULL is refused"                "NULL"                                 1
  check "a connection failure is refused"          "psql: could not connect to server"    1
  check "a missing-relation message is refused"    'relation "entity_facts" does not exist' 1
  check "a JSON census is accepted"                '{"chapter_scale": 48610}'             0
  echo
  if [ "$fails" -ne 0 ]; then
    echo "architecture-live-proof-iso --selftest: FAIL ($fails case(s) wrong)"; exit 1; fi
  echo "architecture-live-proof-iso --selftest: OK (7 cases, 5 of them negative)"; exit 0
fi

c() { # container by compose service name
  local n; n="$(docker ps --format '{{.Names}}' | grep -E "^${PROJ}-$1-[0-9]+$" | head -1)"
  [ -n "$n" ] || die "no running container for service '$1' in compose project '${PROJ}'"
  printf '%s' "$n"
}

PG="$(c postgres)"; KPG="$(c knowledge-pg)"; GW="$(c knowledge-gateway)"; NEO="$(c neo4j)"
say "containers: $PG · $KPG · $GW · $NEO"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

psql_pg()  { docker exec "$PG"  psql -U loreweave -d "$1" -tAc "$2" 2>&1; }
psql_kpg() { docker exec "$KPG" psql -U loreweave -d loreweave_knowledge_vectors -tAc "$1" 2>&1; }

# ── secrets, read from the RUNNING stack rather than baked in ─────────────────────────────
env_of() { docker exec "$1" sh -c "printenv $2" 2>&1; }
TOKEN="$(env_of "$GW" INTERNAL_SERVICE_TOKEN)"
require_value 'INTERNAL_SERVICE_TOKEN (gateway env)' "$TOKEN"
SECRET="$(env_of "$GW" JWT_SECRET)"
require_value 'JWT_SECRET (gateway env)' "$SECRET"
PORT="$(docker port "$GW" 3000/tcp 2>/dev/null | head -1 | sed 's/.*://')"
require_value 'the gateway published port' "$PORT"
BASE="http://localhost:${PORT}"
say "base-url $BASE"

# ── the subject: a book with facts, its project, one of its entities ──────────────────────
# Every value here is assigned FIRST and validated in the CURRENT shell. The obvious spelling
# — `X="$(require_value ... "$(psql ...)")"` — reads as fail-closed and is not: `die` runs
# inside the command substitution, so `exit 1` kills the subshell and the script sails on with
# an empty variable. The first live run printed two REFUSED lines and then handed the proof an
# empty --project-id, which it turned into two SKIPs. Fail-closed has to be structural.
#
# The subject must satisfy BOTH stores: facts live in glossary, the project link lives in
# knowledge, and 38 of this stack's 468 projects have no book_id at all. So the candidates are
# ranked by fact count and the first one that also resolves to a project wins — rather than
# taking the richest book and discovering it is unlinked.
CANDS="$(psql_pg loreweave_glossary \
  "SELECT book_id FROM entity_facts GROUP BY 1 ORDER BY count(*) DESC LIMIT 25")"
require_value 'the candidate books carrying entity_facts' "$CANDS"
BOOK=""; PROJECT=""
for b in $CANDS; do
  pr="$(psql_pg loreweave_knowledge \
    "SELECT project_id FROM knowledge_projects WHERE book_id='$b' ORDER BY created_at LIMIT 1")"
  case "$pr" in *ERROR:*) die "knowledge_projects unreadable: $(first_error "$pr")";; esac
  if [ -n "$pr" ]; then BOOK="$b"; PROJECT="$pr"; break; fi
done
[ -n "$BOOK" ] || die "none of the 25 books with the most facts has a row in knowledge_projects"
require_value 'the subject project' "$PROJECT"

ENTITY="$(psql_pg loreweave_glossary \
  "SELECT entity_id FROM entity_facts WHERE book_id='$BOOK' ORDER BY 1 LIMIT 1")"
require_value "an entity of book $BOOK" "$ENTITY"
USER="$(psql_pg loreweave_book "SELECT owner_user_id FROM books WHERE id='$BOOK'")"
require_value "the owner of book $BOOK" "$USER"

say "book $BOOK · project $PROJECT · entity $ENTITY"

# ── leg 6's census — the command is the one in glossary-ordinal-axis-gate's own docstring ──
AXIS="$(psql_pg loreweave_glossary "
  SELECT json_build_object(
    'chapter_scale', count(*) FILTER (WHERE valid_from_ordinal <  1000000
                                        AND valid_from_ordinal IS NOT NULL),
    'stride_scale',  count(*) FILTER (WHERE valid_from_ordinal >= 1000000),
    'mixed_books', (SELECT count(*) FROM (
        SELECT book_id FROM entity_facts WHERE valid_from_ordinal IS NOT NULL
        GROUP BY book_id
        HAVING count(*) FILTER (WHERE valid_from_ordinal <  1000000) > 0
           AND count(*) FILTER (WHERE valid_from_ordinal >= 1000000) > 0) t))
  FROM entity_facts")"
require_value 'the glossary ordinal-axis census' "$AXIS"
printf '%s' "$AXIS" > "$TMP/axis.json"
say "axis census $AXIS"

# ── leg 2's two censuses: {project_id: node_count}, one per store ─────────────────────────
# The OTHER store is read first, and that is not an aesthetic choice. `graph-store-migrated`
# asks, per project the other store holds, whether the declared store holds it too — so the
# other census is what drives the comparison, and the declared one only has to cover it.
#
# That ordering is also the difference between a 2-second derivation and a 25-minute one.
# This stack carries 4356 AGE graphs (one per project, `g_<uuid without dashes>`). Counting
# all of them costs ~25 min one `docker exec` at a time, and collapsing it into a single
# statement trades that for `out of shared memory` — 4356 relations exceed
# max_locks_per_transaction. Neither is necessary: Neo4j names a handful of projects, and
# those plus the subject are the only counts the comparison can use.
NEOPW="$(env_of "$(c knowledge-service)" NEO4J_PASSWORD)"
require_value 'NEO4J_PASSWORD (knowledge-service env)' "$NEOPW"
neo_raw="$(docker exec "$NEO" cypher-shell -u neo4j -p "$NEOPW" --format plain \
  "MATCH (n) WHERE n.project_id IS NOT NULL RETURN n.project_id AS p, count(n) AS c" 2>/dev/null \
  | tail -n +2)"
"$PY" - "$TMP/neo4j.json" <<PYEOF
import json, sys
out = {}
for line in """${neo_raw}""".splitlines():
    line = line.strip().replace('"', '')
    if not line or ',' not in line:
        continue
    p, c = line.rsplit(',', 1)
    try:
        out[p.strip()] = int(c)
    except ValueError:
        continue
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"))
print(f"  [derive] Neo4j (other) census: {len(out)} project(s), {sum(out.values())} node(s)")
PYEOF

# The declared store is ONE graph, `g_shared`, keyed by a project_id property. This stack
# also carries 4356 legacy `g_<uuid without dashes>` per-project graphs, and censusing THOSE
# is what the first version of this script did: it reported 367 projects and 0 nodes, the
# STORE leg answered EMPTY_DECLARED, and the failure was mine, not the architecture's. The
# giveaway was that no `g_<hex>` graph existed for the one real project Neo4j holds.
age_raw="$(psql_kpg "LOAD 'age'; SET search_path=ag_catalog,public;
  SELECT * FROM cypher('g_shared', \$\$ MATCH (n) WHERE n.project_id IS NOT NULL
    RETURN n.project_id AS p, count(n) AS c \$\$) AS (p agtype, c agtype);")"
case "$age_raw" in *ERROR:*) die "AGE g_shared census failed: $(first_error "$age_raw")";; esac
"$PY" - "$TMP/age.json" <<PYEOF
import json, sys
out = {}
for line in """${age_raw}""".splitlines():
    line = line.strip()
    if "|" not in line:
        continue
    p, c = line.rsplit("|", 1)
    p = p.strip().strip('"')
    try:
        out[p] = int(c)
    except ValueError:
        continue
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"))
print(f"  [derive] AGE g_shared (declared) census: {len(out)} project(s), {sum(out.values())} node(s)")
PYEOF

# ── leg 7 needs a VALID token with no grant on --book-id ──────────────────────────────────
# A random uuid subject: authenticated, and a stranger to every book on the stack. Minting it
# here rather than reading a fixture from disk is deliberate — T48ap found that fixture rotted
# and its leg had been silently unrunnable.
STRANGER="$("$PY" - "$SECRET" <<'PYEOF'
import base64, hashlib, hmac, json, sys, time, uuid
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
p = b64(json.dumps({"sub": str(uuid.uuid4()), "user_id": str(uuid.uuid4()),
                    "iat": int(time.time()), "exp": int(time.time()) + 900},
                   separators=(",", ":")).encode())
sig = b64(hmac.new(sys.argv[1].encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
print(f"{h}.{p}.{sig}")
PYEOF
)"
require_value 'a minted stranger JWT' "$STRANGER"
say "stranger JWT minted (${#STRANGER} chars)"

echo
"$PY" "$ROOT/scripts/architecture-live-proof.py" --run \
  --base-url "$BASE" \
  --book-id "$BOOK" --project-id "$PROJECT" --entity-id "$ENTITY" --user-id "$USER" \
  --internal-token "$TOKEN" \
  --declared-census "$TMP/age.json" --other-census "$TMP/neo4j.json" \
  --axis-census "$TMP/axis.json" --axis-ceiling 1 \
  --stranger-jwt "$STRANGER" \
  "$@"
