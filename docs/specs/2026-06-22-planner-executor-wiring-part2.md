# D-CACHE-PLANNER-WIRING Part 2 — executor-loop planner wiring (DESIGN)

Status: **DESIGN — awaiting approval** · 2026-06-22 · branch `feat/extraction-knowledge-architecture`
Part 1 (split-aware cost estimate) shipped `30c7549d`. This doc designs Part 2 only.

## 1. The constraint that reframes everything

`loreweave_extraction.plan()` is a **token-budget STRUCTURE planner**: its inputs are `Unit`s
carrying `est_input`/`est_output` **token estimates**, and its output is `LLMCall`s + `Unplannable`
+ `model_fit_warning`. **It never carries the actual text payloads.** It decides *how many* calls
and *whether* the work fits — not *what prose* each call sends.

The executor's two current planners DO produce payloads:
- `_plan_chapter_windows` → actual **window prose** (block-joined paragraph text), via the
  translation block batcher `build_batch_plan` (packs whole blocks up to the input budget).
- `plan_kind_batches` → actual **kind lists** per batch (≤ `MAX_KINDS_PER_BATCH`).

**Therefore `plan()` cannot REPLACE them.** A "full replace" still needs the executor to slice
real text to match whatever structure `plan()` decides — so `plan()` would duplicate the budget
math the windower already does, and we'd add a fragile `unit_id → (window_idx, batch_idx)` remap
onto the cache-gate key + OBS `event_id` for zero payload benefit. That is high risk, low gain.

## 2. What is actually worth wiring — the real gap

The epic's motivating failure class is **S1–S5: an oversized unit truncates mid-output
(`finish_reason=length` → lost entities) instead of being split or surfaced.** The current
windower packs *whole paragraph blocks*; if a **single block exceeds the input budget**, it
becomes its own oversized window → the LLM truncates → entities silently lost. The windower has
no "this can't fit" signal — it just runs. `plan()`'s `Unplannable` exists precisely to surface
that (a unit that can't be split below budget along its axis).

So the high-value, low-risk wiring is **`plan()` as a pre-flight FEASIBILITY GATE over the
windowing the executor already produced**, NOT as a replacement for it.

## 3. Recommended design — Option B: plan() as a pre-flight gate

After `windows` + `batches` are built (unchanged), and before the LLM loop:

1. Build `Unit`s from the **actual** windows × batches — `est_input` = `estimate_tokens(window_text)
   + schema(batch) + overhead`, `est_output` = the per-batch output reservation, `group` = chapter,
   `splittable=False` (the window prose is already the finest block-join the executor can emit;
   it can't sub-split a paragraph without a sentence splitter we don't have), `id` = the stable
   `f"{window_idx}:{batch_idx}"` (which is *already* the cache/OBS coordinate — no remap needed).
2. Run `plan(PlanRequest(units, ModelCaps(context_window), Policy(reasoning_effort=effort,
   max_units_per_call=1)))` — `max_units_per_call=1` matches Part 1 (one batch call per unit; the
   window text is per-call, never shared/packed).
3. Use the result as a GATE, not a driver:
   - **`unplannable`** → for each flagged `(window_idx, batch_idx)`, record a batch-outcome with a
     new taxonomy status **`unplannable`** and **skip its LLM call** (don't spend tokens to
     truncate). The chapter then derives `completed_with_errors` (INV-F15, already wired) — the
     entities that *did* fit still land; the un-fittable batch is VISIBLE, not silently lost.
   - **`model_fit_warning`** → log + include in the chapter result for telemetry.
   - **`est_cost_range`/`est_llm_calls`** → log (the executor's actual loop count should match).
4. The LLM loop, cache-gate (`chunk_idx`/`batch_idx`), `event_id`, put/get, provenance, merge,
   writeback are **ALL UNCHANGED** — Option B touches none of the seams from the main-merge.

### Why Option B over A/C
| | A (full replace) | C (plan decides counts) | **B (pre-flight gate)** |
|---|---|---|---|
| Replaces proven windowing | yes (risk) | partial (risk) | **no** |
| Remaps cache-key/event_id | yes | maybe | **no — ids already match** |
| Captures S1–S5 Unplannable | yes | yes | **yes** |
| Payload duplication problem | unsolved | unsolved | **n/a (windower keeps payloads)** |
| Risk on hot just-merged path | high | medium | **low** |

Gain captured by B = the actual robustness goal. Gains foregone vs A = "one planner object"
purity — not worth a hot-path rewrite when `plan()` structurally can't own the payloads anyway.

## 4. Open decisions for CLARIFY (need a call before BUILD)

- **D1 — taxonomy:** add `unplannable` to the OBS batch-outcome enum, or fold into `truncated`?
  Recommend a **distinct `unplannable`** (truncated = "we tried + lost tail"; unplannable = "we
  refused to try" — different operator action: shrink the block / bigger-context model). Touches
  `extraction_outcomes.classify_*` + the migrate enum comment + `chapter_status_from_outcomes`.
- **D2 — effort source:** thread the clamped `reasoning_effort` into the `Policy` so the gate's
  budget matches the real call (today the worker uses `thinking_enabled`→band; this overlaps the
  tracked `D-RE-WORKER-GRADED-EFFORT`). Scope: thread it or use the band's coarse mapping?
- **D3 — scope of "skip":** when a unit is unplannable, skip only that `(window,batch)` (other
  batches of the window still run) — confirm that's the desired granularity (recommend yes).
- **D4 — live smoke:** the VERIFY gate needs a real ≥2-service run (extract an entity-dense
  chapter end-to-end + a deliberately oversized block to exercise the unplannable path). Confirm
  the stack is bootable for this, or track a `LIVE-SMOKE deferred` row.

## 5. Rough plan (post-approval)

S (logic ~3, 1 side-effect = the enum): (1) `unplannable` taxonomy member + classifier + status
derivation; (2) the pre-flight `plan()` gate in `_process_extraction_chapter` (build units from
windows×batches, run, mark+skip unplannable); (3) thread effort into `Policy`; (4) unit tests
(oversized-block → unplannable outcome, normal → no change, fan-out warning surfaced) + a live
smoke. Estimated one focused BUILD increment — NOT the XL "rewrite the executor" I'd flagged,
*because* Option B keeps the windower.

## 6. Recommendation

Adopt **Option B**. It delivers the epic's actual S1–S5 robustness goal, is a small contained
change (the executor's proven windowing/cache/OBS seams stay intact), and avoids the
architecturally-impossible "make plan() own the text payloads" trap that Options A/C run into.
Decisions D1–D4 are quick calls; then it's one BUILD increment, not a structural rewrite.
