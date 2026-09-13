# LoreWeave overrides for `aif-plan`

Read [`.ai-factory/skill-context/aif/SKILL.md`](../aif/SKILL.md) first.

## Where plans and specs live

This repo predates `.ai-factory/` and keeps its planning corpus in `docs/`:

| Artifact | Path |
|---|---|
| Spec (CLARIFY) | `docs/specs/YYYY-MM-DD-<topic>.md` |
| Plan (PLAN) | `docs/plans/YYYY-MM-DD-<feature>.md` |
| Session state | `docs/sessions/SESSION_HANDOFF.md` |
| Deferred items | `docs/deferred/DEFERRED.md` |
| Legacy tracks | `docs/03_planning/<TRACK>/` |

Write there, not into `.ai-factory/PLAN.md`, so one corpus stays searchable.

## State what DONE means, before the board

**Every plan carries an `## Acceptance criteria` section, above its task board.** This is a project
rule and it is ENFORCED — `scripts/plan-acceptance-criteria-gate.py` fails a plan without one.

A board says what you intend to **do**. Acceptance criteria say what must be **true** afterwards.
Only the second can answer *"is this done?"*, and the difference is not academic: on 2026-09-13 a
release candidate reached `main` with 23 rows ticked, every row carrying pasted bite evidence and
every gate green, and the PO still could not decide whether it could ship — *"without ACs we cannot
decide this repo can ship v0.1.0 or not"*.

Five columns, one row per criterion:

```markdown
| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | No user-facing string ships that nobody has read | `i18n-placeholder-parity-gate.py` + the review record | T5, T6 | ❌ not met |
```

- **Must be true** is a statement that can be FALSE — a state of the product, not an activity.
  *"Review the strings"* is a task; *"no unreviewed string ships"* is a criterion.
- **Verified by** names an artifact someone else can re-run or read. **"Reviewed" and "tested" are
  rejected by the gate**; they name nothing.
- **Rows** ties criteria to work. A board row no criterion references is work nobody agreed was
  needed, and the gate says so.
- **Status** is `✅ met` (with its evidence), `❌ not met`, `🚧 partial`, or `🅿 waived` naming who
  waived it and why.

Full rule: [`docs/standards/plan-acceptance-criteria.md`](../../../docs/standards/plan-acceptance-criteria.md).
It composes with [Non-Vacuity](../../../docs/standards/non-vacuity.md) rather than replacing it:
**AC says which checks must exist, NV says those checks must be able to fail.**

## Read before planning

- The **▶ NEXT SESSION** block of `docs/sessions/SESSION_HANDOFF.md`.
- The **Deferred Items** section: any row whose target phase is the current phase is a
  must-do for this plan, not a suggestion.
- [`docs/standards/README.md`](../../../docs/standards/README.md) for any rule governing the area you are about to touch.

## Size the whole effort, once

Classify by **complexity and risk**, not file count — a wide mechanical sweep is not XL:

```bash
./scripts/workflow-gate.sh size <XS|S|M|L|XL> <files> <logic> <side_effects> <context_pct>
```

Logic (distinct semantic changes) is the primary axis; side effects (API/DB/config/migration/
auth) set a hard floor. Classify the **whole coherent effort as one** — not each sub-task with
its own build/review/commit cycle.

## Do not fan out sub-agents by list element

One agent per question, per finding, or per row is the anti-pattern — it once cost 605 agents
and ~45M tokens to produce what 4 agents grouped by file produced for 864k. Group by **file or
disjoint slice**, and before any fan-out state: *"N agents, each reading ⟨what⟩, because ⟨why one
agent can't⟩."* If you cannot complete that sentence, do not fan out.
