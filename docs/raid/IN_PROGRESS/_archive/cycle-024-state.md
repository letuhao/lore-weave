---
cycle: 24
title: Divergence wizard + derivative studio (FE)
current_phase: SESSION
phase_started_at: 2026-06-14T17:43:49Z
last_checkpoint_at: 2026-06-14T17:43:49Z
retry_count: 0
dps_status: []
adversary_findings: null
scope_guard_result: null
verify_script_exit: null
notes: ESCALATED design_gap: FE complete+green (19 vitest, verify-cycle-24.sh exit0, tsc/eslint/provider-gate clean). Genderbend Playwright drove all 4 steps + reached real derive endpoint (FE/BFF/BE wiring OK). BLOCKED by C23 BE bug: knowledge create_or_get dedupes book project per (user,book) -> derive reuses source project_id -> uq_composition_work_project 500. G2 unsatisfiable via current path. Fix is upstream C23/knowledge (force_new param), C24 forbidden to edit C23. Evidence in docs/raid/evidence/cycle-24/. FE files NOT committed (held in working tree).
---

# Cycle 24 in-progress state

