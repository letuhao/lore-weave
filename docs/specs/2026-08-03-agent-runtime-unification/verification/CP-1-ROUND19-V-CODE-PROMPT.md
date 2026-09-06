# CP-1 · round 19 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R18's delta** (`7bb963db9`). Items with an independent PASS from rounds 1–18 are not
re-graded.

R18 settled three things at once: my probe was wrong three times in three different ways, the two
records of the same finding disagreed, and a fix of mine blinded five detections that already
worked. **The instrument, the record and the fix each failed separately**, so this round grades all
three, and two of them before the code.

## The two predictions R18-B made in advance — settle them first

Each is one command on this artifact, and settling them is worth more than a new finding, because a
prediction made before the delta is the only evidence this run has produced that can distinguish a
process improving from a series of flattering numbers.

* **P18-B1** — fixing B18-2 at the anchor leaves the *class* alive: the CP-2 injection will still
  leave **≥1** test red. *Falsified if it yields `0 failed`.*
* **P18-B2** — B18-1 was closed by rewording: neutering its assertion to `assert True` will still
  leave **both** drift injections RED (i.e. the assertion contributes 0 of 2). *Falsified if either
  goes GREEN.*

Report each as HELD or FALSIFIED with the command and its output. **Do not soften a falsification** —
a prediction that fails is the most useful result available, because it means the model of this
codebase that produced it was wrong in a locatable way.

## The axis R18-A proposed, now standing

For every load-bearing claim in the graded delta, record whether it was established **by execution**
or **by argument**. R18-A's finding was that the executed claim was correct and the argued one was
false, 1:1. **Report the ratio.** A rate cannot see this and every rate in this run has flattered.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read. Verify each injection took effect**, and **verify it is the injection you
  meant** — R18 proved that deleting a wrapper and downgrading it read identically green, and that a
  fixture chosen for convenience answered a different question than the one being asked.
* **A fix without a red-able test is not a closed finding.**
* **Derive your own denominator.** Mine was 11; the last two verifiers derived 48 and 87.
* Builder's record over ten rounds: five crashes recreated inside their own fixes; six findings
  fixed at what a verifier pointed *at* rather than what it *meant*; guards loosened, deleted and
  made vacuous while comments denied it; **two consecutive rounds where the refutation was a
  sentence the builder wrote and did not re-read**; four self-measurements wrong in the flattering
  direction; a probe wrong three ways in one round; and **two records of one finding that
  contradicted each other**.

---

## Verifier A — the instrument

1. **The SQL matcher is reassembled** (every string in the expression, whitespace-normalised).
   Verify all five previously-blinded spellings are caught again **and** that `db/migrate.py` stays
   out. Then find the sixth spelling.
2. **One narrowing predicate now serves both the `Try` rule and the delegation filter.** Verify the
   two agree on every shape, and check whether unifying them widened the exemption anywhere.
3. **W4 and W7 were still green at R18.** Confirm, and say whether the `Try` rule's subset is now
   right or merely different.
4. **`G01` and `G12` have been silent for four rounds**, asked for by name twice. Either construct
   the guard or state plainly that the property has no subject — with the execution that shows it.
5. **The outage residual is recorded OPEN and "unaddressable by this variable."** That is another
   negative claim from the party who benefits. **Attack it**: is there a mechanism *outside*
   `catalogue_outage` — not a turn identity — that closes the seventh ordering?
6. **Convergence**, raw and per changed line, plus the executed-vs-argued ratio.

## Verifier B — the membrane

1. **Settle P18-B1 and P18-B2** (above) before anything else.
2. **The three restored holes have tests.** Verify each reds for the reason it names, and check I did
   not repeat the probe error — that the test's vehicle exercises the clause it claims, not a
   different refusal that happens to fire first.
3. **Four raise sites got guards** (`Filter` field, `OrderBy` keys, `TakeWhileBudget` cost field,
   `pipeline = list(pipeline)`). Find the sixth unguarded one, with your own denominator.
4. **B18-10 — a fifth exported door — is now four rounds old.** Re-measure and say whether the
   scoping to CP-2 is still honest.
5. **The record.** R18's commit message and RUNSTATE block both now claim the same three holes.
   Verify that against the verdicts, and check no other finding has drifted between the two.
6. **Convergence**, and one new falsifiable prediction settleable next round.

---

## What both verdicts must contain

* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round19-v-code-{a,b}.md`.
