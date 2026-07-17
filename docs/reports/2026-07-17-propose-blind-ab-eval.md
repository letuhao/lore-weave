# PROPOSE-BLIND A/B eval — does grounding improve the proposed plan?

> **Date:** 2026-07-17 · **Feature:** D-PLANFORGE-PROPOSE-BLIND · **Gate:** OQ-2 (flip the deploy
> ceiling `PLANFORGE_GROUND_ON_EXISTING_ALLOWED` ON only if the eval proves grounding helps).
> **Verdict: ceiling STAYS OFF — grounding did not improve cast continuity in this measurement.**

## Why this eval exists
OQ-2 sealed that the richer cast/spine/systems grounding ships **dark** (ceiling OFF, fails closed)
until an A/B eval shows it actually improves the plan. This is that eval — run for real on a live
stack with the local gemma model, not asserted.

## Method
- **Book** `019f6555` (test account). Ground truth: existing arcs = {The Discarded Miss, The Corrupt
  Path, Reckoning}; existing cast = {Diệp Vấn Vũ, Elara, Void}; 9 chapters; variables PA/HA/CD/THR.
- **Model** gemma-4-26B-A4B QAT (local lm_studio, `019ebb72…`), mode=llm, both conditions identical
  except the flag.
- **Conditions** — same NEUTRAL braindump (deliberately names NO characters, so any cast in the output
  is the *model's* choice, not the prompt's):
  - **BLIND** — `ground_on_existing=false`. (Note: the always-on `_ground_llm_source` STILL prepends
    the existing ARC digest, so blind already grounds on arcs — the A/B **delta** is cast+spine+systems.)
  - **GROUNDED** — `ground_on_existing=true`, ceiling ON. The full EXISTING STATE block (arcs+cast+
    spine+systems) is prepended + the CONTINUITY rule active.
- **Metric** — of the 3 existing cast names / 3 existing arc titles, how many the proposed spec
  references (substring match over the spec JSON) + the `layers.characters[].name` list.

## Results (two runs; the 2nd after strengthening the CONTINUITY→name-override prompt rule)

| run | condition | proposed cast | cast continuity | arc continuity |
|---|---|---|---|---|
| 1 | BLIND | `['Nữ chính']` | **0/3** | 3/3 |
| 1 | GROUNDED | `['Nữ chính']` | **0/3** | 3/3 |
| 2 | BLIND | `['Nữ chính']` | **0/3** | 3/3 |
| 2 | GROUNDED | `['Nữ chính']` | **0/3** | 3/3 |

**Both runs: TIE.** Grounding added **nothing** to cast continuity. Arc continuity is 3/3 in ALL cells
— but that is the BASELINE arc digest (`_ground_llm_source`), present in blind too, so it is not a
grounding win; it is the pre-existing behaviour.

## Root cause of the null result (measured, not guessed)
1. The neutral braindump has **no character content**, so analyze extracts no cast → materialize emits
   none → `normalize_spec._pad_traits_from_analyze` **pads a single `Nữ chính` placeholder**. The
   "Nữ chính" is a NORMALIZE artifact, not the model ignoring grounding.
2. Prompt grounding makes the model *reference* existing entities when it generates related content —
   it does **not make the model INVENT a cast** the braindump never asked for. So with a character-less
   braindump, there is no cast for grounding to anchor.
3. Strengthening the CONTINUITY rule (run 2: "existing names OVERRIDE the Nữ chính default") did not
   change the outcome — there was still no generated cast to name.

## Decision (evidence-based)
- **Keep `PLANFORGE_GROUND_ON_EXISTING_ALLOWED=false`** (ceiling OFF). The eval did NOT prove grounding
  improves the plan, so per OQ-2 the flip does not happen. The feature stays dark + fails-closed.
- This is the eval working as designed: it stopped a generation-quality claim that isn't real. The
  PROPOSE-BLIND plumbing is correct + safe (grounded_on records, fails-closed, arc grounding + the
  deterministic rules-path merge all live-proven) — but the **LLM cast-grounding payoff is unproven**,
  so it does not ship on.

## What IS proven to work (from the build's live smokes, not this A/B)
- **grounded_on** recorded with fingerprint + counts; **fails-closed** (blind ⇒ null).
- **Rules-path merge-not-duplicate**: a re-declared arc annotated `continues_existing=true`, a new one
  `false` (deterministic, no model needed) — the reliable mechanism.
- **Systems** now populate live ("4 variable(s) in play").

## Follow-ups for whoever revisits (to make grounding actually help)
1. **Character-rich braindump eval** — re-run with a braindump that asks for a protagonist's
   continuation; measure whether grounding then anchors to existing names vs invents. (This A/B tested
   the pure-injection hypothesis and refuted it.)
2. **Deterministic protagonist injection** — rather than rely on the prompt, have the gather lens seed
   the existing protagonist into `layers.characters` directly (like the rules-path merge carries
   entity_ids), so continuity does not depend on model compliance.
3. **Stronger model** — re-measure on a larger model; the 26B local model did not follow the
   name-override rule even when strengthened.
4. **De-fixture the propose prompts** — the MATERIALIZE/ANALYZE system prompts still carry POC-fixture
   rules (the Arc-2-7-events / "Nữ chính" hardcodes) welded to one novel; they compete with grounding.
   (Same "fixture severing" the rules-path `propose.py` already did; the LLM prompts still need it.)
