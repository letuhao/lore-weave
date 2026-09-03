# The declaration backlog — what gets admitted, in what order, and why

**Status of the design question, answered plainly: no declaration has been written against the new
contract yet.** C-0…C-17 exist; nothing implements them. This document is the first pass — the
candidate set, chosen from production data rather than taste, with the contract shape each one
demands.

**Selection rule.** A benchmark declaration must be **high-volume** (so evidence accrues at real
traffic rates — the whole product produces only ~414 tool calls/week) **and** must exercise a clause
whose failure class we measured. A low-traffic declaration cannot generate a bound; a high-traffic one
that exercises nothing proves nothing.

---

## 1 · The measured ground truth

Real calls only (blank-args harness traffic excluded):

| declaration | calls | fails | fail % | why it is here |
|---|---|---|---|---|
| `tool_list` | 1,744 | 1,180 | 68% | **not a candidate** — a runtime primitive, and its "failures" are the breaker cap. The new runtime replaces it |
| **`book_get`** | 555 | 496 | **89%** | **deprecated already** (*"use `book_read`"*) and still the second-busiest call in the product |
| **`kg_project_create`** | 471 | 270 | 57% | measured **×57 in a single turn** — the C-13 `re_runnable` case |
| `glossary_book_ontology_read` | 318 | 63 | 20% | the chain's entry read |
| `kg_project_entities_to_nodes` | 296 | 24 | 8% | consumes the previous step's output — a C-6 case that mostly works |
| **`glossary_propose_entities`** | 289 | 109 | 38% | the chain's producer; **its emitted `entity_id` is the one the model later sends as `"0"`** |
| **`glossary_list_chapter_links`** | 264 | **263** | **100%** | a total failure nobody noticed |
| **`book_chapter_save_draft`** | 229 | 130 | 57% | **the consumer half of the sharpest C-6 pair** |
| **`glossary_get_entity`** | 197 | 183 | **93%** | *"use after `glossary_search`"* — **the id-resolution class in one declaration** |
| `book_chapter_create` | 161 | 1 | **1%** | **the producer half.** It works; its consumer does not |
| `plan_propose_spec` | 156 | 4 | 3% | works, and is a plan-shaped step already |
| **`glossary_propose_entity_edit`** | 101 | **101** | **100%** | the `placeholder_id_1` specimen — **the model writing a plan with no syntax for one** |

**The chain, recovered from real session sequences** — this is the product's actual dogfood pipeline,
not a designed example:

```
glossary_extract_entities_from_doc ─65→ glossary_propose_entities ─92→ kg_project_create
   ─138→ kg_project_entities_to_nodes ─118→ plan_propose_spec ─101→ book_chapter_create
   ─111→ book_chapter_save_draft
```

---

## 2 · The admission order, and what each brick tests

| brick | declaration(s) | tests | contract clauses under test |
|---|---|---|---|
| **2** | **`book_list`** | **the membrane, not the declaration** | C-0, C-3 — it already ships references-only, paged, self-terminating, and `kind` defaults |
| **3** | **`glossary_get_entity`** | **the 57% identifier class** | **C-4** — it must accept a *name*, and return `ambiguous` (C-14) with candidates rather than a wrong object |
| **4** | **`book_chapter_create` → `book_chapter_save_draft`** | **the 61.8% carry-forward class** | **C-6** both sides; the executor must satisfy the binding **without asking the model to retype the id** |
| **5** | **`kg_project_create`** | **re-run safety** | **C-13** — measured ×57 in one turn; `duplicates`, so it may never be auto-re-run by `binding-invalid` |
| **6** | **`glossary_propose_entities`** | a write approved **as a plan** | C-6 emits + §0.8's plan-hash approval — its `entity_id` is the value the 61.8% loses |
| **7** | **`glossary_list_chapter_links`** | **the honest-failure case** | C-14 + C-12 — 100% failure that no gate caught. If the new contract does not make this loud, it is not working |

**Brick 4 is the centre of the whole run, and the data chose it:** the producer fails **1%** and the
consumer fails **57%** on the *same* pair, 111 times. The defect cannot be in either declaration — it
is in the space between them, which is exactly what the plan's bindings occupy.

---

## 3 · Contract design — the two that carry the argument

### `glossary_get_entity` — C-4 (`accepts` provenance)

**Today:** requires `entity_id` (a UUID), its description says *"use after `glossary_search`"*, and it
fails **183 of 197** times. The guidance is prose; nothing enforces or assists it.

| | today | under the contract |
|---|---|---|
| `accepts` | `entity_id: uuid` (required, opaque) | `entity_id` **or** `name` — and the declaration **names its producer** (`glossary_search`) as the provenance of `entity_id` |
| ambiguity | resolved silently — `matches[0]` at `confidence: 1.0` with siblings hidden in `other_matches` | **`outcome: ambiguous`** (C-14) carrying the candidates. **This is also the missing trigger for `awaiting_input`** — the model asks, which §0.5 defines as success |
| wrong id | *"not found"*, fused with *"not permitted"* by design | C-12 locus + C-17's withheld-vs-absent distinction |

### `book_chapter_create` → `book_chapter_save_draft` — C-6 (`emits` → `accepts`)

**Today:** create returns a chapter id; save_draft requires one; the model must carry it across turns
through a conversation measured to be a **lossy carrier** (`LIMIT 50`, pin-blind, arguments dropped by
the transcript renderer).

| | today | under the contract |
|---|---|---|
| producer | returns a chapter id in prose-shaped JSON | **declares `emits: {chapter_id}`** |
| consumer | requires `chapter_id` from the caller | **declares `accepts.chapter_id` is satisfiable from a prior step's `emits`** |
| the carry | the model retypes a UUID it has already seen | **the executor binds it directly**; the projection **never compresses an identifier** (§0.11) |
| checkability | none | **satisfiability is checked at plan generation** — step 2 asking for what no earlier step emits is a generation error |

**`book_chapter_save_draft` already proves half the thesis.** Its own description says *"you do NOT
pass a version… pick the chapter by NUMBER or TITLE"* — someone already applied C-4 to one argument by
hand, in one tool, and it works. **The contract is that instinct made mandatory and checkable.**

---

## 4 · Skills and workflows — derived, not authored separately

Under §0.2 these are **kinds of declaration over the same substrate**, so neither is a new mechanism:

- **the first skill** is the chain's first half — the glossary-build set — and it owns exactly one
  group (R3). Its member list is a **foreign key into the manifest** (C-11), so it cannot name a
  declaration that is not admitted. Today, by contrast, 12 rails point at **30 dead tools** behind a
  gate that fails open.
- **the first workflow is the 7-step chain above**, and it is a **plan template**, not a rail (§0.4).
  It is the natural CP-3 subject: it already exists in production behaviour, it is ordered, every step
  consumes the previous step's output, and **C-6 satisfiability across all seven steps is checkable at
  generation before anything runs.**

---

## 5 · What this document is not

**It is not a design of the declarations themselves.** Six of the seven have no written contract yet;
this fixes the *order* and the *reason*, so that the first one written is written against a target we
can defend. Each brick's declaration is designed when its brick opens — and, per `RUNSTATE` CP-4,
verified by an independent agent that never saw the reasoning above.
