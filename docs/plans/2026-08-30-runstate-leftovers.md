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

RESUME: L1 — causal coverage, accepted and never measured.

## Progress

7 tasks — 5 done, 0 tracked, 2 untouched.

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

- [x] **L3** — **`event_order` collides under concurrent extraction.**
  `b6c8fde13` fixed the deterministic half: the within-chapter index continues from the
  band's maximum instead of restarting at 0. Two jobs extracting one chapter at the SAME time
  still both read that maximum and both write above it.
  **Criteria:** either closed (a reservation, an advisory lock, or a unique constraint that
  makes the second writer retry), or ACCEPTED in writing with the reason and the blast radius
  — how often two jobs can touch one chapter at once, measured, not assumed.
  **BITE:** if closed, two writers racing one chapter must not produce a duplicate
  `event_order`; if accepted, the spec section must name what makes it rare.

- [x] **L2** — **51 colliding `(project_id, event_order)` pairs in the store.**
  The writer fix stops new ones; it renumbers nothing. Measured on iso 2026-08-30: 51
  duplicate pairs in `g_shared`. Every consumer of the reading axis is reading them today.
  **Criteria:** a decision with a number behind it — backfill and renumber, or accept and say
  what breaks while they stand. `backfill_orders.py` already exists and already imports the
  shared stride, so the cost of the first option is measurable rather than guessed.
  **Rule 6:** iso is authorised for the writes; the dev store is READ-ONLY.
  **BITE:** the collision count is a COMMAND, and after the chosen action it prints what the
  decision says it should — 0 for a backfill, 51 with a recorded reason for an acceptance.

- [x] **L6** — **`GO_INLINE_CAP` cannot see a cap against a named constant.**
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

### ✅ L3 2026-08-30 — **the race the row named was impossible; the one nobody named was real**

```
writers of event_order                                    2
  pass2_writer          under the one-active-job invariant  YES
  run_orders_backfill   under it                            NO  <- unguarded
extraction x extraction   prevented by a UNIQUE partial index (read LIVE)
backfill  x extraction    unguarded, and the two schemes DISAGREE
```

🎯 **The row asked for the two-extractions race to be closed or accepted with the blast
radius measured.** Measuring inverted the question: two extractions **cannot** race.
`idx_extraction_jobs_one_active_per_project` is a UNIQUE partial index over
`(project_id) WHERE status IN (pending, running, paused)`, so the second `POST
/extraction/start` fails its INSERT and answers 409. The claim was already in
`pass2_writer`'s docstring — *"Concurrent writers on the same chapter are not expected
(one-active-job-per-project K17.9)"* — and rule 2 says run it rather than read it, which is
what turned up the actual hole.

⚠️ **Verifying it took two tries, and the first would have produced the WRONG answer.** The
index lives on `loreweave_knowledge` (5555); querying `loreweave_knowledge_vectors` (5556,
the AGE store) returns **empty**, which reads exactly like "no such invariant". Fourth time
this plan's lineage has hit the wrong-store defect.

🔴 **`POST /internal/projects/{id}/backfill-orders` was outside the invariant entirely** —
it checked the project exists and a graph is configured, then renumbered `event_order`
project-wide. And the two writers do not merely overlap, they **disagree**: the backfill
assigns `base + idx` over sorted ids (dense from 0), the writer continues from the band's
maximum. Run together, one chapter gets two numberings and the axis is whatever interleaving
won — a stable sort silently falling back to row order, not a crash.

The events consumer was checked too, because its own comments say it runs *"OUTSIDE the
one-active-job-per-project extraction lock"*. It **retracts evidence** and never calls
`merge_event`, so it is not a third writer.

📐 **Closed by giving the backfill the same invariant** (§24). 409 while a job holds the
project, naming the job; the status tuple is ONE constant so the guard cannot drift narrower
than the index; and the 404 still wins so an unknown project hears that instead.

⚖️ **What it does NOT claim:** the guard is a read, so a job starting inside the check→act
window remains possible. It closes the reachable case — a backfill fired at a visibly busy
project — and §24 says so rather than leaving it to be discovered.

🧪 **BITE — three, each on its own claim, by line number.**

```
1 the guard is never called (line 106)        -> 2 FAIL (409 test + status-set test)
2 statuses narrowed to ("running",)           -> "guard covers ['running'], the partial
                                                  index covers pending/running/paused"
3 guard moved BEFORE the project lookup       -> "a missing project is 404 not 409" FAILs
```

⚠️ **The existing test harness had to be repaired first, and it is the same class again.**
`_fake_pool` answered every `fetchrow` with one row, so the endpoint's new second query got
the *project* row as the answer to "is a job running?" and two passing tests turned 409. A
fake that cannot tell two questions apart agrees with whatever the caller asks next; it now
dispatches on the query.

**QC (a) gates:** `gate-wiring-gate --run-all` **104 GREEN, 0 RED, exit 0**; knowledge unit
suite **4461 passed**, 1 skipped (was 4458), 3 new cases.
**QC (b) live smoke:** seam crossed, `knowledge-service` REBUILT on `lw-iso` and restarted.
Against it — idle project → **HTTP 200**; a `running` job inserted on iso → **HTTP 409**
naming that job id; row deleted → **HTTP 200** again. The job row was written to the
isolated stack only and removed, verified 0 active after.
**QC (c) real data:** iso — the live index definition above, and the 200/409/200 sequence on
project `019fefde…`.
---

### ✅ L2 2026-08-30 — **the repair tool reaches 0 of the 102 events, and the real harm was somewhere else**

```
ordered events                                    1224
colliding (project_id, event_order) pairs           51   -> ACCEPTED, frozen (§25)
events on a collision                              102   across 6 projects
of those carrying `chapter_id`                       0   <- the backfill's own filter
collisions spanning two chapter bands                0   <- the spoiler cutoff is untouched
```

🎯 **The row's premise was wrong and measuring showed it.** L2 said *"`backfill_orders.py`
already exists … so the cost of the first option is measurable rather than guessed."* It
selects `WHERE e.chapter_id IS NOT NULL`, and **none of the 102 affected events has that
property** (104 of 1320 store-wide do). A live `POST /backfill-orders` returning
`events_ordered: 0` on the worst project is what sent me to look.

⚖️ **ACCEPTED, because repair does not produce a CORRECT order.** There is no narrative
source to renumber from — the emission order that produced these is the same one T33k caught
putting `盤古開天闢地` at position 18 of 20 — and the backfill's own scheme is `sorted(ids)`,
arbitrary in a different way. Renumbering 102 nodes would trade one deterministic wrong order
for another. §25 carries the four checks behind that: the cutoff is band-level and no
collision spans a band; nothing keys on `event_order` as an identity.

🔴 **WHAT ACTUALLY BROKE.** Four sites order by `event_order` and disagreed on the tie-break —
`events.py` ×2 on `title`, `timeline.py` on `id`, and
`fact_for_check._EVENTS_AT_OR_BEFORE_CYPHER` on **nothing**, a bare `ORDER BY … DESC` in front
of a `LIMIT`. On colliding data the cut is decided by the store, so one canon check could see
a different evidence set on two runs. That is a DETERMINISM bug, and it is the actual cost of
the 51. Fixed with `e.id` — not `title`, because a title is editable and ordering history by a
mutable field means a rename silently reorders the evidence behind a past check.

📐 **The freeze is a ratchet, not a sentence.** `event-order-collision-gate.py`, shrink-only
at 51, red on growth, registered `NEEDS_STACK` so `--run-all` prints why it skips (L4).

⚠️ **A selftest case of mine passed for the wrong reason and I nearly shipped it.** "A store
that cannot be reached REFUSES" asserted only that the word REFUSED appeared — and it stayed
GREEN with the returncode check disabled, because the *empty-result* guard caught the
fallthrough and says REFUSED too. Two guards, one assertion, and the bite proved the case
could not fail for its own reason. Split into two, each asserting its own sentence; both now
bite independently.

🧪 **BITE — four, each on its own claim.**

```
1 remove the tie-break from fact_for_check (line 150)  -> "these order by event_order with
                                                          NOTHING after it" names the constant
2 ceiling 51 -> 50                                     -> gate FAIL, exit 1
3 swallow a failed query (returncode guard)            -> "cannot be REACHED" case FAILs
4 drop the empty-result guard                          -> "returns nothing" case FAILs
```

**QC (a) gates:** `event-order-collision-gate --selftest` **7 cases, 4 negative**;
`gate-wiring-gate` **134 discovered**, self-test exit 0; knowledge unit suite **4464 passed**,
1 skipped (was 4461).
**QC (b) live smoke:** seam crossed, `knowledge-service` REBUILT on `lw-iso`. The running
container carries `ORDER BY e.event_order DESC, e.id DESC` ×1 and the bare form ×0. Against
the live store on the worst project the ordering is byte-identical across runs — and the
output shows the collision it is coping with: **two events both at `12000017`**.
**QC (c) real data:** the census above, off `g_shared`.

⚠️ **The full suite went 2 RED, and it was rule 5 catching an omission from L4.**
`gate-teeth-gate`'s `CI_SCOPE_FLOOR = 118` was left behind when L4 widened discovery; adding
this row's gate moved the CI-invoked census 118 → 119 and
`gate-number-visibility-gate` reported *"a ratchet nobody can see"*. **The floor had only
ever reached the output by coincidence** — it happened to equal `len(invoked)`, so the moment
the census grew by one it vanished. Floor raised to 119 in this commit (rule 5) and now
PRINTED explicitly, so its visibility is no longer an accident. Bitten by line number:
drop the print AND move the floor off the census → `FAIL — CI_SCOPE_FLOOR = 117 never reaches
the output`. Suite back to **104 GREEN, 0 RED**.
---

### ✅ L6 2026-08-30 — **§22's batch of 8 is 2, and both survivors are the shape L5 deliberately introduced**

```
selftest cases          8 -> 15  (9 negative)
BASELINE rows          27 -> 24  (3 were never defects; pruned by intersection)
§22 step-3 batch        8 ->  2  after two instrument bugs were fixed
```

🎯 **Two instrument bugs, not one.** The row named the first: `GO_INLINE_CAP` required `\d+`
on both sides, so `if limit <= 0 || limit > maxChapterBlocks { limit = maxChapterBlocks }` read
as uncapped — and it failed on the SHAPE too, since the old pattern needed `if <limit> >`
immediately after the `if`. The second turned up while measuring: **three of the five findings
a stricter signal produced were `//` COMMENTS** — `search.go` documenting its own placeholders
(`// $3 = escaped ILIKE pattern   $4 = limit`). The instrument was reporting on its own prose,
the "hygiene grep matches a comment" defect this repo has hit before.

📐 **A VARIABLE is still not a cap**, and that is the half worth guarding. `_go_int_consts`
resolves only package-level `const NAME = <int>` — never a `var`, never a chained const, never
a string. Widening a signal is precisely the change that quietly starts accepting what it
should not.

🔴 **THREE BASELINE ROWS WERE NEVER DEFECTS.** `canonical_summary_handler.go`,
`wiki_gold_pairs.go` and `wiki_handler.go` cap against `maxCanonicalDirtyLimit`,
`goldPairsMaxLimit` and a compound `if limit <= 0 || limit > 100`. Pruned by intersection,
never `--regen`, with a note where they stood: a baseline row for a non-defect makes the list
look like it is carrying work that does not exist.

⚖️ **§22 step 3 is NOT taken, and now for a better reason than §22 had.** Measured with the
instrument honest, it would newly red **two** sites — `runLexicalSearch` and
`buildBookListQueries` — and **both are query BUILDERS whose cap lives one hop up, in the
caller**. The repo wants that shape: L5 extracted `buildBookListQueries` so the page query and
the COUNT could not drift. Function-scoping the helper signal would penalise the structure
this plan spent a cycle introducing. §22 records the number and what step 3 would first need:
the resolver already follows a file-scope SQL const to the functions that NAME it, and would
have to follow a builder to the functions that CALL it.

⚠️ **One of my four bites did not land, and fixing that found a missing case.** "Only the
comparison bound is checked, not the assigned value" left the suite GREEN — because the
`a VARIABLE bound is NOT a cap` case puts `someVar` on both sides, so checking the comparison
alone catches it. `if limit > 500 { limit = someVar }` is the case that separates them, and
it did not exist. Added; the bite now reds.

🧪 **BITE — four, each on its own claim, by line number.**

```
1 const resolver returns nothing (line 112)      -> "cap against a package-level int const" FAILs
2 any identifier accepted as a bound (line 120)  -> the VARIABLE and non-int-const cases FAIL
3 only the comparison bound checked (line 234)   -> "ASSIGNS a variable" FAILs (after the case existed)
4 comment guard removed (line 258)               -> "a LIMIT inside a // comment" FAILs
```

**QC (a) gates:** `pagination-cap-lint --selftest` **15 cases, 9 negative**;
`pagination-cap-lint` OK, 28 baselined; `gate-wiring-gate --run-all` **104 GREEN, 0 RED,
exit 0**.
**QC (b) live smoke:** N/A — a lint predicate and a baseline list. No service code, no image,
no seam crossed.
**QC (c) real data:** the whole tree, scanned: 24 findings, 0 outside the BASELINE; the
step-3 simulation above run over the same walk.
---
