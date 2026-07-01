# Planning Pipeline Architecture — decompose-and-refine, not one-shot

> **Date:** 2026-06-30 · Status: DESIGN DIRECTION (PO architectural re-examination) ·
> **Related:** [`2026-06-30-chapter-synthesis-self-healing.md`](2026-06-30-chapter-synthesis-self-healing.md)
> (the same principle proven for chapter prose) · [`2026-06-30-editor-compose-overhaul/`](2026-06-30-editor-compose-overhaul/).
> **Origin:** reviewing the committed 12-chapter / 36-scene threaded plan surfaced many holes at once
> (no motif binding, no cast / scene-presence, anonymous new characters, ch1 telescoped, generic arc).
> The PO's diagnosis: these are NOT independent bugs — they are symptoms of a **one-shot** planner.

## The disease — `decompose` is one-shot

`engine/plan.py decompose` is **1–2 LLM calls**: L1 maps beats onto chapters, L2 emits ~3 scenes per
chapter from `premise + template + (empty) cast roster`. Asking one prompt to simultaneously select
themes, design characters, plan introductions, shape an arc, set a tension curve, AND write 40 scene
synopses is the **exact anti-pattern of the old whole-chapter `stitch`** (one prompt → the whole
artifact). The review holes are its symptoms:

| Symptom (from the plan review) | Root |
|---|---|
| `motif_coverage = {}` — no thematic structure | the one-shot call never *selects* motifs (the library + `MotifRetriever` exist, unused) |
| every scene's present cast empty | cast roster was empty at plan time (the named premise cast aren't glossary entities yet) — and the planner never *proposes* a cast |
| new characters appear anonymous ("a group", "someone") | no step decides to INTRODUCE a new character at scene X, name it, add it to the glossary |
| CH1 telescopes the whole origin, hits tension 100 in ch1 | no deliberate tension-curve / beat-budget step |
| arc reads generic | theme + character arcs never shaped before scenes are written |

## The principle (unifying — same as stitch → self-heal)

**Decompose-and-refine beats one-shot at EVERY level** — scene prose (satellite edits, not whole-chapter
rewrite), chapter assembly (self-heal, not stitch), **and planning**. A good detailed plan is built the
way a real author plans: **N focused steps, each detailed, each building on the last → assemble →
plan-level self-heal → polish.** You cannot hand an LLM a few lines and get a good 40-scene plan, just
as you cannot hand it 3 scenes and get a good merged chapter. Scope: **ONE arc is enough** — a
sufficiently detailed single-arc plan can beat an amateur writer; don't multiply arcs.

**Human ↔ LLM at every step:** the LLM *proposes* (autonomously, using tools — motif search, cast
extraction); the human *directs* at a checkpoint (approve / edit / swap / manual). That answers
"human-directed or LLM-self-proposed?" — **both**, by step.

## The multi-step planning pipeline (proposed)

Each step: **input → LLM proposes (tool) → human checkpoint → output**. EXISTS = a piece already in the
codebase; MISSING = to build.

| # | Step | LLM does (tool) | Human checkpoint | Status |
|---|------|-----------------|------------------|--------|
| 1 | **Theme & motif selection** | read premise → propose themes + **search the motif library** → select N to weave | approve / swap motifs | piece EXISTS (`motif_select`, `MotifRetriever`) — needs to be a discrete first step |
| 2 | **Cast design** | extract the named cast from the premise + propose roles/traits/relationships + propose the supporting cast the arc needs → **seed into glossary** | edit / approve the cast | **MISSING** (the "propose cast + glossary seed" step) |
| 3 | **World / power-system** | propose sects, cultivation realms/stages, key locations, factions → lore entries | approve | partial (glossary lore; no dedicated step) |
| 4 | **Arc & beat shaping** | pick ONE arc (template) → map beats informed by theme/cast/world → set a deliberate **tension curve / beat budget** (fixes ch1 telescoping) | approve the shape | piece EXISTS (templates, L1) — needs tension-curve intent |
| 5 | **Character arcs + introduction schedule** | plot each main character's trajectory across beats; decide WHERE each new character is introduced (named) | approve / direct callbacks | **MISSING** (char-arc + introduction scheduling) |
| 6 | **Scene decomposition** | the current L2 decompose, now conditioned on ALL of 1–5: present cast, new-char introductions, bound motifs, world | spot-check | EXISTS (`decompose` L2) — needs the rich inputs |
| 7 | **Plan self-heal** | a PLAN-judge reads the whole outline → finds holes (pacing, unplanned character, unused motif, setup-without-payoff) → satellite-fix plan spans | approve fixes | **MISSING** — but the judge→locate→satellite→splice pattern is already built for chapters (`engine/self_heal.py`); reuse the design at plan granularity |

Steps 1–5 feed step 6 so the 40 scenes come out grounded (who's present, what motif, what's introduced,
what tension) instead of invented. Step 7 is the planning analogue of chapter self-heal.

## What exists vs what's missing (build surface)

- **Reusable now:** motif library + retriever + `motif_select` (step 1); structure templates + L1
  beat-map (step 4); `decompose` L2 (step 6); the judge→satellite→splice pattern from
  `engine/self_heal.py` (step 7, re-targeted to the outline).
- **To build:** the **orchestration** that chains the steps with human checkpoints; step 2 (cast
  proposal + glossary seed); step 5 (character arcs + introduction schedule); step 7's plan-judge.

## Open questions for the PO
- [ ] Build the full pipeline, or stage it (e.g. steps 2 + 5 + the orchestration first, since cast /
  introductions are the biggest hole and unblock grounded drafting)?
- [ ] Where are the human checkpoints **blocking** (wait for approval) vs **advisory** (proceed, let
  the human edit after)? Default: blocking at 1, 2, 4; advisory at 3, 5, 6, 7.
- [ ] One arc confirmed as the scope unit — the pipeline plans a single arc end-to-end.
