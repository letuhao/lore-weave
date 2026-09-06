# CP-1 · round 26 · V-CODE **Verifier A** — the instruments

> **PROVENANCE, added at re-emission and the only text not in the original.** The verdict below was
> written to `<worktree>/docs/specs/2026-08-03-agent-runtime-unification/verification/CP-1-round26-v-code-a.md`
> and destroyed when the coordinator removed the worktree. It is re-emitted here **verbatim from the
> authoring transcript** — no section is a reconstruction, nothing was re-graded, and no measurement
> was re-run. The worktree and scratch paths recorded in the header table are the paths the work was
> actually done in; the worktree no longer exists.

> **VERDICT: FAIL.**
> **A2's headline claim is refuted end to end.** The new gate binds the PATH, and the path set is
> *not* closed: **20 of 24 axis vehicles I enumerated are BLIND**, including the census's **own
> inner-loop shape** (`for p in sorted(PKG.glob('*.py')): p.write_bytes(...)`). And the union of the
> AST gate with the behavioural watcher below it does not close either — I made the census **create
> 8 directories inside the live `app/agentruntime/` package** with the CP-1 suite reporting
> **152 passed**. The gate's own no-vacuity assertion (`LIVE <= tainted_fns["census"]`) is a
> **tautology**, proved by renaming every live root out of the module and watching it pass.
> **A1's whitelist** leaves **4 of 11 trigger-narrowing keys** unread — including `branches-ignore`,
> the literal sibling of `paths-ignore` in the same dict — and its own failure mode is real: it
> constrains only steps that *spell* `agentruntime-census.py`. **A6 kept the very axis A2 abandoned
> in the same commit** (10 of 12 blind, and it reds on 2 correct-code vehicles). **A4** is fixed for
> its vehicle and blind one hoist out, **5 of 5**.
> What HELD, re-derived independently: **A5** (twin fixed at both doors, red-able), **A7** (property,
> red-able, leak reproduced, and its debris attribution verified), the **7 allowlist rows are the
> same SITES**, **B5's** unreachability, and **zero production importers**.

| | |
|---|---|
| **worktree** | `C:\Users\NeneScarlet\AppData\Local\Temp\claude\d--Works-source-lore-weave\f169eff6-bff5-4d6e-9ab7-c5df09bea346\scratchpad\r26-a` |
| **scratch directory** | `C:\Users\NeneScarlet\AppData\Local\Temp\claude\d--Works-source-lore-weave\f169eff6-bff5-4d6e-9ab7-c5df09bea346\scratchpad\scratch-a` |
| **`git rev-parse HEAD` at start** | `55871f6f3ba1e881bd704e5caf6dd30dd4a1820a` |
| **`git rev-parse HEAD` at finish** | `55871f6f3ba1e881bd704e5caf6dd30dd4a1820a` |
| **tree at finish** | `git status --porcelain` **empty**. Every mutation restored by `write_bytes` of the captured original and asserted with a **bytes** comparison (`read_bytes() == raw`). `Path.write_text` was never used by a restore; `git checkout <file>` was never used |
| **FREEZE** | **held.** No file changed under me. No file appeared under my scratch directory that I did not write |
| **baselines executed** | CP-1 + CP-0 `293 passed / 72.95 s` · CP-1 alone `152 passed / 12.75 s` · CP-0 alone `141 passed / 51 s` |
| **census (full, ~25 min)** | **SKIPPED, deliberately, and stated.** None of my findings turns on the 61/7 split, and for the claims that *are* about the census's numbers I ran something stronger than the run: I executed **the census's own `_sites`/`_shape_digest` over both revisions** to verify the site enumeration, the allowlist id mapping and the collision count exactly (§5). `lw-census-*` in `%TEMP%`: **0 before, 0 after** every pristine run |

---

## 1 · The falsifier per claim

| # | claim graded | the falsifier I ran | outcome |
|---|---|---|---|
| **A2** | "It binds the **PATH**, not the API … the set of expressions that can name the live tree is small and **closed**. One clause covers all nineteen vehicles and the twentieth nobody has written" | Enumerate **24 vehicles that attack the AXIS** — a path that reaches the tree without passing through `ROOT`/`PKG`/`CS`/`ALLOWLIST` — and run each through the gate's **real** `_offenders`, extracted from the test file's AST with no transcription | 🔴 **REFUTED — 20 of 24 BLIND** |
| **A2′** | (the same, end to end) "The behavioural drive stays below it" | Splice an **untainted path × unwatched API** into `census()` — a `for`-target over `PKG.glob` plus `os.makedirs` — and run the whole CP-1 suite | 🔴 **REFUTED — 8 directories created inside the live package, `152 passed`** |
| **A2″** | "the gate must be able to see the live roots at all — otherwise it is green over a module whose names were simply spelled differently" | Rename **every** live root out of the census module and re-evaluate `LIVE <= set(tainted_fns["census"])` | 🔴 **REFUTED — a tautology.** `tainted` is initialised to `set(LIVE)` |
| **A2‴** | `EXEMPT = {_mirror, main}` is honest | Splice a live-tree source write and an `rmtree(ROOT)` into each exempt function | 🔴 **4 of 4 BLIND** — the exemption is *whole-function*, not scoped to the stated reason |
| **A1** | "the structural keys are read … **and every trigger VALUE**. 36 shapes as controls" | Enumerate **all 11 GitHub trigger-narrowing keys** and **16 further disable shapes**, each through the real `_assert_census_ci` | 🔴 **REFUTED — 4 of 11 trigger keys GREEN**; 5 of 16 further shapes are genuine green disables |
| **A5** | "`s.body[:1]` at the `with`/`async with` door too, with both probes and a first-statement control" | Revert `s.body[:1]` → `s.body` at the `with` door and run CP-0 | ✅ **HOLDS** — 1 failed / 140 passed, the named test, zero bystanders |
| **A6** | "the literal is refused **anywhere**; the path must **derive** from `_swept_root()` by assignment. 10 vehicles" | 12 new vehicles + 2 false-positive vehicles through the real `_probe_writer_offenders`; plus per-clause attribution of the builder's own 11 | 🔴 **REFUTED — 10 of 12 BLIND, and 2 of 2 correct-code vehicles FIRE.** Control attribution itself is honest |
| **A4** | "the SQL is flattened in **source order** and any name bound to a string literal is substituted" | 5 "one more level of hoisting" vehicles through the real gate; then revert to the **exact** pre-R26 breadth-first flatten (verified to restore the defect) and run CP-0 | 🔴 **BLIND 5 of 5** one level out. Guard itself ✅ **red-able**, 1 test, 0 bystanders |
| **A3** | "alias maps are **per module plus imports**; both false-positive vehicles are controls that must stay GREEN" | Re-run R25-A's two cross-module FPs, then construct 2 new ones | ⚠️ **PARTLY** — both R25 vehicles fixed; **2 new FPs on correct code execute** |
| **A7** | "`_mirror()` frees what it allocated, `BaseException`" | Revert the `except BaseException: _discard(out); raise`, run CP-1, then count `lw-census-*` | ✅ **HOLDS** — 1 failed / 151 passed; **exactly 1 empty mirror leaks** under reversion, 0 pristine |
| **A7′** | the leaked directory in the builder's confirming run "came from the prover's own A7 case, which disables `_discard` on purpose" | Reproduce: disable `_discard` in the allocator, measure the debris | ✅ **ATTRIBUTION VERIFIED** — one *empty* `lw-census-` dir, which is the `git ls-files` branch exactly |
| **F3 / census** | "the 7 remaining are the same SITES … 68 sites, 7 silent, 61 red" | Run the **new** `_shape_digest` over the **old** sources and map every allowlist row across the two revisions; count digest collisions on both | ✅ **the 7 ARE the same sites** · 🔴 **F3 took digest collision groups 1 → 2**, and `_shape_digest`'s published "0 collisions" is false today |
| **B5** | the two deleted `except UntrustedRow` clauses were unreachable | Independent AST call-closure over the **whole package** (not just `contract.py`) + the exception MRO | ✅ **HOLDS** — closure raises only `ContractViolation`; `ContractViolation` **is** a subclass of `UntrustedRow`, so the handler order matters and the record does not say so |
| **transfer** | "zero production importers of `app.agentruntime`" | grep every import across `services/` and `scripts/` | ✅ **HOLDS**, third independent re-derivation |

---

## 2 · Bypass table

### 2a · A2 — the axis, executed over 24 vehicles

Harness: the gate's `_offenders`/`_scan`/`_scan_fn`/`LIVE`/`READS`/`PURE`/`EXEMPT` extracted **from
the test file's own AST** and `exec`'d — no transcription. Verified to reproduce the pristine result
(`[]`) and all four builder controls. `in-tree?` is executed separately: the vehicle's path
expression is evaluated against the real `ROOT`/`PKG`/`CS` and asserted to resolve under the repo.

| # | vehicle | gate | in tree? |
|---|---|---|---|
| 1 | **`for _p in sorted(PKG.glob('*.py')): _p.write_bytes(...)`** — the census's own inner-loop shape | 🔴 **BLIND** | ✅ |
| 2 | **`pkg2, cs2 = PKG, CS`** then the same loop — `census()` retargeted at the live package | 🔴 **BLIND** | ✅ |
| 3 | a write at **module scope** | 🔴 **BLIND** | ✅ |
| 4 | a **new module-level global** derived from `ROOT` (`CONTRACTS = ROOT / 'contracts'`), written in a function | 🔴 **BLIND** | ✅ |
| 5 | `ROOT` **rebuilt from `__file__`** inside a function (line 53's own expression) | 🔴 **BLIND** | ✅ |
| 6 | a path from a **string literal** | 🔴 **BLIND** | ✅ |
| 7 | a path from **`os.environ`** | 🔴 **BLIND** | ✅ |
| 8 | **`os.chdir`** to a `__file__`-derived root, then a relative `open` | 🔴 **BLIND** | ✅ |
| 9 | a **function-parameter default** `def _sg(cwd=CS)` | 🔴 **BLIND** | ✅ |
| 10 | tainted value stored through a **subscript** target | 🔴 **BLIND** | ✅ |
| 11 | tainted value stored through an **attribute** target | 🔴 **BLIND** | ✅ |
| 12 | a **comprehension** target | 🔴 **BLIND** | ✅ |
| 13 | returned from a **module-level helper** | 🔴 **BLIND** | ✅ |
| 14 | an **augmented-assign** target (`_a /= ROOT`) | 🔴 **BLIND** | ✅ |
| 15 | a read the gate ALLOWS, then a write on the result (`for g in PKG.glob(...): g.unlink()`) | 🔴 **BLIND** | ✅ |
| 16–19 | a live write / `rmtree(ROOT)` inside the exempt **`_mirror`** and the exempt **`main`** | 🔴 **BLIND ×4** | ✅ |
| 20 | `_discard(ROOT)` — `PURE` documents its members as *"callables that cannot touch a filesystem no matter what they are handed"*, and `_discard`'s body calls `shutil.rmtree` | 🔴 **BLIND** | ✅ |
| 21 | a `with`-statement target | 🔴 CAUGHT | ✅ |
| 22–24 | *(controls)* direct `write_bytes` on `ROOT` · `shutil.rmtree(ROOT)` · the same write in non-exempt `census` | 🔴 CAUGHT ×3 | ✅ |

**20 of 24 BLIND.** The claim *"the set of expressions that can name the live tree is small and
closed"* is false as implemented. The taint relation is **only** intra-function `Assign`/`AnnAssign`/
`NamedExpr` with a `Name` (or tuple-of-`Name`) target, rooted at four module globals. It does not
follow a `for` target, a comprehension target, a `with` target, a subscript or attribute target, a
parameter, a parameter default, a return value, or **module scope at all** — and it does not need
following if the path is simply reconstructed from `__file__`, a literal, `os.environ`, or a `chdir`.

**Vehicle 4 is the axis defect in its purest form**, and the code already contains the evidence:
`ALLOWLIST = ROOT / "contracts" / …` is a module-level derivation that the walk cannot see, so the
builder had to add `ALLOWLIST` to `LIVE` **by hand**. Every future module-level path constant must
also be hand-added, silently, or it is invisible. The prompt asks whether `READS`/`PURE` widen
silently: they do — but the **root set widens silently too**, which is worse, because `READS`/`PURE`
at least carry a stated reason.

### 2b · A2′ — the union, end to end. **This is the finding that decides the round.**

The gate's docstring says *"the behavioural drive stays below it"*. The drive
(`test_NEITHER_CENSUS_WRITER_CAN_REACH_THE_LIVE_TREE__all_8_cells`) patches exactly four APIs:
`Path.write_bytes`, `Path.write_text`, `Path.open`, `builtins.open` — **the API list this delta
declared "not the space"**. So the union has a hole with a name: *a path the gate cannot taint × an
API the watcher does not patch.*

Executed. Spliced into `census()`:

```python
import os as _vaos
for _vap in sorted(PKG.glob('*.py')):
    _vaos.makedirs(str(_vap) + '.vadir', exist_ok=True)
```

* `python -m pytest tests/test_cp1_membrane.py -q` → **`152 passed`**
* `ls -d services/chat-service/app/agentruntime/*.vadir` → **8 directories, inside the live tracked
  package**, created on every census invocation the suite makes.
* Restored `write_bytes`, bytes asserted identical, debris removed, `git status --porcelain` empty.

`os.makedirs` was chosen because it is *recoverable*. `os.remove`, `Path.unlink`, `shutil.rmtree` and
`os.replace` are in the same cell and are not, which is why I did not execute them — and which is
exactly the point of the finding: the recorded `%TEMP%`-deletion incident's API is still reachable
from a path this gate cannot see.

### 2c · A2″ — the no-vacuity assertion is satisfied by construction

```python
tainted = set(LIVE)          #  <- unconditional, line 2881
...
tainted_fns[fn.name] = tainted
...
assert LIVE <= set(tainted_fns.get("census", ()))
```

I renamed `ROOT`→`XROOT`, `PKG`→`XPKG`, `CS`→`XCS`, `ALLOWLIST`→`XALLOW` throughout the census
source — i.e. produced exactly *"a module whose names were simply spelled differently"*, the state
the assertion says it exists to refuse — and re-evaluated it: **True**. The assertion binds only
*"a non-exempt function named `census` exists"*. It is the third distinct instance in this run of a
check whose control and seed agree by construction, and it shipped **inside** the fix written to
close an axis.

### 2d · A1 — the whitelist, over my own enumeration

**(i) Trigger values — a derived denominator.** GitHub defines 11 narrowing keys across the two
required triggers. Each applied so the trigger can never match, run through the real
`_assert_census_ci`:

| key | check |
|---|---|
| `on.push.branches: [no-such-branch]` | 🔴 caught |
| **`on.push.branches-ignore: ['**']`** | 🟢 **GREEN** |
| `on.push.paths` / `paths-ignore` | 🔴 caught |
| **`on.push.tags: ['v-never-*']`** | 🟢 **GREEN** |
| **`on.push.tags-ignore: ['**']`** | 🟢 **GREEN** |
| `on.pull_request.branches: [no-such-branch]` | 🔴 caught |
| **`on.pull_request.branches-ignore: ['**']`** | 🟢 **GREEN** |
| `on.pull_request.paths` / `paths-ignore` / `types` | 🔴 caught |

**4 of 11 GREEN.** `branches-ignore: ['**']` on both triggers disables the workflow outright, and it
is the **literal sibling of `paths-ignore` sitting in the same dict**, in the fix whose stated scope
was *"`paths`, `paths-ignore`, `branches` and `types` each narrow a trigger to nothing … and none of
them was read."* Three of the four were read. **Thirteenth pair fixed at one end**, and this one is a
single hyphenated word away from the clause that fixed its twin.

**(ii) The whitelist's own failure mode — and the answer to the prompt's question is yes.** The
exact-string clause applies only to steps selected by `"agentruntime-census.py" in r`. So the way
through is to leave the exact string *exactly* alone and put the disablement in a step that never
spells the name:

| shape | check | genuinely disables while green? |
|---|---|---|
| a prior step: `python scripts/agentruntime-cens*.py --write` (shell glob) | 🟢 **GREEN** | ✅ the allowlist is regenerated, so the gate can never drift |
| a prior step: `sed -i 's/return 1 if/return 0 if/' scripts/agentruntime-cens*.py` | 🟢 **GREEN** | ✅ |
| a prior `actions/checkout` pinned to an old `ref:` | 🟢 **GREEN** | ✅ the census runs and passes, over code that is not the PR's |
| a prior step: `printf '' > scripts/agentruntime-census.py` | 🔴 caught | — caught only **incidentally**, because that step spells the literal |
| workflow `concurrency.cancel-in-progress` | 🟢 GREEN | ✖ cancelled ≠ success |
| step `working-directory:` / `timeout-minutes: 1` / `env: PYTEST_ADDOPTS` / a stubbed pytest | 🟢 GREEN ×4 | ✖ each makes the job **red**, not green — recorded and withdrawn |
| the job key is renamed · a second `--write` step · `on:` as a list | 🔴 caught ×3 | — |

**5 of 16 further shapes are genuine green disables**, and I withdraw the other 7 GREENs explicitly
rather than count them, because a shape that reds CI is not a bypass.

**Combined A1 denominator: 36 builder shapes + 11 trigger keys + 16 mine = 63 distinct shapes;
9 leave the check green over a census that does not gate.**

### 2e · A6 — the probe-writer gate kept the axis A2 abandoned

`_probe_writer_offenders`'s half two binds a **write-API list**: `_WRITES = (write_text, write_bytes,
touch, mkdir, unlink, symlink_to)` plus four hard-coded call shapes. That is precisely the axis this
same delta declared *"the space a previous verdict happened to name"* — kept, in the same commit.

| vehicle | gate |
|---|---|
| `open(p, mode='w')` — the mode passed by **keyword** (`len(call.args) >= 2` fails) | 🔴 **BLIND** |
| `p.open('w').write(...)` | 🔴 **BLIND** |
| `os.replace` / `os.rename` onto the path | 🔴 **BLIND** |
| `shutil.move` | 🔴 **BLIND** |
| `os.makedirs` | 🔴 **BLIND** |
| `Path.hardlink_to` | 🔴 **BLIND** |
| `f = open(p)` then `f.write(...)` | 🔴 **BLIND** |
| a local named **`tmp_path`** bound to the app tree (`_SAFE_ROOTS` is matched by NAME) | 🔴 **BLIND** |
| an attribute whose `.attr` is in `_SAFE_ROOTS` (`_c._sweep = …`) | 🔴 **BLIND** |
| the literal `'app'` built by concatenation (`'ap' + 'p'`) | 🔴 **BLIND** |
| *(control)* the typed root `/ 'app'` | 🔴 CAUGHT |
| *(control)* a dead mention with no literal | 🔴 CAUGHT |
| **(false positive)** a write through **`_APP`**, this module's own constant, defined at line 39 as `Path(__file__).resolve().parents[1] / _TURN_SCOPE_ROOT` — *the correct derivation* | 🔴 **FIRES on correct code** |
| **(false positive)** a helper that takes the path as a **parameter** | 🔴 **FIRES on correct code** |

**10 of 12 blind, 2 of 2 false positives fire.** By the file's own criterion — *"a gate that reds on
correct code is one that gets deleted"* — this gate convicts the single most correct way to spell its
own subject.

**The control attribution is honest, and I verified it.** Of the builder's 11 vehicles, 10 are caught
by *both* halves and only `_v3b` ("a dead mention with NO literal") is caught by half two alone. So
the self-correction the builder made after its own prover is real — but it also means the
discriminating power of an 11-vehicle enumeration is **1 vehicle for half two and 0 for half one**.

### 2f · A4 — fixed for the vehicle, blind one hoist out

Harness: the gate's analysis body extracted from the test method's AST, `_swept_root()` overridden to
a temp directory. Controls first: literal SQL **CAUGHT**, column hoisted **CAUGHT**, table+column
hoisted (A4's own vehicle) **CAUGHT**.

| vehicle — *one more level of hoisting* | gate |
|---|---|
| table bound to an **f-string** (`_TBL = f"chat_messages"`), `INSERT INTO {_TBL} (id, {_COL})` | 🔴 **BLIND** |
| table built by **concatenation** (`"chat_" + "messages"`) | 🔴 **BLIND** |
| both names by **tuple unpacking** (`_TBL, _COL = "chat_messages", "withheld_tools"`) | 🔴 **BLIND** |
| both names in a **dict** (`_N["tbl"]`, `_N["col"]`) | 🔴 **BLIND** |
| column via **`.format()`** with the names hoisted | 🔴 **BLIND** |

**5 of 5.** Root cause: `_strs_by_mod` records a name only when its value is `ast.Constant(str)` or a
`Name` already recorded. An f-string, a `BinOp`, a tuple target and a subscript are all outside that,
and `_bindings` makes the tuple case worse — it pairs *each* target name with the **whole tuple
node**, so `_TBL, _COL = "a", "b"` resolves neither.

And the load-bearing detail: A4's fix is only doing work for the `UPDATE … SET col =` form, which the
`f"{_COL} ="` clause already catches without any table resolution. For the **`INSERT INTO t (…, col)`
column-list form — which the docstring names as a real writer's spelling** — the table literal is the
only anchor, so hoisting it goes silent. The `.format` result also refutes the comment two lines
above it: *"the SQL is ASSEMBLED from every string in the expression … and discards no spelling of a
write."*

### 2g · A3 — the FP class was shrunk, not removed

| vehicle | R25 | R26 |
|---|---|---|
| cross-module `_COL` parameter, no import | 🔴 FP | ✅ **fixed** |
| cross-module `_SQL` generic executor, no import | 🔴 FP | ✅ **fixed** |
| **`_COL` bound in one function convicting another function in the SAME module** | — | 🔴 **FP fires** |
| **a module that legitimately `from app.a import _COL` and uses the name for something else** | — | 🔴 **FP fires** |

`_col_aliases` is built from `_bindings(tree)` over the **whole module including every function
body**, so a function-local hoist pollutes the module; and the import edge the fix adds makes the
alias visible to the importer regardless of what the importer does with the name. The
delete-the-gate criterion still applies, at a smaller radius.

### 2h · The one write the path gate is forbidden from seeing, and it is a tracked artifact

`main` is `EXEMPT`, and `main` holds the module's only writer of a **committed** file:

```python
ALLOWLIST.write_text("…" + "".join(f"{s}\n" for s in silent), "utf-8")
```

Executed on this machine: `Path.write_text("a\nb\n")` → `b'a\r\nb\r\n'`, and `read_text` returns
`'a\nb\n'`. The committed allowlist has **0 CRLF**. So `--write` on Windows rewrites all 50 lines
byte-differently and meaning-identically, and the drift check that reads it back with `read_text`
**cannot see it** — which is verbatim this round's own method rule (*"a restore assertion must
compare BYTES"*) and verbatim the census docstring's own claim (*"🔴 It reads and writes BYTES"*),
in the one place the module writes a tracked artifact, inside the one function the path gate is
forbidden from inspecting.

---

## 3 · Red-ability table — **with my own denominator**

| item | builder's denominator | **my denominator** | bound / total | how measured |
|---|---|---|---|---|
| **A2** path gate | 22 vehicles, 22/22 | **24 axis vehicles** (22 builder vehicles are 22 APIs on **one** path shape) | 🔴 **4 / 24** | real `_offenders`, AST-extracted; path resolution verified against the live roots |
| **A2** gate + drive, end to end | "the behavioural drive stays below it" | **1 cell**: untainted path × unwatched API | 🔴 **0 / 1** | full CP-1 suite, `152 passed`, 8 dirs in the live package |
| **A2** no-vacuity NV | 1 assertion | **1** | 🔴 **0 / 1** | roots renamed out of the module; assertion still True |
| **A1** CI check | 36 shapes, 36/36 | **63** (36 builder + 11 trigger keys + 16 mine) | 🔴 **54 / 63** | each shape through the real `_assert_census_ci` |
| **A1** guard | — | 1 reversion | ✅ **1 / 1** | whitelist → substring blacklist ⇒ `1 failed / 151 passed`, named |
| **A5** W4 `with` door | 2 probes + 2 controls | **4** | ✅ **4 / 4** | reversion `s.body[:1]` → `s.body` ⇒ `1 failed / 140 passed`, named |
| **A6** probe gate | 11 vehicles, 11/11 | **14** (12 bypass + 2 correct-code) | 🔴 **2 / 12** bypass, **0 / 2** FP-free | real `_probe_writer_offenders` |
| **A4** T11d flatten | "5 vehicles" | **5 controls + 5 one-level-out** | 🔴 **5 / 10**; guard ✅ **1 / 1** red-able | real gate over a synthetic swept tree; reversion **verified to restore the defect first** |
| **A3** T11d scoping | 2 controls that must stay green | **4** FP vehicles | ⚠️ **2 / 4** | same harness |
| **A7** allocator | 2 failure paths | **2 paths + 1 debris measurement** | ✅ **3 / 3** | reversion ⇒ `1 failed / 151 passed` **and exactly 1 leaked mirror**; 0 pristine |
| **census ids** | "the 7 are the same sites — my reading of my own output" | **9 old rows × 2 digest algorithms × 2 revisions** | ✅ **7 / 7 verified**, 2 verified deleted | new `_shape_digest` executed over the **old** sources |

### 3a · A method finding against my own harness, recorded before it is used against a result

**My first A4 reversion did not restore the defect, and I nearly published a `no guard` finding from
it.** I replaced `ast.iter_child_nodes` with `list(ast.walk(n))[1:]` inside the recursive `go()`,
observed `141 passed` — green — and would have reported A4 as shipped unguarded. Before writing that
down I applied this round's own rule and checked whether the mutation reproduced A4's behaviour: it
did not. Re-doing it with the **exact** pre-R26 body from `HEAD~1` and first confirming through the
harness that the table-hoist vehicle went **CAUGHT → BLIND**, the suite reported **`1 failed`**, the
named test. **A4 is guarded.** This is the same error the builder made twice this round, made once by
me, and it is the failure mode of the whole method: *a reversion that does not restore the defect
proves nothing, in either direction.*

---

## 4 · Sibling table — for every fix, is its twin fixed?

| fix | its twin | twin fixed? |
|---|---|---|
| W4's `[:1]` at the `try` door | the same at the **`with`/`async with`** door | ✅ **YES** — both doors, both probes, a control at each, red-able |
| `census()` and `_selftest()` free their mirror | **`_mirror()` frees what it allocated** | ✅ **YES** — 1 leaked dir under reversion, 0 pristine |
| the CI check reads `paths`, `paths-ignore`, `types`, `branches` | **`branches-ignore`, `tags`, `tags-ignore`** — the same dict | 🔴 **NO** — 4 of 11 keys green, measured |
| the CI whitelist bounds **the census step's** command | the **neighbouring steps** that decide what that command runs on | 🔴 **NO** — glob-spelled prep steps and an old `checkout` ref all green |
| A2 abandons the **API list** for the **path** | **A6's `_probe_writer_offenders` half two**, which is an API list, in the same commit | 🔴 **NO** — 10 of 12 blind |
| A2's taint follows an **`Assign` target** | a **`for` / comprehension / `with` / subscript / attribute / parameter** target, and **module scope** | 🔴 **NO** — 20 of 24 blind |
| T11d resolves a hoisted **column** and now a hoisted **table** | a table hoisted **one more level** (f-string, concat, tuple, dict, `.format`) | 🔴 **NO** — 5 of 5 blind |
| T11d's aliases scoped to **module + imports** | the same identifier reused **inside one module**, and a **legitimate import** | 🔴 **NO** — 2 new FPs |
| the census "reads and writes BYTES" | `main`'s `ALLOWLIST.write_text` — the one **tracked** artifact it writes | 🔴 **NO**, and it is inside `EXEMPT` |
| `check_row`'s dead handler deleted in `build()` | the same in `validate_document()` | ✅ **YES** — both, one guard on the closure |

---

## 5 · The census's numbers — the highest-risk change, verified exactly

I did not run the 25-minute census. For the claims that are *about* the census's own ids I ran
something stronger: the census's own `_sites`/`_shape_digest` from **both revisions** over the
sources of **both revisions**, which isolates digest-algorithm churn from source churn exactly.

**(i) The 7 rows are the same SITES. ✅ VERIFIED.** Applying the **new** digest to the **old** source
reproduces the new allowlist digest for every carried row:

| old row | new-digest id on `HEAD~1` | at `HEAD` |
|---|---|---|
| `canon.py::_norm::NotCanonicalisable::1::be8fd1f7` | `…::1::417da3eb` | ✅ same, in the allowlist |
| `canon.py::_norm::NotCanonicalisable::2::795ce436` | `…::2::94328cec` | ✅ |
| `canon.py::_norm::NotCanonicalisable::4::1598291a` | `…::4::15c0d4e9` | ✅ |
| `manifest.py::generate::UntrustedRow::1::aac73feb` | `…::1::0265f69f` | ✅ |
| `manifest.py::generate::UntrustedRow::2::311a6e16` | `…::2::ec0cf983` | ✅ |
| `manifest.py::validate_document::UntrustedRow::5::dfe69192` | `…::**5**::843af89b` | ✅ same digest, **ordinal 5 → 1** |
| `surface.py::TakeWhileBudget…::ValueError::1::3130a968` | unchanged | ✅ no f-string |
| `manifest.py::build::UntrustedRow::4` · `…validate_document::UntrustedRow::6` | — | ✅ **deleted from source**, verified gone |

**Precision correction to the record.** RUNSTATE says *"The 6 other allowlist rows changed id, and
that is the F3 fix working."* For five of the six that is exactly right. For
`validate_document::UntrustedRow::5 → ::1` the id moved for **two independent reasons** — the F3
digest change *and* an **ordinal renumbering** caused by four sibling raises relocating to
`contract.check_document`. The record names one. And the ordinal is the half F3 does **not** fix: I
measured `manifest.py::build::UntrustedRow::5::6688ede8 → ::4::6688ede8`, a **RED** site whose id
moved silently — which is the very invisibility the F3 block describes, arriving through the other
component of the id.

**(ii) "68 sites" is stable by coincidence, not by stability.** Executed per module:

| | `admission` | `ambient` | `canon` | `contract` | `manifest` | `narrowing` | `surface` | total |
|---|---|---|---|---|---|---|---|---|
| `HEAD~1` | 4 | 0 | 4 | 18 | 17 | 0 | 25 | **68** |
| `HEAD` | 4 | 0 | 4 | **22** | **11** | 0 | **27** | **68** |

Six refusals left `manifest.py`; four arrived in `contract.check_document`; two were deleted; two new
ones appeared in `surface.py` (`Filter.__post_init__::ValueError::5`, `_require_names::ValueError::4`).
A row that reads "68 → 68" beside "9 silent → 7 silent" invites the reading that the site set held.
**Ten of the 68 ids are different sites or new ones**, and 10 of them changed id.

**(iii) 🔴 Blanking a `JoinedStr` DOUBLED the digest collision groups, and `_shape_digest`'s published
count is false today.** Executed over all 68 sites:

| | sites | distinct digests | collision groups | sites in a collision |
|---|---|---|---|---|
| `HEAD~1`, old digest | 68 | 66 | **1** | 3 |
| `HEAD~1`, **new** digest (same source) | 68 | 65 | **2** | 5 |
| `HEAD`, new digest | 68 | 65 | **2** | 5 |

The new group at `HEAD~1` is `manifest.py::build::UntrustedRow::4` and
`manifest.py::validate_document::UntrustedRow::6` — **the two deleted handlers, collapsed onto one
digest `9e61cfe8` by F3**, because `f'{exc}. …'` and `f'{source}: {exc}'` both blank to `'\x00'`. At
`HEAD` the new group is `surface.py::Filter.__post_init__::ValueError::5` and
`surface.py::_require_names::ValueError::4`, both `9564d070`.

**Answer to the prompt's question:** blanking has **not** collapsed two refusals onto one *id* — the
qualname prefix separates every current pair, and `_selftest`'s ordinal-free injectivity check
confirms 0 collisions and would fail closed if one arrived. But it **has** collapsed two onto one
*digest*, twice, and `_shape_digest`'s own docstring publishes *"takes the collision groups from 4 to
**0**"*. That was already false before this delta (the `admission.py` `__reduce__`/`__copy__`/
`__deepcopy__` trio) and F3 made it worse. The digest's stated ability to distinguish a reorder rests
on that number.

**(iv) B5's two departures really are unreachable — and the stated reason is incomplete.** My own AST
call-closure, run over the **whole package** rather than `contract.py` alone (the shipped guard walks
only bare-`Name` callees in one file), reaches `{check_row, check_row_shape, check_contract,
derive_owning_service}` and finds exactly one raisable class: `ContractViolation`. ✅ But
`ContractViolation` **is a subclass of `UntrustedRow`** (MRO executed). So `except UntrustedRow` was
dead because of the **handler order** — `except ContractViolation` sits above it — *combined* with the
raise set, not because of the raise set alone. The shipped guard binds `reached == {"ContractViolation"}`,
which is sufficient; the record's one-line reason is not the whole reason, and the distinction matters
the next time someone writes `except UntrustedRow` above `except ContractViolation`.

**What I could not determine: the 61 red / 7 silent split.** Skipped deliberately.

---

## 6 · Guard table

| guard | binds the property, or the nearest proxy? |
|---|---|
| `test_NO_LIVE_TREE_PATH_REACHES_A_MUTATING_CALL__the_property_not_the_API_LIST` | 🔴 **proxy, and the name overstates it.** The property is *"no expression in this module names the live tree at a mutating call"*; it binds *"no intra-function `Assign`-chain rooted at four module globals reaches a non-read call in a non-exempt function"*. Its **22-vehicle control is 22 APIs on one path shape**, so it cannot detect the gap. Its NV is a tautology |
| `test_NEITHER_CENSUS_WRITER_CAN_REACH_THE_LIVE_TREE__all_8_cells` | **proxy** — 4 creation APIs, unchanged. Its `len(results) >= 50` / `rc == 0` / leak assertions are genuine and load-bearing |
| `_assert_census_ci` + 36 shapes | 🔴 **proxy.** The property is *"the census gates a PR"*; it binds *"one named step's `run:` text is exact, and 8 structural keys are absent"* — over a workflow whose other steps, `branches-ignore`, `tags`, `tags-ignore` and checkout ref are unread |
| `_unconditional_calls` `s.body[:1]` at **both** doors (A5) | ✅ **property**, for the statement kinds enumerated. Red-able, 1 test, 0 bystanders |
| `_probe_writer_offenders` half one (literal anywhere) | **property** for the literal; over-broad by design |
| `_probe_writer_offenders` half two (derive by assignment) | 🔴 **proxy of a proxy.** Derivation is bound correctly; the **write** is an API list of 6 methods + 4 shapes, and `_SAFE_ROOTS` is matched by *name*, so a local called `tmp_path` absolves anything |
| T11d `_flat_sql` source-order + per-module aliases | 🔴 **proxy in both directions**, at a smaller radius than R25: under-approximates one hoist out (5/5), over-approximates into 2 executed FPs |
| `_mirror`'s `except BaseException: _discard(out); raise` (A7) | ✅ **property.** Red-able, and the debris is measurable |
| `test_CHECK_ROW_RAISES_EXACTLY_ONE_CLASS…` (B5) | ✅ **property** (the closure, not the deletion) — though the closure walk is `contract.py`-only and bare-name-only |
| `test_THE_DIGEST_IS_BLIND_TO_PROSE__including_an_f_STRING` (F3) | **property** for prose-blindness, with class/arity controls. 🔴 It asserts **nothing about collisions**, which is what blanking costs |

---

## 7 · Reachability verdict on every finding

| # | finding | production-reachable **today**? | needs code that does not exist? |
|---|---|---|---|
| A-1 | A2 blind on 20 of 24 axis vehicles | ✅ **YES** — vehicles 1, 2 and 15 are the census's own loop idiom; one edit to `census()` retargets it at the live package | no |
| A-2 | **gate + drive union does not close** — 8 dirs written into the live tracked package, suite green | ✅ **YES, executed.** The destructive members of the same cell (`os.remove`, `Path.unlink`, `shutil.rmtree`, `os.replace`) are the recorded `%TEMP%` incident's APIs | no |
| A-3 | A2's NV is a tautology | ✅ **YES** — a rename of `ROOT` today leaves the gate green over nothing | no |
| A-4 | `EXEMPT` is whole-function; 4 of 4 live writes blind inside it | ✅ **YES** | no |
| A-5 | `main`'s `ALLOWLIST.write_text` emits CRLF on Windows, unreadable by the drift check, unseeable by the path gate | ✅ **YES** — `--write` on any Windows checkout, and this verification runs on Windows 11 | no |
| A-6 | A1: `branches-ignore` / `tags` / `tags-ignore` unread, 4 of 11 | ✅ **YES** — one hyphenated word un-gates the census | no |
| A-7 | A1: a neighbouring step defeats the census without spelling its name | ✅ **YES** — a 2-line YAML edit | no |
| A-8 | A6 blind on 10 of 12; `open(p, mode='w')` is a one-keyword bypass | ✅ **YES** for the gate's subject (the 12th probe writer). Does not affect production code | no |
| A-9 | A6 reds on `_APP`, the module's own correct constant | ⚠️ **latent** — fires the moment a probe uses the constant provided for it | no |
| A-10 | A4 blind one hoist out, 5 of 5, incl. the `INSERT (…, col)` form | ⚠️ **latent**, by the same standard T11d itself was held to for six rounds | no |
| A-11 | A3 FPs inside one module and through a legitimate import | ⚠️ **latent** — needs a hoist plus an identifier reuse; `_COL`/`_SQL`/`q` are normal | no |
| A-12 | F3 doubled the digest collision groups; `_shape_digest`'s "0" is false | ✅ **YES** (a false sentence, and a weakened reorder detector, in the tree now). Contained: no ordinal-free id collides, `_selftest` fails closed | no |
| A-13 | "68 → 68" conceals 10 moved/new sites | ✅ **YES** (a misleading row in the record now) | no |
| A-14 | the F3 attribution for `validate_document::5 → ::1` names one of two causes; the **ordinal** churns invisibly on RED sites | ✅ **YES** | no |
| A-15 | branch protection not requiring the job | ✅ **YES**, and **unmeasurable from the repo**. Correctly carried as a permanent named residual — the delta does this, and it is right to | no |

**No finding in this verdict requires code that does not exist.** Eleven are actionable today; four
are latent behind one ordinary refactor each.

---

## 8 · Convergence

| round | items I was asked to grade | refuted | partial | fully upheld |
|---|---|---|---|---|
| R25-A | 8 | 5 | 2 | 1 |
| **R26-A** | **9** (A2, A1, A5, A6, A4, A3, A7, the census ids, the transfer) | **4** (A2, A1, A6, A4) | **1** (A3) | **4** (A5, A7, the census ids, the transfer's fact) |

**The signal from R25 repeated exactly, and the builder predicted it in writing.** Every item settled
by a **control** held — A5 (two probes plus a first-statement control at each door), A7 (a per-path
reversion with a measurable leak), and the census ids (which I could verify because the digest is a
pure function I could run over both revisions). Every item settled by **an enumeration the builder
chose** was short: 22 vehicles → 4/24, 36 shapes → 54/63, 11 vehicles → 2/12, 5 vehicles → 5/10.
That is now **six consecutive rounds**, and it held even for A2, whose entire premise was that
changing the *axis* escapes it. **Changing the axis did not escape it, because the new axis was also
an enumeration the builder chose** — of six kinds of assignment target, in one function scope.

**Upheld count is up (1 → 4) and the refuted count is down (5 → 4) on a larger scope.** That is the
first two-way improvement in my seat. It is not convergence on the instruments: the two headline
instruments are still short by 20/24 and 9/63.

**Prediction, falsifiable, for R27.** If A2 is repaired by adding `for`/comprehension/`with`/
subscript/attribute/parameter targets to the taint walk, I predict the next round finds it through
**interprocedural flow** — a helper that returns a live path, or a live path passed as an argument
into another function in the same module — because the walk is per-function and has no call graph.
The enumeration-free form of the property is not an AST rule at all: it is *"no syscall issued by
this process mutates anything under `ROOT`"*, which is answerable by hashing the tracked tree around
the run, or by running the census against a read-only mount. §2b is the executed argument that no
union of a path rule and an API list closes it.

---

## 9 · Executed-vs-argued — **my own denominator**

| | count |
|---|---|
| claims I make | **26** |
| **EXECUTED** (a command ran and its output is the evidence) | **21** |
| **ARGUED** (reasoning from source or documented platform behaviour) | **5** |
| **ratio** | **21 / 26 = 81 % executed** |

The five argued claims, named so they can be attacked:

1. that `branches-ignore: ['**']`, `tags:` and `tags-ignore:` actually stop GitHub firing the
   workflow — *I executed only that the **check** stays green*;
2. that a shell glob (`scripts/agentruntime-cens*.py`) expands on the runner, and that
   `actions/checkout` with `ref:` really checks out that ref;
3. that `working-directory`, `timeout-minutes: 1`, `PYTEST_ADDOPTS=--collect-only` and a stubbed
   pytest make the job **red** — this is why I **withdrew** those 7 GREENs rather than counting them,
   so the argued direction is the conservative one;
4. that `--write` on a Windows checkout would dirty the committed allowlist — I executed the
   **mechanism** (`Path.write_text` → CRLF on this machine) and read the call site, but did not run
   the 25-minute `--write`;
5. that `os.remove`/`unlink`/`rmtree` behave in §2b's cell as `os.makedirs` did — I executed the
   non-destructive member only, deliberately.

Every finding in §2–§7 rests on an executed claim. The argued five affect only *how bad*, never
*whether*.

---

## 10 · Verdict

**FAIL**, on the instruments, with the reason stated:

1. **A2's claim is refuted, and refuted end to end.** *"The set of expressions that can name the live
   tree is small and closed"* is false: **20 of 24 BLIND**, including the census's own inner loop.
   And the union of the new path gate with the API watcher below it does not close — **executed:
   8 directories inside the live `app/agentruntime/` package, `152 passed`.** This is the exact class
   of damage the instrument exists to prevent, produced by the instrument, with the gate green.
2. **The gate's own no-vacuity assertion is satisfied by construction.** `tainted` is initialised to
   `set(LIVE)`, so `LIVE <= tainted_fns["census"]` cannot fail. I proved it by producing the exact
   state it says it refuses. Third instance in this run of a control that agrees with its seed by
   construction — shipped inside the fix built to close an axis.
3. **A1's whitelist leaves 9 of 63 shapes green**, and the four trigger keys it misses include
   `branches-ignore`, the literal sibling of `paths-ignore` in the same dict, in the clause written
   to close that family. The whitelist's own failure mode is real and is the answer to the prompt's
   question: it bounds only the steps that spell the script's name.
4. **A6 kept the axis A2 abandoned in the same commit** — a write-API list, 10 of 12 blind — and it
   reds on the module's own correct constant.
5. **A4 is fixed for its vehicle and blind one level out, 5 of 5**, and its fix is load-bearing only
   for the `UPDATE … SET col =` form.

**What HELD, and it is more than last round:** **A5** (the twin fixed at both doors, red-able, with a
first-statement control at each); **A7** (a real property, red-able, the leak reproduced at 1
directory, and **its debris attribution independently verified**); **the 7 allowlist rows are the
same SITES** — verified by executing the new digest over the old sources, which is the one number in
this delta the builder called *"my reading of my own output"* and which survives an independent
reading; **B5's unreachability**; and **zero production importers**, re-derived a third time. The
corrected transfer is right: the two criteria are now attached to the rows they govern, and I could
not find a third situation hiding under either.

**What I could NOT determine**

* The **61 red / 7 silent** split. The 25-minute census was skipped deliberately; I verified the site
  enumeration, the id mapping and the collision count exactly instead, which is a different and
  stronger claim about a smaller thing.
* Whether the 4 relocated `check_document` refusals and the 2 new `surface.py` refusals are actually
  RED. They are absent from the allowlist, which asserts it; nothing I ran measures it.
* Whether the 9 green CI shapes produce a green **check on GitHub** as opposed to a green
  `_assert_census_ci` — see §9.
* Whether branch protection requires the job. Unmeasurable from the repository, correctly carried.
* Anything in Verifier B's scope (B1–B4, F7's `check_document`) beyond the two crossings recorded in
  §5(iv).
