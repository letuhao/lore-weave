#!/usr/bin/env bash
# verify-cycle-6.sh — CI gate for RAID cycle 6 (Gap MODEL spec, M1a). Exit 0 = PASS.
# Generated from scripts/raid/verify-cycle-template.sh.
#
# Asserts (per docs/raid/cycle_briefs/06_gap-model-spec.md acceptance criteria):
#   1. Spec doc exists and lists all 5 demo dimensions w/ Chinese labels +
#      the gap definition + the ranking formula.
#   2. Typed model exists: app/gaps/model.py defines EntityKind / Dimension /
#      Gap / GapRanking + a deterministic rank_score().
#   3. Fixtures complete: all 4 locked LOCATIONs present in gaps_fengshen.json,
#      each classifying the 5 dimensions present/missing.
#   4. Gap-model unit suite green (schema, ranking determinism + pinned
#      ordering, completeness, H0 purity).
#   5. ruff clean on app/gaps/ + tests/test_gap_model.py.
#   6. NO hardcoded provider/model names (this cycle has zero LLM calls).
#   7. Pure data: model.py imports NO graph/DB/LLM client (C7 boundary).
#   8. Full service unit suite green (no regression).
# Single-service, pure-data model → NO cross-service live-smoke token required.
set -uo pipefail
CYCLE=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
MODEL="$SVC/app/gaps/model.py"
SPEC="$SVC/docs/gap_model.md"
FIXTURE="$SVC/tests/fixtures/gaps_fengshen.json"
TESTFILE="$SVC/tests/test_gap_model.py"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-6] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-6] ok: $1"; }

echo "[verify-cycle-6] running CI gate"

# ── 1. spec doc: 5 dims w/ Chinese labels + gap def + ranking formula ──────────
[ -f "$SPEC" ] || fail "missing docs/gap_model.md spec"
for label in "历史" "地理" "文化" "features" "inhabitants"; do
  grep -q "$label" "$SPEC" || fail "spec missing dimension label $label"
done
grep -q "history" "$SPEC" && grep -q "geography" "$SPEC" && grep -q "culture" "$SPEC" \
  || fail "spec missing a dimension id"
grep -qi "gap" "$SPEC" || fail "spec missing the gap definition"
grep -qi "rank" "$SPEC" || fail "spec missing the ranking formula"
ok "spec doc lists 5 dimensions (历史/地理/文化/features/inhabitants) + gap def + ranking"

# ── 2. typed model: EntityKind / Dimension / Gap / GapRanking / rank_score ─────
[ -f "$MODEL" ] || fail "missing app/gaps/model.py"
for sym in "class EntityKind" "class Dimension" "class Gap" "class GapRanking" \
           "def rank_score" "def rank_gaps"; do
  grep -q "$sym" "$MODEL" || fail "model.py missing: $sym"
done
ok "model.py defines EntityKind/Dimension/Gap/GapRanking + rank_score/rank_gaps"

# ── 3. fixtures: all 4 locked LOCATIONs, each classifying the 5 dimensions ─────
[ -f "$FIXTURE" ] || fail "missing tests/fixtures/gaps_fengshen.json"
for place in "玉虛宮" "碧遊宮" "蓬萊" "陳塘關"; do
  grep -q "$place" "$FIXTURE" || fail "fixture missing locked LOCATION $place"
done
python - "$FIXTURE" <<'PY' || fail "fixture structure invalid (see error above)"
import json, sys
DIMS = {"history","geography","culture","features","inhabitants"}
EXPECTED = {"玉虛宮","碧遊宮／金鰲島","蓬萊","陳塘關"}
data = json.load(open(sys.argv[1], encoding="utf-8"))
gaps = data["gaps"]
names = {g["canonical_name"] for g in gaps}
assert names == EXPECTED, f"fixture places {names} != locked {EXPECTED}"
for g in gaps:
    classified = set(g["present_dimensions"]) | set(g["missing_dimensions"])
    assert classified == DIMS, f"{g['canonical_name']} mis-classifies dims: {classified}"
    assert not (set(g["present_dimensions"]) & set(g["missing_dimensions"])), \
        f"{g['canonical_name']} has a dim in both present and missing"
    assert g["missing_dimensions"], f"{g['canonical_name']} has no missing dim (not a gap)"
print("fixture-ok")
PY
ok "all 4 locked LOCATIONs present, each classifying the 5 dimensions"

cd "$SVC" || fail "service dir missing"

# ── 4. gap-model unit suite green (determinism + pinned ordering) ──────────────
if ! python -m pytest "$TESTFILE" -q >/tmp/c6_gap.log 2>&1; then
  cat /tmp/c6_gap.log
  fail "gap-model unit suite red"
fi
ok "gap-model unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c6_gap.log | head -1))"

# ── 5. ruff clean ─────────────────────────────────────────────────────────────
if ! python -m ruff check app/gaps/ "$TESTFILE" >/tmp/c6_ruff.log 2>&1; then
  cat /tmp/c6_ruff.log
  fail "ruff check failed on app/gaps/ + test_gap_model.py"
fi
ok "ruff clean on app/gaps/ + test_gap_model.py"

# ── 6. no hardcoded provider/model names (this cycle has zero LLM calls) ───────
if grep -rniE --include="*.py" \
   "text-embedding-bge-m3|bge-m3|nomic-embed|\bqwen|\bgemma|gpt-4|gpt-3\.|text-embedding-3|claude-[0-9]|\bllama" \
   "$SVC/app/gaps/"; then
  fail "hardcoded provider/model name in app/gaps/"
fi
ok "no hardcoded provider/model names in app/gaps/"

# ── 7. pure data: no graph/DB/LLM client import in model.py (C7 boundary) ──────
if grep -nE "import (httpx|asyncpg|openai|litellm|requests|neo4j)|from (httpx|asyncpg|openai|litellm|requests|neo4j)" "$MODEL"; then
  fail "model.py imports an I/O/LLM client — that is the C7 engine boundary"
fi
ok "model.py is pure data (no graph/DB/LLM imports)"

# ── 8. full service unit suite green (no regression) ──────────────────────────
if ! python -m pytest -q >/tmp/c6_unit.log 2>&1; then
  cat /tmp/c6_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c6_unit.log | head -1))"

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-6] PASS"
exit 0
