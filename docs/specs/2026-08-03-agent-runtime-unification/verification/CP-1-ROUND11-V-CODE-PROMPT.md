# CP-1 · round 11 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R10's delta only.** Items with an independent PASS from rounds 1–10 are not re-graded.

R10's one-sentence verdict was *"round 10 made the row arrive, and nothing in the tree would notice
if it stopped"* — the mechanism worked and **everything holding it up was absent**. R10's fixes are
therefore mostly *guards*, and a guard is the easiest thing in this codebase to get wrong: three of
the last four rounds found a gate that was green over the live defect it named.

**So grade the guards, not the mechanism.**

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.**

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read.** Rounds 5–10 each shipped a defect that source-reading had blessed.
* **For every guard added this round, ask the two questions in order:** *can it fail?* and *does it
  fail for the reason it names?* A guard that reds for the wrong reason is a guard that will be
  deleted the first time it is inconvenient.
* **Measure the baseline yourself.**
* The builder has, in this run: recreated a crash inside the function written to fix it; fixed what
  a verifier pointed **at** rather than what it **meant**, twice; and shipped three gates that were
  green over the defect they were written for.

---

## Verifier A — the guards around arrival

1. **Sink adoption moved into `AdvertisedToolsRecorder.__init__`.** Drive it. Then break it: is
   there a construction order on any real path where the recorder is built **before** the sink is
   armed? `_emit_chat_turn`, the resume path, voice, a subagent call, a background task, a recorder
   built at import. Report per path.
2. **`test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE`** reads the parse tree for
   `withheld_tools=` keywords. **Defeat it**: bind the value through a local variable, a helper, a
   dict spread, a positional argument, or a fifth write site it does not see. Does it count *every*
   site that persists the column, including the orphan-stamp `UPDATE` and voice's INSERT?
3. **`test_NO_ALLOW_LIST_ENTRY_IS_STALE`** refuses an exemption the sweep cannot see. Can an entry
   be **wrong** and still discovered — i.e. does anything check that a `_NOT_A_TURN` member is
   genuinely not a turn, as opposed to merely visible?
4. **The gate now walks the whole tree and closes over a name→[functions] index.** Find **route
   fifteen**. Consider: a narrowing behind a decorator, inside a `try`, in a comprehension, reached
   through `functools.partial`, through a class attribute, through a module-level alias assigned at
   import, or in a module under `app/` outside `services/` and `routers/`.
5. **The admin cache.** `[]` is no longer cached and a zero-tool fetch registers. Check the
   **non-admin** cache for the same shape, and check whether a *successful* fetch that returns zero
   tools on the user path registers anything.
6. **`absorb`'s unknown-scope branch** records rather than drops. Verify it cannot crash on any row
   shape at all — missing keys, non-string values, a row that is not a dict — and that what it
   records is readable rather than merely present.

## Verifier B — the bounds, the pipeline, and the P4 test

1. **`pipeline = list(pipeline)`.** Verify the TOCTOU is closed for `assemble`, and then find the
   **other** places in the package where a caller-supplied iterable is consumed more than once, or
   where a value is read twice between a check and a use.
2. **`rows_of` now validates row shape (`dict`, non-empty plain-`str` id).** Find the row field that
   is still unbounded and reaches a decision — `kind`, `members`, `lifecycle`, `owning_service`,
   anything a stage reads. And check the doors that do **not** go through `rows_of`.
3. **The P4 defect-assertion test now drives the carry-forward path** and expects
   `UntrustedRow("IS NOT BUILT")`. **Build §6.4's grandfathering yourself** — as round 10's verifier
   did — and confirm the test **reds**. Then try to make it red *for the wrong reason*, and try to
   make it green with the mechanism present.
4. **`previous={"declarations": None}`** is refused. Enumerate the other malformed `previous` shapes
   and report which are accepted.
5. **`_seen` now prefixes scoped keys with `#`.** Confirm the two namespaces cannot meet, including
   for a declaration id that itself starts with `#`.
6. **The second dispatch now routes through `absorb`.** Confirm there is exactly one place that
   knows the scope enum, and that the legacy `"*"` translation cannot mint a `tool` key again.

---

## What both verdicts must contain

* The falsifier per claim, stated before the search.
* A **bypass table**, a **red-ability table** with your own baseline, and a **sibling table**.
* **A guard table**: for each guard added this round — *can it fail?* / *does it fail for the reason
  it names?*
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round11-v-code-{a,b}.md`.
