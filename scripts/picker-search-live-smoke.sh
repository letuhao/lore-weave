#!/usr/bin/env bash
# picker-search-live-smoke — does the world picker's search reach the SERVER, in a browser?
#
# WHY THIS EXISTS
# ---------------
# ProjectPicker, MultiProjectPicker and WorldPicker each loaded one clamped page and filtered
# it with a client-side `includes()`. Past the route's ceiling an entry could not be found by
# typing its name and nothing said so — the same defect the library page shipped, where a book
# at rank 32 of 83 was filed as a Vietnamese diacritic bug for six days.
#
# The unit tests for that fix all mock something. The picker's tests mock the API client, so
# the URL is invisible to them; the API client's tests stub `apiJson`, so the network is
# invisible; the Go tests build SQL strings and never touch Postgres. Each link is pinned and
# NONE of them proves the chain. This runs the chain: real image, real browser, real request,
# real database.
#
# ⚠️ **THE ASSERTION IS ON THE REQUEST.** Typing a name and seeing one row is exactly what the
# BUG did. Only "the term appeared in an outgoing /v1/worlds request" separates them.
#
# The browser half lives under `frontend/tests/live/` and NOT beside this script: Node
# resolves a bare `playwright` import by walking up from the IMPORTING file, so a driver
# in `scripts/` cannot see `frontend/node_modules` no matter what the cwd is.
#
# Usage:  bash scripts/picker-search-live-smoke.sh            # against lw-iso
#         BASE=http://localhost:25174 bash scripts/…          # explicit
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOK_SVC="${BOOK_SVC:-lw-iso-book-service-1}"
PG="${PG:-lw-iso-postgres-1}"
BASE="${BASE:-http://localhost:25174}"

die() { echo "REFUSED — $*" >&2; exit 1; }

# Every value is assigned FIRST and validated in the CURRENT shell. The obvious spelling
# `X="$(die_if_empty "$(...)")"` reads as fail-closed and is not: `exit 1` inside a command
# substitution kills only the subshell, and the script sails on with an empty variable.
docker inspect "$BOOK_SVC" >/dev/null 2>&1 || die "$BOOK_SVC is not running"

SECRET="$(docker exec "$BOOK_SVC" sh -c 'printenv JWT_SECRET' 2>/dev/null || true)"
[ -n "$SECRET" ] || die "no JWT_SECRET in $BOOK_SVC — read from the RUNNING container, never baked in"

# The owner is whoever actually holds worlds here, chosen by count rather than hardcoded: a
# fixture id that rots is how a leg goes silently unrunnable.
OWNER="$(docker exec "$PG" psql -U loreweave -d loreweave_book -tAc \
  "SELECT owner_user_id FROM worlds GROUP BY 1 ORDER BY count(*) DESC LIMIT 1" 2>/dev/null | tr -d '\r' || true)"
[ -n "$OWNER" ] || die "no owner holds any worlds in this stack — nothing to search"

# A book with NO world attached, so the picker renders its COMBOBOX and not the selected chip.
BOOK="$(docker exec "$PG" psql -U loreweave -d loreweave_book -tAc \
  "SELECT id FROM books WHERE owner_user_id='$OWNER' AND world_id IS NULL \
   AND lifecycle_state='active' ORDER BY created_at DESC LIMIT 1" 2>/dev/null | tr -d '\r' || true)"
[ -n "$BOOK" ] || die "owner $OWNER has no active book without a world — the picker would render its chip, not its input"

# The term is a world this owner really has, so a zero result means the search broke rather
# than that nothing matched.
TERM_TO_TYPE="${TERM_TO_TYPE:-$(docker exec "$PG" psql -U loreweave -d loreweave_book -tAc \
  "SELECT name FROM worlds WHERE owner_user_id='$OWNER' ORDER BY created_at ASC LIMIT 1" \
  2>/dev/null | tr -d '\r' || true)}"
[ -n "$TERM_TO_TYPE" ] || die "could not read a world name to type"

PY="${PY:-python}"
JWT="$("$PY" - "$SECRET" "$OWNER" <<'PYEOF'
import base64, hashlib, hmac, json, sys, time
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
p = b64(json.dumps({"sub": sys.argv[2], "user_id": sys.argv[2],
                    "iat": int(time.time()), "exp": int(time.time()) + 3600},
                   separators=(",", ":")).encode())
print(f"{h}.{p}." + b64(hmac.new(sys.argv[1].encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()))
PYEOF
)"
[ -n "$JWT" ] || die "JWT minting produced nothing"

echo "picker-search-live-smoke"
echo "  base   $BASE"
echo "  owner  $OWNER"
echo "  book   $BOOK   (no world attached, so the combobox renders)"
echo "  type   '$TERM_TO_TYPE'"
echo

# ── the endpoint, before the browser ─────────────────────────────────────────────────────
# If this half is wrong the browser half cannot be right, and the failure is far easier to
# read here than through a UI.
PORT="$(docker port "$BOOK_SVC" 8082/tcp 2>/dev/null | head -1 | sed 's/.*://' | tr -d '\r')"
[ -n "$PORT" ] || die "book-service publishes no port"
API="http://localhost:${PORT}/v1/worlds"
ENC="$("$PY" -c "import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))" "$TERM_TO_TYPE")"

read_total() { curl -s -H "Authorization: Bearer $JWT" "$1" | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(d['total'],len(d['items']))"; }
ALL="$(read_total "${API}?limit=100")"
HIT="$(read_total "${API}?limit=1&q=${ENC}")"
PCT="$(read_total "${API}?limit=100&q=%25")"
echo "  --   unfiltered      total/items = $ALL"
echo "  --   q=<name>,limit=1 total/items = $HIT   (total>0 with limit=1 proves the COUNT is filtered too)"
echo "  --   q='%'            total/items = $PCT   (must be 0 0 — a LIKE wildcard would return everything)"
case "$PCT" in "0 0") ;; *) die "a literal '%' matched rows — escapeLikePattern is not being applied" ;; esac
case "$HIT" in "0 "*) die "a world this owner OWNS was not found by name" ;; esac

echo
cd "$ROOT/frontend"
BASE="$BASE" JWT="$JWT" USER_ID="$OWNER" BOOK_ID="$BOOK" TERM_TO_TYPE="$TERM_TO_TYPE" \
  node "$ROOT/frontend/tests/live/picker_search_smoke.mjs"
