# Plan Acceptance Criteria — a plan states what DONE means, before work starts

**Status: ENFORCED** by [`scripts/plan-acceptance-criteria-gate.py`](../../scripts/plan-acceptance-criteria-gate.py)
(self-tested, wired via the `--run-all` runner). Introduced 2026-09-13.

## 1. AC-1 — the rule

> **Every plan declares its acceptance criteria BEFORE its board, and a plan is not done while any
> criterion is unmet and unwaived.**

A board of tasks is not a definition of done. Tasks say what somebody intends to *do*; acceptance
criteria say what must be *true* afterwards. Those are different, and only the second can settle a
release argument.

## 2. Why this exists, and it is not hypothetical

On **2026-09-13** a release candidate reached `main` with 23 remediation rows all ticked, every one
carrying pasted bite evidence, every gate green — and neither the PO nor the agent could answer
*"can this ship?"*. The PO's words:

> *"this work is ad-hoc … what have we done and not, without ACs we cannot decide this repo can
> ship v0.1.0 or not"*

Nothing had gone wrong on the board. The board was simply answering a different question. Twenty-
three finished tasks establish that twenty-three intentions were carried out; they say nothing
about whether the product is acceptable, because **nobody had written down what acceptable meant.**

The same session had already produced the sharper version of this failure: an agent stopped three
separate times to report a goal "complete", then found more work each time a different check was
run. Without criteria there is no last check — only the next one.

## 3. The shape

A plan carries one `## Acceptance criteria` section, ABOVE its board:

```markdown
## Acceptance criteria

| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | Every README capability claim is true of the build or marked with its phase | `scripts/readme-claim-phase-gate.py` | T22, T23 | ✅ met — gate OK, self-test 9/9 |
| **AC-2** | No user-facing string ships that no person has read | T6's review record | T5, T6 | ❌ not met |
| **AC-3** | A real browser completes the author journey end to end | `persona-journeys.spec.ts` on a rebuilt stack | T3, T4 | ❌ not met |
```

Five columns, and each earns its place:

- **AC** — a stable id (`AC-<n>`). Referred to in commits and in the ship decision.
- **Must be true** — a statement about the WORLD that **can be false**. Not a task. Not "review the
  strings" (an activity) but "no unreviewed string ships" (a state).
- **Verified by** — the *named* check: a script, a suite, a live run, a document. **"Reviewed" and
  "tested" are not verification methods**; they name no artifact a third party can re-run or read.
- **Rows** — which board rows serve this criterion. Empty means the criterion is *unclaimed*: real,
  agreed, and nobody is doing it. That is legitimate and must be visible.
- **Status** — `✅ met` with its evidence, `❌ not met`, `🚧 partial` with what remains, or
  `🅿 waived` naming **who** waived it and **why**.

## 4. The rules the gate enforces

| id | rule |
|---|---|
| **AC-1** | The plan has an `## Acceptance criteria` section with at least one row. |
| **AC-2** | Ids are `AC-<n>`, unique within the plan. |
| **AC-3** | Every criterion names a verification method. Bare "reviewed"/"tested"/"checked"/"n/a" is rejected. |
| **AC-4** | Status is one of the four tokens. An invented status is a status nobody can filter on. |
| **AC-5** | `✅ met` carries evidence text. A tick with nothing after it is the claim this repo already refuses everywhere else. |
| **AC-6** | `🅿 waived` names a waiver. A waiver with no author is an unattributed decision. |
| **AC-7** | Every board row is referenced by at least one criterion, or the plan says why not. Work serving no criterion is work nobody agreed was needed. |

## 5. What this is NOT

**It is not a second board.** Criteria do not get ticked by doing tasks; they get met by the world
being a certain way, which is usually established by running something.

**It does not replace [Non-Vacuity](./non-vacuity.md).** NV governs whether a *check* can fail; this
governs whether the *plan* said what passing means. A plan can satisfy every AC with checks that
cannot fail — that is an NV-6 violation and NV catches it. They compose: **AC says which checks
must exist, NV says those checks must bite.**

**It is not a release process.** See [Versioning & Releases](./versioning-and-releases.md) for how a
version ships. This only guarantees that when the ship question is asked, there is something to
read other than a list of finished tasks.

## 6. Scope, stated honestly

The gate applies to plans dated **2026-09-13 or later**, by the date in the filename. The repo's
existing planning corpus predates the rule and is not retrofitted — a rule applied retroactively to
dozens of closed plans produces a wall of red that teaches everyone to ignore the gate, which is
worse than not having it.

The gate **reports** how many plans it skipped for this reason on every run, because a check that
silently examines a fraction of its subject is the failure mode this repo has fixed more than once.
