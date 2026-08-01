"""composition-service's evaluation instrument (spec §S10).

Why this package exists when nine `scripts/eval_*.py` already do
----------------------------------------------------------------
There were 2,279 lines of eval harness in `scripts/`, covering nine distinct concerns
(cold-start coherence, decompose, motif select+bind, dropped promises, conformance
calibration, …). None of it runs anywhere automated — verified against every workflow — and,
the part that matters, **only one of the nine SEEDS a defect at all**: `eval_a2_canon.py`,
which plants a gone-cast contradiction and asserts the engine detects it.

Scoring real output tells you how good today is. It cannot tell you a later slice BROKE
something, because there is no known answer to regress against. That is what the spec means
by *"a baseline whose known-defect set is one cannot detect a new defect a later slice
introduces"*.

The defect the existing harness has, and this package fixes
-----------------------------------------------------------
`eval_a2_canon.py` runs five scenarios — all the SAME class — and gates on
`status=="checked" AND iterations>=1`, the detector FIRING. **No negative control exists in
any of the nine scripts** (verified 2026-07-31). So it cannot separate these two worlds:

  * the canon loop works — fires on a contradiction, quiet otherwise
  * the canon loop fires on EVERY scene, contradiction or not

Both print "5/5 detected · PASS". The second is a broken engine with a green eval, which is
worse than no eval: a guarantee with nothing behind it, wearing a number.

So every class here carries a **control** — the same scenario with the defect removed — and
counts as detected only when its detector fires on the seeded variant AND stays quiet on the
control. That is a 2×2, not a hit count, and `loreweave_eval.calibration.confusion` already
computes it.

What runs where
---------------
`gate.py` is the static half: CI, no stack, asserts the registry can MEASURE (enough classes,
every one controlled, no shared or constant detectors, and the scorer punishes a
control-firing class). `suite.py` is the live half — it needs a driver that can seed a book
and generate. Splitting them is deliberate: an instrument that only runs against a live stack
rots exactly the way the nine scripts did, and every failure reads as "no stack today".
"""

from app.eval.defects import DEFECTS, DefectClass, Observation, Outcome
from app.eval.suite import ClassResult, SuiteResult, score_class, score_suite

__all__ = [
    "DEFECTS", "DefectClass", "Observation", "Outcome",
    "ClassResult", "SuiteResult", "score_class", "score_suite",
]
