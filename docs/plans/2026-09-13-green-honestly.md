# Green, honestly — fix the product until the suite passes, and never the other way round

Reconciles: Plan Acceptance Criteria · Non-Vacuity · Remediation Cycle — this plan adds no rule.
It continues [red-by-red](2026-09-13-red-by-red.md), which answered *why* 51 tests failed. This
one closes the 18 that remain.

> **APPROVED by the PO**, in these words:
>
> > *"The realistic path: fix the five product defects → 9 tests go green. Diagnose #267/#268 → 3
> > more. Decide #269 and the one-model question → 2. Do the fixture work → 4. That's 18,
> > honestly."* → **"approve, set new goal"**
>
> **Nothing here ships anything.** The tag is still the PO's.

## What is different about this plan, and why it is more dangerous

red-by-red touched the product **twice**, and both times it was a `data-testid`. This plan
**changes product code on purpose** — five defects, in the frontend, the API and the schema.

That inverts the risk. The old danger was editing a test until it passed. The new danger is
**editing the product until the test passes**, which looks like real work and can be just as
hollow: a z-index nudged until a click lands, a flag cleared until a dialog stops appearing, a
constraint widened until an INSERT succeeds. Each would turn a red test green without the user's
problem going away.

So the mechanism is NV-6 run **backwards**, and it is the core of this plan:

> **A fix is proven by RE-BREAKING it.** Fix the product, watch the test that found the defect go
> green, then put the defect back and watch the SAME test go red again for the SAME reason, then
> restore the fix. A fix whose test cannot be made to fail again did not fix anything that test
> was measuring.

## The 18, and what each actually needs

| # | tests | needs |
|---|---|---|
| **#262** reasoning menu unclickable | 4 | a stacking/portal fix in Compose |
| **#264** false "unsaved changes" after save | 2 | reset the dirty baseline on save success |
| **#263** API offers node kinds the DB forbids | 1 | **a data-model DECISION** — which half moves |
| **#265** approving cast does not advance `pass_cursor` | 1 | backend investigation |
| **#266** grounded affirmation never renders | 1 | frontend/API investigation |
| **#267** nav executor does not navigate | 2 | **diagnosis first** — cause unknown |
| **#268** wiki articles never appear | 1 | **diagnosis first** — sync vs job-backed unknown |
| **#269** `kg-overview-no-project` rendered by nothing | 1 | **a PO DECISION** |
| D13 `compose-need-model` unreachable | 1 | **a PO DECISION** — the one-model constraint |
| B3 enrichment-profile | 2 | a seeded + extracted book fixture |
| B4 mock-SSE intermediate phase | 1 | a mock that streams |
| D12 assistant end-of-day | 1 | a per-run session, and a Tier-A consent decision |

**Plus two skips, which are not passes.** A 100% pass rate cannot be claimed while they sit there:
`campaign-factory` needs `E2E_FACTORY_PROJECT_ID` / `E2E_FACTORY_BOOK_ID`; `composition-generate`
needs a **second active model**, which the PO's own one-model constraint forbids. That conflict is
real and only the PO can resolve it.

## Acceptance criteria

| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | Every one of the 18 is GREEN, or carries a recorded reason it cannot be | the suite, plus a row per exception | all | ❓ unknown |
| **AC-2** | Every product fix is proven by RE-BREAKING it — the test that found the defect goes red again, for the same reason | both outputs pasted, per fix | F1–F5 | ❓ unknown |
| **AC-3** | No test was weakened to accommodate a fix | per row, the claim before and after, stated and unchanged | all | ❓ unknown |
| **AC-4** | Both SKIPS are answered, or their blocker is named and owned | passed / failed / skipped stated separately | K1, K2 | ❓ unknown |
| **AC-5** | The whole suite is re-run and the delta explained test by test, with **no newly red** | the two result sets and their diff | Z1 | ❓ unknown |
| **AC-6** | Every decision owed to the PO is asked as a CHOICE, with options and a recommendation | the decision record | H1, H2, F2 | ❓ unknown |
| **AC-7** | The PO can reach a GO or NO-GO | **their own words.** No row ticks this | Z2 | ❓ unknown |

## Board

### Lane F — fix the product. Each ends in a RE-BREAK, or it is not done.

- [~] **F1** — **#262 FIXED and RE-BROKEN (Cycle 1). 3 of its 4 green; the 4th moved to F6.**
  The reasoning menu cannot be clicked. *(4 tests)*
  **The row's original premise was wrong and Cycle 1 corrected it.** It said the promote bar "wins
  the hit test", which reads as a stacking problem. The probe found NO competing stacking context:
  the menu opened upward out of `composition-content` (`overflow-auto`) and was CLIPPED away, with
  the bar merely occupying those coordinates. A z-index change could not have worked. Fixed with
  `createPortal` + fixed coordinates. **Re-broken** per Rule 1.

- [~] **F2** — **INVESTIGATED, OPTIONS READY, AWAITING THE PO (Cycle 5).** The ambiguity is gone:
  M5 deliberately removed both kinds, so the `Literal` is STALE and the schema is the intended end
  state. What remains is a contract call, which is the PO's.
  **#263**, the API offers `arc` and `beat`; the table permits `chapter` and `scene`.
  *(1 test)* **A DATA-MODEL DECISION, not a repair.** Investigate which half is correct — was the
  migration missed, or is the `Literal` stale? — then **present both options with a
  recommendation and STOP.** Widening a CHECK constraint to make an INSERT succeed is exactly the
  hollow fix this plan is guarding against.

- [~] **F3** — **#264 FIXED and RE-BROKEN (Cycle 2). 1 of its 2 green; the other moved to F7.**
  The structure editor claims unsaved changes after a save. *(2 tests)*
  `initial` is a `useRef` captured at mount and never reassigned, so the draft is permanently
  "diverged" after the first edit. The baseline must move on save success — and the component's
  remount/`onDirty` contract has to stay coherent. **Re-break:** freeze the baseline again; both
  must go red.

- [x] **F4** — **DONE (Cycle 3), but #265 as I FILED it was wrong.** The rail is correct: it
  refused because the cast pass produced `{"cast": []}` and so opened no seed proposal — *"you
  cannot accept a cast that does not exist"*. A REAL defect was found alongside it and fixed:
  `canApprove` offered an Approve button that 409s forever. E2E green twice. *(1 test)*

- [x] **F5** — **DONE (Cycle 4). #266 was NOT a product defect either.** The test targeted
  `plan-run-open-<id8>`, a testid that exists nowhere, and swallowed the failure with
  `.catch(() => {})` — so the planner never opened the grounded run. Product untouched; 3 passed. *(1 test)*

- [ ] **F6** — `composition-journey` asserts **1** scene where there are **2**. *(1 test, from F1)*
  It is past #262 now and fails on `composition-scene-select` option count — `unexpected value
  "2"`. The GUIDED first run seeds an "Opening scene" before `addScene` adds its own; this is
  the identical stale assumption Cycle 12 of red-by-red fixed in `composition-gate`, in a spec
  that never got there because the reasoning control blocked it first. Harness, not product.

- [ ] **F7** — the archive test never CONFIRMS the archive. *(1 test, from F3)*
  `onArchive` opens the app's own `ConfirmDialog` (*"C1/C4 -- the app's own confirm, never OS
  confirm()"*), and the spec clicks Archive then immediately asserts the row is gone. Measured:
  `archived=false | v2` -- the save landed, the archive never happened, because nobody confirmed
  it. A user must confirm too, so adding the step is faithful, not a weakening. Harness.

### Lane G — diagnose before touching anything.

- [x] **G1** — **DONE (Cycle 6). #267 was NOT a product defect.** The tests drove the SUSPEND path
  for `ui_*`, which was deliberately retired; the executor listens for a directive RESULT. Product
  untouched; 4 passed. *(2 tests)*
  The sibling card tests pass on the same suspend/resume machinery, so the plumbing works and only
  the navigation does not. Find the cause, THEN decide who owns it. A verdict of
  "undiagnosed, with the trace" remains legal and is better than a guess.

- [x] **G2** — **DONE (Cycle 7). #268 was NOT a product defect.** Generate only OPENS a dialog;
  nothing is generated until it is confirmed. Product untouched; 1 passed. *(1 test)*
  The spec's comment says the API is synchronous. **If it is job-backed now, the test is stale and
  the product is fine** — that has to be established before either is touched.

### Lane H — decisions. These STOP for the PO.

- [ ] **H1** — **#269**: was the Overview panel's no-project gate dropped deliberately? *(1 test)*
  Present what each answer costs. Also fix the unit test that renders the component with the id
  directly — it cannot fail for the reason it was written, whichever way the decision goes.

- [ ] **H2** — **D13 and the one-model constraint.** *(1 test now, 1 skip)*
  `compose-need-model` asserts a state the model cascade exists to prevent, and
  `composition-generate` needs a second ACTIVE model. Both are downstream of *"we only can run 1
  strong model at same time"*. Options, cost of each, PO decides.

### Lane J — fixture work. No product change.

- [ ] **J1** — **B3**: a seeded + extracted book for `enrichment-profile`. *(2 tests)*
  They assert a non-empty worldview and an extraction history. The pieces exist — adopt + extract
  now work end to end — and must be assembled, not shortcut. Pointing them at a fresh book would
  make both claims vacuous.

- [ ] **J2** — **B4**: a mock that STREAMS. *(1 test)* `route.fulfill` delivers the whole SSE body
  at once, so an intermediate phase can pass unpainted. The claim — phases reach the inspector —
  is worth keeping; the mock is what must change.

- [ ] **J3** — **D12**: a per-run Assistant session on an active model. *(1 test)*
  One long-lived session currently carries earlier runs' unanswered Tier-A consent gates. Decide
  deliberately whether the test answers consent or avoids provoking it.

### Lane K — the skips. A skip is unanswered.

- [ ] **K1** — `campaign-factory` needs `E2E_FACTORY_PROJECT_ID` / `E2E_FACTORY_BOOK_ID`.
  Seed them the way `seed-evidence-account.py` seeds the rest, so a clean machine can run it.
- [ ] **K2** — `composition-generate` needs **two active models**, which the one-model constraint
  forbids. **Do not quietly activate a second** — that already exhausted this machine once (#260).
  It is H2's decision; this row only records the outcome.

### Lane Z — the close.

- [ ] **Z1** — Rebuild (Rule 4), re-run the WHOLE suite, diff it test by test against
  `evidence/z1-baseline-failures.txt` and the 180/18/2 recorded here. **No newly red.** *(AC-5)*
- [ ] **Z2** — Hand over. **The PO's words close it.** No row ticks this. *(AC-7)*

## Cycles

### Cycle 1 — the menu was not out-stacked, it was clipped out of reach (F1, F6)

**Investigated:** `src/components/ai-task/EffortSelect.tsx`;
`src/features/composition/components/CompositionPanel.tsx:701` (`composition-content`,
`overflow-auto`); `ComposeView.tsx:159`; and the live DOM through a throwaway probe spec that
measured rects, clipping ancestors, stacking ancestors and `elementFromPoint`.

**Issues:** #262 — fixed here.

**Fix:** **the diagnosis in red-by-red's Cycle 3 was incomplete, and acting on it would have failed.**
That cycle recorded "the what-if promote bar wins the hit test", which reads as a z-index problem.
The probe says otherwise:

```
option rect            top=181  bottom=224
its scroll container   top=335  bottom=696   (composition-content, overflow-auto)
stackingAncestors      ONLY the menu itself (z=20) -- nothing competes
elementAtCenter        span "Name the what-if to promote it."
```

The menu was `absolute bottom-full` inside the trigger's box, so it opened **upward out of its own
scrolling container** and came to rest 150px above it, clipped away. The promote bar merely
occupies those coordinates. **There was no competing stacking context, so raising `z-index` could
not have worked** — the menu was not painted under something, it was painted where nothing could
reach it.

It is now rendered through `createPortal` with fixed coordinates measured off the trigger, which
escapes every ancestor clip. It still prefers to open upward — that is the point of the control,
which sits at the bottom of an input bar — and flips down only when there is no room. The
outside-click handler now consults the portalled menu as well as the trigger; without that the
first click on an option would close the menu before it registered. No new dependency: this repo
has `@radix-ui/react-dialog` but no dropdown primitive, so React's own portal is the honest tool.

**Proof:**

```
PROBE, after the fix -- same coordinates, now reachable:
  clippingAncestors : []                       (was 7, innermost composition-content)
  elementAtCenter   : span "Off"               (was the promote bar)
  isTheOption       : true
  stackingAncestors : div[effort-select-menu] z=50 pos=fixed

TESTS ......... 3 passed (B4.2, B4.4, correction-gate)

RE-BREAK (Rule 1) -- the defect put BACK, frontend rebuilt:
  9ffe6f0e2ae3d762f78ba8f56c429f21  /tmp/es.tsx.orig
  9ffe6f0e2ae3d762f78ba8f56c429f21  src/components/ai-task/EffortSelect.tsx
  TimeoutError: locator.click -- waiting for getByTestId('effort-select-opt-off')
    <span>Name the what-if to promote it.</span> from
    <div data-testid="composition-whatif-promote"> subtree intercepts pointer events
  RED again, same reason.

FIX RESTORED, rebuilt:
  2f45b19464a93fb4ce06c1904ce47655  /tmp/es.tsx.FIXED
  2f45b19464a93fb4ce06c1904ce47655  src/components/ai-task/EffortSelect.tsx
  2 passed (13.3s) + correction-gate 1 passed (31.5s)
```

**Not ticked.** F1 covers 4 tests and 3 are green. `composition-journey` is past #262 and now fails
on a scene count — the same guided-"Opening scene" assumption Cycle 12 of red-by-red fixed
elsewhere, in a spec that never reached it before. That is F6, and it is harness work, not a
retreat from this fix.

**AC impact:** AC-2 met for F1 — the fix was proven by re-breaking it and watching the same tests
fail for the same reason. AC-1 — 3 of the 18 are green. AC-3 holds: no test was touched at all in
this row. The probe spec was deleted rather than left behind as a permanent fixture.

### Cycle 2 — three fixes deep, and only the third was the cause (F3, F7)

**Investigated:** `StructureTemplatesPanel.tsx:270-310,179-186,429-439`;
`useStructureTemplates.ts:86-129,153-155`; the templates API round-trip by hand; and finally the
two snapshots themselves, through a throwaway debug attribute.

**Issues:** #264 — fixed here.

**Fix:** three changes, and **I guessed wrong twice before measuring**, which is worth recording
because the guesses were plausible and both failed.

**(1) The baseline was snapshotted at mount and never reassigned.** `OwnEditor` is keyed on
`s.selected.id`, so it remounts when the SELECTION changes but not when the same template is
SAVED. The baseline is now DERIVED from `tpl`: `save` invalidates `['structure-templates']` and
`selected` is re-read from that query, so on success `tpl` carries the saved values and dirty
falls to false with no `useEffect`. **This was necessary and not sufficient.**

**(2) `save` stamped `order` on the way out but kept the un-stamped beats in state**, so a newly
added beat never matched the row that came back. Also necessary, also not sufficient.

**(3) The real cause: `JSON.stringify` on objects whose KEY ORDER differed.** The draft spreads
`{...b, order}` and produces `key,label,purpose,order`; the API returns `key,label,order,purpose`.
Identical data, different strings — measured directly:

```
server: {"key":"beat_2","label":"","order":2,"purpose":""}
draft : {...b, order}  ->  key, label, purpose, order
```

Beats are now reduced to positional TUPLES, which no key order can disturb.

**(4) And one race.** Between clicking Save and the refetch arriving, `tpl` is still the OLD row,
so comparing against it alone warns about discarding work already saved. The draft is now also
clean when it matches what was last SUBMITTED and `saveError` is null — if the save errors, it is
dirty again, which is correct.

**Proof:**

```
INSTRUMENTED (a temporary data attribute, removed afterwards -- `grep -c __f3dbg` -> 0):
  DRAFT : {"name":"PROBE …","kind":"save_the_cat","beats":[…["beat_16","","",16]]}
  ROW   : {"name":"PROBE …","kind":"save_the_cat","beats":[…["beat_16","","",16]]}
  EQUAL : true

RE-BREAK (Rule 1) -- the mount-snapshot version restored, frontend rebuilt:
  89f12bcd0d2cf6981f2b02c06c796cf5  /tmp/stp.tsx.orig
  89f12bcd0d2cf6981f2b02c06c796cf5  src/features/studio/panels/StructureTemplatesPanel.tsx
  - tabpanel "Structure Templates": ● Unsaved
  - dialog "Discard unsaved changes?"
  1 failed   <- the original symptom, exactly

FIX RESTORED, rebuilt:
  fa15aacbeb76eb820780258b58782498  /tmp/stp.tsx.FIXED
  fa15aacbeb76eb820780258b58782498  src/features/studio/panels/StructureTemplatesPanel.tsx
  2 passed, 1 failed (31.8s)      <- the 1 is F7
  unit suite: 100 files, 804 tests, all passing
```

**Not ticked.** The archive test is past the dirty dialog and now fails because it never confirms
the archive — measured as `archived=false | v2`: the save landed, the archive did not. That is F7
and it is harness work.

**A latent inconsistency fixed in passing, and named as latent:** the draft normalised `kind` with
`?? ''` while the baseline used `?? 'generic'`, so a template with a null kind would have been born
dirty. No row has a null kind today (`custom 3, generic 19, hero_journey 2, kishotenketsu 11,
save_the_cat 13, story_circle 8`), so it was never firing — but the two halves of one comparison
should not disagree.

**AC impact:** AC-2 met for F3 — proven by re-breaking, with the original symptom reproduced
exactly. AC-1 — 4 of the 18 are now green. AC-3 holds: no test was touched in this row.

### Cycle 3 — the rail was right, and the bug was next to it (F4, #265)

**Investigated:** `plan_pass_service.py:259-300` (`pass_cursor`, `PASS_ORDER`);
`routers/plan_forge.py:389-413`; `worker/job_consumer.py:108-140`;
`hooks/useCheckpointReview.ts:59-60`; `components/CheckpointReview.tsx:1-11,128`; and the live
run's `pass_state`, `plan_artifact` and `plan_bootstrap_proposal` rows.

**Issues:** #265 — and **my own filing of it was wrong**; corrected on the issue.

**Fix:** the chain, measured end to end rather than reasoned:

```
pass_state.cast.decision              = "pending"     (the approve never landed)
POST …/checkpoint {approved, cast}    -> 409 CHECKPOINT_REFUSED
  "cast cannot be accepted before its glossary seed proposal exists"
plan_bootstrap_proposal WHERE run_id  -> (none)
plan_artifact cast_plan content       -> {"cast": []}
```

So the refusal is **correct**, and the product says why in its own source: a pass that produced
nothing opens no proposal, *"and for `cast` that means acceptance will refuse, which is correct:
you cannot accept a cast that does not exist."* **#265 is not a pass-rail defect.** Had I "fixed"
the rail to accept an empty cast I would have destroyed a deliberate guard — which is precisely the
hollow fix this plan was written to prevent.

**The real defect was one line away.** `canApprove = !proposalId || proposal?.status === 'applied'`
made `!proposalId` do double duty: it means "advisory pass, no gate", but it is ALSO true for a
BLOCKING pass whose proposal was never opened. In that state the button was **enabled while the
server refused forever** — exactly what `CheckpointReview.tsx`'s own header warns about ("409s the
approve forever"). Blocking passes are now gated on the proposal EXISTING as well as being applied.

**A unit test was guarding the broken state.** `CheckpointReview.test.tsx` rendered
`checkpoint: 'blocking'` with `bootstrap_proposal_id: undefined` and asserted Approve worked — it
would pass on a build that dead-ends the author. Its real claim ("Approve reports the approval") is
kept, on a pass that CAN be approved, and a second case now pins the disabled state. **This is the
third time in this work a test was found defending a bug** (red-by-red Cycles 11 and 18).

**Proof:**

```
RE-BREAK (Rule 1) -- the conflation restored:
  ff2b188a1b38f8b9ec17d119aac0c029  /tmp/ucr.ts.orig
  ff2b188a1b38f8b9ec17d119aac0c029  hooks/useCheckpointReview.ts
  × blocking pass with NO seed proposal → Approve is DISABLED, not a 409 waiting to happen
  Tests  1 failed | 10 passed

FIX RESTORED:
  c70a483125f410b7cee75ecb5c1f7999  /tmp/ucr.ts.FIXED
  c70a483125f410b7cee75ecb5c1f7999  hooks/useCheckpointReview.ts
  Test Files 18 passed | Tests 185 passed

E2E, rebuilt, twice:  2 passed (1.1m)   then   2 passed (50.6s)
```

**An honest limit on this green.** The E2E passes because the cast pass produced characters. The
artifacts show both outcomes across today's runs:

```
{"cast": [{"name": "Diep Van Vu", "role": "protagonist", …}]}   <- the last two runs
{"cast": []}                                                    <- the run that failed
```

With an empty cast it will fail again — and now it will fail by TIMING OUT on a disabled button
rather than on a cursor assertion, which is a clearer signal but still a failure. That is
model-output dependence with a named cause, not flakiness, and Z1 must watch it.

**AC impact:** AC-2 met for F4 — the fix was proven by re-breaking it and watching the guard go
red. AC-1 — 5 of the 18 green. AC-3: one unit test was CORRECTED, with the server's 409 as the
evidence that its old assertion was wrong; no E2E assertion was touched.

### Cycle 4 — a testid that never existed, and a swallow that hid it (F5, #266)

**Investigated:** `specs/plan-forge-grounding.spec.ts:104-114`;
`components/PlannerPanel.tsx:208-224`; `components/PlanRunsListView.tsx:84-104`; every
`plan-run*` testid in `src/`.

**Issues:** #266 — **not a product defect.** To be corrected on the issue.

**Fix:** the note is gated on `plan.run?.grounded_on`, i.e. the run **currently loaded** in the
planner. The test tried to load its grounded run with

```ts
await page.getByTestId(`plan-run-open-${grounded.slice(0, 8)}`).click().catch(() => {});
```

`plan-run-open` exists **nowhere in `src/`** — it never did — and `.catch(() => {})` swallowed the
miss, so the planner silently stayed on whatever run was already loaded and correctly showed no
grounded note. **The product was right the whole time.**

Rows are `plan-run-row`, each printing `id.slice(0, 8)` (`PlanRunsListView.tsx:91`) — data, not
copy, so it survives translation. The swallow is gone: a click that cannot land must say so.
**No product code was touched in this row** (`git diff --stat` on `PlannerPanel.tsx` is empty).

**Proof:**

```
AFTER the repair ............................ 3 passed (50.6s)

BITE 1 -- `grounded_on` dropped in the API serializer:
  1 skipped, 2 passed      <- NOT a failure. The spec's own ceiling guard
  (`test.skip(!run.grounded_on, 'ceiling off in this deployment')`) converts a
  backend regression into a SKIP. Worth knowing: if grounding stopped being
  recorded, this test would go quiet rather than red. Restored md5-identical.

BITE 2 -- the note's testid renamed, frontend rebuilt:
  Locator: getByTestId('plan-grounded-note')
  1 failed, 2 passed

RESTORED byte-exact, rebuilt:
  d540385be57cb6df6220f7c24b772f2d  /tmp/pp.tsx.orig
  d540385be57cb6df6220f7c24b772f2d  components/PlannerPanel.tsx
  git diff --stat -> empty
  3 passed (2.2m)
```

**A Rule 4 trap I walked into, recorded because it produced a false green.** My first attempt at
bite 2 used `{false && plan.run?.grounded_on ? …}`. The build FAILED (`exit code: 2`), the
container went on serving the OLD bundle, and the suite reported **3 passed** — a pass against
un-bitten code that I nearly accepted. I had grepped the build output with `tail -1` and caught an
unrelated line instead of the error. **Checking that a build command RAN is not checking that it
SUCCEEDED**; the grep is now `grep -E "Built|ERROR"`.

**AC impact:** AC-1 — 6 of the 18 green. AC-2 is not applicable: there was no product fix to
re-break, and the repaired test was shown to bite instead. AC-3 holds — the locator got stricter
(a swallowed click became a real one) and no assertion changed.

### Cycle 5 — the migration already decided it; only the contract call is left (F2, #263)

**Investigated:** `services/composition-service/app/db/arc_lift.py:5-28` (the M4/M5 migration
header); `app/db/models.py:39,283`; `package_migration`; and `outline_node` itself.

**Issues:** #263 — the finding is recorded on the issue.

**Fix:** **none applied, deliberately.** The row asked which half is correct — a missed migration,
or a stale `Literal`. It is the `Literal`, and the product says so in its own migration:

```
M5 — CONTRACT (the point of no return; gated on M4 assertions):
  1. re-assert guards (zero kind='beat', zero orphan arc-children), DELETE the lifted arc
     rows, swap the kind CHECK to ('chapter','scene').
```

`arc` was **lifted out** of `outline_node` into `structure_node`; `beat` had to be ZERO before M5
would run at all. The CHECK constraint is not a gap — it is the migrated end state.

**Proof:**

```
package_migration:  pkg_lift_v1 | 2026-07-11 07:56:35     <- M5 completed here
outline_node kinds: chapter x274
                    scene   x489                          <- no arc, no beat anywhere
models.py:39        NodeKind = Literal["arc", "chapter", "scene", "beat"]   <- stale
models.py:283       StructureNodeKind = Literal["saga", "arc", "part"]      <- where arc lives now
```

**Widening the CHECK constraint would have been the wrong fix**, and it was the obvious one: it
would re-admit rows that a "point of no return" migration deliberately deleted, and `arc_lift`
refuses to run while any `kind='beat'` exists. This is the hollow fix this plan named in advance —
*"a constraint widened until an INSERT succeeds"*.

**Why this still STOPS.** Narrowing a published type removes two values other clients may send.
That is an API-compatibility judgement, not a code question, so it is the PO's. Options and a
recommendation are on the issue and in the hand-back.

**AC impact:** AC-6 — the decision is prepared as a CHOICE with evidence and a recommendation,
not a bare question. AC-1 — #263's single test is neither green nor undiagnosed: it carries a
recorded reason (it creates a `beat`, a kind the data model deleted in July). AC-2 not
applicable — nothing was fixed, so there is nothing to re-break.

### Cycle 6 — the tests drove a mechanism the product had retired (G1, #267)

**Investigated:** `hooks/useUiToolExecutor.ts:10-48,58-70`; `nav/uiNav.ts:17,27-41,131-150`;
`hooks/runChatStream.ts:318-335`; `hooks/agUiEvents.ts:85-92`;
`tests/e2e/helpers/frontendToolInject.ts:52-80`.

**Issues:** #267 — **not a product defect.** To be corrected on the issue.

**Fix:** the executor's own header says what happened:

```
The legacy pending-suspend path was retired in Phase 4 / D-P3-RETIRE-UI-SUSPEND once the
ui_* cutover was live-proven — no ui_* suspends any more.
```

It now watches the message list for a `TOOL_CALL_RESULT` whose content carries an
`io.loreweave/ui-directive`, and acts on it at most once. The two tests injected a **suspended
call** (`TOOL_CALL_START/ARGS/END` + `RUN_FINISHED status:'suspended'`, no result), so the
executor had nothing to act on and correctly did nothing. **The sibling CARD tests kept passing
because those are genuinely still suspend-based** — a human gate — which is why the failure looked
selective and product-shaped.

A new `installUiDirectiveResult` emits what the executor actually listens for. **No product code
was touched** (`git diff --stat` on `features/chat` is empty).

**One claim was narrowed, and it is not a weakening.** `ui_show_panel` asserted a `/tool-results`
round-trip and its name said "and resolves the round-trip". That round-trip **no longer exists**:
a ui_* call does not suspend, so the FE has nothing to resolve. Asserting a POST the product
deliberately stopped making would be pinning the retired design. The name lost that clause, and in
its place the test now pins the executor's IDEMPOTENCY — `panel` must appear exactly once in the
query, never stacked by a re-render:

```ts
expect(url.searchParams.getAll('panel')).toEqual(['glossary']);
```

**Proof:**

```
AFTER the repair ............................ 4 passed (16.6s)

BITE -- the executor made to stop navigating, frontend rebuilt (build CONFIRMED "Built"):
  TimeoutError: page.waitForURL  > 126 |  /[?&]panel=glossary/
  TimeoutError: page.waitForURL  > 144 |  /books/${bookId}/
  2 failed        <- both red on the navigation, which is the claim

RESTORED byte-exact, rebuilt:
  bbd10004d847f288cba4d2b97dfe6af0  /tmp/uite.ts.orig
  bbd10004d847f288cba4d2b97dfe6af0  hooks/useUiToolExecutor.ts
  git diff --stat features/chat -> empty
  4 passed (17.6s)
```

**A harness bug of my own, fixed and recorded:** the first version of the injector called
`page.unroute()` from inside its own handler, which makes Playwright treat the in-flight route as
handled — `route.fulfill: Route is already handled!`. A one-shot flag replaces it.

**AC impact:** AC-1 — 8 of the 18 green. AC-2 not applicable: no product fix, and the repaired
tests were shown to bite instead. AC-3 — one claim was narrowed because the mechanism it described
was removed; a stricter idempotency guard replaces it, and the reasoning is recorded rather than
buried.

### Cycle 7 — Generate opens a dialog; the test never confirmed it (G2, #268)

**Investigated:** `pages/WikiTab.ts:18-26`; `WikiWorkspace.tsx:505,571,589-596`;
`GenerateWikiDialog.tsx:166,206-208`; `glossary-service/internal/api/server.go:462-466`;
`wiki_handler.go:117`.

**Issues:** #268 — **not a product defect.** To be corrected on the issue.

**Fix:** the row said to establish sync-vs-job-backed before touching either side. It is neither:
the Generate button does not generate at all. It calls `openBatchGenerate`, which is
`setGenOpen(true)` — it **opens `GenerateWikiDialog`**. Nothing is requested until
`wiki-gen-confirm` is pressed, and `canConfirm` wants a model or stub mode. The page object
clicked Generate and returned, so the spec waited for articles **that had never been asked for**,
and it read as "generation is broken".

`WikiTab.generate()` now opens the dialog AND confirms it — which is what a person does, so the
claim is completed rather than weakened. It also asserts the confirm is ENABLED first, with a
message naming the model/stub requirement, so a future gating change fails with a reason instead
of a bare timeout.

**This is the second row in this plan to be a missed confirmation step** (F7 is the archive
`ConfirmDialog`). Both times the product had added a deliberate "are you sure" and the test read
its absence of effect as a broken feature.

**Proof:**

```
AFTER the repair ............................ 1 passed (58.6s)

BITE -- `listWikiArticles` forced to return an empty list, glossary-service rebuilt:
  Error: expect(locator).toBeVisible() failed
  Locator: getByTestId('wiki-article-row').first()
  1 failed        <- red on the articles claim

RESTORED byte-exact, rebuilt:
  56165c779c18acfa01f31f5dbc562ec6  /tmp/wh.go.orig
  56165c779c18acfa01f31f5dbc562ec6  services/glossary-service/internal/api/wiki_handler.go
  git diff --stat services/glossary-service -> empty
  1 passed (50.9s)
```

**AC impact:** AC-1 — 9 of the 18 green, exactly half. AC-2 not applicable: no product fix, and the
repaired test was shown to bite instead. AC-3 holds — the claim is unchanged and the page object
gained an assertion it did not have.

## What this plan will NOT do

- **It will not edit the product until a test passes.** Every fix is proven by re-breaking it.
- **It will not weaken, skip, delete or `fixme` a test** to make a fix look complete.
- **It will not decide #263, #269 or the one-model question.** Those are the PO's.
- **It will not activate a second model** to clear a skip.
- **It will not run against anything but loopback**, and never against the PO's own stack.
- **It will not tag, build or publish anything.**

RESUME: Cycles 1-7 done. 9 of the 18 green (half). REAL defects fixed + re-broken: #262 (F1), #264 (F3), and the canApprove bug beside #265 (F4). NOT defects, issues corrected: #266, #267, #268 -- retired mechanisms, a testid that never existed, and an unconfirmed dialog. FOUR of my five filings needed correcting. F2 awaits the PO with options ready; decisions BANKED for one hand-back. Head of the queue is J1 (a seeded + extracted book for enrichment-profile) -- fixture work, no decision.

```goal-prompt
goal: every one of the 18 remaining failures is green or carries a recorded reason it cannot be, every product fix is proven by RE-BREAKING it, and both skips are answered or owned
po_decisions: [F2, H1, H2, AC-7]
lanes: |
  F fix      = F1, F3, F4, F5, F2
  G diagnose = G1, G2
  J fixture  = J1, J2, J3
  H decide   = H1, H2
  K skips    = K1, K2
  Z close    = Z1, Z2
rules: |
  1 A product fix is proven by RE-BREAKING it: fix, watch the test that found the defect go GREEN, put the defect back, watch the SAME test go RED for the SAME reason, restore the fix. Paste both outputs. A fix whose test cannot be made to fail again fixed nothing that test measured.
  2 Never edit a test to accommodate a fix. The user-visible claim is stated before and after and must be identical or stricter.
  3 Never delete, skip or fixme a test to close a row.
  4 Rebuild the container before any E2E run -- it serves a BAKED build.
  5 "Flaky" is not a verdict. Undiagnosed WITH a reason and a trace is legal; silence is not.
  6 A SKIP is unanswered, never a pass. Report passed / failed / skipped separately, always.
  7 Re-verify a cited path, line, count or premise before building on it. The previous plan corrected more than a dozen wrong premises, several of them its own.
  8 Run scripts/doc-language-gate.py --staged before every commit and ACT on its exit code. Never --no-verify.
discipline: |
  One row, one commit. Write the cycle before ticking anything; partial is an honest answer.
  A defect found while closing a row gets its OWN row and its own commit.
  Reach a decision row with OPTIONS and a recommendation ready -- never a bare question.
note: |
  The danger has inverted. The old failure mode was editing a test until it passed; the new one is editing the PRODUCT until a test passes -- a z-index nudged, a flag cleared, a constraint widened. Each turns a test green while the user's problem remains. Rule 1 is the whole guard.
  F1 first: 4 of the 18 hang on it, and it is the only one on the ordinary writing path.
stop: |
  a fix would need a data-model or UX decision that is the PO's (F2, H1, H2)
  a fix would need a destructive or irreversible action
  activating a second strong model would be required
  the write target would be a shared deployment or a non-throwaway database
  an E2E target is not loopback
  a NEW security or data-loss-shaped bug is found
  anything would be BUILT AND PUBLISHED for real
```
