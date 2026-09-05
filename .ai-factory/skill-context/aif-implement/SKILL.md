# LoreWeave overrides for `aif-implement`

Read [`.ai-factory/skill-context/aif/SKILL.md`](../aif/SKILL.md) first — it carries the precedence rules and the
project invariants. This file covers only what changes for implementation work.

## Tests are NOT opt-in here

`aif-implement`'s general rule is *"Do not add tests by default … when in doubt, prefer NO
tests."* **That rule does not apply to this repository.** LoreWeave's Phase 6 VERIFY is an
evidence gate: run the command, read the whole output, then claim. A change that alters
behaviour ships with a test that would fail without it.

This is not stylistic. The repo's history is a list of defects that unit-green code hid —
which is also why a passing test is not automatically evidence: if the test cannot fail when
the behaviour breaks, it is a claim wearing the costume of evidence. Break the guarded thing,
watch it go red, put it back, paste the output.

Exceptions are narrow and stated out loud: a pure rename, a comment, a generated file.

## Execute the plan, do not narrate it

`aif-implement` Step 3.8 asks *"ready to commit?"* at every commit checkpoint. **That prompt is
disabled in this repository.** A plan here routinely carries 10–15 checkpoints, so honouring it turns
one execution into fifteen interrupted ones, and the human is answering "yes" to a question whose
real gate — the QC task — has already been evaluated by the agent.

**Commit at a checkpoint without asking, provided the checkpoint's QC task is green.** If the plan
has no QC task for that checkpoint, the tests-and-evidence rule above is the gate. QC red is not a
reason to ask either: fix it and carry on.

**Between tasks, keep going.** Do not stop to summarise progress, do not hand back because the next
task looks large, do not treat a phase boundary as an ending. Stop only for:

- an explicit ⏸ POST-REVIEW checkpoint the plan marks stop-and-wait,
- a stop condition the plan names,
- a decision genuinely reserved to the PO,
- exhausted context.

**Exhausted context is a handoff, not a stop.** Write the current task's evidence into the plan,
refresh whatever "current state" block it carries, and end with `RESUME: <task id>`. Then the next
invocation — or `/loop /aif-implement @<plan>` — picks it up. Stopping *cleanly* mid-plan without
leaving that pointer is the failure mode: it reads as completion and the next session re-derives
what was already done.

## Follow the repo's phases, not a parallel set

Implementation sits inside `CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY → REVIEW → QC
→ POST-REVIEW → SESSION → COMMIT → RETRO`. The state machine is real:

```bash
./scripts/workflow-gate.sh size M 3 4 0 45     # classify first
./scripts/workflow-gate.sh phase build
./scripts/workflow-gate.sh complete build "<evidence>"
```

- **Never self-authorise a skip.** If the work turns out larger than classified, stop,
  reclassify, and say so.
- **POST-REVIEW is a human checkpoint** — present the summary and WAIT. Do not pre-write
  "0 issues found"; that is the rubber-stamp tell.
- When a change spans **≥2 services**, unit-green is insufficient — the VERIFY evidence needs
  a `live smoke:` line, an explicit `LIVE-SMOKE deferred to D-…` row, or
  `live infra unavailable: <reason>`.

## Frontend work

React MVC separation is enforced by convention and review: hooks own logic, components render,
context shares state. Never conditionally unmount stateful components; no `useEffect` for event
handling; split context by update frequency. Check
[`docs/FEATURE_INDEX.md`](../../../docs/FEATURE_INDEX.md) **before** adding a feature folder,
and update it in the same commit.

## Fix now, defer rarely

There is no deadline here, so "we'll come back to it" is the trap. A finding may be deferred
only if it clears the eligibility gate in `AGENTS.md` (out of scope · large/structural ·
naturally-next-phase · genuinely blocked externally · conscious won't-fix). **"I'd have to
build it" is not "blocked."** If writing the defer row costs more than the fix, just fix it.
