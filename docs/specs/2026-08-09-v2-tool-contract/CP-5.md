# CP-5 · the tool contract — the solid ground

**Scale:** β · **Status:** SPEC, nothing built · 2026-08-09

**Why this checkpoint exists.** CP-1 built a contract for a **registry row**. There is no contract
for a **tool**. C-3…C-17 were deferred with a stated reason — *"their subjects do not exist until a
declaration is written"* — CP-4 then wrote declarations, and nobody went back. Measured:
`inputSchema` validated at admission → **0**; declared result shape → **0**.

**PO directive, 2026-08-09:** *build the new architecture AGAINST the defects we already face, not
clone them into it.* **No v2 tool is built until CP-5 closes.**

---

## 0.5 · EVALUATION, 2026-08-09 — six findings against this spec, before anything was built

The PO asked for CP-5 to be evaluated rather than started. It does not survive intact. **Four of the
six findings are the spec committing the defects it was written to prevent.**

### E1 · The prioritisation was wrong — ranked by events, not by journeys

4,175 failed calls span **358 sessions**, and the **top 3 sessions alone hold 1,180 of them
(28.3%)**. The median session has **3**. Ranking members by call count therefore ranks a handful of
pathological loops. By **sessions affected** the order inverts:

| member | calls | sessions | % of 358 |
|---|---|---|---|
| **typed inputs** | 703 | **91** | **25.4%** |
| **argument supplier** | 401 | **85** | **23.7%** |
| preconditions | 417 | 58 | 16.2% |
| **repeat semantics** | **2039** | 46 | **12.8%** ← *was ranked #1 at 48.8%* |
| registry name source | 198 | 42 | 11.7% |
| partial outcome | 88 | 37 | 10.3% |
| consent | 36 | 20 | 5.6% |
| closed vocabulary | 25 | 10 | 2.8% |
| output contract | 40 | 6 | 1.7% |
| **concurrency** | 17 | **1** | **0.3%** |
| **empty-change** | 16 | **1** | **0.3%** |

**`typed inputs` + `argument supplier` are the two that break the most user journeys**, and together
they are one problem: *the model could not supply the right value.* That is the problem CP-3's
executor already solves for planned steps.

### E2 · Member 6 as specified is metric laundering — the defect this board exists to catch

`tool_list` produced **1,180 repeat errors across 3 sessions — 393 per session.** Declare it
idempotent and serve the cache, and those become **393 silent successes**. Errors go to zero; the
loop runs exactly as long, burns exactly as many passes, and now emits no signal at all.

**That is converting loud failures into quiet ones**, which is the precise question V-METRIC was
built to ask. Corrected requirement: a repeat may be served from cache to remove its *cost*, but it
**must still be counted and must still escalate** — the breaker stays; only the wasted dispatch goes.

### E3 · No required-vs-optional distinction — and two members have a population of one

`concurrency` and `empty-change` each affect **1 session in 358**. Requiring all 17 members of every
tool makes migration impossible and is over-engineering. Members must be **conditional on lane and
shape** (concurrency for writes; partial-outcome for batch tools) — which is ironic, since member 16
is *conditional parameters*.

### E4 · 🔴 The enforcement ladder governs 2.8% of the tools

Rungs 1–5 (`ABC`, `__init_subclass__`, frozen dataclass, private token, site-counting gate) are
**Python-class mechanisms**. chat-service implements **9** tools in Python. The catalogue holds
**315** federated from Go and Python services — composition 107, glossary 54, book 35, kg 31.

**9 of 324 = 2.8%.** I specified a mechanism whose subject is almost the whole point, and it is not
there. **This is the same clause-with-no-subject failure that produced CP-5**, committed inside the
document correcting it.

Corrected: the contract is a **language-neutral declaration carried in the MCP tool's `_meta`** —
a mechanism that already exists and is already proven, since `_meta` carries `tier`, `ambient_book`
and `superseded_by` today. **Rung 6 is the enforcement for the 97.2%.** Rungs 1–5 apply where
chat-service owns the implementation, as the reference implementation and nothing more.

### E5 · No measurement plan

The spec assumes that declaring a member fixes the failure. Today's own lesson refutes that: the
executor was built, measured null, and the null was a **placement bug** — the supply ran after the
check that rejected the shape it repaired. Every member needs a stated before/after with a control,
and the metric must be **sessions affected**, not events.

### E6 · The residual is larger by journey than by call

`other` is 5.1% of calls but **21.2% of sessions** (76 of 358) — third-largest by the honest
denominator. It is not classified, and CP-5 cannot claim coverage while a fifth of affected journeys
sit in it.

### Verdict

**CP-5's direction holds; its priority, scope and enforcement do not.** Revised order:
**typed inputs → argument supplier → preconditions**, with repeat semantics reframed per E2 and
demoted, `concurrency`/`empty-change` dropped to optional, the ladder replaced by `_meta` +
rung 6, and E6 closed before any coverage claim.

**Do not start 5.1 as written.**

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
