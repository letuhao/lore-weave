# RUN-STATE — Work Assistant autonomous build

> ## 📌 READ THIS FILE FIRST after any compaction, and at every checkpoint.
> This file — not my memory of the conversation — is the source of truth for the run.
> Context is lossy. Disk is not.

**Started:** 2026-07-11 · **Branch:** `feat/context-budget-law` · **Mode:** long autonomous run, self-checkpointing.
**Spec set:** [`docs/specs/2026-07-11-work-assistant-mode/`](../specs/2026-07-11-work-assistant-mode/README.md) ·
**Sealed decisions:** [`DECISIONS-SEALED.md`](../specs/2026-07-11-work-assistant-mode/DECISIONS-SEALED.md) (binding) ·
**Plan:** [`implementation-plan`](2026-07-11-work-assistant-implementation-plan.md)

---

## 1. The goal (one sentence)

**Ship the Work Assistant end to end — Phase 0 → Phase 5 — with every slice `/review-impl`-clean, every
deferred item closed before "done", and no silent lowering of the bar.**

## 2. Autonomy contract (agreed with PO 2026-07-11)

| | Rule |
|---|---|
| **Don't stop** | Work continuously. Solve deferred items until closed. Do not pause for approval between slices or phases. |
| **Self-checkpoint** | I checkpoint myself (commit + update this file). No human gate at checkpoints. |
| **Auto-compact** | Session compacts at the limit; **on resume, re-read this file first.** |
| **`/review-impl` per phase** | **Mandatory.** Findings fixed in the same phase, not deferred. |
| **I decide** | All ordinary technical decisions are mine. Record them in §6. |
| **STOP only if** | (a) **dangerous** — destructive/irreversible, security-critical, or data-loss risk; or (b) **needs redesign** — a sealed decision turns out to be wrong. Then: stop, write it up, ask. |
| **Blocked ≠ stop** | If I cannot solve something: **park it in §7, move to other work, keep going.** PO reviews parked items and decides. Never block the run on one problem. |
| **Final audit** | At the end: decisions · drift · debt · deferred · completeness (§6–§10). Built incrementally so the audit is a *byproduct*, not archaeology. |

## 2b. The `/goal` condition (the human↔agent commitment — durable copy)

The human sets this with `/goal` (a built-in CLI command; **the agent cannot set it**). Recorded here so it
survives compaction and can be re-set verbatim. ⚠️ The `/goal` evaluator **reads the transcript only — it
cannot run commands or read files**, so the condition is deliberately written to force proof *into* the
transcript.

```
/goal Phase 0 of docs/plans/2026-07-11-work-assistant-implementation-plan.md is COMPLETE. Done means ALL of: (1) every slice WS-0.1..WS-0.9 is marked ✅ in docs/plans/2026-07-11-work-assistant-RUN-STATE.md §5 with a real evidence string; (2) the transcript contains the ACTUAL PASTED OUTPUT of the test runs and the live-smokes from §5 of docs/specs/2026-07-11-publish-independent-kg-indexing.md — specifically: a draft chapter that is never published gets indexed into the KG; autosave triggers ZERO extraction jobs; a single index click leaves the other 199 chapters' extraction_leaves intact; the whole-book rebuild enumerates draft-indexed chapters; and composition's index_stale is false after publish@A + index-draft@B; (3) /review-impl has been run on the phase and every finding is FIXED (not deferred), with the fixes committed; (4) the transcript shows `git log --oneline` with the commits; (5) RUN-STATE §6-§9 registers are updated. Claiming a check passed without pasting its output does NOT satisfy this condition. If you cannot solve something, park it in RUN-STATE §7 and continue with other slices — do not stop. Stop and ask ONLY if an action is destructive/irreversible or a sealed decision turns out to be wrong. Or stop after 60 turns.
```

**Subsequent phases:** re-set `/goal` per phase, same shape (evidence pasted into the transcript, findings
fixed not deferred, registers updated, turn-bounded).

## 3. Standing invariants (the bar — never lower these silently)

These are the things that *feel* skippable at 2am and must not be:

1. **A slice is DONE only when its evidence string exists in §5.** Not when the code compiles. Not when tests
   are green. **Evidence = the behavior was observed.**
2. **Live-smoke for any slice touching ≥2 services.** Unit-green has hidden cross-service bugs 4× in this repo.
3. **Consumed-by-effect** — every flag/guard/setting gets a test asserting the *behavior*, not the stored value.
4. **Fail-closed** — every privacy/spend toggle defaults off and fails closed.
5. **No silent success** — a success status with no work done is a **bug**. Every skip logs a reason.
6. **Erasure tests assert ABSENCE** (row gone, node gone, rebuild doesn't resurrect) — never "invisible".
7. **Never `git add -A`** — enumerate files (concurrent sessions share this checkout).
8. **Grep before trusting a list.** The red team found "canon = published" in 6+ places after I'd found one.
   *Assume my enumeration is incomplete.*

**Mechanical enforcement:** use `scripts/workflow-gate.py` (+ the pre-commit hook) — it blocks phase jumps and
commits without VERIFY/POST-REVIEW evidence. If I find myself wanting to bypass it, that **is** the drift.

## 4. Phase board

| Phase | Status | `/review-impl` | Notes |
|---|---|---|---|
| **0 — Publish-independent KG indexing** | ⬜ not started | ⬜ | Prereq. 4 services. Red team: "do not build as written" (v1) → v2 fixed |
| **1 — Assistant MVP + diary-lite** | ⬜ | ⬜ | WS-1.0 (encryption) ships FIRST |
| **2 — Facts · erasure · amendment · spend** | ⬜ | ⬜ | D18 erasure = release requirement (PO-4) |
| **3 — Scheduler & proactive** | ⬜ | ⬜ | |
| **4 — Voice parity** | ⬜ | ⬜ | |
| **5 — Coaching** | ⬜ | ⬜ | Gated on 4 prerequisites (R4) |

## 5. Slice board — the only place "done" is defined

`⬜ todo · 🔵 in progress · ✅ done (evidence recorded) · 🅿️ parked (see §7)`

| Slice | Status | Evidence (required for ✅) |
|---|---|---|
| WS-0.1 chapter-scoped cache invalidation | ⬜ | |
| WS-0.2 columns + backfill | ⬜ | |
| WS-0.3 all six writers + hygiene test | ⬜ | |
| WS-0.4 index action + `chapter.kg_indexed` | ⬜ | |
| WS-0.5 sweeper full re-key + unpublish | ⬜ | |
| WS-0.6 generalize the publish gate in every reader | ⬜ | |
| WS-0.7 composition mirror + canon-markers | ⬜ | |
| WS-0.8 knowledge consumer + canon flag + retraction | ⬜ | |
| WS-0.9 FE "Add to knowledge" + indexed indicator | ⬜ | |
| *(Phase 1+ slices appended as phases open)* | | |

## 6. Decision register (every call I make, so the audit is free)

| # | Decision | Why | Reversible? |
|---|---|---|---|
| *(appended as I go)* | | | |

## 7. Parked problems (blocked ≠ stopped — PO reviews these)

| # | Problem | What I tried | Why parked | Blocks what? |
|---|---|---|---|---|
| *(appended as I go)* | | | | |

## 8. Debt register (things I knowingly did the cheap way)

| # | Debt | Where | Cost of leaving it | Pay-off trigger |
|---|---|---|---|---|
| *(appended as I go)* | | | | |

## 9. Drift log (bar-lowering, caught and corrected)

Anything where I *nearly* skipped a gate, or where a spec turned out to be wrong. **Recording these is the
point** — a run with an empty drift log is either perfect or dishonest, and it is never perfect.

| # | Drift | Caught by | Corrected how |
|---|---|---|---|
| *(appended as I go)* | | | |

## 10. Completeness ledger (the definition of "done" for the whole run)

- [ ] Every phase built, `/review-impl`-clean
- [ ] Every parked problem (§7) resolved or explicitly accepted by PO
- [ ] Every debt (§8) paid or converted to a tracked defer with a gate reason
- [ ] Every sealed decision (DECISIONS-SEALED) still true — or amended with a review-record line
- [ ] The 5 "most likely to go wrong" items in the plan each have a passing test
- [ ] `docs/sessions/SESSION_HANDOFF.md` updated
- [ ] Final audit written: decisions · drift · debt · deferred · completeness

---

## 11. If you are me, resuming after a compaction — do this

1. Read this file (you just did).
2. `git log --oneline -10` — what actually landed.
3. Read §5 for the current slice; §7 for what's parked.
4. Re-read the slice's spec section **before** touching code (do not trust a remembered summary of it).
5. Continue. Do not re-litigate a sealed decision.
