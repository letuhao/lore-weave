# CP-1 · round 11 · V-CODE — Verifier A (the guards around arrival)

*Artifact frozen at `2c63496b4535eb37d0f98296933179984575b5a7`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move.** I wrote
no tracked file other than this one, ran no `git checkout`, and touched nothing live. Every injection
was applied to a **copy of `services/chat-service` in a scratch directory** and reversed by restoring
a pristine snapshot; `git status` on `services/` is clean.*

**Every line marked *measured* was produced by code I executed.** The drives ran the real
`AdvertisedToolsRecorder`, the real `KnowledgeClient.get_tool_definitions` /
`get_admin_tool_definitions` against a stubbed MCP transport, and the real gate helpers
(`_turn_entry_calls`) against the real parse tree.

## Baselines I measured myself

| where | suites | result |
|---|---|---|
| in-tree | `test_cp0_instrument` + `test_stream_service` | **`162 passed`** |
| in-tree | + `test_admin_surface` + `test_knowledge_client` + `test_cp1_membrane` + `test_cp0_merge_db` + `test_voice_router` + `test_voice_billing` | **`410 passed`** |
| scratch copy | `test_cp0_instrument` + `test_stream_service` | **`2 failed, 160 passed`** |
| scratch copy | the wide set, minus `test_cp1_membrane` (21 copy artefacts) | **`2 failed, 299 passed`** |
| scratch copy | `TestTheTurnSinkIsArmedBeforeAnythingNarrows` alone ("the gate") | **`6 passed`** |

The scratch copy's two failures are the same copy artefacts round 10 identified
(`test_the_class_4_metric_no_longer_pins_outcome_to_one_finish_reason`,
`test_the_fingerprint_does_not_hash_a_column_no_class_reads` — both read files outside `app/` and
`tests/`). Every row below reports **extra** failures beyond those two.

---

## 1 · Verdict

| # | guard under test | verdict |
|---|---|---|
| 1 | **sink adoption moved into `__init__`** | **PASS on every live path, by execution — FAIL on the claim.** 54/54 live constructions had the sink already armed. But `_emit_chat_turn` still contains the inversion it was written to remove, and `bind_sink` — measured **green** to delete — is its only repair |
| 2 | **`test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE`** | **FAIL.** It sees **4 of 8** sites, **none** of which is an SQL bind, and **zero** in voice. R10's I13 (the clean finish), R10's I4 (voice) and **this round's own orphan-`UPDATE` fix** are all still green |
| 3 | **`test_NO_ALLOW_LIST_ENTRY_IS_STALE`** | **can fail, and fails for its stated reason — but it is the wrong question.** Nothing checks a `_NOT_A_TURN` member is *not a turn*. A real fourth turn entry point, wrongly exempted: gate `6 passed`, wide set **at baseline** |
| 4 | **the widened gate — find route fifteen** | **FAIL. Seven routes measured green on the gate *and* on the whole wide set**, control reds. Four are R10's, unclosed; three are new. And the fix adds a false-positive class that, if acted on, produces the sixth recurrence |
| 5 | **the admin cache** | **FAIL on every sub-question.** The user door has the identical `[]`-cached shape unfixed; a zero-tool user fetch registers nothing; a cache hit registers nothing; and the admin cache **still has no TTL for a non-empty value**. Plus a **new** defect: a legitimately empty admin catalogue is now reported to the model as an outage |
| 6 | **`absorb`'s unknown-scope branch** | **FAIL. It still crashes on 7 of 19 row shapes**, one of them at the line immediately *above* the branch written to stop crashing — and what it records for the shape its own comment predicts is wrong, not merely present |

**Overall: FAIL.**

What round 11 got right, said plainly. Three real defects are closed and I measured each: the
`__init__` adoption does fire on every live construction (54/54); the `else` branch no longer
`KeyError`s on an unknown *scope*; the `#`-prefixed `_seen` key genuinely separates the two
namespaces; `count or 0` at `_record_scoped` now reds; the admin `[]` is no longer cached, so an
admin turn **does** recover after a zero-tool answer (measured: `dials` went 1 → 2). R10's R5 (the
class-method route) is closed by `ast.walk`, and that was route nine — the one R10 called the sharpest.

Six things turn the verdict, and five of them are the same shape: **a guard was written against the
thing the last verifier pointed at, not against the thing it meant.**

1. **The new terminal-write gate reads the wrong layer.** It matches `withheld_tools=` **keyword
   arguments**. Every actual persistence bind in this tree is **positional** — `stream_service.py`
   lines 6303, 6390, 7424 and `voice_stream_service.py:684`. So the gate sees the four sites that
   *hand the value to a writer* and none of the four that *write it*. Measured green: the clean
   finish binding `None` (R10's I13, "the path every successful turn takes"), voice binding `None`
   (R10's I4), and **the orphan-stamp `UPDATE` that is this round's own headline fix**.
2. **It also reds for the wrong reason.** Binding the value through a *correct* helper reds it
   (J5) while binding `**{'withheld_tools': None}` does not (J6), and its `sites >= 3` floor lets a
   write site be deleted outright with 299 tests green (J7). That is the prompt's exact warning: a
   guard that reds on a correct refactor is a guard that gets deleted.
3. **The allow-list guard checks visibility and calls it correctness.** Measured: a real fourth turn
   entry point that narrows and never arms reds the gate — and the *same* entry point listed in
   `_NOT_A_TURN` with an untrue reason leaves the gate at `6 passed` and the wide set at baseline.
   The only thing that would catch it is a hard-coded three-name subset assertion in a different test.
4. **Seven routes past the gate, all green on 299 tests.** `functools.partial`, a module-level alias
   assigned at import, and a **name collision with an arming function** are new; `getattr`, a
   module-level lambda, a module outside `_TURN_SCOPE`, a subpackage and a sync `def` are R10's,
   unchanged. The `arming` and `reaching` sets are still keyed on the **bare name**, and `ast.walk`
   made that pool much larger — the builder's comment says "Keyed by module now", which is true of
   `by_name`'s values and false of the two sets built from it.
5. **The admin-cache fix reached the `[]` and not the cache.** `if self._admin_tool_definitions:`
   fixes only the falsy value. Measured: a 1-tool catalogue is pinned process-wide while the gateway
   offers 3 — `dials` frozen at 2, no TTL. A *partial* federation is a larger narrowing than an empty
   one and it now looks healthy. The user door was not touched at all: `[]` is still cached for the
   full TTL, a recovered gateway is not re-dialled, and a zero-tool success registers nothing.
6. **And the admin fix introduced the defect U-2's own doctrine forbids by name.** A deployment with
   zero admin tools now registers `stage="catalogue_unavailable"`, so `catalogue_outage_registered()`
   returns **True** and the model is told the catalogue is unavailable when it is merely empty.
   `test_an_EMPTY_catalogue_is_not_an_outage` exists to stop exactly this, and it is green.

---

## 2 · The guard table — *can it fail?* / *does it fail for the reason it names?*

| guard added this round | can it fail? | does it fail for the reason it names? |
|---|---|---|
| `AdvertisedToolsRecorder.__init__` adopts `surface_withheld.get()` (`instrument.py:385`) | **yes** — K1 (`self._sink = None`) reds `test_A_RECORDER_ADOPTS…` | **partly.** The name says *the turn's sink*; the test drives a bare recorder in a `copy_context()`. K4 — adoption removed **and both `bind_sink` calls deleted** — reds only that one unit test. No wiring test exists |
| `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None` | **yes** — J4 (literal `None` at a keyword), J8 (site count 4→2) | **no.** It sees 4 of 8 sites and no SQL bind. Reds on a *correct* helper (J5); silent on a dict spread (J6), on a deleted site (J7), on the clean finish (J1), on voice (J2), on the orphan `UPDATE` (J3) and on the main INSERT (J3b) |
| `test_A_RECORDER_ADOPTS_THE_TURNS_SINK_WITHOUT_ANYONE_REMEMBERING_TO` | **yes** — K1, K4 | **no.** Recorder-only: it proves `__init__` reads the ContextVar, not that a turn's row reaches a column. It is the same shape R10 rejected in `test_THE_ROW_REACHES_THE_COLUMN…` |
| `test_NO_ALLOW_LIST_ENTRY_IS_STALE` | **yes** — adding an undiscovered key reds it | **yes, for *staleness*** — and staleness is not the property that matters. Q3d: a wrongly-classified **discovered** entry is invisible to it, gate `6 passed`, wide set at baseline |
| the gate's `ast.walk` (methods + nested fns) | **yes** — Q3c reds, CONTROL reds | **no, on the shape it was written for.** V1 (a narrowing behind a bare-name decorator) reds naming **`_wrapped`**, a nested helper, with the message *"no `arm_turn_surface()` at all"* — telling the developer to arm a helper that runs **inside** an armed turn, which is the sixth-recurrence discard the same class warns about three assertions above |
| `_narrowing_helpers_multi` (name → \[functions]) | **yes**, transitively | **no.** It over-approximates `reaching` (safe) but `arming` is still a bare-name set built the same way (**unsafe**) — V9: a new unarmed narrowing entry point named `voice_stream_response` in a new module is skipped wholesale, gate `6 passed` |
| `if self._admin_tool_definitions:` (`knowledge_client.py:724`) | **yes** — the `[]` re-dial is real, measured `dials` 1→2 | **partly.** It closes the falsy case; R10's finding was *"no TTL and no invalidation"*. A3: a 1-tool catalogue is still pinned forever |
| `if not tools: _register_catalogue_outage(...)` (`knowledge_client.py:793`) | **yes** | **no — it fires for a reason that is not true.** A4: a legitimately empty admin catalogue registers `catalogue_unavailable` and `catalogue_outage_registered()` → `True` |
| `absorb`'s `else` branch (`instrument.py:596`) | n/a (it is a fix, not an assertion) | **no.** It cannot crash on an unknown *scope* and still crashes on a non-dict row (`:584`), an unhashable `stage` (`:550`) and an unhashable `tool` (`:468`) — and misfiles a new scope that carries a `tool` |
| `key = (f"#{scope}", …)` (`instrument.py:549`) | — | **yes.** Verified by construction: `#` cannot appear in a declaration id, and the per-declaration key at `:468` is unprefixed |
| `count is not None` at `_record_scoped` (`:554`) | **yes** — R10's I9 is closed | **yes** |

---

## 3 · The falsifier, per claim — stated before the search

### 1 · Sink adoption in `__init__` — **PASS on every live path, FAIL on the claim**

**Falsifier (stated first):** any real path on which `AdvertisedToolsRecorder()` is constructed while
`surface_withheld.get() is None` — `_emit_chat_turn`, the resume path, voice, a subagent call, a
background task, a recorder built at import.

**Enumerated from the tree.** There are exactly **two** construction sites:
`stream_service.py:6576` (`_emit_chat_turn`) and `voice_stream_service.py:242`. None at import, none
in a router, none in a background task.

**Measured**, by instrumenting the scratch copy at the construction site and at the defensive re-arm
branch, then running both suites (`2 failed, 160 passed` — baseline, the probe changes nothing):

```
   54x  emit_chat_turn armed_at_construction=True
    0x  emit_chat_turn TOOK-THE-DEFENSIVE-ARM-BRANCH
   55x  RECORDER __init__ adopted=True
   16x  RECORDER __init__ adopted=False        ← recorders built by unit tests outside any turn
```

**Per path:**

| path | arms at | constructs at | ordering | measured |
|---|---|---|---|---|
| `stream_response` → `_emit_chat_turn` | `:5003`, unconditional, first statement | `:6576` | arm first | ✅ 54/54 |
| `resume_stream_response` → `_emit_chat_turn` | `:7749`, before `:8181` | `:6576` (same function) | arm first | ✅ same 54 |
| `voice_stream_response` | `:237` | `:242` | arm first | ✅ structural; no live-turn suite exists for voice |
| `_run_subagent_call` (`:4782–4914`) | — | — | builds **no** recorder and narrows nothing | ✅ inherits the outer one |
| `_stream_with_tools` (`:1702–4779`) | — | — | same | ✅ |
| a recorder at import | — | — | none exist | ✅ |
| `asyncio.create_task` in the cancel/error handlers (`:7574`, `:7667`, `:7671`) | — | — | run after construction; `create_task` copies the context | ✅ |

**And the claim is still false, structurally.** `_emit_chat_turn` reads:

```
6576:    _advertised = instrument.AdvertisedToolsRecorder()   ← adopts surface_withheld.get()
6583:    _surface_sink = instrument.surface_withheld.get()
6584:    if _surface_sink is None:
6585:        _surface_sink = []
6586:        instrument.surface_withheld.set(_surface_sink)   ← the function's OWN arming
6590:    _advertised.bind_sink(_surface_sink)                 ← the repair
```

The recorder is constructed **ten lines before** the only arming this function performs. That branch
is dead today (0 hits in 54 turns) and `bind_sink` is the only thing that would repair it if it ever
became live — and **deleting `bind_sink` is measured green** (K2, K3, wide set at baseline). So the
docstring's *"the DEFAULT is no longer a step that can be skipped"* is true only because a branch
nobody asserts to be dead happens to be dead. `:6586` is also a bare `surface_withheld.set()` — the
construction `arm_turn_surface`'s own docstring names as the sixth recurrence's shape — and the gate's
`raw_sets` check does not reach it because `_emit_chat_turn` is not a discovered entry point.

### 2 · `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE` — **FAIL**

**Falsifier:** any way to stop a persisted column carrying the recorder's value while the test is
green; any site that persists `withheld_tools` the test does not count; any *correct* change that
reds it.

**What it counts, enumerated from the parse tree** — `ast.keyword` with `arg == "withheld_tools"`:

```
stream_service.py       : 6970, 7132, 7592, 7633     (4 sites)
voice_stream_service.py : (none)                     (0 sites)
```

All four are **arguments to `_persist_terminal_assistant`**. Every site that actually persists the
column is **positional** and therefore invisible:

| line | function | what it is | counted? |
|---|---|---|---|
| `stream_service.py:6303` | `_persist_terminal_assistant` | the **orphan-stamp `UPDATE`** — this round's own fix | ❌ |
| `stream_service.py:6390` | `_persist_terminal_assistant` | the main assistant `INSERT` | ❌ |
| `stream_service.py:7424` | `_emit_chat_turn` | **the clean finish** — R10's I13 | ❌ |
| `voice_stream_service.py:684` | `voice_stream_response` | voice's only `INSERT` — R10's I4 | ❌ |

**Measured**, wide set, baseline `2 failed, 299 passed`:

| # | injection | result |
|---|---|---|
| **J1** | `:7424` — the **clean finish** binds `None` (R10's I13) | **GREEN — baseline** |
| **J2** | `voice:684` binds `None` (R10's I4) | **GREEN — baseline** |
| **J3** | `:6303` — **the orphan `UPDATE` added this round** binds `None` | **GREEN — baseline** |
| **J3b** | `:6390` — the main `INSERT` binds `None` | **GREEN — baseline** |
| J4 | a keyword site → literal `None` | **1 extra** — the guard ✅ |
| **J5** | a keyword bound through a **correct** helper (value unchanged) | **1 extra — FALSE POSITIVE** |
| **J6** | `**{'withheld_tools': None}` | **GREEN — baseline** |
| **J7** | delete a keyword site entirely (4 → 3; floor is `>= 3`) | **GREEN — baseline** |
| J8 | delete two (4 → 2) | **1 extra** — on the *count*, not the site |

The test's docstring says *"this reads the parse tree at every site that persists the column"*. It
reads **zero** of them. It closes three of R10's four `None`-binds — the ones that happen to be
keyword arguments — and leaves open the one R10 singled out as decisive, plus the one R11 itself
added, plus voice, which the docstring cites by name as an injection it exists to close.

### 3 · `test_NO_ALLOW_LIST_ENTRY_IS_STALE` — **can fail, fails for its stated reason, wrong question**

**Falsifier:** an entry that is **wrong** — a genuine turn — and still discovered, therefore still
exempted, with the gate green.

`_NOT_A_TURN` is now exactly the five discovered non-turn entries (measured: `stale = []`), and the
three pre-emptive entries R10 flagged were deleted. The guard works for staleness.

**But nothing checks a member is not a turn. Measured:**

| # | injection | gate | wide set |
|---|---|---|---|
| Q3c | a real 4th entry point (`routers/agent_turn.py::run_agent_turn`) that narrows and never arms | **2 failed** ✅ | — |
| **Q3d** | **the same entry point, added to `_NOT_A_TURN`** | **`6 passed`** | **`2 failed, 299 passed` — AT BASELINE** |

The only thing standing between a wrong exemption and silence is
`test_EVERY_DISCOVERED_entry_point_arms_exactly_once_and_unconditionally`'s hard-coded
`{"stream_response", "resume_stream_response", "voice_stream_response"} <= found`. Exempting one of
*those three* reds (Q3b, measured `1 failed`) — but that is a **name list**, which is the construction
this gate was rewritten twice to stop using, and it protects exactly the entry points that already
exist. Anything discovered later — the case the allow-list is *for* — is unprotected.

### 4 · Route fifteen — **FAIL, seven routes**

**Falsifier:** any construction that puts a narrowing above the arming, or a narrowing entry point
with no arming at all, while the gate stays green. Baseline gate `6 passed`; wide set
`2 failed, 299 passed`. Each injection is runtime-safe (`try/except`) so the wide number measures
detection, not my injection.

| # | construction | gate | wide set |
|---|---|---|---|
| — | **CONTROL** — a direct `get_tool_definitions(...)` above the arm | **`1 failed`** ✅ | **1 extra** ✅ |
| V8 | **`getattr(kc, 'get_tool_definitions')`** — R10's R6, unchanged | **`6 passed`** | **baseline** |
| V7 | a **module-level lambda** helper — R10's R7, unchanged | **`6 passed`** | **baseline** |
| V5 | a helper in **`app/turnhelp.py`** — outside `_TURN_SCOPE`; R10's R8, unchanged | **`6 passed`** | **baseline** |
| V6 | a helper in **`app/services/surface/loader.py`** — the glob is `glob`, not `rglob`; R10's R9, unchanged | **`6 passed`** | **baseline** |
| V4 | a **sync `def`** turn entry point — R10's R10, unchanged | **`6 passed`** | — |
| **V3** | **`functools.partial(kc.get_tool_definitions, …)`** — **NEW** | **`6 passed`** | **baseline** |
| **V2** | a **module-level alias assigned at import** (`_V2_FETCH = KnowledgeClient.get_tool_definitions`) — **NEW** | **`6 passed`** | **baseline** |
| **V9** | a new unarmed narrowing entry point **named `voice_stream_response`** in a new module — **NEW** | **`6 passed`** | **baseline** |
| V1 | a narrowing behind a **bare-name decorator** | `2 failed` — **for the wrong reason** | — |

The mechanisms, each a specific line:

* **V2, V3, V8** — the same family: the narrowing name never appears as `node.func` of a `Call`.
  `_called_name` (`:1653–1660`) returns `None` for a `Call` func, and the alias check (`:1806–1810`)
  fires only on an `ast.Assign` **inside the function**, so a module-level alias is invisible.
  `functools.partial` is new to this list and is the most ordinary refactor of the three.
* **V7** — `by_name` collects `ast.FunctionDef` / `ast.AsyncFunctionDef` only (`:1755–1757`).
  `ast.Lambda` is neither.
* **V5** — `_TURN_SCOPE = ("services", "routers")` (`:1650`), unchanged since round 9. R10 wrote
  *"a boundary drawn at a file is a boundary a refactor crosses by accident"*; the boundary is still
  drawn, one level out.
* **V6** — `(base / sub).glob("*.py")` (`:1742`) is still not `rglob`.
* **V4** — `if not isinstance(fn, ast.AsyncFunctionDef): continue` (`:1782`), unchanged.
* **V9 — the new one that matters.** `arming` (`:1763–1778`) is a set of **bare names**, and
  `if fn.name in arming …: continue` (`:1786`) skips *any* function whose name matches. `ast.walk`
  enlarged the name pool from module-level functions to every method, nested function and closure in
  both directories. The builder's comment says *"Keyed by module now, with a name index kept
  separately for the call-graph closure, which can only over-approximate … the safe direction for a
  gate."* Over-approximating `reaching` is the safe direction. Over-approximating `arming` is the
  **unsafe** direction, and it is built the same way in the same commit.

**V1 and the new false-positive class.** V1 does red — and names the wrong function:

```
E  AssertionError: services/stream_service.py::_wrapped: expected exactly one arm_turn_surface(),
   found 0 at []. A second arming DISCARDS everything the first collected; zero means every
   narrowing in this turn registers nowhere.
```

`_wrapped` is the decorator's inner function. It runs *inside* an armed turn. The gate's own message
instructs the reader to add an `arm_turn_surface()` to it — which is the sixth recurrence verbatim,
described correctly in the same sentence that demands it. `stream_response`, the function that
actually narrows before its arm, is not mentioned. `ast.walk` bought discovery of methods (closing
R5, which was real) and paid for it by promoting every nested async helper to a "turn entry point";
none exists in the tree today, so nothing is red now, and the first one to arrive gets this advice.

**That every green route reproduces the defect, measured directly** rather than argued:

```
narrowing BEFORE the arm -> (catalogue_outage_registered(), persisted rows) = (False, None)
entry point that never arms -> surface_withheld.get() = None
```

`record_catalogue_unavailable` returns early on `sink is None` (`instrument.py:330–332`). A narrowing
above the arm registers nowhere and persists nothing. That is the defect, not a style point.

### 5 · The admin cache — **FAIL on every sub-question, plus a new defect**

**Falsifier:** the non-admin cache having the same shape; a successful zero-tool fetch on the user
path registering nothing; any remaining way for a stale catalogue to be pinned.

Driven against the real `KnowledgeClient` with a stubbed MCP transport, inside a real armed turn:

```
ADMIN DOOR
  A1 healthy gateway, ZERO admin tools : result=[] dials=1 registered=['admin catalogue returned zero tools'] outage=True
  A2 gateway recovers (1 tool)         : result=['admin_a'] dials=2   ← the [] fix WORKS
  A3 gateway now offers 3 tools        : result=['admin_a'] dials=2   ← NON-EMPTY value still pinned, no TTL
     admin cache has a TTL             : False

USER DOOR — the same three questions
  U1 healthy gateway, ZERO user tools  : result=[] dials=1 registered=[] outage_registered=False
  U2 gateway recovers, same TTL window : result=[] dials=1 registered=[]
     -> `[]` IS cached on the user door : cache=[]  ttl_remaining=60s
  U3 second turn, cache HIT on `[]`    : result=[] dials=1 registered=[] outage_registered=False

IS A LEGITIMATELY EMPTY ADMIN CATALOGUE NOW AN OUTAGE?
  A4 deployment with zero admin tools  : catalogue_outage_registered() = True
     stage recorded                    = ['catalogue_unavailable']
```

**A3 — the fix reached the value and not the cache.** `if self._admin_tool_definitions:` (`:724`)
re-dials only when the cached value is falsy. `self._admin_tool_definitions = tools` (`:798`) is
still unconditional and there is still **no TTL and no invalidation anywhere in the class**. So a
*partial* federation — 1 of 40 admin tools, a provider still booting — is pinned process-wide
permanently, exactly as `[]` was, and it is **worse**: an empty catalogue is visibly broken; a
one-tool catalogue looks like a healthy small surface. R10's finding was *"no TTL and no
invalidation"*; the fix answered the example.

**U1/U2/U3 — the user door was not touched.** `[]` is cached for the full `_TOOL_CATALOG_TTL_S`
(measured 60 s), a recovered gateway is not re-dialled inside it, a zero-tool success registers
nothing, and a cache **hit** registers nothing at all even when the cached value is `[]`. The
question the prompt asks — *"check the non-admin cache for the same shape, and whether a successful
zero-tool fetch on the user path registers anything"* — answers **same shape** and **nothing**.

**A4 — and the admin registration is a new defect, not a residual.** `if not tools:` at `:793` fires
on a *successful* fetch, so a deployment that legitimately has zero admin tools records
`stage="catalogue_unavailable"`, `catalogue_outage_registered()` returns `True`, and
`stream_service` puts `CATALOGUE_UNAVAILABLE_NOTICE` in the prompt. `test_an_EMPTY_catalogue_is_not_an_outage`
says, in the tree, today, green:

> *"`outage = not catalog` conflates an unavailable catalogue with a legitimately empty one — a user
> with no permissions has zero tools and no outage — which is the exact confusion U-2 exists to end,
> reproduced inside U-2's own fix."*

R11 reproduced it a second time, one door over, and the test does not see it because it drives
`record_surface_withheld` / `record_catalogue_unavailable` directly rather than either catalogue door.
If the intent is that an empty admin catalogue *is* worth recording, it needs its own stage — the
column's whole purpose is that a reader can tell the two apart.

### 6 · `absorb`'s unknown-scope branch — **FAIL**

**Falsifier:** any row shape that crashes `absorb` or the persist boundary; any recorded value that is
present but not readable.

Driven over 19 row shapes against the real recorder. **7 crash.**

| row shape | outcome |
|---|---|
| row is a bare `str` / `None` / `list` / `int` | **`AttributeError` at `instrument.py:584`** — `scope = row.get("scope")` |
| `stage` is a `dict` or `list` (unhashable) | **`TypeError: unhashable type` at `instrument.py:550`** — `if key in self._seen` |
| the same, with `scope == "catalogue"` | **`TypeError` at `:550`** — the catalogue branch reaches it too |
| `tool` is unhashable | **`TypeError` at `instrument.py:468`** — `key = (tool, stage, len(self._passes))` |
| `reason` is a non-JSON object, on the **catalogue** / **pass** / **declaration** branch | absorbs fine, then **`TypeError: not JSON serializable`** at the `json.dumps` write site |
| `count` is a non-JSON object | same |
| `scope` is an `int` / `list` / `dict`; empty dict; missing `stage`/`reason` | ✅ handled |

`:584` is **one line above** the branch whose comment says *"the branch stops trusting the shape"*.
The branch stopped trusting `row["tool"]` and the line that reads `row` at all was left as it was —
which is the same *fix-what-was-pointed-at* shape as findings 1–5 above, inside the function the
prompt calls out as having recreated its own crash once already. The four persist-boundary crashes
are worse than the P0 was, because they fire at the `json.dumps` in the terminal write path, after
the turn has produced its answer.

**And what it records is wrong, not merely present.** `elif row.get("tool")` is tested **before** the
`else`, so a genuinely new scope that also carries a tool — the shape the comment predicts, since
both existing per-declaration scopes carry one — is misfiled and the new scope is **silently
discarded**:

```
in : {"scope": "declaration_group", "tool": "book_get", "stage": "budget", "reason": "over"}
out: {"scope": "declaration",       "tool": "book_get", "stage": "budget", "reason": "over"}   ← scope LOST

in : {"scope": None, "tool": "book_get", ...}
out: {"scope": "declaration", ...}                                                             ← scope FABRICATED
```

Only a row with **no** `tool` reaches the else and is recorded honestly:

```
in : {"scope": "declaration_group", "stage": "budget", "reason": "over"}
out: {"scope": "declaration_group", "stage": "budget",
      "reason": "over (unrecognised scope 'declaration_group'; recorded rather than dropped)"}   ✅
```

So *"an unrecognised row is recorded as an unrecognised row"* holds for the subset of unrecognised
rows that carry no tool. For the rest, the recorder writes a `scope` the sink never said — which is
the fabricated-by-default shape `count is not None` exists three methods away to prevent.

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? |
|---|---|---|
| U-2 · the recorder's value reaches `withheld_tools` | `:7424` — **the clean finish** binds `None` (R10's I13) | ✅ wide set at baseline |
| " | `voice:684` binds `None` (R10's I4) | ✅ baseline |
| " | `:6303` — **this round's own orphan-`UPDATE` fix** binds `None` | ✅ baseline |
| " | `:6390` — the main `INSERT` binds `None` | ✅ baseline |
| " | `**{'withheld_tools': None}` — a `**` keyword has `arg is None` | ✅ baseline |
| " | delete a write site (`sites >= 3` allows 4 → 3) | ✅ baseline |
| the recorder adopts the turn's sink | `_emit_chat_turn:6576` constructs before `:6586` arms; `bind_sink:6590` deletable | ✅ K2/K3 baseline; branch measured dead (0/54) |
| `_NOT_A_TURN` entries are trustworthy | a **discovered** entry with an untrue reason | ✅ Q3d: gate `6 passed`, wide set at baseline |
| arm gate · no narrowing precedes the arming | **`functools.partial`** | ✅ gate `6 passed`, wide baseline |
| " | a **module-level alias** assigned at import | ✅ gate `6 passed`, wide baseline |
| " | a new entry point **named like an arming function** | ✅ gate `6 passed`, wide baseline |
| " | `getattr`, a **lambda**, a module **outside `_TURN_SCOPE`**, a **subpackage**, a **sync `def`** | ✅ all five, gate `6 passed` |
| the admin catalogue cannot be pinned stale | a **non-empty** stale value — no TTL, never invalidated | ✅ 1 tool pinned while the gateway offers 3 |
| every catalogue path registers | the **user** door: a successful zero-tool fetch, and every cache hit | ✅ `registered=[]`, `outage=False` |
| an empty catalogue is **not** an outage | the admin door now records one | ✅ A4 — `catalogue_outage_registered()` → `True` |
| `absorb` cannot crash | a non-dict row; an unhashable `stage`; an unhashable `tool` | ✅ `:584`, `:550`, `:468` |
| " | a non-JSON `reason`/`count` — crashes at the write boundary instead | ✅ 4 shapes |
| `absorb` records rather than drops | an unrecognised scope **carrying a tool** — scope silently discarded | ✅ |
| the two `_seen` namespaces cannot meet | none found — `#` cannot appear in a declaration id | — |
| `count` absent ≠ zero, recorder side | none found — R10's I9 now reds | — |
| the `[]` admin cache recovers | none found — `dials` 1 → 2, measured | — |

---

## 5 · The red-ability table

Baseline for every row: **scratch copy, wide set = `2 failed, 299 passed`**, both failures copy
artefacts. Gate rows use `TestTheTurnSinkIsArmedBeforeAnythingNarrows` alone, baseline **`6 passed`**.
Two-suite scratch baseline `2 failed, 160 passed`; in-tree `162 passed` / `410 passed`. Every
injection applied to the scratch copy and reversed by restoring a pristine snapshot — never
`git checkout`. "extra" counts failures **beyond** the two artefacts.

| # | injection | what it models | result |
|---|---|---|---|
| **J1** | `:7424` clean finish binds `None` | **R10's I13 — the path every successful turn takes** | **GREEN — baseline** |
| **J2** | `voice:684` binds `None` | R10's I4, cited by name in the new guard's docstring | **GREEN — baseline** |
| **J3** | `:6303` orphan `UPDATE` binds `None` | **round 11's own headline fix** | **GREEN — baseline** |
| **J3b** | `:6390` main `INSERT` binds `None` | the other half of `_persist_terminal_assistant` | **GREEN — baseline** |
| J4 | a keyword site → literal `None` | the guard's stated purpose | **1 extra** ✅ |
| **J5** | a keyword bound through a **correct** helper | a routine refactor | **1 extra — FALSE POSITIVE** |
| **J6** | `**{'withheld_tools': None}` | a `**`-spread bind | **GREEN — baseline** |
| **J7** | delete one keyword site (4 → 3) | a write site loses the column | **GREEN — baseline** |
| J8 | delete two (4 → 2) | the `sites >= 3` floor | **1 extra** — on the count |
| K1 | `__init__` stops adopting | **round 11's headline fix** | **1 extra** — `test_A_RECORDER_ADOPTS…` ✅ |
| **K2** | delete `bind_sink` in `_emit_chat_turn` | R10's I2 | **GREEN — baseline** (now harmless *on the live path*) |
| **K3** | delete `bind_sink` in voice | R10's I3 | **GREEN — baseline** |
| **K4** | **no adoption AND no `bind_sink` anywhere** | the fix and its predecessor both gone | **1 extra** — the recorder unit test only; no wiring test reds |
| Q3c | a real 4th turn entry that narrows and never arms | discovery | **2 extra** ✅ |
| **Q3d** | **the same entry, wrongly exempted** | an untrue `_NOT_A_TURN` reason | **gate `6 passed`, wide set AT BASELINE** |
| Q3b | `voice_stream_response` wrongly exempted | one of the three named turns | **1 extra** — via the hard-coded name list |
| CONTROL | a direct narrowing above the arm | the gate's subject | **gate `1 failed`, 1 extra** ✅ |
| **V2** | module-level alias assigned at import | **NEW** | **gate `6 passed`, wide baseline** |
| **V3** | `functools.partial` | **NEW** | **gate `6 passed`, wide baseline** |
| **V9** | new entry named like an arming function | **NEW** | **gate `6 passed`, wide baseline** |
| V4–V8 | sync `def`, `getattr`, lambda, outside-module, subpackage | R10's R6–R10, **unchanged** | **gate `6 passed`** each |
| V1 | narrowing behind a bare-name decorator | a decorator refactor | **2 extra — names `_wrapped`, not the caller** |

**J1, J2, J3 and Q3d are the block that decides this round.** K1 shows the `__init__` adoption is
guarded. J1 and J3 together show that the connection between that recorder and the database still is
not — including the connection this round built — and Q3d shows the new allow-list guard cannot
distinguish an exemption that is stale from one that is false. R10's sentence about the *tests* rather
than the code is still true of four of the eight sites.

---

## 6 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| adoption moved into `__init__` | every construction site, and whether the sink is armed first | AST-enumerated both sites; probed 54 live constructions + the defensive branch | **YES on every live path** |
| " | the construction order **inside** `_emit_chat_turn` | read `:6576–6590`; probed the defensive branch | **NO** — construction precedes the function's own arm; `bind_sink` deletable, green |
| " | a test that would notice the *wiring* going | K2, K3, K4 | **NO** — only the recorder unit test reds |
| the terminal-write gate | **every** site that persists the column, not just keyword ones | AST-enumerated `ast.keyword` **and** every textual occurrence in both modules | **NO** — 4 of 8; zero in voice; no SQL bind |
| " | whether the round's own new write is covered | J3 | **NO** — the orphan `UPDATE` is positional |
| " | whether a correct refactor reds it | J5, J6, J7 | **NO** — reds on a correct helper, silent on a spread and on a deletion |
| `_NOT_A_TURN` staleness | whether an entry can be **wrong** rather than stale | Q3b, Q3c, Q3d | **NO** — a discovered-but-false exemption is invisible |
| the gate's `ast.walk` | the other five bypasses R10 measured | V4–V8, control | **NO** — all five unchanged, all green |
| " | the constructions R10 did not try | V1, V2, V3, V9 | **NO** — three new routes green; V1 reds naming the wrong function |
| " | whether `arming` got the same treatment as `reaching` | read `:1763–1786`; drove V9 | **NO** — still a bare-name set, and the name pool grew |
| the admin `[]` cache | the **non-empty** stale value in the same cache | drove A1→A3 across a gateway that grew | **NO** — still no TTL, still pinned |
| " | the **user** door, same shape | drove U1→U3 | **NO** — `[]` cached for the TTL, nothing registered, cache hits silent |
| the zero-tool admin registration | whether an empty catalogue is an outage | drove A4 against `catalogue_outage_registered()` | **NO — and it contradicts a green test by name** |
| `absorb`'s `else` branch | every other row shape | drove 19 shapes + the persist boundary | **NO** — 7 crash, 3 in `absorb`, 4 at `json.dumps` |
| " | whether the recorded row is readable | drove a new scope with and without a `tool` | **NO** — with a `tool` the scope is discarded and `declaration` is fabricated |
| `#`-prefixed `_seen` key | the per-declaration key at `:468` | read both; `#` is not a legal id character | **YES** |
| `count is not None` at `_record_scoped` | R10's I9 | injection | **YES** |

---

## 7 · Where the builder's documentation of a residual is incomplete or wrong

1. **`test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE`'s docstring states a property the test does
   not have.** *"So this reads the parse tree at every site that persists the column"* — it reads
   none of them; all four persistence binds are positional. The docstring lists voice's `bind_sink`
   and the four `None`-binds as the injections it exists to close, and measured, three of the six are
   still green, including voice, which the test iterates and finds nothing in. This is the same
   relationship round 10 identified in `test_THE_ROW_REACHES_THE_COLUMN…`, and that one **retracted
   its own claim in place** — the form this one should take.
2. **`AdvertisedToolsRecorder.__init__`'s comment says the default *"is no longer a step that can be
   skipped."*** It is, in the one function that constructs it: `_emit_chat_turn` builds the recorder
   at `:6576` and arms at `:6586`. The claim holds only because that branch never fires today, and
   nothing asserts that.
3. **`_narrowing_helpers_multi`'s docstring names over-approximation as *"the safe direction for a
   gate."*** True for `reaching`, false for `arming`, which is built the same way twenty lines below
   and where over-approximating **removes** scrutiny. V9 is that sentence, measured.
4. **`_turn_entry_calls`'s new comment claims the key problem is fixed** — *"Keyed by module now"*.
   `by_name` is keyed by name with a list of functions; `reaching` and `arming` are still sets of bare
   names. The `_jsonb`/`_sse` collision R10 found is genuinely closed for `reaching`; the same
   collision in `arming` is now a bypass rather than a loss.
5. **`get_admin_tool_definitions`'s new comment says *"An empty catalogue is not a cacheable answer
   here."*** Correct — and the fix at `:724` only stops the *falsy* value being served from cache. The
   sentence three lines up, *"This cache is process-wide, has no TTL and no invalidation"*, is still
   true after the fix, for every non-empty value.
6. **The `if not tools:` registration has no comment about the case where zero tools is the truth.**
   Its comment says *"A successful fetch that returned nothing IS a whole-catalogue narrowing for this
   turn"* — but the tree's own doctrine, in a green test, is that an empty catalogue is not an outage,
   and the row it writes is `stage="catalogue_unavailable"`, which is what `catalogue_outage_registered()`
   reads to put the notice in the prompt.
7. **`absorb`'s new comment says *"an unrecognised row is recorded as an unrecognised row."*** It is,
   unless it carries a `tool` — in which case it is recorded as a `declaration`, with the unrecognised
   scope discarded. And the sentence *"Losing it would be worse than a crash was"* is written directly
   below three lines that still crash on a shape that is not a `dict` and on a `stage` that is not
   hashable.
8. **Exemplary, and worth naming.** The `#`-prefixed `_seen` key is the cleanest fix in this round:
   the invariant that makes it work (`#` cannot appear in a declaration id) is stated, is true, and is
   checkable without running anything. The `[]`-admin-cache recovery is real and I measured it. And
   `test_NO_ALLOW_LIST_ENTRY_IS_STALE` deleting three exemptions rather than documenting them is the
   right response to R10's finding — it is only the *next* question it does not ask.

---

## 8 · What would have to be true for this to PASS

* **The terminal-write gate must anchor on the SQL, not on the call.** The four binds that persist the
  column are positional; a gate over `ast.keyword` cannot see them and will not see the fifth. The
  cheapest honest version asserts, over each `execute`/`fetchval`/`fetchrow` whose SQL text names
  `withheld_tools`, that some argument expression contains `withheld_json()` — that shape reds J1, J2,
  J3 and J3b, and does not red J5.
* **`_emit_chat_turn` must construct the recorder after the sink exists**, or the defensive branch at
  `:6584–6586` must be deleted and the precondition asserted. As it stands the fix's own claim depends
  on a dead branch.
* **`_NOT_A_TURN` needs a check that an entry is not a turn**, not only that it is visible. The
  discovered facts are already in hand — an exempted entry that *arms* is a contradiction; an exempted
  entry reached from a discovered turn entry point is another. Either would red Q3d.
* **The arm-order gate needs an anchor that is not a parse tree.** Round 8 proposed it, rounds 9 and 10
  repeated it, and it is still right: assert at **runtime**, on a request-scoped path, that
  `record_catalogue_unavailable` / `record_surface_withheld` never find `surface_withheld.get() is
  None`. Every one of V2–V9 is invisible to any syntactic gate and visible to that one. Ten routes
  have now been measured green across three rounds; the eleventh is cheaper to build than to find.
* **`arming` must be keyed by module**, like `by_name`'s values, or V9 is a rename away.
* **The admin catalogue needs a TTL for every value, and the user door needs the same audit** — an
  empty *or* shrunken catalogue served from cache is the largest narrowing this system performs, and
  on the user door it is still recorded as nothing.
* **A legitimately empty catalogue must not be recorded as `catalogue_unavailable`**, on either door,
  or `test_an_EMPTY_catalogue_is_not_an_outage` must be retracted and §0.14.3 amended to say the two
  are the same fact. They are not, and that test says so.
* **`absorb` must validate the row before reading it** — `isinstance(row, dict)` and plain-`str`
  `stage`/`reason`/`tool`, exactly as `surface.rows_of` was taught to do for declarations in this same
  commit. The rule was written on one side of the package and not the other.

`git rev-parse HEAD` at start: `2c63496b4535eb37d0f98296933179984575b5a7`.
`git rev-parse HEAD` before writing: `2c63496b4535eb37d0f98296933179984575b5a7`.
