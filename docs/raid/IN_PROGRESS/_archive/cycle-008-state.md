---
cycle: 8
title: Strategy core
current_phase: COMMIT
phase_started_at: 2026-05-30T07:40:00Z
last_checkpoint_at: 2026-05-30T07:55:00Z
retry_count: 0
dps_status: []
adversary_findings: 0blk/0maj/0min/1note
scope_guard_result: CLEAR
verify_script_exit: 0
notes: verify-cycle-8.sh exit 0; 43 new C8 tests + 76 prior = 119 pass, 11 db-skip; ruff clean; CYCLE_LOG row 8 DONE; AUDIT_LOG appended; staging cycle files
---

# Cycle 8 in-progress state

DESIGN: EnrichmentStrategy ABC + registry + feature-flags + per-job cost guardrail + job state machine.
NOTE: `app/config.py` already exists as a module — cannot create `app/config/` package, so feature_flags land in `app/strategies/feature_flags.py` (cleaner cohesion with the registry anyway). All new code under app/strategies/ + app/jobs/. No migrations, no LLM, no model names.
