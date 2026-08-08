# CP-1 · round 9 · V-CODE — Verifier A (U-2, the P0 crash, and CP-0's drain path)

*Artifact frozen at `86ae725929215cbb20201308db1120b0855f1222`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move**, and the
only untracked path in the tree is Verifier B's verdict file. I wrote no tracked file other than this
one, ran no `git checkout`, and touched nothing live.*

*Every line below marked **measured** was produced by code I executed. Injections were applied to a
**copy of `services/chat-service` in a scratch directory**, never to the working tree, and reversed
by restoring from a pristine snapshot. End-to-end drives ran the real `stream_response` and the real
`voice_stream_response` with the real `KnowledgeClient` on an unreachable MCP transport.*

**Baselines I measured myself.** In-tree, the five named suites
(`test_cp0_instrument`, `test_stream_service`, `test_knowledge_client`, `test_cp1_membrane`,
`test_admin_surface`): **`362 passed`**. In the scratch copy the same five give **`361 passed,
1 failed`** — `test_the_gate_actually_RUNS_in_ci`, which reads `.github/` and is an artefact of the
copy, not of any injection. Every red-ability row below is measured against **`361 passed / 1 env
failure`**.

---

## 1 · Verdict

| # | claim under test | round 8 | round 9 |
|---|---|---|---|
| 1 | **the P0 crash** — a catalogue-scope row cannot kill the turn | FAIL (turn died) | **PASS** — the crash is genuinely closed at both sites |
| 1b | **U-2 half one** — the outage *registers*, i.e. the row reaches the column | not asked | **FAIL** — the row reaches `withheld_tools` on **1 of 4** measured live turn shapes |
| 2 | the rebuilt arm-order gate has no further route past it | FAIL (4 routes) | **FAIL** — **4 further routes measured**, two of them reproduce the end-to-end defect while the gate is green |
| 3 | `voice_stream_response`'s arming covers what that turn narrows | FAIL (unarmed) | **FAIL** — it arms, and delivers **neither** half of §0.14.3 |
| 4 | U-1's admin door composes; the `mcp not installed` branch registers | FAIL | **PASS on both, by execution** — with the sibling neither reached, and **neither fix is guarded by a test** |

**Overall: FAIL.**

The P0 itself was fixed properly and I say so plainly: the dispatch is at both sites, the row is
kept by reconciliation on merit, `count` is absent when unknown and carried when known, and a real
agui-editor turn on a failing catalogue now completes, persists, and tells the model. Three things
turn the verdict.

1. **The row arrives nowhere on most turns.** The drain hangs off the `advertised` chunk, which only
   `_stream_with_tools` emits — so a turn that ends up **tool-free** never drains its sink. A
   catalogue outage is *the* thing that makes a turn tool-free. Measured, four live shapes:

   | shape | model told | `withheld_tools` written |
   |---|---|---|
   | agui + `editor_context` (keeps `propose_edit`) | ✅ | ✅ the outage row |
   | plain chat turn, no editor context | ✅ | ❌ `NULL` |
   | admin turn, token present, transport fails | ✅ | ❌ `NULL` |
   | admin turn, **no** `X-Admin-Token` | ❌ | ❌ `NULL` |
   | voice turn | ❌ | ❌ the column is **not in the INSERT** |

   The prompt's own sentence is the finding: *a row that crashes nothing and arrives nowhere is the
   same silence U-2 exists to end.*
2. **The arm-order gate has four more ways past it**, including the *identical refactor* round 8
   used — extract the fetch into a helper — moved one file over, and the same refactor with one more
   `def` in between. Both green, both reproducing round 7's defect end-to-end.
3. **`voice_stream_response` was armed into a sink with no reader.** Measured: the outage row lands
   in the sink, the model is never told, nothing is drained, and the voice INSERT has no
   `withheld_tools` column at all. The new gate requires the arm and **cannot ask for either half**
   of the property the arm exists to serve.

---

## 2 · The falsifier, per claim — stated before the search

### 1 · The P0 — **PASS**, and 1b — **FAIL**

**Falsifier (stated first):** any of (a) a consumer, on any path, that indexes `tool` on a row that
lacks it; (b) the row being dropped between the sink and the `withheld_tools` bind; (c) `count`
fabricated as `0`, or lost between the sink and the column; (d) a reader of the persisted column, in
code or on the wire, that assumes `tool`.

**(a) — closed.** I enumerated every `["tool"]` index under `app/services`, `app/client`,
`app/routers` and executed the two that can see a sink row:

* `stream_service.py:6975-6979` — the drain now dispatches on `scope` before touching `tool`;
* `instrument.py:589-590` — `withheld_json`'s reconciliation keeps a catalogue row unconditionally.

The third `["tool"]` in the drain block, `stream_service.py:6985`, reads `_adv_ev["withheld"]` —
rows minted by `_stream_with_tools`, which never emits a scope row. Driven: a real agui + editor
turn with the MCP transport genuinely failing now yields **no `RUN_ERROR`**, reaches surface
assembly, calls the model, and persists.

**(b) — FAIL, and this is the finding.** Measured with the real generator, capturing the parameter
bound to `withheld_tools` at `stream_service.py:6337` (the `conn.fetchrow` upsert):

```
[agui-editor]   path=tool-loop        told=True   withheld_tools=
   [{"segment":"2a324005e964","scope":"catalogue","stage":"catalogue_unavailable",
     "reason":"list-tools failed: ExceptionGroup","pass":1}]
[legacy-plain]  path=gateway-direct   told=True   withheld_tools=NULL
[admin, token]  path=gateway-direct   told=True   withheld_tools=NULL
[admin, no tok] path=gateway-direct   told=False  withheld_tools=NULL
```

The mechanism: `_emit_chat_turn` drains the sink **inside `if _adv_ev is not None`**
(`stream_service.py:6959-6982`). A tool-free pass never produces that chunk, so the sink is never
transferred to the recorder and `withheld_json()` returns `None`. With the whole catalogue gone the
turn *is* tool-free unless something else keeps a declaration advertised — which only the agui editor
surface does. **The record path is disabled by the very event it exists to record.** Round 8 noted
this mechanism as the reason the crash did not fire on legacy turns; nobody has stated it as the
record loss it also is, and §0.14.3's first half ("the row must record it") is therefore satisfied on
one surface.

**(c) — PASS.** `count` is written only when a prior fetch left an expired cache entry, and it
survives the drain (`count=_sw.get("count")` → `if count is not None`). Driven end-to-end with a
warm-then-expired cache of 7 tools:

```
count-known:  {... "reason":"list-tools failed: ExceptionGroup","pass":1,"count":7}
count-cold:   {... "pass":1}            ← absent, not 0
```

Injecting `"count": count or 0` reds three tests (I6 below). Consistent at all three layers.

**(d) — no reader found, and here is how I searched.** `git grep withheld_tools` across the whole
repository: the only non-doc hits are the migration DDL (`app/db/migrate.py:327`), the two write
sites, and this round's tests. `grep -rn "withheld" frontend/src` returns two unrelated comments —
there is **no FE contract**. `app/routers/internal.py:1033`'s `r["tool"]` reads `tool_calls`, not
`withheld_tools`.

**Two residuals inside the record shape, both measured.**

* **`scope` never reaches the column for a declaration row.** §0.14.3's table declares
  `declaration | {scope, tool, stage, reason, pass}` — *"today's record, with the field made
  explicit."* The sink carries it (`instrument.py:300`), and the drain **throws it away**:
  `record_withheld(tool, stage, reason)` writes no `scope` (`instrument.py:457-489`). Measured with
  the production drain verbatim:

  ```
  {"segment":"a668a681ff03","tool":"book_list","stage":"token_budget","reason":"over budget","pass":1}
  {"segment":"a668a681ff03","scope":"catalogue","stage":"catalogue_unavailable","reason":"boom","pass":1}
  declaration row carries 'scope'?  False
  SCOPE_DECLARATION reaches the column?  False
  ```

  So every consumer must dispatch on the **absence** of `scope` — the "absence carries meaning"
  pattern the field was introduced to replace — and `SCOPE_DECLARATION` is a constant no persisted
  row has ever contained. `ARCHITECTURE.md:1424` still declares the column as `[{tool, stage,
  reason}]`, which now describes neither row.
* **The `tool: "*"` sentinel §0.14.3 rejects is minted by a live site.** `record_catalogue_unavailable`'s
  docstring and §0.14.3 both reject `"*"` because *"a sentinel makes every consumer that counts tools
  return a wrong answer while looking correct"*. `stream_service.py:2344-2353` emits
  `{"tool": "*", "stage": "pass_offered_no_tools", …}` and the drain at `:6983-6986` accepts it
  without comment. Measured: fed the verbatim production payload, it persists beside the outage row:

  ```
  [{"segment":"5aca…","scope":"catalogue","stage":"catalogue_unavailable",…},
   {"segment":"5aca…","tool":"*","stage":"pass_offered_no_tools",…}]
  ```

  One row-set, two representations of "no tools", one of which the design rejects by name. *(I did
  not measure the reachability of `not offered_tools` on an outage turn specifically; the emission
  site and the drain's acceptance are what I measured.)*

### 2 · The rebuilt arm-order gate — **FAIL**

**Falsifier:** any construction — refactor, rename, new module — that puts a narrowing above the
arming while `TestTheTurnSinkIsArmedBeforeAnythingNarrows` stays green. I worked the prompt's list:
two levels of helper, a method, a decorator, `functools.partial`, a comprehension/nested function, a
module outside `_TURN_MODULES`, and a `_`-prefixed entry point.

The gate is a genuine improvement — entry points are discovered from the parse tree, helpers are
followed one level, the arm must be at top level of the body, and aliases are flagged. All four of
round 8's routes are now detected (its own control test exercises each). **Four further routes,
each measured against the real module:**

| # | route | arm-gate | end-to-end |
|---|---|---|---|
| **R1** | **both catalogue fetches extracted into a helper in a *neighbouring module*** (`app/services/_catfetch.py`), arm drifts below | **`5 passed` — GREEN** | **`told=False` on both shapes; `withheld_tools=NULL`** — round 7's defect verbatim |
| **R2** | **the same refactor with *two* levels of module-local helper** (`_outer` → `_inner` → fetch) | **`5 passed` — GREEN** | **`told=False` on both shapes** |
| R3 | a turn entry point named `_stream_response_v2`, unarmed, in `stream_service.py` | **`5 passed` — GREEN** | (discovery skips it entirely) |
| R4 | a turn entry point in a third module (`app/services/agent_turn_service.py`) | **`5 passed` — GREEN** | (module never parsed) |

R1 is the one that matters. `_narrowings_in` builds `helpers` from `tree.body` **of the same module**
(`test_cp0_instrument.py:1573-1576`), so a callee one file over is invisible — and its own docstring
argues *"a boundary drawn at one stack frame is a boundary a refactor crosses by accident"* while
drawing that boundary at one stack frame **and** one module. R2 is that sentence taken literally:
`_depth == 0 and name in helpers` (`:1552`) stops exactly one frame short, so inserting one more
`def` restores the hole the walk was added to close. R3 is `fn.name.startswith("_")` (`:1578`);
R4 is `_TURN_MODULES` (`:1524`), a two-element tuple.

The builder's disclosure — *"it matches by called name … it also cannot see a narrowing that happens
inside a callee rather than at a call site named here"* — is generic enough to gesture at R1/R2 and
specific enough to have been checked against them, and was not: the class docstring simultaneously
presents the one-level walk as **the fix** for exactly this shape.

### 3 · `voice_stream_response` was armed — **FAIL**

**Falsifier:** the voice turn registering an outage that no consumer reads, or reaching the model
without the notice. I drove the real generator (`voice_stream_service.voice_stream_response`) with
STT/TTS/pool stubbed, the shared tool generator stubbed at its real signature, and the catalogue
outage produced by the **real** `KnowledgeClient._register_catalogue_outage`:

```
A. sink at the moment the model is called:
     [{"scope":"catalogue","stage":"catalogue_unavailable","reason":"list-tools failed: ConnectError"}]
B. outage registered?                 True     ← the arm works
C. model told (notice in messages)?   False
C2. message roles:                    ['system']
D. assistant INSERT columns:  message_id, session_id, owner_user_id, role, content, content_parts,
     sequence_num, model_ref, branch_id, local_date, finish_reason, outcome, runtime_variant,
     advertised_tools, tool_calls
    mentions withheld_tools?          False
E. sink AFTER the turn:  [ …the same row, never drained… ]
```

So the fourth entry point now arms a sink that (i) **no code drains** — `voice_stream_service.py`
contains no `AdvertisedToolsRecorder` and ignores the `advertised` chunk (`chunk_data.get("content",
"")` at `:482`), (ii) **cannot be persisted** — the voice INSERT at `:609-651` has no
`withheld_tools` column and binds `advertised_tools=None` by an explicit retraction, and (iii)
**never tells the model** — `CATALOGUE_UNAVAILABLE_NOTICE` and `catalogue_outage_registered()` do
not appear in the module.

§0.14.3 is explicit that U-2 is **two halves** and *"shipping only the first would repeat the defect
that started this work."* Voice ships neither. What was shipped is the thing the gate can see. The
suite is `362 passed` over that.

### 4 · U-1's admin door — **PASS on both fixes**, with the sibling neither reached

**Falsifier:** a branch of either door that narrows the whole catalogue without registering; a field
of the admin definition still stored decomposed.

**Both fixes verified by execution.** Every branch of both doors driven directly:

```
user   / mcp-not-installed -> []  registered=1  [{'scope':'catalogue','reason':'mcp package not installed'}]
user   / transport raises  -> []  registered=1  [{'scope':'catalogue','reason':'list-tools failed: RuntimeError'}]
admin  / mcp-not-installed -> []  registered=1  [{'scope':'catalogue','reason':'mcp package not installed'}]
admin  / transport raises  -> []  registered=1  [{'scope':'catalogue','reason':'list-tools failed: RuntimeError'}]
admin  / no admin_token    -> []  registered=0  []                        ← the sibling
```

and the composition, both doors, same NFD input:

```
admin description NFC?  True     admin schema NFC?  True     user description NFC?  True
```

**The sibling neither fix reached: `if not admin_token: return []` (`knowledge_client.py:713-714`).**
It is the third early return of the same method — the two round-9 fixes landed on the other two — and
it returns an empty catalogue with no log line, no record and no notice. **It is reachable by
construction**: `admin_context` is a *body* field (`routers/messages.py:540`) while `admin_token` is
`Header(default=None)` (`:355`), so the two are independent, and `stream_service.py:5612` gates the
fetch on `admin_context` alone. Driven end-to-end, with the token-present case as the control:

```
[admin_token=None]        tool loop entered? True   NOTICE REACHED MODEL: False   withheld_tools = None
[admin_token='adm-token'] tool loop entered? True   NOTICE REACHED MODEL: True    withheld_tools = None
```

An admin whose token is missing or expired holds an empty surface, is told nothing, and leaves no
row. That is P1's counter-example verbatim, in the method both fixes were applied to.

**And neither fix is guarded.** Deleting the admin `mcp package not installed` registration the
round just added leaves the suite **green** (I4). So does deleting the *user* one (I8). The
parametrised `test_EVERY_catalogue_path_registers_on_a_real_failure` drives only the
transport-exception branch of each door — which is exactly what round 8 wrote about this sibling.
The correction was made where the reviewer pointed and the *coverage* gap that let it hide was not.

---

## 3 · The bypass table

| the property asserts | the path that defeats it | measured? |
|---|---|---|
| U-2 · "a catalogue outage **registers**" | the drain hangs off the `advertised` chunk; an outage makes the turn tool-free, so no chunk, no drain, `withheld_tools = NULL` | ✅ 3 of 4 shapes NULL |
| " | voice has no `withheld_tools` column in its INSERT at all | ✅ column list captured |
| U-2 · "…**and** the model is told" | voice never emits `CATALOGUE_UNAVAILABLE_NOTICE` | ✅ `told=False` |
| " | an admin turn with `admin_context` and no `X-Admin-Token` registers nothing, so the notice is not gated on | ✅ `told=False`, control `told=True` |
| §0.14.3 · declaration rows carry `scope` | the drain discards it; `record_withheld` never writes one | ✅ `SCOPE_DECLARATION` reaches the column: False |
| §0.14.3 · "no `tool: "*"` sentinel" | `stream_service.py:2349` mints one and `:6985` accepts it | ✅ persisted beside the outage row |
| arm gate · "no narrowing precedes the arming" | the fetch extracted into a helper in **another module** (R1) | ✅ gate `5 passed`, defect e2e |
| " | **two** levels of module-local helper (R2) | ✅ gate `5 passed`, defect e2e |
| " | a turn entry point whose name starts with `_` (R3) | ✅ gate `5 passed` |
| " | a turn entry point in a module outside `_TURN_MODULES` (R4) | ✅ gate `5 passed` |
| the P0 · "a scope row cannot reach a `tool` consumer" | none found — enumerated every `["tool"]` under `app/services`, `app/client`, `app/routers`, executed the two on the sink path; `git grep withheld_tools` repo-wide for a reader; `grep -rn withheld frontend/src` | — |
| `count` · "absent when unknown, never 0" | none found — driven cold and warm, at the client, the recorder and the column | — |

---

## 4 · The red-ability table

Baseline for every row: **scratch copy, five named suites = `361 passed, 1 failed`**, the one failure
being `test_the_gate_actually_RUNS_in_ci` (reads `.github/`, absent from the copy). In-tree baseline
`362 passed`. Each injection applied to the scratch copy and reversed by restoring a pristine
snapshot — never `git checkout`.

| # | injection | what it models | result |
|---|---|---|---|
| I1 | drain reverts to `_sw["tool"]` | the P0 itself | **1 extra failure** — `test_A_DEGRADED_CATALOGUE_DOES_NOT_KILL_THE_EDITOR_TURN` |
| I2 | `withheld_json`'s `scope` clause removed | the P0's second copy | **3 extra** — incl. both new instrument tests |
| I3 | voice's `arm_turn_surface()` deleted | the round-9 voice fix | **2 extra** — both arm-gate tests |
| **I4** | **admin `mcp package not installed` registration removed** | **the round-9 admin fix** | **GREEN — `361 passed`** |
| I5 | admin description/schema no longer composed | the round-9 U-1 admin fix | **1 extra** — `test_THE_ADMIN_INGESTION_PATH_COMPOSES_TOO` |
| I6 | `count` fabricated as `count or 0` | §0.14.3's "absent ≠ zero" | **3 extra** |
| I7 | `record_catalogue_withheld` drops the row | the recorder made inert | **2 extra** |
| **I8** | **user `mcp package not installed` registration removed** | the sibling of I4 | **GREEN — `361 passed`** |
| I9 | user transport-failure registration removed | U-2's original n=1 | **2 extra** |
| **R1** | catalogue fetches → helper in a neighbouring module, arm drifts | a routine refactor, one file over | **arm-gate `5 passed` — GREEN**, notice stops reaching the model |
| **R2** | the same, through two levels of helper | the depth-1 boundary | **arm-gate `5 passed` — GREEN**, notice stops reaching the model |
| **R3** | `_`-prefixed unarmed entry point | discovery's name filter | **arm-gate `5 passed` — GREEN** |
| **R4** | unarmed entry point in a third module | `_TURN_MODULES` | **arm-gate `5 passed` — GREEN** |

**I4 and I8 together are the sharpest row.** Both doors' *"mcp package not installed"* branches can
be deleted with the suite green. One of them is the fix this round shipped.

---

## 5 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| the drain's scope dispatch (`stream_service.py:6975`) | every other consumer that indexes `tool` | enumerated `["tool"]` under `app/services`, `app/client`, `app/routers`; executed both sink consumers; `git grep withheld_tools` repo-wide + `frontend/src` | **YES** — `instrument.py:589` fixed, and no third consumer exists |
| the record's `scope` field | the **declaration** half of the same field | ran the production drain verbatim and read the output | **NO** — `record_withheld` writes no `scope`; `SCOPE_DECLARATION` never reaches the column, contradicting §0.14.3's own table |
| §0.14.3's rejection of `tool: "*"` | every producer of a withheld row | grepped the drain's two inputs; read `stream_service.py:2249` and `:2345` | **NO** — `:2349` mints `"*"`, `:6985` accepts it |
| the row must *register* | the other turn shapes' drain | drove agui, plain, admin×2, voice and captured the `withheld_tools` bind | **NO** — written on 1 of 4; voice has no column |
| voice's arming | the two halves the arming exists to serve | drove the real voice generator; grepped the module for the recorder, the notice and `catalogue_outage_registered` | **NO** — neither drained nor told |
| admin `mcp not installed` registration | the *third* early return of the same method | read all three branches; executed each | **NO** — `if not admin_token: return []` registers nothing, and is reachable (body field vs optional header) |
| admin `mcp not installed` registration | its **test** | I4, then I8 on the twin | **NO** — both branches untested on both doors |
| admin door composition | the user door's `_meta` handling | executed both doors on the same tool with `meta` | **N/A but notable** — the admin door carries no `_meta` at all and stores no `_catalog_meta`; nothing to normalise, so U-1 is complete, but the two doors return different shapes |
| the arm-order gate's one-level walk | the module boundary and the depth boundary | R1, R2 against the real module + e2e | **NO** — both green |
| entry-point discovery | names and modules the filter excludes | R3, R4 | **NO** — both green |

---

## 6 · Where the builder's documentation of a residual is incomplete or wrong

1. **`TestTheTurnSinkIsArmedBeforeAnythingNarrows`'s disclosure is incomplete by four.** It names the
   alias and "a narrowing inside a callee"; `_narrowings_in`'s docstring presents the one-level walk
   as *"the fix for the hole that mattered most"* and says *"a boundary drawn at one stack frame is a
   boundary a refactor crosses by accident"* — while the walk itself stops at one stack frame and one
   module. R1 and R2 are that sentence, measured, with the end-to-end defect reproduced.
2. **`voice_stream_response`'s new comment is true and its implication is not.** It says the voice
   turn *"fetches the same federated catalogue and narrows it the same way, so everything it
   withholds — including a whole-catalogue outage — registered nowhere."* After the fix it registers
   into a list nothing reads, on a path whose INSERT has no column for it, on a turn whose model is
   never told. "Registered nowhere" became "registered into nowhere". Nothing in the tree records
   that as open.
3. **`record_catalogue_withheld`'s docstring, *"a record shape and its consumer are ONE change"*, is
   the right lesson applied to one consumer.** The consumer that decides whether the row is ever
   written — the `if _adv_ev is not None` guard around the drain — is not addressed, and it is the
   one the outage itself disables.
4. **§0.14.3's `declaration` row shape is not what the code writes.** `{scope, tool, stage, reason,
   pass}` is documented; `{segment, tool, stage, reason, pass}` is stored. Measured.
5. **`ARCHITECTURE.md:1424` still declares `withheld_tools` as `[{tool, stage, reason}]`** — the row
   §0.14.3 designed is inadmissible to the SSOT table two hundred lines earlier, and the
   `declaration` row does not match it either.
6. **The admin fix's own residual is unstated:** the `not admin_token` branch, and the absence of any
   test for either door's `mcp not installed` branch. Round 8 named the coverage gap; round 9 fixed
   the code the gap was hiding and left the gap.
7. **Exemplary, and worth naming:** `test_ALL_THREE_TURN_SHAPES_reach_the_notice`'s docstring now
   *retracts* its "a fourth entry point cannot inherit the silence" claim in place, explains that it
   checks two names and nothing else, and points at the test that does discovery. That is the correct
   form, and it is the reason I could grade item 3 against the right property instead of the label.

---

## 7 · What would have to be true for this to PASS

* **The drain must not be conditional on the turn having offered tools.** The sink is armed at the
  top of the turn; it should be drained at the terminal path, not inside the `advertised` chunk
  handler. Until then U-2's first half holds on one surface.
* **`voice_stream_response` must drain and tell**, or the voice INSERT must gain the column and the
  turn the notice. An arm with no reader satisfies the gate and nothing else.
* **The arming property needs an anchor that is not a parse tree over a hand-listed pair of
  modules.** The cheapest honest version is still the one round 8 proposed: assert at **runtime**
  that `record_catalogue_unavailable` / `record_surface_withheld` never find
  `surface_withheld.get() is None` on a request-scoped path.
* **`get_admin_tool_definitions(None)` must register**, and both doors' `mcp not installed` branches
  must be covered — I4 and I8 must red.
* **A declaration row must carry `scope`**, or §0.14.3's table must say that it does not.

`git rev-parse HEAD` at start: `86ae725929215cbb20201308db1120b0855f1222`.
`git rev-parse HEAD` before writing: `86ae725929215cbb20201308db1120b0855f1222`.
