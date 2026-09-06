# CP-1 · round 21 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R20's delta** (`3caac262d` + `ad4e69030`). Items with an independent PASS from rounds 1–20
are not re-graded.

R20 answered the termination question and both verifiers agreed: **no convergence, close against the
mechanised census, stop V-CODE.** The criterion is the PO's to change and that decision is open, so
**this round runs under the existing criterion** — with one difference that matters.

## ▶ The delta is a GATE, so grade it as one

The census (`scripts/agentruntime-census.py`) is the first thing this run has shipped whose purpose
is to make *"a finding is closed"* mechanical. **If it is wrong, every future closure is wrong.**
Grade it before anything else:

1. **Can it be defeated?** A refusal that stays SILENT while the suite still passes is its subject —
   but what about a refusal it cannot *see*? `assert`, `sys.exit`, a `return None` where a raise
   belonged, a raise inside a `lambda`/comprehension, a raise in a module the glob misses, a
   conditional import. Enumerate the shapes it does not enumerate.
2. **Is its allowlist honest?** 13 sites are recorded SILENT. Verify each is genuinely unguarded and
   that none is SILENT for a *harness* reason — a neutered `raise` inside a `try` whose `except`
   swallows it would read SILENT while being perfectly guarded.
3. **Does it fail closed?** It restores bytes and asserts them; its selftest fires in both
   directions. Kill it mid-run and say what the tree looks like. Give it a syntactically broken
   module and say whether it skips or stops.
4. **Is the id stable?** The key is `module::qualname::ExcClass::ordinal`. Reorder two raises of one
   class in one function and say what the allowlist does. An allowlist that goes stale silently is
   worse than none.

## ▶ The claim I am NOT allowed to settle

R20-A found the ordering argument may concern **unreachable states**: if the design's own premise
holds — *"each request runs in its own task and therefore its own context copy"* — five rounds were
about impossible states, and if it fails, the delta makes the system worse. **That is not answerable
from source and I must not answer it from source.** State plainly what would answer it and who owns
that question.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE over an ENUMERATED space, not a chosen sample.** R20-A's sentence is now a standard here:
  *execution over a hand-picked sample is argument wearing a lab coat.* Nine hand-picked orderings
  certified a patch that regressed 584 of 30,948.
* **A fix without a red-able test is not a closed finding.**
* **Derive your own denominator.**
* Builder's record over thirteen rounds: seven findings fixed at what a verifier pointed *at* rather
  than what it *meant*; **three refuted negative claims**; five self-measurements wrong in the
  flattering direction; records that contradicted each other, then agreed on a false sentence, then
  dropped four items while restoring two; and a harness that reproduced a defect a verifier had
  recorded one round earlier.

---

## Verifier A — the instrument

1. **The census gate** — items 1–4 above are yours as much as B's; split by what you can defeat.
2. **The `recorder=` door is now type-bounded and the carried case has a test.** Verify the test
   drives the hazard rather than describing it, and that the bound does not make a legitimate caller
   crash.
3. **W4's rule shipped as one token** (`s.body[:1]`). Verify 9/9 and find what the narrowing left.
4. **The three weak oracles are four rounds old** and unfixed. Say whether they are worth fixing or
   whether the tests they guard should go.
5. **T11d, the probe modules in the live tree, and the `:531`/`:542` contradiction** — all carried.
6. **Convergence**, raw, plus executed-vs-argued **over an enumerated space**.

## Verifier B — the membrane

1. **The census gate** — items 1–4 above.
2. **`dict(r)` is SHALLOW**: all four doors hand back the source document's own `members` list.
   Confirm, and say whether a deep copy is the fix or whether the row should be frozen.
3. **B18-8, B18-11 and B18-10** are open at three, three and six rounds. Re-measure all three.
4. **B20-4**: my corrected `Open, carried` list restored two and dropped four. It is corrected again
   in R20's block. **Audit it against every verdict**, and say whether the record is now trustworthy.
5. **`surface.py:305` and `_ID`'s missing length bound** — carried.
6. **Convergence**, plus one new falsifiable prediction.

---

## What both verdicts must contain

* **The census verdict first** — it is the mechanism every future closure would rest on.
* The falsifier per claim, a **bypass table**, a **red-ability table with your own denominator**, a
  **sibling table**, a **guard table**, a **reachability verdict on every finding**, and the
  **executed-vs-argued ratio**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round21-v-code-{a,b}.md`.
