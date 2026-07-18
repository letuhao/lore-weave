# Deterministic capability sweep — 116 tools, no LLM, no spend

**Date:** 2026-07-10 · **Track D · WS-D3 / ND3** · `scripts/eval/tool_liveness/sweep.py`

## The idea

The CD4 ship gate blocks on **`executes`** — *"does this tool work when called correctly?"*
That question **does not need a model.** Only `proven` (G1–G4 under a real LLM) does.

    NL probes  → `proven`   expensive · one model turn each · yields the F5 selection signal
    THIS sweep → `executes` cheap · MCP-direct · finds BROKEN tools

So the gate's blocking predicate can be populated over the whole catalog for free. The
manifest went from **10 tools → 119**.

## Safety — why calling ~116 real tools is allowed

| tier | n | swept? | why |
|---|---|---|---|
| **R** | 70 | ✅ | reads |
| **W** | 48 | ✅ | mints a `confirm_token` and writes **nothing** at call time; never redeemed |
| **A** | 83 | ❌ | auto-commits. `settings_update_profile` would mutate the real account; `memory_forget` would delete rows. Needs authored, fixture-scoped args. |
| paid | 5 | ❌ | a capability probe must never spend the user's money |

Everything ran against a throwaway fixture, torn down after. No probe addressed an id it
did not create.

## Result

    executes=true   57      proven to work when called correctly
    executes=false   0      (after the fix below)
    executes=null   62      inconclusive — never blocks

## The bug it found: `settings_get_profile` had **never worked**

```
validating tool output: validating root: validating /properties/profile:
type: map[...] has type "object", want one of "null, array"
```

Reproduced directly against provider-registry — no gateway, no LLM, **empty arguments**.

**Root cause.** `getProfileOut.Profile` was `json.RawMessage`. That type is `[]byte`, so the
Go MCP SDK infers its output schema as `["null","array"]` — while `encoding/json` marshals
it as the raw JSON it *holds*, an **object**. The SDK validates the tool's own output
against its own declared schema and rejects it. **100 % of calls, for every user, since the
tool was written.**

Its twin **`settings_update_profile`** is broken identically. The sweep could not call it —
it is Tier A — but the declared schema proves it: `profile.type = ["null","array"]`. Found
by reasoning from the root cause, not by probing.

**Why nothing caught it.** Every wire gate in this repo asserts over `tools/list`
**metadata**. Not one issues a `tools/call`. And no NL probe covered the settings domain.
A tool can be fully tiered, correctly scoped, schema-mirrored, drift-locked — and still
fail every single call.

**Fix + gate.** Both fields become `map[string]any`.
`TestSettingsMCP_NoOutStructUsesRawMessage` walks the package AST and fails on any
`*Out` struct with a `json.RawMessage` field. It asserts on the **Go type**, not the
schema: a genuine slice (`[]webSearchSource`) *also* declares `["null","array"]` and
correctly marshals as an array — the schema shape cannot tell them apart, the type can.
(My first attempt got this wrong and flagged four healthy tools. Negative-controlled: a
temp `Out` struct with a `RawMessage` field reds it; removing it greens.)

## The mistake I nearly shipped

The **first** sweep reported **11 broken tools**. Ten were my own bad arguments:

```
badly formed hexadecimal UUID string     ← I passed "tle-sweep" where a UUID was wanted
unknown kind: tle-sweep                  ← I passed a placeholder kind-code
no live genre with that code in this book
world_id is not a valid id: 'tle-sweep'
```

Had I fed that to the manifest, the CD4 gate would have **blocked ten healthy tools** from
every workflow and hidden them from `tool_list` — the exact false-block the three-valued
`executes` exists to prevent, defeated by a sloppy classifier.

Two fixes, and the second matters more than the first:

1. **Refuse to call what you cannot supply.** `fill_args` returns `None` for an id/uuid/
   reference-code with no fixture value. Not calling is the safe move: a placeholder id
   produces a lookup failure that says nothing about the tool.
2. **A widened caller-fault regex must not swallow the real bug.**
   `test_sweep_classifier_still_catches_the_real_bug_it_was_built_to_find` pins the exact
   `settings_get_profile` output-validation message as `executes: false`, alongside eight
   observed caller-fault messages pinned as `null`. Widen the regex all you like — that
   test says whether you widened it too far.

## Also found: 3 untiered tools on the federated wire

`tool_list`, `tool_load`, `find_tools` carried **no `_meta` at all**, so `tool_tier()`
silently defaulted them to `R`. Correct by luck — they are pure disclosure — but it is the
exact silent-default hole the per-service wire gates exist to close. They are
**consumer-local**, so no domain service's gate ever covered them. Now declared
`tier: R, scope: none` in lockstep (ai-gateway `find-tools.ts` + chat-service
`tool_discovery.py`). The federated catalog is now **100 % tiered**.

## Round 2 — Tier-A writes, and `_meta.scope` finally earns its keep

The first sweep skipped all 83 Tier-A tools because they auto-commit. But the *twin* of the
bug it found — `settings_update_profile` — is itself Tier A. Tier-A tools **write**, nothing
had ever called them, and that is exactly where the next output-schema break hides.

`_meta.scope` is what makes them reachable. Until now it was a validated declaration nobody
consumed; here it becomes the **safety predicate**:

| scope | n | swept? |
|---|---|---|
| `book` / `project` | **58** | ✅ can only touch the throwaway fixture we hand it, deleted afterwards |
| `user` / `none` | 25 | ❌ `settings_update_profile` rewrites the real profile; `memory_forget` deletes real rows |

Writes are opt-in (`--include-writes`), and four tests pin the filter — a bug there mutates
real user data. **174 of 204 tools swept. 72 execute. 0 broken.**

### And the false-positive class bit again

Round 2 reported two "broken" tools:

```
book_update_meta          no fields to update
book_chapter_update_meta  no fields to update
```

We called with **only the required args**, so there was nothing to change. The tool is right
to refuse. `book_chapter_update_meta` is sweep-only, so scoring it broken would have
**blocked it from every workflow**. Reclassified from the recorded error text — no re-run —
and asserted that reclassification only ever *relaxes*: **0 rows flipped toward broken**.

That is the third time this class has appeared. The lesson generalises: **a capability probe
that supplies only required args is not a meaningful call for a tool whose whole purpose is
an optional patch.** The classifier is a backstop, not the design.

### Cleanup bug in the sweeper itself

The sweep creates its own kg project (`Fixture.build()` doesn't), so `Fixture.teardown()`
knew nothing about it and leaked one row per run — three orphans before I noticed. *"No probe
may touch an id it did not create"* cuts both ways: it must also **destroy** what it did.
Fixed, and the orphans removed.

## Round 3 — the authored-args pass, and two more tools that never worked

Supplying **optional scope keys** the fixture already holds (`project_id`, `book_id`) unlocked
13 `kg_*` tools that had been refusing with *"no project in scope"* — they declare `project_id`
optional because it normally rides the `X-Project-Id` envelope, so a required-args-only call
never exercised them. `executes: true` went **71 → 81**.

Reading the *verbatim* errors of the tools that were merely "inconclusive" surfaced two more
tools that could never work — both **laundered by my own classifier**.

### `kg_entity_edge_timeline` — `TypeError` on every call

```
run_read() missing 1 required positional argument: 'user_id'
```

`get_entity_by_id_any_owner` legitimately needs an **unfiltered** lookup (`Entity.id` is
globally unique, and its caller grant-checks the returned project before exposing anything).
But it called `run_read`, whose `user_id` is a *required* parameter and whose
`assert_user_id_param` demands the cypher reference `$user_id`. Its cypher does neither — so
the call raised `TypeError`, twice over, on every invocation. Nothing else ever called it.

Fixed with a loudly-named `run_read_any_owner`, whose assertion is **inverted on purpose**: a
cypher that *does* carry `$user_id` meant to be filtered and must go through `run_read`, where
the filter is *enforced* rather than merely present. That stops the unfiltered path from
silently absorbing a query that wanted tenancy.

### `translation_list_versions` — SQL against a column that doesn't exist

```
column ct.model_source does not exist
```

`model_source` / `model_ref` live on `translation_jobs` — the model is a property of the *job*
that produced a version, not of the version. Postgres rejects the statement at parse time, so
the tool failed on **every real chapter, always**. (`LEFT JOIN`, not `INNER`: a hand-edited
version has a `NULL job_id` and hence no model.)

Its service's tests assert the tool's **name and tier**; nothing ever ran its SQL. New gate:
`PREPARE` every `_*_SQL` constant against the live schema — parse + plan, no rows, no side
effects, and a wrong column is a hard error. Negative-controlled.

## The classifier was wrong in *shape*, not content

I widened the caller-fault regex **four times**:

```
badly formed hexadecimal UUID string            ← our placeholder where a UUID was wanted
unknown kind: tle-sweep                         ← our placeholder kind-code
no fields to update                             ← our required-args-only call is a no-op
this project has no embedding model configured  ← our fixture lacks setup
```

Each widening killed a false positive and edged closer to swallowing a true one — **and twice
it did**, laundering both bugs above into "inconclusive".

The asymmetry is the point. **Caller-fault prose is unbounded**: every domain invents its own
vocabulary for *"you didn't set this up"*. **Tool-fault has a small, recognisable,
language-level vocabulary**: exceptions, SQL errors, panics, output-schema violations.

So the design inverted: **broken only on positive evidence, never by exclusion.** An
unrecognised failure is `null`, which blocks nothing; a missed detection costs nothing, while
a false positive blocks a healthy tool from every workflow. The costs are wildly asymmetric,
so the default must be `null`. The `_CALLER_FAULT` regex is deleted.

The inversion had to keep `settings_get_profile` — whose failure is an *output-schema
violation*, not an exception — so that pattern is now explicitly in the positive-evidence set.
A test pins exactly that: an unrecognised error is `null`, and the schema violation is still
`false`.

## Round 4 — the throwaway USER, and chaining

`_meta.scope` unlocked the 58 book/project-scoped writes: they can only touch the throwaway
book we hand them. The 25 **`user`/`none`-scoped** writes have no such handle — they mutate
*the caller*. `settings_update_profile` rewrites the profile; `glossary_user_create` adds a
user-tier kind. Against the real test account that is vandalism, so nothing ever called them.

**That is exactly where the bug lived.** `settings_update_profile` carried the same
`json.RawMessage` output-schema break as its twin and failed 100 % of calls — fixed earlier by
*reasoning from the root cause*, because nothing could call it. A throwaway user is how we stop
needing to be lucky. It is now **proven**, not inferred.

The fixture registers a real user (an invented UUID fails at auth-service), sweeps as them, and
deletes every row keyed to the id it created — across `auth`, `knowledge`, `glossary`,
`agent_registry`, `composition`. Tables enumerated from `information_schema`, not guessed.

### Chaining: a fixture cannot invent a row the tool is supposed to make

`glossary_user_patch` / `_delete` / `_restore` need a `code` + `base_version` that only
`glossary_user_create` can mint. So `_sweep` now threads a `state` dict of every successful
result forward, and `USER_SWEEP_ORDER` guarantees a creator runs before its consumers. A test
pins the ordering — *a delete before its create silently skips forever*.

That took the user-scoped set from **5 → 11 of 25 proven**:

```
glossary_user_create → _patch → _delete → _restore     (full lifecycle, ending restored)
kg_project_create → kg_view_upsert → kg_view_delete
settings_update_profile · settings_model_set_default
registry_propose_skill · registry_propose_workflow
```

The remaining 14 need a motif, a job, or a provider credential. `settings_model_*` cannot be
reached at all: creating a credential is deliberately **not** a tool (OD-S1, no secret may be an
LLM-visible arg). Honest `null`; blocks nothing.

### And the leak, again

`run.py` creates a kg project via `kg_project_create` and never deleted it — the same bug I had
just fixed in `sweep.py`. **Five orphans** had accumulated from yesterday's harness runs. Fixed
at the source and cleaned up. *"No probe may touch an id it did not create"* cuts both ways: it
must also destroy what it did.

## Where the manifest stands

**199 of 204 tools** (the 5 missing are paid — never swept). **126 execute · 0 broken · 78
inconclusive · 5 proven G1–G4.** (Was 93 execute / 106 inconclusive before the three
reachability passes below.)

### The three passes that took 93 → 126 execute

1. **`$ref`/`$defs` resolution in `fill_args`** — 28 composition tools wrap their real args in
   a single required field, `{"args": {"$ref": "#/$defs/_XArgs"}}`. The old builder saw
   `type: None` on the `$ref` node and refused; the `$defs` fully describe the object, so it is
   *buildable* (a model resolving the schema constructs it too). Unblocked the composition
   create/generate/list family.
2. **A seeded, KEYLESS throwaway credential + model** — the 6 credential-gated tools
   (`settings_provider_inventory` + the five `settings_model_*`) all need a
   `provider_credential_id` / `user_model_id`. A model in the loop cannot MINT a credential — that
   needs a secret in the Settings UI, and OD-S1 forbids a secret as an LLM-visible arg — so
   nothing ever called them. That is missing *fixture* state, which is buildable (not "unreachable
   by design"). The fixture seeds a keyless credential (a real production state: provider added, no
   key yet) directly in the DB; every one of these 6 is a metadata op that never reads the secret.
   **All 6 now execute.** (This corrected an earlier plan to WAIVE them — waiving would have
   asserted "never executes:true", which a 2-INSERT seed disproves.)
3. **Chained creators (`project_chain.py` + the phase-2 motif order)** — the composition and
   planforge families mint an id a sibling consumes. `composition_create_work` mints the
   COMPOSITION `project_id` (distinct from the kg project — a kg id fails these tools with "not
   found"); `plan_propose_spec` in `rules` mode runs SYNCHRONOUSLY ($0, no LLM) and returns a real
   `run_id`; `outline_node_create` (kind `beat`) and `canon_rule_create` return `{id, version}`
   their update/delete twins consume; `composition_motif_create` mints a `motif_id` for the
   user-scoped motif reads/writes. All threaded through the sweep's `state` dict, all torn down
   (a leak check confirms 0 rows survive).

Four tools that could never work, all found in one day, none by a test:

| tool | failure | reachable now |
|---|---|---|
| `settings_get_profile` | `json.RawMessage` output-schema break | ✅ executes |
| `settings_update_profile` | same, Tier-A twin | ✅ executes |
| `translation_list_versions` | SQL against a dropped column | ✅ executes |
| `kg_entity_edge_timeline` | `TypeError` on every call | past the crash; needs graph state |

Every one was fully tiered, correctly scoped, schema-mirrored and drift-locked. The gates only
ever read `tools/list` **metadata**; not one had issued a `tools/call`.

## WS-D4 — `executes ∧ effect` for the workflow-critical set

`executes` from the sweep means *"the tool returned success."* But a tool can return
`{"ok": true}` and write nothing — the silent-success bug this whole eval exists to catch.
For most tools that gap is tolerable (they are on no shipped path). For the tools a
**curated workflow** references, it is not. So those — and only those — are held to the
stronger bar `executes ∧ effect`, where `effect` is an INDEPENDENT read-back (CD3's
anti-oracle rule: the domain's Postgres directly, or the tool's own returned id re-read
from the DB — never the tool's read API).

The critical set is **derived live** from `agent_registry.workflows` (anti-drift — a
workflow that starts referencing a new tool pulls it in automatically). Today it is the
four steps of `glossary-bootstrap`:

| critical tool | effect check | result |
|---|---|---|
| `book_get` (R) | returned `book.book_id` == the fixture book | ✅ effect verified |
| `glossary_adopt_standards` (W) | a real `confirm_token` was minted (not an empty ok) | ✅ effect verified |
| `glossary_propose_entities` (A) | the claimed `entity_id` actually exists in `glossary_entities` | ✅ effect verified |
| `glossary_extract_entities_from_doc` (R, **paid**) | an LLM extraction — cannot verify at $0 | ⚠️ honest gap |

A critical tool that returns ok but whose effect does NOT land is scored **`executes:
false`** (a silent success lies — worse than a crash), which the CD4 gate already rejects.
The manifest records `effect_verified: true` for tools that cleared the bar (matrix-proven
tools inherit it — a matrix PASS is G1–G4; `proven ⊆ effect_verified`). One honest
finding: the sole curated workflow depends on a **paid** tool the $0 sweep cannot prove
end-to-end.

## What `executes: null` means here

78 tools remain inconclusive. They are **not** blocked and **not** hidden — `null` blocks
nothing. The residue is now well-characterized, and it is no longer "the fixture cannot supply
an id" (that was the pass-3 grind); what is left genuinely needs more than authored args:

| residue | n | why it is left |
|---|---|---|
| authoring-run family (`composition_authoring_run_*`, `plan_compile`/arc) | ~14 | needs a real authoring run — `authoring_run_create` is Tier-W (mints a token, no run) and confirming it **spends** a `budget_usd`; `plan_compile` needs an `arc_id` that only a model plan run produces |
| `job_id` consumers (`jobs_*`, `composition_get_*_job`) | 7 | needs a real async job result — enqueuing one spends |
| kg graph-state (`kg_build_graph`, `kg_sync_apply`, `kg_triage_*`, `kg_world_query`) | ~9 | needs an adopted ontology + a built graph — a deeper fixture |
| glossary `items`/`ops`/`kinds` batch tools | ~8 | needs authored structured payloads (a real proposal batch) |
| registry `slug` consumers (`registry_get_skill`, …) | 5 | a *proposed* skill is not retrievable/editable — needs admin **approval** |
| long tail: translation versions, glossary merge, kg template/edge, one-off creators | ~35 | each a bespoke creator chain or a genuinely-external dependency |

The cheap grind is done; the rest clears the defer gate (blocked on spend / approval / a
larger fixture). Closing any cluster is a scoped follow-up, not a one-liner.

## Reproduce

```bash
python -m scripts.eval.tool_liveness.sweep                  # dry run: the plan + safety split
python -m scripts.eval.tool_liveness.sweep --execute --date <date>
python -m scripts.eval.tool_liveness.manifest \
    docs/eval/tool-liveness/<date>/matrix.json \
    docs/eval/tool-liveness/<date>-sweep/sweep.json
```

The manifest writes `contracts/tool-liveness.json` plus the two service copies; a drift
lock in each service reds if they diverge.
