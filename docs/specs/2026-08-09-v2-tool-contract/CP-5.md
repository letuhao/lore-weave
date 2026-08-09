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
