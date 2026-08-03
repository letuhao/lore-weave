# LoreWeave overrides for `aif-review`

Read [`.ai-factory/skill-context/aif/SKILL.md`](../aif/SKILL.md) first.

## Two stages, both must pass

1. **Spec compliance** — does the code implement what was designed? Anything missing? Any
   scope creep?
2. **Code quality** — patterns, security, accessibility, performance, maintainability.

Issues found → fix → **re-VERIFY** → re-review. A review that ends "0 issues found" without
having tried to break something is the rubber-stamp tell, not a result.

## What this repo has actually been bitten by — look here first

- **A check that cannot fail.** Four shapes, each a real occurrence: the subject cannot vary ·
  the scope never reaches it (an enumerated file list is default-uncovered — what about a file
  added tomorrow?) · an adjacent decision defeats it · the escape hatch cannot reach its reason.
  If the change adds a gate, lint, test or assertion, demand the red-then-green evidence.
- **A tenancy hole.** A shared row any authenticated user can mutate. Ask: who owns this row,
  what is its scope key, can user A's action change user B's view?
- **A provider SDK imported directly**, or a model name/price hardcoded in runtime code.
- **A per-user choice implemented as a global env flag** — "would two users want different
  values?" If yes, it is a user setting, not `*_ENABLED`.
- **A stored-but-never-read setting** — write-only behaviour is a bug, not a feature.
- **Mock-only coverage across a service boundary.** If the change spans ≥2 services, unit-green
  is not evidence; look for the live smoke.
- **Non-English text in a persisted artifact** — most often a quote pasted into a doc. Quote the
  *meaning* in English.

## Deferring a finding

A finding may be deferred only if it clears the gate in `AGENTS.md`. "It would take work" is not
"blocked". If the defer row costs more than the fix, fix it. Anything deferred gets a tracked row
**and a mechanism** — an asserted trigger, a `KNOWN_RED` row, or a test named for it. Prose alone
does not survive; that is measured, not theoretical.

## Emitting the result

Follow the shared `aif-gate-result` contract (`aif-verify/references/GATE-RESULT-CONTRACT.md`):
human-readable report first, then one final fenced `aif-gate-result` JSON block. This repo has
adopted that contract as the uniform shape for gate output — see
[`docs/standards/agent-workflow.md`](../../../docs/standards/agent-workflow.md).
