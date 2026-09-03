# CP-1 · round 10 · V-CODE — Verifier A (does the record ARRIVE, on every path?)

*Artifact frozen at `a43c24fcc0d14fba34977c2c61506cf6380ba690`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move**. I wrote
no tracked file other than this one, ran no `git checkout`, and touched nothing live. Injections were
applied to a **copy of `services/chat-service` in a scratch directory** and reversed by restoring
from a pristine snapshot; the end-to-end drives ran as **untracked** driver files inside
`services/chat-service/tests/`, which were deleted before this file was written (`git status` on
`services/` is clean — the only untracked path in the tree is Verifier B's verdict).*

**Every line marked *measured* below was produced by code I executed.** The drives ran the real
`stream_response`, the real `resume`-shared `_emit_chat_turn`, the real `voice_stream_response`, and
the real `KnowledgeClient.get_tool_definitions` / `get_admin_tool_definitions` against a genuinely
failing MCP transport, capturing **the value bound to the `withheld_tools` parameter of the SQL that
writes it**.

**Baselines I measured myself.**

| where | suites | result |
|---|---|---|
| in-tree | `test_cp0_instrument` + `test_stream_service` | **`159 passed`** |
| in-tree | + `test_admin_surface` + `test_knowledge_client` + `test_cp1_membrane` | **`372 passed`** |
| scratch copy | `test_cp0_instrument` + `test_stream_service` + `test_admin_surface` + `test_knowledge_client` | **`2 failed, 261 passed`** |
| scratch copy | `TestTheTurnSinkIsArmedBeforeAnythingNarrows` alone | **`5 passed`** |

The scratch copy's two failures are copy artefacts, not injections:
`test_the_class_4_metric_no_longer_pins_outcome_to_one_finish_reason` and
`test_the_fingerprint_does_not_hash_a_column_no_class_reads` both read files outside `app/` and
`tests/`. Every red-ability row below is measured against **`2 failed, 261 passed`** and reports only
the **extra** failures. (`test_cp1_membrane` is excluded from the scratch set: it contributes 21
copy-artefact failures.)

---

## 1 · Verdict

| # | claim under test | round 9 | round 10 |
|---|---|---|---|
| 1 | **the drain** — the row reaches the persisted value on every turn shape | FAIL (1 of 4) | **PASS on all six live shapes + voice, by execution** — R9's headline is genuinely fixed |
| 1b | …**and on every terminal path** | not asked | **FAIL — three paths where the value never reaches a column, one of them 100 % of aborted turns** |
| 1c | …**and something asserts that it arrives** | not asked | **FAIL — all four terminal write sites can bind `NULL` with the suite green** |
| 2 | **double-counting** — a row recorded twice, or at the wrong pass | not asked | **PASS, by execution** — idempotent, one row per absorb+drain, checkpoint ≡ terminal |
| 3 | **voice** — both halves, and the voice-shaped sibling | FAIL (neither half) | **PASS on both halves; FAIL on the sibling** — voice has no cancel handler and no terminal-path sibling at all |
| 4 | **the widened arm-order gate** — find route nine | FAIL (4 routes) | **FAIL — six further routes, and route nine reproduces the defect on ONE turn shape with every suite at baseline** |
| 5 | **the five catalogue branches — are there six?** | not asked | **FAIL — there are six. The sixth registers nothing and has no TTL** |

**Overall: FAIL.**

And I want to say plainly what round 10 got right, because it is the largest single correction in this
run. **R9's headline is closed, at the level R9 measured it.** The drain moved into
`AdvertisedToolsRecorder.withheld_json()`, the sink is bound at both text and voice entry points, and
I measured the outage row reaching the `withheld_tools` bind on **six** live `stream_response` shapes
plus voice — including the two R9 measured as `NULL` and the admin-no-token branch R9 found
registering nothing. The model is told on every shape that fetches. That is a real fix, verified by
execution, not by reading.

Five things turn the verdict, and they are all the same question asked one level further out again.

1. **There is a window in every turn where no terminal handler exists.** `_emit_chat_turn`'s only
   `try` opens at line **6781**; the generator starts yielding SSE at **6602**. A client that
   disconnects in between hits no handler, and there is **no `finally`**. Measured: aborting after 1–5
   SSE lines produces **zero INSERTs**, `_persist_terminal_assistant` is **never called**, and the
   outage row dies in the sink.
2. **`_persist_terminal_assistant` computes `withheld_json()` and throws it away** on an empty turn
   (`:6251`). Measured: `wrote_row=False`, the only SQL is `UPDATE chat_messages SET outcome`, and
   `carries_outage=False`. That branch is *more* likely on an outage turn, not less.
3. **Nothing asserts arrival.** Binding `NULL` at the clean finish, the suspend, the cancel handler
   or the error handler — **all four** — leaves the four suites at baseline (I10–I13). The only guard
   on the whole round-10 fix is a **recorder unit test**; removing the *wiring* that connects it to a
   turn (I2, I3) is green.
4. **Route nine.** Six further constructions walk past the arm-order gate. The one that matters:
   route the **admin** door alone through a class method and let the arm drift between the two doors.
   Gate `5 passed`, four suites **exactly at baseline**, and the admin turn loses *both* halves of U-2
   while fresh/editor/book stay green. That is this run's most repeated shape — a change applied to
   one member of a set — as a *regression* nothing can see.
5. **There is a sixth catalogue branch.** `get_admin_tool_definitions:724` returns a process-wide
   cached list with **no TTL and no invalidation**. Measured: one `/mcp/admin` answer of zero tools
   pins every admin turn for the rest of the process, the transport is never re-dialled after the
   gateway recovers, and nothing registers. P1's counter-example verbatim, in the same method whose
   other three exits were fixed in rounds 8, 9 and 10.

---

## 2 · The falsifier, per claim — stated before the search

### 1 · The drain — **PASS on arrival, FAIL on completeness**

**Falsifier (stated first):** (a) any live turn shape whose persisted `withheld_tools` is `NULL`
while the sink held a row; (b) any terminal path that writes a row without calling `withheld_json()`;
(c) any path on which `withheld_json()` is never called at all — cancel, crash, early `return`, an
exception before the terminal handler, a suspend that never resumes; (d) `withheld_json()` called and
its value dropped.

**(a) — closed. Measured**, with the real generator, capturing the parameter bound to `withheld_tools`
on the INSERT that names it, with the real `KnowledgeClient` on a failing MCP transport:

```
### 1 fresh chat (legacy): model told = True   INSERT finish='stop'  col named: True
   [{"segment":"072043c0292e","scope":"catalogue","stage":"catalogue_unavailable",
     "reason":"list-tools failed: RuntimeError","pass":null}]
### 2 agui + editor      : model told = True   ... "pass":1
### 3 admin + token      : model told = True   ... "pass":null
### 4 admin NO token     : model told = True
   [{... "reason":"no admin token presented","pass":null}]        ← R9's unfixed sibling, now fixed
### 5 book surface       : model told = True   ... "pass":1
### 6 disable_tools      : model told = False  (no fetch happens — correct, not a hole)
### VOICE                : model told = True   ... "pass":null
```

All four of R9's shapes plus two more, plus voice. `pass` is `null` on the tool-free shapes and `1`
on the shapes that advertised — consistent with `len(self._passes) or None`, and never fabricated.

**(b) — closed.** All five write sites read `withheld_json()`: the mid-turn checkpoint
(`stream_service.py:6962`), the suspend (`:7121`), the clean finish (`:7413`), the cancel handler
(`:7581`), the error handler (`:7622`), and voice (`voice_stream_service.py:684`). Enumerated from
the parse tree, not by grep.

**(c) — FAIL, and this is finding A1.** Structural, then measured.

`_emit_chat_turn` (`:6483–7709`) has exactly one large `try`, at **`:6781–7625`**, with handlers at
`:7541` (`CancelledError, GeneratorExit`) and `:7601` (`Exception`) and **no `finally`** — I dumped
this from the AST. But the generator begins yielding at **`:6602`** (`emitter.open_run()`), and
`:6608`, `:6611–6620` yield too. Everything between `:6483` and `:6781` — recorder construction,
sink adoption, the `open_run` / `memoryMode` / `agentSurface` frames, three small `try`s for
compaction and hooks — is **outside every handler**.

Measured, aborting the real generator after N SSE lines, under **both** disconnect mechanisms
(consumer `break` + `aclose`, and cancelling a consumer task parked between chunks), with async
generator finalisation forced by `await loop.shutdown_asyncgens()` so the result is not a timing
artefact:

```
  abort@ 1  last_sse=RUN_STARTED             INSERTs=0  outage_reached_column=False  persist_calls=[]
  abort@ 2  last_sse=CUSTOM memoryMode       INSERTs=0  outage_reached_column=False  persist_calls=[]
  abort@ 3  last_sse=CUSTOM agentSurface     INSERTs=0  outage_reached_column=False  persist_calls=[]
  abort@ 4  last_sse=CUSTOM agentSurface     INSERTs=0  outage_reached_column=False  persist_calls=[]
  abort@ 5  last_sse=TEXT_MESSAGE_START      INSERTs=0  outage_reached_column=False  persist_calls=[]
  abort@ 6  last_sse=TEXT_MESSAGE_CONTENT    INSERTs=1  outage_reached_column=True   [('interrupted','withheld=SET')]
  abort@ 7  last_sse=TEXT_MESSAGE_CONTENT    INSERTs=1  outage_reached_column=True   [('interrupted','withheld=SET')]
  abort@ 9  last_sse=CUSTOM persisted        INSERTs=1  outage_reached_column=True
```

The boundary is exactly where the parse tree says it is. Lines 1–5 are the hole: **no handler, no
`finally`, no `withheld_json()`, no row, and no `outcome` either** — so this is simultaneously a
CP-0.4 hole (a terminal path that records nothing) and a U-2 hole (a narrowing that registers
nowhere). It is not exotic: a fast reload, a double-submit, or a user who hits stop before the first
token all land in it, and a **catalogue outage makes the pre-first-token window longer**, because the
model has no tool surface to think with.

**A4, the same measurement's second half, stated as an honest limit on my own claim.** Without the
forced `shutdown_asyncgens()`, `persist_calls` was `[]` at *every* abort point including 6 and 7.
`stream_response` consumes `_emit_chat_turn` with a bare `async for` (`:6132`) and has **no
try/finally**, so when GeneratorExit is delivered to the outer generator the inner one is not closed
in-band — its `:7541` handler runs only when the event loop finalises the async generator. I could
not determine from a harness when that happens under uvicorn, so I do **not** claim the interrupt
persist is dead in production. What I do claim, measured: **it does not run within the request**, and
the code's own comment at `:7552–7562` (*"DETACH, then shield… measured as failing on EVERY cancel"*)
addresses a different half of this problem — the write's survival — while the handler's *reachability*
is decided one frame out, in a function with no `finally`.

**A3.** `stream_response` itself (`:4950–6205`) has **no `try` at any level of its body** — I dumped
its statement list. That is **1,129 lines** between `instrument.arm_turn_surface()` (`:5003`) and
`async for line in _emit_chat_turn(...)` (`:6132`), and it contains *both* catalogue fetches
(`:5623`, `:5625`), the intent gate (`:6003`) and the discovery seed (`:6073`). Any exception there —
including one raised *by* a catalogue door, since neither fetch is wrapped (`:5623`/`:5625` are bare
`await`s) — takes the whole sink with it. The turn dies, so nothing is *mis*recorded; but every
narrowing it collected is lost, and the turn is one of the four silent exits.

**(d) — FAIL, and this is finding A2.** `_persist_terminal_assistant:6251`:

```python
if not content and not reasoning and not tool_calls_history:
    ...  # stamps the USER row's outcome, then `return False`
```

Its callers evaluate `withheld_tools=_advertised.withheld_json()` at the call site — which **drains
the sink** — and this branch then discards the value. Driven directly with the production function
and a sink holding one outage row:

```
  wrote_row=False
    SQL='UPDATE chat_messages SET outcome = $2 WHERE message_id '  carries_outage=False
```

The orphan branch is the *documented* CP-0.4 improvement (a turn with no assistant row still records
an outcome on the user row). It carries `outcome` and nothing else — so on a cancel or an error
before the first token, U-2's row is computed, drained out of the sink, and dropped. The comment
block above it is 60 lines about which column an outcome belongs on; `withheld_tools` is not
mentioned, and `chat_messages.withheld_tools` is available on a user row exactly as `outcome` is.

**(1c) — FAIL, and it is the sharpest row in this verdict.** I asked what R9 asked, of the *tests*
rather than of the code: **is there anything that would notice if the row stopped arriving?**
Injected into the scratch copy, one site at a time:

| site | injection | four suites |
|---|---|---|
| the clean finish (`:7413`) | bind `None` | **GREEN — baseline** |
| the suspend (`:7121`) | bind `None` | **GREEN — baseline** |
| the cancel handler (`:7581`) | bind `None` | **GREEN — baseline** |
| the error handler (`:7622`) | bind `None` | **GREEN — baseline** |
| `stream_service:6582` | delete `bind_sink(_surface_sink)` | **GREEN — baseline** |
| `voice_stream_service:243` | delete `bind_sink(_voice_sink)` | **GREEN — baseline** |
| `voice_stream_service:684` | bind `None` | **GREEN — baseline** |
| `instrument:635` | delete `self.absorb(self._sink)` | **1 extra** — `test_THE_ROW_REACHES_THE_COLUMN_ON_A_TURN_THAT_NEVER_ADVERTISED` |

The **clean finish is the path every successful turn takes**, and it can stop carrying the column
with 261 tests green. The single guard on the whole round-10 fix,
`test_THE_ROW_REACHES_THE_COLUMN_ON_A_TURN_THAT_NEVER_ADVERTISED`, constructs a recorder by hand,
calls `bind_sink` by hand and reads `withheld_json()` by hand — it proves the *recorder* drains and
says nothing about whether any turn is wired to it. Its own docstring says *"Measured across the four
live turn shapes"*, which is true of the round-9 verifier's measurement and not of the test.
**The fix is real and the property is untested**, which is the same relationship round 9 found
between the arming and the two halves it was supposed to serve.

### 2 · Double-counting — **PASS**

**Falsifier:** a row recorded twice; a row stamped with a pass it does not belong to; a mid-turn
checkpoint plus a terminal write producing a duplicate through `segment_merge_sql`.

Driven, all four:

```
  withheld_json() x3 on one bound sink : 1st=1 2nd=1 3rd=1   sink_after=[]
  absorb(sink) [:6979] then the terminal drain, same row      : 1 catalogue row
  checkpoint  = [{"segment":"aeb94ad4ece3", ... ,"pass":1}]
  terminal    = [{"segment":"aeb94ad4ece3", ... ,"pass":1}]   same segment? True
```

The mechanism holds because `absorb` is **destructive** (`sink.pop(0)`), so the second call finds an
empty sink; and because `_record_scoped` dedupes on `(scope, stage, len(self._passes))`. The
checkpoint and the terminal write emit byte-identical arrays with the same segment, so
`segment_merge_sql`'s "delete my segment, then append" is a genuine no-op — the property its docstring
claims, verified by execution rather than by the SQL's shape. I found no way to make `EXCLUDED -> 0
->> 'segment'` be `NULL` (which would take the unconditional-concat branch): every row the recorder
mints, on all three shapes, carries `segment`.

**One residual, measured, not a defect.** Two *different* failed fetches in one turn produce two rows:

```
  [{"segment":"495d92…","scope":"catalogue","stage":"catalogue_unavailable","reason":"boom","pass":1},
   {"segment":"495d92…","scope":"catalogue","stage":"catalogue_unavailable","reason":"boom","pass":2}]
```

This is reachable — a failure is deliberately not cached (`knowledge_client.py:630`) and
`_compute_rail_drive_context` (`stream_service.py:624`) fetches the catalogue a second time — so one
outage can yield two rows. That is the documented per-pass fan-out (`record_withheld`'s comment says
so in as many words), and it is right for a per-pass claim; but a consumer counting catalogue outages
counts **pass-instances**, and no comment on the *scoped* path says so.

### 3 · Voice — **PASS on both halves; FAIL on the sibling**

**Falsifier:** the voice turn registering without telling, or telling without registering; a
voice-shaped sibling of anything found elsewhere.

**Both halves, measured** on the real `voice_stream_response` with STT/TTS/pool stubbed, the shared
tool generator spied at its real signature, and the outage produced by the **real**
`KnowledgeClient`:

```
### VOICE: model told = True
### VOICE persist: INSERTs = 2
    INSERT col-withheld=False (the user row)
    INSERT col-withheld=True  finish='stop'
       [{"segment":"4ec100729942","scope":"catalogue","stage":"catalogue_unavailable",
         "reason":"list-tools failed: RuntimeError","pass":null}]
```

`advertised_tools` stays `NULL` by an explicit retraction, which is correct and correctly explained.

**The voice-shaped sibling of finding A1, and it is worse.** Dumped from the parse tree:

```
  voice main try 480-837: handlers=['Exception'] finally=False
```

`voice_stream_response` has **no `CancelledError`/`GeneratorExit` handler at all** and **no
`finally`**, and — unlike the text path — **no terminal-path sibling**: there is no voice equivalent
of `_persist_terminal_assistant`, so the single INSERT at `:641` is the only way a voice turn is ever
recorded. Measured:

```
  voice abort@1 (yielded 1): assistant INSERTs=0   sqls=[]
  voice abort@3 (yielded 3): assistant INSERTs=1   ← the USER row only
  voice abort@5 (yielded 5): assistant INSERTs=2
```

A voice turn stopped before its last sentence records **nothing**: no outcome, no withheld row, no
reply. Voice is the surface where a user stopping mid-answer is the *normal* interaction.

And **I3/I4 are green**: deleting voice's `bind_sink` or binding `None` to its `withheld_tools`
leaves the four suites at baseline. R9's finding — *"an arm with no reader"* — is re-introducible with
the suite green, in the file whose comment now says *"ARMING A SINK NOBODY READS IS NOT
INSTRUMENTATION"*.

### 4 · The widened arm-order gate — **FAIL, route nine found**

**Falsifier:** any construction that puts a narrowing above the arming while
`TestTheTurnSinkIsArmedBeforeAnythingNarrows` stays green. I worked the prompt's list — a lambda, a
method on a class, dynamic dispatch, `getattr`, a module outside both directories — plus three the
gate's own structure suggested.

The gate **is** substantially better than round 9's: `_TURN_SCOPE` is a directory sweep, the helper
closure is transitive to a fixed point across modules, and R9's R1–R4 are genuinely closed (I
confirmed the fixed point reaches `_leaf`/`_mid` and that discovery includes `_`-prefixed names).

**Six further routes, each measured against the real module in a scratch copy, with a red control:**

| # | construction | arm gate |
|---|---|---|
| — | **CONTROL**: a direct `get_tool_definitions(...)` above the arm | **`1 failed`** ✅ |
| R5 | the fetch behind a **method on a module-level class** | **`5 passed` — GREEN** |
| R6 | `getattr(kc, 'get_tool_definitions')` then `await _f0(...)` | **`5 passed` — GREEN** |
| R7 | a **module-level lambda** helper | **`5 passed` — GREEN** |
| R8 | a helper in **`app/turnhelp.py`** — a module outside both swept directories | **`5 passed` — GREEN** |
| R9 | a helper in **`app/services/surface/loader.py`** — the glob is non-recursive | **`5 passed` — GREEN** |
| R10 | a **sync `def`** turn entry point that narrows and never arms | **`5 passed` — GREEN** |

The mechanisms, each a specific line:

* R5/R7 — `all_fns` is built from `tree.body` only (`:1656–1658`), so **methods and lambdas are not in
  the closure**. `_called_name` returns the bare attribute, so `self._loader.load()` resolves to
  `load`, which no top-level `def` supplies.
* R6 — `_called_name` returns `None` when `node.func` is itself a `Call`; and the alias check
  (`:1708`) only fires on `ast.Attribute`, not on `getattr(...)`.
* R8 — `_TURN_SCOPE = ("services", "routers")` (`:1587`). R9 closed the *cross-module* hole **inside**
  those two directories and drew the new boundary at the directory.
* R9 — `(base / sub).glob("*.py")` (`:1649`) is **not** `rglob`. A subpackage is invisible. There are
  none today, which is exactly when a boundary is cheap to cross.
* R10 — `if not isinstance(fn, ast.AsyncFunctionDef): continue` (`:1681`).

**Route nine proper — the one that matters, because it is a regression nothing in the tree can see.**
Round 9's routes were all "the whole surface drifts", and `test_builds_message_history` (which was
retrofitted into U-2's end-to-end proof, and correctly so) catches those: routing *both* doors through
a class method and letting the arm drift reds it, and I measured that — `told=False` on all six shapes.

So I asked the question this run keeps answering the hard way: **what if only one member of the set
drifts?** I routed the **admin** door alone through a class method and moved the arm to sit *between*
the two doors:

```
ARM-ORDER GATE                                    : 5 passed
instrument + stream_service + admin_surface suites: 2 failed, 168 passed   ← EXACTLY the baseline
--- END TO END ---
### 1 fresh chat  : model told = True   [{... "catalogue_unavailable" ...}]
### 2 agui+editor : model told = True   [{... }]
### 3 admin+token : model told = False  (no row)      ← both halves of U-2 gone
### 4 admin NO tok: model told = False  (no row)      ← both halves of U-2 gone
### 5 book surface: model told = True   [{... }]
```

**No extra failure anywhere.** The gate is green because it cannot see the method; the U-2 end-to-end
guard is green because it drives the fresh-chat shape; `test_admin_surface` is green because it
asserts *which catalogue is fetched*, not *whether the turn was told about its failure*. This is round
7's defect, restored, on the surface that has now had a U-2 sibling fixed in three consecutive rounds.

**`_NOT_A_TURN` — no entry is wrongly classified, and three are stale.** I ran `_turn_entry_calls()`
against the real tree and compared:

| entry | discovered? | actually not a turn? |
|---|---|---|
| `services/stream_service.py::_stream_with_tools` | **no — STALE** | yes (inner, runs inside an armed turn) |
| `services/stream_service.py::_emit_chat_turn` | **no — STALE** | yes (inner; both callers arm) |
| `services/stream_service.py::_run_subagent_call` | **no — STALE** | yes (inner) |
| `services/stream_service.py::_compute_rail_drive_context` | yes | yes — a helper called from both entry points |
| `routers/catalog.py::list_tools_catalog` | yes | yes — UI tool-picker feed, no model |
| `routers/sessions.py::patch_session` | yes | yes — validates pinned names, 422s |
| `routers/tool_permissions.py::set_permission` | yes | yes — same shape |
| `routers/tool_permissions.py::_assert_known_tool` | yes | yes — same shape |

So the answer to *"is one of them wrong"* is **no** — the reasons hold. But three of the eight are
**pre-emptive exemptions for entry points the sweep does not currently find**, and nothing tells the
reader that. An allow-list entry that is never exercised is a permanent exemption with a reason nobody
re-checks: if a narrowing is ever added directly to `_stream_with_tools` on a path that does *not*
inherit an armed sink, the exemption fires silently. The gate has no assertion that every
`_NOT_A_TURN` key is actually discovered.

**One more structural hole in the same machinery, measured.** `all_fns.setdefault(f.name, f)`
(`:1658`) keys the closure on the **bare function name across all modules**, first-writer-wins. Two
collisions exist today — `_jsonb` (`routers/evaluate.py`, `routers/sessions.py`) and `_sse`
(`services/stream_events.py`, `services/voice_stream_service.py`). Neither narrows, so nothing is lost
now; but if the *second* definition of a colliding name were the narrowing one, it would be dropped
from `all_fns` and therefore from `reaching`, and every call to it would be invisible.

### 5 · The five catalogue branches — **there are six**

**Falsifier:** any exit from either door that yields an empty catalogue without registering.

**The five `return []` — enumerated and all registering.** `knowledge_client.py`:

| line | door | branch | registers? |
|---|---|---|---|
| 641 | user | `mcp` package not installed | ✅ |
| 663 | user | transport / `list-tools` raised | ✅ |
| 723 | admin | **no admin token** | ✅ — round 10's fix, and it reaches the column (shape 4 above) |
| 734 | admin | `mcp` package not installed | ✅ |
| 764 | admin | transport / `list-tools` raised | ✅ |

And unlike round 9, **all three of the previously-unguarded ones now red**: I5, I6 and I7 each add
`test_EVERY_catalogue_path_registers_on_a_real_failure[...]`. R9's I4/I8 (both green) are closed.

**The sixth, and it is not a `return []`.** `get_admin_tool_definitions:724`:

```python
if self._admin_tool_definitions is not None:
    return self._admin_tool_definitions
```

`self._admin_tool_definitions = tools` is assigned unconditionally at `:782` — **including when
`tools == []`** — and there is **no TTL and no invalidation anywhere in the class**. Driven against
the real client:

```
  fetch 1 (gateway returns 0 admin tools): []   transport_called=True
  cached value: []
  fetch 2 (gateway healthy, 1 tool)      : []   transport_called=False
  fetch 3                                : []
  outage registered on any of them       : False
  admin cache has a TTL                  : False
```

A single `/mcp/admin` answer of zero tools — a partial federation, a provider still booting, an
`admin:write` scope not yet granted — **pins every admin turn in the process at an empty surface,
permanently**, with no log line, no record and no notice, and the transport is never dialled again
even after the gateway recovers. That is *the largest narrowing this system can perform, recorded as
nothing*, which is the sentence `_register_catalogue_outage`'s own docstring uses about the defect it
was written to fix. The comment at `:785–789` reasons carefully about why the admin cache has no
`_tool_defs_cache` entry to compare `count` against — and does not notice that the same cache never
expires.

The user door has the identical shape at `:634–635` (`first=[] second=[] refetched=False`), bounded by
`_TOOL_CATALOG_TTL_S` rather than by the process lifetime. Both are *successes* rather than outages,
so I do not claim they should emit `catalogue_unavailable`; what I claim is measured and narrower:
**there is a sixth way out of a door that hands a turn an empty catalogue, it is not one of the five
that were audited, and on the admin side it is unbounded in time.**

---

## 3 · The bypass table

| the property asserts | the path that defeats it | measured? |
|---|---|---|
| U-2 · the outage row reaches `withheld_tools` | abort in `_emit_chat_turn`'s **pre-`try` window** (SSE lines 1–5): no handler, no `finally`, no persist | ✅ 0 INSERTs, `persist_calls=[]`, both disconnect mechanisms |
| " | `_persist_terminal_assistant:6251` — the empty-turn branch drains the sink and writes only `outcome` | ✅ `wrote_row=False`, `carries_outage=False` |
| " | `stream_response` has **no `try`** across the 1,129 lines from the arm to `_emit_chat_turn` | ✅ AST dump of its statement list |
| " | the cancel handler at `:7541` is reached only at async-generator finalisation, not in-band | ✅ `persist_calls=[]` until `shutdown_asyncgens()` forced |
| " | **any** of the four terminal write sites binding `None` | ✅ I10–I13 all at baseline |
| " | `stream_service:6582` / `voice:243` — deleting `bind_sink` | ✅ I2, I3 at baseline |
| " (voice) | voice has no cancel handler, no `finally`, and no terminal-path sibling | ✅ `handlers=['Exception'] finally=False`; abort@1 → 0 INSERTs |
| arm gate · no narrowing precedes the arming | a **method on a class** (R5) | ✅ gate `5 passed`; e2e `told=False` on every shape |
| " | **`getattr`** dynamic dispatch (R6) | ✅ gate `5 passed` |
| " | a **module-level lambda** (R7) | ✅ gate `5 passed` |
| " | a module **outside** `app/services` and `app/routers` (R8) | ✅ gate `5 passed` |
| " | a **subpackage** — the glob is non-recursive (R9) | ✅ gate `5 passed` |
| " | a **sync `def`** entry point (R10) | ✅ gate `5 passed` |
| " | **only the admin door drifts** — route nine | ✅ gate `5 passed`, three suites **at baseline**, admin turn loses both halves |
| " | `all_fns` keys the closure on a bare name, first-writer-wins | ✅ 2 live collisions enumerated (`_jsonb`, `_sse`) |
| every catalogue branch registers | `get_admin_tool_definitions:724` — a process-wide cache with no TTL and no invalidation | ✅ empty catalogue pinned across a gateway recovery |
| double-counting · a row cannot be recorded twice | none found — `withheld_json` ×3, absorb+drain, checkpoint≡terminal, `segment` present on every minted row | — |
| the row reaches the model | none found — the notice reaches the model on all five fetching shapes **and** voice | — |

---

## 4 · The red-ability table

Baseline for every row: **scratch copy, four suites = `2 failed, 261 passed`**, both failures being
copy artefacts (`test_the_class_4_metric_...`, `test_the_fingerprint_...`, which read files outside
`app/` and `tests/`). In-tree baseline `372 passed` over five suites, `159 passed` over the two named
ones. Each injection applied to the scratch copy and reversed by restoring a pristine snapshot —
never `git checkout`. "extra" counts failures **beyond** the two artefacts.

| # | injection | what it models | result |
|---|---|---|---|
| I1 | `withheld_json` no longer calls `self.absorb(self._sink)` | **the round-10 headline fix** | **1 extra** — `test_THE_ROW_REACHES_THE_COLUMN_ON_A_TURN_THAT_NEVER_ADVERTISED` |
| **I2** | `stream_service:6582` — delete `bind_sink(_surface_sink)` | **the fix's wiring into the text turn** | **GREEN — baseline** |
| **I3** | `voice:243` — delete `bind_sink(_voice_sink)` | the fix's wiring into voice | **GREEN — baseline** |
| **I4** | `voice:684` — bind `None` to `withheld_tools` | **R9's voice finding, restored** | **GREEN — baseline** |
| I5 | admin **no-token** registration removed | round 10's admin fix | **1 extra** — `test_EVERY_catalogue_path_registers_on_a_real_failure` |
| I6 | admin `mcp not installed` registration removed | R9's **I4**, which was green | **1 extra** — now guarded ✅ |
| I7 | user `mcp not installed` registration removed | R9's **I8**, which was green | **1 extra** — now guarded ✅ |
| I8 | scoped row fabricates `pass: 1` when no pass ran | "`None`, never a fabricated 1" | **1 extra** |
| **I9** | `_record_scoped` writes `entry["count"] = count or 0` | **§0.14.3's "absent ≠ zero", recorder side** | **GREEN — baseline** |
| **I10** | the **suspend** path binds `withheld_tools=None` | does the row arrive on an `awaiting_input` turn | **GREEN — baseline** |
| **I11** | the **cancel** handler binds `None` | does it arrive on an abandoned turn | **GREEN — baseline** |
| **I12** | the **error** handler binds `None` | does it arrive on a failed turn | **GREEN — baseline** |
| **I13** | the **clean finish** binds `None` | **does it arrive on the path every successful turn takes** | **GREEN — baseline** |
| R5 | the fetch behind a class method, arm drifts | a routine refactor | **arm gate `5 passed`**; e2e `told=False` on all six shapes; caught only by `test_builds_message_history` |
| R6–R10 | `getattr`, lambda, outside-module, subpackage, sync `def` | five more constructions | **arm gate `5 passed`** each; control reds |
| **R11** | **only the admin door drifts** (route nine) | one member of a set | **arm gate `5 passed`, three suites AT BASELINE**, admin turn loses both halves of U-2 |

**I9 through I13 are the block that decides this round.** I1 shows the recorder's drain is guarded.
I2 and I13 together show that **the connection between that recorder and the database is not** — the
row can stop arriving at the clean finish, on every successful turn, with 261 tests green. R9's
sentence — *"a row that crashes nothing and arrives nowhere is the same silence U-2 exists to end"* —
is now true of the **test suite** rather than of the code.

I9 deserves its own line. `count is not None` is guarded at `record_catalogue_unavailable`
(`instrument.py:334`, R9's I6 reddened three tests there) and **unguarded** at `_record_scoped`
(`:547`), the recorder-side twin introduced in the same design. The rule was tested on one member of
the pair.

---

## 5 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| the drain moved into `withheld_json()` | every terminal path that reads it | AST-enumerated all five sites; drove six shapes + voice + abort + crash | **YES** — all five call it |
| " | a path that never calls it | AST'd every `try`/handler/`finally` in the three entry points; drove aborts at 12 points | **NO** — the pre-`try` window of `_emit_chat_turn`, and `stream_response` has no `try` at all |
| " | a path that calls it and drops the value | read every branch of `_persist_terminal_assistant`; drove the empty-turn branch | **NO** — `:6251` writes `outcome` only |
| " | a **test** that would notice it stopping | I2, I10–I13 | **NO** — all four write sites and both binds are green |
| the admin no-token registration | the other exits of the same method | enumerated every `return` in both doors; drove each | **NO** — the process-wide cache at `:724` is a sixth exit with no TTL |
| `count` absent-not-zero | the **recorder** twin of the client-side rule | I9 against `_record_scoped` | **NO** — green |
| voice's drain + column | voice's terminal *paths* | AST'd voice's `try`; drove aborts | **NO** — `handlers=['Exception']`, no `finally`, no `_persist_terminal_assistant` sibling |
| the arm-order gate's directory sweep | the boundaries the sweep still draws | R5–R10, control | **NO** — six routes green |
| " | the *set* problem: one door vs both | route nine | **NO** — gate green, three suites at baseline, defect on the admin shape |
| `_NOT_A_TURN`'s written reasons | whether each is true, and whether each is live | ran `_turn_entry_calls()` and diffed against the allow-list | **reasons all hold**; three entries are stale, and nothing asserts an entry is exercised |
| `segment_merge_sql`'s idempotence | a row with no `segment` (the unconditional-concat branch) | inspected every mint site; drove checkpoint + terminal | **YES** — every minted row carries `segment` |

---

## 6 · Where the builder's documentation of a residual is incomplete or wrong

1. **`AdvertisedToolsRecorder.absorb`'s docstring is right about the diagnosis and silent about the
   remaining half.** *"the loop moves here, where the recorder can run it from every path that reads
   the column, rather than staying somewhere a caller has to remember"* — true, and it does not
   address the paths that read **no** column. Two of the four ways a turn can end (an abort before the
   first token, an empty terminal turn) still reach no writer, and one of them is *created* by the
   thing the sentence is about.
2. **`test_THE_ROW_REACHES_THE_COLUMN_ON_A_TURN_THAT_NEVER_ADVERTISED` does not test what its name
   says.** It constructs a recorder, binds a hand-made sink and reads `withheld_json()`. No column,
   no turn, no INSERT. Its docstring cites the round-9 four-shape measurement as though the test
   carried it; measured, the test is green while every one of the four real write sites binds `None`.
   This is the same relationship as round 9's `test_ALL_THREE_TURN_SHAPES_reach_the_notice` — and that
   one *retracted its own claim in place*, which is the form this one should take.
3. **`voice_stream_service:238–241`'s comment closes the finding and not its sibling.** *"The recorder
   exists here so the column has a writer"* is true. The module still has no cancel handler, no
   `finally` and no terminal-path sibling, so the writer runs only on a clean finish — and a voice
   turn stopped mid-answer is the surface's normal interaction, not its edge case. Nothing in the tree
   records that as open.
4. **`TestTheTurnSinkIsArmedBeforeAnythingNarrows`'s disclosure is incomplete by six.** It names the
   alias route and the hand-kept `_NARROWING_CALLS` list as the residuals "with teeth". Measured, the
   gate is also blind to a method, a lambda, `getattr`, a module outside the two directories, a
   subpackage, and a sync `def` — and `_narrowing_helpers`' docstring says *"a fixed-point closure has
   no depth to exceed and no file boundary to cross"* while the closure it builds excludes every
   function that is not at a module's top level.
5. **`_TURN_SCOPE`'s comment states the lesson and then repeats the error.** *"A boundary drawn at a
   file is a boundary a refactor crosses by accident"* — and the replacement draws the boundary at two
   directories, non-recursively. R8 and R9 are that sentence, measured.
6. **`get_admin_tool_definitions`'s docstring says the catalogue is *"cached process-wide (identical
   for every admin)"* and treats that as a property rather than a risk.** It is cached process-wide
   *including when it is empty*, with no TTL, so the one state an admin cannot recover from is the one
   the cache makes permanent. The `_ADMIN_CATALOG_KEY` comment three lines below reasons about the
   absence of a cache entry for `count`, in the same class, without reaching this.
7. **Exemplary, and worth naming.** `test_builds_message_history` was converted from a history test
   into U-2's genuine end-to-end proof, with the reason written into the test rather than into a
   verdict — and it is what caught R5. It is the only test in the tree that fails when the notice stops
   reaching the model on a real turn. The correct next step is the one it already demonstrates: the
   same shape, for the **row**, on each of the four terminal paths, and for the **admin** shape.

---

## 7 · What would have to be true for this to PASS

* **A `finally` on `_emit_chat_turn`**, or the `try` moved up to `:6483`. As it stands the turn has a
  window in which nothing records anything, and it is the window a user's stop button lands in.
* **`_persist_terminal_assistant`'s orphan branch must carry `withheld_tools`** onto the user row it
  already stamps, or §0.14.3 must say that an empty turn's narrowings are discarded.
* **A test that fails when a terminal write site stops binding the column.** I10–I13 must red. The
  cheapest honest version drives the real generator and asserts on the bound parameter, which is what
  I did here in ~60 lines; the recorder unit test cannot substitute for it.
* **Voice needs a cancel handler and a terminal-path sibling**, or the verdict for voice is "records
  only turns that end well", which is not what §0.14.3 claims.
* **The arm-order gate needs an anchor that is not a parse tree.** Round 8 proposed it, round 9
  repeated it, and it is still right: assert at **runtime**, on a request-scoped path, that
  `record_catalogue_unavailable` / `record_surface_withheld` never find `surface_withheld.get() is
  None`. Every one of R5–R11 is invisible to any syntactic gate and visible to that one.
* **`test_builds_message_history`'s property must hold for the admin and voice shapes too** — route
  nine is exactly the gap between "one shape is guarded end-to-end" and "the set is".
* **The admin catalogue cache needs a TTL, and an empty successful fetch must not be cached** — or the
  sixth branch is a permanent, silent, whole-catalogue narrowing for one class of user.
* **`_NOT_A_TURN` must assert that each of its keys is actually discovered**, so a stale exemption
  cannot become a live one without anyone deciding.

`git rev-parse HEAD` at start: `a43c24fcc0d14fba34977c2c61506cf6380ba690`.
`git rev-parse HEAD` before writing: `a43c24fcc0d14fba34977c2c61506cf6380ba690`.
