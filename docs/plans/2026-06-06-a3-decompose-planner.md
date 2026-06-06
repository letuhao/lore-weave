# A3 — `decompose` planner + adaptive K (BUILD PLAN)

> Spec: [`2026-06-06-a3-decompose-planner.md`](../specs/2026-06-06-a3-decompose-planner.md). XL · v2.2 · composition-only.
> This plan locks the interfaces so the BUILD session doesn't re-litigate them (design-checkpoint pattern).

## Build order (one milestone, internal sub-steps; single eval-gate + commit at the end)

### B1 — read surfaces + config (no behavior change)
- `BookClient.list_chapters(book_id, bearer) -> list[{chapter_id, title, sort_order}]` wrapping gateway `GET /v1/books/{book}/chapters` (ordered by sort_order). Graceful degrade → `[]` on error (like the other read methods).
- `config.py`: `plan_max_chapters: int = 40`, `plan_min_scenes_per_chapter: int = 1`, `plan_max_scenes_per_chapter: int = 6`, `plan_high_tension_threshold: int = 4`.
- Tests: client method (mock gateway), config defaults.

### B2 — adaptive K (small, independently testable)
- `engine/adaptive_k.py`: `adaptive_k(beat_role, tension, *, k_ceiling) -> int` + the closed `HIGH_WEIGHT_BEATS` set. Pure function.
- Wire into `routers/engine.py` auto path: `k = adaptive_k(node.beat_role, node.tension, k_ceiling=settings.compose_diverge_k)`; fallback to `compose_diverge_k` when both are None.
- **⚠ Compute `k` BEFORE the budget pre-check** (REVIEW design HIGH#1) and thread the SAME value into both the budget reservation and `select_draft(k=…)`. K now varies per scene; reserving at the old fixed-K site (after the check) would reserve the wrong amount.
- Tests: a TABLE of (beat_role, tension) → expected K incl. clamp + None-fallback (regression-lock the no-beat-role path = unchanged behavior); **a test asserting reserved-K == K-passed-to-diverge** (locks the ordering).

### B3 — the planner (`engine/plan.py`)
- Prompts: `build_chapter_map_messages(premise, beats, chapters)` (Level 1) + `build_scene_decompose_messages(premise, chapter_intent, beat, cast_roster)` (Level 2). Abstract, source-language-aware, NO English-only illustrative phrases (the CJK-bias lesson); examples symmetric/abstract.
- `decompose_chapter_map(...) -> list[ChapterPlan{chapter_id, beat_role, intent, unmapped_beats}]` (1 call, tolerant parse, every existing chapter present).
- `decompose_scenes(chapter_plan, cast, ...) -> list[ScenePlan{title, synopsis, tension, present_entity_ids, present_entity_names_unresolved, suggested_k}]` per chapter; bounded `asyncio.gather` over chapters (cap concurrency), per-chapter degrade.
- Cast name→id resolver (case/canonical match against the glossary roster; unmatched → `present_entity_names_unresolved`).
- Tests: Level-1 reconcile (B>C, B<C, B==C; no chapter dropped), Level-2 tolerant filter (malformed scene dropped, chapter keeps good), cast resolution (matched + unmatched), bounded fan-out.

> **/review-impl carry-ins (from the B1-B3 checkpoint review):**
> - **MUST (B4)** — enforce `plan_max_chapters` at the decompose endpoint BEFORE calling `plan.decompose` (refuse/clamp larger books with a clear error). `decompose` itself has no guard; a 500-chapter book would fire 500 L2 calls.
> - **Accepted/LOW** — `_resolve_cast` matches canonical glossary names only, not aliases (the L2 prompt constrains the model to the roster, so bounded); revisit if alias-named cast refs show up unresolved in the eval.
> - **Resolved at BUILD** — design HIGH#1 ("compute K before the budget reservation") was MOOT: there is no K-multiplied reservation in the auto path (only the K-independent prompt-size 413); adaptive K just derives-and-passes. The real bug found+fixed was a **tension SCALE mismatch** (adaptive_k/planner assumed 1-5; outline_node.tension is 0..100 per reasoning/policy `>=70`) — now aligned to 0..100, threshold 70, with an engine-level regression-lock.

### B4 — endpoints (`routers/plan.py` or extend `routers/outline.py`)
- `POST /works/{project_id}/outline/decompose` → preview tree (no persist).
- `POST /works/{project_id}/outline/decompose/commit` → persist arc+chapter+scene nodes (rank order; reuse `OutlineRepo.create_node` or a new `create_nodes_bulk`). Guards: `_require_work`, every `chapter_id` ∈ the book (IDOR), every `present_entity_id` a real glossary id, `replace` flag (default refuse double-plan).
- Pydantic request/response models (mode-enum / 422-pre-validate per the M6 lesson).
- Confirm gateway `pathFilter` proxies `/v1/composition/works/*/outline/*` (likely already; add a block only if missing — additive).
- Tests: preview shape, commit persists the right kinds/fields (beat_role on scene only; chapter_id set), IDOR reject, replace-guard, present_entity validation.

> **/review-impl carry-ins (from the B4 endpoints review):**
> - **D-A3-COMMIT-TRUE-REPLACE (deferred)** — the commit `force` flag adds scenes ALONGSIDE existing ones; it does NOT replace. True replace (archive the prior decomposed subtree before adding) needs its own design (what to archive: manual vs prior-decompose scenes). Renamed `replace`→`force` so the name is honest meanwhile.
> - **D-A3-COMMIT-IDEMPOTENCY (deferred, MED)** — commit has no idempotency_key; a double-submit with `force=true` duplicates the whole tree. `/generate` has a key; revisit if the FE surfaces double-submit.
> - **B5 MUST live-smoke the repo persistence** — `create_decomposed_tree` + `existing_scene_chapter_ids` are router-stub-tested only (no unit/integration coverage of the real atomic insert / replace-guard query); the B5 `decompose → commit → generate` run is their first real exercise.

### B5 — eval + VERIFY
- `scripts/eval_a3_decompose.py` (host-orchestrated, mirrors `eval_a1_diverge.py`): A3 (decompose→commit→generate, adaptive K) vs A1 (bare outline, fixed K) on coherence + outline-relevance medians; report wall-clock + total K spend.
- **Live cross-process token** at VERIFY (composition + glossary + book + provider-registry): `live smoke: eval_a3_decompose …`. Run on a seeded book with real chapters + a small cast.
- **Eval-gate:** ship only if A3 coherence ≥ A1 (or a clear outline-relevance lift if coherence saturates — the A1 saturation lesson). If it loses, STOP + rethink before commit (validate-first).

## Sequencing
B1 → B2 → B3 → B4 → B5(eval-gate) → REVIEW(code) → /review-impl (planner prompts, reconcile policy, IDOR/commit guards are load-bearing) → QC → POST-REVIEW → SESSION → COMMIT → RETRO.
**Natural mid-BUILD checkpoint** (XL-checkpoint lesson): B1–B3 are isolated foundation (client/config/pure-planner, no API surface); B4–B5 are the integration (endpoints + eval). Offer a checkpoint at the B3/B4 seam if the session runs long.

## Locked interfaces (do not re-litigate in BUILD)
- Committed tree = `arc → chapter(chapter_id, beat in title/goal) → scene(beat_role, tension, intent, present_entity_ids)`; beat_role lives on **scenes**.
- decompose = read-only over EXISTING book chapters; **never creates book chapters**.
- preview ≠ persist; commit is the only writer; `replace` guards double-plan.
- adaptive K = `f(tension primary, beat_role secondary)`, clamped `[1, compose_diverge_k]`, None→ceiling fallback.
- planner emits per-scene tension (1–5); cast resolved name→glossary-id, unmatched surfaced not dropped-silently.

## Out of scope (Phase B / later)
- FE for the planner (preview/edit/commit UI) — BE + eval only this milestone (mirrors A1/A2 → A2-S4 FE follow-up).
- Deeper beat-level decompose (scene→beats), recipe `operators`/constraints, the `narrative_thread` ledger (§4/§5 Phase B).
- Creating book chapters from the plan (the cross-service alternative the PO declined).
