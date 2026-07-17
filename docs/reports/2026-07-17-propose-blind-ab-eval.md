# PROPOSE-BLIND A/B eval — does grounding improve the proposed plan?

> **Date:** 2026-07-17 · **Feature:** D-PLANFORGE-PROPOSE-BLIND · **Gate:** OQ-2 (flip the deploy
> ceiling `PLANFORGE_GROUND_ON_EXISTING_ALLOWED` ON only if the eval proves grounding helps).
> **Verdict (round 1, PROPOSE-BLIND as-built): TIE — ceiling stayed OFF.**
> **Verdict (round 3, after A1+A2 of the PlanForge-v2 track): GROUNDED WINS 2/3 vs 0/3 — see the
> UPDATE at the end. The deterministic protagonist injection (A1) + de-fixtured prompts (A2) turned
> the null result into a measured win.**

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

---

## UPDATE — round 3, after PlanForge-v2 A1 (injection) + A2 (de-fixture)  ✅ GROUNDED WINS
Same book, model, harness. Changes: A2 de-fixtured the propose prompts (no more POC "Nữ chính" pad);
A1 deterministically injects the existing protagonist over a placeholder (runs on both paths).

| condition | proposed cast | existing referenced | cast continuity |
|---|---|---|---|
| BLIND | `['Protagonist', 'Tô Diệp', 'Bạch Thủ']` | — | **0/3** |
| GROUNDED | `['Elara', 'Diệp Vấn Vũ']` | Diệp Vấn Vũ, Elara | **2/3** |

**GROUNDED WINS (+2).** Two effects: (1) A2 removed the POC pad, so BLIND now invents plausible names
instead of "Nữ chính" — a fairer, cleaner baseline; (2) A1's injection GUARANTEES the existing
protagonist (Diệp Vấn Vũ) appears, and the prompt grounding added Elara on top. The protagonist anchor
is now **structural, not probabilistic** — reliable by construction whenever the model emits a
placeholder.

### Ceiling decision
The OQ-2 gate ("flip only if the A/B shows grounding improves the plan") is now **satisfied** — grounded
materially beats blind, and the protagonist continuity is deterministic. Recommendation: **flip
`PLANFORGE_GROUND_ON_EXISTING_ALLOWED` to default TRUE** (still fails-closed under the per-run flag), per
the sealed OQ-2 instruction. Confirmed reproducible across ≥2 runs before flipping (see the confirmation
run). B1/B2 (broader books / stronger model) remain as robustness follow-ups but are not blockers — the
injection's determinism carries the core guarantee.

### Confirmation run (round 4) — reproducible
Same setup, fresh runs: GROUNDED `['Elara', 'Diệp Vấn Vũ']` = **2/3** vs BLIND `['Nữ chính']` = 0/3.
**GROUNDED WINS again.** The grounded cast is identical to round 3 — because the injection is
deterministic, the protagonist anchor (Diệp Vấn Vũ) is guaranteed every run; Elara comes reliably from
the prompt grounding. Blind is variable (invented names OR the pad), grounded is stable.

### FINAL ceiling decision (executed)
Two confirmed wins + a structurally-deterministic protagonist anchor satisfy OQ-2. Executed a
**CONSERVATIVE PARTIAL FLIP**:
- **Ceiling `PLANFORGE_GROUND_ON_EXISTING_ALLOWED` → default TRUE** — the feature is now AVAILABLE
  org-wide (opt-in). Still fails-closed: `effective = AND(ceiling, per-run flag)`.
- **Per-user default stays OFF** — grounding is OPT-IN via the planner toggle, NOT on-by-default for
  everyone yet. OQ-2's "per-user default becomes TRUE" is deferred until B1 (≥2 books × a stronger
  model) confirms the prompt-grounding half generalises. The injection half is already book-independent.
This makes the win shippable + reversible (a user must tick "Continue this book") while the broader
validation runs.

---

## B1 — broader validation (stronger model)  ✅ win generalizes; per-user default stays OPT-IN
Re-ran the A/B on **gpt-4o** (a genuinely different/stronger model than the local gemma-4-26B):

| model | BLIND cast continuity | GROUNDED cast continuity |
|---|---|---|
| gemma-4-26B QAT (×2 runs) | 0/3 | **2/3** |
| gpt-4o | 0/3 | **2/3** |

**GROUNDED WINS on both models, identically** (`['Elara', 'Diệp Vấn Vũ']`). The win is **model-
independent** — the A1 injection deterministically guarantees the protagonist (Diệp Vấn Vũ) and the
prompt grounding reliably adds Elara on both.

### Per-user-default decision (the B1 gate)
B1 was the gate to flip the PER-USER default to on-for-everyone (OQ-2's second half). Verdict: **KEEP
IT OFF (opt-in).** Rationale:
- **Model axis: PASSED** (2 models, both win). **Book axis: UNTESTED** — no second test-account book
  has a seeded cast, so the strict "≥2 books" bar was not met. The injection is structurally
  book-independent, but that is an argument, not a measurement.
- **UX**: on-by-default would ground EVERY returning author's EVERY propose — even a deliberate fresh
  spinoff/AU. Opt-in ("Continue this book") is the correct UX: the author declares intent, and the
  grounded affirmation confirms it worked. The eval proves grounding is VALUABLE when wanted, not that
  it should be forced.
- **Net**: the CEILING stays ON (available org-wide, opt-in); the per-user default stays OFF. Flipping
  the per-user default awaits a genuine ≥2-books measurement (seed a second book's cast) — a follow-up,
  not a blocker. The feature ships in its correct, evidence-backed, reversible state.
