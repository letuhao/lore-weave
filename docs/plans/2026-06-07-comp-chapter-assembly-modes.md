# Composition chapter-assembly modes — per-scene+stitch vs chapter-granularity (DESIGN / BUILD PLAN)

> **Track:** LOOM · **Milestone:** D-COMP-CHAPTER-STITCH-PASS (the GRANULARITY lever). **Size:** XL → **design-checkpoint now, BUILD in a fresh session.**
> **Why:** state-reinjection is DONE (LOOM-33 timeline-axis fix + LOOM-36 anti-re-establishment instruction killed gross re-narration). The residual A3 concat-pairwise loss is **granularity** — 9 short per-scene-stitched fragments vs 3 long single-pass chapters. `eval_a_fair` proved the decompose plan wins **3-0 at equal (chapter) granularity**. PO (LOOM-36) chose **both-as-switch**: a work-level `assembly_mode`.

## Decision (LOCKED at CLARIFY)
- A work setting **`assembly_mode: 'per_scene' | 'chapter'`** (default `per_scene` for co-write; `chapter` for autonomous long-form). Optional per-request override.
- **`per_scene` (+ stitch):** keep the validated per-scene engine (A1 diverge→converge, A2 canon-check/reflect, A3 adaptive-K) → when all a chapter's scenes are `done`, a **chapter-stitch pass** rewrites the concatenation into a smooth chapter (dedup echoes, smooth transitions) → **re-run the A2 canon-check on the stitched output** (the stitch rewrites, so the per-scene guard must be re-applied at chapter level).
- **`chapter` (single-pass):** generate the whole chapter in ONE pass from the decompose plan (the chapter's scene synopses as a combined outline). This is `eval_a_fair`'s winning config. **Loses** per-scene adaptive-K / diverge / per-scene canon-check → **MUST run a chapter-level A2 canon-check** on the output (the cast = union of the chapter's scene `present_entity_ids`; position = chapter start).

## Design

### Packer (reuse, position = chapter start)
Both modes pack at the chapter's reading position: `at_order = scene_at_order(chapter_sort)` (the LOOM-33 dense axis). For `chapter` mode the "scene node" is synthetic (the chapter), so the pack request needs a node carrying `chapter_id`, `story_order = chapter_sort*1000` (chapter opening), combined `present_entity_ids` (union of the plan's scenes), and a combined `synopsis` (the chapter intent + ordered scene beats). No new spoiler surface — the existing `before_order`/`filter_inworld_events` cutoff applies.

### `chapter` single-pass path (engine + router)
- New engine fn `generate_chapter(...)`: builds the combined chapter outline from the decompose plan (chapter intent + each scene `title/synopsis/tension` in order) → `build_messages` (reuse; the LOOM-36 instruction still applies) → single drafter call (max_tokens sized to scene-count) → returns the chapter draft.
- **Canon-safety:** after generation, run `check_canon` (A2) over the chapter cast at the chapter position; if a HARD contradiction fires, run one `reflect_revise` pass (reuse the A2 machinery at chapter granularity).
- Router: `POST …/generate` branches on `assembly_mode` (or a `target_chapter_id` body field) → scene path vs chapter path. Keep the per-scene endpoint contract unchanged.

### `per_scene` + stitch pass (engine)
- New engine fn `stitch_chapter(scene_drafts, chapter_intent, profile, ...)`: ONE LLM pass, system = "merge these consecutive scene drafts of one chapter into a single seamless chapter; remove repeated introductions/echoes, smooth transitions; change NO plot facts." User = the concatenated scene drafts + chapter intent. Position-safe by construction (only this chapter's own scenes).
- Trigger: when the chapter-gate sees all scenes `done` (the existing publish-gate hook), produce the stitched chapter draft as the publishable artifact.
- **Canon-safety:** re-run `check_canon` on the stitched output (the rewrite could re-introduce a gone character).
- Degrade-safe: stitch LLM fails → fall back to the raw concatenation (never block).

### Config / settings
- `config.py`: `composition_assembly_mode_default = 'per_scene'`.
- work `settings.assembly_mode` (validated enum); request override optional.
- `stitch_max_tokens`, `chapter_gen_max_tokens` knobs.

## Eval
- Extend `eval_a_grounded.py` with an `--assembly` flag → measure 3 arms on the concat metric: per-scene (current), per-scene+stitch, chapter-single-pass — each vs V0. Expect chapter-single-pass ≈ `eval_a_fair`'s 3-0; stitch should close most of the per-scene granularity gap while preserving canon guards.
- `eval_a_fair.py` stays the equal-granularity plan-value reference.

## Files (BUILD, ~XL)
engine: `chapter_gen.py` (new), `stitch.py` (new), canon re-check wiring · `routers/engine.py` (mode branch) · `config.py` + work settings enum · maybe `db` (store chapter draft) · `eval_a_grounded.py` (--assembly) · tests (chapter-gen, stitch, canon-recheck, mode plumbing, spoiler). **/review-impl** (new engine paths + canon-safety re-checks + spoiler).

## /review-impl hardening (folded, design-cycle)
- **MED-1 — chapter mode needs a CHAPTER-scoped entry.** `/generate` loads a real outline node by `node_id`; the "synthetic chapter node" is not in the DB. BUILD: add either a new `POST …/works/{p}/chapters/{chapter_id}/generate` or a `target_chapter_id` body field on `/generate`; construct an in-memory pack node (`chapter_id`, `story_order = chapter_sort*1000`, union `present_entity_ids`, combined `synopsis`) — never persist it.
- **MED-2 — output storage = book-service chapter draft.** Composition does NOT store chapter prose; it proxies the versioned book-service chapter DRAFT (`routers/prose.py`, optimistic `_version` → 409 `CHAPTER_DRAFT_CONFLICT`). Both modes WRITE their result via that path (409-safe). BUILD must first read how a chapter draft is composed from scenes today (if at all) and reconcile (stitch/chapter-gen REPLACES vs augments the current assembly).
- **MED-3 — stitch input cap.** Cap the concatenated-scenes input (`stitch_max_input_chars`) or window to the last K scenes; a long chapter blows the prompt (same class as D-COMP-COMPRESS-INPUT-CAP).
- **LOW-1 — chapter-gen job idempotence.** Re-generating a chapter must not pile duplicate `generation_job` rows / dup drafts; reuse the idempotency_key surface (key on chapter_id + assembly_mode).
- **LOW-2 — chapter-gen output ceiling.** A whole chapter is ONE pass; to fit `max_output_tokens` you cannot scene-window (that re-introduces the granularity you're removing). Document the long-chapter ceiling; very long chapters may stay `per_scene+stitch`.
- **CANON-SAFETY (verified NOT a regression):** composition scenes all resolve to their chapter's sort_order, so the per-scene A2 guard already runs at `at_order = chapter_sort*stride` for every scene. A single whole-chapter `check_canon` at that position is EQUIVALENT for gone-character detection. Both modes equally cannot catch a death that happens *within the same un-published chapter* (the KG lacks it until publish) — pre-existing, not introduced here. Still: run `check_canon` (+ one `reflect_revise`) on the assembled output in BOTH modes.

## Risks / open
- **Cost/latency:** stitch = +1 LLM pass/chapter; chapter-gen = 1 long pass (token limits on long chapters → may need scene-windowed generation). 
- **Canon regression:** both modes weaken the per-scene A2 guard → the chapter-level re-check is load-bearing (test it: seed a gone character, assert the chapter output is checked/repaired).
- **Metric honesty:** the concat pairwise is granularity-confounded; once chapter-granularity exists, A3-vs-V0 is finally apples-to-apples — that's the real validation.

## Sequencing
Design-checkpoint (this doc) → **fresh-session BUILD**: B1 `assembly_mode` plumbing + config → B2 `chapter` single-pass path + chapter-level canon-check → B3 stitch pass + post-stitch canon-check → B4 eval (`--assembly`, 3-arm) + live-smoke. /review-impl after B2/B3 (canon-safety + spoiler).
