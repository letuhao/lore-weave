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
| **AC-5** | The whole suite is re-run and the delta explained test by test, with **no newly red** | the two result sets and their diff | Z1 | ✅ met — 18→7, 0 newly red |
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

- [x] **F2** — **DONE (Cycle 19). The PO ruled: reconcile toward the schema.** Narrowed; the sweep found #271 and #272.
  *(Cycle 5 investigated it and banked the options.)* The ambiguity is gone:
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

- [x] **F6** — **DONE (Cycle 16).** Not the scene-select count the row claimed — the publish gate, correctly refusing "1 of 2 scenes not yet done". *(1 test, from F1)*
  It is past #262 now and fails on `composition-scene-select` option count — `unexpected value
  "2"`. The GUIDED first run seeds an "Opening scene" before `addScene` adds its own; this is
  the identical stale assumption Cycle 12 of red-by-red fixed in `composition-gate`, in a spec
  that never got there because the reasoning control blocked it first. Harness, not product.

- [x] **F7** — **DONE (Cycle 17).** The confirm step was missing, and ConfirmDialog had no testid to reach it by. *(1 test, from F3)*
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

- [~] **H1** — **INVESTIGATED; the question turned out to be a DIFFERENT one (Cycle 11).** The
  gate was never dropped, and the unit test is not vacuous — BOTH of my earlier claims were wrong
  and are corrected. The real question is that opening a book in the Studio AUTO-PROVISIONS a
  knowledge project, which makes the no-project state unreachable. Awaiting the PO. *(1 test)*
  Present what each answer costs. Also fix the unit test that renders the component with the id
  directly — it cannot fail for the reason it was written, whichever way the decision goes.

- [x] **H2** — **INVESTIGATED, OPTIONS READY, AWAITING THE PO (Cycle 12).** The constraint blocks
  THREE things, not two, and one of them wants a NON-REASONING model rather than a second strong
  one — which changes the memory arithmetic.
  **D13 and the one-model constraint.** *(1 test now, 1 skip)*
  `compose-need-model` asserts a state the model cascade exists to prevent, and
  `composition-generate` needs a second ACTIVE model. Both are downstream of *"we only can run 1
  strong model at same time"*. Options, cost of each, PO decides.

### Lane J — fixture work. No product change.

- [x] **J1** — **DONE (Cycle 8).** The fixture is assembled for real — adopt, extract, profile —
  rather than shortcut. 2 passed, bitten. **B3**: a seeded + extracted book. *(2 tests)*
  They assert a non-empty worldview and an extraction history. The pieces exist — adopt + extract
  now work end to end — and must be assembled, not shortcut. Pointing them at a fresh book would
  make both claims vacuous.

- [x] **J2** — **DONE (Cycle 9), and NOT by making the mock stream.** The inspector already keeps
  a phase TRAIL, which records the same claim deterministically. 4 passed, bitten.
  **B4**: a mock that STREAMS. *(1 test)* `route.fulfill` delivers the whole SSE body
  at once, so an intermediate phase can pass unpainted. The claim — phases reach the inspector —
  is worth keeping; the mock is what must change.

- [~] **J3** — **PARTIAL (Cycle 10).** The stale session is FIXED and verified. The test stays red
  for a cause the product itself names: the one active model is a REASONING model and returns a
  blank completion to the distiller. **This is H2's constraint, not a defect.**
  **D12**: a per-run Assistant session on an active model. *(1 test)*
  One long-lived session currently carries earlier runs' unanswered Tier-A consent gates. Decide
  deliberately whether the test answers consent or avoids provoking it.

- [x] **F9** — **DONE (Cycle 25).** The distiller never asked the model to stop thinking. *(1 test, D12)*

- [x] **F8** — **DIAGNOSED, NOT FIXED (Cycle 23).** `plan-forge-pass-rail` proposes 0 arcs because the
  LLM job is `truncated`. Converges with `assistant-endofday` and K2 on one cause. *(1 test)*

- [x] **H4** — **DONE (Cycle 21).** #269's test destroyed the state it asserted, in its own first line.
  *(1 test, found while measuring H1 in Cycle 20)* Independent of the PO's H1 decision.

- [x] **H3** — **DONE (Cycle 18). Does not reproduce.** 16 of 17 pass; the one failure is H1's.
  *(1 test, found in Cycle 11)* Which repair removed it is deliberately not guessed.

### Lane K — the skips. A skip is unanswered.

- [x] **K1** — **DONE (Cycle 13). The skip is GONE: 7 passed, 0 skipped.** The test had never run
  anywhere. `campaign-factory` needed `E2E_FACTORY_PROJECT_ID` / `E2E_FACTORY_BOOK_ID`.
  Seed them the way `seed-evidence-account.py` seeds the rest, so a clean machine can run it.
- [x] **K2** — **ANSWERED (Cycle 27). The skip is GONE — it RUNS, and it fails on its first-ever execution.**
  *(was: OWNED, not answered, Cycle 13)* It belongs to **H2**, where it is priced
  alongside the other two things the constraint blocks. Nothing was activated.
  `composition-generate` needs **two active models**, which the one-model constraint forbids. **Do not quietly activate a second** — that already exhausted this machine once (#260).
  It is H2's decision; this row only records the outcome.

### Lane Z — the close.

- [x] **Z1** — Rebuild (Rule 4), re-run the WHOLE suite, diff it test by test against
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

### Cycle 8 — the fixture that had to be built, not borrowed (J1)

**Investigated:** `specs/enrichment-profile.spec.ts:1-20,55-70`; `pages/EnrichmentTab.ts:27-42`;
`src/features/enrichment/api.ts:27,305-322`; the live profile endpoint by hand;
`specs/demo-pipeline-3b.spec.ts` for the extraction sequence.

**Issues:** none — no product defect here.

**Fix:** the spec defaulted to a hard-coded *"seeded demo Fengshen book"* on one stack and one
account. **The shortcut was the trap.** Pointing it at a FRESH book would have made both tests
pass and prove nothing: the worldview would be empty, so *"loads the seeded profile"* would be
vacuous, and the C2 "extract first" notice would be CORRECT, so asserting its absence would be
asserting a bug. Two green tests, zero information.

`seedProfiledExtractedBook` builds the real thing — create, adopt the ontology, run a LIVE
extraction, then PUT a worldview — and **refuses rather than degrade**: it throws if adopt yields
no auto-selected kinds (`"the fixture would be vacuous"`), and if extraction does not finish
`completed` exactly. It costs a live model run, and that cost is what makes the two claims mean
anything.

**Proof:**

```
AFTER the fixture ........................... 2 passed (1.0m)

BITE -- `worldview` removed from the profile view (lore-enrichment rebuilt):
  Error: expect(locator).not.toHaveValue(expected) failed
  Locator: getByTestId('profile-worldview')
  > 63 |  await expect(enr.worldview).not.toHaveValue('');
  1 failed, 1 passed      <- red on the worldview claim, which is the point of the fixture

RESTORED byte-exact:
  f48eabdd89323486867fdc0eefba933d  /tmp/bp.orig
  f48eabdd89323486867fdc0eefba933d  /app/app/api/book_profile.py
  2 passed (42.0s)
```

The bite is the answer to "did the fixture actually matter": with the worldview blanked the test
goes red, so it is reading real data rather than rendering something regardless.

**AC impact:** AC-1 — 11 of the 18 green. AC-2 not applicable: no product fix; the repaired tests
were shown to bite. AC-3 holds — no assertion changed, and the fixture now supports the ones that
were already there.

### Cycle 9 — the deterministic record was already there (J2)

**Investigated:** `specs/agent-context-rack.spec.ts:94-170`;
`components/AgentRuntimeInspector.tsx:31-36,44-59,85-92`; `hooks/useAgentSurface.ts:23-24,44-60`.

**Issues:** none — no product defect.

**Fix:** the row proposed making the mock STREAM with gaps so the intermediate phase could be
painted. That turned out to be the wrong shape of answer. `route.fulfill` delivers one body and
cannot stream, and chasing a transient render is a race however it is arranged — the old assertion
polled 23 times and saw `Idle` every one.

**The inspector already keeps a phase TRAIL** (`useAgentSurface.ts:24`, appended on every
transition), rendered as `Curated → Idle`. That is the same claim — *"agentSurface phases update
inspector"* — recorded rather than glimpsed. The end state is settled first, then the trail is
asserted:

```ts
await expect(phase).toHaveText('Idle', { timeout: 10_000 });
await page.getByTestId('agent-runtime-inspector').getByRole('button').first().click();
await expect(page.getByTestId('agent-inspector-trail')).toContainText('Curated → Idle');
```

**This is STRICTER than what it replaced.** The old version could pass on timing luck — if the
paint happened to land, it went green for the wrong reason. The trail cannot: the phase either
reached the inspector or it did not.

The expand click is not a workaround: the trail lives in the inspector's expanded body
(`AgentRuntimeInspector.tsx:59`), collapsed by default, so a person reading the trail expands it
too. The toggle carries no testid, so it is reached by ROLE within the inspector — still
language-agnostic.

**Proof:**

```
first attempt ... trail element not found -- it renders only when expanded
AFTER the expand step ....................... 4 passed (13.2s)

BITE -- the trail stops recording (`setTrail(() => [])`), frontend rebuilt:
  Locator: getByTestId('agent-inspector-trail')
  Expected substring: "Curated → Idle"
  1 failed, 3 passed

RESTORED byte-exact, rebuilt:
  801433d976fb72b905d9f933dbea1a72  /tmp/uas.ts.orig
  801433d976fb72b905d9f933dbea1a72  hooks/useAgentSurface.ts
  git diff --stat -> empty
  4 passed (12.9s)
```

**AC impact:** AC-1 — 12 of the 18 green. AC-2 not applicable: no product fix; the repaired test
was shown to bite. AC-3 — the claim is unchanged and the assertion became deterministic where it
had been a race.

### Cycle 10 — the product diagnosed itself, and the answer is H2's (J3)

**Investigated:** `specs/assistant-endofday.spec.ts:14-52`; `pages/AssistantPage.ts:54-62`;
`src/features/chat/useAssistantAutoSession.ts`; `features/assistant/hooks/useEndOfDay.ts:48`;
`chat_sessions` before and after; `POST /v1/assistant/end-day` by hand; and `worker-ai`'s log.

**Issues:** none — nothing here is a defect.

**Fix:** real, and partial. `/assistant` auto-creates a session ONLY when none exists, and
`useEndOfDay` then finds it by kind — so the FIRST one ever made is reused forever. On this stack
that was a session created before the one-model switch, still pinned to a now-INACTIVE model and
carrying two unanswered Tier-A consent gates from earlier runs. `clearAssistantSessions` now runs
per-test, so the product's own auto-create path executes on the CURRENT default — which is what
the spec's first assertion actually claims.

```
BEFORE  assistant | model=01a09a1f-…(qwen, is_active=false) | 2026-09-13 10:04:44
AFTER   assistant | model=01a09a53-…(gemma, is_active=true) | 2026-09-13 17:48:28
```

**Proof:** the two rows above are the fix, measured before and after. What follows is why the row
is still red, and it is not flakiness. The distiller is asynchronous
(`POST /assistant/end-day` → `201 {"enqueued": true}`), so I triggered it directly and polled the
entries endpoint: **0 entries after 270s**, well past the test's 150s. Not slow — not happening.
The worker says why, in its own words:

```
distiller map chunk: model returned a BLANK completion — the distill model produced no output
  (a reasoning model? use a non-reasoning distill model; DBT-15/Q8)
distill msg (distill) status=no_entry reason=model_no_output advisory=distill_model_no_output
```

**Gemma is a reasoning model**, and the distiller gets an empty completion from it. The product
DETECTS this, names the cause, and reports `no_entry` with an advisory rather than failing
silently. That is correct behaviour meeting an unsuitable model.

**This is the third thing blocked by the one-model constraint** — after the `composition-generate`
skip (needs a second ACTIVE model) and D13 (`compose-need-model` unreachable). It belongs to **H2**
and is evidence for that decision, not a separate problem.

**No bite, and the rule says why.** The session fix is proven by effect (the two rows above, before
and after). The remaining failure cannot be bitten: a bite proves a REPAIRED test goes red and back
to green, and this one does not pass, so it FAILS CLOSED and the row is not ticked.

**AC impact:** AC-1 — J3's failure carries a recorded, measured reason rather than a guess. AC-2
not applicable. AC-6 — this hands H2 a concrete cost: the one-model constraint is not only about
two-model tests, it also means the diary distiller cannot produce an entry at all.

### Cycle 11 — two of my own findings were wrong, and the real question is better (H1, #269)

**Investigated:** `KgOverviewPanel.tsx:9,26-41`; `hooks/useBookKnowledgeProject.ts:18-23`;
`hooks/useProjects.ts:36,77`; `api.ts:1048`; the projects API with a `book_id` filter;
`git log -S` over the panel; and `knowledge_projects` timings.

**Issues:** #269 — **to be corrected**, because I filed it on two premises that do not hold.

**Fix:** none applied. What changed is the question.

**Correction 1 — the gate was never dropped.** I reported that `kg-overview-no-project` "is
rendered by nothing". It is rendered at `KgOverviewPanel.tsx:38`, behind `if (!projectId)`. My
Cycle-14 grep in red-by-red listed the two OTHER callers and was cut off by `head -5`; I read the
absence of a third line as an absence in the code. `git log -S` confirms the id has only ever been
ADDED, never removed.

**Correction 2 — the unit test is not vacuous.** I said `KgNoProjectState.test.tsx` guards an id
the app never passes. The app passes exactly that id, one line from the panel. The test is fine.

**What is actually true, and is worth a decision.** The bare book DOES get a project:

```
books             01a09bef-db7e-… | E2E KG bare … | 18:03:02.910
knowledge_projects 01a09bef-ffc0-… | E2E KG bare … | 18:03:12.190
```

Ten seconds later, named after the book, created by opening it in the Studio — the same
auto-provisioning shape as D4's composition Work. The API filter is correct (`?book_id=<bare>`
returns 0 for a book that has not been opened), so nothing is broken. But it means the no-project
empty state is **unreachable through the Studio**, and every book a writer merely LOOKS at gets a
knowledge project.

**Proof:**

```
grep KgOverviewPanel.tsx      -> line 38: <KgNoProjectState … testId="kg-overview-no-project" />
git log -S kg-overview-no-project -> one commit, the one that ADDED it
GET /v1/knowledge/projects?book_id=<never-opened bare book>  -> returned: 0
knowledge_projects for the opened bare book                  -> 1, created 10s after the book
```

**The decision, for the PO.** Options are on the issue. This is not a bug report any more; it is
"should opening a book silently create a knowledge project", and the cost is a project per book
opened plus an empty state that can never be seen.

**A second failure in this spec is NOT this row.** The same run showed
`TimeoutError: page.goto: Timeout 15000ms exceeded` on another kg-panels test. That is unexamined
and is recorded as such rather than folded in here.

**AC impact:** AC-6 — the decision is prepared with evidence and options. AC-1 — #269's test
carries a recorded reason. AC-2 not applicable. **Two corrections to my own prior findings are
recorded rather than quietly dropped.**

### Cycle 12 — the one-model constraint costs more than two tests (H2)

> **Superseded in part by Cycle 15.** The costs measured below are real; the CAUSE attributed to
> them is wrong. Items 1 and 3 are not blocked by memory. Left standing rather than rewritten,
> because the wrong reason is the finding.

**Investigated:** the three blocked items and their exact requirements;
`CompositionPanel.tsx:317-325` (the cascade); `worker-ai` distiller advisory; LM Studio's
advertised model list (read-only — no control, per the standing instruction); live memory.

**Issues:** none — this is a constraint, not a defect.

**Fix:** none applied. This row prepares a decision.

**Proof:** what the constraint actually blocks, measured:

```
1 composition-generate   SKIP  "needs a chat-tagged drafter + >=1 distinct active critic"
2 compose-need-model     FAIL  the cascade ends "... > the sole-registered model auto-pick"
                               (CompositionPanel.tsx:325), so "no model picked" cannot occur
3 assistant-endofday     FAIL  distiller: "model returned a BLANK completion — the distill model
                               produced no output (a reasoning model? use a NON-REASONING distill
                               model)"; 0 entries after 270s

memory now:  14.6 GB free of 95.7   (gemma-4-26b resident, ~14 GB)
LM Studio advertises 72 models, including smaller ones (e.g. google/gemma-4-12b-qat)
```

**The important nuance.** I had been treating this as "one STRONG model". Item 3 does not want a
second strong model — it wants a **non-reasoning** one, which can be small. That is a different
memory profile from the two-model load that exhausted this machine in #260 (a 35B beside a 27B).

**Options, for the PO:**

**A — keep exactly one model.** 1 skip and 2 permanent reds, each with a recorded reason. Honest,
and the suite can never reach 100%. No risk.

**B — add ONE SMALL NON-REASONING model beside gemma, used only as critic/distiller.** Unblocks 1
and 3. Does NOT unblock 2. Memory: gemma ~14 GB resident with 14.6 GB free; a ~12B QAT is roughly
7-8 GB, leaving ~7 GB. **Not risk-free** — #260 is why this is the PO's call and not mine, and I
will not activate anything without a yes.

**C — for item 2 specifically, retire or REAIM the test.** `compose-need-model` asserts a state the
cascade exists to prevent. It cannot be reached without removing the sole-model auto-pick, which
would make the product worse. **Recommended:** re-aim it at what the cascade actually promises —
*with exactly one registered model it is auto-picked* — which is a real, currently untested claim.
That is not weakening: it swaps an unreachable assertion for a reachable one about the same code.

**Recommendation: A + C now, B only if the PO wants 100%.** A+C costs nothing and removes one
permanent red honestly. B buys the last two at a memory risk only the PO can price.

**AC impact:** AC-6 — prepared as a choice with measured costs and a recommendation. AC-4 — K2's
skip (`composition-generate`) is owned by this decision rather than left unexplained. AC-1 — items
2 and 3 carry recorded reasons.

### Cycle 13 — a skip that had never run anywhere (K1, K2)

**Investigated:** `specs/campaign-factory.spec.ts:134-142,165-175`;
`services/book-service/internal/api/server.go:403` (the publish route);
`helpers/api.ts:175-181`; and the publish + project endpoints by hand.

**Issues:** none — no product defect.

**Fix:** `campaign-factory`'s fixture-gated test skipped on
`!E2E_FACTORY_PROJECT_ID || !E2E_FACTORY_BOOK_ID`, and **nothing anywhere ever set them** — not the
seeder, not CI, not the run command. So the create → report/activity/chapters contract it guards
had never been exercised on any machine. A skip is UNANSWERED, and this one had been unanswered
since it was written.

`seedFactoryFixture` seeds what it actually needs: a book with a **PUBLISHED** chapter plus a
knowledge project. Published is the load-bearing word — the factory drafts against published
chapters, so a draft chapter would satisfy the env check and prove nothing. The env still wins if
someone sets it.

**K2 is OWNED, not answered.** `composition-generate` needs two ACTIVE models. Activating one is on
this plan's STOP list and it is what exhausted this machine in #260, so it goes to **H2** with its
price rather than being quietly arranged.

**Proof:**

```
BEFORE ..... 6 passed, 1 skipped   "set E2E_FACTORY_PROJECT_ID + E2E_FACTORY_BOOK_ID"
AFTER ...... 7 passed, 0 skipped

BITE -- `error_groups` dropped from the campaign report (campaign-service):
  Error: expect(received).toBeTruthy()
  170 |  for (const k of ['status', 'total_chapters', 'stages', 'error_groups'])
  1 failed, 6 passed      <- the newly-running test red on the contract it guards

RESTORED byte-exact:
  b4fa41e200130aa10e14ea48172100fc  /tmp/cs.orig
  b4fa41e200130aa10e14ea48172100fc  /app/app/routers/campaigns.py
  7 passed (1.5s)
```

The bite matters more than usual: a test that has never run is exactly the kind that could be
vacuous. It is not — dropping one key from the report turns it red.

**AC impact:** **AC-4 half met** — one skip ANSWERED (it now runs and is proven to bite), one
OWNED by H2 with a named blocker. AC-1 — 13 of the 18 green. AC-2 not applicable: no product fix.

## What this plan will NOT do

- **It will not edit the product until a test passes.** Every fix is proven by re-breaking it.
- **It will not weaken, skip, delete or `fixme` a test** to make a fix look complete.
- **It will not decide #263, #269 or the one-model question.** Those are the PO's.
- **It will not activate a second model** to clear a skip.
- **It will not run against anything but loopback**, and never against the PO's own stack.
- **It will not tag, build or publish anything.**

RESUME: Cycles 1-15 done. Z1 CLOSED: 192 passed / 7 failed / 1 skipped of 200, verified by allure summary.json CONTENT -- 18 became 7, 0 newly red. Cycle 15 CORRECTS H2 and filed #270: assistant-endofday and the K2 skip fail because `critic` and `distill` are settable in NO settings row, not because of memory. The PO has ruled on all three decisions (F2, H1, H2) and that work is NEW, beyond this plan. Head of the queue is Z2 -- hand over; only the PO closes AC-7.

### Cycle 14 — the whole suite, test by test (Z1)

**Investigated:** the full 200-test suite re-run on `lw-iso` against a rebuilt frontend image, diffed
test by test against `docs/plans/evidence/z1-green-honestly-baseline.txt` (18 rows) and
`z1-green-honestly-skips.txt` (2 rows).

**Issues:** none new — **0 newly red**. All 7 remaining failures are baseline rows.

**Fix:** no code changed in this cycle; it is the measurement row. 18 failures → 7, and all 11 that
went green did so for the reason their row claimed. The 7 that remain are the three banked PO
decisions (`#263`/F2 telemetry, `#269`/H1 kg-panels, D13 `B4.1`), the two model-role failures that
Cycle 12 attributed to the one-model constraint (`assistant-endofday`, and K2's skip beside it),
and the two open product rows F6 (composition-journey scene count) and F7 (archive ConfirmDialog).

The single remaining SKIP is `composition-generate` — **unanswered, not passed** — and it is the same
root as `assistant-endofday`: both need a role (`critic`, `distill`) that the settings UI has no row
for. That reframes H2 and is recorded there, not here.

**Proof:**

```
BASELINE .... 18 failed,  2 skipped, 180 passed   (200 total)
Z1 .......... 7 failed,   1 skipped, 192 passed   (200 total)

allure-report/widgets/summary.json (read by CONTENT, not exit code):
  {'failed': 7, 'broken': 0, 'skipped': 1, 'passed': 192, 'unknown': 0, 'total': 200}
  duration 1741979 ms (29.0 min)

evidence-capture-gate: 201 test dir(s), 576 watchable artefact(s). Every one left something.

FIXED (11): composition-engine B4.2 · composition-engine B4.4 · composition-correction-gate Diverge
            · studio-structure-templates "edit a cloned" · plan-forge-grounding · frontend-tools
            ui_open_book · frontend-tools ui_show_panel · demo-pipeline-3c wiki · enrichment-profile
            "Profile tab loads" · enrichment-profile "Gaps detect" · agent-context-rack mock SSE
STILL RED (7): assistant-endofday · composition-engine B4.1 · composition-journey · composition-
            telemetry · kg-panels · plan-forge-pass-rail · studio-structure-templates "archive an own"
NEWLY RED (0): none.
```

**AC impact:** AC-5 is met — the suite was re-run whole and the delta is explained test by test, with no newly red.
AC-1 stands at 11 of 18 green with a recorded reason for each of the 7; AC-4's K2 remains owned, not answered.


### Cycle 15 — the "one-model constraint" was a missing settings row (H2, corrected)

**Investigated:** every declaration of the model-ROLE vocabulary — `frontend/src/features/chat-ai-settings/types.ts:42`;
`frontend/src/features/settings/api.ts:99-113`; the rows `DefaultModelsCard.tsx` actually renders;
and every `get_default_model(...)` / `resolve_default_model(...)` call in `services/`.

**Issues:** #270 — `critic` and `distill` are resolvable by the backend but settable in no settings row; the role vocabulary is declared in four places and no two agree.

**Fix:** none applied here — this corrects a recorded reason and hands H2 back to the PO with a different question. Cycle 12 attributed `composition-generate` (K2) and `assistant-endofday` to "only one strong model fits in memory". That is false. Both need a ROLE, and the role has no settings row, so `get_default_model` falls back to `chat` and returns the same reasoning model. A second model would have hidden a settings gap behind a hardware story.

The product already knows. `evaluate.py:180` refuses to score and instructs the user, verbatim, to
*"Set a critic model in Settings › Chat & AI › default models."* No such row exists. The instruction
cannot be followed.

**Proof:**

```
role vocabulary, as declared:
  chat-ai-settings/types.ts:42   chat composer planner embedding rerank critic     (6)
  settings/api.ts:99-113         chat composer planner embedding rerank            (5)
  DefaultModelsCard rows         chat composer planner        rerank                (4)
  backend get_default_model()    chat composer         embedding      critic distill (5)

settable but never resolved : planner, rerank
resolved but NEVER SETTABLE : critic, distill      <- K2 and assistant-endofday
declared but no row         : embedding

evaluate.py:171-180    judge = get_default_model("critic") or get_default_model("chat")
                       -> "Set a critic model in Settings > Chat & AI > default models."
internal.py:570-571    get_default_model("distill") or get_default_model("chat")

frontend surfaces that pick a model independently: 53
```

**AC impact:** AC-6 — H2 returns to the PO as a different choice, with the measured cause rather than the assumed one. AC-4 — K2 stays owned, but by a settings gap, not by memory.


### Cycle 16 — the row named the wrong symptom; the gate was right all along (F6)

**Investigated:** `specs/composition-journey.spec.ts:36-38,60-63`; `composition-gate.spec.ts:35`
(the same sequence, already pinning 2); `CompositionPanel.tsx:192` and
`hooks/useGuidedFirstRun.ts:22` (the guided "Opening scene" and its no-second-seed guard);
the Z1 Allure `statusDetails` for this test.

**Issues:** none — no product defect. The publish gate is correct; the spec's model of the world was not.

**Fix:** the row said this failed on `composition-scene-select` option count with `unexpected value "2"`. **It does not, and has not.** Re-reading the Z1 failure before building on it (Rule 7) showed the run reaching the END of the journey and failing on `publish-button` disabled with `title="1 of 2 scenes not yet done"`. The stale `toHaveCount(1)` was *passing* — by racing the guided seed's arrival — and the damage surfaced forty lines later on a gate that was behaving correctly.

Two changes, both to the spec's assumptions, neither to its claim. The count assertion now pins **2**, which is what `composition-gate` already asserts for the identical setup→addScene sequence, and Playwright's retry makes it wait for the seed instead of outrunning it. Mark-done now iterates **every** scene: a user with two scenes must finish both, and the button says exactly that.

The user-visible claim is unchanged and stricter: *publish is gated until the scenes are done, then enables*. Before, it proved that for one scene by accident; now it proves it for all of them on purpose.

**Proof:**

```
BEFORE (stale count passes by racing, gate refuses at the end)
  Error: expect(locator).toBeEnabled() failed
    24 x <button disabled data-testid="publish-button" title="1 of 2 scenes not yet done">
  1 failed

AFTER
  1 passed (1.3m)
  verified by PRODUCT STATE, not the reporter word:
    E2E journey 1789326010503 | published | published_revision_id NOT NULL

BITE — replace the loop with the single markDone the spec used to do, nothing else:
  Error: expect(locator).toBeEnabled() failed
    <button disabled data-testid="publish-button" title="1 of 2 scenes not yet done">
  1 failed                      <- SAME failure, SAME reason

RESTORED byte-exact (git diff: 18 insertions, 3 deletions -- the fix only):
  1 passed (1.3m)
```

**AC impact:** AC-1 — F6 is green, 12 of 18. AC-3 — the claim is stated before and after and is stricter, not weaker. AC-2 — the bite is pasted both ways.


### Cycle 17 — the archive that nobody confirmed (F7)

**Investigated:** `specs/studio-structure-templates-journey.spec.ts:120-158`;
`StructureTemplatesPanel.tsx:72-79` (`askArchive`) and `:192-196` (*"C1/C4 — the app's own
confirm, never OS confirm()"*); `components/shared/ConfirmDialog.tsx:64,123,144`.

**Issues:** none — no product defect. The dialog is correct; the spec walked past it.

**Fix:** `onArchive` does not archive. It opens the app's own `ConfirmDialog`, and the spec clicked Archive and asserted immediately, so the archive never happened — measured earlier as `archived=false | v2`: the rename had saved, the archive had not. A user has to confirm as well, so adding the step is faithful to the journey rather than an accommodation.

`ConfirmDialog` had **no `data-testid` on either button**, so the confirm could only be reached by its translated label — which E2E CONVENTIONS §1 exists to forbid on a product whose UI language changes. Added `confirm-dialog`, `confirm-dialog-confirm` and `confirm-dialog-cancel`: additive affordances on shared UI, no behaviour touched, the same class of change as the epub-import testids earlier in this work.

The claim is unchanged: *archive removes it from the default list, the archived toggle shows it, restore brings it back — a round-trip, not a dead-end.* It simply now performs the archive it always claimed to.

**Proof:**

```
AFTER
  3 passed (13.1s)

BITE — delete the two confirm lines, change nothing else:
  Error: after archiving, the template is gone from the default list
  expect(locator).toHaveCount(expected) failed
    Expected: 0
    Received: 1
  1 failed                   <- the ORIGINAL F7 failure, reproduced exactly

RESTORED byte-exact:
  3 passed (13.1s)
```

The end state in the database cannot tell these apart — a round-trip finishes
un-archived by design, so `is_archived=f` is correct for both a real archive-then-restore
and an archive that never happened. The bite is what distinguishes them, which is the
reason the rule asks for one.

**AC impact:** AC-1 — F7 is green, 13 of 18. AC-3 — the claim is identical before and after; only the missing user step was added.


### Cycle 18 — the second kg-panels failure no longer exists (H3)

**Investigated:** `specs/kg-panels.spec.ts` in full (17 tests), re-run on the rebuilt image; and the Z1 Allure results for that spec.

**Issues:** none — the failure this row recorded does not reproduce.

**Fix:** none needed. H3 recorded a second `kg-panels` failure — `page.goto: Timeout 15000ms exceeded` — as unexamined, deliberately kept out of H1 rather than folded into it. Re-checking it before acting on it (Rule 7) finds it gone: **16 passed, 1 failed**, and the single failure is the empty-state test that belongs to **H1/#269**, which is the PO's decision, not a second defect.

**I did not isolate which repair removed it** and will not guess. Between Cycle 11 and now the login throttle got isolated-stack headroom, the DB and API helpers stopped crossing stacks, and several studio URLs were corrected — any of which could account for a navigation timeout. Naming one without evidence would be the kind of premise this plan has had to correct a dozen times.

**Proof:**

```
kg-panels.spec.ts, full spec, rebuilt image:

  16 passed (1.5m)
  1 failed   -> "kg-overview shows the empty state for a book with no linked KG project"
               Error: expect(locator).toBeVisible() failed
               Timeout: 5000ms — element(s) not found

  page.goto: Timeout 15000ms exceeded   <- NOT PRESENT. 0 occurrences.
```

**AC impact:** AC-1 — H3 carries a recorded reason: it no longer reproduces, measured, with the cause honestly left unattributed.


### Cycle 19 — the API offered two kinds the database refuses (F2, #263, #271, #272)

**Investigated:** the live `outline_node` CHECK; `models.py:39` and `frontend/src/features/composition/types.ts:218`; `migrate.py:2365-2400` (`_assert_lift_applied`); every site the narrowing turned red.

**Issues:** #263 closed by the PO's ruling; #271 and #272 filed — two real defects the narrowing surfaced.

**Fix:** the PO ruled: reconcile toward the schema, then sweep for the same class of drift. `NodeKind` becomes `Literal["chapter","scene"]` and the TS union with it. Widening the CHECK was never an option — `pkg_lift_v1` is explicitly *"M5 — CONTRACT: the point of no return"*.

The schema side was already sound: fresh databases auto-lift and the service refuses to boot unlifted. **The drift was entirely in code that still spoke the pre-lift vocabulary**, and narrowing the type is what made it visible — seven sites, of which two were real user-visible defects and five were dead branches.

**#272 — the outline tree offered "Add beat" on every scene.** A reachable ＋ button that POSTs a kind the database refuses. Removed. A unit test was *asserting* this behaviour, which is how it survived; corrected with the constraint error as evidence.

**#271 — the chapter browser's arc grouping has been empty since the migration.** It reads `outline_node` for `kind === 'arc'`. Its behaviour is **left exactly as it was** and marked: repairing it means reading `structure_node` and needs a test that would have caught it, which is #271's work, not this row's. It is not pinned in a test either — the three tests covering it still describe the intended grouping, not the broken result.

Fourteen unit tests failed under the narrowing, every one built on the pre-lift model: arcs nested above chapters, beats below scenes. **That is why the drift survived the migration** — the suite kept proving the code correct against fixtures the database can no longer produce. Corrected to the real tree, chapter > scene, rooted.

**Proof:**

```
LIVE SCHEMA
  CHECK ((kind = ANY (ARRAY['chapter'::text, 'scene'::text])))

#272 proven directly, not assumed:
  INSERT ... kind='beat'
  ERROR: violates check constraint "outline_node_kind_check"

AFTER
  composition-telemetry ..... 1 passed (5.4s)
  tsc --noEmit .............. exit 0
  vitest .................... 176 files, 1288 passed, 0 failed

BITE — put the four-kind Literal back and the test's 'beat' node with it:
  API .../outline/nodes -> 400 {"code":"CONSTRAINT","detail":"new row for relation
  \"outline_node\" violates check constraint \"outline_node_kind_check\" ... beat ..."}
  1 failed                                   <- the original failure, exactly

RESTORED byte-exact (NodeKind = Literal["chapter", "scene"]):
  1 passed (5.4s)
```

**AC impact:** AC-1 — F2 is green, 14 of 18. AC-2 — the product fix is bitten both ways. AC-6 — the PO's decision is applied as given, and the sweep they asked for produced #271 and #272.


### Cycle 20 — H1 measured properly, and it stops on a SEALED decision (H1, #269)

**Investigated:** `events/book_lifecycle_consumer.py:88-112` (`_provision_work`); `routers/works.py:180-250` (POST /work) and its `OQ-1 (ratified)` comment at :221; `useEnsureWork` (`hooks/useWork.ts:38`) and `StudioFrame.tsx:52`; the live rows for two books, one opened and one never opened.

**Issues:** none new — but my earlier diagnosis of #269 was wrong twice and is corrected here.

**Fix:** none applied. **This row STOPS**: delivering what the PO asked for reverses a decision the code records as ratified.

What is actually true, measured on two books rather than reasoned about:

A book's `book.created` event provisions a composition Work with **`project_id = NULL` and `pending_project_backfill = true`** — deliberately, because the consumer has no bearer. The knowledge project appears only when somebody OPENS the book in the Studio: `StudioFrame` mounts `useEnsureWork`, which POSTs `/work`, and that route creates the project with **the caller's own bearer**. So creation ships a half-provisioned Work and opening finishes it. **298 books on this stack are sitting in that state right now.**

The PO's ruling — ship Work *and* knowledge project at creation — needs the consumer to create a knowledge project with no user bearer. There are exactly two ways, and the code has already refused one of them:

> `# OQ-1 (ratified): knowledge auto-provision stays OWNER-only — the caller's own bearer is forwarded and knowledge rejects a non-owner (F4), which surfaces below rather than minting an owner-identity token.`

**A — a new internal knowledge route that trusts `owner_user_id` from the event.** Delivers exactly what was asked. It is a new service-to-service trust boundary that mints user-owned data from a caller-supplied id, which is the shape OQ-1 was ratified to avoid. **My recommendation, but only with the PO's explicit yes**, because it is a security decision and not mine.

**B — mint an owner-identity token in the consumer.** Smaller diff, and the thing the comment names and rejects outright. Not recommended.

**C — leave provisioning where it is and backfill the 298 on the owner's next visit.** No new trust boundary, no change to the sealed decision. The half-provisioned window stays.

**Separately: #269's test is not blocked by any of this.** I was wrong twice about it. It fails because the panel resolves a project for a book created bare — and the reason it resolves one is that the *test itself* opens the Studio, which provisions it. The empty state is reachable; the spec destroys it in its own setup. That is a test defect, independent of the PO's decision, and it gets its own row rather than waiting on A/B/C.

**Proof:**

```
book created by API, NEVER opened in the Studio:
  composition_work | project_id = NULL | pending_project_backfill = t
  knowledge_projects .......................... (none)

book created by API, then OPENED in the Studio:
  composition_work | project_id = 01a09c48-b835-... | pending = f
  knowledge_projects | "E2E KG bare 1789328395394" | 19:40:06.581

the read does NOT provision (so it is the Studio's POST, not a lazy GET):
  GET /v1/knowledge/projects?book_id=<never-opened>  ->  {"items":[]}  HTTP 200
  ... and no row appeared afterwards.

books currently holding a pending Work with no project: 298
```

**AC impact:** AC-6 — H1 returns to the PO as a choice with a measured cost and a recommendation. AC-1 — #269 stays red with a corrected reason, and its real cause is now a separate test defect rather than this decision.


### Cycle 21 — the test destroyed the state it was asserting (H4, #269)

**Investigated:** `specs/kg-panels.spec.ts:81-90`; `StudioFrame.tsx:52` → `useEnsureWork` (`hooks/useWork.ts:38`); `KgOverviewPanel.tsx:34` (the gate) and `useBookKnowledgeProject.ts` (`includeArchived: false`); the failing run's own screenshot.

**Issues:** none in the product — #269 is a test defect, and the gate it doubted is real and correct.

**Fix:** the spec created a bare book and asserted the no-project empty state immediately. It could never have worked. `StudioPage.goto` mounts `StudioFrame`, which mounts `useEnsureWork`, which POSTs `/work` — and that route creates the book's knowledge project. **Opening the Studio to look at the panel is what gives the book a project.** The failure screenshot shows it plainly: a fully rendered overview with STATIC MEMORY and CONFIGURATION cards, for the book the test calls "bare".

Twice I blamed something else — first "the Studio auto-provisions, so the empty state is unreachable" (half right, wrong conclusion), then "the panel never opened" (wrong; the screenshot shows it open). Reading the artefact the run already produced settled it in one look.

The empty state is real and reachable: a user can archive their knowledge project, and the resolver lists with `includeArchived: false`. So the test now reaches it the way a user would — open, archive what the product provisioned, reload — rather than mocking the resolution under test. **The claim is unchanged**: a book with no linked KG project shows the empty state.

**Proof:**

```
BEFORE
  Error: expect(locator).toBeVisible() failed — getByTestId('kg-overview-no-project')
  Error: element(s) not found
  ... and the screenshot shows the panel OPEN, rendering a project overview.

AFTER
  1 passed (6.1s)
  whole spec: 17 passed (1.1m)

BITE — delete the archive step, change nothing else:
  Error: expect(locator).toBeVisible() failed
  Error: element(s) not found        <- the original #269 red, exactly

RESTORED byte-exact:
  17 passed (1.1m)
```

**AC impact:** AC-1 — #269 is green, 15 of 18. AC-3 — the claim is identical before and after; only the route to the state changed, from impossible to real.


### Cycle 22 — two roles the backend resolves and nothing could set (H2, #270)

**Investigated:** `provider-registry-service/internal/api/default_models_handler.go:19-56` (the capability whitelist) and `:71-85` (`defaultModelCapQuery`); `settings/api.ts:99-113`; the rows `DefaultModelsCard.tsx` actually renders; `chat-service/app/routers/evaluate.py:171-180` and `internal.py:565-575`.

**Issues:** #270 — `critic` and `distill` were resolvable by the backend and settable in no row.

**Fix:** the PO ruled that the one-model story was wrong and the model setup is stale and scattered. It is, and the measurement is unambiguous: **the backend has supported both roles all along.** `defaultModelCapabilities` has carried `distill` since WS-3.0 and `critic` since WS-5.10, and `defaultModelCapQuery` validates them against the `chat` flag exactly like `planner` and `composer`. **Only the settings card never rendered a row for either.** So `get_default_model("critic")` and `get_default_model("distill")` fell through to `chat` and handed every role the same reasoning model.

The product already told users to fix it and gave them nowhere to do it — `evaluate.py:180` refuses to score and says *"Set a critic model in Settings › Chat & AI › default models."*

Added both rows. This is a **surface**, not a new mechanism: nothing in the resolution path changed, and no model was activated. Whether a second model is worth loading stays the PO's call and is untouched here.

`embedding` stays deliberately unexposed — a query-time embedding default would break retrieval, which must use the model the project was indexed with. That is a documented decision, not drift, and the row-count test now says so instead of leaving it to be "fixed" later by someone counting roles.

**The guard that was missing is the real lesson.** Nothing asserted the card covered the roles it claims to cover, so a role could be added to the backend and silently never surfaced. Two tests now save through each new row.

**Proof:**

```
BACKEND, all along:
  defaultModelCapabilities = rerank embedding chat planner distill critic composer
  defaultModelCapQuery: planner|distill|critic|composer  ->  validated as 'chat'

LIVE, against the account under test:
  PUT /v1/model-registry/default-models/critic   -> HTTP 200
  PUT /v1/model-registry/default-models/distill  -> HTTP 200

AFTER
  settings suite: 10 files, 66 passed, 0 failed
  tsc --noEmit: exit 0

BITE — delete the critic row, change nothing else:
  AssertionError: expected [...] to have a length of 6 but got 5
  AssertionError: expected "vi.fn()" to be called with arguments: [ 'tok', 'critic', 'm1' ]
  3 failed | 4 passed

RESTORED byte-exact:
  7 passed
```

**AC impact:** AC-2 — the fix is bitten both ways. AC-6 — the PO's H2 ruling is applied as far as it goes without activating anything; the remaining question is theirs. AC-4 — K2's skip now has a settable role behind it rather than a hardware story.


### Cycle 23 — three reds and a skip turn out to be one cause (F8, #265)

**Investigated:** `specs/plan-forge-pass-rail.spec.ts:65-69`; the `plan_run` rows this run wrote and the one from 18:33 that did not fail; `error_detail` on both.

**Issues:** none new in the product — it detected the bad model output and said so.

**Fix:** none applied; this row diagnoses rather than guesses, and names a cause instead of calling it flaky. The propose step returns **0 arcs**, and the product is not silently swallowing it:

The model's completion was **truncated**, so nothing parseable came back. A run 85 minutes earlier, same spec, same model, reached `proposed` — so this is borderline rather than broken: the sole registered model is a **reasoning** model, it spends completion budget on `reasoning_content` before the structured answer, and whether the real payload fits is a coin toss on prompt length.

That is the same root as the other two open reds and the remaining skip:

| | wants | gets |
|---|---|---|
| `assistant-endofday` | a NON-reasoning **distill** model | the reasoning model, blank completion |
| `composition-generate` (K2, SKIP) | a distinct **critic** | nothing to be distinct from |
| `plan-forge-pass-rail` | a completion that fits | reasoning eats the budget → truncated |

**#270 made all three settable.** What it did not do — deliberately — is load anything. Every one of these closes the moment a small non-reasoning model exists on the account, and none of them closes without one. That is the PO's call and it is the only thing between this plan and its last three rows.

**Proof:**

```
plan_run, most recent first:
  failed   | "LLM job unusable: truncated" | 2026-09-13 19:58:30
  proposed | (none)                        | 2026-09-13 18:33:19   <- same spec, same model

spec result:
  Error: expect(received).toBeGreaterThanOrEqual(expected)
    Expected: >= 1
    Received:    0
  1 failed | 1 passed (3.2m)
```

**AC impact:** AC-1 — F8 carries a diagnosed reason with the product's own error string and a counter-example run, not a "flaky" label. AC-5 — it is a known, explained red rather than a newly discovered one.


### Cycle 24 — B4.1 joins them, and my earlier recommendation was wrong (D13)

**Investigated:** `specs/composition-engine.spec.ts:16-38`; `CompositionPanel.tsx:317-325` (the model cascade); the live registry for the account under test.

**Issues:** none — no product defect, and no test defect either.

**Fix:** none, and **I am withdrawing the fix I recommended.** Cycle 12 proposed re-aiming this test on the grounds that it asserts a state the cascade exists to prevent — *"with exactly one registered model it is auto-picked, so 'no model picked' cannot occur"* — and called the assertion unreachable.

It is not unreachable. It is unreachable **on an account with exactly one model**. Add a second and the cascade has nothing to auto-pick, the `needModel` hint renders, and the test asserts precisely what it says it does. Re-aiming it would have weakened a correct test to fit a temporary environment — the exact failure mode this plan's note warns about, and I nearly did it.

So D13 is not a decision about a test. It is the same decision as F8, K2 and `assistant-endofday`: **whether a second, small, non-reasoning model exists on this account.** Four items, one answer.

**Proof:**

```
B4.1, current:
  Error: expect(locator).toBeVisible() failed   [composition-need-model]
  Expected: visible
  Error: element(s) not found
  1 failed | 2 passed (22.7s)

cause: CompositionPanel.tsx:325 — "... > the sole-registered model auto-pick"
       one model registered  ->  auto-picked  ->  the "pick a model" hint never renders
```

**AC impact:** AC-3 — a correct test was NOT weakened; the earlier recommendation to re-aim it is withdrawn with the reason. AC-6 — D13 collapses into the single model decision rather than standing as its own.


### Cycle 25 — it was never the model, it was the missing ask (F9, D12)

**Investigated:** `worker-ai/app/distill_job.py:90-112` (the distill call); `sdks/python/loreweave_llm/models.py:120-153` (the reasoning contract); `provider-registry-service/internal/provider/adapters.go:676-685` (`forwardOptionalChatFields`); and LM Studio directly.

**Issues:** none filed — the defect and its fix are one line, in this row.

**Fix:** the PO said any model can turn reasoning off, and they were right. Three cycles of this plan recorded `assistant-endofday` as needing a **non-reasoning** distill model, a claim the code itself asserts — *"use a non-reasoning distill model; DBT-15/Q8"*. It was wrong.

The SDK is explicit about which knob is which: `reasoning_effort="none"` is **the** cross-provider way to disable hidden thinking, and `chat_template_kwargs={"enable_thinking": False}` is its **companion** — *"a no-op for models that only honor reasoning_effort"*. The distiller sent only the companion. On a model that ignores the chat-template flag, thinking stayed on, reasoning tokens ate the whole budget, `content` came back empty — and the empty result was read as *"this model is unusable"* rather than *"we never asked it to stop"*.

Measured against LM Studio, the model everyone had written off:

That is the same model, the same prompt, the same budget. It always could.

**A second thing this row caught.** The first run after the fix still failed, and I nearly recorded the fix as ineffective. The container serves a **baked** image and I had restarted it, not rebuilt it — Rule 4 applies to services, not just the frontend. `grep -c reasoning_effort /app/app/distill_job.py` answered `0`. The same trap produced a false green earlier in this plan; this time it nearly produced a false negative.

**Proof:**

```
LM STUDIO, google/gemma-4-26b-a4b-qat, identical prompt and max_tokens:
  (no reasoning_effort) content='OK'  reasoning_content=192 chars
  reasoning_effort=low  content='OK'  reasoning_content=192 chars
  reasoning_effort=none content='OK'  reasoning_content=0 chars     <- it honours it

AFTER (rebuilt, not merely restarted)
  1 passed (14.5s)
  worker-ai: "distill msg (distill) status=written facts=4 reason=None advisory=None"

BITE — delete the one line, REBUILD, run again:
  Error: a distilled diary entry is produced from the day
  worker-ai: "model returned a BLANK completion ... reason=model_no_output"
  1 failed                                   <- identical red, identical cause

RESTORED byte-exact + rebuilt:
  1 passed (13.9s)
```

**AC impact:** AC-1 — F9 is green, 16 of 18. AC-2 — bitten both ways, through a real rebuild. AC-6 — the PO's correction overturned a claim this plan had recorded three times.


### Cycle 26 — it was never the model count, it was the account default (D13, B4.1)

**Investigated:** `CompositionPanel.tsx:317-325` (the cascade, read rather than assumed); the account's registered models; `personas/account.ts:84` (`freshAccount`, `markOnboarded`); and the gate measured with the account chat default set and cleared.

**Issues:** none in the product — the cascade is correct and the test is correct. The FIXTURE was wrong.

**Fix:** three cycles of this plan said B4.1 was blocked by having one model, and Cycle 24 said adding a second would free it. Both wrong, and adding a second model proved it: **still red.** Reading the cascade instead of theorising a fourth time:

> session pick > per-Work default > **the account-tier chat model** > the sole-registered auto-pick

The shared evidence account has an account-tier chat default, so a model always resolves and the "pick a model" hint can never render — whatever the model count. Measured both ways: clear that default and B4.1 passes; restore it and B4.1 fails.

So B4.1 now runs on its **own fresh account**, which is race-free under parallel workers and more faithful besides — a brand-new author who has configured no model is exactly the user this gate exists for.

**Proof:**

```
with the shared account's chat default SET      -> 1 failed   (compose-need-model absent)
with that default CLEARED                       -> 1 passed (5.2s)
default restored, test moved to a fresh account -> 1 passed (5.1s)
whole spec                                      -> 3 passed (18.7s)

BITE — point it back at the shared account, change nothing else:
  Error: expect(locator).toBeVisible() failed — element(s) not found
```

**AC impact:** AC-1 — D13 is green, 17 of 18. AC-3 — the test was not re-aimed or weakened; only the account it runs on changed. AC-2 — bitten both ways.


### Cycle 27 — a skip that had never run anywhere, answered (K2)

**Investigated:** `specs/composition-generate.spec.ts:17-36` (which models it picks, and whether an INACTIVE 35B could be chosen); `scripts/e2e/seed-evidence-account.py:166-190` (the second-model safety rule); machine memory before and after; the run's own screenshot.

**Issues:** none filed yet — two observations from a first execution, recorded before being chased.

**Fix:** the seeder already owned this decision, with an opt-in flag, a documented incident and an explicit rule: *"Pass `--allow-second-model` only if the pair FITS — two small models, not a 35B beside a 27B."* So the sanctioned path was used rather than a hand-written registry row: a second SMALL model (`gemma-4-12b-qat`) beside the 26B-a4b MoE.

Checked first, because the rule is a safety rule: the spec picks its critic from `listActiveModels`, so the two inactive Qwens (35B, 27B) can never be chosen — the exact pair that exhausted this machine in #260 is unreachable. Memory after: **23.4 GB free, higher than before**, because LM Studio unloads as it goes.

**The skip is gone. The test runs.** And on its first execution anywhere it fails, showing two real things:

1. **The drafter did not write prose.** It produced *"I am ready to write the scene, but I need the specific context (the data fields) to ensure I adhere to your constraints…"* — a meta-reply, accepted into the manuscript as if it were prose.
2. **The critic call timed out** — `Request timed out`, with `compose-critic` never rendering inside 90s.

Neither is chased here. A skip that has never run anywhere is unanswered, and answering it *is* the row; what it found gets its own rows rather than being folded in and half-done.

**Proof:**

```
BEFORE .... 1 skipped   "needs a chat-tagged drafter + >=1 distinct active critic model"
AFTER ..... 1 failed    getByTestId('compose-critic') not found within 90s

memory: 16.3 GB free before the second model -> 23.4 GB free after a run with both
critic candidates: listActiveModels only -> the inactive 35B/27B pair is unreachable

the accepted "prose", verbatim from the editor:
  "Please provide the **canon, characters, threads, beat, recent prose, and lore**
   mentioned in your instructions."
  "I am ready to write the scene, but I need the specific context ..."
and a toast: "Request timed out"
```

**AC impact:** AC-4 — K2 is ANSWERED, not owned: it runs, and passed/failed/skipped are reported separately. AC-1 — it is now a red with a measured reason instead of a silent unknown.


### Cycle 28 — the second model turned a green test red, and the cause was test-order luck (Z2)

**Investigated:** the full re-run's three failures against the Z1 set; `helpers/api.ts` `listChatModels`; the eleven `chatModels.find(...) ?? chatModels[0]` sites across eight specs; the registry's returned order before and after Cycle 27; `GET /v1/model-registry/default-models` (the per-capability GET answers 405).

**Issues:** none in the product. A NEWLY RED test, caused by this plan's own Cycle 27.

**Fix:** the full re-run found `composition-correction-gate` red — green in Z1, nothing in its spec or the product touched since. Cause: eleven call sites pick the drafter by `.find(<a model this account does not have>) ?? chatModels[0]`, so every one of them silently depended on registry order. Cycle 27 registered a small 12B, the registry returned it FIRST, and the Diverge path's K candidates collapsed to one on the smaller drafter.

The seeder already warns *"a second active model is NOT additive"* about the critic path. This is the other half. `listChatModels` now sorts the **account's own chat default** first, so slot 0 is a declared preference, not an accident of order; a missing default falls back to registry order, exactly the old behaviour.

My first version of the helper called the per-capability GET, which answers **405** — it would have fallen back silently and fixed nothing while looking correct. Checked the endpoint before trusting the green.

**Proof:**

```
full re-run:            197 passed, 3 failed, 0 skipped
  NEWLY RED:            composition-correction-gate   (green in Z1)
registry order after Cycle 27:
  0 google/gemma-4-12b-qat        <- new, small, now the drafter
  1 google/gemma-4-26b-a4b-qat    <- the account chat default
GET /default-models/chat -> HTTP 405 ; GET /default-models -> {"defaults":{"chat":"01a09a53-..."}}

AFTER:  composition-correction-gate  1 passed (33.1s)
BITE — disable only the reorder:
  Expected: >= 2   Received: 1   1 failed
RESTORED: all eight order-dependent specs  13 passed (1.9m)
```

**AC impact:** AC-5 — the newly red test was caught, explained and closed rather than reported as a pass. AC-2 — bitten both ways.


```goal-prompt
goal: every one of the 18 remaining failures is green or carries a recorded reason it cannot be, every product fix is proven by RE-BREAKING it, and both skips are answered or owned
po_decisions: [F2, H1, H2, AC-7]
lanes: |
  F fix      = F1, F3, F4, F5, F2, F6, F7, F8, F9
  G diagnose = G1, G2
  J fixture  = J1, J2, J3
  H decide   = H1, H2, H3, H4
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
