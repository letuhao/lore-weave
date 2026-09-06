# CP-0.6 — binding format: **complete, and it discriminates nothing**

Ran 2026-08-04, all five arms, `gemma-4-26b-a4b-it-uncensored-apex-quality` (the local target
model), temperature 0.2, n=3 per arm. Raw: `binding-format-20260804T035320Z.json`.

| arm | exact | invented | sent decoy | no call |
|---|---|---|---|---|
| `prose` — the id buried in narration (how it reaches the model today) | **3/3** | 0 | 0 | 0 |
| `labelled` — `chapter_id: <uuid>` under a PLAN STATE heading | **3/3** | 0 | 0 | 0 |
| `binding` — named as a binding, with its producer | **3/3** | 0 | 0 | 0 |
| `json` — structured plan with `emits`/`accepts` | **3/3** | 0 | 0 | 0 |
| **`decoy_control`** — two ids present, the WRONG one mentioned more recently | **3/3** | 0 | **0** | 0 |

## The result is a ceiling, and it is not the good news it looks like

**Every arm is perfect, so no arm is better than any other.** This measurement was built to choose a
binding format for CP-3's projection. It cannot: five formats are indistinguishable at this n on
this task.

**The control is what makes that readable rather than ambiguous.** `decoy_control` puts a second,
wrong UUID in the context and mentions it *more recently* than the right one. The model sent the
correct id 3/3 and never once reached for the decoy — so it is genuinely resolving the binding, not
copying the nearest identifier. Without this arm, five 3/3s would have been equally consistent with
a model that ignores the plan entirely; that is why an arm whose answer is available without reading
the binding is theatre, and why this one existed.

## What may and may not be concluded

**May:** on this model, at this difficulty, *the written form of a binding is not the bottleneck.*
The prose form — the one production uses today — is already sufficient to carry one identifier
across one step.

**May not:** that any format is *better*. **`3/3` bounds a failure rate only at ≤63.2%** (n=3), so
five arms at 3/3 do not rank formats — they **fail to rank** them, which is a different statement
and the one that goes in the spec.

**And the task was too easy.** One binding, one step, no compression, a context of a few hundred
tokens. The 61.8%→6.0% carry-forward class occurs after *many* steps, under compression, with
several live bindings competing. This measurement does not reach that regime, so it says nothing
about it.

## What CP-3 should take from this

1. **Do not spend CP-3 choosing a format on this evidence.** Take the cheapest that satisfies §0.11's
   rule (*identifiers are never compressed*) — the structural `binding` form — because it is
   checkable, not because it measured better. It did not.
2. **The discriminating experiment is a different one:** N bindings across M steps with the
   projection under real compression pressure, which is only constructible once the projection
   exists. It belongs to CP-3, not to CP-0.
3. **This arm set stays as the regression floor.** If a future projection change makes any of these
   five drop below 3/3, that is a real regression on a case that demonstrably worked.
