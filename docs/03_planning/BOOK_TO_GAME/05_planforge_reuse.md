# 04 — Can PlanForge be reused, or must this be built new?

The PO asked directly. The answer is neither of the two obvious ones, and the shape of the answer is
the same shape the game tier already found for its planner kinds: **the machine is reusable and the
schema is not.**

Everything below is read from `services/composition-service/app/engine/plan_forge/` and its fixtures.

---

## 1. What PlanForge actually is

Not a prose writer. **PlanForge extracts a SYSTEM from a novel** — and that is the finding that changes
the answer, because it was not what the name suggested.

Its output, `NovelSystemSpec`, as it appears in `tests/fixtures/plan-forge/llm_mock_spec.json`:

```
meta      { title, version_label, open_questions[] }
charter   { consistency_anchors[], forbids[], style_constraints[] }
layers    { characters[]
            mechanics[]  { id, name, rules[], planner_secrets[] }
            variables[]  { code, name, range, transition_rules[] } }
arcs[]    { id, title, theme, arc_kind, summary }
events[]  { id, arc_id, title, synopsis, goal, planner_notes, var_deltas[] }
links[]
```

Three of those fields are things this tier was about to invent from nothing:

* **`charter.consistency_anchors` / `charter.forbids`** — a human-authored statement of what the work
  must stay true to and what it must never do, with `eval_fidelity.py` scoring a spec against it. That
  is the fidelity mechanism of §[`04`](04_fidelity.md), already built, already evaluated.
* **`meta.open_questions[]`** — the assistant's unanswered questions, **as a first-class field of the
  artifact**. The "workflow that keeps asking the human questions" has a home in the schema.
* **`layers.variables[] { code, range, transition_rules }`** — strikingly close to `PPL-A1`'s definition
  of a progression system (variables · inflows · gates · couplings). And one of PlanForge's seven
  validator rules is **`pa_not_realm`** — the power variable must not *be* the cultivation ladder.
  A novel-planning tool already encodes a distinction the game tier had to rediscover.

## 2. What is reusable, and it is most of the machine

| piece | why it transfers |
|---|---|
| the **run model** — `POST /v1/books/{book_id}/plan/runs`, `NovelSystemSpecPatch` (`extra: allow`), modes, `force` | authoring a game concept is a run against a book producing a versioned spec plus patches. Identical shape. |
| `interpret.py` + `apply_policy.py` (**`focus_paths`**) | the human says something in chat; it is interpreted into a **patch against specific spec paths** and applied under policy. This is the human-in-the-loop the game tier has been faking with `approve = lambda: True`. |
| `eval_chat_hil.py` (I1–I4) | the HIL turn is already **measured** — did the interpretation focus where the human meant, did the patch land |
| `charter` + `eval_fidelity.py` | §[`04`](04_fidelity.md)'s charter, already scored |
| `meta.open_questions[]` | the question channel |
| `existing_state.py` / `ground_on_existing` | a new run grounded on what has already been authored — the difference between iterative authoring and starting over each time |
| `self_check.py`, `refine.py` | the quality loop, and the precedent for the game tier's own heal round |
| `compare.py` | spec diffing (keyed by `variables[].code`) — what a fidelity change invalidates |
| `json_extract`, `normalize`, `llm_client`, `prompts` | plumbing, already provider-gateway-clean |

> **`BTG-A10`.** The reusable part is the **authoring machine**: run → interpret → patch → validate →
> re-run, with a charter, open questions, and a measured HIL turn. That machine is expensive to build,
> it is built, and it is measured. Rebuilding it for the game tier would be the third divergent idiom in
> a repo that already measured the cost of the second (`BLD-A6`).

## 3. What is not reusable, and the reason is precise

| piece | why it does not transfer |
|---|---|
| `arcs[]`, `events[]`, `var_deltas[]` | narrative structure. A game concept has no arcs; it has entities and closed sets. |
| the seven validator rules — `spec_has_arc`, `spec_has_events`, `every_arc_has_events`, `arc2_discovery`, `anchors_min`, `vars_four`, `pa_not_realm` | every one is a statement about a *story*. Against a game concept they are either vacuous (no arcs to check) or wrong. |
| `compile.py` | compiles the spec for narrative consumption |

And the one that matters most:

> **`BTG-A11`.** **PlanForge models a system DESCRIPTIVELY; a game needs it ENUMERATIVELY.**
> `layers.variables[]` says *what varies and how*; `mechanics[].rules[]` is free text. Neither can say
> *"these are all six equip slots and there are no others"* — there is no place in the schema for a
> **closed set**, and closure is the whole product of the game tier (`EPL-A1`, `PPL-A2`). This is not a
> missing field. A novel does not need closure and would be damaged by it: an author who has enumerated
> every possible treasure has written a rulebook.

So the answer to *reuse or rebuild* is: **reuse the machine, replace the schema and the rule set.**
Which is exactly the relationship the contract generator has to its own planner kinds — the operation
decides the criteria, and the machine is shared (`BLD-A1`, `BLD-A5`). The pattern is already this
project's pattern.

There is also a **precedent for how to do it safely**: `validate_story_grid.py` exists as a
side-by-side module, deliberately *not* imported by `validate.run_rules`, because a locked decision
said a new rule set must be scored against the same fixtures before adoption. A game rule set enters
the same way.

## 4. The seam, restated after the two-jobs correction

The first draft asked *"if the game concept enumerates the world's closed sets, what is left for the
contract generator?"* — and treated the answer as an open discovery that might delete a subsystem.

§[`03`](03_two_jobs.md) settles the direction: **the concept does not enumerate.** It is authored,
unstructured prose; enumeration is the structuring side's job and is supposed to be deterministic.
Nothing is competing to produce the same artifact — they produce different ones, for different readers.

What remains is the platform's own two-layer pattern (`glossary-service` authored SSOT ↔
`knowledge-service` derived, anchored by `glossary_entity_id`) applied one tier up:

| | **game concept** (this tier) | **contract pool** (game tier) |
|---|---|---|
| is | the **authored SSOT** — a document | the **derived** machine artifact |
| holds | the decision, its reason, its citation, its provenance, the human's disagreements — in prose | codes, typed references, closed sets, a digest |
| audience | a human, reading and editing | a generator, resolving codes |
| changes by | someone **deciding** | **re-derivation** |
| invents | yes — that is its purpose | never |
| anchored by | — | a reference back to the concept entity, as `glossary_entity_id` anchors knowledge to glossary |

Under this split the contract generator stops planning **from the novel** and starts deriving **from
the concept** — precisely the fix §[`01`](01_the_missing_tier.md) identified for all three of its stuck
problems, arrived at from the other direction.

**What would falsify it** is no longer *"is the derivation mechanical"* — it is supposed to be. It is
this: **does the authored concept decide enough that deriving requires no judgement?** A concept that
under-decides forces the structuring side to invent, which is the one thing it must not do
(`BTG-A14`), and that is a measurable rate rather than a yes/no. §[`06`](06_poc_plan.md) POC-C measures
it.

## 5. What would have to change in composition-service

Stated so the cost is visible before anyone commits:

1. **A second spec type.** `NovelSystemSpec` is assumed throughout (`spec_index`, `compile`, `decompose`,
   `validate`). A `GameConceptSpec` is not a variant of it; the run machinery has to become
   spec-type-parametric, which it currently is not.
2. **A second rule set**, entering by the `validate_story_grid` precedent — side-by-side, scored, wired
   only by a human decision.
3. **A world-scoped run.** PlanForge runs against a `book_id`. This tier's input is a **world** — several
   books with different roles (§[`02`](02_world_as_corpus.md)). Either the run takes a world and resolves
   the bible book, or the bible book is the run target and the other members are retrieval sources.
4. **Language-rule check.** `composition-service` is Python (AI/LLM). A game-concept authoring engine is
   AI/LLM. No conflict — but the ownership row in `contracts/language-rule.yaml` has to say so.
