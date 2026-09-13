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

- [ ] **F2** — **#263**, the API offers `arc` and `beat`; the table permits `chapter` and `scene`.
  *(1 test)* **A DATA-MODEL DECISION, not a repair.** Investigate which half is correct — was the
  migration missed, or is the `Literal` stale? — then **present both options with a
  recommendation and STOP.** Widening a CHECK constraint to make an INSERT succeed is exactly the
  hollow fix this plan is guarding against.

- [ ] **F3** — **#264**, the structure editor claims unsaved changes after a save. *(2 tests)*
  `initial` is a `useRef` captured at mount and never reassigned, so the draft is permanently
  "diverged" after the first edit. The baseline must move on save success — and the component's
  remount/`onDirty` contract has to stay coherent. **Re-break:** freeze the baseline again; both
  must go red.

- [ ] **F4** — **#265**, approving the cast checkpoint leaves `pass_cursor` at 1. *(1 test)*
  Backend. Find where approval is meant to advance the cursor and why it does not.
  **Re-break** once fixed.

- [ ] **F5** — **#266**, the grounded affirmation never renders. *(1 test)*
  The run records `grounded_on` and `plan-grounded-note` exists in `PlannerPanel.tsx`, so the gap
  is between them. **Re-break** once fixed.

- [ ] **F6** — `composition-journey` asserts **1** scene where there are **2**. *(1 test, from F1)*
  It is past #262 now and fails on `composition-scene-select` option count — `unexpected value
  "2"`. The GUIDED first run seeds an "Opening scene" before `addScene` adds its own; this is
  the identical stale assumption Cycle 12 of red-by-red fixed in `composition-gate`, in a spec
  that never got there because the reasoning control blocked it first. Harness, not product.

### Lane G — diagnose before touching anything.

- [ ] **G1** — **#267**, `ui_open_book` / `ui_show_panel` never navigate. *(2 tests)*
  The sibling card tests pass on the same suspend/resume machinery, so the plumbing works and only
  the navigation does not. Find the cause, THEN decide who owns it. A verdict of
  "undiagnosed, with the trace" remains legal and is better than a guess.

- [ ] **G2** — **#268**, wiki articles never appear after Generate. *(1 test)*
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

## What this plan will NOT do

- **It will not edit the product until a test passes.** Every fix is proven by re-breaking it.
- **It will not weaken, skip, delete or `fixme` a test** to make a fix look complete.
- **It will not decide #263, #269 or the one-model question.** Those are the PO's.
- **It will not activate a second model** to clear a skip.
- **It will not run against anything but loopback**, and never against the PO's own stack.
- **It will not tag, build or publish anything.**

RESUME: Cycle 1 done. F1: #262 FIXED (portal, not z-index -- the probe proved there was NO competing stacking context; the menu opened upward out of an overflow-auto container and was clipped out of reach) and RE-BROKEN per Rule 1. 3 of its 4 tests green; the 4th is now F6 (composition-journey asserts 1 scene where the guided first run makes 2 -- the same stale count Cycle 12 fixed elsewhere). Head of the queue is F3 (#264, the false 'unsaved changes' -- reset the dirty baseline on save success). F2, H1, H2 STOP for the PO with options ready.

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
