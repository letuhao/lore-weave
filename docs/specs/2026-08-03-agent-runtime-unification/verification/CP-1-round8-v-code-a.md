# CP-1 · round 8 · V-CODE — Verifier A (items 1.8 and 1.9, and the spec they rest on)

*Artifact frozen at `73241817cb7424069862e9ea2df9db09b8b4e35a`. Verified with `git rev-parse HEAD`
at the start of this session and again immediately before writing this file; **HEAD did not move**,
and the only untracked path in the tree is Verifier B's verdict file. I wrote no tracked file other
than this one, ran no `git checkout`, and touched nothing live.*

*Every line below that says **measured** was produced by code I executed. Injections were applied to
a **copy of the repository in a scratch directory** (`repo/services/chat-service` + `contracts`,
`sdks`, `scripts`), never to the working tree. End-to-end drives used the real `stream_response` /
`resume_stream_response` / `KnowledgeClient` with the MCP transport raising.*

**Baselines, measured at HEAD:** full chat-service suite `2175 passed`; the five named suites
`357 passed`; `python scripts/agentruntime-membrane-gate.py` → `rc=0`, *"OK — 8 module(s), 0 allowed
external import(s), 2 single-sited type(s)"*, selftest *"fires on 7 import shapes + 3 forgery + 14
ambient shapes"*.

---

## 1 · Verdict

| | claim | round 7 | round 8 |
|---|---|---|---|
| **U-1** | Unicode normalisation cannot silently delete a declaration from the wire | FAIL | **PASS, with two residuals** — the deletion mechanism is genuinely closed at both ends |
| **U-2** | a catalogue that fails to load registers the narrowing **and** tells the model | FAIL | **FAIL** — it now registers, and the registration **kills the turn** on the two shapes that run the tool loop |
| **U-3** | skill vectors are never shared between two embedding models | PASS | **PASS** — F11 (the twin's second fix) is ported |
| **U-4** | one user's availability signal never reaches another user's turn | PASS | **PASS** — F15 closed (`_catalog_meta` dropped on outage) |
| **1.8a** | narrowing stages are data with a closed kind set; ordering explicit | FAIL | **FAIL** — three further routes to arbitrary logic, measured; the kind set is closed for `Filter.value` and for nothing else |
| **1.8b** | one canonical serialisation | PASS w/ correction | **PASS** — and §0.14.1c now names the enforcement honestly |
| **1.8c** | ambient reads confined to one module, gate-enforced | PASS w/ residual | **PASS** — F12 closed via `ambient.module_anchor()`; all seven measured blind spots covered, each with a selftest probe |

**Overall: FAIL.**

Twelve of the sixteen findings are genuinely closed, several of them well. The verdict turns on two
things:

1. **U-2's fix introduced a harder defect than the one it repaired.** The catalogue-scope record
   deliberately omits `tool`; two consumers index `_sw["tool"]` unguarded. Round 7's arm-after-use
   meant the row was never written, so the landmine was latent. Round 8 armed the sink first — and
   the row now reaches `stream_service.py:6970` and raises `KeyError: 'tool'`. **Measured on a real
   agui editor turn and on a real resume turn: `RUN_ERROR "'tool'"`, the model never called.**
   Before the fix, the outage was silent; after it, the outage takes the turn down.
2. **The new arm-order gate has four ways past it, not one.** The builder disclosed one (an alias).
   I measured three more green, including a *routine refactor* (extract the fetch into a helper) that
   reproduces round 7's defect end-to-end while the gate reports `14 passed` — and a **fourth turn
   entry point that already exists in the tree, unarmed**: `voice_stream_response`.

---

## 2 · The falsifier, per claim — stated before the search

### U-2 — FAIL

**Falsifier:** any of (a) a path through either entry point where a narrowing precedes the arming;
(b) a turn shape where the outage registers but the notice does not reach the model; (c) a way past
the gate other than the disclosed alias; (d) **anything the record's own shape breaks**.

(a) and (b) are **closed on the happy path**, and I say so plainly. `arm_turn_surface()` is the
first statement of both entry points (`stream_service.py:4998`, `:7726`), the async-generator body
mutates the caller's context so the set propagates, `_emit_chat_turn` adopts rather than replaces
(`:6570-6573`), and the sink is a list whose appends survive a `contextvars` copy into a child task.
Driven end-to-end with the real client on a failing MCP transport:

```
FRESH   notice_reached_model=True   events=5
ADMIN   notice_reached_model=True   events=5
RESUME(admin) notice_reached_model=True   events=10
```

(d) is where it fails. `record_catalogue_unavailable` writes `{scope, stage, reason}` — **no `tool`,
deliberately**, and the docstring argues that choice at length. The turn's drain does not know:

```python
# services/chat-service/app/services/stream_service.py:6968-6971
while _surface_sink:
    _sw = _surface_sink.pop(0)
    _advertised.record_withheld(
        _sw["tool"], stage=_sw["stage"], reason=_sw["reason"],   # ← KeyError on a scope row
    )
```

Measured, real drive of `stream_response(stream_format="agui", editor_context={...})` with the MCP
transport raising — the ordinary editor chat turn:

```
events: 5
last:   data: {"type": "RUN_ERROR", "message": "'tool'", "code": "STREAM_ERROR"}
---- traceback ----
  File ".../app/services/stream_service.py", line 6970, in _emit_chat_turn
    _sw["tool"], stage=_sw["stage"], reason=_sw["reason"],
KeyError: 'tool'
```

and the same on the plain resume turn (`RESUME notice_reached_model=False, RUN_ERROR "'tool'"`).
The crash happens **before** the gateway is called, so on those shapes the model does not merely
miss the notice — it never runs.

Why it fires there and not on the legacy fresh turn: the drain hangs off the `advertised` chunk,
which only `_stream_with_tools` emits. A legacy turn with an empty catalogue is tool-free, so no
drain. An **agui** turn keeps `propose_edit` advertised regardless of the memory catalogue (the
resume path's own comment says it mirrors the fresh path), so `use_tools` stays true — and the agui
editor `<Chat>` is the product's main surface.

**The second landmine, same shape:** `instrument.py:551`,
`if w["tool"] not in by_pass.get(w.get("pass"), set())` in `withheld_json()`. Measured directly:
`KeyError: 'tool'`. It would fire at persist if the drain were patched with `.get("tool")`. And
`record_withheld(None, …)` is *accepted* — measured, producing `{'tool': None, …}`, which is the
`tool: "*"` sentinel the record's own docstring rejects as *"a wrong answer while still looking
correct"*, arrived at by a `.get()`.

**Proof this is NEW, not pre-existing:** with round 7's ordering restored (injection I3b below), the
same agui turn yields `6 events` and **no** `RUN_ERROR`. The fix converted a silent no-op into a
turn-killing crash.

(c) — three more ways past the gate, all measured green. See §4.

**A fourth, live turn entry point.** `voice_stream_service.voice_stream_response` (`:215`, routed at
`app/routers/voice.py:83`) fetches the catalogue at `:452`, feeds it to the shared
`_stream_with_tools` at `:456`, and **never arms**. Measured: `arm_turn_surface` and
`surface_withheld` do not appear anywhere in the module, and `CATALOGUE_UNAVAILABLE_NOTICE` does
not either. In an unarmed context the outage registers nowhere. The gate cannot see it — it parses
`stream_service.py` only and hardcodes two function names — and `test_ALL_THREE_TURN_SHAPES_reach_
the_notice` asserts a **subset** (`{...} <= users`), so a fourth entry point is invisible to it by
construction, despite the docstring claiming *"so a fourth entry point cannot inherit the silence by
omission."*

**Did the admin move break anything?** No. Measured with a counting stub on a full admin turn:
`get_admin_tool_definitions` awaited **once**, `get_tool_definitions` **zero** times; the guard at
`:5612` is byte-identical to the old site's (`not disable_tools and kctx.tool_calling_enabled` +
`admin_context`); `:5964` reads `_admin_tool_defs` rather than re-fetching; `tests/test_admin_
surface.py` — the file that owns this contract, including `assert_awaited_once_with` — is 11/11
green.

**One sibling still open on the admin door.** `get_tool_definitions` registers an outage on *both*
its failure branches — the transport exception (`:662`) and *"mcp package not installed"* (`:640`).
`get_admin_tool_definitions` registers on the first (`:749`) and **not** on the second
(`:717-721`: log, `return []`, no record). The new parametrised test drives only the
transport-exception branch, so the half-fixed sibling is green.

### U-1 — PASS, with two residuals

**Falsifier:** a string that reaches a consumer assuming NFC and is still decomposed, *and* whose
decomposition changes an outcome.

**The deletion mechanism is closed, and closed at the right end.** `_nfc_text` composes
`description`/`title`/`summary` at any depth plus all of `_meta`; `_tool_tokens`
(`tool_surface.py:123`) composes the *whole* dump before counting, and **every ranking and budget
path goes through it** — `:204`, `:207`, `:210`, `:298`, `:770`. So even a field the door does not
touch cannot move a budget cut. Measured: schema `description`, `enum`, `x-hint`, `examples`,
`$comment`, `default` — NFD and NFC all cost the same. `canon.digest` normalises before hashing, so
NFD and NFC documents digest identically (measured `True`); F9's stated harm was already absent, and
`canon.nfc` at `manifest.py:311` is nonetheless a correct fix.

**Residual 1 — the admin door composes nothing.** `knowledge_client.py:754-763` builds the admin
tool list with `"description": t.description or ""` and a raw `_normalize_tool_parameters(...)`.
Measured: `admin description stored NFC? False` against `user description stored NFC? True`. Token
damage is closed by `_tool_tokens`, so this is not a falsifier of the headline claim — but it is the
same door, the same round, and the **same sibling the builder just fixed for U-2 and parametrised a
test over**. U-1's test covers one method.

**Residual 2 — "identifiers verbatim" is safe for the estimator and not for the three consumers that
read a name as prose.** `_embedding_text` (`tool_discovery.py:1221`) and `_score` (`:670`) treat the
tool name as part of the semantic haystack, and `_catalog_signature` (`:1229`) hashes the name set
as a snapshot key. Measured on one overlay tool, NFC name vs NFD name, same words:

```
_embedding_text equal?     False
_catalog_signature equal?  False       (→ a cache split, then a re-embed)
_score(intent="tim kiem")  0.0  vs  0.857
```

That is arrival encoding changing which tools `find_tools` returns. `_nfc`'s own docstring gives the
embedder as a reason for normalising; the decision to leave identifiers verbatim is right for the
wire and was never checked against the two consumers that read one as text.

**Residual 3 (minor) — a second, non-composing estimator over the same object.**
`stream_service.py:2268`, `estimate_tokens(json.dumps(_td))` — no NFC, no `ensure_ascii=False`.
Measured on the same definition: `_tool_tokens` = 36, this = 40. Observability only (it feeds the
`schema_tokens` split and the persisted `context_breakdown`), but it is the sibling `_tool_tokens`
did not get.

### 1.8a — FAIL

**Falsifier:** a third route to arbitrary per-row logic that passes `validate_pipeline`, or a
constructible stage that is not content-addressable.

The two routes the previous round measured are genuinely closed: exact-type membership
(`surface.py:290`) rejects a duck-typed stage and a subclass, and `Filter.value` is bounded by
`type(x) in SCALARS` (`:112-127`). Both injections red (I9, I10). The ordering rules, the rank
record and `_require_names` are all real. **But the bound was applied to one field.** Seven other
stage operands carry a declared type and no check, and three of them run arbitrary logic. All
executed against the real `SurfaceAssembler`:

| route | measured |
|---|---|
| **`TakeWhileBudget.budget`** — `used + cost > stage.budget` (`surface.py:466`) puts the operand on the right of `>`, so `int.__gt__` returns `NotImplemented` and Python calls **the operand's `__lt__`, once per row** | `TakeWhileBudget("s","r",budget=<Oracle>)` constructed, `validate_pipeline` silent, assembled → `names=('t0',)`, **oracle consulted 3×**. An arbitrary predicate deciding a rank-dependent cut |
| **`Filter.field`** — only `if not self.field`; `row.get(self.field)` then dispatches on the operand's `__hash__`/`__eq__` | `Filter("s","r",field=<EvilKey>,op="eq",value="tool")` ran → `names=('t0','t1','t3')` |
| **`TopK.k`** — only `if self.k < 0`; `rows[:k]` calls `__index__` | `TopK("s","r",k=<ComputedK>)` ran → `names=('t0','t2')`, withheld 2, conservation law satisfied |
| **`_Narrowing.stage` / `.reason`** — only truth-tested | `Filter(<Truthy>, <Truthy>, …)` constructed |
| **`OrderBy.keys`** — no element typing at all | `OrderBy(keys=((<FieldKey>,"asc"),))` constructed and sorted; `effective_keys()` returns the forged key |
| **the class-identity check itself** — `type(s) in _KIND_SET` is frozenset containment, i.e. `hash` + `__eq__` **on the class** | a `ForgeMeta` metaclass returning `hash(Filter)` and `__eq__(Filter)` → the arbitrary-lambda stage **ran**: `names=('t0','t2')`, withheld 2, `validate_pipeline` silent |
| **post-construction mutation** — frozen+slots is not a lock | `object.__setattr__(f,"value",Regexish())` on a validated `Filter` → the round-7 regex stage, restored, ran |
| **`_narrow` without `validate_pipeline`** | `assembler._narrow(rows, ArbitraryStage(), pass_number=1)` ran and registered |

The first three are the answer to *"find a third route"*: they need no metaclass, no
`object.__setattr__`, and no private method — an ordinary construction with a wrong-typed argument.
`TakeWhileBudget.budget` is the sharpest: it is the accumulator §0.14.1 built the whole design
around, and it consults an arbitrary object once per row.

**"Every constructible stage is now content-addressable" is false, measured.** §0.14.1 states this
as the reason the operand bound makes the second justification true *"of the whole kind set rather
than of its examples"*:

```
Filter(plain)                       digest OK
OrderBy(plain)                      digest OK
Filter(stage=<Truthy>)              NotCanonicalisable: $.stage has no canonical form
Filter(field=<EvilKey>)             NotCanonicalisable: $.field
TopK(k=<Sneak>)                     NotCanonicalisable: $.k
TakeWhileBudget(budget=<Oracle>)    NotCanonicalisable: $.budget
OrderBy(keys=((<FieldKey>,…),))     NotCanonicalisable
```

The test named after the claim (`test_every_kind_is_CONTENT_ADDRESSABLE__which_was_the_stated_
reason`) enumerates six well-formed instances and asserts their digests differ. That is the
"well-behaved subset" the previous verdict objected to, restated — not answered.

**"The default IS the failure mode" was applied to two of the four kinds that have one.** Measured
against a 4-row document:

```
AllowList('s','r')          REJECTED  ("narrows the surface to NOTHING")
DenyList('s','r')           REJECTED
Filter('s','r')             REJECTED  (no field)
OrderBy()                   REJECTED  (no keys)
TopK('s','r')               CONSTRUCTED and RAN -> names=()      ← 4 admitted, 0 offered
TakeWhileBudget('s','r')    CONSTRUCTED and RAN -> names=('t2',) ← budget 0
```

`TopK`'s default `k=0` is *literally* the AllowList failure — "narrows the surface to nothing,
reached by a default rather than by a decision" — in the kind next to it in the same file.

### 1.8b — PASS

**Falsifier:** a second thing in `app/agentruntime/` deciding what bytes get hashed. None:
`hashlib`, `sort_keys=` and `separators=` occur only in `canon.py`. The §0.14.1c row now reads
*"**built**, enforced by a unit test"* rather than "gate-enforced" — the correction is honest and is
the model the other rows should follow.

### 1.8c — PASS

**Falsifier:** an ambient read inside the package outside `ambient.py` that the gate is green on.
F12's live instance is closed: `Path(__file__).resolve()` moved to `ambient.module_anchor()`, and
`manifest.py` now carries only `Path("contracts")/…` and an explicit-override path. The gate's
selftest reports **14 ambient shapes** (up from the list that missed seven), `_purity_boundary()`
runs on every default invocation, and the `receiver != "ambient"` carve-out is intact. `ambient.py`'s
docstring names the residual — *"a disclosure of one blind spot is not a disclosure of the others"* —
which is the right form.

---

## 3 · The bypass table

| the property asserts | the path that defeats it | measured? |
|---|---|---|
| U-2 · "a catalogue outage registers **and** the model is told" | the record's own shape crashes the drain at `stream_service.py:6970`; on an agui or resume turn the model is never called | ✅ `RUN_ERROR "'tool'"`, traceback captured |
| U-2 · the arming precedes every narrowing in a turn | `voice_stream_response` is a third live entry point, unarmed, outside the gate's file and name list | ✅ registers nothing in an unarmed context |
| U-2 gate · "no narrowing precedes the arming" | extract the fetch into a module-level helper (I3b) | ✅ gate `14 passed`, defect reproduced e2e |
| " | make the arm conditional (I4) — the gate compares **line numbers**, not reachability | ✅ suite `356 passed` |
| " | add a fourth entry point (I5) — `set(found) == {...}` / `<=` are pinned to two names | ✅ suite `356 passed` |
| " | `getattr(kc,'get_tool_definitions')(...)` (I14b) — the disclosed alias, without a local binding | ✅ gate `14 passed` |
| U-1 · "text is composed at the door" | `get_admin_tool_definitions` composes nothing | ✅ `stored NFC? False` |
| U-1 · "identifiers verbatim is safe" | `_embedding_text` / `_score` / `_catalog_signature` read the name as prose | ✅ score `0.0` vs `0.857` |
| 1.8a · "membership by exact type" | a metaclass forging `hash`/`__eq__` on the class | ✅ arbitrary lambda ran |
| 1.8a · "the operand is bounded" | `budget`, `field`, `k`, `stage`, `reason`, `cost_field`, `keys` are unbounded | ✅ three ran arbitrary logic |
| 1.8a · "rejected at construction" | `object.__setattr__` on a frozen+slots stage; `_narrow` called directly | ✅ both ran |
| 1.8a · "the default IS the failure mode" | `TopK("s","r")` → surface of zero | ✅ |
| 1.8a · "every constructible stage is content-addressable" | five constructible stages `canon.digest` refuses | ✅ |
| **1.8b** · one canonicalisation in the package | none found — regex for `hashlib`/`sort_keys=`/`separators=` over all 8 modules, plus a read of every module's imports | — |
| **1.8c** · ambient reads confined to `ambient.py` | none found — gate run at HEAD (`rc=0`), selftest covers 14 shapes incl. all seven the last round measured missing; `manifest.py` re-read for `Path`/`environ`/`__file__` | — |
| **U-4** · per-user availability signal | none found — `_catalog_meta` is now popped on every registered outage (`knowledge_client.py:786`) | — |

---

## 4 · The red-ability table

Baseline for every row: **suite = `356 passed, 1 deselected`** (the five named suites minus one
CI-workflow-file test that cannot run in a scratch copy); **arm-gate subset = `14 passed`**;
**membrane gate `rc=0`**. Every injection was applied to the scratch copy and reversed by restoring
from a pristine snapshot — never `git checkout`.

| # | injection | what it models | suite | gate |
|---|---|---|---|---|
| I1 | delete `arm_turn_surface()` from `stream_response` | the fix itself | **1 failed** (`test_both_entry_points_arm_exactly_once`) | rc=0 |
| I2 | a `get_tool_definitions(...)` call above the arm | the seventh recurrence, verbatim | **1 failed** (`test_no_narrowing_precedes_the_arming`) | rc=0 |
| **I3b** | **both catalogue fetches extracted into module-level helpers, arm drifts below** | **a routine refactor** | **356 passed — GREEN** *(arm-gate 14 passed)* | rc=0 |
| **I4** | **the arm wrapped in `if admin_context is None:`** | a line-number gate cannot see reachability | **356 passed — GREEN** | rc=0 |
| **I5** | **a fourth entry point in the same module, unarmed** | the docstring's own claim | **356 passed — GREEN** | rc=0 |
| **I14b** | **`getattr(kc,'get_tool_definitions')(…)`, arm drifts** | the disclosed alias blind spot | **arm-gate 14 passed — GREEN** | rc=0 |
| I6 | `parameters` no longer composed at the door | U-1's missed half, restored | 1 failed (`test_the_INGESTION_PATH…`) | rc=0 |
| I7 | `_meta` no longer composed | U-1's other missed half | 1 failed (same) | rc=0 |
| I8 | `_tool_tokens` no longer composes | the identifier residual re-opens | 1 failed (`test_an_identifier_left_verbatim…`) | rc=0 |
| I9 | `type(s) not in _KIND_SET` neutralised | 1.8a route 1 | 1 failed (`test_AN_ARBITRARY_STAGE_OBJECT_IS_REFUSED…`) | rc=0 |
| I10 | `Filter.value` bound removed | 1.8a route 2 | 1 failed (`test_THE_OPERAND_IS_BOUNDED…`) | rc=0 |
| I11 | admin catalogue stops registering its outage | U-2's sibling | 1 failed (`test_EVERY_catalogue_path_registers…`) | rc=0 |
| I12 | resume stops telling the model | U-2's third turn shape | 1 failed (`test_ALL_THREE_TURN_SHAPES…`) | rc=0 |
| I13 | `_require_names` neutralised | "the default IS the failure" | 1 failed (`test_an_EMPTY_list_kind_is_refused…`) | rc=0 |

**I3b, in full, because it is the one that matters.** Extract `get_tool_definitions` and
`get_admin_tool_definitions` into two module-level helpers and let the arm settle below the fetch
block — the shape a tidy-up commit produces. The entry point still contains
`filter_intent_gated_setup_tools` and `discovery_seed_for_surface`, so the gate keeps a subject and
reports `14 passed`. Driven end-to-end on the same injected copy:

```
FRESH  notice_reached_model=False       ← round 7's defect, reproduced verbatim
arm-gate under I3b: 14 passed
```

The gate is anchored to a *hand-kept list of callee names inside two hand-named functions*. Both of
those are the same class of anchor as the 900-character window it replaced, one level up.

---

## 5 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| U-2 arm at the top of two entry points | every other turn entry point in the service | repo-wide `get_tool_definitions` callers; read `voice_stream_service`; grepped it for `arm_turn_surface`/`surface_withheld`/the notice | **NO** — `voice_stream_response:215/452`, live, routed at `routers/voice.py:83` |
| U-2 admin outage registration | the *other* early-return in the same method | read both methods branch by branch | **NO** — `knowledge_client.py:717-721` ("mcp not installed") registers nothing; the twin at `:640` does |
| U-2 catalogue-scope record | every consumer of the sink that indexes a field the new row-type lacks | `grep '\["tool"\]'` across `app/services`, then executed both | **NO** — `stream_service.py:6970` (crashes the turn) and `instrument.py:551` |
| U-1 `_nfc_text` at the door | the other catalogue ingestion in the same file | read both list-tools methods; executed both outputs | **NO** — `get_admin_tool_definitions` (`:754-763`) |
| U-1 `_tool_tokens` composes | every other place that counts a tool definition | `grep estimate_tokens` across `app/`; ran both expressions on one definition | **NO** — `stream_service.py:2268` (36 vs 40 tokens) |
| U-1 "identifiers verbatim, closed at the estimator" | the *other* consumers that read a name | read `_embedding_text`, `_score`, `_catalog_signature`; executed all three | **NO** — all three differ under NFD |
| 1.8a `Filter.value` bounded | every other stage operand | enumerated `dataclasses.fields` of all six kinds and executed a wrong-typed value into each | **NO** — `budget`, `field`, `k`, `stage`, `reason`, `cost_field`, `keys` |
| 1.8a `_require_names` on the list kinds | every kind whose default is the failure | constructed all six with defaults and assembled | **NO** — `TopK(k=0)` → surface of zero |
| 1.8a exact-type membership | how `in` on a frozenset of classes is decided | metaclass `__hash__`/`__eq__`; `object.__setattr__`; direct `_narrow` | **NO** — three routes past it |
| §0.14.2 "gate-enforced" → "enforced by a unit test" | the other rows using the word "gated" | grepped the gate script for `STAGE_KINDS`/`validate_pipeline`/`OrderBy`/`canon`/`arm_turn` — **zero hits** | **NO** — §0.14.1c rows 1 and 2 still say "built and gated" |
| U-3 `_get_skill_vectors` model key | the twin's *second* fix (HIGH-2) | read the diff and the new test | **YES** — `_resolve_embedding_model(user_id)`, static fallback when absent |
| U-4 `_catalog_meta` per-user | its invalidation on failure | read `_register_catalogue_outage` | **YES** — `.pop(cache_key, None)` |
| 1.8c ambient list | the seven shapes the last round measured missing | ran the gate + selftest at HEAD; re-read `manifest.py` | **YES** — all seven, each with a probe |

---

## 6 · §0.14 and §0.14.1c, judged as claims

The four rewritten overstatements are genuine improvements. §0.14.1's new 🔴 block states the two
measured routes as requirements rather than leaving them to follow from a table; §0.14.1c's
"UNBUILT" rows (`lane`/`tier`/`cost`, `relevance`, `_is_read_tool`, the budget) are honest, correctly
owned, and match the code — I checked each. §0.14.2's *"enforced by a unit test"* is exactly the
correction the last round asked for.

**The table is not true in two rows.**

| row | says | measured |
|---|---|---|
| `order_by` required…; rank recorded | **built and gated** | **built**, enforced by pytest. `scripts/agentruntime-membrane-gate.py` contains no `validate_pipeline`, `OrderBy`, `STAGE_KINDS` or ordering check — zero grep hits. Same equivocation the row two lines below was corrected for |
| kind set closed by exact type; `value` bounded; empty list kinds rejected | **built and gated** | **false in three respects and not gated.** Exact type is defeated by a metaclass; `value` is bounded and six other operands are not (three run arbitrary logic); "empty list kinds rejected" holds for `AllowList`/`DenyList` and `TopK("s","r")` still narrows to zero |
| one canonical serialisation | **built**, enforced by a unit test | ✅ accurate |
| ambient boundary | **built and gated**, blind spots disclosed | ✅ accurate — this is the one row where "gated" names the mechanism that actually enforces it |

A row claiming "built and gated" whose gate cannot fire is the failure §0.14 opens by promising not
to repeat. Two of four rows do it, and the word "gated" now means two different things inside one
table.

**Also unstated in §0.14.3.** The section designs the outage record's shape — `scope`, no `tool`,
optional `count` — and argues each choice well. It says nothing about the consumers that already
read the sink, and there is no requirement that a new row-type be admissible to them. That gap is
where the crash lives.

---

## 7 · Judging the tests

| test | red-able by the shape that will occur? | can it pass over the defect it names? |
|---|---|---|
| `test_EVERY_catalogue_path_registers_on_a_real_failure` (parametrised, driven on a raising transport, does **not** pre-arm) | ✅ I11 red | ⚠️ yes — it drives only the transport-exception branch; the admin *"mcp not installed"* branch is unregistered and green |
| `test_ALL_THREE_TURN_SHAPES_reach_the_notice` | ✅ I12 red | ⚠️ yes — `{...} <= users` is a **subset**; I5 (a fourth entry point) stayed green, contradicting the docstring |
| `test_no_narrowing_precedes_the_arming` / `test_both_entry_points_arm_exactly_once` | ✅ I1, I2 red | ⚠️ **yes, four ways** — I3b, I4, I5, I14b all green |
| `test_the_gate_reds_when_a_narrowing_moves_above_the_arming` | it injects into a **list it built itself**, then asserts the comparison. A control on the comparison, not on the gate | it cannot see any of the four bypasses |
| `test_the_armer_actually_arms` | ✅ real function, real `contextvars`, with a negative control | no |
| `test_the_emit_path_ADOPTS_the_armed_sink…` | **source-text** (`"_surface_sink = instrument.surface_withheld.get()" in src`) — the last of the `in src` gates in this area | yes; and it is three lines above the `_sw["tool"]` crash it cannot see |
| `test_the_INGESTION_PATH_composes_the_schema__driven_not_grepped` | ✅ I6, I7 red; drives the real door through a stubbed transport | ⚠️ covers `get_tool_definitions` only |
| `test_ARRIVAL_ENCODING_CANNOT_CHANGE_WHICH_DECLARATIONS_SURVIVE` | ✅ I8 red. Has a **control** (the pre-fix estimator) and asserts the budget actually cut — the best test in this set | no |
| `test_an_identifier_left_verbatim_still_cannot_INFLATE_the_estimate` | ✅ I8 red | ⚠️ it proves the *estimator* is safe and is cited as the reason verbatim identifiers are safe; three prose consumers are not covered |
| `test_identifiers_are_left_VERBATIM…` | asserts on `_nfc_text` output, a fixture it builds | fine — it is a boundary statement, not a gate |
| `test_AN_ARBITRARY_STAGE_OBJECT_IS_REFUSED…`, `test_a_SUBCLASS_of_a_kind_is_refused_too` | ✅ I9 red; drives `assemble` | ⚠️ blind to the metaclass forgery and to `_narrow` |
| `test_THE_OPERAND_IS_BOUNDED_NOT_ONLY_THE_OPERATOR` | ✅ I10 red; four operand shapes incl. a `str` subclass | ⚠️ `Filter.value` only — six other operands, three of them live routes |
| `test_every_kind_is_CONTENT_ADDRESSABLE…` | **cannot fail for the reason it names.** Six hand-picked well-formed instances; the claim it is named after is false for five constructible stages | yes |
| `test_an_EMPTY_list_kind_is_refused…` | ✅ I13 red | ⚠️ `TopK("s","r")` — the identical failure — is not asserted |
| `test_no_stage_kind_DECLARES_a_callable_field` | honestly demoted in its own docstring to "the shape check, kept" | no complaint |
| `test_there_is_exactly_one_CANONICAL_implementation_in_the_package` | narrowed from "no `json.dumps`" to canonicalisation markers, argued in the docstring | ✅ the narrowing is correct and stricter about the thing that matters |

The round's improvement is real: **four of the five `in src` gates are gone**, replaced by driven
tests with controls. The one left (`test_the_emit_path_ADOPTS…`) sits three lines from the crash.

---

## 8 · Where the builder's own documentation of a residual is incomplete or wrong

1. **RUNSTATE, *"One injection stayed green and is recorded rather than hidden: an alias…"* —
   incomplete by three.** I measured I3b (a routine helper extraction — and the defect reproduced
   end-to-end), I4 (a conditional arm), and I5 (a fourth entry point) all green. The same paragraph
   calls the residual *"narrower now, because this list is one place and the old anchor was one call
   site."* The list is one place; the **function-name pin and the file pin** are two more anchors of
   the same kind, and one of them is already violated in the tree.
2. **`TestTheTurnSinkIsArmedBeforeAnythingNarrows`'s docstring, and
   `test_ALL_THREE_TURN_SHAPES_reach_the_notice`'s — *"so a fourth entry point cannot inherit the
   silence by omission"* — is false.** Measured green with a fourth entry point injected; and
   `voice_stream_response` is a fourth entry point that already inherits exactly that silence.
3. **§0.14.1's *"every constructible stage is now content-addressable"* — false**, five
   counter-examples measured, and the test named after the sentence cannot see them.
4. **§0.14.1c rows 1 and 2, *"built and gated"* — the gate named does not contain the check.** Row 2
   is additionally false on its merits.
5. **RUNSTATE's "Still open" list omits four live residuals**: the admin door's missing U-1
   normalisation; the admin door's unregistered "mcp not installed" branch; the six unbounded stage
   operands and `TopK`'s zero default; and the crash — which is not a residual at all but a
   regression the fix introduced.
6. **The one place the disclosure is exemplary:** `ambient.py`'s *"a disclosure of one blind spot is
   not a disclosure of the others"*, with all seven measured shapes covered and each given a
   selftest probe. That is the standard the arm-order gate's disclosure does not meet.

---

## 9 · What would have to be true for this to PASS

* `stream_service.py:6970` and `instrument.py:551` must admit a scope row **without** inventing a
  `tool` value — and a test must drive a real turn through an outage on an agui/resume shape, which
  no test does today.
* The arming property needs an anchor that is not a hand-written function list in one file. The
  cheapest honest version: assert at **runtime** that `record_catalogue_unavailable` /
  `record_surface_withheld` never find `surface_withheld.get() is None` on a request-scoped path —
  the property is *"a narrowing that predates its sink is lost"*, and that is observable where it
  happens, not in a parse tree.
* `voice_stream_response` arms and tells its model.
* The operand bound reaches the other six fields, or `_KIND_SET` membership stops being the only
  thing standing between a pipeline and `__lt__`.

`git rev-parse HEAD` at start: `73241817cb7424069862e9ea2df9db09b8b4e35a`.
`git rev-parse HEAD` before writing: `73241817cb7424069862e9ea2df9db09b8b4e35a`.
