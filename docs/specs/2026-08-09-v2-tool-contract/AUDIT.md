# V2 · the tool contract — a failure-mode audit, and the patterns that are missing

**Status:** audit complete, design proposed, **nothing built**. 2026-08-09.

**Why this exists.** The v1→v2 effort produced a working plan runtime and a *registry-row metadata*
contract, and I described it as *"a solid contract for tools."* That was wrong. The contract
constrains ten fields **about a catalogue row** — `id`, `kind`, `owning_service`, `lifecycle`,
`contract_version`, `admitted_against`, `members`, `lane`, `tier`, `cost` — and **nothing about the
tool**. Measured: `inputSchema`/`parameters` validated at admission → *zero occurrences*; a declared
result shape → *zero occurrences*; C-3…C-17 implemented → *no*.

The PO's instruction is the right one and this document exists to serve it:

> **the new architecture must be built AGAINST the defects we already face in the old one, not clone
> them into the new one.**

---

## 0 · The failure this document is itself an instance of

`contract.py` opens by deferring the per-tool clauses:

> *"C-3…C-17 are per-kind contract clauses whose subjects (arguments, results, error classes) do not
> exist until a declaration is written, and CP-4 admits the first one."*

CP-4 admitted declarations. **Nobody went back.** The deferral became permanent, silently, and no
gate could notice because a gate for a clause with no subject is exactly the vacuity this board has
a standard about. **The standard was applied to every mechanism except the contract itself.**

This is the same shape as `sweep_expired_runs` (zero callers behind a docstring) and
`agentruntime_arm` (a flag with no deployment path), both found on 2026-08-09. Three instances in
one day, and this is the third and largest.

---

## 1 · The audit — 4,175 recorded failures, from production data

Classified from `chat_messages.tool_calls` where `ok = false`. The denominator is the query's own
count, not a typed figure.

| # | failure mode | n | share | what the tool never declared |
|---|---|---|---|---|
| **A** | repeat-identical call | **2039** | **48.8%** | its **repeat semantics** — is a re-call free, or an error? |
| **B** | type / shape violation | 703 | 16.8% | **typed parameters** (`entity_id must be a UUID`, ×337) |
| **C** | required argument absent | 590 | 14.1% | **who supplies each argument** — model, context, or plan |
| **D** | precondition unmet | 349 | 8.4% | the **state it requires** (an open book, a project scope) |
| **F** | unknown / phantom tool | 198 | 4.7% | — the registry is not the only source of callable names |
| **E** | output unparseable | 40 | 1.0% | a **result contract** |
| Y | other | 215 | 5.1% | |
| Z | no message at all | 41 | 1.0% | |

**88.1% of every recorded tool failure is a missing declaration on the tool.** Not a model failure,
not a prompt failure. The runtime asked the model to supply something the tool never described.

### 1a · The two that deserve naming

**A is half of all failure, and the runtime's own response makes it worse.** `You have already
called X with these exact arguments` is the repeated-call breaker firing — a *generic* refusal,
because no tool declares whether repetition is meaningful. For a pure read, a repeat is free and the
right answer is the cached result. For a create, it is a real error. The runtime cannot tell them
apart, so it errors on both, burns a pass, and teaches the model nothing.

**F is not hypothetical.** `glossary_propose_entity_edit` was called **101 times with a 0% success
rate** and **does not exist in the catalogue**. A name the model invented, dispatched 101 times.

---

## 2 · The tool contract this implies

Ten members. Four exist today; **six are missing and they are the six that matter.**

| member | status | closes |
|---|---|---|
| identity + ownership (C-0) | ✅ derived from `source_path` | — |
| lane / tier | ✅ declared at registration (C-1) | — |
| cost | ✅ a pure function of the definition | — |
| supersession | ✅ `WithSupersededBy` | — |
| lifecycle + state machine | ✅ **added 2026-08-09** | release ≠ registration |
| **input contract** | ❌ | **B** (16.8%) — semantic types, not `string` |
| **argument supplier** | ❌ | **C** (14.1%) — model \| context \| plan, per argument |
| **output contract** | ❌ | **E** (1.0%) *and* makes `emits` checkable at build time |
| **preconditions** | ❌ | **D** (8.4%) — and gates advertisement (§4.3) |
| **repeat semantics** | ❌ | **A** (48.8%) — the largest single class |
| **error contract (C-7 per tool)** | ❌ | makes recovery decidable instead of guessed |

### 2a · The output contract is load-bearing beyond its 1%

CP-3's `emits` path is declared as a **literal string** (`books[0].book_id`) and `check_emit_path`
can only verify it is *syntactically* a path. It cannot verify that the path exists in
`book_list`'s result, **because `book_list` has no declared result shape**.

So `EmitPathError` fails at **execution**. §6.2's principle is *"a generation error, not a runtime
one"*, and for outputs it is currently inverted — the runtime failure was built and written up as a
feature. **An output contract turns that back into a plan-build rejection**, which is the whole
reason §6.2 exists.

---

## 3 · Enforcement — and the language is not the obstacle

The concern raised was that C# restricts and Python does not. **This repository has already proved
the pattern**, twice, and applied it to the wrong subject:

* `Admitted` **cannot be forged** — private module token + `object.__setattr__`, confined to
  `admission.py`. That is a sealed constructor.
* `Surface` has **exactly one construction site**, and a *gate counts them* rather than a docstring
  asking nicely.

Both techniques exist here and neither was applied to a tool. The enforcement ladder for v2:

| level | mechanism | fails at |
|---|---|---|
| 1 | `ABC` + abstract members | instantiation |
| 2 | **`__init_subclass__` validating the class** | **import** — the closest Python has to a compile error, and *stricter* than C#, which would need a source generator or startup reflection |
| 3 | frozen dataclass + `__slots__` | attribute smuggling |
| 4 | private-token construction for `Registered` | forgery |
| 5 | a CI gate counting registration sites | a second door |
| 6 | **admission refuses an incomplete contract** | release |

**Level 6 is the one that needs no other team's cooperation.** Tools live in Go and Python services
across the estate; chat-service cannot rewrite them. It *can* refuse to promote any declaration
whose contract is incomplete — so an unmigrated tool is registered `draft` and simply never serves.
The pattern becomes mandatory by consequence rather than by memo.

---

## 4 · Registry — discovery, not a file

Confirmed as the correct target:

* **populated by discovery** at runtime, never by a committed list. `derive.py` currently reads a
  frozen 315-tool snapshot, which is the opposite;
* **persisted with the lifecycle state machine**, so registration survives a restart and release is
  a recorded decision;
* **the count is never typed** — `len(registry)` is discovered, and no literal tool count may appear
  in code or in a guard.

Each tool self-registers from its own file (the plugin pattern), so `tool_list` / `tool_load`
genuinely do not know the population until the app runs.

---

## 5 · Sequence

1. **The tool contract type + `__init_subclass__` enforcement** — the subject C-3…C-17 never had.
2. **Admission refuses an incomplete contract** — level 6; makes 1 mandatory without cross-team work.
3. **Runtime registry** — discovery-populated, lifecycle-persisted, count never typed.
4. **Migrate the essential tools onto the pattern**, each released only on QC evidence.

(1) before (3): a runtime registry without (1) just moves unvalidated rows from a file into a table,
which is cloning the defect into the new architecture — the thing this document exists to prevent.

**Nothing here is built.** This is the audit and the proposal.
