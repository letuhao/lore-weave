# Wave-2 RECONCILE — ownership map, frozen seams, batching

> **Date:** 2026-06-27 · Branch `feat/narrative-pattern-library` · Follows Wave-1
> (W1–W7 built + merged + R-NODE-P1 verified). This is the Wave-2 parallelization
> contract — the analogue of `F0-foundation.md` + `00-RECONCILE.md` for Wave 2.
> Authoritative spec sections: **§12** (arc + import/deconstruct), **§13** (MCP),
> **§14** (conformance), **§17** (stitch). Master-plan §5 has the one-line WS rows.

## §0 The survey insight that reshapes Wave 2

The W-tier MCP tools (`composition_motif_mine`, `composition_arc_import_analyze`,
`composition_conformance_run`) **already exist and already enqueue worker jobs** via
their Tier-W confirm effects in [`routers/actions.py`](../../../services/composition-service/app/routers/actions.py)
(`_execute_motif_mine` / `_execute_arc_import` / `_execute_conformance_run`). The jobs
land `pending` and the only gap is the **worker handler**. So Wave-2's compute
workstreams are "fill the worker op behind an already-frozen MCP/confirm contract",
not "design new surfaces".

This means the real disjointness hazard is the **worker-dispatch trio** — three WSs
(W8 mine, W9 import, W5 conformance-wiring) would each edit
`worker/constants.py` (`SUPPORTED_OPERATIONS`) **and** `worker/job_consumer.py`
(`_run_operation`). That is a 3-way conflict (Wave 1 only ever had a 2-way `main.py`
union). **W2-F0 freezes that seam once** (below) so each WS only fills its own engine
module.

## §1 W2-F0 — Wave-2 foundation (LANDED FIRST, then FROZEN)

Mirrors F0: freeze the shared seams once, serially, then fan out. W2-F0 touches **only**
shared files; every WS body lives in a disjoint, WS-owned module.

**Delivered (commit on this branch):**
- `worker/constants.py` — `mine_motifs`, `analyze_reference`, `conformance_run` added to
  `SUPPORTED_OPERATIONS` (recognized + retryable).
- `worker/job_consumer.py` `_run_operation` — three dispatch branches, each **lazy-importing**
  its WS-owned engine-module entrypoint (keeps the worker top-level import surface small +
  the seam frozen).
- Three **stub engine modules** (each is the SOLE file its WS fills — the dispatch is frozen):
  - `engine/motif_mine.py` → `run_mine_motifs(pool, llm, knowledge, *, user_id, input)` — **W8**
  - `engine/motif_deconstruct.py` → `run_analyze_reference(pool, llm, *, user_id, input)` — **W9**
  - `engine/motif_conformance_run.py` → `run_conformance_run(pool, llm, knowledge, *, user_id, project_id, input)` — **W5-wiring**
  - Each stub raises a tracked `ValueError` (a TERMINAL business error → clean job-failed,
    no infra redeliver loop) until its WS lands the compute.
- `config.py` — all Wave-2 knobs added (cost estimates + `motif_mine_extractor_version` /
  `motif_mine_min_support`) so **no WS edits config.py**.
- `tests/test_wave2_worker_seam.py` — the freeze test (ops recognized + drivable; dispatch
  routes each op to its module; stub → terminal business fail).

**FROZEN worker-op input envelopes** (stamped by the confirm effects — a WS consumes, never redefines):

| op | input (besides `worker_op`) | ids off the job row |
|---|---|---|
| `mine_motifs` | `scope`('book'\|'corpus'), `book_id?`, `min_support?`, `promote_to?`, `language?` | `user_id` |
| `analyze_reference` | `import_source_id`, `use_web?`, `arc_hint?` | `user_id` |
| `conformance_run` | `book_id`, `scope`('chapter'\|'arc'), `chapter_id?` | `user_id`, `project_id` |

## §2 Workstream ownership map (disjoint files)

| WS | P | Owns (sole) | Consumes (frozen) | Shared-file seam |
|---|---|---|---|---|
| **W-STITCH** | P2 | `engine/stitch.py`, `tests/unit/test_stitch_motif.py` | existing `stitch_chapter` call sites | **none** (fully disjoint) |
| **W11 sync** | P2 | `routers/motif_sync.py` (new), `tests/unit/test_motif_sync.py` | `motif_repo` (`source_version`, read-only), `motif_max_*` quotas | `main.py` +1 include line |
| **W8 mine** | P3 | `engine/motif_mine.py` (body), knowledge-service `motif_beat` extractor, `tests/unit/test_motif_mine.py` | W2-F0 dispatch, `motif_repo.create`, `motif_mine_*` config | **none** in composition (worker seam frozen); cross-service into knowledge-service |
| **W9 import** | P4¹ | `engine/motif_deconstruct.py` (body), `db/repositories/import_source_repo.py` (new), `routers/import.py` (new), tests | W2-F0 dispatch, `arc_template_repo`², extraction rails | `main.py` +1 include line |
| **W10 arc** | P4 | `routers/arc.py` (new), `engine/arc_apply.py` (new), `db/repositories/arc_template_repo.py` (new)², FE arc-timeline subtree, tests | `motif_repo`, planner (`engine/plan.py` decompose, read-only) | `main.py` +1 include line; FE arc tree is disjoint by namespace |

¹ §12.7: import (W9) is product-prioritized *before* mine (W8) — bootstrap a library from
admired works before waiting for your own corpus. This is a **priority** order, not a code
dep; the files are disjoint.
² **`arc_template_repo.py` is owned by W10** (the arc-CRUD owner). W9's deconstruct writes
`arc_template` rows — it consumes W10's frozen repo signature (or, if W10 hasn't landed, a thin
local insert it hands to W10 at reconcile). Resolve at Batch-B kickoff: land W10's
`arc_template_repo` CRUD first (small), then W9 + W10 fan out against it.

**Only remaining shared-file seam after W2-F0:** `main.py` router includes — W9/W10/W11 each
add **one** `include_router` line (W11's `motif_sync`, W9's `import`, W10's `arc`). A trivial
3-way union at reconcile (Wave 1 proved the 2-way `main.py` union is conflict-free with a
union merge). Each WS adds its line; reconcile unions them.

## §3 Cross-WS contracts to freeze before Batch B

- **`motif_beat` extractor (W8, cross-service)** — a 5th map-extractor in `loreweave_extraction`
  (§12.4): per scene/chapter emit `{beat, thread, tension, role_mentions}`. Declared with an
  extractor version (`motif_mine_extractor_version` = `motif_beat@v1`) so its cached results are
  keyed like the existing 4 extractors. W8 owns both the knowledge-service extractor AND the
  composition-side mining pipeline that calls it.
- **`source_version` 3-way diff (W11)** — `motif.source_version` exists; `clone()` already copies
  `src.version` into the new row. W11's upstream-diff re-fetches the source by lineage, diffs
  (base = pinned `source_version`, ours = local edits, theirs = current upstream), surfaces
  merge/conflict. Read-only on `motif_repo`; new logic in `routers/motif_sync.py`.
- **Copyright abstraction guardrail (W9, §12.6)** — `analyze_reference` MUST strip proper nouns /
  verbatim phrasing into role slots + generic beats; imported-derived motifs carry
  `imported_derived=true` (B-3 taint, already enforced by the publish-strip trigger). A
  post-check rejects near-verbatim retelling. `examples[]` author-written/synthetic only.

## §4 Batching (execution order)

- **Batch A (P2, parallel, fully disjoint, no LLM infra):** W-STITCH + W11 sync. Completable
  + unit-verifiable now; no lm_studio / embedding credential needed. **← fan out first.**
- **Batch B (P3/P4, LLM + cross-service):** W10 arc (land `arc_template_repo` first) → W9 import
  + W8 mine. Need lm_studio (LLM-decompose/deconstruct/abstraction) + the platform embedding
  credential (`motif_embed_model_ref`) for live-smoke. R-NODE-P4 (import → arc_template → apply
  → conformance) and R-NODE-P3 (mine → draft → promote → reuse) are the reconcile gates.

## §5 Risk guards carried as tests (per master-plan §7)

- W-STITCH: dedup-across-boundary signal fires on repeated imagery; dial-respect (style/voice
  profile preserved); ≤2-scene over-resolve fix; **eval-gate** (stitch improves seams, doesn't
  flatten — non-regression vs un-stitched).
- W11: 3-way diff is deterministic; quota ceilings (`motif_max_public`) reject N+1; replay-safe.
- W8: mined drafts below `motif_mine_min_judge` shown not silently dropped; one platform embed
  model (B-1); cross-service extractor-version keyed cache.
- W9: imported motif carries `imported_derived` taint; abstraction post-check blocks verbatim;
  `import_source` is per-user, no public path (§12.6).
- W10: proportional placement rescale on `chapter_span` ≠ target (R2.5); dropped/merged motifs
  surfaced never silent (§12.6 scale-mismatch).
