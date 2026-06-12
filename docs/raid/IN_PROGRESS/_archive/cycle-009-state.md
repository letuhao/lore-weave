---
cycle: 9
title: Strategy (a) template
current_phase: COMMIT
phase_started_at: 2026-05-30T08:00:00Z
last_checkpoint_at: 2026-05-30T08:12:00Z
retry_count: 0
dps_status: []
adversary_findings: 0blk/0maj/0min/1note
scope_guard_result: CLEAR
verify_script_exit: 0
notes: verify-cycle-9.sh exit 0; 19 new C9 tests + 119 prior = 138 pass, 11 db-skip; ruff clean; CYCLE_LOG row 9 DONE; AUDIT_LOG appended; staging cycle files
---

# Cycle 9 in-progress state

DESIGN: `TemplateStrategy(EnrichmentStrategy)` (technique='template', tier P1) in
`app/strategies/template.py`. Given a `Gap` → emit a `ScaffoldedProposal` SKELETON:
one slot per MISSING dimension, dimension KEYS in Chinese (derived from C6
`DimensionSpec.label` — single source of truth, NOT hardcoded), EMPTY placeholder
values. H0 at construction: origin='enrichment', technique='template',
review_status='proposed', confidence=low positive (DB CHECK >0 AND <1.0 → use
small constant, scaffold has near-zero confidence), pending_validation=True,
provenance_json noting template technique + source gap. Scope (user_id/project_id)
carried from StrategyContext.

KEY DECISIONS:
- Dimension keys = C6 `DimensionSpec.label` (历史/地理/文化 Chinese, features/inhabitants
  English per the LOCKED C6 dimension set — brief lists "历史/地理/文化/features/inhabitants").
  Derived live from `dimensions_for(kind)` → no drift from C6.
- confidence: DB schema CHECK is `>0 AND <1.0` (cannot be exactly 0). Use a low
  positive `_SCAFFOLD_CONFIDENCE` (e.g. 0.01) → scaffold = empty, near-zero confidence,
  still DB-valid and <1.0 (H0).
- NO LLM, NO retrieval, NO model names, NO migrations. Pure in-memory scaffolding.
- Register into C8 registry under 'template'; P1 flag ON by default → selectable.

SCOPE: only app/strategies/template.py (+ __init__ export) + tests/test_template_strategy.py
+ scripts/raid/verify-cycle-9.sh + docs/raid.
