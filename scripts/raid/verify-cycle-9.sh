#!/usr/bin/env bash
# verify-cycle-9.sh — CI gate for RAID cycle 9 (Strategy (a) template). Exit 0 = PASS.
# Modeled on scripts/raid/verify-cycle-8.sh.
#
# Asserts (per docs/raid/cycle_briefs/09_strategy-template.md acceptance criteria):
#   1. TemplateStrategy module exists with the required symbols
#      (app/strategies/template.py: TemplateStrategy + ScaffoldedProposal).
#   2. The C9 unit suite is green (gap → scaffolded proposal; H0; scope; registry).
#   3. Live in-process demonstration (no cross-service call): a typed Gap for a
#      locked demo LOCATION (玉虛宮) → strategy returns a scaffolded proposal with
#      one EMPTY slot per missing dimension, Chinese core dimension keys, all H0
#      fields set (origin='enrichment', technique='template', review_status=
#      'proposed', 0<confidence<1.0, pending_validation), Q3 scope preserved, and
#      resolves through the C8 registry under 'template' (P1 flag ON).
#   4. ruff clean on the new module + tests.
#   5. NO hardcoded provider/model names; NO LLM/embed/retrieval client imports;
#      NO migrations (reuses the C2 schema).
#   6. Full service unit suite green (no regression).
# Single-service cycle (in-process scaffolding) → NO cross-service live-smoke token.
set -uo pipefail
CYCLE=9
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
STRAT_DIR="$SVC/app/strategies"
TEMPLATE="$STRAT_DIR/template.py"
TESTS="$SVC/tests/test_template_strategy.py"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-9] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-9] ok: $1"; }

echo "[verify-cycle-9] running CI gate"

# ── 1. module exists with required symbols ────────────────────────────────────
[ -f "$TEMPLATE" ] || fail "missing module: $TEMPLATE"
[ -f "$TESTS" ]    || fail "missing tests: $TESTS"
grep -q "class TemplateStrategy" "$TEMPLATE" || fail "template.py missing TemplateStrategy"
grep -q "class ScaffoldedProposal" "$TEMPLATE" || fail "template.py missing ScaffoldedProposal"
grep -q "Technique.TEMPLATE" "$TEMPLATE" || fail "template.py not keyed on Technique.TEMPLATE"
ok "TemplateStrategy + ScaffoldedProposal present"

# ── 2. C9 unit suite green ────────────────────────────────────────────────────
cd "$SVC" || fail "service dir missing"
if ! python -m pytest tests/test_template_strategy.py -q >/tmp/c9_units.log 2>&1; then
  cat /tmp/c9_units.log
  fail "C9 unit suite red"
fi
ok "C9 unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c9_units.log | head -1))"

# ── 3. live in-process demonstration: gap → scaffolded H0 proposal ────────────
python - <<'PY' || fail "C9 in-process demonstration failed (see error above)"
import asyncio
import json
from pathlib import Path

from app.gaps.model import Dimension, EntityKind, Gap, dimensions_for
from app.strategies.base import StrategyContext, Technique, Tier
from app.strategies.feature_flags import load_feature_flags
from app.strategies.registry import InactiveStrategyError, StrategyRegistry
from app.strategies.template import ScaffoldedProposal, TemplateStrategy

# load the locked demo place 玉虛宮 from the C6 golden fixture
data = json.loads(
    (Path("tests") / "fixtures" / "gaps_fengshen.json").read_text(encoding="utf-8")
)
entry = next(e for e in data["gaps"] if e["canonical_name"] == "玉虛宮")
gap = Gap(
    entity_kind=EntityKind(entry["entity_kind"]),
    canonical_name=entry["canonical_name"],
    target_ref=entry.get("target_ref"),
    mention_count=entry.get("mention_count", 0),
    present_dimensions=tuple(Dimension(d) for d in entry.get("present_dimensions", [])),
    missing_dimensions=tuple(Dimension(d) for d in entry.get("missing_dimensions", [])),
)

# (a) resolves through the C8 registry under 'template' (P1 active by default)
reg = StrategyRegistry()
reg.register(TemplateStrategy())
strat = reg.select("template")
assert isinstance(strat, TemplateStrategy), type(strat)
assert strat.tier is Tier.P1

ctx = StrategyContext(user_id="user-7", project_id="proj-42")
[proposal] = asyncio.run(strat.run([gap], ctx))

# (b) one EMPTY slot per MISSING dimension, keys = C6 labels in C6 order
expected_keys = [
    s.label for s in dimensions_for(gap.entity_kind)
    if s.dimension in set(gap.missing_dimensions)
]
assert list(proposal.dimensions.keys()) == expected_keys, proposal.dimensions
assert len(proposal.dimensions) == len(gap.missing_dimensions)
assert all(v == "" for v in proposal.dimensions.values()), "placeholders must be EMPTY"
# core dimension keys are the source-faithful Chinese labels (not English ids)
assert {"历史", "地理", "文化"} <= set(proposal.dimensions.keys())
for english in ("history", "geography", "culture"):
    assert english not in proposal.dimensions

# (c) H0: born quarantined, NEVER canon
assert proposal.origin == "enrichment" and proposal.origin != "glossary"
assert proposal.technique == "template"
assert proposal.review_status == "proposed"
assert proposal.pending_validation is True
assert 0.0 < proposal.confidence < 1.0, proposal.confidence
assert "glossary" not in json.dumps(proposal.model_dump(), ensure_ascii=False)

# (d) Q3 scope preserved gap → proposal
assert proposal.user_id == "user-7" and proposal.project_id == "proj-42"

# (e) disabling the P1 flag makes template unselectable (registry/flag respected)
off = StrategyRegistry(flags=load_feature_flags(env={"ENRICH_STRATEGY_TEMPLATE_ENABLED": "0"}))
off.register(TemplateStrategy())
try:
    off.select("template")
    raise SystemExit("BUG: disabled template was selectable")
except InactiveStrategyError:
    pass

print("c9-demo-ok: 玉虛宮 gap → empty Chinese-keyed scaffold; H0 stamped; scope kept; flag respected")
PY
ok "in-process demo: gap → scaffolded proposal (Chinese keys, empty, H0, scope, registry/flag)"

# ── 4. ruff clean ─────────────────────────────────────────────────────────────
if ! python -m ruff check "$TEMPLATE" "$STRAT_DIR/__init__.py" "$TESTS" \
     >/tmp/c9_ruff.log 2>&1; then
  cat /tmp/c9_ruff.log
  fail "ruff check failed on template strategy + tests"
fi
ok "ruff clean on template strategy + tests"

# ── 5. no hardcoded model names; no LLM/retrieval client; no migrations ───────
if grep -rniE --include="*.py" \
   "text-embedding-bge-m3|bge-m3|nomic-embed|\bqwen|\bgemma|gpt-4|gpt-3\.|text-embedding-3|claude-[0-9]|\bllama" \
   "$TEMPLATE"; then
  fail "hardcoded provider/model name in template strategy"
fi
if grep -rnE "^\s*(import|from)\s+(httpx|openai|litellm|requests|neo4j|sentence_transformers)" \
   "$TEMPLATE"; then
  fail "template strategy imports an LLM/HTTP/retrieval client — C9 is scaffolding only (retrieval=C10, generation=C11)"
fi
if grep -rnE "CREATE TABLE|ALTER TABLE|run_migrations" "$TEMPLATE"; then
  fail "template strategy touches migrations — C9 reuses the C2 schema, no new DDL"
fi
ok "scope clean: no model names, no LLM/retrieval client, no migrations"

# ── 6. full service unit suite green (no regression) ──────────────────────────
if ! python -m pytest -q >/tmp/c9_unit.log 2>&1; then
  cat /tmp/c9_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c9_unit.log | head -1))"

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-9] PASS"
exit 0
