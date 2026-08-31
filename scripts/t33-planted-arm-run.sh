#!/usr/bin/env bash
# t33-planted-arm-run.sh — put the PLANTED corpus through the real extractor, on lw-iso.
#
# WHAT THIS IS
# ────────────
# T33's stop condition asks whether the causal pass "yields few or low-quality causal edges".
# Answering it needs a corpus with known ground truth. The primary route is a person
# labelling real events, and `t33-causal-labelling-sheet.py --score` refuses an assistant
# signature — correctly, and this does not touch that.
#
# This is the PLANTED arm: prose written so the causal structure is known by construction,
# with the design fixed and committed BEFORE anything ran (see
# docs/measurements/2026-08-30-t33-planted-corpus/DESIGN.md and its SHA-256 binding).
#
# WHAT IT CANNOT ESTABLISH, said before it runs rather than after: the same agent wrote the
# prose and the ground truth, so a PASS says only "the pass recovers causation planted for
# it". A FAILURE is the stronger result.
#
# WRITES. It creates a book, chapters, a knowledge project, and graph nodes — all on lw-iso,
# which the GRANT authorises for exactly this (LLM spend and graph writes THERE). It refuses
# to run against anything else.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${COMPOSE_PROJECT:-lw-iso}"
CORPUS="$ROOT/docs/measurements/2026-08-30-t33-planted-corpus"

die() { echo "t33-planted-arm: REFUSED — $*" >&2; exit 1; }
say() { echo "  [arm] $*"; }

[ "$PROJ" = "lw-iso" ] || die "this run WRITES (LLM spend + graph nodes). The GRANT authorises
  lw-iso or a throwaway, and COMPOSE_PROJECT is '$PROJ'."

c() {
  local n; n="$(docker ps --format '{{.Names}}' | grep -E "^${PROJ}-$1-[0-9]+$" | head -1)"
  [ -n "$n" ] || die "no running container for '$1' in compose project '${PROJ}'"
  printf '%s' "$n"
}
BOOKC="$(c book-service)"; KNOW="$(c knowledge-service)"; PGC="$(c postgres)"

env_of() { docker exec "$1" sh -c "printenv $2" 2>/dev/null; }
SECRET="$(env_of "$BOOKC" JWT_SECRET)";        [ -n "$SECRET" ] || die "no JWT_SECRET on $BOOKC"
ITOKEN="$(env_of "$KNOW" INTERNAL_SERVICE_TOKEN)"; [ -n "$ITOKEN" ] || die "no INTERNAL_SERVICE_TOKEN on $KNOW"
BOOK_PORT="$(docker port "$BOOKC" 8082/tcp | head -1 | sed 's/.*://')"
KNOW_PORT="$(docker port "$KNOW" 8092/tcp | head -1 | sed 's/.*://')"
[ -n "$BOOK_PORT" ] && [ -n "$KNOW_PORT" ] || die "book/knowledge ports not published"

# The extraction model must be a user_model the OWNER holds, so the run is BYOK through the
# provider registry rather than a hardcoded model name (the provider-gateway invariant).
read -r USER_ID MODEL_REF <<<"$(docker exec "$PGC" psql -U loreweave -d loreweave_provider_registry -tAc "
  SELECT owner_user_id || ' ' || user_model_id FROM user_models
  WHERE is_active AND provider_kind='lm_studio' AND provider_model_name ILIKE '%gemma%'
  ORDER BY created_at DESC LIMIT 1" 2>/dev/null)"
[ -n "${USER_ID:-}" ] || die "no active lm_studio gemma user_model on ${PROJ} to extract with"
say "owner $USER_ID · model_ref $MODEL_REF"

TOK="$(python - "$SECRET" "$USER_ID" <<'PY'
import base64, hashlib, hmac, json, sys, time
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
p = b64(json.dumps({"sub": sys.argv[2], "user_id": sys.argv[2],
                    "iat": int(time.time()), "exp": int(time.time()) + 3600},
                   separators=(",", ":")).encode())
print(f"{h}.{p}." + b64(hmac.new(sys.argv[1].encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()))
PY
)"
BOOK_API="http://localhost:${BOOK_PORT}"; KNOW_API="http://localhost:${KNOW_PORT}"
AUTH=(-H "Authorization: Bearer $TOK" -H 'Content-Type: application/json')
INTERNAL=(-H "X-Internal-Token: $ITOKEN" -H 'Content-Type: application/json')

MARKER="$(date +%s)"
BOOK_ID="$(curl -s "${AUTH[@]}" -X POST "$BOOK_API/v1/books" \
  -d "{\"title\":\"T33 planted corpus $MARKER\",\"original_language\":\"en\"}" \
  | python -c 'import sys,json; print(json.load(sys.stdin).get("book_id",""))')"
[ -n "$BOOK_ID" ] || die "book creation returned no book_id"
say "book $BOOK_ID"

PROJECT_ID="$(curl -s "${AUTH[@]}" -X POST "$KNOW_API/v1/knowledge/projects" \
  -d "{\"name\":\"T33 planted arm $MARKER\",\"project_type\":\"book\",\"book_id\":\"$BOOK_ID\"}" \
  | python -c 'import sys,json; print(json.load(sys.stdin).get("project_id",""))')"
[ -n "$PROJECT_ID" ] || die "project creation returned no project_id"
say "project $PROJECT_ID"

# ── the two chapters, in reading order ────────────────────────────────────────────────────
# `chapter_index` is NOT optional in practice: without it every extracted Event lands with
# `event_order = NULL`, and the sheet's whole premise — pairs in reading order — collapses.
# The extractor's own request model documents that it was the field the two entry points had
# diverged on.
CH_IDS=()
i=0
for f in "$CORPUS/chapter-01-the-cistern.md" "$CORPUS/chapter-02-the-salt-road.md"; do
  [ -f "$f" ] || die "corpus chapter missing: $f"
  TITLE="$(head -1 "$f" | sed 's/^# *//')"
  CH="$(curl -s "${AUTH[@]}" -X POST "$BOOK_API/v1/books/$BOOK_ID/chapters" \
        -d "$(python - "$TITLE" "$i" <<'PY'
import json, sys
print(json.dumps({"title": sys.argv[1], "original_language": "en",
                  "sort_order": int(sys.argv[2]) + 1}))
PY
)" | python -c 'import sys,json; print(json.load(sys.stdin).get("chapter_id",""))')"
  [ -n "$CH" ] || die "chapter creation failed for $f"
  CH_IDS+=("$CH")
  say "chapter $((i+1)) $CH  ($TITLE)"

  BODY="$(python - "$f" "$USER_ID" "$PROJECT_ID" "$CH" "$MODEL_REF" "$i" <<'PY'
import json, sys, uuid
text = open(sys.argv[1], encoding="utf-8").read()
# drop the markdown H1: the beats are the paragraphs, and a title line is not a beat
text = "\n".join(l for l in text.split("\n") if not l.startswith("# "))
print(json.dumps({
    "user_id": sys.argv[2], "project_id": sys.argv[3],
    "item_type": "chapter", "source_type": "chapter", "source_id": sys.argv[4],
    "job_id": str(uuid.uuid4()),
    "model_source": "user_model", "model_ref": sys.argv[5],
    "chapter_text": text.strip(), "chapter_index": int(sys.argv[6]) + 1,
}))
PY
)"
  say "extracting chapter $((i+1))…"
  OUT="$(curl -s -m 900 "${INTERNAL[@]}" -X POST "$KNOW_API/internal/extraction/extract-item" -d "$BODY")"
  echo "$OUT" | python -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("    (non-JSON response)", sys.stdin.read()[:200]); raise SystemExit
print("    events=%s entities=%s facts=%s in %ss" % (
    d.get("events_merged"), d.get("entities_merged"),
    d.get("facts_merged"), d.get("duration_seconds")))
' || die "extraction failed for chapter $((i+1)): $(printf '%s' "$OUT" | head -c 300)"
  i=$((i+1))
done

# ── the causal pass ───────────────────────────────────────────────────────────────────────
# tagged_only=false ON PURPOSE. The default restricts inference to motif-tagged events, and
# an untagged corpus would give the pass an EMPTY input — which reports as "no edges" and is
# indistinguishable from "the detector found nothing". That confound would answer T33's stop
# condition with a number that never described the detector at all.
say "causal pass (tagged_only=false)…"
CAUSAL="$(curl -s -m 900 "${INTERNAL[@]}" -X POST "$KNOW_API/internal/extraction/causal-edges" \
  -d "{\"user_id\":\"$USER_ID\",\"book_id\":\"$BOOK_ID\",\"model_source\":\"user_model\",
       \"model_ref\":\"$MODEL_REF\",\"tagged_only\":false}")"
echo "$CAUSAL" | python -c '
import sys, json
d = json.load(sys.stdin)
print("    edges_written=%s events_considered=%s" % (
    d.get("edges_written"), d.get("events_considered")))
' || die "causal pass failed: $(printf '%s' "$CAUSAL" | head -c 300)"

echo
echo "PROJECT_ID=$PROJECT_ID"
echo "CHAPTER_IDS=${CH_IDS[*]}"
echo "BOOK_ID=$BOOK_ID"
echo
echo "Next: emit the sheet bound to the design digest, then --score-planted."
