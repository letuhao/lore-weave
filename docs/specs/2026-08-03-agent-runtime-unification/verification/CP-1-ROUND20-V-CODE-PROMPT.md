# CP-1 · round 20 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R19's delta** (`35cf987ce`). Items with an independent PASS from rounds 1–19 are not
re-graded.

---

## ▶ ITEM ZERO — the termination question, and it outranks every finding

**Eleven rounds. Eleven FAIL ×2.** `introduced`, raw: `2,1,2,1,3,2,4,3,2,2,2` — **no direction in
eleven rounds**. Closure has moved 14 → 10 → 8 → 27 → 54 → 25–37 → 22–28 → 36–41, and both R16-B and
R18-B showed that movement tracks **delta structure**, not process. Every denominator a verifier has
derived (48, 87, 92) is larger than the last, so every coverage figure so far is a measure of **who
looked hardest**, not of what is covered.

**So answer this before you look for anything new, and answer it against evidence you gather:**

1. **Is this loop converging?** Not "did the last round improve" — is there a measurable trend, and
   which measurement carries it? If the honest answer is *no evidence of convergence*, say so.
2. **What would close CP-1?** Name a criterion that is checkable, that this run could actually reach,
   and that is not satisfiable by the builder writing more tests about the builder's own fixes. If
   the right criterion is *"three consecutive rounds at `introduced == 0`"*, say that. If it is
   *"the silent-site census is mechanised in CI and returns a stable set"*, say that. If it is
   *"CP-1 cannot be closed by V-CODE at all and the remaining risk is only visible live"*, **say
   that** — it is a legitimate answer and the most valuable one if true.
3. **Is more V-CODE the right axis?** Eleven rounds have all been V-CODE. Nothing in CP-0 or CP-1 has
   ever been through **V-LIVE**. State plainly whether the largest unmeasured risk is still in the
   source you are reading, or in the running system nobody has exercised.

**These answers are for the PO, not for the builder.** Do not soften them to fit the plan.

---

## The two standing instruments

* **Executed vs argued.** Record, for every load-bearing claim in the delta, whether it was
  established **by execution** or **by argument**. Two rounds, two verifiers: **executed 7/7 correct,
  argued 0/6 correct.** Report the ratio; it is the only measure here that has never flattered.
* **The mechanical census.** Two independent enumerations (87 and 92 `raise` sites + invariants) now
  **agree on the silent set**. Re-derive it. If it agrees a third time, say so — that is the first
  coverage number in this run that could be mechanised into a gate.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read.** Verify each injection took effect **and that it is the injection you
  meant** — a deleted wrapper and a downgraded one read identically green; a fixture chosen for
  convenience answers a different question (both verifiers have now made that error, one about the
  other).
* **A fix without a red-able test is not a closed finding.**
* **Derive your own denominator.**
* Builder's record over eleven rounds: five crashes recreated inside their own fixes; **seven**
  findings fixed at what a verifier pointed *at* rather than what it *meant*; guards loosened,
  deleted and made vacuous while comments denied it; **three consecutive refuted negative claims**;
  four self-measurements wrong in the flattering direction; two records of one finding that
  contradicted each other; and a record whose corrected sentence was still false.

---

## Verifier A — the instrument

1. **The recorder as a second witness** (`instrument.py`, `catalogue_outage_registered(recorder=)`).
   Verify the nine orderings, including `O_R`. Is `O_J` genuinely the only survivor? **Look for a
   tenth.**
2. **`stream_service.py:5642` and `:8176` read the outage without a recorder in scope.** The voice
   path passes one; the chat path does not. Is that a real gap, and what does it cost?
3. **The three weak oracles** (`:3183`, `:3238`, and the new one) — confirm and say which assertions
   they should name.
4. **T11d**: the live SQL is an f-string whose literal column name is the only thing keeping the
   gate's anchor alive. Does the reassembly resolve `FormattedValue` through module constants, as
   `global_sql_names` already does for the executor's arguments?
5. **W4 is four rounds old.** Write the rule R16-A specified, or show why it cannot be written.
6. **The probe modules are written into the live `app/` tree.** Grade the risk and the fix.

## Verifier B — the membrane

1. **`rows_of`'s `dict(r)` now has its own assertion.** Verify it reds for the reason it names and
   that the `validate_document` half was not weakened.
2. **B18-8 and B18-11** were open, unfixed and missing from the board for three rounds; they are back
   on it and **still unfixed**. Re-measure both and state reachability.
3. **B18-10 — a fifth exported door — is six rounds old.** Re-measure. If the scoping to CP-2 is
   still honest, say what would make it dishonest.
4. **`surface.py:305`** (`OrderBy`'s key-pair shape) and **`_ID`'s missing length bound** — grade
   both.
5. **The record.** Verify every claim in R19's RUNSTATE block against the verdicts, including the
   corrected `Open, carried` list.
6. **Convergence**, plus **item zero**, plus one new falsifiable prediction.

---

## What both verdicts must contain

* **Item zero's three answers**, first, with the evidence you gathered for them.
* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round20-v-code-{a,b}.md`.
