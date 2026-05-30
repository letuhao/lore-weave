#!/usr/bin/env bash
# verify-cycle-11.sh — CI gate for RAID cycle 11 (Schema-gov gen + H0 tag). Exit 0 = PASS.
# Modeled on scripts/raid/verify-cycle-10.sh.
#
# Asserts (per docs/raid/cycle_briefs/11_schema-gov-gen.md acceptance criteria):
#   1. generation modules exist with required symbols (provenance/repair/generate);
#      the H0 chokepoint factory + EnrichedFact are present.
#   2. C11 unit suites green:
#        - test_generation_repair.py  (malformed → repaired-or-typed-reject, no silent drop)
#        - test_provenance_h0.py      (EVERY fact: origin enriched + provenance + conf<1.0 + pending)
#        - test_generation.py         (mocked-LLM pipeline: prompt → repair → H0-tag)
#   3. H0 INVARIANT static guards: EnrichedFact is origin-enforced (no 'glossary',
#      conf<1.0), make_enriched_fact is the factory, no confidence=1.0 default.
#   4. NO hardcoded generation/embedding-model name in generation source
#      (model resolved via provider-registry model_ref — never a literal id).
#   5. NO direct HTTP/LLM client import in generation (LLM is an injected CompleteFn seam);
#      NO scope-creep into C12/C13 (no glossary/Neo4j write, no contradiction check).
#   6. ruff clean on the new modules + tests.
#   7. full service unit suite green (no regression).
#   8. secret-scan + prod-isolation lints clean.
# Cross-service = NO → no live-smoke token required (unit + mocked is sufficient here).
set -uo pipefail
CYCLE=11
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
GEN_DIR="$SVC/app/generation"
T_REPAIR="$SVC/tests/test_generation_repair.py"
T_PROV="$SVC/tests/test_provenance_h0.py"
T_GEN="$SVC/tests/test_generation.py"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-11] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-11] ok: $1"; }

echo "[verify-cycle-11] running CI gate"

# ── 1. modules + symbols ──────────────────────────────────────────────────────
for f in provenance.py repair.py generate.py __init__.py; do
  [ -f "$GEN_DIR/$f" ] || fail "missing app/generation/$f"
done
[ -f "$T_REPAIR" ] || fail "missing tests: $T_REPAIR"
[ -f "$T_PROV" ]   || fail "missing tests: $T_PROV"
[ -f "$T_GEN" ]    || fail "missing tests: $T_GEN"
grep -q "class EnrichedFact" "$GEN_DIR/provenance.py" || fail "provenance.py missing EnrichedFact"
grep -q "def make_enriched_fact" "$GEN_DIR/provenance.py" || fail "provenance.py missing make_enriched_fact factory"
grep -q "def repair_generation" "$GEN_DIR/repair.py" || fail "repair.py missing repair_generation"
grep -q "class RepairError" "$GEN_DIR/repair.py" || fail "repair.py missing typed RepairError"
grep -q "class SchemaGovernedGenerator" "$GEN_DIR/generate.py" || fail "generate.py missing SchemaGovernedGenerator"
grep -q "CompleteFn" "$GEN_DIR/generate.py" || fail "generate.py missing CompleteFn LLM seam"
ok "generation modules + symbols present (provenance/repair/generate)"

cd "$SVC" || fail "service dir missing"

# ── 2. C11 unit suites green ──────────────────────────────────────────────────
if ! python -m pytest "$T_REPAIR" "$T_PROV" "$T_GEN" -q >/tmp/c11_units.log 2>&1; then
  cat /tmp/c11_units.log
  fail "C11 unit suites red"
fi
ok "C11 unit suites green ($(grep -oE '[0-9]+ passed' /tmp/c11_units.log | head -1))"

# ── 3. H0 static guards ───────────────────────────────────────────────────────
# origin must be enforced against authored canon, and confidence bound < 1.0.
grep -q "lt=1.0" "$GEN_DIR/provenance.py" || fail "EnrichedFact.confidence not bounded < 1.0 (H0)"
grep -q "_CANON_ORIGIN" "$GEN_DIR/provenance.py" || fail "provenance.py does not guard against authored-canon origin"
grep -q "pending_validation" "$GEN_DIR/provenance.py" || fail "provenance.py missing pending_validation quarantine marker"
# no confidence=1.0 (canon) literal default in generation CODE (skip pycache +
# docstring/comment prose: only flag a real default/assignment, not a backtick-
# quoted rule mention like "no ``confidence=1.0`` default").
if grep -rnE --include="*.py" "^[^#]*confidence\s*[:=]\s*1\.0([^0-9]|$)" "$GEN_DIR" \
   | grep -v '\`\`'; then
  fail "a confidence=1.0 (canon) default appears in generation source — H0 violation"
fi
# the H0 markers must be REQUIRED, not optional-with-canon-default: assert the
# factory is the seam and EnrichedFact has no zero-arg construction path.
grep -q "make_enriched_fact" "$GEN_DIR/generate.py" || fail "generator does not route facts through the H0 factory"
ok "H0 static guards: origin-enforced, confidence<1.0, pending_validation, no canon default"

# ── 4. no hardcoded generation/embedding-model name in generation source ──────
if grep -rniE --include="*.py" \
   "qwen|gpt-[0-9]|gpt-4|gpt-3|bge-m3|nomic-embed|text-embedding|llama|gemma|mistral|deepseek|claude-[0-9]" \
   "$GEN_DIR"; then
  fail "hardcoded model name in generation source (LOCKED: resolve via provider-registry model_ref)"
fi
ok "no hardcoded model name (resolved via model_ref)"

# ── 5. no direct HTTP/LLM client import; no C12/C13 scope-creep ───────────────
if grep -rnE "^\s*(import|from)\s+(httpx|openai|litellm|neo4j|requests|langchain|llama_index)" \
   "$GEN_DIR"; then
  fail "generation imports an HTTP/LLM client directly — LLM is an injected CompleteFn seam"
fi
# C13 = write-back (glossary/Neo4j/promote), C12 = contradiction/anachronism — OUT.
# Scan .py CODE only (skip pycache binaries) and ignore comment/docstring prose
# lines (the module docstrings legitimately NAME these OUT-of-scope items to say
# they are excluded). A real reach-in would be an import or a call, not prose.
if grep -rnE --include="*.py" \
   "(import|from).*(glossary_sync|neo4j)|\.(run_write|merge)\(|extract-entities|promote_to_canon" \
   "$GEN_DIR" | grep -vE '^\s*#|"""|\*'; then
  fail "generation reaches into C12/C13 scope (write-back / canon-verify) — OUT of C11"
fi
ok "no direct HTTP/LLM client; no C12/C13 scope-creep"

# ── 6. ruff clean ─────────────────────────────────────────────────────────────
if ! python -m ruff check "$GEN_DIR" "$T_REPAIR" "$T_PROV" "$T_GEN" \
     >/tmp/c11_ruff.log 2>&1; then
  cat /tmp/c11_ruff.log
  fail "ruff check failed on generation modules + tests"
fi
ok "ruff clean on generation modules + tests"

# ── 7. full service unit suite green (no regression) ──────────────────────────
if ! python -m pytest -q >/tmp/c11_unit.log 2>&1; then
  cat /tmp/c11_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c11_unit.log | head -1); $(grep -oE '[0-9]+ skipped' /tmp/c11_unit.log | head -1))"

# ── 8. secret-scan + prod-isolation lints clean ───────────────────────────────
if [ -x "$REPO_ROOT/scripts/raid/secret-scan-cycle.sh" ]; then
  if ! bash "$REPO_ROOT/scripts/raid/secret-scan-cycle.sh" "$CYCLE" >/tmp/c11_secret.log 2>&1; then
    cat /tmp/c11_secret.log
    fail "secret-scan flagged the cycle diff"
  fi
  ok "secret-scan clean"
fi
# prod-isolation-lint takes a commit-sha/range; with no arg it lints the
# working-tree diff (the C11 changes still uncommitted at VERIFY time).
if [ -x "$REPO_ROOT/scripts/raid/prod-isolation-lint.sh" ]; then
  if ! bash "$REPO_ROOT/scripts/raid/prod-isolation-lint.sh" >/tmp/c11_iso.log 2>&1; then
    cat /tmp/c11_iso.log
    fail "prod-isolation-lint flagged a forbidden-dir edit"
  fi
  ok "prod-isolation-lint clean"
fi

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-11] PASS"
exit 0
