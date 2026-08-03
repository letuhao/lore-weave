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
