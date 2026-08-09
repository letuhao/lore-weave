# CP-5 · the tool contract — the solid ground

**Scale:** β · **Status:** SPEC, nothing built · 2026-08-09

**Why this checkpoint exists.** CP-1 built a contract for a **registry row**. There is no contract
for a **tool**. C-3…C-17 were deferred with a stated reason — *"their subjects do not exist until a
declaration is written"* — CP-4 then wrote declarations, and nobody went back. Measured:
`inputSchema` validated at admission → **0**; declared result shape → **0**.

**PO directive, 2026-08-09:** *build the new architecture AGAINST the defects we already face, not
clone them into it.* **No v2 tool is built until CP-5 closes.**

---

## 1 · The count

**17 contract members. 5 exist. 12 are missing.** Every share below is measured from 4,175 failed
`tool_calls` in production; the denominator is the query's own count.

### Present (5)

| # | member | since |
|---|---|---|
| 1 | identity + ownership (C-0) | CP-1 |
| 2 | lane / tier (C-1) | CP-1 |
| 3 | cost | CP-4 |
| 4 | supersession | CP-4 |
| 5 | lifecycle state machine + wire gate | **2026-08-09** |

### Missing (12), ordered by measured cost

| # | member | share | the failure it ends |
|---|---|---|---|
| 6 | **repeat semantics** | **48.8%** | `already called X with these exact arguments` — the runtime cannot tell a free re-read from a duplicate create, so it errors on both |
| 7 | **typed inputs** | **16.8%** | `entity_id must be a UUID` — the schema says `string` |
| 8 | **preconditions** (scope · capability · prerequisite) | **10.0%** | `book not accessible`, `this project has no embedding model`, `this book has no chapters yet — create one first` |
| 9 | **argument supplier** (model \| context \| plan) | **9.6%** | `missing required argument(s)` — nothing says who was meant to provide it |
| 10 | **partial-outcome contract** | 2.1% | `no entities were created — 3 of 3 item(s) failed` — batch tools have no per-item result shape |
| 11 | **output contract** | 1.0% | `mcp tool returned unparseable content` — **and it is why `emits` paths fail at execution** |
| 12 | **consent declaration** | 0.9% | `blocked: you chose 'Never allow'` — the tool is still advertised, so it is still called |
| 13 | **closed vocabularies** | 0.6% | `unknown kind:`, `unknown subagent 'universal'` — the valid set exists only inside the error |
| 14 | **concurrency / read-version** | 0.4% | `the row changed since you read it (409)` |
| 15 | **empty-change precondition** | 0.4% | `no fields to update` |
| 16 | **conditional parameters** | in tail | `arc_id is required when scope='arc'` — a flat required-list cannot express it |
| 17 | **result completeness** | **0% by construction** | 🔴 see below |

**Directly attributable to a missing member: 90.6%.** A further **4.7%** (`invalid arguments for
'glossary_propose_entity_edit'` — a name called **101 times at 0% success that does not exist in the
catalogue**) belongs to the registry, not the tool: *the registry must be the only source of
callable names.*

### 1a · Member 17 scores 0%, and that is the point

`book_list` returns `{total: 197, returned: 20, has_more: true, is_complete: false}`. A model asked
for *"the first book"* reads a **truncated page** and is never told. It cannot fail loudly, so it
appears in **no** error bucket.

**This is the quiet-failure class the whole V-METRIC exercise was built to detect, sitting inside a
tool result.** Members 6–16 are visible because they are loud. 17 is invisible, and a contract that
only fixes what is loud converts nothing — it just stops counting.

---

## 2 · Enforcement — the ladder, and why Python is not the obstacle

The concern was that C# restricts and Python does not. **This repository already built the
restriction pattern twice and aimed it at the wrong subject:** `Admitted` cannot be forged (private
module token + `object.__setattr__`), and `Surface` has exactly one construction site **counted by a
gate** rather than requested by a docstring.

| level | mechanism | fails at |
|---|---|---|
| 1 | `ABC` + abstract members | instantiation |
| 2 | **`__init_subclass__` validates the class** | **import** — stricter than C#, which needs a source generator or startup reflection |
| 3 | frozen dataclass + `__slots__` | attribute smuggling |
| 4 | private-token `Registered` | forgery |
| 5 | CI gate counting registration sites | a second door |
| 6 | **admission refuses an incomplete contract** | **release** |

🔴 **Level 6 is the lever that needs no other team.** Tools live in Go and Python services across the
estate and chat-service cannot rewrite them. It **can** refuse to promote any declaration whose
contract is incomplete — so an unmigrated tool registers `draft` and never serves. The pattern
becomes mandatory **by consequence**, not by memo.

---

## 3 · Rows

| row | claim | exit |
|---|---|---|
| **5.1** | `ToolContract` — the 17 members as **data**, not prose. Missing member = **import-time** failure | a class omitting any required member cannot be defined |
| **5.2** | **Level 6** — admission refuses to promote an incomplete contract; incomplete ⇒ stays `draft` | injection: strip one member, promotion refuses, tool does not serve |
| **5.3** | **repeat semantics** (48.8%) — declared per tool; a re-read returns the **cached result**, a duplicate create is a real error | the generic breaker no longer fires on a declared-idempotent read |
| **5.4** | **typed inputs + conditional params** (16.8%) — semantic types; `required-when` expressible | `entity_id: str` is refused at registration; `EntityId` is not |
| **5.5** | **argument supplier** (9.6%) — every input says model \| context \| plan | a `plan`-supplied input the model sends is **discarded** (CP-3.10 already does this; the contract makes it declarable) |
| **5.6** | **output contract + completeness** (1.0% + the quiet class) — declared result shape, and truncation is a **declared field the runtime must surface** | 🔴 **an `emits` path is checked at PLAN-BUILD time** against the tool's declared output — §6.2 restored for outputs |
| **5.7** | **preconditions** (10.0%) — scope · capability · prerequisite, checked before dispatch **and** used to gate advertisement (§4.3) | a tool whose precondition is unmet is not advertised, and the withholding is recorded |
| **5.8** | the remaining members (partial outcome · consent · vocabularies · concurrency · empty-change) | each refuses at registration when absent |
| **5.9** | **registry is the only name source** (4.7%) — an unknown name is a structured refusal naming the nearest real tool | `glossary_propose_entity_edit` cannot be dispatched 101 times |

---

## 4 · QC bar — unchanged, and it applies to CP-5 itself

**CODE** tests + a falsifier that reds on the original defect · **LIVE** real service, real boundary
· **DATA** measured DB/API state with an explicit falsifier.

🔴 **And one gate this checkpoint owes specifically, because it is the defect that produced CP-5:**
every member must have a **subject** and a test that would go red if the member were dropped. A
member declared and never enforced is C-3…C-17 again, and *"the subject does not exist yet"* is not
an acceptable state to leave a clause in.

---

## 5 · Exit

CP-5 closes when a tool that does not implement the pattern **cannot be released**, proven by
injection, and the first essential tool is admitted **through** the contract with QC evidence.

**Only then does tool v2 resume.** A runtime registry built before this just moves unvalidated rows
from a file into a table — which is cloning the defect into the new architecture, the one thing this
checkpoint exists to prevent.
