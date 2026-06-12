#!/usr/bin/env bash
# verify-cycle-7.sh — CI gate for RAID cycle 7 (Gap-detection ENGINE, M1b). Exit 0 = PASS.
# Modeled on scripts/raid/verify-cycle-6.sh.
#
# Asserts (per docs/raid/cycle_briefs/07_gap-detection-engine.md acceptance criteria):
#   1. Engine module exists: app/gaps/engine.py defines EntityCoverage +
#      GapDetectionEngine + detect/detect_ranked + the Q6 project entrypoint.
#   2. Engine consumes the C1 KnowledgeReadPort + the C6 model (imports them,
#      defines NO dimensions/ranking of its own).
#   3. Gap-engine unit suite green: known C6 fixture → EXACT expected ranked Gap
#      list (dimensions + order + scores), determinism, Q6 degradation, no-gap
#      for a fully-described place.
#   4. Determinism re-check: the ranked order/scores the engine produces from the
#      fixture coverage equal the fixture's own _meta.expected_ranking_order /
#      expected_scores (golden, computed by the C6 model — not the engine).
#   5. ruff clean on app/gaps/engine.py + tests/test_gap_engine.py.
#   6. NO hardcoded provider/model names (LLM-free engine).
#   7. LLM-free / DB-write-free: engine.py imports NO graph/DB/LLM client and
#      issues NO write (reads only through the C1 port).
#   8. Full service unit suite green (no regression).
# Not a cross-service cycle (the C1 port is exercised via its Null/mock impl) →
# NO cross-service live-smoke token required.
set -uo pipefail
CYCLE=7
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
ENGINE="$SVC/app/gaps/engine.py"
MODEL="$SVC/app/gaps/model.py"
FIXTURE="$SVC/tests/fixtures/gaps_fengshen.json"
TESTFILE="$SVC/tests/test_gap_engine.py"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-7] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-7] ok: $1"; }

echo "[verify-cycle-7] running CI gate"

# ── 1. engine module: EntityCoverage / GapDetectionEngine / entrypoints ────────
[ -f "$ENGINE" ] || fail "missing app/gaps/engine.py"
for sym in "class EntityCoverage" "class GapDetectionEngine" \
           "def detect" "def detect_ranked" "def detect_ranked_for_project" \
           "def detect_gaps" "def detect_ranked_gaps"; do
  grep -q "$sym" "$ENGINE" || fail "engine.py missing: $sym"
done
ok "engine.py defines EntityCoverage/GapDetectionEngine + detect/detect_ranked + project entrypoint"

# ── 2. consumes the C1 port + C6 model (does not redefine them) ────────────────
grep -q "from app.clients.port import" "$ENGINE" || fail "engine.py must import the C1 KnowledgeReadPort"
grep -q "KnowledgeReadPort" "$ENGINE" || fail "engine.py must reference KnowledgeReadPort (C1 seam)"
grep -q "from app.gaps.model import" "$ENGINE" || fail "engine.py must consume the C6 gap model"
grep -q "rank_gaps" "$ENGINE" || fail "engine.py must use the C6 rank_gaps (no own ranking)"
ok "engine consumes the C1 KnowledgeReadPort + the C6 model/ranking"

# ── 3+4. gap-engine unit suite green + golden-vs-engine determinism re-check ────
[ -f "$FIXTURE" ] || fail "missing tests/fixtures/gaps_fengshen.json"
cd "$SVC" || fail "service dir missing"

if ! python -m pytest "$TESTFILE" -q >/tmp/c7_engine.log 2>&1; then
  cat /tmp/c7_engine.log
  fail "gap-engine unit suite red"
fi
ok "gap-engine unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c7_engine.log | head -1))"

# Independent golden re-check: the engine, fed ONLY each fixture entry's
# present_dimensions, must reproduce the fixture's recorded ranked order + scores.
python - "$FIXTURE" <<'PY' || fail "engine output != fixture golden (see error above)"
import json, sys
from app.gaps.engine import EntityCoverage, detect_ranked_gaps
from app.gaps.model import Dimension, EntityKind

data = json.load(open(sys.argv[1], encoding="utf-8"))
covs = [
    EntityCoverage(
        entity_kind=EntityKind(e["entity_kind"]),
        canonical_name=e["canonical_name"],
        target_ref=e.get("target_ref"),
        mention_count=e["mention_count"],
        present_dimensions=tuple(Dimension(d) for d in e["present_dimensions"]),
    )
    for e in data["gaps"]
]
ranked = detect_ranked_gaps(covs)
order = [r.gap.canonical_name for r in ranked]
exp_order = data["_meta"]["expected_ranking_order"]
assert order == exp_order, f"order {order} != golden {exp_order}"
scores = {r.gap.canonical_name: r.score for r in ranked}
exp_scores = {k: float(v) for k, v in data["_meta"]["expected_scores"].items()}
assert scores == exp_scores, f"scores {scores} != golden {exp_scores}"
# determinism: a second run is byte-identical.
again = [(r.gap.canonical_name, r.score, r.rank) for r in detect_ranked_gaps(covs)]
first = [(r.gap.canonical_name, r.score, r.rank) for r in ranked]
assert again == first, "non-deterministic ranked output across runs"
print("engine-golden-ok")
PY
ok "engine reproduces the fixture golden ranked order + scores (deterministic)"

# ── 5. ruff clean ─────────────────────────────────────────────────────────────
if ! python -m ruff check "$ENGINE" "$TESTFILE" >/tmp/c7_ruff.log 2>&1; then
  cat /tmp/c7_ruff.log
  fail "ruff check failed on engine.py + test_gap_engine.py"
fi
ok "ruff clean on engine.py + test_gap_engine.py"

# ── 6. no hardcoded provider/model names (LLM-free engine) ─────────────────────
if grep -rniE --include="*.py" \
   "text-embedding-bge-m3|bge-m3|nomic-embed|\bqwen|\bgemma|gpt-4|gpt-3\.|text-embedding-3|claude-[0-9]|\bllama" \
   "$ENGINE"; then
  fail "hardcoded provider/model name in engine.py"
fi
ok "no hardcoded provider/model names in engine.py"

# ── 7. LLM-free / DB-write-free: no graph/DB/LLM client import, no write ────────
if grep -nE "import (httpx|asyncpg|openai|litellm|requests|neo4j)|from (httpx|asyncpg|openai|litellm|requests|neo4j)" "$ENGINE"; then
  fail "engine.py imports an I/O/LLM client — it must read only through the C1 port"
fi
if grep -nE "\b(INSERT|UPDATE|DELETE)\b|\.execute\(|\.executemany\(" "$ENGINE"; then
  fail "engine.py issues a write/DB call — C7 is read-only (writes are C11/C13)"
fi
ok "engine is LLM-free + DB-write-free (reads only through the C1 port)"

# ── 8. full service unit suite green (no regression) ──────────────────────────
if ! python -m pytest -q >/tmp/c7_unit.log 2>&1; then
  cat /tmp/c7_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c7_unit.log | head -1))"

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-7] PASS"
exit 0
