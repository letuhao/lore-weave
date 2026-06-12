# Composition long-form ASSEMBLY — state-reinjection + compress + thread-ledger (BUILD PLAN)

> **Track:** LOOM · **Milestone:** `D-COMP-LONGFORM-STATE-REINJECTION` (the eval-validated long-form lever; the first §10.2 build).
> **Design SSOT (LOCKED):** [`2026-06-05-composition-v1-reasoning-engine.md`](../specs/2026-06-05-composition-v1-reasoning-engine.md) — §3 (`compress` primitive), §5 (constraint ledger), §10.2 (narrative_thread), F2 (re-inject state). This doc = the IMPLEMENTATION PLAN, not new design.
> **Size:** XL · **Workflow:** v2.2 · multi-session. **PO scope (2026-06-06): FULL §10.2** (compress + ReasoningState + ledger) + **dual-source** state. **/amaw not required** (composition+knowledge reads, no schema migration in S1-S3; S4 ledger may add a table — /amaw that slice).

## Why (eval-grounded)
A-EVAL/B/C resolved the eval arc: the decompose **plan is validated** (C: 3-0 fair), and the long-form gap is **ASSEMBLY** = (1) **state-reinjection** (B: raw guide-threading −55% defects) + (2) **granularity** (per-scene-then-concat fragments). This milestone builds the §10.2 state architecture; **re-run `eval_a_validate.py` (the unfair-but-realistic concat metric) after each slice** — the gap should close as state-reinjection + compress land. Build on the proven decompose plan; do NOT re-litigate it.

## Validate-first slicing (reconciles "full §10.2" with §8 prove-first)
Build the validated lever FIRST and measure; expand into the fuller architecture slice-by-slice, each eval-gated. "Full §10.2" is the target, reached incrementally — not big-bang.

### S1 — packer dual-source state-reinjection ("story so far") — THE validated lever
- **Gather** (`packer/`): a new `gather_story_so_far` — the prior in-chapter prose, **dual-source (PO), as a FALLBACK not a merge** (review #4): prefer the book-service **chapter draft** (`BookClient.get_draft`) when non-empty; **else** fall back to the prior sibling scenes' latest completed `generation_job` winner text (composition-side; enables the autonomous eval to measure it). No dedup needed (one source or the other).
  - ⚠ **POSITION-BOUND (review #1, HIGH — spoiler-safety):** state-reinjection is a NEW path into the prompt that the spoiler system (`spoiler.py filter_reading_order`) does not currently guard. The **generated-scene source MUST filter `story_order < current scene`** — pulling all sibling scenes would inject FUTURE scenes (a spoiler leak + logically wrong: a scene can't know its own future). Add a **spoiler regression test** (a later-positioned sibling scene's prose must NOT appear in an earlier scene's pack).
  - ⚠ **Draft-source semantics (review #3, MED):** `get_draft` returns the WHOLE linear chapter draft (no scene markers) — if the human wrote ahead it includes text AFTER the current scene, so it is NOT strictly "prior." Decision: the draft source is **"current chapter context"** (whole draft — defensible for a human-in-loop co-writer who wants consistency with everything written), while the **generated-scene source is strictly prior** (position-bounded). Document this split in the block label so it's not mistaken for reading-order-strict.
- **Assemble** (`packer/assemble.py`): a `story_so_far` block, **budget-trimmed** on the priority ladder. ⚠ **Must rank BELOW canon/spoiler-safety blocks** (review): story-so-far is trimmed-first; it must never evict canon-fact / spoiler-cutoff context (that's load-bearing safety). Keep the most-recent prose when over budget (compress lands in S2).
- **Wire**: `pack()` calls the gather; the block flows into the prompt for BOTH cowrite + auto paths automatically (no `guide` hack).
- **Eval-gate:** re-run `eval_a_validate.py` (concat metric) — A3 defect-count should drop toward/below the B-threaded −55%, now automatic. ⚠ **First REVERT B's manual `guide`-threading in `eval_a_validate.py`** (review) — with S1 auto-injecting, the guide-threading would double-inject + confound the measurement. Live cross-service (composition+book).
- Files: `packer/gather.py` (+gather), `packer/assemble.py` (+block), `packer/pack.py` (wire), `clients/book_client.get_draft` (exists), a generation-jobs prior-winner query (repo), tests + eval re-run. **No schema.**

### S2 — `compress` primitive (§3 — scale to long chapters)
- `engine/compress.py`: `compress(state) → re-injectable summary` — an LLM call summarizing the story-so-far + plan + open threads into a bounded NL summary (RecurrentGPT) anchored on the KG's SVO+timeline quadruples (DOME; knowledge-service reads). Disjoint-model not required (it's summarization, not judging).
  - ⚠ **SPOILER-FILTERED KG (review #2, HIGH):** the packer already position-filters KG reads (`filter_inworld_events` by `story_order`). `compress` MUST build its summary from the SAME reading-position-filtered KG (or apply the cutoff itself) — reading the RAW KG would pull future events into the re-injected summary, leaking canon past the scene's reading position. Reuse the packer's already-filtered timeline/bundle rather than re-querying the raw KG.
- **Wire**: when S1's raw "story so far" exceeds its budget slice, `compress` it instead of tail-truncating → the prompt carries a dense summary, not a lossy tail. Bounds long-chapter cost.
- **Eval-gate:** concat metric holds/improves on a LONGER book (more chapters/scenes) where raw truncation would have lost early context.
- Files: `engine/compress.py`, packer wire (compress-on-over-budget), knowledge SVO/timeline read (reuse `KnowledgeClient.timeline`/build_context), tests + eval.

### S3 — `ReasoningState` threading (F2 per-scene re-injection)
- A per-scene `ReasoningState` = {plan (decompose chapter intent + this scene's beat), compressed story-state (S2), open promises/threads (S4 feeds this)} threaded through the engine auto loop + re-injected each scene (the §2 loop step 9 "update state → recursively re-inject").
- **Wire**: engine builds/updates ReasoningState per scene; packer consumes it (replaces ad-hoc S1+S2 wiring with the formal state object).
- **Eval-gate:** multi-scene coherence on the concat metric holds; no regression on single-scene.
- Files: `engine/state.py` (ReasoningState), engine loop wire, packer consume, tests.

### S4 — narrative_thread ledger (§10.2, ADVISORY per D4)
- Promise/foreshadow/MICE PAY/DEBT ledger: detect open promises (a setup/foreshadow) + their payoffs; surface unresolved DEBT **advisory** (D4 — flag + author-override, NOT a hard gate; PAY/DEBT detection is fuzzy per review M5). Feeds open-threads into ReasoningState (S3).
- **/amaw this slice** if it adds a `narrative_thread` table (schema migration).
- **Eval-gate:** advisory ledger surfaces real open-threads on a seeded foreshadow; no false-block.
- Files: ledger repo/table (maybe), detection (LLM or KG), engine surface, FE deferred. tests.

## Sequencing + checkpoints
S1 (validated lever, measure) → S2 (scale) → S3 (formalize) → S4 (ledger). **Human checkpoint after S1's eval** (does automatic state-reinjection close the concat gap?) before S2-S4. Each slice = own VERIFY (live concat-metric re-run) + COMMIT. **/review-impl S1 + S3** (packer/engine load-bearing) + S4 (advisory-gate semantics).

## Locked interfaces / decisions
- Dual-source "story so far": chapter draft if present, else prior generated scene winners (PO).
- State-reinjection is AUTOMATIC in the packer (no `guide` dependency); `guide` stays author-steer.
- Ledger is ADVISORY (D4) — never a hard gate.
- Decompose plan is the PROVEN foundation (C 3-0) — consumed, not re-litigated.
- Measure every slice against `eval_a_validate.py` (the realistic concat metric); `eval_a_fair.py` already isolated the plan (don't re-run for assembly).

## Risks / open
- **Budget pressure:** raw "story so far" on a long chapter blows the prompt budget → S2 compress is the mitigation; S1 ships with tail-trim as the interim.
- **Granularity residual:** state-reinjection helps but C showed granularity is a separate axis — a chapter stitch/coherence pass is NOT in this milestone (a possible S5 / follow-up if the concat gap persists after S1-S3). Flagged: **D-COMP-CHAPTER-STITCH-PASS**.
- **Dual-source staleness:** the chapter draft (human-accepted) and the generated-winner text can diverge (human edited); prefer the draft as truth when present.
- **Use-case reframe:** LOOM is a human-in-loop co-writer — S1 (each scene aware of prior scenes) is valuable for that flow regardless of autonomous long-form; S2-S4 lean more autonomous.
