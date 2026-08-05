# CP-1 · round 10 · V-CODE — the prompt, committed BEFORE the verifiers run

**Scope: R9's delta only.** Items with an independent PASS from rounds 1–8 are not re-graded.

R9 returned FAIL twice on thirteen findings, and the headline is why this round exists: **the sink
drain sat behind an event a tool-free turn never emits, and a catalogue outage is what makes a turn
tool-free — so the record path was disabled by the event it exists to record.** Three of the four
live turn shapes persisted `NULL` while the sink held the row. Every round before that had argued
about whether the row was *written correctly*; nobody had asked whether it **arrived**.

**Ask that question about everything this round.**

**Artifact:** the commit named in the deployment message. Report `git rev-parse HEAD` at start and
finish. **Modify no tracked file** except your own verdict. **Never `git checkout`.** Inject against
a scratch copy or an out-of-tree pytest plugin.

---

## Standing rules

* **A `PASS` with no stated falsifier is `CANNOT DETERMINE`.**
* **EXECUTE, do not read.** Rounds 5–9 each shipped a defect that source-reading had blessed.
* **Gate behaviour, not shape.** Declared types, source text, and a self-mutated fixture are all
  vacuous — all three have shipped green over live defects in this run.
* **Measure the baseline yourself.**
* The builder has now been wrong about **P4 three times**, **U-2's wiring three times**, and has
  three times applied a correction to **one member of a set** — most recently an identity check that
  reached 1 of 3 sites.

---

## Verifier A — does the record ARRIVE, on every path?

1. **The drain.** `AdvertisedToolsRecorder.absorb` + `bind_sink` + a drain inside `withheld_json()`.
   **Drive all four turn shapes** (fresh chat, agui+editor, admin, resume) and **voice**, and for
   each report whether the row reaches the value that is persisted. Then ask the round-9 question
   one level further out: *is there a path where `withheld_json()` itself is never called?* Cancel,
   crash, an early `return`, an exception before the terminal handler, a suspend that never resumes.
2. **Double-counting.** `absorb` is now called from two places (the advertise event, and
   `withheld_json`). Can a row be recorded **twice**, or recorded with the **wrong pass number**?
   Can a mid-turn checkpoint plus a terminal write produce a duplicate through
   `segment_merge_sql`?
3. **Voice.** It has a recorder, a `withheld_tools` column, and the notice. `advertised_tools` is
   deliberately `NULL`. Drive a voice turn with a failing catalogue and confirm both halves; then
   look for the voice-shaped sibling of anything you find.
4. **The widened arm-order gate** — it sweeps `app/services` and `app/routers`, closes helpers
   transitively, and carries a `_NOT_A_TURN` allow-list with written reasons. **Find route nine.**
   Consider: a lambda, a method on a class, a dynamic dispatch, a narrowing behind
   `getattr`, an entry point in a module outside both directories, and whether `_NOT_A_TURN`'s
   entries are each **actually** not a turn — one wrong entry is a permanent hole with a reason
   attached.
5. **The five catalogue branches.** Are there six? Enumerate every `return []` in both doors.

## Verifier B — 1.8a's bounds, and the manifest after the backfill was removed

1. **`_is_exactly` is now the single identity helper.** Verify it is used at **every** site that
   decides a type, and find the site that still does not use it. Then attack the helper: can a
   metaclass, `__class__` property, or `__instancecheck__` defeat `type(x) is y`?
2. **`op`, `direction`, `field`, `cost_field`, `k`, `budget`, `names`, `keys`, `stage`, `reason`,
   and the row-side `cost` are all bounded.** **Find the operand that is not.** Include anything
   reaching `canon`, `asdict`, the `ordered_by` record, and `Surface.withheld`.
3. **The backfill is gone and `load()` is strict.** Confirm no old-shape document is silently
   accepted, and confirm `validate_document` no longer mutates its argument — including nested
   objects, not just the top level.
4. **`build()` refuses to lose a declaration.** Re-verify after this round's changes, and check the
   interaction with the drift gate's `build([])`.
5. **The P4 defect-assertion test.** It now asserts the amendment took. **Try again to make it pass
   for the wrong reason**: a partial amendment, an amendment that changes only one of the two
   bindings, zero rows, `build` raising, a fixture that never had two declarations.
6. **The `pass` scope** was added to §0.14.3 and to the recorder. Is the spec's table now true of
   the code, for **all three** row shapes — including what reaches the database column?

---

## What both verdicts must contain

* The falsifier per claim, stated before the search.
* A **bypass table**, a **red-ability table** with your own baseline, and a **sibling table**.
* `git rev-parse HEAD` at start and finish.

Write to `verification/CP-1-round10-v-code-{a,b}.md`.
