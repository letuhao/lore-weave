# CP-1 · round 13 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R12's delta, plus the six findings R12 recorded OPEN.** Items with an independent PASS from
rounds 1–12 are not re-graded.

Four rounds have each returned FAIL, and the builder's fixes have twice made things worse in a new
way. **This round adds one question the previous four did not ask, and it is the most important one
here:**

> **Is what you found reachable in production, or only by an adversary who already controls the
> input?** Say which, per finding, and say how you decided.

That is not an invitation to soften anything. A hand-typed manifest row **is** in scope — the
membrane exists because a text editor is a writer this code does not have. But *"a `dict` subclass
whose `.get` mutates the caller's list"* and *"the outage notice appears on a turn with no outage"*
are different kinds of fact, and the board cannot weigh them if the verdict does not separate them.

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read.** **Verify your injection took effect** before concluding from a green run
  — patch every binding (module, package re-export, test module) and print the check.
* **A fix without a red-able test is not a closed finding**, however correct the code is.
* The builder's record over four rounds: a crash recreated inside the function written to fix it,
  four times; a verifier's finding fixed at what it pointed **at** rather than what it **meant**,
  four times; **a headline fix that closed a shape nobody had reported while the eight measured
  routes stayed open**; and **two defects introduced by the fixes themselves** — one of which
  (a `ContextVar` outliving its turn) would not have been visible in production until a user saw it.

---

## Verifier A — the arming, the flag, and the guards

1. **Arming now ADOPTS, and the outage fact is a `ContextVar` DERIVED from the rows.** Attack the
   new shape: can the derived flag be wrong — stale rows in a reused context, a sink mutated after
   arming, a subagent, `asyncio.create_task`, a thread pool? Can adopting now carry a **previous
   turn's** rows into this turn's column?
2. **The row/notice contradiction.** Confirm it is closed on every construction order, and find any
   remaining path where the persisted row and `catalogue_outage_registered()` disagree.
3. **`_as_text` is exact-typed and `absorb` coerces the container.** Feed it what the parametrised
   test does not.
4. **The terminal-write gate still has the `Name` escape hatch, recorded OPEN.** Confirm it, and say
   whether the hatch is reachable by an ordinary refactor or only by someone trying.
5. **Route sixteen and the wrong `_NOT_A_TURN` reason, recorded OPEN.** Confirm both, and find route
   seventeen.
6. **`[]`-not-cached has no test, recorded OPEN.** Confirm, and check the user door's 60 s cache.

## Verifier B — the manifest and the bounds

1. **`validate_document` returns what it validated.** Find the remaining way to hand a consumer a
   row the validator did not check — through `load`, `declarations`, `rows_of`, `SurfaceAssembler`,
   `discover`, or the drift gate.
2. **The outer `previous` is checked.** Find the fifth TOCTOU, or state that you searched every
   read-twice in the package and found none.
3. **The `r.get("id")` / `r["id"]` split, recorded OPEN.** Measure what it still permits.
4. **The P4 defect-assertion test is still green if the mechanism lands in `generate()`, recorded
   OPEN.** Confirm by building it there, and say whether that landing site is the likely one.
5. **The guard axis, again**: inject every fix in `app/agentruntime/` from this delta and report
   green/red. Last round it was 5 of 5 silent.
6. **Convergence, as a measurement rather than an impression.** Across rounds 9–13, classify every
   finding you can see in the verdict files as **production-reachable** or **adversarial-input
   only**, and report the two counts per round. If the first is falling and the second is not, say
   so. If neither is falling, say that.

---

## What both verdicts must contain

* The falsifier per claim, stated before the search.
* A **bypass table**, a **red-ability table** with your own baseline, a **sibling table**, and a
  **guard table**.
* **A reachability column on every finding**: production-reachable, or adversarial-input only.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round13-v-code-{a,b}.md`.
