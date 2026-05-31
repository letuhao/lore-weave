# Plan — Pass2 writer auto-create (cycle 73e)

**Cycle:** 73e — D-PASS2-WRITER-CASCADE-GAP-CLOSE option (b)
**Size:** L (10 files: 6 MODIFY + 3 NEW + 1 compose; ~5 logic blocks; 1 side effect = Neo4j entity property + optional auto-create writes)
**Session:** 1 (single-session BUILD-VERIFY-SHIP per L-cycle workflow)
**Workflow mode:** v2.2 default (no AMAW)

## Goal

Close the baseline 10.7% writer-cascade gap (c73c finding) by auto-creating `:Entity` nodes at Pass2 write time for unresolved relation subjects/objects. Two-tier strategy:

- **Tier A** (free): in-memory canonical-name match against chapter's `entity_list`. Repairs cases where relation subject name matches an extracted entity but IDs don't (kind-mismatch, etc.).
- **Tier B** (env-gated): when STILL unresolved, MERGE a new `:Entity` node with `kind="concept"`, `auto_created=true`, `confidence=min(rel.confidence, 0.3)`.

No LLM in path → no self-reinforcement risk (cycle 73d blocker bypassed by construction).

## Phase 1 — Schema + entity-layer changes (low risk)

**Files:**
- MODIFY `services/knowledge-service/app/db/neo4j_repos/entities.py`
  - ADD `auto_created: bool = False` kwarg to `merge_entity` + `merge_entity_at_id`
  - ADD `e.auto_created = $auto_created` to `_MERGE_ENTITY_CYPHER` ON CREATE
  - ADD ON MATCH CASE clause: `e.auto_created = CASE WHEN $auto_created = false THEN false ELSE coalesce(e.auto_created, false) END` (M1 — promotion semantics)
  - ADD header comment: "Read sites MUST use `coalesce(e.auto_created, false)` — legacy nodes lack the property." (M2)
- MODIFY `services/knowledge-service/app/extraction/entity_resolver.py`
  - ADD `auto_created: bool = False` kwarg to `resolve_or_merge_entity`
  - Plumb to `merge_entity` + `merge_entity_at_id` calls

**Verify gates:**
- `pytest services/knowledge-service/tests/unit/test_entities.py -v` → all existing pass + 2 new tests:
  - `test_merge_entity_auto_created_true_sets_property_on_create`
  - `test_merge_entity_auto_created_false_clears_property_on_match` (M1 promotion regression-lock)
- `pytest services/knowledge-service/tests/unit/test_entity_resolver.py -v` → all existing pass

**Checkpoint commit candidate:** `feat(entities): add auto_created property + promotion semantics [L/BUILD-1]`

## Phase 2 — Writer logic (Tier A + Tier B)

**Files:**
- MODIFY `services/knowledge-service/app/extraction/pass2_writer.py`
  - ADD `autocreate_enabled: bool = False`, `autocreate_max: int | None = None` kwargs to `write_pass2_extraction`
  - ADD `entities_autocreated: int = 0`, `endpoints_repaired_by_name: int = 0` fields to `Pass2WriteResult`
  - In Step 2 entity loop: build `chapter_entity_by_canonical_name: dict[str, list[tuple[str, str]]]` keyed by `canonicalize_entity_name(name)` → list of `(kind, entity_id)` (H1 — multi-kind aware)
  - In Step 3 relation loop, BEFORE existing cascade-skip:
    - **Tier A.1** (chapter map): if subject_id missing/unmerged AND `canon_subj` in chapter map AND `len(candidates) == 1` → repair `rel.subject_id`, emit `outcome="tier_a_name_repair"`
    - **Tier A.1 ambiguous**: if `len(candidates) > 1` → emit `outcome="kind_ambiguous"`, cascade-skip (skip BOTH Tier A.2 and Tier B — pollution defense)
    - **Tier A.2** (anchor map): if still unresolved AND anchor_index has match → repair, emit `outcome="tier_a_anchor_repair"` (NOT `tier_b_autocreated` — anchor existed pre-write per H4)
    - **Tier B** (autocreate): if still unresolved AND `autocreate_enabled` AND `budget > 0`:
      - Pre-check `_is_noise_subject(rel.subject)` → if True, emit `outcome="noise_skipped"`, cascade-skip (H2)
      - Pre-check `canonicalize_entity_name(name)` empty → emit `outcome="invalid_name"`, cascade-skip (M6)
      - Try `resolve_or_merge_entity(name, kind="concept", confidence=min(rel.confidence, 0.3), auto_created=True)` (H3)
      - On success: add to `merged_entity_ids` + chapter map; emit `outcome="tier_b_autocreated"`; `entities_autocreated += 1`; decrement budget
      - On exception: emit `outcome="error"`, log warning, cascade-skip (M3, M5)
      - On cap exhausted: emit `outcome="cap_exhausted"` (+ `cap_exhausted_high_conf` if `rel.confidence > 0.8` per H5)
  - Repeat the same Tier A.1 / A.2 / B for `rel.object` / `rel.object_id`
  - Add header comment on Tx boundary + concurrency safety (M5, L5)
- MODIFY `services/knowledge-service/app/metrics.py`
  - NEW counter `knowledge_extraction_writer_autocreate_total{role, outcome}`
  - Outcomes enum: `tier_a_name_repair | tier_a_anchor_repair | tier_b_autocreated | kind_ambiguous | noise_skipped | cap_exhausted | cap_exhausted_high_conf | invalid_name | error`
  - Roles: `subject | object`

**Verify gates:**
- `pytest services/knowledge-service/tests/unit/test_pass2_writer.py -v` → all existing pass + 14 new tests per DESIGN test plan
- `pytest services/knowledge-service/tests/ -v -k "writer or autocreate"` → no cross-module breakage
- Grep audit per memory `feedback_audit_all_callsites_when_adding_optional_kwarg`:
  - `grep -rn 'write_pass2_extraction(' --include='*.py'` → enumerate every call site; verify none break with new kwarg defaults

**Checkpoint commit candidate:** `feat(pass2-writer): tier-A name repair + tier-B autocreate (env-gated, default off) [L/BUILD-2]`

## Phase 3 — Orchestrator wiring + compose envs

**Files:**
- MODIFY `services/knowledge-service/app/extraction/pass2_orchestrator.py`
  - NEW `_load_writer_autocreate_config()` returns `{'enabled': bool, 'max': int|None}`
  - Reads `KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED` (default `false`) + `KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER` (default `20`)
  - Spread into `write_pass2_extraction(autocreate_enabled=..., autocreate_max=...)`
- MODIFY `services/knowledge-service/tests/unit/test_pass2_orchestrator.py`
  - 2 new env-loader regression-lock tests:
    - `test_writer_autocreate_env_unset_disables_default_false_none`
    - `test_writer_autocreate_env_set_enables_with_cap`
- MODIFY `infra/docker-compose.yml`
  - knowledge-service service block: ADD 2 envs default-off:
    ```yaml
    KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED: ${KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED:-false}
    KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER: ${KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER:-20}
    ```
  - worker-ai NOT touched (worker-ai doesn't call writer directly per design module map)

**Verify gates:**
- `pytest services/knowledge-service/tests/unit/test_pass2_orchestrator.py -v` → all existing pass + 2 new
- Stack-up smoke (`docker compose up -d`): knowledge-service comes up healthy with new envs defaulted to OFF; no behavior change vs c73b-drop

**Checkpoint commit candidate:** `feat(extraction+infra): wire writer autocreate to orchestrator + compose (default off) [L/BUILD-3]`

## Phase 4 — Eval validation (the ship test)

**Files (eval artifacts under `services/knowledge-service/tests/quality/eval_runs/c73e/`):**
- NEW `services/knowledge-service/tests/quality/run_c73e_writer_autocreate.py` (eval driver)
- NEW `eval_runs/c73e-autocreate-off/` — c73b-drop dump + writer-cascade (autocreate OFF) → realized actual.json
- NEW `eval_runs/c73e-autocreate-on/` — c73b-drop dump + writer-cascade (autocreate ON, cap=20) → realized actual.json
- NEW `eval_runs/c73e_compare.md` — full D10 5-clause gate evaluation + per-tier outcome breakdown

**Execution steps (script-based, no new code):**
1. Verify fixture: `ls eval_runs/c73b-drop/` exists (c73b filter dump from prior cycle)
2. Run `run_c73e_writer_autocreate.py` with `KNOWLEDGE_C73E_VARIANT=c73e-autocreate-off` → simulates writer with autocreate OFF; outputs realized dump
3. Run with `KNOWLEDGE_C73E_VARIANT=c73e-autocreate-on` + cap=20 → simulates writer with autocreate ON; outputs realized dump + per-chapter outcome stats
4. Run 3-judge ensemble on both variants (reuses `test_judge_eval.py --run-quality` with `KNOWLEDGE_JUDGE_DUMP_PATH=eval_runs/c73e-autocreate-{off,on}`)
5. Generate `c73e_compare.md` with:
   - Per-variant realized F1 (3-judge median + per-judge breakdown)
   - 2-judge subset (no claude) F1 for vestigial D10(c) sanity
   - Per-tier outcome counts (how many tier_a_name_repair / tier_b_autocreated / kind_ambiguous / noise_skipped per chapter)
   - D10 5-clause gate PASS/FAIL per clause + final ship verdict

**Verify gates (the ship test):**
- D10(a) realized RELATION-ONLY F1 lift ≥ +0.5pp vs c73b-drop relation-only baseline OR documented NEGATIVE
- D10(b) min judge F1 lift ≥ -0.5pp
- D10(c) 2-judge subset lift ≥ +0.3pp (vestigial — sanity check)
- D10(d) Fleiss κ ≥ 0.60
- D10(e) entity F1 regression ≤ -0.3pp AND event F1 regression ≤ -0.3pp (anti-pollution gate per H3/M7)
- `c73e_compare.md` prints all 5 gates + recommended ship verdict (activate default-on / opt-in SDK only / revert)

**Live-smoke evidence (per CLAUDE.md Phase 6 — single-service writer change, no cross-service touch):**
- Single-service change (knowledge-service only); no live-smoke required by autodetect
- BUT spawn a small synthetic chapter extraction via `docker exec` to confirm end-to-end runtime behavior: build small `LLMRelationCandidate` with unresolved subject, call writer with autocreate_enabled=True, assert entity auto-created in Neo4j with `auto_created=true`
- Captured as: `live smoke: c73e writer autocreate end-to-end via knowledge-service, entities_autocreated=1 endpoint=subject outcome=tier_b_autocreated`

**Checkpoint commit candidate:** `eval(c73e): pass2 writer autocreate validation cycle [L/BUILD-4]` OR `eval(c73e): pass2 writer autocreate NEGATIVE cycle (SDK opt-in only) [L]`

## Phase 5 — REVIEW (code, 2-stage) + /review-impl round 2

Per CLAUDE.md Phase 7 + memory `feedback_review_impl_on_design_cycles`:

**Stage 1 — spec compliance:**
- Every CLARIFY decision D1-D12 implemented? (env-gate D1, name source D2, kind=concept D3, cap D4, anchor reuse D5, marker D6, no quarantine D7, telemetry D8, fail-soft D9, ship gate D10, c73b dump eval D11, default-off D12)
- All 14 unit tests + 2 env-loader tests exist?
- Tier A.1 (chapter) + A.2 (anchor) + B (autocreate) all coded with distinct metric outcomes?
- 9-outcome metric label enum implemented + tested?
- Pass2WriteResult new fields (`entities_autocreated`, `endpoints_repaired_by_name`) included?

**Stage 2 — code quality (/review-impl round 2 on BUILD diff):**
- Likely findings (a priori): Tier A.1 + A.2 split correctness, autocreate failure mode on partial subject/object success, Cypher promotion CASE logic, chapter_entity_by_canonical_name map population timing (must be IN STEP 2 loop, not after, to preserve entity ordering for kind selection)
- Patterns: log levels (autocreate at INFO, error at WARNING)
- Security: subject/object names go through `_sanitize` before merge_entity? (existing path does for entities; verify for autocreate path)
- Performance: 9-outcome metric label cardinality is bounded (manageable); no extra Cypher queries per relation in Tier A (in-memory map)
- Edge cases: relation with subject_id set but pointing to STALE id (from prior chapter cached?) → existing `not in merged_entity_ids` check catches; new test in Phase 2 (L3)

**Stage 1 + Stage 2 fixes → re-VERIFY → continue.**

## Phase 6 — QC

Per CLAUDE.md Phase 8: scope-guard final gate. Confirm:
- No scope creep beyond D-PASS2-WRITER-CASCADE-GAP-CLOSE option (b) target (no Tier-A-only or filter-side changes accidentally landed)
- No production behavior change when envs unset (regression-lock tests verify)
- Autocreate failure path never raises into orchestrator's retry budget (per D9)
- AMAW NOT enabled this cycle (single-service, well-bounded, deterministic logic)

## Phase 7 — POST-REVIEW (Human-Interactive Checkpoint)

Per CLAUDE.md Phase 9 + memory `feedback_review_impl_round_3_on_fix_delta`:
- Present concise summary + D10 5-clause gate results
- STOP and WAIT for human
- If human approves: SESSION + COMMIT
- If human asks deeper: `/review-impl` round 3 on fix delta first

**Proactively suggest /review-impl round 3 IF:** any Cypher change in Phase 1 produces non-trivial promotion-CASE logic OR multiple HIGHs surfaced in /review-impl round 2 OR per-tier eval numbers don't match expectation.

## Phase 8 — SESSION + COMMIT + RETRO

Per CLAUDE.md Phases 10-12:
- Update `docs/sessions/SESSION_HANDOFF.md` with cycle-73e outcome
- Update `docs/sessions/SESSION_PATCH.md` if cycle materially shifts module status (probably not — additive feature)
- Move cleared D-PASS2-WRITER-CASCADE-GAP-CLOSE deferral to "Recently cleared"
- Commits per-phase: 3-4 commits expected
  - Phase 1 schema (`auto_created` property)
  - Phase 2 writer logic (Tier A + Tier B)
  - Phase 3 + 4 wiring + eval combined
  - SHIP commit (activation decision + handoff update)
- RETRO: capture lessons via `add_lesson` IF non-obvious decisions surfaced. Likely lessons:
  - "Two-tier free-repair + opt-in autocreate pattern for cascade-gap closure" (H1/H4 generalizes)
  - "ON MATCH promotion semantics for marker properties" (M1)
  - "Char-length + word-count combined heuristic for multilingual noise filter" (H2)

## Risk → mitigation → test mapping

| Spec risk | Phase | Mitigation | Test |
|---|---|---|---|
| H1 — kind-collision wrong repair | 2 | Map keyed by canonical_name → list of (kind, eid); skip if multi-kind | `test_tier_a_repair_skipped_on_kind_ambiguity` |
| H2 — word-count broken for CJK | 2 | char-length 60 + word-count 4 combined heuristic | `test_noise_heuristic_handles_cjk_long_string` |
| H3 — hardcoded concept+0.0 pollutes | 2 | confidence floor from `rel.confidence` | `test_tier_b_autocreate_confidence_floored_from_relation_confidence` |
| H4 — anchor-hit silently marked auto | 2 | Tier A.2 anchor pre-check separate from Tier B | `test_tier_a_anchor_hit_uses_repaired_by_anchor_outcome_not_autocreate` |
| H5 — cap eats budget high-conf | 2 | Relations already sorted desc-confidence; metric `cap_exhausted_high_conf` for tuning | `test_autocreate_per_chapter_cap_exhausted` |
| M1 — ON MATCH never clears | 1 | CASE clause clears on `auto_created=false` write | `test_merge_entity_auto_created_false_clears_property_on_match` |
| M2 — read-path coalesce missing | 1 | Header comment + regression-lock test | `test_legacy_entity_without_auto_created_property_returns_via_coalesce_query` |
| M3 — `error` outcome missing | 2 | Added to outcome enum | `test_autocreate_failure_logs_warning_emits_error_outcome` |
| M5 — Tx boundary ambiguous | 2 | Doc comment in writer header | (manual confirm in /review-impl round 2) |
| M6 — empty canonical → error | 2 | Pre-check + `invalid_name` outcome | `test_invalid_name_outcome_for_empty_canonical` |
| M7 — eval gate too permissive | 4 | D10 5-clause with (e) per-category regression cap | `c73e_compare.md` prints all 5 clauses |
| L3 — both endpoints autocreate | 2 | Both subject + object run independent autocreate | `test_both_subject_and_object_need_autocreate_in_same_relation` |

## Out of scope (deferred items written to SESSION_HANDOFF on session ship/revert)

- **D-PASS2-WRITER-AUTOCREATE-FE-CLEANUP** — UI surface for reviewing auto-created entities (depends on D6 marker + this cycle's ship)
- **D-PASS2-WRITER-AUTOCREATE-PROMOTION-WORKFLOW** — explicit user-promote-to-confirmed workflow (auto-promote on legit re-extraction works via M1 fix; explicit confirm UI is separate)
- **D-PASS2-WRITER-AUTOCREATE-WORKER-AI** — port env loader to worker-ai if/when worker calls writer directly (currently doesn't)
- **D-PASS2-FILTER-FACTS-SUPPORT** — orthogonal cycle for facts category
- **Option (a) entity prompt to extract abstract subjects** — stacks with this cycle later; not exclusive
- **Option (c) pre-filter unresolved relations** — would duplicate cycle 72's filter step; wasteful

## Session-end expectations

| Phase | Output | Commit |
|---|---|---|
| 1 schema | entities.py + _MERGE_ENTITY_CYPHER + entity_resolver.py + 2 unit tests | 1 |
| 2 writer | pass2_writer.py + 14 unit tests + metrics.py counter | 1 |
| 3 wiring | pass2_orchestrator.py + 2 env-loader tests + docker-compose.yml | 1 |
| 4 eval | run_c73e_*.py + eval_runs/c73e/ + c73e_compare.md | 1 |
| 5-7 review/QC/post-review | (folded fixes if any) | 0-1 |
| 8 SESSION+SHIP+RETRO | SESSION_HANDOFF.md + memory anchors | 1 |

**Expected total:** 4-6 commits.

**Ship verdict shapes:**
- If D10 5/5 PASS → activate default-on in compose (single env flip) → 5-commit total
- If D10 partial PASS (e.g. (a)+(d) PASS, (e) FAIL) → ship SDK opt-in only, compose default OFF, document in c73e_compare → 4-commit total
- If D10 negative (a) FAIL → ship as documented NEGATIVE with c73e_compare explaining; SDK + counter still ship for future revisit → 4-commit total

---

**Plan status:** ready for BUILD phase.
