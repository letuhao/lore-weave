# CP-5 · the tool contract — the solid ground

**Scale:** β · **Status:** SPEC v2, nothing built · 2026-08-09
**Supersedes** SPEC v1 of the same day, which did not survive its own evaluation. The six findings
that killed it are kept in `EVALUATION-v1.md` — **four were the spec committing the defect it was
written to prevent**, and deleting them would destroy the record of why v2 looks like this.

**Why this checkpoint exists.** CP-1 built a contract for a **registry row**. There is no contract
for a **tool**. C-3…C-17 were deferred — *"their subjects do not exist until a declaration is
written"* — CP-4 then wrote declarations, and nobody went back. Measured: `inputSchema` validated at
admission → **0**; declared result shape → **0**.

**PO directive:** *build the new architecture AGAINST the defects we already face, not clone them
into it.* **No v2 tool is built until CP-5 closes.**

---

## 0.5 · EVALUATION of v2, same day — three findings, and one rewrites the top row

v2 survives better than v1. It does not survive intact, and the surviving defect is the **most
expensive kind: a correctly-measured symptom with the wrong cure attached.**

### V1 · Typed inputs cannot be derived — row 5.3 needs four teams before one tool can ship

Across the 315-tool catalogue: **1,313 properties, and ZERO carry a `format`.** Of **477 `*_id`
properties**, every one is a bare `string` — and **120 have no `type` at all**.

So `typed inputs` is not derivable from anything we hold. It requires composition (107 tools),
glossary (54), book (35) and kg (31) each to annotate their schemas *before a single tool can be
promoted*. v2 named rung 2 as *"needs no other team's cooperation"* and then made its top row
entirely dependent on four of them.

### V2 · 🔴 The top member is MISDIAGNOSED — and the frozen baseline already named it correctly

What the model actually sends when `entity_id must be a UUID` fires:

```
glossary_list_chapter_links   {"book_id": "019f482c-…", "entity_id": "Ember Codex"}   ×197
glossary_get_entity           {"book_id": "019f6531-…", "entity_id": "Lâm Uyên"}      ×106
glossary_list_entity_revisions{"book_id": "019eef55-…", "entity_id": "Count Dracula"} × 24
book_list_chapters            {"book_id": "all"}                                      ×  9
```

**390 of 392 (99.5%), across 22 sessions: a human NAME sent where an opaque id is required.**

**A semantic type does not fix this.** Declaring `entity_id: EntityId` rejects `"Ember Codex"`
*earlier* — the same failure, moved forward one layer. The model still holds a name and still cannot
proceed. Neither does `argument supplier`: there is no context id for *"the entity the user just
named."*

The real member is **identifier resolution** — *how does a name become an id?* — and it is not a new
discovery. **The frozen baseline named it in class 3: `IDENTIFIER RESOLUTION — 676 of 1,676 real
errors, 40.3%`.** My audit re-derived the symptom from raw error text, filed it as *typed inputs*,
and attached a cure that would not have worked. **The board already had the right answer and the
audit walked past it.**

### V3 · The correct member is buildable NOW, and composes with what already exists

This is the constructive half. A **resolution contract** — *`entity_id` is an `EntityRef`, resolved
by `glossary_search(name) → entity_id`* — is declarable **without any other team**, because it is a
statement about how two existing tools relate, not a change to either one's schema.

And the binding half is **already built and already measured**: CP-3.10's executor supplies a
resolved identifier and discards what the model typed (10/10 vs 1/10, 22 wasted calls → 0). A
resolution contract feeds exactly that mechanism. **The top member becomes a reuse, not a new
build** — and unlike typed inputs it ships without a cross-team migration.

### Verdict

**Reorder.** `identifier resolution` is row 5.3 and is the checkpoint's first build. `typed inputs`
demotes to a conditional member covering the residue — the 120 properties with **no type at all**,
which is a real defect but a smaller and different one. Every remaining row keeps its v2 shape.

**The lesson this evaluation is an instance of:** *measuring a failure correctly and naming its cure
from the error text are two different acts, and the second one is where the audit failed.*

---

## 1 · The evidence

4,175 failed `tool_calls` across **358 sessions**, 480 turns. **The denominator is SESSIONS, not
calls** — v1 ranked by call events and the top 3 sessions alone held 28.3% of them (median session:
3). Ranking by events ranks pathological loops.

Shares exceed 100% because one session can hit several members. Every figure is a query result.

| member | sessions | % of 358 | calls | required? |
|---|---|---|---|---|
| **typed inputs** | **101** | **28.2%** | 774 | **core** |
| **argument supplier** | **85** | **23.7%** | 401 | **core** |
| **preconditions** | **67** | **18.7%** | 441 | conditional — if it needs scope/capability/prerequisite |
| **repeat semantics** | 46 | 12.8% | **2039** | **core** (see §3) |
| **partial outcome** | 37 | 10.3% | 88 | conditional — batch tools |
| *registry: name source* | 36 | 10.1% | 110 | *registry property, not a member* |
| **error contract (C-7)** | **29** | **8.1%** | 41 | **core** — these failures carried **no message at all** |
| **consent** | 20 | 5.6% | 36 | conditional — gated tools |
| **closed vocabulary** | 10 | 2.8% | 25 | conditional — enum params |
| **empty-change / uniqueness** | 10 | 2.8% | 109 | conditional — writes |
| **conditional params** | 6 | 1.7% | 15 | conditional — cross-field constraints |
| **output contract** | 6 | 1.7% | 40 | **core** (see §2) |
| **concurrency** | 1 | 0.3% | 17 | conditional — versioned writes |
| *transport* | 8 | 2.2% | 9 | *not a contract member — C-7 `retryable_transient`* |
| *unclassified residual* | **18** | **5.0%** | 30 | **stated, not hidden** |

**Two members are invisible in this table and belong anyway:**

* **result completeness — 0% by construction.** `book_list` returns `{total: 197, returned: 20,
  is_complete: false}`. A model asked for *"the first book"* reads a truncated page and is never
  told. It cannot fail loudly, so it appears in **no** bucket. This is the quiet-failure class
  V-METRIC exists to detect, sitting inside a tool result — **a contract that fixes only the loud
  members converts nothing, it just stops counting.**
* **effect + undo.** `undo_hint` exists in `_meta` today but is not contractual, so a write's
  reversibility is a convention.

---

## 2 · Why the output contract outranks its 1.7%

CP-3 declares an `emits` path as a **literal string** (`books[0].book_id`), and `check_emit_path`
can only prove it is *syntactically* a path. It cannot prove the path exists in `book_list`'s
result, **because `book_list` has no declared result shape**. So `EmitPathError` fires at
**execution**.

§6.2's principle is *"a generation error, not a runtime one."* For outputs it is currently inverted,
and the runtime failure was built and written up as a feature. **An output contract turns that back
into a plan-build rejection** — which is the entire reason §6.2 exists. Its 1.7% understates it: it
is load-bearing for CP-3, not for its own error class.

---

## 3 · Repeat semantics — reframed, because v1's version was metric laundering

`tool_list` produced **1,180 repeat errors across 3 sessions — 393 per session**. v1 said *declare
it idempotent and serve the cache*. That turns 393 errors into **393 silent successes**: the loop
runs exactly as long, burns the same passes, and emits no signal.

**That is converting loud failures into quiet ones — the precise question V-METRIC exists to ask.**

> **The contract may remove a repeat's COST. It may never remove its SIGNAL.**
> A declared-idempotent read MAY be served from cache. It **must still be counted, and the breaker
> must still escalate.** `repeat_served_from_cache` is recorded as its own outcome so the two
> populations never merge — the same separation `plan_supplied.overrode` had to make on 2026-08-09.

---

## 4 · Where the contract lives — and it is not a Python base class

**v1's fatal error.** The enforcement ladder was `ABC` + `__init_subclass__` + frozen dataclass +
private token — all **Python-class** mechanisms. chat-service implements **9** tools in Python; the
catalogue holds **315** federated from Go and Python services (composition 107, glossary 54, book
35, kg 31). **9 of 324 = 2.8%.** A mechanism whose subject is 2.8% of the population, specified as
*the* pattern. The clause-with-no-subject failure, inside the document correcting it.

**The contract is a language-neutral declaration in the MCP tool's `_meta`.** That mechanism already
exists and is already proven — `_meta` carries `tier`, `ambient_book` and `superseded_by` today, and
CP-4's producer already derives from it for 315/315 tools.

| rung | mechanism | scope | fails at |
|---|---|---|---|
| 1 | `_meta` schema, versioned | **all 324** | — |
| 2 | **admission refuses an incomplete contract** | **all 324** | **release** |
| 3 | `ABC` + `__init_subclass__` + frozen + token | the 9 Python tools | import |
| 4 | CI gate counting registration sites | the 9 | build |

🔴 **Rung 2 is the whole enforcement, and it needs no other team's cooperation.** chat-service
cannot rewrite Go services. It can refuse to promote a declaration whose contract is incomplete — so
an unmigrated tool registers `draft`, never serves, and the pattern becomes mandatory **by
consequence**. Rung 3 is a reference implementation, not the mechanism.

---

## 5 · Rows

| row | claim | exit |
|---|---|---|
| **5.1** | the `_meta` contract schema — members as **versioned data**, core vs conditional, with the conditionality itself declared | a tool omitting a **core** member fails validation; a conditional member is required only when its trigger is present |
| **5.2** | **rung 2** — admission refuses to promote an incomplete contract | injection: strip one core member ⇒ promotion refuses ⇒ the tool does not serve |
| **5.3** | **typed inputs** (28.2%) — semantic types, not `string` | `entity_id: str` is refused; `EntityId` is not |
| **5.4** | **argument supplier** (23.7%) — every input declares model \| context \| plan | a `plan`-supplied input the model sends is **discarded** — CP-3.10 already does this; the contract makes it *declarable* rather than plan-only |
| **5.5** | **error contract** (8.1%) — every failure carries a C-7 class **and a message** | a failure with no message cannot be produced |
| **5.6** | **output contract + completeness** | 🔴 an `emits` path is checked at **plan-build** time; a truncated result is a **declared field the runtime must surface** |
| **5.7** | **repeat semantics** per §3 — cost removed, signal retained | a cached repeat is still counted and still escalates |
| **5.8** | **preconditions** (18.7%) — checked pre-dispatch **and** used to gate advertisement (§4.3), withholding recorded | a tool whose precondition is unmet is not advertised |
| **5.9** | the conditional members, each required only on its trigger | absent-when-triggered is refused |
| **5.10** | **registry is the only name source** (10.1%) | `glossary_propose_entity_edit` — 101 calls, 0% success, not in the catalogue — cannot be dispatched |

---

## 6 · Measurement — because declaring is not fixing

v1 assumed a declared member fixes its failure. **2026-08-09 refuted that in this repo**: the
executor was built, measured **null**, and the null was a *placement* bug — the supply ran after the
check that rejected the shape it repaired.

Every row states, before it is built:

1. **the before figure, in sessions affected** (the table in §1);
2. **the after measurement, same denominator, same query**;
3. **a control** — the arm without the member, at the condition where the failure occurs;
4. **a quiet-failure check** — what would this member convert from loud to silent, and is that
   population counted? §3 is the worked example.

**No member is claimed closed on a call-count improvement.**

---

## 7 · QC and exit

**CODE** tests + a falsifier red on the original defect · **LIVE** real service, real boundary ·
**DATA** measured state with an explicit falsifier.

🔴 **The gate this checkpoint owes specifically, because it is the defect that produced CP-5:**
every member must have a **subject** and a test that goes red if the member is dropped. *"The
subject does not exist yet"* is how C-3…C-17 became permanent, and it is not an acceptable state to
leave a clause in.

**Exit:** a tool that does not implement the pattern **cannot be released**, proven by injection;
the residual (§1, 5.0%) is either classified or declared out of scope with a reason; and the first
essential tool is admitted **through** the contract with QC evidence.

**Only then does tool v2 resume.**
