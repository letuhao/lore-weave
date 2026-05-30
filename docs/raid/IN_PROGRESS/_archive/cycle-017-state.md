---
cycle: 17
title: Strategy (d) re-cook (gate-enforced + licensing)
current_phase: COMMIT
phase_started_at: 2026-05-31T00:00:00Z
last_checkpoint_at: 2026-05-31T00:45:00Z
retry_count: 0
quota_block_count: 0
dps_status:
  - dps_id: 1
    worktree: in-place (worktrees broken; build on lore-enrichment/foundation)
    branch: lore-enrichment/foundation
    status: in_progress
    model: opus-4-8
    started_at: 2026-05-31T00:00:00Z
    completed_at: null
adversary_findings_count: 0
scope_guard_result: CLEAR
verify_script_exit: 0
notes: >
  Cold-start. Deps C15+C16 DONE confirmed in CYCLE_LOG. Baseline pytest 400 pass/26 skip.
  C16 wired build_live_runner -> GateAwareStrategyFactory (gate enforced e2e). C17 mirrors:
  ReCookStrategy (P3, technique=recook) registered the SAME way + a LICENSING CHECK
  (refuses unlicensed/unknown sources, default-deny). Additive license CHECK constraint on
  source_corpus. H0 quarantine non-negotiable. No web search. Chinese output. No model names.
---

# Cycle 17 in-progress state

Re-cook P3 strategy. Read all required files: factory.py / fabrication.py / registry.py /
base.py (C16 gate-aware factory + P2 pattern to mirror), provenance.py (C11 H0 chokepoint),
canon_verify.py + wiring.py (C12), migrate.py (source_corpus already HAS a `license` column,
default 'public-domain', but NO CHECK constraint + no licensing-gate logic), store.py
(upsert_corpus already accepts license param), assembly.py + stages.py (runner wiring:
FabricationPipeline is the template for ReCookPipeline; build_live_runner already routes via
GateAwareStrategyFactory).

Design: `gated_feature_flags` already forces ALL non-P1 (incl RECOOK) off when gate fails;
factory already default-enables ANY non-P1 tier on a passed gate. So recook plugs into the
EXISTING gate machinery with NO factory regression — just register the recook strategy in the
factory's strategies list + route the pipeline in assembly. The C17-specific surface is the
LICENSING CHECK module (default-deny; admits only public_domain|licensed; refuses
unknown/unlicensed/copyrighted/missing at BOTH corpus-admission and fact-emit) + an additive
license CHECK constraint on source_corpus.

Next: BUILD (TDD) — licensing module, recook strategy, ReCookPipeline, registry/factory/assembly
wiring, migration CHECK constraint, tests, verify-cycle-17.sh.
