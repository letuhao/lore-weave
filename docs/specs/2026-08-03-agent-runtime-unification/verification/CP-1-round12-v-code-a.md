# CP-1 · round 12 · V-CODE — Verifier A (ordering, arrival, and the guards)

*Artifact frozen at `9c8df7800af7a297ea8fe758ded20714f70ad611`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move.** I wrote
no tracked file other than this one, ran no `git checkout`, and touched nothing live. Every injection
was applied to a **copy of `services/chat-service` in a scratch directory** and reversed by restoring
a pristine snapshot; `git status services/` is clean.*

**Every line marked *measured* was produced by code I executed.** Every injection was verified to
have taken effect before any conclusion was drawn from a green run — by a source-content assertion
for the AST gates (which read source, so source *is* their input) and, for `C-B`, by driving the
real `KnowledgeClient` under the injection and watching the behaviour regress while the suite
stayed at baseline. `R16` carries a **matched control**: the same file with one line removed reds
the gate twice, which proves the negative was a real negative and not an unparsed file.

## Baselines I measured myself

| where | suites | result |
|---|---|---|
| in-tree | `test_cp0_instrument` + `test_stream_service` | **`180 passed`** |
| in-tree | + `test_admin_surface` + `test_knowledge_client` + `test_cp1_membrane` + `test_cp0_merge_db` + `test_voice_router` + `test_voice_billing` | **`428 passed`** |
| scratch copy | the wide set **minus** `test_cp1_membrane` (7 suites) | **`2 failed, 317 passed`** |
| scratch copy | `test_cp0_instrument` alone | **`2 failed, 108 passed`** |
| scratch copy | `TestTheTurnSinkIsArmedBeforeAnythingNarrows` ("the gate") | **`6 passed`** |
| scratch copy | `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE` alone | **`1 passed`** |

The scratch copy's two failures are the copy artefacts rounds 10 and 11 identified
(`test_the_class_4_metric_no_longer_pins_outcome_to_one_finish_reason`,
`test_the_fingerprint_does_not_hash_a_column_no_class_reads`). `test_cp1_membrane` contributes 21
further copy artefacts and is excluded from the wide set, as in R11. Every row below reports **extra**
failures beyond the two.

---

## 1 · Verdict

| # | claim under test | verdict |
|---|---|---|
| 1 | **ordering is no longer load-bearing** (`_sink_for_record`) | **FAIL.** It fixes *"an entry point that arms nowhere"*. **Every one of the eight routes it names is a narrowing ABOVE an arm, and `arm_turn_surface` still replaces** — measured: `outage=False, rows=None`, unchanged from before the fix. And it creates a **new** state the old code could not: a turn whose column carries the outage row while `catalogue_outage_registered()` returns `False` |
| 2 | **`absorb` is total over row shapes** | **FAIL. 6 shapes still crash**, and the mechanism is the one the fix names: `_as_text` returns `str` **subclasses** unchanged, so an unhashable `stage`/`tool` still blows up the dedupe key at `instrument.py:596` / `:515` — the exact two crashes its own comment claims to have closed. Plus a `dict` subclass whose `.get` raises, and the sink container itself is unvalidated |
| 3 | **the terminal-write gate matches SQL naming the column** | **REAL IMPROVEMENT, still FAIL.** It now sees all three SQL-writing functions and closes R10's I4 (voice). But it is **function-granular** with an `any Name containing "withheld"` escape hatch: `_withheld_json = None` (killing the main INSERT **and** the orphan UPDATE) and the clean finish binding `None` are both **green at baseline**. And it reds on a correct refactor, naming a cause that is not true |
| 4 | **the stale-exemption gate and the whole-tree sweep** | **FAIL. Route sixteen found**, with a matched control: a router that narrows and then **delegates** to an armed entry point is exempted wholesale — not merely unflagged, **not discovered at all**. The gate is byte-identical to R11, so its seven open routes are open by construction (V3 re-measured green). And one `_NOT_A_TURN` reason is now **wrong**, not stale — made untrue by this round's own change |
| 5 | **the empty-vs-outage revert** | **PASS on the revert, FAIL on the cache half it was tangled with.** Empty registers nothing on **both** doors ✅ and is guarded ✅. `[]`-not-cached is real on the **admin** door (measured `dials` 1→2) — and **has no test at all**: re-caching `[]` regresses the door to permanently pinned and leaves the suite at baseline. The **user** door still caches `[]` for the full 60 s and does not re-dial a recovered gateway |

**Overall: FAIL.**

What round 12 got right, said plainly, because it is a lot. The empty-catalogue revert is correct,
complete on both doors, and **guarded by a test that reds for the reason it names** — the first time
in this run's record that a founding-confusion recurrence has been closed *and* fenced in the same
commit. The terminal-write gate genuinely moved from a call shape to the SQL: it now sees the three
functions that write the column, and R10's I4 — voice binding `None`, green for two rounds — reds.
`absorb`'s branch order, its non-dict guard and `withheld_json`'s `not w.get("tool")` are each real
fixes with a test that reds for its stated reason (A-A, A-C, A-D). Five of the ten fixes in my scope
are properly closed.

Three things turn the verdict, and the first is the round's headline.

1. **The fix for the ordering class does not fix the ordering class.** Its own docstring lists the
   eight routes: *"a helper one module over, two levels of helper, a `_`-prefixed entry point, a
   class method, `getattr`, `functools.partial`, a module-level alias, a name collision."* Every one
   of those is a construction that puts a **narrowing above the arm**. `_sink_for_record` opens a
   sink for that narrowing; `arm_turn_surface` then **replaces it**, by design, asserted by a test
   added in the same commit. Measured, driving the real functions:

   ```
   narrow, then arm (the eight routes' shape) -> outage=False  rows=None      ← LOST, as before
   arm, then narrow (the control)             -> outage=True   rows=2 rows    ← fine, as before
   ```

   The class that is fixed is the one nobody measured: an entry point that **never arms at all**.
   That is one of the eight (V9). The other seven are untouched, and the docstring's *"every one of
   them is now harmless"* is false for seven of the eight it enumerates.

2. **And it introduces a state the old code could not reach.** With the recorder constructed before
   the arm — which is `_emit_chat_turn`'s literal order, `:6576` before `:6586` — the recorder adopts
   the auto-armed sink, the arm replaces the ContextVar, and the two halves of the same turn
   disagree:

   ```
   rows persisted to withheld_tools : [{scope: catalogue, stage: catalogue_unavailable, ...}]
   catalogue_outage_registered()    : False   ← the model is NOT told
   ```

   The column says there was an outage; the prompt says there was none. Before this round, that path
   produced nothing and told nobody — wrong, but *consistent*, and §0.14.3's whole argument for a
   `scope` column is that a reader must be able to trust one fact against another. A row that
   contradicts the notice built from the same sink is a worse failure than the silence it replaced.

3. **The `[]`-not-cached fix — the thing this round's revert points at as "the real finding" — has no
   test.** `get_admin_tool_definitions`'s new comment reads: *"The real finding it was reaching for is
   the CACHE, and that is fixed above."* I changed `if self._admin_tool_definitions:` to
   `is not None:`, **verified the regression live** (the door returns `[]` forever, `dials` frozen at
   1 while the gateway grows to three tools), and the suite is at baseline — `2 failed, 212 passed`.
   The round's justification for deleting a registration rests on a behaviour nothing asserts. Per
   this round's own rule, that is not a closed finding.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every fix in the delta that falls in my scope (`instrument.py`, `knowledge_client.py`, and the tests
that guard them). `manifest.py` is Verifier B's.

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| `_sink_for_record` auto-arms (`instrument.py:287`) | **yes** — `test_A_NARROWING_BEFORE_ANY_ARMING_IS_STILL_RECORDED`, `test_the_armer_actually_arms` | **yes** — O-A (restore the no-op) and O-C (don't publish the sink) each red **2 extra** | **NO.** Both tests drive *"arms nowhere"*. The reason the fix names is *"eight measured routes past the ordering gate"*, and **seven of those eight are narrow-**then**-arm, which is still lost** (S1, measured) |
| `_sink_for_record` deliberately ≠ `arm_turn_surface` | **yes**, transitively | **yes** — O-B2 (arm unconditionally) reds **14 extra** | **yes.** The discard it warns about is well fenced |
| `absorb`: `isinstance(row, dict)` guard (`:632`) | **yes** — `test_ABSORB_IS_TOTAL…` params `"not a dict"`, `None`, `42` | **yes** — A-A reds **3 extra** | **yes** |
| `absorb`: `_as_text` coercion (`:265`, `:641–645`) | **yes** — `test_ABSORB_IS_TOTAL…` rows 8/9 | **yes** — A-B reds **2 extra** | **NO.** The test's name asserts *"no row shape can kill the turn or the write"*, and **6 shapes still do** — because `_as_text` short-circuits on `isinstance(value, str)` and a `str` subclass is a `str` |
| `absorb`: scope dispatched **before** tool (`:647–655`) | **yes** — `test_a_FUTURE_scope_carrying_a_tool_keeps_its_scope` | **yes** — A-C reds **1 extra** | **yes** |
| `withheld_json`: `if not w.get("tool")` replaces the scope list (`:759`) | **yes**, transitively via the parametrised absorb test | **yes** — A-D reds **10 extra** | **yes** |
| admin door: the outage registration **removed** (`knowledge_client.py:793`) | **yes** — `test_AN_EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE__AT_THE_CALLER_TOO` | **yes** — C-A (re-add it) reds **1 extra** | **yes.** Drives the real client through a stubbed transport inside a real armed turn, and asserts `catalogue_outage_registered() is False` — the property, at the layer where the defect was |
| admin door: `[]` is not a cacheable answer (`:724`) — **the revert's stated justification** | **NO** | — | — **C-B, verified live: the door regresses to `[]` pinned forever and the suite is AT BASELINE.** A "no" in column one |
| `test_EVERY_TERMINAL_WRITE…` rewritten to match SQL | it **is** the test | **yes** — G3 (voice binds `None`) reds ✅; G6 (delete a writer) reds | **partly.** It closes voice — a real gain. It is **green** on `_withheld_json = None` (both binds in `_persist_terminal_assistant`) and on the clean finish. And G5 — a *correct* parameterisation of the column name — reds with *"the column lost a writer"*, which is not true |
| `test_the_armer_actually_arms` inverted to assert the new property | n/a (an assertion, not a fix) | yes (O-A, O-C) | yes, for what it asserts |

---

## 3 · The falsifier, per claim — stated before the search

### 1 · Ordering is no longer load-bearing — **FAIL**

**Falsifier (stated first):** any narrowing that still fails to reach the column despite the
auto-arm; any record landing in a *different* turn's sink; any live ordering where the replacement
discards rows a caller needed; anything draining a sink that was never a turn's.

**S1 — the eight routes are narrow-then-arm, and narrow-then-arm is still lost.** Driven against the
real `instrument` module in a fresh `copy_context()`:

| # | construction | measured |
|---|---|---|
| **S1** | narrow ×2, **then** `arm_turn_surface()`, then build the recorder | **`outage=False, rows=None`** — both narrowings discarded |
| **S1b** | narrow, build the recorder, **then** `arm_turn_surface()` (`_emit_chat_turn`'s order) | **`outage=False`, rows = the catalogue row** — the two halves disagree |
| S1c | CONTROL — `arm_turn_surface()` first, then narrow ×2 | `outage=True`, rows = both ✅ |

`arm_turn_surface` is `sink = []; surface_withheld.set(sink)` (`instrument.py:305–307`) —
unconditional replacement. `test_arming_still_REPLACES_the_sink_so_a_turn_starts_clean`, added this
round, **asserts that replacement as a feature**, and is correct to: a turn must start clean. The
consequence nobody drew is that the auto-arm therefore cannot rescue anything that happens *before*
the arm, which is what all eight bypass routes are. The one route it does close — an entry point
that never arms at all — is V9, one of eight.

**S1b is a new defect.** `catalogue_outage_registered()` (`:389–393`) reads
`surface_withheld.get()` — the *current* ContextVar, i.e. the fresh armed list — while the recorder
holds the orphaned one it adopted at `__init__`. So the row reaches `withheld_tools` and
`CATALOGUE_UNAVAILABLE_NOTICE` never reaches the prompt. §0.14.3's argument for a scoped record is
that a reader can tell two facts apart; here the same sink produces two contradictory answers in one
turn, and no test drives the recorder and the notice together.

**Live paths are safe today, and I checked rather than assumed.** All three arms are the first
statement of their entry point (`stream_service.py:5003`, `:7749`, `voice_stream_service.py:237`),
and the six narrowing call sites (`stream_service.py:1401`/`:1413`, `tool_discovery.py:499`,
`tool_surface.py:266`/`:427`, and `knowledge_client.py`'s six) are all reached from inside them. The
finding is that the fix does not do what it claims for the class it names, not that a live turn is
losing rows today.

**A record in the wrong turn's sink — two mechanisms, both measured, both latent.**

```
S2  base-context record (a startup probe / a non-task caller) pins a shared list:
      base sink after the record : [{tool: LEAKED_FROM_TURN_0, ...}]
      turn 1 (copy_context) then persists : ['LEAKED_FROM_TURN_0', 'turn_1_tool']
S4  a POOLED worker thread has no context copy, so the sink outlives the request:
      req_A -> ['req_A']        req_B -> ['req_A', 'req_B']
```

`copy_context()` copies the *binding*, not the list, so an ambient sink is the **same object** in
every later task and `sink.append` in one crosses into the next. The docstring's *"this allocates
one list that nothing drains and the context discards"* is true only for a caller that copies its
context. `asyncio.create_task` does; a bare `run_in_executor` thread does not, and a thread's
top-level context lives as long as the thread. Neither is on a live path today —
`run_in_executor` appears only in `app/storage/minio_client.py`, which narrows nothing — but the
sentence in the docstring states it unconditionally, and it is the sentence that makes the "cost of
nothing" argument.

**Does anything drain a sink that was never a turn's?** Structurally yes — a recorder constructed in
any context where a background narrowing auto-armed adopts and drains it (S3, measured: `adopted=True`,
one row). Not on a live construction site: both `AdvertisedToolsRecorder()` sites sit inside armed
turns. The live version of this is the **converse**, and it is R16 below: the turn's *first* rows
land in a sink the turn then throws away.

### 2 · `absorb` is total over row shapes — **FAIL**

**Falsifier:** any row shape, or any sink shape, that crashes `absorb`, `withheld_json` or the
`json.dumps` at the write boundary; any value recorded that is not what the sink said.

Driven over 15 shapes the parametrised test does not carry. **6 crash.**

| shape | outcome |
|---|---|
| `stage` is a **`str` subclass with `__hash__ = None`** | **`TypeError: unhashable type` @ `instrument.py:596`** |
| `tool` is the same | **`TypeError` @ `instrument.py:515`** |
| `stage` is a `str` subclass whose `__hash__` **raises** | **`RuntimeError` @ `:596`** |
| `stage` is an object whose `__str__` **returns a `str` subclass** with no hash | **`TypeError` @ `:596`** |
| the row is a **`dict` subclass whose `.get` raises** | **`RuntimeError` @ `:641`** |
| the **sink** is a tuple / generator / str / dict | `AttributeError` / `KeyError` @ `:630` |
| `scope` is a `str` subclass with no hash; `__len__` liar; recursive dict; deep nesting; non-string keys; `bytes`; `MappingProxyType`; `__str__` that raises; `count` as a bool or an `int` subclass | ✅ handled |

**The mechanism is the one the fix names.** `_as_text` (`:265–279`) opens with
`if isinstance(value, str): return value` — and `isinstance(EvilStr("s"), str)` is `True`, so a
`str` **subclass** is returned uncoerced and reaches `key = (f"#{scope}", stage, len(self._passes))`
at `:596` and `key = (tool, stage, len(self._passes))` at `:515`. Those are, verbatim, *"an
unhashable `stage` blew up the dedupe `set`, an unhashable `tool` blew up the other one"* — the two
crashes the comment three lines above says it closed. The `try: return str(value)` fallback has the
same hole: `str(x)` returns whatever `x.__str__` returned, subclass and all. `str(value)` applied
unconditionally — which *does* normalise a subclass to `str` — is the one-line version of the
property claimed.

**`isinstance(row, dict)` checks the type and then trusts the behaviour.** A `dict` subclass whose
`.get` raises passes the guard and crashes at `:641`. That is the prompt's "a `dict` subclass",
and it is the same shape as the `str`-subclass hole: a check on the nominal type standing in for a
check on what the value will do.

**The sink container is unvalidated.** `absorb` coerces every *row* and trusts the *list*: `while
sink: row = sink.pop(0)` (`:630`). A generator, a tuple or a string reaches `withheld_json()` and
raises on the terminal path. The comment says *"the sink is a plain list any code in the request can
append to, so its contents are input"* — the container is input for the same reason, and
`bind_sink(sink: list | None)` is a type hint, not a check. Low reachability; identical class, one
level up.

**And `count` admits a bool.** `isinstance(row.get("count"), int)` is `True` for `True` and `False`,
so `{"count": False}` persists `"count": false` into the jsonb. `count is not None` exists at `:604`
precisely because *absent is not zero*; `false` is a third thing that is neither, written by the
guard that was added to stop exactly this.

### 3 · The terminal-write gate — **improved, still FAIL**

**Falsifier:** any way to stop a persisted column carrying the recorder's value while the gate is
green; any *correct* change that reds it.

**What it sees now**, enumerated from the real parse tree with the gate's own predicate:

```
stream_service.py::_persist_terminal_assistant   names=['_withheld_json','withheld_tools']  calls=[]
stream_service.py::_emit_chat_turn               names=[]                calls=['absorb','withheld_json']
voice_stream_service.py::voice_stream_response   names=[]                calls=['withheld_json']
```

Three functions — which is exactly the `>= 3` floor. That is a genuine advance on R11's four
keyword sites, none of which was a bind. But the offender test is **per function**, and its second
disjunct is `any ast.Name whose id contains "withheld"` — so **one surviving identifier absolves the
whole function**.

Baseline: gate alone `1 passed`; wide set `2 failed, 317 passed`.

| # | injection | gate | wide |
|---|---|---|---|
| **G1** | `_withheld_json = None` at `:6341` — **both** the main `INSERT` (`:6390`) and the **orphan `UPDATE`** (`:6303`) now persist NULL | **`1 passed` — GREEN** | **baseline** |
| **G2** | `:7424` — **the clean finish** binds `None` (R10's I13, *"the path every successful turn takes"*) | **`1 passed` — GREEN** | **baseline** |
| G3 | voice `:684` binds `None` (R10's I4) | **`1 failed`** ✅ | 1 extra ✅ |
| G4 | rename the local + parameter in `_persist_terminal_assistant` (a correct refactor) | `1 passed` | — |
| **G5** | the clean-finish SQL **parameterises the column name** — a correct refactor | **`1 failed` — FALSE POSITIVE** | — |
| G6 | delete a SQL writer outright (voice stops writing the column) | `1 failed` ✅ | — |

**G1 is the one that decides this.** `_withheld_json` survives on the left-hand side, so the Name
disjunct is satisfied and the function is absolved — while *both* of its binds carry `None`. That is
R11's J3 (the orphan `UPDATE`, round 11's own headline fix) and J3b (the main `INSERT`) in a single
edit, still green. G4 shows why: I renamed two of the three `_withheld_json` occurrences and the
third, at `:6303`, kept the function green on its own.

**G5 is the false positive, and its message is untrue.** Extracting the column name to a placeholder
— a correct, ordinary refactor — drops the count to 2 and reds with *"only 2 function(s) write
`withheld_tools` in SQL … The column lost a writer, which is how three of four turn shapes persisted
NULL."* No writer was lost. The gate cannot distinguish a deleted writer from a parameterised one,
and R11's warning stands verbatim: a guard that reds on a correct refactor is a guard that gets
deleted.

The honest form was in R11's §8 and is still cheap: assert **per bind expression**, over each
`execute`/`fetchrow`/`fetchval` whose SQL names the column, that the argument at the column's
position contains `withheld_json()`. That reds G1, G2, G3 and does not red G5.

### 4 · Route sixteen, and a `_NOT_A_TURN` entry that is wrong — **FAIL**

**Falsifier:** any construction that puts a narrowing above an arming, or a narrowing entry point
with no arming, while the gate is green; any exempted entry whose stated reason is untrue.

**The gate is byte-identical this round.** `git diff` over `tests/test_cp0_instrument.py` touches
`_NOT_A_TURN`, `_TURN_SCOPE`, `arming`, `glob`, `_narrowings_in` and `_called_name` **zero** times.
R11's seven routes are therefore open by construction; I re-measured one (V3, `functools.partial`)
and the control, to show the negative can measure something:

| # | construction | gate |
|---|---|---|
| — | **CONTROL** — a direct narrowing above the arm in `stream_response` | **`2 failed`** ✅ |
| V3 | `functools.partial(kc.get_tool_definitions, …)` above the arm | **`6 passed`** |

**Route sixteen: a router that narrows and then delegates.** `arming` closes transitively over bare
names, and `_turn_entry_calls` does `if fn.name in arming and not any(arm_turn_surface in fn):
continue` — so anything that calls `stream_response` is exempted **wholesale**, including when its
own narrowing runs *before* the delegation. Measured with a matched control, the two files differing
by one `async for … in stream_response(…)` line:

| variant | sweep discovers it? | gate |
|---|---|---|
| `send_message_v2` narrows, **returns** | `['routers/r16_probe.py::send_message_v2']` | **`2 failed`** ✅ |
| `send_message_v2` narrows, **then delegates to `stream_response`** | **`[]` — not discovered at all** | **`6 passed`**, wide **at baseline** |

The gate's own comment blesses this: *"A router that DELEGATES to an armed entry point is covered by
it."* It was true when a pre-arm narrowing no-op'd — nothing existed to be lost. **This round made it
false**: the router's narrowing now auto-arms a sink, and `stream_response`'s `arm_turn_surface()`
replaces it (S1). So the exemption is now the mechanism by which a real row is created and then
discarded, and the shape it exempts — an eligibility pre-check in front of a delegation — is the
most ordinary router there is.

**A `_NOT_A_TURN` entry that is now wrong rather than merely visible.**
`routers/catalog.py::list_tools_catalog`'s stated reason reads:

> *"there is no turn for a narrowing to belong to, and `record_catalogue_unavailable` **correctly
> no-ops unarmed** rather than attributing a row to a turn that never happened."*

`record_catalogue_unavailable` no longer no-ops unarmed — this round deleted that behaviour, and the
same commit's docstring says so in bold. The exemption's entire justification is a description of
code that was removed three files away. `test_NO_ALLOW_LIST_ENTRY_IS_STALE` cannot see it: it
compares the set against `discovered`, and this entry is still discovered, so `stale == []` and the
gate is `6 passed`. That is R11's finding #3 — *"nothing checks a member is not a turn"* — arriving
as an actual false statement in the tree rather than as an injected hypothetical. The same sentence
underwrites `routers/tool_permissions.py::set_permission` and `::_assert_known_tool` implicitly:
all three now auto-arm a sink on a catalogue failure in a non-turn request.

### 5 · The empty-vs-outage revert — **PASS on the revert, FAIL on the cache**

**Falsifier:** either door registering an outage on a *successful* empty fetch; the `[]`-not-cached
fix having regressed, or having no guard; a recovered gateway not being re-dialled.

Driven against the real `KnowledgeClient` with a stubbed MCP transport, one armed turn per row,
counting real dials at `session.initialize`:

```
--- ADMIN door ---
  turn 0: gateway offers []          -> got []     dials=1  outage=False  registered=[]
  turn 1: gateway offers ['a']       -> got ['a']  dials=2  outage=False  registered=[]
  turn 2: gateway offers ['a','b','c'] -> got ['a'] dials=2  outage=False  registered=[]
--- USER door ---
  turn 0: gateway offers []          -> got []     dials=1  outage=False  registered=[]
  turn 1: gateway offers ['a']       -> got []     dials=1  outage=False  registered=[]
  turn 2: gateway offers ['a','b','c'] -> got []   dials=1  outage=False  registered=[]
  admin cache TTL field? []          _TOOL_CATALOG_TTL_S = 60.0
```

* **The revert is correct and complete.** A successful empty fetch registers **nothing on either
  door**, and `catalogue_outage_registered()` is `False`. R11's A4 is closed, and the two doors now
  agree — which also settles R11's U1 complaint the other way: registering nothing on a zero-tool
  success is the doctrine now, not a gap. It is guarded, and the guard reds for its reason (C-A).
* **The `[]`-not-cached fix is real on the admin door and untested.** Turn 0 → turn 1 re-dials
  (`dials` 1→2). C-B reverses it: I verified live that the door then returns `[]` forever with
  `dials` frozen at 1, and the suite ran **`2 failed, 212 passed` — at baseline**. The comment that
  justifies the revert calls this fix *"the real finding it was reaching for"*; nothing asserts it.
* **The user door still caches `[]`.** Turn 1 offers a tool and the door returns `[]` without
  dialling. Bounded by the 60 s TTL, so it is not the admin door's permanence — but the fix was
  applied to one door and the sibling was not audited, which is the shape R11 named and this round
  did not answer.
* **A non-empty admin catalogue is still pinned forever.** Turn 2: the gateway offers three, the door
  serves one, `dials` frozen. `self._admin_tool_definitions = tools` (`:806`) is unconditional and
  the class has no TTL field. R11's A3, unfixed and unmentioned.

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? |
|---|---|---|
| a narrowing can no longer be lost to ordering | **narrow, then arm** — seven of the eight routes it names | ✅ S1 `outage=False, rows=None` |
| " | the recorder built before the arm — row persisted, notice not raised | ✅ S1b |
| a record belongs to its own turn | a base-context record pins a list every later task shares | ✅ S2 |
| " | a pooled worker thread keeps the sink for the thread's life | ✅ S4 |
| U-2 · the recorder's value reaches `withheld_tools` | `_withheld_json = None` — the main INSERT **and** the orphan UPDATE | ✅ G1, gate `1 passed`, wide baseline |
| " | `:7424` the clean finish binds `None` (R10's I13) | ✅ G2, baseline |
| " | one surviving `withheld`-containing identifier absolves the function | ✅ G4 |
| the terminal-write gate does not red on correct code | parameterising the column name reds it, naming a lost writer | ✅ G5 |
| arm-order gate · no narrowing precedes the arming | **a router that narrows then delegates — not even discovered** | ✅ R16, gate `6 passed`, wide baseline, matched control reds |
| " | `functools.partial` (and R11's six others, gate unchanged) | ✅ gate `6 passed` |
| `_NOT_A_TURN` entries are trustworthy | `catalog.py::list_tools_catalog`'s reason cites behaviour deleted this round | ✅ by reading, against `record_surface_withheld`'s new body |
| `absorb` cannot crash | a `str` **subclass** as `stage` / `tool` / a `__str__` returning one | ✅ `:596`, `:515` |
| " | a `dict` subclass whose `.get` raises | ✅ `:641` |
| " | the **sink** is not a list | ✅ 4 shapes @ `:630` |
| `count` is absent-or-a-count | `count: false` persists | ✅ |
| an empty catalogue is not an outage | none found — closed on both doors | — |
| the admin `[]` is not cached | none found — `dials` 1→2 — **but nothing tests it** | — |

---

## 5 · The red-ability table

Baseline for every row: **scratch copy**. Gate rows use `TestTheTurnSinkIsArmedBeforeAnythingNarrows`
alone (**`6 passed`**); terminal-write rows use that test alone (**`1 passed`**); "instrument" rows use
`test_cp0_instrument.py` alone (**`2 failed, 108 passed`**); "wide" is the 7-suite set
(**`2 failed, 317 passed`**). "extra" counts failures **beyond** the two copy artefacts. Every
injection was applied to the scratch copy, verified present, and reversed by restoring a pristine
snapshot — never `git checkout`.

| # | injection | what it models | result |
|---|---|---|---|
| **G1** | `_withheld_json = None` | the main `INSERT` **and** the orphan `UPDATE` persist NULL | **gate `1 passed`, wide baseline — GREEN** |
| **G2** | `:7424` clean finish binds `None` | R10's I13, still open | **GREEN — baseline** |
| G3 | voice `:684` binds `None` | R10's I4 | **`1 failed`** ✅ *(new this round)* |
| G4 | rename the local + parameter | a correct refactor | GREEN — one identifier survived |
| **G5** | parameterise the column name in the SQL | a correct refactor | **`1 failed` — FALSE POSITIVE** |
| G6 | delete a SQL writer | a writer is lost | `1 failed` ✅ (same message as G5) |
| O-A | `_sink_for_record` no-ops when unarmed | **the round's headline fix** | **2 extra** ✅ |
| O-B2 | `_sink_for_record` arms unconditionally | the mid-turn discard its docstring forbids | **14 extra** ✅ |
| O-C | the auto-armed sink is not published | the record lands nowhere | **2 extra** ✅ |
| A-A | drop the non-dict row guard | `absorb` crashing on a bad row | **3 extra** ✅ |
| A-B | drop `_as_text` | unhashable values reaching the dedupe key | **2 extra** ✅ (but 6 shapes still crash **with** it) |
| A-C | tool branch before the scope dispatch | the one-behind enumeration | **1 extra** ✅ |
| A-D | `withheld_json` filters by a scope list | the fourth recurrence | **10 extra** ✅ |
| C-A | re-add `if not tools: register an outage` | **U-2's founding confusion** | **1 extra** ✅ |
| **C-B** | cache `[]` on the admin door again | **the revert's stated justification** | **BASELINE — GREEN.** Regression verified live: `dials` frozen at 1, `[]` served forever |
| **R16** | a router that narrows, then delegates | **route sixteen** | **gate `6 passed`, wide baseline** |
| R16-b | the same router **without** the delegation | the matched control | **gate `2 failed`** ✅ |
| CONTROL | a direct narrowing above the arm | the gate's subject | **gate `2 failed`** ✅ |
| V3 | `functools.partial` above the arm | R11's route, gate unchanged | **gate `6 passed`** |

**G1, C-B and R16 are the block that decides this round.** C-B shows the fix the round's own comment
calls "the real finding" is unguarded. G1 shows the rewritten write gate — a real improvement —
still cannot see the two binds in the function that performs every text-turn write. R16 shows the
ordering gate exempting the one shape this round's change turned from harmless into lossy.

---

## 6 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| `_sink_for_record` auto-arm | the other half of the class — narrowing **above** an arm | drove S1/S1b/S1c against the real functions | **NO** — seven of the eight named routes still lose the row |
| " | whether the row and the notice can now disagree | drove `catalogue_outage_registered()` beside `withheld_json()` | **NO — a new state**, S1b |
| " | a record reaching a different turn | drove the base context and a pooled thread | **NO** — S2, S4; latent, not live |
| " | whether the ordering gate's exemptions are still sound under it | R16 + matched control | **NO** — the delegation exemption is now a loss channel |
| " | whether any `_NOT_A_TURN` reason was invalidated | read all five against the new `record_*` body | **NO** — `catalog.py::list_tools_catalog`'s reason is now untrue |
| `_as_text` coercion | every value that is nominally a `str` but does not behave like one | drove 15 shapes | **NO** — `str` subclasses bypass it, at the two exact lines it names |
| `isinstance(row, dict)` guard | a `dict` whose *behaviour* is not a dict's | drove a `.get` that raises | **NO** — crashes at `:641` |
| " | the **sink** container, same class one level up | drove tuple/generator/str/dict | **NO** — 4 shapes crash at `:630` |
| " | `count`'s type check | drove `True` / `False` / an `int` subclass | **NO** — `count: false` persists |
| the terminal-write gate rewrite | every function that writes the column | AST-enumerated with the gate's own predicate | **YES** — all three, and voice now reds |
| " | whether a bind inside a covered function can still be `None` | G1, G2, G4 | **NO** — one identifier absolves the function |
| " | whether a correct refactor reds it | G5 | **NO** — reds, with an untrue message |
| the empty-catalogue revert | the **other** door | drove both, one armed turn per fetch | **YES** — both register nothing |
| " | whether the revert is guarded | C-A | **YES** — reds at the caller, for its reason |
| the `[]`-not-cached fix | whether anything asserts it | C-B, verified live | **NO — no test at all** |
| " | the user door's `[]` cache | drove U0→U2 | **NO** — `[]` cached for the full 60 s, no re-dial |
| " | a **non-empty** stale admin value | drove A0→A2 across a growing gateway | **NO** — pinned forever, still no TTL |
| `absorb` branch order (scope first) | a future scope carrying a tool | A-C + `test_a_FUTURE_scope…` | **YES** |
| `withheld_json`'s `not w.get("tool")` | the enumeration class it replaces | A-D | **YES** |

---

## 7 · Where the builder's documentation of a residual is incomplete or wrong

1. **`record_surface_withheld`'s new docstring states a property the fix does not have.** *"A
   narrowing cannot be lost to ordering, because the narrowing itself is what creates the place to
   put it."* It creates the place; `arm_turn_surface` then takes the place away. Measured: narrow-then-arm
   loses both rows. The eight routes it lists are, with one exception, narrow-then-arm.
2. **`_sink_for_record`'s docstring gives the right reason for the wrong conclusion.** *"Calling
   [`arm_turn_surface`] from here would let a mid-turn narrowing silently replace a sink that already
   held rows — the discard this whole area has been fighting since the sixth recurrence."* Correct,
   and it is the same discard that happens when the arm follows the narrowing. The analysis stops one
   step short of noticing that its own fix is on the losing side of it.
3. **The claim that the ordering gate "stays as a second line" is now load-bearing, not secondary.**
   Since narrow-then-arm is still lossy, the gate is the *only* line for seven of the eight routes —
   and it is the same gate that was green on all seven, plus route sixteen.
4. **`absorb`'s new comment claims the crash class is closed.** *"An unhashable `stage` blew up the
   dedupe `set`, an unhashable `tool` blew up the other one … EVERY value is coerced to a plain
   string."* Both still crash, at `:596` and `:515`, because `_as_text` returns `str` subclasses
   uncoerced. `str(value)` unconditionally is the coercion the sentence describes.
5. **`test_ABSORB_IS_TOTAL__no_row_shape_can_kill_the_turn_or_the_write` names a totality it does not
   test.** Fourteen parameters, all of them either plain types or plain non-dicts; six untested shapes
   still crash. The docstring says *"this asserts the property rather than the enumeration"* — it
   asserts a longer enumeration.
6. **`test_EVERY_TERMINAL_WRITE…`'s new docstring says the right thing and the code does something
   narrower.** *"If a function writes `withheld_tools` in SQL, the recorder's value has to appear in
   that function."* It requires an *identifier containing "withheld"* to appear in that function,
   which the function's own local variable satisfies while every bind carries `None` (G1).
7. **The gate's `_NOT_A_TURN` comment for `list_tools_catalog` is now factually wrong** — it cites the
   unarmed no-op this round deleted. And the comment *"A router that DELEGATES to an armed entry
   point is covered by it"* was true under the old semantics and is false under the new ones.
8. **Exemplary, and worth naming.** `test_AN_EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE__AT_THE_CALLER_TOO` is
   the best test added in this run's record: it drives the real client through a real transport stub
   inside a real armed turn, asserts the property at the layer where the defect actually lived rather
   than at the layer where the previous test looked, and reds for exactly its stated reason. The
   revert itself — deleting a registration rather than adding a scope for it — is the right call and
   the comment explains why without hedging. `absorb`'s scope-before-tool reordering and
   `withheld_json`'s `not w.get("tool")` are both the *class* fix rather than the instance fix, and
   both are guarded. That is four fixes closed properly in one commit.

---

## 8 · What would have to be true for this to PASS

* **Narrow-then-arm must stop losing rows**, because that is what all eight routes are. Either
  `arm_turn_surface` **adopts** a non-empty ambient sink instead of replacing it (with a
  turn-boundary marker so a genuine new turn still starts clean), or the arm must be provably the
  first statement — which is the gate, and the gate has sixteen routes. Adoption is the smaller
  change and it is the one that makes the fix's own sentence true.
* **The row and the notice must not be able to disagree.** `catalogue_outage_registered()` reads the
  ContextVar while the recorder holds its adopted sink; one of the two must become the single source,
  and a test must drive both in the same turn.
* **`_as_text` must be `str(value)` on every path**, not a pass-through gated on `isinstance(…, str)`
  — and `absorb` must validate the sink container as it validates the row. Then the totality the
  test's name claims is true, and the six shapes above are the parameters that prove it.
* **The terminal-write gate must anchor per bind, not per function.** Over each
  `execute`/`fetchrow`/`fetchval` whose SQL names the column, assert that the argument in the
  column's position contains `withheld_json()`. That reds G1, G2 and G3, and does not red G5 — which
  is the property R11 asked for and the property this rewrite reached toward.
* **The delegation exemption must be positional, not wholesale.** A delegator is covered only for
  narrowings that follow the delegation; one that precedes it is exactly the defect. That is a
  line-number comparison the gate already performs for arms.
* **`_NOT_A_TURN` needs its reasons checked, not just its membership** — and the first thing to check
  is that `catalog.py::list_tools_catalog`'s reason describes code that still exists.
* **The `[]`-not-cached fix needs a test**, and the user door needs the same audit and a TTL for
  non-empty admin values. A fix whose only evidence is two verifiers measuring it by hand is one
  refactor from being gone, and this round's own rule says so.

`git rev-parse HEAD` at start: `9c8df7800af7a297ea8fe758ded20714f70ad611`.
`git rev-parse HEAD` before writing: `9c8df7800af7a297ea8fe758ded20714f70ad611`.
