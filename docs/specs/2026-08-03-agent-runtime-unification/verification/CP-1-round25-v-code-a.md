# CP-1 · round 25 · V-CODE **Verifier A** — the instruments

> **VERDICT: FAIL.**
> The two instrument enumerations the delta publishes as complete are both **lower bounds by a
> large factor, measured**: the 8-cell write guard is blind to **14 further write APIs** (one of
> them the API of this run's own `%TEMP%`-deletion incident), and the 17-shape CI check stays
> **GREEN under 19 of 22 disable shapes I enumerated**. Two of the four instrument fixes I was
> assigned bind a **proxy** rather than the property: W4's rule is installed at the `try` door and
> not at the `with` door, and T11d **reds on correct code — twice, cross-module —** while staying
> **blind to the same refactor one level out**. The probe-writer property gate is bypassed by a
> **dead mention of an identifier**. The three claims that survive intact are `_probe_offender`
> (a real oracle, re-derived), C3's per-writer leak property (2/2 red-able), and the
> transfer's load-bearing fact (zero importers) — though the transfer's *stated common cause* is
> false for one of the three items.

| | |
|---|---|
| **worktree** | `C:\Users\NeneScarlet\AppData\Local\Temp\claude\d--Works-source-lore-weave\f169eff6-bff5-4d6e-9ab7-c5df09bea346\scratchpad\r25-a` |
| **`git rev-parse HEAD` at start** | `c181a35253aea18f5da827163274964e8ecda4b9` |
| **`git rev-parse HEAD` at finish** | `c181a35253aea18f5da827163274964e8ecda4b9` |
| **tree at finish** | `git status --porcelain` empty — byte-clean. Every source mutation was restored by rewriting the exact bytes; `git checkout <file>` was never used |
| **FREEZE** | **held.** No file changed under me during the round. HEAD identical at both ends |
| **baselines executed** | CP-1 `144 passed / 17.96s` · CP-1 + CP-0 `284 passed / 50.48s` · `agentruntime-census.py --selftest` → `OK - 68 raise sites, fires on a guarded one`, rc 0 · `agentruntime-membrane-gate.py` → `OK - 8 module(s), 0 allowed external import(s)` |
| **census (full, ~20 min)** | **SKIPPED, deliberately.** Stated rather than omitted. The delta's `68/9/59` is the builder measuring the builder's own instrument and none of my findings turn on the count; C3's leak property I measured **per writer by reversion**, which is strictly stronger than inspecting a run's aftermath. I did run `--selftest` (both directions) and counted `%TEMP%` around it: **0 mirrors before, 0 after.** |

---

## 1 · The falsifier per claim

| # | claim graded | falsifier I ran | outcome |
|---|---|---|---|
| C1 | "Both writers are now driven with every write API wrapped and **all eight cells** enumerated as controls" | AST-inject a live-tree write through **19 write APIs** into `census()`, drive it through a **verbatim clone** of the guard's own watcher, and check both (a) whether the watcher recorded it and (b) whether the file system actually changed | **REFUTED — 14 of 19 APIs invisible** |
| C2 | "**17 shapes**, each of which must make the check raise" | Enumerate **22 further disable shapes** and run each through the guard's own `_assert_census_ci` | **REFUTED — 19 of 22 stay GREEN** |
| C3 | "Each writer now frees its mirror in a `finally` … each returns having removed the directory it was given. Measured: **0 leaked directories**" | Revert `_discard(mirror)` **separately in each writer**; and separately, make `_mirror()` itself fail after `mkdtemp` | **HOLDS for the two writers (2/2 red). A third, unguarded leak site found: `_mirror()` itself** |
| 6 | W4 — "`s.body[:1]` … plus a control, so a `[:0]` overshoot cannot pass either" | Drive the real `_turn_entry_calls()` over an arm that is the **second statement of a `with`**, and of a `with` nested as the first statement of a swallowing `try` | **REFUTED as a property — bound at the `try` door only** |
| 7 | the three weak oracles — "bound to the offender **sentence** … only the offender-sentence form reds" | Break the gate's `>= 4` anchor to `>= 99` — a red having nothing to do with any probe — and run the **four** `_probe_offender`-bound probe tests | **HOLDS — 4 passed pristine, 4 failed under the unrelated break** |
| 8 | T11d — "column-name aliases resolved to a fixed point; **4 vehicles**" | (a) revert the alias fixed point and re-drive each vehicle **individually**; (b) hoist the **table** name as well; (c) construct correct code that the alias set convicts | **PARTLY REFUTED — 3 of 4 vehicles bind the fix; blind on the table hoist; 2 independent false positives on correct code** |
| 9 | probe writers — "`_swept_root()` **+ a property gate**, so the seventh writer cannot arrive typed" | Append 8 probe-writer shapes to the real file, run the real gate, restore byte-exactly | **REFUTED — 2 of 8 caught; a DEAD mention of `_swept_root` absolves a typed root** |
| 5 | the transfer — "The load-bearing fact is that `agentruntime` has zero importers outside the package" | `grep` every `import` of `app.agentruntime` and of `app.services.instrument` across `services/` and `scripts/` | **fact HOLDS; the stated *common cause* is FALSE for one of the three items** |

---

## 2 · Bypass table

### 2a · C1 — the ninth cell, and the ninth cell is fourteen cells

Executed: one writer (`census`) × 19 APIs, each injected by AST as the writer's first statement, run
through a **byte-for-byte clone** of the guard's watcher (`Path.write_bytes`, `Path.write_text`,
`Path.open`, `builtins.open`). `CAUGHT` = the watcher recorded it. `BLIND` = the watcher saw nothing
**and the file system actually changed** (verified per cell by globbing the repo root).

| # | write API | seen by the guard? | note |
|---|---|---|---|
| 1 | `Path.write_bytes` | **CAUGHT** | the guard's own cell |
| 2 | `Path.write_text` | **CAUGHT** | the guard's own cell |
| 3 | `Path.open('wb')` | **CAUGHT** | the guard's own cell |
| 4 | `builtins.open('w')` | **CAUGHT** | the guard's own cell |
| 5 | `shutil.copyfile` | **CAUGHT** | incidentally — it goes through `builtins.open` |
| 6 | `io.open('w')` | 🔴 **BLIND** | `io.open` is a separate module attribute; patching `builtins.open` does not touch it |
| 7 | `os.open` + `os.write` | 🔴 **BLIND** | |
| 8 | `Path.touch()` | 🔴 **BLIND** | |
| 9 | `Path.mkdir()` | 🔴 **BLIND** | |
| 10 | `shutil.copytree` | 🔴 **BLIND** | uses `os` primitives, not `open` |
| 11 | `os.replace` | 🔴 **BLIND** | the atomic-write idiom |
| 12 | `os.rename` | 🔴 **BLIND** | |
| 13 | `tempfile.NamedTemporaryFile(dir=ROOT, delete=False)` | 🔴 **BLIND** | |
| 14 | `subprocess` writing the path | 🔴 **BLIND** | and the census already imports `subprocess` |
| 15 | `os.link` | 🔴 **BLIND** | |
| 16 | `mmap` over an `os.open` fd | 🔴 **BLIND** | |
| 17 | `os.remove` of a live file | 🔴 **BLIND** | a **deletion** is a write, and no cell in the guard is destructive |
| 18 | `Path.unlink` of a live file | 🔴 **BLIND** | |
| 19 | **`shutil.rmtree` of a live directory** | 🔴 **BLIND** | ⬅ **the ninth cell that matters** |

**Result: 5 caught / 19. `{2 writers} × {4 APIs}` is not the space; it is the space the previous
verdict happened to name, and the guard's controls were built to match it.**

**Why #19 is the one to fix first, and it is not hypothetical.** `scripts/agentruntime-census.py`
calls `shutil.rmtree` on a path returned by `_mirror()` in **three** places — `_discard()`, the
`atexit` lambda in `census()`, and `_selftest()`'s `finally`. `_mirror()` is monkeypatchable and *was*
monkeypatched. The docstring of `_own_mirror` records what happened the last time that path was
wrong: *"it deleted the system temp directory … the most likely cause of six 'another process deleted
my output file' failures that were blamed on the environment for an evening."* **The guard written
after that incident cannot observe the API that caused it.** All four of its cells are creation APIs.
Worse, the guard's own safety claim — *"the interception records the write and **stops** it, so a
control cannot leave debris"* — is only true for the four APIs it patches: I confirmed by execution
that an `rmtree` control **actually destroys the directory**, so an honest control for cell 19 cannot
be written in the guard's current shape at all.

### 2b · C2 — the CI check, over my own enumeration

Executed against the guard's own `_assert_census_ci`, on the real `lint-foundation.yml`.
**24 shapes: 22 new + 2 of the builder's as controls. 19 new shapes stay GREEN.**

| family | shape | check | why the check cannot see it |
|---|---|---|---|
| scheduling | `runs-on: [self-hosted, never-exists]` | 🟢 **GREEN** | `runs-on` is never read |
| scheduling | `needs: [lint]` where `lint` is `if: false` (dependent is **skipped**, workflow succeeds) | 🟢 **GREEN** | `needs` is never read |
| scheduling | `strategy.matrix` with every combination `exclude`d → zero jobs | 🟢 **GREEN** | `strategy` is never read |
| triggers | `paths-ignore: ['**']` on both triggers | 🟢 **GREEN** | only the trigger **keys** are checked, never their values |
| triggers | `paths: ['docs/**']` | 🟢 **GREEN** | ditto |
| triggers | `branches: [no-such-branch]` | 🟢 **GREEN** | ditto |
| triggers | `pull_request: {types: [labeled]}` — never fires on a PR push | 🟢 **GREEN** | ditto |
| triggers | `pull_request` deleted; push-to-`main` only — **never gates a PR** | 🟢 **GREEN** | the check is `{"push","pull_request"} & set(triggers)`, an **intersection**: one key suffices |
| shell | workflow-level `defaults.run.shell` swallowing rc | 🟢 **GREEN** | `defaults` is never read |
| shell | job-level `defaults.run.shell` swallowing rc | 🟢 **GREEN** | ditto |
| shell | step-level `shell:` swallowing rc | 🟢 **GREEN** | the step's `shell` key is never read |
| command | `python … census.py ; true` — **same line** | 🟢 **GREEN** | the `exit 0`/`true` check is `line.strip() in ("exit 0","true")`, i.e. per **whole line** |
| command | `python … census.py &` — backgrounded, rc 0 immediately | 🟢 **GREEN** | |
| command | `python … census.py \| cat` — pipeline rc is `cat`'s | 🟢 **GREEN** | only `\|\|` is checked, not `\|` |
| command | `echo python … census.py` | 🟢 **GREEN** | the check is a substring test over the run text |
| command | `python … census.py --help` | 🟢 **GREEN** | only `--write`/`--selftest` are refused |
| command | `if false; then … fi` | 🟢 **GREEN** | |
| command | `trap 'exit 0' ERR` before it | 🟢 **GREEN** | |
| structure | a second job runs the real census; this step is `echo stub  # python … census.py` | 🟢 **GREEN** | the comment-stripper runs per **line**, and this `#` is mid-line |
| command | `( python … census.py ) \|\| :` | 🔴 CAUGHT | by the `\|\|` clause |
| structure | the step becomes a composite action (`uses:`) | 🔴 CAUGHT | no step has the script in `run` |
| structure | the job becomes a reusable-workflow call | 🔴 CAUGHT | the job has no `steps` |
| *(control)* | the job is deleted | 🔴 CAUGHT | builder's shape |
| *(control)* | `\|\| true` | 🔴 CAUGHT | builder's shape |

**Not in the repo and therefore unmeasurable from it: branch protection not requiring the job.** That
is the twentieth shape and no YAML check can ever see it. It should be recorded as a permanent,
named residual rather than left implicit.

**Structural reading:** every clause of `_assert_census_ci` lives in one narrow family — *the text of
a `run:` string, plus `if`/`continue-on-error` at two levels*. It never reads `defaults`, `shell`,
`runs-on`, `needs`, `strategy`, or **any trigger value**. The builder's "removing any one clause
reopens exactly one shape — 9/9" is true and is the wrong measurement: it establishes the clauses are
non-redundant *within the family they cover*, not that the family is the space.

### 2c · Item 9 — the probe-writer property gate

Executed by appending each shape to the real `test_cp0_instrument.py`, running the real gate,
restoring byte-exactly. Pristine: GREEN.

| # | shape | gate |
|---|---|---|
| 1 | `Path(...).parents[1] / "app"` — the shape the gate names | 🔴 CAUGHT |
| 2 | `.joinpath("app")`, no `_swept_root` mention | 🔴 CAUGHT (by the *second* half) |
| 3 | `.joinpath("app")` **plus a dead `_ = _swept_root`** | 🟢 **BYPASS** |
| 4 | writes via `open(path, "w")`, root typed | 🟢 **BYPASS** |
| 5 | writes via `shutil.copyfile`, root typed | 🟢 **BYPASS** |
| 6 | `write_text` inside a **lambda** | 🟢 **BYPASS** |
| 7 | write at **module scope** | 🟢 **BYPASS** |
| 8 | an unrelated local named `_sweep` absolves the function | 🟢 **BYPASS** |

**2 of 8.** Shape 3 is the headline and it is this run's signature failure with a new spelling: the
second half asserts only that the **identifier** `_swept_root` or `_sweep` *appears somewhere in the
function*, not that the written path derives from it. *A test satisfied by a comment is not a test* —
this is a **test satisfied by a token**, and it is the fourth instance of the pattern. Shapes 4–7 are
the first half's real hole: it matches a `BinOp(/)` with the literal `"app"` on the right, so
`.joinpath("app")`, `os.path.join`, and string concatenation all walk past it, and only an
attribute call named `write_text`/`write_bytes` triggers the second half at all.

---

## 3 · Red-ability table — **with my own denominator**

| item | builder's denominator | **my denominator** | bound / total | how measured |
|---|---|---|---|---|
| C1 write guard | 8 cells (2 writers × 4 APIs), 8/8 | **19 APIs** × 2 writers = **38 cells**; I drove 19 on `census` | **5 / 19** | AST injection through a verbatim watcher clone + filesystem verification |
| C2 CI check | 17 shapes, 17/17 | **39** (17 builder + 22 mine) | **20 / 39** | each shape through the real `_assert_census_ci` |
| C3 mirror leak | "per writer", 2 | **3 sites** (`census`, `_selftest`, **`_mirror`**) | **2 / 3** | reverting `_discard` separately in each writer; injecting failure into `_mirror` |
| 6 · W4 | 1 test + 1 control | **6 cells** ({`try`,`with`,`async with`} × {1st, 2nd statement}) | **2 / 4** non-trivial cells bound (`try` 1st and 2nd) | real `_turn_entry_calls()` over three written probe modules |
| 7 · the oracles | 3 tests, 2×2 | **4** tests carry `_probe_offender` (the builder's prose says three) | **4 / 4** ✅ | anchor broken `>=4`→`>=99`, an unrelated red |
| 8 · T11d | "4 vehicles" | **4 vehicles + 1 table-hoist + 2 false-positive vehicles = 7** | **3 / 4** vehicles bind the fix; **0 / 1** table hoist; **2 / 2** false positives fire | per-vehicle drive with the alias fixed point reverted |
| 9 · probe writers | 1 property (2 halves) | **8 vehicles** | **2 / 8** | append-run-restore against the real gate |

### 3a · T11d, per vehicle — the reversion the delta names is *"the alias set stops accepting members"*

| vehicle | pristine | T11d reverted | binds the fix? |
|---|---|---|---|
| interpolated column name | CAUGHT | **BLIND** | ✅ |
| column name through TWO bindings | CAUGHT | **BLIND** | ✅ |
| `segment_merge_sql` on a hoisted name | CAUGHT | **BLIND** | ✅ |
| **bare-name `segment_merge_sql`** | CAUGHT | **CAUGHT** | ❌ — caught with the fix gone; it is a *T9 bare-name-executor* vehicle, already covered |

**3 of 4.** The delta's "4 vehicles" over-counts by one.

### 3b · T11d — blind, and red on correct code

*The alias set on the pristine tree is EMPTY.* I recomputed the gate's own `_col_aliases` fixed point
over `app/` at this commit: **`|_col_aliases| = 0`**. So the delta's framing — *"SIX ROUNDS, AND THE
SUBJECT IS THE LIVE WRITE"* — is not what the code measures today: **no live write uses a hoisted
column constant.** The fix is prospective, which is fine and is not what it says.

**(i) BLIND on the table hoist — the same refactor one level out.**
```python
_COL = "withheld_tools"
_TBL = "chat_messages"
async def probe_write(conn, mid):
    await conn.execute(f"UPDATE {_TBL} SET {_COL} = $1 WHERE message_id = $2", None, mid)
```
→ **gate GREEN.** Root cause: `_names_the_column` flattens with `ast.walk`, which is **breadth-first**,
so an alias's spelling is always appended **after** every literal in the expression. `withheld_tools =`
is therefore never contiguous, and the only surviving anchors are the *literal* `UPDATE chat_messages`
/ `INSERT INTO chat_messages`. T11d survives the column hoist **only because the table name is still a
literal.** T9e is that exact refactor applied to the SQL; the delta cites T9e as the precedent and
then leaves its twin open. **Twelfth pair fixed at one end.**

**(ii) RED ON CORRECT CODE, twice, cross-module.** The prompt asks whether the over-approximation can
red correct code — *"a gate that reds on correct code is one that gets deleted."* It can:

```python
# module A — correct: the constant, i.e. exactly the refactor T11d exists to survive
_COL = "withheld_tools"

# module B — correct: never touches the column; `_COL` is an unrelated parameter
async def rename_content(conn, mid, _COL):
    await conn.execute(f"UPDATE chat_messages SET content = {_COL} WHERE message_id = $1", mid)
```
→ `services/…_fp_b.py::rename_content:2 writes 'withheld_tools' and NO argument of that call carries
the recorder's value` — **a false positive**, because `_col_aliases` is global and there is no import
graph. The same construction fires through `global_sql_names`:

```python
# module C
_SQL = "UPDATE chat_messages SET withheld_tools = $1 WHERE message_id = $2"
# module D — correct: a generic executor helper
async def run_any(conn, _SQL, arg):
    await conn.execute(_SQL, arg)
```
→ **false positive** on `run_any`. Both executed.

**What the over-approximation costs, answered:** not "a few extra binds to check", as the comment
says. It costs **the identifier namespace of the entire `app/` tree**. Any name bound anywhere to
`"withheld_tools"` — or to SQL naming it — convicts every *other* module that reuses the identifier
in an executor call whose expression also carries a table verb. With generic spellings (`_COL`,
`col`, `column`, `_SQL`, `sql`, `q`) that is a normal thing to write.

### 3c · W4 — the rule is at the `try` door and not at the `with` door

Executed against the real `_turn_entry_calls()`:

| probe | `arms` | `conditional` | verdict |
|---|---|---|---|
| arm 2nd in a `try` body (**W4's own vehicle**, positive control) | `[6]` | `[6]` | ✅ CONDITIONAL — the gate sees it |
| arm 2nd in a **`with`** body | `[7]` | `[]` | 🔴 **UNCONDITIONAL — blind** |
| arm 2nd in a **`with` nested as the 1st statement of a swallowing `try`** | `[8]` | `[]` | 🔴 **UNCONDITIONAL — blind** |

`_unconditional_calls` recurses `s.body[:1]` for `ast.Try` and **`s.body` in full** for
`With`/`AsyncWith`, eight lines apart in the same function. The third probe is W4's exact defect
restored: the arm runs only if `await c.get_preferences()` did not raise, the handler swallows, and
the turn then narrows into a sink nothing armed — with the gate reporting the arm **unconditional**.

**Reachability, measured not guessed:** the three real turn entry points contain **2 `async with`
statements and 20 `try` statements**; `app/` contains **45 `with`/`async with` statements, 20 of them
with multi-statement bodies**. The shape is ordinary here. W4's own standard — *"a preceding `await`
is exactly what a real turn does before it arms"* — applies verbatim to `async with`.

### 3d · the three (four) weak oracles — **the one claim that fully holds**

`_probe_offender` is carried by **four** tests, not three (`…sees_a_writer_in_ANY_module`,
`…SQL_HOISTED_TO_A_MODULE_CONSTANT`, `…THE_COLUMN_NAME_HOISTED_TO_A_CONSTANT`,
`…EVERY_SPELLING_OF_THE_SAME_WRITE`). Breaking the gate's anchor from `>= 4` to `>= 99` — a red with
nothing to do with any probe — gives:

* pristine gate: **4 passed**
* anchor broken: **4 failed**

The old `match="withheld_tools"` oracle and the builder's first repair both stayed green under this
break; the offender-sentence form does not. **Re-derived independently, and it holds.** The
offender sentence exists in exactly one assertion, and `binds_checked` renders `mod::fn:line` with no
following ` writes`, so the anchor's message cannot satisfy the pattern.

Residual, and it is small: the pattern binds *"my probe was reported as an offender"*, not *"for the
reason this probe tests"* — which is exactly why the per-vehicle attribution in §3a was necessary and
is what exposed the fourth T11d vehicle.

---

## 4 · Sibling table — **for every fix, is its twin fixed too?**

| fix | its twin | twin fixed? |
|---|---|---|
| `census()` frees its mirror | `_selftest()` frees its mirror | ✅ **yes** — 2/2 red under separate reversion. The eleventh pair, finally closed at both ends |
| both writers free their mirror | **`_mirror()` frees what it allocated when it fails** | 🔴 **NO** — measured: leaks 1 dir when `git ls-files` fails (**S1**), and 1 dir holding a *partial repo copy* when the copy loop raises (**S2**). Neither writer's `try` has been entered, so neither `finally` covers it and `census()`'s `atexit` is not yet registered |
| W4 truncates a **`try`** body to `[:1]` | the same rule for **`with` / `async with`** | 🔴 **NO** — measured blind |
| T11d resolves a hoisted **column** name | a hoisted **table** name (T9e's own refactor) | 🔴 **NO** — measured blind |
| the write guard watches **4 creation** APIs | the **deletion** APIs the census actually calls (`shutil.rmtree` ×3 call sites) | 🔴 **NO** — measured blind, and it is the API of the recorded `%TEMP%` incident |
| the CI check refuses `\|\|` | `\|`, `;`, `&`, `trap`, `if false` | 🔴 **NO** — all measured green |
| the probe-writer gate refuses a typed `/ "app"` | `.joinpath("app")`, `os.path.join`, concatenation | 🔴 **NO** — measured green (caught only incidentally, via the second half) |
| the probe-writer gate requires deriving from `_swept_root` | requiring the **path** to derive from it, not the **name** to appear | 🔴 **NO** — a dead `_ = _swept_root` absolves it |

---

## 5 · Guard table

| guard | binds the property, or the nearest proxy? |
|---|---|
| `test_NEITHER_CENSUS_WRITER_CAN_REACH_THE_LIVE_TREE__all_8_cells` | **proxy.** The property is *"the instrument cannot modify the live tree"*; the guard binds *"the instrument cannot modify the live tree **through four creation APIs**"*. Its two "drive is a drive" assertions (`len(results) >= 50`, `rc == 0`) are genuine and worth keeping |
| `_assert_census_ci` + the 17 shapes | **proxy.** The property is *"the census gates a PR"*; the check binds *"the `run:` string of a step named in one job is not one of eleven textual disablements"* |
| `_discard` / `_own_mirror` + the leak assertion | **property**, for the two writers it names. Denominator short by one site |
| `_unconditional_calls` `s.body[:1]` (W4) | **proxy.** The property is *"a statement that can raise does not precede the arm inside an unconditionally-entered block"*; the token binds it for `Try` only |
| `_probe_offender` | **property.** ✅ Re-derived under an unrelated break |
| T11d alias fixed point | **proxy, and in both directions.** Under-approximates (table hoist) and over-approximates into false positives (no import graph). 3/4 vehicles bind it |
| `test_EVERY_PROBE_IS_WRITTEN_INTO_THE_TREE…` | **proxy of a proxy.** Half 1 binds one syntactic form of one spelling; half 2 binds *an identifier appearing in the function*, not the path deriving from it |

---

## 6 · Item 5 — the transfer, challenged

**The load-bearing fact is TRUE and I checked it myself.** Every `import` of `app.agentruntime`
outside `services/chat-service/app/agentruntime/` is in **`tests/test_cp1_membrane.py`** or in
**`scripts/agentruntime-membrane-gate.py`** (the gate's own import probe). **Zero production
importers.** `services/chat-service/app/agentruntime/surface.py:27` defines `rows_of`; nothing
outside the package calls it. B18-10's fifth door has no consumer for the same reason.

**But the criterion is stated once and applied three different ways, and for one item its stated
common cause is false.**

| transferred item | criterion as written: *"no SUBJECT until a later checkpoint's code exists"* | honest? |
|---|---|---|
| `rows_of` document-level stamp check | The **subject exists today** (the function is in the tree and is V-CODE-readable; R20-B *did* measure it). What does not exist is a **caller**. So the applicable criterion is **unreachability**, not absence of subject | **honest in substance**, mis-stated in form |
| B18-10, the fifth exported door | identical — the door is in `__init__.py` today; the consumer is not | **honest in substance**, mis-stated in form |
| the catalogue-outage ordering residual | 🔴 **the stated common cause does not apply.** The subject is `AdvertisedToolsRecorder` / `surface_withheld` in **`app/services/instrument.py`**, which has **9 production importers today**, including both live turn entry points (`stream_service.py:50`, `voice_stream_service.py:43`), `routers/internal.py`, `main.py`, `tool_surface.py`, `tool_discovery.py`, `knowledge_client.py`. This code serves real turns **now**. It is transferred because **V-CODE cannot falsify an ordering claim from source**, which is a different and legitimate reason — but the RUNSTATE's *"The common cause, stated once: nothing outside `app/agentruntime/` imports it"* is **false for this item** | **transfer defensible, stated cause FALSE** |

**Was the criterion used to clear a board?** No — none of the three is a live CP-1 defect anyone can
act on today, and each has a real blocker. **But the paragraph that unifies them is wrong about one
of the three**, and it is the one that has consumed four verifiers over five rounds. That sentence
should be corrected in place, at the claim, not where a reviewer looked. Recommended wording: two
items move on **zero production reachability**; the third moves on **V-CODE non-falsifiability of a
runtime ordering**, with `instrument.py` explicitly noted as live today.

**Is any of the three measurable today? One is, partially.** `rows_of`'s missing document-level stamp
check is a **source property** and can be asserted today by a V-CODE test that calls `rows_of`
directly with a document whose stamp is absent/wrong — the function is importable and the membrane
suite already imports it. What cannot be measured today is whether any **production** path reaches it.
If the PO wants that row closed at CP-1 rather than carried, the honest split is: **assert the
behaviour now, carry the reachability to CP-2.**

---

## 7 · Reachability verdict on every finding

| # | finding | production-reachable **today**? | needs code that does not exist? |
|---|---|---|---|
| A-1 | CI check green under 19/22 disable shapes | ✅ **YES.** A one-line YAML edit, today, silently un-gates the census | no |
| A-2 | write guard blind to 14 APIs, incl. `shutil.rmtree` | ✅ **YES.** `shutil.rmtree(mirror)` runs on **every** census invocation, at three call sites, on a path from a patchable `_mirror()`. The recorded `%TEMP%`-deletion incident is this exact API | no |
| A-3 | `_mirror()` leaks on its own failure paths | ✅ **YES.** `git` absent/erroring, a permission error, or Windows path-length on a deep tracked path — and this verification workflow checks the repo out under a long temp path | no |
| A-4 | probe-writer gate: 6/8 bypasses, incl. the dead-token bypass | ✅ **YES** for the gate's own subject (the seventh probe writer). It does not affect production code | no |
| A-5 | W4 blind through `with`/`async with` | ⚠️ **latent.** The blind shape is a normal one here (45 `with`s under `app/`, 2 `async with` inside the entry points), but **no arm sits in one today** — the gate is green on the pristine tree for the right reason. Reachable by an ordinary refactor, which is precisely the standard W4/T9e/T11d are held to | no |
| A-6 | T11d blind on a table-name hoist | ⚠️ **latent**, same standard. Not present today | no |
| A-7 | T11d reds on correct code (2 vehicles) | ⚠️ **latent.** `\|_col_aliases\| = 0` on the pristine tree, so no false positive fires today. It arms itself the moment anyone performs the hoist T11d exists to survive | no |
| A-8 | 4th T11d vehicle does not bind the fix | ✅ **YES** (a documentation/denominator defect that exists now) | no |
| A-9 | transfer's stated common cause false for the catalogue-outage item | ✅ **YES** (a false sentence in the record now) | no |
| A-10 | branch protection not requiring the job | ✅ **YES**, and **unmeasurable from the repo by any check.** Must be a named standing residual | no |

**No finding in this verdict requires code that does not exist yet.** Six are actionable today; four
are latent behind one ordinary refactor each, which is the same status T11d itself had for six rounds
before it was closed.

---

## 8 · A method finding about my own harness, recorded before it is used against a result

My first restore of `test_cp0_instrument.py` used `Path.write_text`, which **rewrote 3,678 LF line
endings as CRLF** — byte-different, meaning-identical, `git status` dirty. The assertion I had
written (`read_text() == src`) **passed**, because `read_text` universal-newlines the file back. This
is the third recorded instance of that defect in this effort (a verifier's restore harness, the
census script, and `generate()` in production), and I reproduced it in the round whose job is to
catch it. Restored with `write_bytes` and LF; final `git status --porcelain` is **empty**.

Two consequences worth carrying:

* **`Path.write_text` must not be used by any restore in this workflow**, verifier or builder. The
  census already reads and writes bytes for this reason; the verification harnesses should say so too.
* **A restore assertion written with `read_text` cannot detect the failure it is guarding.** Restore
  assertions must compare **bytes**.

Note also that `test_cp0_instrument.py` and `test_cp1_membrane.py` are **LF**, not CRLF — the
round prompt's blanket "the tree is CRLF" is not true of the two files this round mutates.

---

## 9 · Convergence

| round | items I was asked to grade | independently refuted | fully upheld |
|---|---|---|---|
| R25-A | 8 (C1, C2, C3, W4, oracles, T11d, probe writers, transfer) | **5 refuted** (C1, C2, W4, T11d, probe writers) · **2 partial** (C3 holds + 1 new site; transfer holds + 1 false sentence) | **1** (`_probe_offender`) |

**Not converging on the instruments; converging on the membrane.** The distinction matters and the
delta already draws it: nine membrane/instrument *fixes* were shipped, and my scope found the
**instrument** enumerations short while `_probe_offender` and C3 — the two items the builder repaired
after a *control* told it the first repair was wrong — both survived independent re-derivation.
**That is the signal: every claim in this delta that was settled by a control held; every claim
settled by an enumeration the builder chose was short.** The builder said this in advance
(*"the ninth cell and the eighteenth shape are exactly what an independent round is for"*), which is
honest and does not make the counts less wrong.

**Prediction, falsifiable, for R26:** if C1 is repaired by adding the fourteen APIs I named as
fourteen more cells, the fifteenth will be found next round. The property is *"no syscall issued by
this process mutates anything under `ROOT`"*, and the only enumeration-free way to bind it is to
**hash the tracked tree's bytes continuously during the run** (or run the census with the repo
mounted read-only) rather than to patch a list of Python-level entry points. I predict a cell-list
repair reds under a `ctypes`/`os.startfile`/`pathlib` re-export vehicle I have not written.

---

## 10 · Executed-vs-argued — **my own denominator**

| | count |
|---|---|
| claims I made | **24** |
| **EXECUTED** (a command was run and its output is the evidence) | **18** |
| **ARGUED** (reasoning from source or from documented platform behaviour, no execution) | **6** |
| **ratio** | **18 / 24 = 75 % executed** |

The six argued claims, named so they can be attacked:

1. that `paths-ignore: ['**']` / `paths:` / `branches:` / `types:` narrowing actually prevents
   GitHub from running the workflow *(I executed only that the **check** stays green)*;
2. that a never-matching `runs-on` label, `needs:` on a skipped job, and a fully-excluded matrix
   produce a green-or-absent check on GitHub *(same caveat)*;
3. that `defaults.run.shell` / step `shell:` can be written to swallow `rc` on GitHub's runner;
4. that `&`, `\| cat`, `; true`, `if false`, `trap … ERR` and `echo` produce exit 0 under
   `bash -e` *(shell semantics, not executed in a runner)*;
5. that branch protection can omit the job — unmeasurable from the repository at all;
6. that `async with` behaves identically to `with` in `_unconditional_calls` — I read the code
   (`isinstance(s, (ast.With, ast.AsyncWith))`, one branch) but drove only `with`.

Every finding in §2–§7 rests on an **executed** claim. The argued six affect only *how bad* the CI
finding is, not *whether* the check is green — which is executed, 19 times.

---

## 11 · Verdict

**FAIL**, on the instruments, with the reason stated:

1. **Both enumerations the delta publishes as complete are short by a large factor, measured.**
   5/19 write APIs; 20/39 CI shapes. Neither is a CP-1 *property* — the RUNSTATE is right that they
   belong to whoever maintains the instrument — but **the PO's open decision is to close CP-1
   *against the census*.** A gate that can be turned off by nineteen one-line YAML edits with nobody
   informed cannot carry a checkpoint closure. **This finding is decision-relevant, not bookkeeping.**
2. **Two of the four instrument fixes in my scope bind a proxy**, and each has an unfixed twin one
   ordinary refactor away — W4 at the `with` door, T11d at the table name. The delta's own thesis
   (*"a repair finds what it was pointed at; a property finds the class"*) is the right one and was
   not applied to either.
3. **T11d reds on correct code, twice, cross-module.** By the prompt's own standard that is a gate
   that gets deleted.
4. **The probe-writer property gate is satisfied by a dead identifier**, which is the fourth
   instance of *a test satisfied by a token* in this run, and the second inside a repair for another.

**What I could NOT determine**

* Whether the census's live numbers (**68 sites / 9 silent / 59 red**, **0 NEWLY SILENT**) are
  correct — I skipped the 20-minute run deliberately and say so. `--selftest` fires in both
  directions and reports 68 sites, which is consistent, and is not the same claim.
* Whether `_selftest`'s four cells are as blind as `census`'s fourteen — I drove **one** writer × 19
  APIs rather than 2 × 19. The watcher is writer-independent by construction, so I expect the same
  result, but I did not execute it and will not claim it.
* Whether the 19 CI shapes produce a green **check on GitHub** as opposed to a green
  `_assert_census_ci` — see §10.
* Whether branch protection currently requires `agentruntime-census`. **Unmeasurable from the
  repository**, and it should be recorded as a permanent named residual rather than silently
  assumed.
* Anything about the membrane items 1–5 or `ID_MAX_LEN` — Verifier B's scope, not re-graded here.
