# Run-state leftovers — 2026-08-30

**GOAL: every leftover the knowledge-architecture run state left behind is either FIXED or
DECIDED IN WRITING, and a command proves which.**

`2026-08-09-knowledge-architecture-refactor.md` closed at 69/69 and was archived
(`dfa2a799f`). It closed honestly — but "the plan is done" is not "there is nothing left",
and the difference had been living in a session transcript, a handoff paragraph and two spec
sections. This plan is that difference, written down as rows so it can be worked and counted
instead of remembered.

**Nothing here is a blocker.** Every row is something that is *unfinished* or *undecided*, and
the discipline is the same as the plan it follows from: a row may be unfinished; it may not be
undecided. Decide it, spec it, keep building.

RESUME: L3 — event_order still collides when two jobs extract one chapter at once.

## Progress

7 tasks — 2 done, 0 tracked, 5 untouched.

---

## Rows

- [x] **L4** — **`picker-search-live-smoke.sh` runs from nothing.**
  Shipped in `3ff182679` and referenced by no gate, no CI leg, no other script;
  `gate-wiring-gate` reports 118 gates discovered and does not see it, because it does not
  match the `*-gate` discovery shape. A live proof nobody runs is a transcript.
  **Criteria:** it is reachable from something that runs on its own — either wired as a
  gate, or named in a CI leg, or registered so `gate-wiring-gate` counts it and can call it
  unwired. Whatever it becomes, `gate-wiring-gate` must be able to *see* it.
  **Decide, don't drift:** it needs a running stack, so it may be legitimately EXEMPT from
  CI — but then the exemption is declared, with the reason, in the place exemptions live.
  **BITE:** break the wiring (rename it, or drop its registration) → the thing that now knows
  about it goes red. If nothing goes red, it is still unwired.

- [x] **L5** — **the books' search test keeps the blind spot worlds lost.**
  `TestAppendTitleSearchFilter` drives the pure helper twice and calls that "count args are a
  prefix of the page args". Measured on the worlds equivalent: deleting the filter from the
  COUNT left every such subtest GREEN, because the helper it drives is untouched. `total`
  then describes the library while `items` describe the search.
  **Criteria:** the books list builds its page query and its COUNT from one function, the way
  `buildWorldListQueries` does, and a test drives THAT.
  **BITE:** delete the predicate from the books COUNT → red. It is green today.

- [ ] **L3** — **`event_order` collides under concurrent extraction.**
  `b6c8fde13` fixed the deterministic half: the within-chapter index continues from the
  band's maximum instead of restarting at 0. Two jobs extracting one chapter at the SAME time
  still both read that maximum and both write above it.
  **Criteria:** either closed (a reservation, an advisory lock, or a unique constraint that
  makes the second writer retry), or ACCEPTED in writing with the reason and the blast radius
  — how often two jobs can touch one chapter at once, measured, not assumed.
  **BITE:** if closed, two writers racing one chapter must not produce a duplicate
  `event_order`; if accepted, the spec section must name what makes it rare.

- [ ] **L2** — **51 colliding `(project_id, event_order)` pairs in the store.**
  The writer fix stops new ones; it renumbers nothing. Measured on iso 2026-08-30: 51
  duplicate pairs in `g_shared`. Every consumer of the reading axis is reading them today.
  **Criteria:** a decision with a number behind it — backfill and renumber, or accept and say
  what breaks while they stand. `backfill_orders.py` already exists and already imports the
  shared stride, so the cost of the first option is measurable rather than guessed.
  **Rule 6:** iso is authorised for the writes; the dev store is READ-ONLY.
  **BITE:** the collision count is a COMMAND, and after the chosen action it prints what the
  decision says it should — 0 for a backfill, 51 with a recorded reason for an acceptance.

- [ ] **L6** — **`GO_INLINE_CAP` cannot see a cap against a named constant.**
  Measured 2026-08-30 (§22, corrected): `mcp_tools_read.go` caps `limit` against
  `const maxChapterBlocks = 300` and the regex requires `\d+` on both sides, so the site reads
  as uncapped. The batch §22 priced at "7 blind spots + 1 real verdict" is 8 blind spots.
  **Criteria:** the signal resolves a package-level `const NAME = <int>` on either side. A
  **variable** must NOT be accepted — the point of the signal is that the bound is knowable at
  the call site, and `limit = someVar` is not.
  **Then, and only if the batch is small enough to be honest:** §22 step 3, pointing
  `GO_CLAMP_SIGNALS` at `_go_capped_in_scope()` and refreshing the BASELINE by intersection,
  never `--regen`.
  **BITE:** `--selftest` gains a case for the named-constant cap and one for the variable it
  must still reject; break the const resolution → the first reds.

- [ ] **L1** — **`D-T33-CAUSAL-COVERAGE-UNMEASURED`: accepted, never measured.**
  *Does the causal pass work across the whole corpus, not just where it was pointed.* Nothing
  measured it. The 32-pair sheet answers accuracy on TWO chapters and says nothing about
  coverage.
  **Criteria:** a coverage number over a defined denominator, produced by a command anyone can
  re-run — or the deferral restated with what makes it unmeasurable. §4.3 already retracted a
  global `0.34 %` that divided by residue from runs which never touched the pipeline; a ratio
  over a denominator the design did not choose is the failure mode to avoid, not repeat.
  **BITE:** the denominator is named in the output. A coverage figure that does not say what
  it divided by is the retracted number wearing a different hat.

- [ ] **L7** — **4355 legacy per-project `g_<hex>` graphs on iso.**
  Raised during the refactor, never chased. The declared deployment reads `g_shared` keyed by
  `project_id`; these are the pre-migration shape.
  **Criteria:** a decision — drop them on iso (they are isolated-stack residue), or keep them
  and say why. Whichever, the count is printed before and after.
  **Rule 6:** iso only. Dropping a graph on the dev store is not authorised by this row.
  **BITE:** the count command exists and reports the number the decision predicts.

---

## Not in this plan, deliberately

- **The 32 causal labels** (`docs/measurements/2026-08-24-t33-causal-labelling-sheet.md`).
  Drafted and awaiting a signature; `--score` refuses an assistant and that guard is
  untouched. **A hand-back, not a row** — no amount of autonomous work can produce it.
- **§19's five merge-to-main steps.** The PO's instruction on 2026-08-30 was to keep them in
  the handoff and merge later. Listed there, not here, so that this plan cannot be read as
  authorising them.

---

### ✅ L4 2026-08-30 — **the row said I created a defect; measuring found a category of fifteen**

```
is_gate() matched -gate / -lint only
live smokes in scripts/ and scripts/raid/          15
of those matched by the predicate                   0
of those carrying a registry row                    0
after: discovered 118 -> 133, SKIP lines 7 -> 22, GREEN 104 (unchanged)
```

🎯 **The row's framing was wrong and that is the finding.** It read *"a live smoke shipped
today that nothing runs"* and named `3ff182679` as having created the defect. Measured
(rule 8): **fifteen** live smokes exist and `is_gate()` matched **none**. `picker-search`
was the fifteenth to arrive, not the first to be missed. Every one was *absent* from
`gate-wiring-gate` — not exempt, not tracked-red, not skipped-with-a-reason.

🔴 **THE FILE CONTRADICTED ITSELF, AND THAT IS WHY THE CATEGORY STAYED INVISIBLE.** Its
SCOPE section argued the smokes were deliberately out because *"pulling them in would
produce nine SKIP lines and no signal"*. Twenty lines below, `NEEDS_STACK`'s own comment
says of exactly those lines: *"Printed, never silent. A skipped gate that says nothing is
indistinguishable from a passing one, and that is the exact confusion this file exists to
remove."* Both cannot be true. **A SKIP carrying a reason is signal; absence is what carries
none.** The docstring now records which side won and why, rather than being quietly deleted.

📐 **Fifteen rows, fifteen reasons, each read out of the script's own header.** A boilerplate
*"needs a stack"* fifteen times is a row that carries no information and rots unnoticed —
the same defect one level down. `--run-all` now prints each by name with what it does.

⚖️ **What this does NOT do, said out loud.** They still cannot run in CI.
`D-PUBLISHER-SMOKE-NOT-IN-CI` and `D-META-LIVE-SMOKE-NOT-IN-CI` are untouched, and a stack-up
CI job remains the thing that would discharge them. This changes *invisible* to *skipped, by
name, with a reason* — worth having, and not a claim to have solved the other problem. The
scope docstring said widening was for "once a stack-up CI job exists"; visibility does not
need one, and that distinction is now written where the old sentence was.

🧪 **BITE — three, each on a different claim, each red for its own reason.**

```
1 predicate drops -live-smoke (line 132)  self-test: 2 FAILs + gate: stale-row FAIL
2 drop picker-search's registry row       self-test: "live smoke(s) with no registry row"
3 rename the script                       gate exit 1 (stale row) + self-test exit 1
```

⚠️ **Bite 2 exposed something I had to check rather than assume.** The main gate exits **0**
under it — `wiring_report()` short-circuits on `runner_in_ci()` and never computes
`uncovered`. The new check only fires under `--self-test`, so "it reds" would have been a
claim about a command nobody runs. Verified: `.github/workflows/gates.yml:85` runs
`--self-test`. It is wired.

**QC (a) gates:** `gate-wiring-gate --run-all` **104 GREEN, 0 RED, exit 0** — GREEN unchanged
while SKIP went 7 → 22, so this changed what is VISIBLE, not what runs. `--self-test` exit 0
with four new cases (the suffix shape both spellings, a merely-smoke-ish name rejected, and
every discovered live smoke carrying a row).
**QC (b) live smoke:** the subject itself, re-run after the change — `picker-search-live-smoke`
**OK**, 4/4 browser checks against the running iso stack. No service seam crossed by this
cycle (a lint predicate and a registry), so no image rebuild was owed.
**QC (c) real data:** the counts above, read off the tree today: 15 live smokes, 0 matched,
0 registered; 118 → 133 discovered.
---

### ✅ L5 2026-08-30 — **the old test passed all five subtests under the exact bite it is named for**

```
bite: delete searchFilter from the books COUNT (server.go line 987)

TestAppendTitleSearchFilter                              5/5 PASS
  ...including the subtest literally called
  "count args are a prefix of the page args"                PASS
TestBuildBookListQueries                                    FAIL
  "COUNT is not filtered — total would describe the library
   while items describe the search"
```

🎯 **The code was already right; only the test was blind.** The books handler has passed
`searchFilter` to both queries since the library-search fix. What L5 fixes is that nothing
could tell — the old subtest demonstrates "count args are a prefix of the page args" by
calling `appendTitleSearchFilter` **twice and comparing the results to each other**, which is
true of the helper no matter what the handler does with it.

📐 **The wiring is now the unit.** `buildBookListQueries` returns page SQL, page args, count
SQL and count args, so the prefix property holds by CONSTRUCTION rather than by a test that
compares a pure function with itself. Same shape as `buildWorldListQueries`, which was built
for the same reason two commits earlier.

🔴 **It pulled in a second thing that was never checked: EGRESS GUARD #7.** `accessFilter`
carries `is_bible=false` and `kind<>'diary'`, and it was built inline in the handler and
pasted into both queries. A guard that reached the page and not the COUNT would leak through
`total` — a smaller leak than a row, and still a number about books the caller may not see.
Now one string, and a test asserts it reaches the COUNT on BOTH the owned and the shared
branch.

⚠️ **My first bite hit the wrong line and I nearly kept it.** The needle matched the PAGE
query (line 982) before the count, so the suite went red for a defect I had not injected.
Re-aimed by line number at 987. A bite that reds for the wrong reason proves the file is
broken, not that the check has teeth — and this file's own CYCLE says mutate BY LINE NUMBER
for exactly this.

⚠️ **A test of mine also failed on correct code**, and it was the test that was wrong: it
asserted the lifecycle value never reaches the SQL text by searching for `trashed`, and the
page SQL selects `b.trashed_at`. The needle is now the quoted literal `'trashed'`, plus a
direct assertion that lifecycle is `args[1]`.

**QC (a) gates:** `gate-wiring-gate --run-all` **104 GREEN, 0 RED, exit 0**; book-service
`./internal/api` green (6 new subtests).
**QC (b) live smoke:** seam crossed (Go handler), image REBUILT on `lw-iso` and restarted.
Against it: unfiltered `total=77`; `q=Salt Cartographers&limit=1` → **`total=4, items=1`** —
the COUNT is filtered, not reporting 77; `q=%` → 0 rows, so `escapeLikePattern` is applied;
and `/v1/books/trash` (the `includeShared=false`, `lifecycle=trashed` branch) answers
`total=205` unfiltered and `0` for a non-matching `q`, so BOTH branches of the extracted
function ran live.
**QC (c) real data:** iso, 77 active books and 205 trashed for the e2e owner.

🧪 **BITE — three, each on a different claim.**

```
1 drop searchFilter from the COUNT (line 987)   -> "COUNT is not filtered" (old test: 5/5 PASS)
2 drop accessFilter from the COUNT (line 986)   -> "COUNT does not hide bible containers"
3 LIMIT/OFFSET numbered off countArgs (984)     -> "expected LIMIT $4 OFFSET $5"
```
---
