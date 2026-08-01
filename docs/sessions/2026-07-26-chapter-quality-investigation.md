# Chapter-Generation Quality — Root-Cause Investigation (2026-07-26)

**Subject:** the 10-chapter arc drafted by the authoring-run subagent.
**Book:** `019f9d2b-b36c-7921-8b4c-96a1bd39c9e4` · **Run:** `019f9dd8-0c98-7964-96f4-5b50ede9232b` (report_ready, $0.60)
**Plan run:** `019f9d2e-aef7-7087-849f-d99533b1c717` (compiled) · **Chapters:** `019f9d72-70xx…`

Method: DB evidence (composition) + code trace of the compile → pack → draft → critic path. Every claim below is backed by a query or a file:line.

---

## Verdict up front
The pipeline is **wired and functional** — PlanForge v2 passes really run and emit artifacts, the drafter grounds on canon, and the critic really catches the bad chapter. The quality loss is **not** a broken tool; it is **three process/design gaps**, and the test **"threw the auto-compiled plan straight at the agent"** with no polish/review loop — exactly the hypothesis.

**Root causes (ranked):**
1. **No structured cross-scene/chapter continuity state.** `exit_state` is populated on **0 / 27** scenes; continuity rides only on a *capped raw-prose blob*. Mid-arc the key facts fall out of the window → the ch5 continuity violations.
2. **Critic detects but does not remediate autonomously.** Severe verdict → *pause + notify a human*; in a script-driven run with no human it is a no-op, so the flawed chapter ships and later chapters build on it.
3. **Plan was auto-compiled from a thin spec and thrown to drafting — no human polish/review, no POV/length/continuity fields set.**

---

## A · WHAT is bad (the critic's own per-chapter verdicts) — EVIDENCE

`authoring_run_units.critic_verdict` for run `019f9dd8` (scale 1–5):

| Ch | unit | coherence | pacing | canon_consistency | severity | status |
|----|------|-----------|--------|-------------------|----------|--------|
| 1 | 0 | 5 | 4 | 5 | ok | **accepted** |
| 2–4 | 1–3 | 5 | 4 | 5 | ok | drafted |
| **5** | **4** | **3** | 4 | **2** | **SEVERE** | drafted |
| 6 | 5 | 4 | **3** | 5 | ok | drafted |
| 7 | 6 | 4 | 4 | 5 | ok | drafted |
| 8 | 7 | 4 | **3** | 5 | ok | drafted |
| 9–10 | 8–9 | 5 | 4 | 5 | ok | drafted |

- [x] **Mid-arc dip is real and quantified** — coherence 5→3, canon 5→2 at ch5; pacing sags to 3 through ch6/ch8.
- [x] **ch5 has 2 logged `logic_internal` violations** (verbatim from the verdict):
  1. *Silas physical-state continuity* — "established earlier that Silas was 'unraveling'/'dissolving'… previously 'a sketch left out in the rain'. The sudden shift to a 'smudge of charcoal against the sky' while still walking, talking, carrying crates" → continuity error on his dissolution scale.
  2. *Void traversability* — the "Empty Valley" is an erased void, yet Silas traverses 10 miles of it to reach Elara, contradicting the void's established emptiness.
- [x] **Only ch1 was `accepted`; ch2–10 stayed `drafted`** (never human-reviewed → never promoted).

---

## B · Did we POLISH the plan before compile? — **NO**

- [x] **Plan compiled from a thin auto-spec, not a hand-polished outline.** `plan_run.source_markdown` = **1260 chars**, `mode = rules`, `updated-created = 2m35s` (that window is the compile passes running, not human editing). Flow was `plan_propose_spec → plan_compile` directly (SESSION_HANDOFF).
- [x] **No manual outline adjustment step ran** before compile — no edit between propose and compile.

> A 1260-char seed spec is a skeleton. The passes fleshed it out, but nobody curated the result before drafting.

---

## C · Were STUDIO TOOLS used/reviewed before start? — **PARTIAL (auto-populated, not human-reviewed)**

| Tool / field | State before drafting | Evidence |
|---|---|---|
| Glossary ontology | ✅ adopted (required — cast seed 422s otherwise) | SESSION_HANDOFF; cast pass succeeded |
| Cast (entities) | ✅ present — **7 distinct** entities across scenes | `distinct unnest(present_entity_ids)=7` |
| Scenes | ✅ 27 scenes; synopsis/goal/conflict on **27/27** | `outline_node` |
| Scene ↔ chapter link | ✅ **27/27** stamped | `chapter_id NOT NULL` |
| **POV per scene** | ❌ **0/27** `pov_entity_id` | population query |
| **exit_state (continuity)** | ❌ **0/27** | population query |
| **value_shift** | ❌ **0/27** | population query |
| **target_words (length steer)** | ❌ **0/27** | population query |
| KG (knowledge graph) | ⚠️ not consumed by the drafting packer (uses glossary canon + recent prose, not KG) | `pack.py` lenses |

- [x] **Structure was auto-generated, not curated.** Cast/scenes exist because the compile passes made them — there is **no evidence of a human review pass** (no POV pinned, no per-scene length, no continuity state, chapters left `drafted`).
- [x] **The continuity- and steer-critical fields the drafter needs were never filled.**

---

## D · PlanForge v2 — WIRED or designed-only? — **WIRED (passes emit real artifacts), but incomplete**

- [x] **All 7 passes emitted real artifacts** (`plan_artifact` for run `019f9d2e`): `motif_plan, cast_plan, world_plan, beat_plan, char_arc_plan, scene_plan` + `link_report ×2` (self_heal) + `spec/document/package/graph`. **Not stubbed.**
- [x] **BUT the passes don't emit the cross-scene state handoff.** The scene pass fills synopsis/goal/conflict/present-entities but leaves `exit_state / value_shift / pov / target_words` NULL — so "the tools ran" ≠ "the drafter got continuity."

> So: the design is wired; the **gap is what the passes leave empty**, not a never-connected tool.

---

## E · Instruction / prompt clarity — **prompt intent is clear; the CONTEXT it's handed is thin on continuity**

- [x] **The drafter's system prompt is reasonable** (`cowrite.py:build_messages`): "use canon, present characters, threads, beat, **recent prose**, lore… never contradict canon… CONTINUE forward, don't re-narrate… vary imagery." Clear intent.
- [x] **But continuity rides ENTIRELY on the packer's "recent prose" blob, which is CAPPED** (`compress.py:cap_recent_prose(prose, max_input_chars)`, default 24000 chars ≈ ~4k words). By ch5 the prior arc exceeds the window → oldest facts (Silas = "sketch in the rain") drop out → the model re-invents his state. **There is no structured `exit_state` to carry the key facts compactly** (0/27).
- [x] **A chapter is drafted as ONE synthetic pack node** (`chapter_gen.py:build_chapter_pack_node`, whole chapter at once) grounded on "strictly-prior context" — no explicit per-scene prior-ending carry.
- [x] **`target_words` NULL ⇒ the length steer never fires** (`build_messages` only appends the LENGTH directive when target_words>0) → pacing sag.

### The critic-remediation gap (the reason bad chapters shipped)
- [x] **The D5 critic DID fire and DID catch it** — `authoring_runs.breaker_state = {"reason":"critic_severe", … "unit_index":4}`.
- [x] **…but the run still reached `report_ready` with all 10 chapters drafted.** By design (`authoring_run_service.py` D5 comments) severe → **pause + notify human**; remediation is **human-only** (accept / reject+revert / revert-all). **There is NO auto-regen/repair path.** In the script-driven run with no human, "interrupt on severe" was a no-op, so ch5 stayed and ch6–10 drafted on top of it.

---

## Did I "adjust the plan / use tools before start" or "throw everything at the agent"? — **THREW IT**

The test drove `propose → compile → materialize → authoring-run` programmatically. It did **not**: polish the 1260-char spec, review/curate the 27 scenes, pin POV, set per-scene target_words, populate exit_state, or human-review cast/glossary/KG in Studio before drafting. That is precisely the "throw everything at the agent" path — and the quality reflects it.

---

## Fix backlog (ranked; for the co-writer / atom-edit + quality track)

1. **Structured continuity carry (highest leverage).** Populate `exit_state`/`value_shift` in the scene compile, and re-inject a compact "state so far" (entity physical-state, location, time, open threads) into every chapter/scene draft — not just raw capped prose. Closes the ch5 class directly.
2. **Autonomous critic remediation.** On `severe`, auto-trigger a bounded REVISE/regen of that unit against the named violations (the `revise_draft` path already exists) before continuing — don't rely on a human that isn't there in an autonomous run. Keep human-review for the interactive path.
3. **A pre-draft "polish gate."** Before an authoring run, require/offer a Studio review pass: pin POV, set target_words, sanity-check cast + scene synopses, adopt glossary/KG — the atom-edit tools the co-writer should drive. Surface this as the co-writer's job.
4. **Set `target_words` at compile** (unblocks the existing length steer → fixes pacing sag).
5. **POV per scene** at compile (anchor voice/continuity).

## ✅ FIXES SHIPPED + PROVEN (2026-07-26)

**Fix #1 — compress → per-entity STATE LEDGER** (`77dc6f3e2`). Rewrote the running
story-so-far summary from a generic recap into a state ledger (each character's
condition + ongoing transformation + location; what changed in the world).
**PROVEN E2E:** the same critic (`judge_prose`) on old vs re-drafted ch5 —
**canon_consistency 2→5, coherence 3→4, violations 2→0** — reproduced the original
severe verdict on the old draft and scored the new one clean. Confirmed again in the
FULL authoring-run path (ch5: severe→ok, canon=5, 0 violations).

**Fix #2 — autonomous critic remediation (auto-revise)** (`221846ca8`). On a
'severe' verdict the driver now auto-REVISES (re-draft against the named violations
+ re-critique) up to max_attempts before falling back to the human-in-loop pause;
gated `AND(deploy ceiling, per-run opt-in)`. **PROVEN:** 5 unit tests (loop
branches + gating) + full suite 103; deployed live; E2E confirmed the gating (a
clean draft did NOT trigger a wasteful re-draft). The repair branch = fix #1's
proven-clean re-draft.

**Fix #3 — chapter LENGTH target** (`ef53eb47e`). The whole-chapter draft passed
NO target_words (only a token ceiling) → short/uneven pacing. Now passes
sum-of-scene-targets + generic length directive. **PROVEN:** 39 unit tests + live
re-draft grew ch5 1345→1505 words, canon still clean.

Combined VERIFY: **2400 composition unit tests pass**, no regressions.

### 🎯 GOAL MET — fresh re-run of the dip chapters clears every threshold
Fresh authoring-run `019f9ef1` over ch5–ch8 (all 3 fixes, auto-revise OFF = honest
first-draft), `authoring_run_units.critic_verdict`:

| ch | severity | canon | coherence | pacing | violations |
|----|----------|-------|-----------|--------|-----------|
| ch5 70b4 | ok | 5 | 5 | 4 | 0 |
| ch6 70cc | ok | 5 | 5 | 4 | 0 |
| ch7 70e2 | ok | 5 | 5 | 4 | 0 |
| ch8 70f6 | ok | 5 | 5 | 4 | 0 |

Baseline (`019f9dd8`) → re-run: **severe 1→0 · violations 2→0 · canon min 2→5 ·
coherence min 3→5 · pacing min 3→4.** ch5–ch8 were the only baseline dips, so this
covers the whole problem. Quality improvement PROVEN by the system's own critic.

Residual levers (not needed to meet the bar, tracked): chapter token cap =
`min(scene_count × chapter_gen_per_scene_tokens[700], 8192)` (~1500 words/3-scene
chapter) binds before the length target — raise `chapter_gen_per_scene_tokens` if
fuller chapters are wanted; Fix #4 deterministic exit_state for extra robustness.

**Still open — Fix #4 (deterministic exit_state):** the belt-and-suspenders on top
of fix #1 — have the scene compile EMIT exit_state per scene + the packer INJECT it
deterministically (not only the LLM-compressed ledger). Larger/structural (compile
writer + persist + packer) — a planned cycle, not a quick edit. Fix #1 already
closed the observed ch5 failure, so this is a robustness upgrade, not a bug.

## Open questions — RESOLVED
- [x] **`exit_state` is never written to scene rows on this path.** The scene persist (`outline.py:524-533`) writes only `title, synopsis, tension, present_entity_ids, story_order, beat_role, chapter_id` — it **omits `pov_entity_id`, `exit_state`, `value_shift`, `target_words`, `conflict`, `outcome`, `stakes`**. (The `conflict`/`goal` fields the DB shows populated come from the separate scene-plan link pass; the continuity/steer columns come from **no** pass.) `ChapterExitState` is constructed in `plan_pass_adapters.py:339` only for the older markdown-grounded path and is not persisted to the authoring-run scene tree. → **Fix #1 is a writer gap, not a missing tool.**
- [x] **KG is not a drafting-packer lens.** The packer lenses (`pack.py`) are L1b timeline / L2 structural (COMP DB) / L3 recent prose — the drafter grounds on glossary canon + prior prose, **not** the knowledge graph. KG is available to the co-writer as a tool but is not auto-injected into chapter drafting.
