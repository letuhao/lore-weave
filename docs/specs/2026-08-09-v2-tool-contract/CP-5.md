# CP-5 · the tool contract — the solid ground

**Scale:** β · **Status:** 🔒 **SEALED v3** — three evaluation rounds applied · 2026-08-09
**Next action:** ~~`5.3-pilot`~~ ✅ **RAN 2026-08-09 — §3b. Verdict: BUILD 5.3.** Next is **5.1 / 5.2**.
*The pilot is the only edit made to a sealed spec: it is the measurement this spec ordered before
code, and §3b records what it returned. No design was re-opened.*
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

## 0.5 · EVALUATION of v2 — three findings, and one rewrote the top row (v3 applies them)

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

## 0.6 · EVALUATION of v3 — three findings; the design holds, two claims do not

v3's *design* survives: two branches with no guess arm, a read-lane constraint, recorded
substitution. **Two of its CLAIMS do not, and one is the same sampling error that produced this
morning's V-METRIC null.**

### W1 · 🔴 "Needs no other team" is FALSE as written

v3 says the ref/resolver declaration *"is a statement about how two existing tools relate, so it
needs no other team."* But it was specified to live in the tool's **`_meta`** — and `_meta` is
produced by the **owning service**. Declaring `entity_id` an `EntityRef` in glossary's `_meta`
requires glossary-service to change. The claim contradicts the placement.

**Correction, and it satisfies the PO constraint better than the original:** the ref/resolver map is
a **runtime-registry fact** — *data in the registry, not a literal in source* — authored once per ref
type and later pushed upstream into `_meta`. So it is *"no other team to START"*, not *"no other team
ever"*. Written as a chat-service constant it would be the hardcoding the PO rejected; written as a
registry row it is exactly the runtime control that was asked for.

### W2 · 🔴 The success rate is measured on a population the member would not serve

v3 cites **11 of 18 exactly-one-exact** as evidence resolution works. Those 18 searches come from
**9 sessions**. The failure it would serve spans **24 sessions**. **The overlap is ONE session.**

The two populations are almost disjoint. The model ran a search precisely in the sessions where it
did *not* send a bare name — so the exact-match rate is measured on the cases that **already went
right**. It cannot be assumed to transfer.

**This is the V-METRIC null again**: a premise measured on a convenient population instead of the
one the mechanism is for, found on the same day, by the same question. **Row 5.3 requires a pilot
before build** — take the actual failing names (`"Ember Codex"`, `"Lâm Uyên"`, `"Count Dracula"`)
against their own books and measure what fraction resolve exactly. Until that runs, the 61%/39%
split is **not evidence**, and the spec may not claim resolution "fixes the 390".

### W3 · The member does not cover every id failure, and should not claim to

`book_id: "all"` (9 calls) is a **quantifier, not a name** — no resolver applies, and the model is
asking for something the parameter cannot express. That is a separate defect (an unexpressible
intent), and folding it into resolution would inflate the member's scope.

### Verdict

**Design: keep.** **Claims: two withdrawn pending a pilot.** Row 5.3 gains a pilot as its first
task, on the pattern that worked this morning: *measure the premise on the real population before
building the mechanism.*

**And the recurring lesson, now three-for-three today:** every one of these evaluations found the
error in **where a thing sat or what population it was measured on** — never in the mechanism
itself. The mechanism is the easy part.

---

## 1 · The evidence

4,175 failed `tool_calls` across **358 sessions**, 480 turns. **The denominator is SESSIONS, not
calls** — v1 ranked by call events and the top 3 sessions alone held 28.3% of them (median session:
3). Ranking by events ranks pathological loops.

Shares exceed 100% because one session can hit several members. Every figure is a query result.

| member | sessions | % of 358 | calls | required? |
|---|---|---|---|---|
| **identifier resolution** | **22+** | **≥6.1%** | **390** | **core** — *a NAME sent where an id is required; 99.5% of every UUID failure* |
| ~~typed inputs~~ → **untyped properties** | 101 | 28.2% | 774 | conditional — the residue after resolution: **120 properties carry no `type` at all** |
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

## 3a · Identifier resolution — the design, and why it never guesses

**The failure.** 390 of 392 UUID failures (99.5%, 22 sessions) are a human **name** in an id field:
`entity_id: "Ember Codex"`, `"Lâm Uyên"`, `"Count Dracula"`. A semantic type rejects these one layer
earlier and fixes nothing — the model holds a name and still cannot proceed.

**The resolver already exists and is better than assumed.** `glossary_search` returns
`{entity_id, cached_name, tier, rank_score}` — and `tier: "exact"` is a **match-quality signal**.
Measured: the model sent `"Lâm Uyên"`, the entity is `"Lâm Uyển"` (different diacritics), and search
still returned `tier: exact`. It normalises.

**The contract.** A ref field declares its resolver — *`entity_id` is an `EntityRef`, resolved by
`glossary_search(query) → entities[].entity_id`, matched on `tier == "exact"`*. This is a statement
about **how two existing tools relate**, so it needs **no other team to START** — unlike typed
inputs, which needs four before anything ships.

🔴 **It is a RUNTIME-REGISTRY ROW, not a chat-service constant, and not `_meta` on day one.**
v3 first placed it in the tool's `_meta` while claiming it needed no other team — but `_meta` is
produced by the owning service, so the placement contradicted the claim (W1). Written as a
constant in chat-service it would be the hardcoding the PO rejected. Written as a registry row
it is the runtime control that was asked for, authored once per ref type and pushed upstream
into `_meta` when the owning service catches up.

**The runtime rule — two branches, no third:**

| condition | action |
|---|---|
| exactly **one** `tier: exact` match | substitute, dispatch, and **record the substitution** |
| zero, or **more than one** | **refuse**, and return the candidates as a structured error |

🔴 **There is deliberately no "pick the best" arm.** v3 argued this from a bound: 18 real searches
gave **0 ambiguous**, and `0/18` bounds ambiguity only at **≤15.4%** (95%, rule of three) — *not*
zero. **The pilot replaced that bound with a measurement, and ambiguity is real: 16.7% of contested
pairs, 37.5% of contested calls** (§3b). A `rank_score` tiebreak is exactly the guess §0.14 forbids
from deciding a correctness question — and it is now known to be a guess the runtime would have had
to make on more than a third of the calls in the stratum that matters, over **four candidates that
tie at 0.9**.

**Two constraints that are safety properties, not preferences:**

1. 🔴 **A resolver MUST be `lane=read`.** Auto-resolution dispatches a tool the user never asked
   for. `glossary_search` is `tier=R`, so it is auto-approved and harmless — but nothing structural
   stops a `W` tool being declared as a resolver, and the runtime would then perform an unrequested
   **write**. The contract must refuse a non-read resolver at registration.
2. **The substitution is recorded like `plan_supplied`.** A resolved argument and a model-typed one
   must not become the same row — the separation `plan_supplied.overrode` had to make on
   2026-08-09, for the same reason.

**Why the refusal branch is still an improvement.** Today a name yields `entity_id must be a UUID`
— loud but **not actionable**. Under this contract the same input yields *"'Ember Codex' matched no
entity exactly; did you mean … "* with candidates. Both are loud; only one can be acted on.

**Cost.** ~44 extra read dispatches replace **390** failed calls. The trade is not close.

---

## 3b · 5.3-pilot — RAN 2026-08-09, and the aggregate would have been the W2 error again

**Verdict: BUILD 5.3.** But the number that justifies it is not the number the aggregate reports.

**The population, derived from live data and not from this document.** 485 failed `tool_calls` carry a
UUID-type error across 34 sessions. Classifying the offending argument's VALUE separates what a
resolver can serve from what it cannot: **a NAME — 338 calls / 11 sessions / 13 distinct (book, name)
pairs**; a placeholder the model invented (`placeholder_id`, `current_book_id`) — 123 / 13; a
quantifier (`"all"`, W3) — 33 / 3; a MANGLED uuid (a dropped nibble, a colon for a dash) — 8 / 5;
a system symbol — 6 / 3; a garbled decode — 1. **Only the first is this member's subject**, and the
pilot's overlap with the failing population is 100% *by construction* — it IS that population.

**Re-runnable:** `python scripts/cp5-resolution-pilot.py` — read-only, every denominator a query
result. A spec-changing number that exists only in a document cannot be re-derived or refuted.

**The instrument.** `POST /internal/books/{id}/select-for-context` invokes `selectGlossaryForContext`
— the same core `glossary_search` calls (`mcp_server.go:454`), same bounds, `max_entities` 20 = the
tool's own default. It differs only in the grant check, which is not what this measures: **the books
were deleted from `loreweave_book`, so the grant-checked MCP path cannot run at all.**

| stratum | pairs | calls | exactly one | ambiguous | zero exact |
|---|---|---|---|---|---|
| single-entity book | 6 | 109 | **6 (100%)** | 0 | 0 |
| **contested book (7–27 entities)** | **6** | **32** | **5 (83.3%) · 20 calls (62.5%)** | **1 (16.7%) · 12 calls (37.5%)** | **0** |
| aggregate (misleading) | 12 | 141 | 11 (91.7%) · 129 (91.5%) | 1 | 0 |

🔴 **The aggregate is 91.5% and it is not the answer.** 109 of 141 measurable calls (77%) come from
books holding **exactly one entity**, where resolving a name to an id cannot fail. Reporting 91.5%
would have measured the cases that were never hard — W2's error, one level down, inside the very
pilot written to prevent it. **The informative rate is the contested stratum: 83.3% / 62.5%.**

✅ **`ZERO_EXACT` = 0 in every stratum.** The resolver never came up empty on a name that failed.
The premise — *a name the model sent can be turned into an id* — holds.

🔴 **Ambiguity is measured, not bounded.** Query `Dracula` in one book returns **4 `tier: exact`
matches — THREE separate live entities literally named `Dracula`, plus `Count Dracula` carrying
`Dracula` as an alias — all tied at `rank_score` 0.9**, separable only by `updated_at`. §3a's
refusal branch is no longer an argument from a rule-of-three; it is the branch that carries 37.5% of
the contested calls. (`tier: exact` means `lower(cached_name) = lower(q)` OR an alias equals `q`,
so this is genuine exact-match ambiguity, not fuzzy drift.) **The duplicate entities themselves are
a separate defect — dedup, not resolution — and go to the debt register, not into 5.3.**

✖ **The bound this pilot cannot pass, stated rather than implied: 197 of 338 calls (58.3%) are
UNMEASURABLE.** They are one pair — `entity_id: "Ember Codex"`, called 197 times in a single
session — whose book was deleted and whose glossary rows are gone. The surviving trace argues it
would have been a **refusal, not a resolution**: that book's only successful glossary writes propose
`Corvin Ashe`, and **no recorded result in any session ever mentions `Ember Codex`**. So the
whole-population resolution rate is bounded **between 38.2% and 91.5%**, and no single figure for it
is published. Both endpoints are useful: even at 38.2% the remainder is not a failure but the
refusal branch, which §3a already argues is the improvement — *both are loud; only one is actionable*.

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

### 4a · Where the contract lives on DAY ONE — a registry row (PO decision, 2026-08-09)

**Found by attempting the first migration, which is the only way this was ever going to surface.**
`_meta` is the right END state — it is the owning service's own statement about its own tool. It
cannot be the START, for two reasons the attempt made concrete:

1. **It needs another team.** `_meta` for the overwhelming majority of the catalogue is emitted by
   Go and Python services chat-service does not own — **the same objection W1 already raised
   against §3a's original placement of the ref/resolver map**, and it gets the same answer:
   *a registry row, authored once, pushed upstream into `_meta` when the owning service catches
   up.* §4's placement inherits the correction §3a already took. The destination is unchanged.
2. 🔴 **And it perturbed CP-2's control group.** `derive.py` had refused to add even ONE `_meta`
   key, for a measured reason: *"`_tool_tokens` serialises the whole definition including `_meta`,
   so one extra key changes every tool's cost, which changes the rank, which changes what the
   budget cuts."* Measured here: a **minimal** contract block took `book_list` from **1284 → 1998
   (+56%), rank 191 → 262 of 315**, against a budget that ends in a hard `break` (U-1).

⭐ **The second reason turned out to be a defect in `cost`, not a cost of the contract.**
`strip_tool_meta` removes `_meta` **before the wire request**, so `_meta` costs the model nothing —
while `token_cost` counted it anyway. **9.6% of the entire ranking key was bytes the model never
receives, all 315 tools inflated** (median 132 characters), and correcting it moves a tool's cost
rank by a median of 6 and up to 38. `token_cost` now measures the wire form. The legacy
`_tool_tokens` is deliberately left alone — that arm is CP-2's control group, and correcting the
control to match the treatment is how a comparison stops measuring anything.

`Completeness.source` records **which side supplied the contract** (`_meta` | `registry` | `none`),
so an owner-published contract and one we authored in the interim never merge into one
indistinguishable row — the separation `plan_supplied.overrode` had to make on 2026-08-09.

🔴 **Rung 2 is the whole enforcement, and it needs no other team's cooperation.** chat-service
cannot rewrite Go services. It can refuse to promote a declaration whose contract is incomplete — so
an unmigrated tool registers `draft`, never serves, and the pattern becomes mandatory **by
consequence**. Rung 3 is a reference implementation, not the mechanism.

---

## 5 · Rows

| row | claim | exit |
|---|---|---|
| **5.1** | ✅ **BUILT** — `toolcontract.py`: members as **versioned data**, each with a `trigger`, a **subject** and its **evidence**. Core 4 apply to 315/315; conditionals select real subsets (`preconditions` 292 · `identifier_resolution` 283 · `effect_and_undo` 213 · `closed_vocabulary` 96 · `consent` 60 · `result_completeness` 36 · `partial_outcome` 3). 🔴 **`untyped_properties` (5.3b) NOT shipped — §7: its subject does not exist** (see below) | a tool omitting a **core** member fails validation; a conditional member is required only when its trigger is present |
| **5.2** | ✅ **BUILT + PROVEN BY INJECTION** — `promotion.promote()` is the only path to `admitted`. `book_list` (8 members) and `book_read` (7) are the **first tools admitted THROUGH the contract**. 🔴 It had to build the PROMOTER too: `check_transition` had **zero production callers**, and re-running the admit script **demoted both serving rows to `draft`** | injection: strip one core member ⇒ promotion refuses ⇒ the tool does not serve. **Done:** removing `error_contract` from `book_list` makes `agentruntime-membrane-gate` exit 1 naming the member; restoring it returns green |
| **5.3-pilot** | ✅ **RAN 2026-08-09 — see §3b. VERDICT: BUILD 5.3.** The informative rate is **83.3% by pair / 62.5% by call**, not the 91.5% aggregate, and **`ZERO_EXACT` is 0 in every stratum** | a rate measured on the population the member SERVES. **W2: the 11/18 figure came from 9 sessions whose overlap with the 24 failing sessions is ONE** — the model searched precisely where it did not send a bare name, so the rate was measured on the cases that already went right. If the pilot rate is low, 5.3 is redirected, not built |
| **5.3** | ✅ **BUILT 2026-08-09/10** — `refresolve.py` + `contracts/agent-runtime-ref-resolvers.json` (1 ref type, **19 bound (tool, param) pairs**), wired at the dispatch chokepoint in `stream_service` with the order **context-ids → PLAN → RESOLUTION → blank-check → dispatch**. Replayed over the REAL failing calls: **152 calls substituted · 209 refused ACTIONABLY · 0 silent · 0 resolver failures — 361/361 reach a branch** where today every one gets `entity_id must be a UUID`. ⭐ **LIVE on the deployed image, BOTH branches, before/after on the identical prompt:** `"Bela Quist"` → `ok:false / must be a UUID` became `ok:true` with the id resolved and recorded; `"Ember Codex"` → *"matched no entry exactly. Did you mean …"* with the argument unsubstituted | a name in an id field is resolved and **recorded**, or refused with candidates. **Never guessed** — see §3a. **Gated on 5.3-pilot** ✅ **CODE · LIVE · DATA all met** |
| 5.3b | 🔴 **WITHDRAWN — THE 120 DO NOT EXIST.** Over the frozen catalogue there are **1,389 properties and ZERO untyped**, at any depth. The figure is a `.get("type")` artifact: it returns `None` for `anyOf: [{"type":"string"},{"type":"null"}]` — Pydantic's `Optional[str]` — which **129 of the 498 `*_id` properties use**. I reproduced the same error before catching it | the member is **not in the registry**, because §7 forbids a clause whose subject does not exist — *that* is how C-3…C-17 became permanent. `test_THE_CATALOGUE_HAS_NO_UNTYPED_PROPERTY` keeps the absence honest: if a provider ever ships one, the subject appears and the test says so |
| **5.4** | **argument supplier** (23.7%) — every input declares model \| context \| plan | a `plan`-supplied input the model sends is **discarded** — CP-3.10 already does this; the contract makes it *declarable* rather than plan-only |
| **5.5** | **error contract** — every failure carries a C-7 class **and a message**. 🔴 **THE DENOMINATOR IS SMALLER THAN §1 SAYS, MEASURED 2026-08-10 BEFORE BUILDING: 26 calls / 17 sessions (4.7%), not 41 / 29 (8.1%)** — because **15 of the 41 are not failures at all.** They are calls SUSPENDED awaiting a human (`task: {status: "input_required"}`, `confirm_action`, `glossary_adopt_standards`), recorded `ok:false` with no message because they are *waiting*, not broken. 🔴 **That is a second defect and a bigger one: `ok:false` is carrying two vocabularies — a call that FAILED and a call AWAITING INPUT — and nothing downstream can tell them apart.** Fixing only the message would give a suspension a plausible error string and make the conflation permanent | a failure with no message cannot be produced — **and a suspension is not recorded as a failure** |
| **5.6** | **output contract + completeness** | 🔴 an `emits` path is checked at **plan-build** time; a truncated result is a **declared field the runtime must surface** |
| **5.7** | **repeat semantics** per §3 — cost removed, signal retained | a cached repeat is still counted and still escalates |
| **5.8** | **preconditions** (18.7%) — checked pre-dispatch **and** used to gate advertisement (§4.3), withholding recorded | a tool whose precondition is unmet is not advertised |
| **5.9** | ✅ **CLOSED BY 5.1/5.2 — CONFIRMED, NOT REBUILT.** Its exit is precisely what rung 2 does, and two falsified guards already prove both halves: `test_A_CONDITIONAL_MEMBER_IS_REQUIRED_ONLY_WHERE_ITS_TRIGGER_FIRES` and `test_STRIPPING_A_CONDITIONAL_MEMBER_THE_TOOL_TRIGGERS_ALSO_REFUSES` | absent-when-triggered is refused |
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

⭐ **WHAT "ESSENTIAL" MEANS — PO, 2026-08-10.** *"essential tools is not only tool_list and
tool_load, it should be considered as search tool and the important workflow is plan tools too, so
we will ship that user can use to write book with co-writer agent."* So the term is defined by a
**user journey**, not by a tool's novelty — and the exit is therefore **not circular**: these tools
already exist and are federated; they have simply never been admitted *through* the contract.

The set is **derived** (`scripts/cp5-essential-set.py`): roles from the journey, membership by
session reach above a floor of 1% of tool-calling sessions. **10 tools — `tool_list` · `tool_load` ·
`glossary_search` · `book_list` ✅ · `book_read` ✅ · `book_chapter_create` ·
`book_chapter_save_draft` · `plan_propose_spec` · `glossary_book_ontology_read` ·
`glossary_propose_entities`.** 🔴 **A first derivation reported the `compose` role as having no qualifying tool. That was WRONG
and is corrected:** `compose_prose` serves it at **2 sessions / 4 calls / 100% ok**, and was
invisible because the search ran over the FEDERATED snapshot alone — §4 scopes rung 2 to *"all
324"*, and the 9 chat-service-local tools are not in that file. What remains is a **decision, not a
gap**: `compose_prose` is the only tool for the role the PO named as the point of the journey, and
it sits below the reach floor (2 vs 3). **Open: does a role's only tool join the set regardless of
reach?**

**Exit:** a tool that does not implement the pattern **cannot be released**, proven by injection;
**the ESSENTIAL SET above is admitted through the contract** (2/10 today);
the residual (§1, 5.0%) is either classified or declared out of scope with a reason; and the first
essential tool is admitted **through** the contract with QC evidence.

**Only then does tool v2 resume.**
