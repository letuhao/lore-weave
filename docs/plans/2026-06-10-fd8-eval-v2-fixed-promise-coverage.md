# FD-8 eval v2 — fixed-promise-set coverage + chapter-mode (the discriminating eval)

**Cycle:** LOOM-68 · **Size:** M · **Branch:** `feat/composition-service`
**Why:** the FD-8 v1 dropped-promise-rate eval returned NULL (LOOM-67). A strong-judge
hand-read of the dumps (this session) showed the null was a **measurement artifact**, not
a feature failure. v2 fixes the three confounds.

## What v1 got wrong (diagnosed by reading the prose, not the metric)

1. **Unstable denominator (introduced-inflation).** v1 let the judge freely list
   `introduced` per arm; re-injection makes the ON arm *surface more* promises into prose →
   bigger denominator → the RATE moves for a reason unrelated to quality. (Book 2: OFF
   "introduced 12" beat ON "introduced 7" on rate while ON actually resolved more.)
2. **Cutoff = "dropped".** v1 scored a promise unpaid-at-the-text-end as "dropped". But
   per_scene+short-token arcs are **truncated before the climax**, so sustained tension was
   mislabeled as a drop — and the ledger *deliberately sustains* open promises (its design),
   so it was penalized for working.
3. **Coarse local judge.** gemma's free-form audit couldn't separate "resolved" from
   "rambled-then-abandoned".

## v2 design (this cycle)

### Metric — fixed-promise-set coverage
- **`extract_tracked_promises(premise, plan)`** — derive a FIXED promise set from the SPEC
  (premise + outline), NOT either arm's prose → **identical for both arms**, denominator
  stable. (`/internal/composition/eval/promise-extract`)
- **`score_promise_coverage(promises, arc)`** — score each fixed promise against one arm's
  prose: **paid / progressing / abandoned / absent**. (`/promise-coverage`)
- Rates (denominator = `introduced` = paid+progressing+abandoned; absent excluded):
  - **pay_rate** = paid/introduced (resolved; higher=better) — the discriminator.
  - **abandon_rate** = abandoned/introduced (the *real* drop; lower=better).
  - **sustained_rate** = (paid+progressing)/introduced (NOT-a-drop).
- Separating ABANDONED (real drop) from PROGRESSING (sustained tension at cutoff) is the key
  fix for confound #2.

### Generation mode — chapter (reaches payoff)
v1 ran per_scene (truncates before the climax) → pay_rate≈0 for BOTH arms (can't
discriminate). The harness now defaults to **chapter single-pass** (`--mode=chapter`), which
reaches the arc's payoff (proven: the chapter-mode probe ended on Kael's redemption). Only
then can pay_rate move.

## Code
| File | Change |
|---|---|
| `app/engine/promise_audit.py` | `+extract_tracked_promises`, `+score_promise_coverage`, `+_coverage_shape/_parse_coverage`, shared `_chat` helper. Ledger-blind, reasoning-disabled, degrade-safe, div-by-zero-guarded. |
| `app/routers/internal_eval.py` | `+/promise-extract`, `+/promise-coverage` (X-Internal-Token). |
| `scripts/eval_narrative_thread.py` | v2 scoring (extract once from premise+plan, coverage both arms) reported alongside v1; `gen_chapter` + `--mode=chapter` (default) so arcs reach payoff; v1/v2 side-by-side summary. |

## Tests
- `test_promise_audit.py` +11: coverage parse (verdict→counts/rates, index-align, missing→absent, bad-token→absent), zero-introduced no-div, extract happy+degrade, coverage empty-set short-circuit, LLM-error all-absent, reasoning-disabled, both endpoints happy+token.

## VERIFY (evidence)
- Full composition unit green (392).
- **Live cross-service**: rebuilt composition (v2 endpoints), ran the harness on the real
  stack. **n=1 chapter-mode: v2 pay-rate OFF=0.33 → ON=1.00 (Δ+0.667)** — the lift v1 hid.
  Powered **n=3 chapter-mode** = the conclusive run (recorded in SESSION).

## Result headline (to fold in at SESSION after n=3)
v2 + chapter mode makes the eval **discriminating**. n=1 shows a large pay-rate lift for the
ledger; n=3 confirms/bounds it. If the lift holds → the FD-8 null is overturned: the ledger
DOES help when arcs reach payoff → reconsider the Phase-B expansion gate.

## /review-impl
Run at POST-REVIEW (new judge abstractions + new endpoints). Focus: the fixed-set is
spec-derived not prose-derived (the whole validity rests on it); absent-default conservatism;
rate denominators; chapter-mode reinjected-count semantics.
