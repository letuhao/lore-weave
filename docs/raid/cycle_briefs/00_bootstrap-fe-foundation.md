# Cycle 0: Bootstrap — shared FE foundation

## 🎯 TL;DR (30 seconds — TOP critical info)
Lay the shared frontend primitives every later creation-unblock cycle reuses: a scrollable `FormDialog` (max-height + internal scroll + pinned action footer so tall forms never bury their submit button), a reusable **`AddModelCta`** that deep-links to model registration and returns the user to where they were, and a **`rerank`/`reranker`** terminology reconcile across the capability-flag plumbing with a wiring test so the picker filter and the flag agree.
- **Scope:** Shared FE foundation — no BE, no new service calls. Pure reusable UI + a vocabulary fix that unblocks the rerank cycles.
- **Acceptance gate:** `scripts/raid/verify-cycle-0.sh` exits 0 (this cycle's runner creates that script).
- **Top 3 LOCKED decisions consumed:** G6 (book-workspace IA — `AddModelCta` deep-link + return pattern), G4 (Playwright UI smoke = screenshot evidence), Scope-LOCKED (rerank is optional grounding-quality, C0 just reconciles the term).
- **DPS count:** 3
- **Estimated wall time:** ~2 hours

> NOTE: C0 is built via the **default workflow**, not `/raid`. This brief exists for the record so the rerank/knowledge cycles have a grep-able foundation dependency.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: none
- Files expected to exist: `frontend/src/components/shared/FormDialog.tsx`, `frontend/src/features/settings/CapabilityFlags.tsx`

## Scope (IN)
- `frontend/src/components/shared/FormDialog.tsx` — apply `max-h` + internal `overflow-y-auto` body + a **pinned (sticky) action footer** so the primary action stays reachable on tall forms (BL-4 / KN-3).
- Reusable **`AddModelCta`** component — a deep-link to the model-registration surface that carries a return path and round-trips the user back to the calling form (consumed by C5, C15).
- Reconcile **`rerank` vs `reranker`** naming across `CapabilityFlags` + the model-picker filter so the capability flag and the picker's match predicate use ONE canonical token.
- A **wiring/unit test** asserting the picker filter matches the capability flag (the nil-tolerant-wiring lesson: a dropped wire must fail a test, not silently no-op).
- `scripts/raid/verify-cycle-0.sh` (acceptance gate) + a Playwright screenshot of a tall dialog scrolling with its footer action reachable.

## Scope (OUT — explicitly)
- NO backend changes; NO provider-registry calls; NO new model-registration page (only the CTA that links to the existing one).
- NO rerank discovery / connection-test logic — that is C2 / C3.
- NO `BookPicker` (C4), NO `BuildGraphDialog` gating (C5), NO knowledge IA restructure (C6/C7).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `frontend` unit test for the picker-filter↔capability-flag wiring (the rerank/reranker reconcile) green.
- Lints pass: `frontend` eslint/tsc clean on touched files.
- Integration smoke (FE-only, Playwright screenshot per G4): a tall `FormDialog` scrolls internally and its pinned footer action stays clickable; `AddModelCta` round-trips (click → registration surface → return). Screenshot filed with this brief.

## DPS parallelism plan
- DPS 1: `FormDialog.tsx` max-h + scroll + pinned footer (return budget: 1500 tokens summary).
- DPS 2: `AddModelCta` reusable component + return-path round-trip.
- DPS 3: rerank/reranker reconcile in `CapabilityFlags.tsx` + picker filter + wiring test (seam-stub the token, integrate last).
- Serial tail: `verify-cycle-0.sh` + Playwright screenshot once DPS 1–3 land.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- Pinned footer that overlaps scrolled content or clips the last field — verify the body scroll region and footer are siblings, not nested.
- `AddModelCta` that hard-codes a route or drops the return path → user lands nowhere after registering.
- rerank/reranker reconcile that fixes ONE site and misses another → the wiring test must actually cover the picker filter call site (spy-injection, not a string-equality stub that always passes).
- Conditional-unmount of the dialog (CLAUDE.md FE rule) — ensure CSS `hidden`/internal branching, not ternary unmount.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (`FormDialog` scroll+footer, `AddModelCta`, rerank reconcile + wiring test).
- No OUT items touched (no BE, no discovery/test logic, no BookPicker).
- All acceptance criteria met; `verify-cycle-0.sh` exits 0 with a filed Playwright screenshot.
- Cross-cycle invariant: the canonical rerank token is the one C1/C2/C3 will consume.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) C0.
- LOCKED: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) §Scope, §G6, §G4.
- Source spec: [knowledge-service-standalone-ux-review](../../specs/2026-06-13-knowledge-service-standalone-ux-review.md) (KN-3 dialog scroll). BL-1..4 origin per the decomposition Sources list (knowledge-fe-ux-qol-gaps).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **G6 LOCKED:** `AddModelCta` must deep-link AND return — it is the book-workspace navigation glue reused by C5/C15; a one-way link breaks the flow.
- 🔴 **G4 LOCKED:** FE VERIFY = a real Playwright screenshot (test account `claude-test@loreweave.dev`), not "units pass". File it with this brief.
- 🔴 **Scope LOCKED:** rerank is optional grounding-quality — C0 only reconciles the `rerank`/`reranker` term + adds the wiring test; it does NOT register/discover/test models.
- 🔴 **Wiring-test rule:** the picker-filter↔flag test must fail if the wire is dropped (spy/injection), else a future reconcile silently no-ops.
- 🔴 **Do NOT touch:** any backend, provider-registry, BookPicker, BuildGraphDialog, or the knowledge IA — those are later cycles.
- 🔴 **Fresh session reminder:** this brief is for-the-record; C0 ships via default workflow. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
