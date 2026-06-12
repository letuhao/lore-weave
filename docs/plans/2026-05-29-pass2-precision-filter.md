# Plan — Pass2 precision filter (cycle 72)

**Spec:** [docs/specs/2026-05-29-pass2-precision-filter.md](../specs/2026-05-29-pass2-precision-filter.md)
**Size:** XL (12 files: 4 NEW + 7 MODIFIED + 1 FIXTURE; ~6 logic blocks; 1 cross-cutting side effect = `Pass2Candidates` field addition)
**Sessions:** 2 (this DESIGN-CHECKPOINT session + 1 BUILD+VERIFY session, per `feedback_design_checkpoint_commit_separates_design_from_implementation`)
**Natural seam (per `feedback_xl_cycle_natural_checkpoint_pattern`):** between Phase 1 (isolated SDK foundation) and Phase 2 (orchestrator integration). Phase 1 ships as dead code (kwarg-defaults `None`); Phase 2 turns it on. If Session 2 hits fatigue mid-BUILD, Phase 1 can ship standalone.

## Session 1 — DESIGN-CHECKPOINT (this session)

Commits:
- `docs(spec): cycle 72 — pass2 precision filter [XL/DESIGN]`
- artifact: spec + plan only, NO code

Files touched:
- NEW [docs/specs/2026-05-29-pass2-precision-filter.md](../specs/2026-05-29-pass2-precision-filter.md) (CLARIFY + DESIGN + round-1 fold)
- NEW [docs/plans/2026-05-29-pass2-precision-filter.md](./2026-05-29-pass2-precision-filter.md) (this file)

End-of-session-1 state:
- `.workflow-state.json` at `commit` phase, ready for session-2 BUILD entry
- `docs/sessions/SESSION_HANDOFF.md` updated with session-1 outcome + session-2 entry-point

## Session 2 — BUILD + VERIFY + ship-or-revert

Six sub-phases sequenced for natural checkpoint resilience:

### Phase 1 — SDK foundation (isolated, no caller changes)

**Files:**
- NEW `sdks/python/loreweave_extraction/extractors/precision_filter_prompts.py` (HIGH-2 fold — single SOT for prompt + builder helper)
- NEW `sdks/python/loreweave_extraction/prompts/precision_filter_system.md` (prompt body, loaded by helper)
- NEW `sdks/python/loreweave_extraction/pass2_filter.py` (~320 lines per design)
- MODIFIED `sdks/python/loreweave_extraction/pass2.py` (Pass2Candidates extension only — adds `filter_status` / `filter_coverage` fields with default values; `extract_pass2` signature unchanged in Phase 1)
- MODIFIED `sdks/python/loreweave_extraction/__init__.py` (re-exports PrecisionFilterConfig, FilterStatus, apply_precision_filter, load_candidates_from_dump)
- NEW `sdks/python/tests/test_extraction/test_pass2_filter_unit.py` (~280 lines, all 11 unit tests per spec test plan)
- NEW `sdks/python/tests/test_extraction/test_precision_filter_prompts.py` (SOT regression — `_PRECISION_SYSTEM` imported in `llm_judge.py` matches `build_precision_prompt(suppress_thinking=True)` byte-for-byte)
- NEW FIXTURE `services/knowledge-service/tests/quality/eval_runs/c70a/` (copied from container `/tmp/eval_dump_cycle70/`)
- MODIFIED `services/knowledge-service/tests/quality/llm_judge.py` (1-line — import `_PRECISION_SYSTEM` from SDK helper)

**Verify gates:**
- `cd sdks/python && pytest tests/test_extraction/test_pass2_filter_unit.py -v` → 11/11 pass
- `cd sdks/python && pytest tests/test_extraction/test_precision_filter_prompts.py -v` → SOT regression passes (prompt strings byte-identical)
- `cd sdks/python && pytest tests/test_extraction/test_pass2.py -v` → unchanged result (Phase 1 only extends Pass2Candidates with default-value fields; existing tests untouched)
- `cd services/knowledge-service && pytest tests/unit/test_pass2_orchestrator.py -v` → unchanged result (orchestrator code not yet touched)
- Fixture verification: `ls services/knowledge-service/tests/quality/eval_runs/c70a/alice_ch01/actual.json` exists + 9 chapters present + `judge_ensemble_report.json` present

**Checkpoint commit candidate:** `feat(extraction): SDK pass2 precision filter foundation [XL/BUILD-1]`

Phase 1 ships as **dead code** — `apply_precision_filter` is callable from tests but no caller wires it in production. Session 2 can naturally checkpoint here if fatigue / context budget runs out; Phase 2 picks up in Session 3.

### Phase 2 — Orchestrator integration

**Files:**
- MODIFIED `sdks/python/loreweave_extraction/pass2.py` (add `precision_filter: PrecisionFilterConfig | None = None` kwarg + `on_filter_decision` kwarg; when non-None, call `apply_precision_filter` after gather)
- MODIFIED `sdks/python/tests/test_extraction/test_pass2.py` (add 4 tests per spec test plan — `test_precision_filter_none_zero_behavior_change`, `test_precision_filter_set_chains_filter_call`, `test_filter_status_field_populated_correctly_per_status`, `test_filter_coverage_populated_per_category`)
- MODIFIED `services/worker-ai/app/runner.py` (read `WORKER_AI_PRECISION_FILTER_MODEL_REF` + `WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY` envs at startup → cached in `PrecisionFilterConfig` instance; passed to `extract_pass2(...)`)
- MODIFIED `services/worker-ai/tests/test_runner.py` (3 regression-lock tests per spec)
- MODIFIED `services/knowledge-service/app/extraction/pass2_orchestrator.py` (add `_maybe_apply_precision_filter` helper + call between gather and write in `_run_pipeline`)
- MODIFIED `services/knowledge-service/tests/unit/test_pass2_orchestrator.py` (4 regression-lock tests per spec)
- MODIFIED `services/knowledge-service/app/metrics.py` (new counter `knowledge_extraction_filter_decisions_total{category, verdict}` + gauge `knowledge_extraction_filter_coverage_ratio{category}`)

**Verify gates:**
- `cd sdks/python && pytest tests/test_extraction/test_pass2.py -v` → 4 new tests pass + all existing tests pass (regression-lock)
- `cd services/worker-ai && pytest tests/test_runner.py -v` → 3 new tests pass + all existing tests pass
- `cd services/knowledge-service && pytest tests/unit/test_pass2_orchestrator.py -v` → 4 new tests pass + all existing tests pass
- Grep audit per memory `audit-all-callsites-when-adding-optional-kwarg`: `grep -rn 'extract_pass2(' --include='*.py'` shows 5 hits (1 SDK + 1 SDK test + 1 worker-ai + 1 worker-ai test + 1 knowledge-service test). All ≥1 hit per file has been touched in this phase OR earlier — no orphan call site.

**Checkpoint commit candidate:** `feat(extraction): wire precision filter into pass2 orchestrator + callers [XL/BUILD-2]`

### Phase 3 — Eval validation (the ship test)

**Files (new artifacts under `services/knowledge-service/tests/quality/eval_runs/c72/`):**
- NEW `extraction_dump_c72b/` — c70a Pass A + filter (keep partial)
- NEW `extraction_dump_c72c/` — c70a Pass A + filter (drop partial)
- NEW `judge_ensemble_report_c72b.json`
- NEW `judge_ensemble_report_c72c.json`
- NEW `c72_compare.md` — narrative comparison of c70a-saved vs c72b vs c72c, explicit print of all 4 D10 gates

**Execution steps (script-based, no new code files):**

1. Verify fixture: `ls services/knowledge-service/tests/quality/eval_runs/c70a/judge_ensemble_report.json` — must exist (Phase 1 copy)
2. Filter Pass on c70a → c72b:
   ```bash
   docker exec infra-knowledge-service-1 python -c "
     from pathlib import Path
     from loreweave_extraction.pass2_filter import apply_precision_filter, load_candidates_from_dump, PrecisionFilterConfig
     # ... wire LLMClient + run per-chapter filter + dump filtered actual.json
   "
   ```
3. Run ensemble judge on c72b filtered dump (reuses existing `tests/quality/test_judge_eval.py --run-quality` path with `KNOWLEDGE_JUDGE_DUMP_PATH=tests/quality/eval_runs/c72/extraction_dump_c72b`)
4. Same for c72c with `partial_policy="drop"`
5. Generate `c72_compare.md` with delta table + D10 4-clause gate evaluation

**Verify gates (the ship test):**
- c72b ensemble report `judge_status="complete"` across all 3 judges
- c72c ensemble report same
- D10 gate (a) median F1 lift ≥ +1.5pp **OR** documented NEGATIVE if not met
- D10 gate (b) min F1 lift ≥ -0.5pp
- D10 gate (c) claude lift ≤ 2× median
- D10 gate (d) Fleiss κ ≥ 0.60
- `c72_compare.md` prints all 4 gates with PASS/FAIL per variant + recommended ship variant

**Live-smoke evidence (per CLAUDE.md Phase 6 cross-service requirement, 4-service touch: worker-ai + knowledge-service + provider-registry + LM Studio):**
- After Phase 2 + before Phase 3: `docker exec infra-worker-ai-1 ...` ad-hoc test that triggers ONE filter call end-to-end on a small synthetic input. Confirm filter_status="applied" + coverage > 0 in the resulting Pass2Candidates. Captured as: `live smoke: c72 precision filter end-to-end via worker-ai+knowledge-service+gateway+lm-studio, filter_status=applied coverage_avg=0.XX`.

**Checkpoint commit candidate:** `eval(c72): run pass2 precision filter validation cycle [XL/BUILD-3]` (or NEGATIVE-shape commit `eval(c72): pass2 precision filter NEGATIVE cycle (reverted) [XL]`)

### Phase 4 — Calibration step (per LOW-1 fold)

**Only triggers if c72b/c72c initial run shows `filter_coverage < 0.9` on any category.**

Action: retune `PrecisionFilterConfig.max_items_per_batch` (try 2 → 1) + `KNOWLEDGE_JUDGE_PER_ITEM_TOKENS` per memory `local-llm-first`. Re-run Phase 3 with retuned config. Document calibration outcome in `c72_compare.md`.

If 2+ retunes still show low coverage → document as MED concern in c72_compare + still ship (coverage is a quality signal, not a hard gate) OR defer ship + open `D-PASS2-FILTER-BATCH-CALIBRATION` for separate cycle.

### Phase 5 — REVIEW (code, 2-stage) + /review-impl round 2

Per CLAUDE.md Phase 7 + memory `review-impl-on-design-cycles`:

**Stage 1 — spec compliance:**
- Every spec interface implemented? `apply_precision_filter` signature matches D5/Module map exactly?
- All 23 test cases in spec test plan (19 original + 4 round-1-added) actually exist?
- Pass2Candidates extension matches design (`filter_status`, `filter_coverage` fields + defaults)?
- Cross-judge gate (a/b/c/d) explicitly printed in c72_compare?

**Stage 2 — code quality:**
- Adversarial: what does the test plan MISS? Run /review-impl round 2 on the BUILD diff (not just spec). Likely findings: error path on `LLMClient` connect refused (filter degraded check), pydantic v1 vs v2 `.model_dump()` compat with current pyproject, `dict[str, float]` vs `dict[Category, float]` typing tightness, race condition in 3-category gather if one category's filter call blocks LM Studio.
- Patterns: filter logging at INFO level for "applied"/"degraded" — is that too noisy?
- Security: filter calls into LLMClient → LLM gets the candidate strings. Filter prompt's text input has been through `_sanitize` already (pass2_orchestrator side)? Or only post-write?
- A11y: N/A
- Performance: 3-category gather concurrent? Memory pressure on 50-relation chapter (50 verdicts × 3 categories × ~60 tokens = ~9KB just verdict text — trivial). Latency budget held?

**Stage 1 + Stage 2 fixes → re-VERIFY → continue.**

### Phase 6 — QC

Per CLAUDE.md Phase 8: scope-guard final gate. Confirm:
- No scope creep beyond D2's "entity/relation/event filter" target (no fact filter accidentally landed)
- No production behavior change when envs unset (regression-lock tests verify)
- Filter degraded path never raises ExtractionError into caller's retry budget
- AMAW NOT enabled this cycle (deliberate; XL but standard workflow per CLAUDE.md L+ recommendation; this cycle's risk is well-bounded)

### Phase 7 — POST-REVIEW (Human-Interactive Checkpoint)

Per CLAUDE.md Phase 9 + memory `post-review-rubber-stamp-trap`:
- Present concise summary + D10 4-clause gate results
- STOP and WAIT for human
- If human approves: SESSION + COMMIT
- If human asks deeper: `/review-impl` round 3 first (per memory `review-impl-round-3-on-fix-delta`)

**Proactively suggest /review-impl IF:** filter degraded path was exercised (auth/error boundary), OR cross-judge gate fired marginally (within +0.3pp of threshold), OR fixture-source dump turned out to lack a chapter we expected.

### Phase 8 — SESSION + COMMIT + RETRO

Per CLAUDE.md Phases 10-12:
- Update `docs/sessions/SESSION_HANDOFF.md` with session-2 outcome + cycle-72 closing summary
- Update `docs/sessions/SESSION_PATCH.md` if cycle materially shifted module status
- Move any cleared deferrals to "Recently cleared"
- Commit per-phase: separate commits for Phase 1 / Phase 2 / Phase 3 ship-or-NEGATIVE artifacts (3-5 commits total, per `feedback_xl_cycle_natural_checkpoint_pattern`)
- RETRO: capture lessons via `add_lesson` to ContextHub MCP IF non-obvious decisions surfaced. Likely lessons (a priori):
  - "Promote eval-side helpers to SDK when production wants them" — pattern (HIGH-2 fold)
  - "Saved-dump fixture eliminates extraction nondeterminism in A/B" — pattern (HIGH-1 fold)
  - "Cross-judge gate must be symmetric (anti-self-reinforcement)" — pattern (MED-2 fold)
  - "Filter-output F1 ≠ writer-realized F1; document the gap" — pattern (MED-3 fold)

## Risk → mitigation → test mapping (cross-checked, end-to-end)

| Spec risk | Phase | Mitigation | Test |
|---|---|---|---|
| HIGH-1 (self-reinforcement) | 3 | D10 gate (c) claude ≤ 2× median | c72_compare prints + asserts |
| HIGH-2 (filter latency in prod) | 2 | env-opt-in default off | `test_runner.py::test_runner_env_unset_skips_filter` |
| MED-1 (`partial_policy="demote"`) | 1 | `__post_init__` raises | `test_pass2_filter_unit.py::test_demote_raises_not_implemented_in_post_init` |
| MED-2 (filter degraded invisible) | 1 | `filter_status` field | `test_filter_status_field_populated_correctly_per_status` |
| MED-4 (`extract_pass2` bypass) | 2 | Option B post-gather step | `test_pass2_orchestrator.py::test_orchestrator_env_set_calls_filter_post_gather_pre_write` |
| MED-6 (prompt SOT drift) | 1 | builder helper + regression test | `test_precision_filter_prompts.py::test_sdk_prompt_matches_llm_judge_import` |
| MED-7 (3-category serial latency) | 1 | `asyncio.gather` across categories | `test_pass2_filter_unit.py::test_three_categories_run_concurrently_in_gather` |
| LOW-1 (coverage <1.0 underapplied) | 1 | coverage field + partial_policy default | `test_coverage_lt_1_partial_policy_applied_to_unjudged` |
| LOW-3 (filter on entity wasteful) | 4 | empirical-driven default tune | c72_compare per-category lift table |
| Round-1 HIGH-1 (re-extract nondeterminism) | 3 | c70a saved-dump fixture | fixture exists + Phase 1 verify gate |
| Round-1 HIGH-2 (`_NO_THINK_PREFIX` missed) | 1 | builder helper migrates both | `test_precision_filter_prompts.py` |
| Round-1 MED-1 (pydantic→dict adapter) | 1 | `model_dump` at filter boundary | `test_pydantic_model_to_judge_format_adapter` |
| Round-1 MED-2 (qwen-30b gate too strict) | 3 | 4-clause symmetric gate | c72_compare prints all 4 gates |
| Round-1 MED-3 (measurement validity) | 3 | caveat in c72_compare | manual reviewer reads c72_compare |
| Round-1 MED-4 (mutable Pass2Candidates) | 1 | `dataclasses.replace` contract | `test_filter_never_mutates_input_instance` |

## Out of scope (deferred items written to SESSION_HANDOFF on session-2 ship/revert)

- **D-PASS2-FILTER-NEO4J-REALIZED-F1** — Neo4j-realized F1 measurement (separate cycle after writer cascade is profiled)
- **D-PASS2-FILTER-FACTS-SUPPORT** — extend filter to facts (per LOW-2 fold)
- **D-PASS2-FILTER-CLOUD-CALIBRATION** — cloud claude-haiku-4-5 calibration (per spec non-goal)
- **D-PASS2-FILTER-RUNTIME-FLAG** — per-request header override (per spec non-goal)
- **D-PASS2-FILTER-CACHE** — `(text_hash, model_ref, item_canonical) → verdict` cache (per spec non-goal)
- **D-PASS2-FILTER-PER-USER-UI** — surface filter toggle in UI (per spec non-goal)

## Session-end expectations

| Session | Output | Commits |
|---|---|---|
| 1 (this) | spec + plan + design-checkpoint commit | 1 (no code) |
| 2 | Phase 1+2+3 ship-or-revert | 3-5 commits depending on phase split |

If c72b OR c72c ships → 4-5 commits (Phase 1, Phase 2, Phase 3 eval data, ship enablement (default env), SESSION update).
If NEGATIVE → 3 commits (Phase 1 keeps SDK, Phase 2 reverted, Phase 3 NEGATIVE doc commit, SESSION update). Per cycle 71/71-bis pattern.

---

**Plan status:** ready for design-checkpoint commit. PLAN complete.
