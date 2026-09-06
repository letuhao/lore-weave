# CP-1 · V-CODE — verdict, round 2

**Artifact:** `7f50949dceee8814c17a97f0aae10f19c12c5fbe`, verified with `git rev-parse HEAD` before the
audit and again immediately before this verdict was written. **HEAD did not move.** All artifact
paths (`app/agentruntime/**`, `scripts/agentruntime-membrane-gate.py`,
`contracts/agent-runtime-manifest.json`, `tests/test_cp1_membrane.py`, `Dockerfile`,
`ARCHITECTURE.md`) are clean in `git status`.

**Method.** Source read. Nothing was run against a live system and **no tracked file was edited**.
Where I needed to prove a gate red-able I mutated a *string copy* of the source in memory or wrote
probes to a temp directory, never to the tree. I ran three things that are static analysers rather
than the system: `scripts/agentruntime-membrane-gate.py` (exit 0), its `--selftest` (fires on 7
shapes), and `pytest tests/test_cp1_membrane.py` (61 passed) — the last because a green suite over a
gate that cannot fire is the finding, and I needed the green to be real.

I read round 1 and treated every one of its findings as a claim to re-test, not as fact.

---

## 1 · Verdict

**Overall: FAIL.**

| # | claim | verdict |
|---|---|---|
| 1.1 | manifest generated, starts empty | **PASS** — round 1's FAIL is closed. The drift gate now exists, runs in CI, and I made it red on five separate realistic hand-edits |
| 1.2 | import-graph gate, no legacy in the transitive imports | **PASS** — the prefix hole is fixed and anchored on the separator; selftest covers both shapes; graph is stdlib-only |
| 1.3 | discovery reads the manifest only; zero rows for all three kinds | **PASS (mechanism)** — with a NEW asymmetry: the fix for the silent-empty document stopped one function short of `discover`, the M3 entry point itself. Its tests remain vacuous |
| 1.4 | construction IS validation; bypass impossible. **P4** at every INSERT | **FAIL** — M4's half is now honest and its *effective* guarantee (revalidation at both ends) I executed and it holds. **P4 has zero subject and the shape it names is live and unfixed elsewhere in the service** |
| 1.5 | an unresolvable reference fails generation | **PASS** — and strengthened: the read path now re-resolves too |
| 1.6 | C-0 identity, owner derived never authored | **PASS** with round 1's residual **not closed**, and a new tautology on the read side |
| 1.7 | every narrowing registers `{tool, stage, reason, pass}` | **FAIL** — the two named drop points are fixed, but **the gate added to catch the third is vacuous**: I proved it stays green with `log.record` deleted from *both* remaining drop sites |

The two items round 1 failed (1.1, 1.4-M4) were genuinely fixed. The fix for 1.7 introduced a gate
that cannot fire, which is the same defect class one layer up.

---

## 2 · The falsifier — what I looked for that would have made this FAIL

1. **A code path — import, call, or value read — in `app/agentruntime/**` originating in
   `tool_surface.py` / `tool_discovery.py` / `stream_service.py` or any non-stdlib module.** Method:
   read all six modules in full; ran the gate over the real package (`exit 0`, 6 modules, 0 allowed
   external imports); `grep -rn agentruntime` repo-wide across `*.py`/`*.yml`/`Dockerfile`/`*.sh` to
   find any importer or bridge. **Found none.** The only non-test, non-gate hits are two CP-0 files
   containing the *string* `"agentruntime"` as a `runtime_variant` enum value
   (`app/services/instrument.py:100`, `app/db/migrate.py:368`) — no importer exists in either
   direction.
2. **A gate that reports safety it does not have.** Method: for each of the three gates added since
   round 1, I constructed inputs and ran them. Two fire; one does not (F1).
3. **A way to get an unchecked declaration into a manifest row.** Method: executed eight documented
   forgeries against the real class and fed each product to `build()`. **Found none that survives the
   write.**
4. **A drop point with no `{tool, stage, reason, pass}` record.** Method: re-enumerated every
   statement in the package that can reduce a row set, then mutated the source in memory to remove
   each record and re-ran the enumeration gate. **Found one drop point and a gate blind to all of
   them.**
5. **An INSERT binding an instrument column to a literal reachable from more than one terminal
   condition.** Method: searched the package for SQL of any kind (none exists — M2 forbids the
   driver), then searched the legacy service for the column the new runtime is supposed to
   distinguish itself with. **Found the shape, live, at three sites.**
6. **A prose claim in `ARCHITECTURE.md` that the code does not support.** Method: took every
   enforcement noun in §3's gate column and §6.1's layer table and looked for the mechanism.
   **Found three.**

---

## 3 · The three gates added since round 1 — does a realistic input make each fire?

### 3.1 The manifest drift check — **ARMED** ✅

`scripts/agentruntime-membrane-gate.py:156-202`. I loaded the gate module, pointed `MANIFEST` at a
temp file, and ran `_manifest_drift()` on six documents:

| input | rc |
|---|---|
| the committed manifest, unchanged | **0** |
| a *well-formed* row typed in by hand (`glossary_search`, contract-valid) | **1** — "manifest drift" |
| a malformed row typed in by hand (`"Bad Id"`) | **1** — "failed the contract" |
| `manifest_version` bumped by hand | **1** |
| an extra top-level key | **1** |
| the version keys stripped | **1** |

It fires on the one bypass the write-side type cannot see, and it fires on the *valid-looking* edit,
not merely the malformed one. This is the strongest gate added this round.

Two things it is not. It compares against a hardcoded `build([])` (`:195`), so it is an
**"is empty and well-formed"** check, not the row-count-versus-admitted-count comparison
`ARCHITECTURE.md:840` still describes; at CP-4 it must be rewritten or it reds on the first admitted
declaration. And it establishes that the file *equals what the generator would produce*, never that
a generator produced it — there is still no generator entry point in the tree (no script, no CI step,
no make target calls `generate()`; every caller is a test with `path=tmp_path`). The gate's own
docstring says this plainly, which is why 1.1 passes: the checkable half is now checked.

### 3.2 Revalidation on load — **ARMED** ✅

`manifest.py:159-218`. I executed both ends. A hand-typed malformed row raises `UntrustedRow`; a
hand-broken member raises `UnresolvedReference`; a forged `Admitted` (`object.__new__` + two
`object.__setattr__`) carrying an *invalid* declaration is rejected by `build()` with the real
`ContractViolation`. **This is the layer that makes the type non-load-bearing, and it works.**

Its boundary, stated honestly: it enforces **conformance, not provenance**. A hand-typed row that
happens to satisfy the contract loads, validates and assembles —

```
validate_document({"declarations":[{"id":"glossary_search","kind":"tool",
  "owning_service":"glossary-service","lifecycle":"admitted",
  "contract_version":"0.0.1-bogus","members":[]}]})   → returns the doc
SurfaceAssembler(that_doc).assemble(pass_number=1).names → ('glossary_search',)
```

— executed, above. The row's own `contract_version` is not checked against `CONTRACT_VERSION` either.
For the *committed* manifest the drift gate closes this; for any other manifest (the
`LOREWEAVE_AGENT_RUNTIME_MANIFEST` override) nothing does.

### 3.3 The drop-site enumeration test — **VACUOUS** ❌ (F1)

Detailed in F1. It cannot fire on any realistic input, including the exact defect it was written to
catch.

---

## 4 · Findings

### F1 · The drop-site enumeration gate examines nothing — proved by mutation
`services/chat-service/tests/test_cp1_membrane.py:394-430`, classifier at `:415`

```python
drops = ("for " in inspect.getsource(mod).split("def " + fn.name)[1][:1200]
         and ".append(" in body and "If(" in body)
```

`body` is `ast.dump(fn)`. **`ast.dump` never emits the substring `".append("`** — a method call is
rendered `Attribute(value=Name(id='kept'), attr='append')`. I checked directly:

```
".append(" in ast.dump(ast.parse("x=[]\nfor a in b:\n    x.append(a)\n"))  ->  False
```

So `drops` is identically `False` for every function in the module, and the only live classifier is
`comprehension_filter` — a list/generator comprehension carrying an `if`. **Neither of the two real
drop sites is that shape.** Running the test's own logic over the real `surface.py`:

| function | `.append(` in dump | `for ` after the def | comprehension filter | classified as a drop site? |
|---|---|---|---|---|
| `_narrow` | False | True | False | **no** |
| `discover` | False | False¹ | False | **no** |

¹ the 1200-character window after `def discover` is entirely docstring, so even the dead half of the
predicate would have missed it.

`offenders` is therefore always `[]` and `assert not offenders` passes over an empty examination. I
proved it by mutating a string copy of the source (no tracked file touched):

| mutation | offenders reported |
|---|---|
| delete `log.record(...)` from `discover` — i.e. restore round 1's exact defect | `[]` |
| delete `self._log.record(...)` from `_narrow` — the checkpoint's core mechanism | `[]` |
| delete both | `[]` |

**The gate is green with every narrowing in the module silent.** The builder's stated red-ability
proof ("injecting a filtering helper that registers nothing") does not hold for the append-loop
shape either — I appended exactly that helper and got `[]`. Only a filtered comprehension reds it.

Two further limits: the test parses `surface.py` alone (`:407`), so a drop site added to
`manifest.py` or a new module is invisible; and the docstring's conclusion — *"P1 is a property of
the module, not of one function in it"* — is asserted by a check that examines no function in it.

### F2 · `discover` keeps the silent-empty default that was removed from the assembler
`services/chat-service/app/agentruntime/surface.py:160` vs `:86-91`

The same commit removed `.get("declarations", [])` from `SurfaceAssembler.__init__` and made a
missing key a `ValueError`, with the correct reasoning: *"a malformed document became an empty
surface, indistinguishable from 'nothing is admitted'."* `discover` — the **M3 entry point**, exported
from `__init__.py` — still has it:

```
discover({})                      -> []          (silent)
SurfaceAssembler({})              -> ValueError  ("malformed")
```

Executed. `discover({"declarations": None})` raises `TypeError` from `list(None)` rather than the
document error. The test that gates this (`test_a_document_without_declarations_is_refused`, `:515`)
covers `SurfaceAssembler` only. This is a drop with no record, in the module whose defining property
is that drops cannot be silent — and F1's gate cannot see it.

### F3 · P4 has no subject, and the shape it names is live and unfixed
Method: the package contains no SQL, no driver, no `INSERT`, and by M2 cannot import one; its only
write is `Path.write_text` (`manifest.py:149`). **Zero INSERTs are reachable from the new runtime.**
Per the vacuity rule, a property whose subject never occurs is a `FAIL` finding.

The column P4 exists for is `chat_messages.runtime_variant` (`app/db/migrate.py:367-368`, values
`'legacy' | 'agentruntime'`). Every INSERT that writes it binds the literal:

- `app/services/stream_service.py:7351` — `instrument.RUNTIME_LEGACY`
- `app/services/voice_stream_service.py:625` — `instrument.RUNTIME_LEGACY`
- `app/routers/internal.py:937` — `instrument.RUNTIME_LEGACY`
- `app/services/stream_service.py:6179` — parameter default `= instrument.RUNTIME_LEGACY`, and
  `grep -rn RUNTIME_AGENTRUNTIME` across the service returns **only its definition
  (`instrument.py:100`) and one test**. No caller can produce the other value.

A literal reachable from every terminal condition is precisely the defect P4 names, and it is
present today in the column that is supposed to tell the two runtimes apart.

Round 1's related observation is also unfixed: `manifest.py:107` writes `ident.contract_version`,
and `identity_of` (`contract.py:150`) hardcodes the module constant. `Admitted.contract_version`
(set at `admission.py:118` from `check_contract`'s return) **is read by nothing** — `grep` over the
package confirms. Today both are `"1.0.0"`, so the defect is invisible; the moment the constant bumps,
every regenerated row claims the new version regardless of what it was admitted under.

### F4 · `ARCHITECTURE.md` still overstates in three places — one of them in §6.1

The user's question is whether §6.1, amended twice, is now true of the code. **Rows 1 and 3 are
true — I executed both. Row 2 is not.**

`ARCHITECTURE.md:1018`:

> | 2 | **detection boundary** — the gate | a bypass must either name a private symbol or call
> `object.__setattr__` on an `Admitted`. Both are greppable, so **the gate** makes a deliberate
> bypass **loud in a diff** rather than impossible in a process. |

`grep -n "_TOKEN\|object.__setattr__\|setattr" scripts/agentruntime-membrane-gate.py` returns
**nothing**. The gate checks imports, the manifest, and the construction-site count for `Admitted`
and `Surface` *inside the package* (`:143-150`). It performs no scan for either form named in the
row, and `_construction_sites` cannot see a caller outside `app/agentruntime/**` at all — which is
exactly where a `_TOKEN` import would live. The two forms are greppable by a human; the gate does not
grep for them. This is a capability named in prose, which is the finding round 1 raised about the
drift gate, recurring one row below the correction that closed it.

The other two are outside §6.1 but part of the same claim set and were not amended:

- `:843` — M4's gate: *"the registration entry point **refuses to boot** on an incomplete contract…
  remove one required clause, watch the service fail to start."* Nothing imports `app.agentruntime`
  (searched repo-wide); there is no boot-time registration and no startup path that touches
  admission. Removing a clause changes nothing about service start.
- `:840` — M1's gate: *"manifest row count == admitted count."* The gate that now exists compares
  the file to `build([])`; there is no admitted count anywhere for it to compare against.
- `:842` — M3's gate: *"a test that **seeds** a legacy-only declaration of each of the three kinds."*
  No test seeds anything; see NV-3.

### F5 · Round-1 residuals not closed (re-tested, still present)

- **`_TOKEN` is importable** (`admission.py:64`). `from app.agentruntime.admission import _TOKEN;
  Admitted(bad_declaration, "1.0.0", _TOKEN)` succeeds — executed. Now correctly disclosed in
  §6.1 and in the module docstring, and defanged by layer 3, but not prevented.
- **`object.__setattr__` on a live `Admitted` swaps its declaration** — executed, succeeds.
- **A subclass with its own `__init__` produces a usable instance** for which `isinstance` is true —
  executed, succeeds, and `build()` accepts it if the wrapped declaration is contract-valid.
- **`Surface` is constructible outside the package** (`__init__.py:46` exports it; the gate's
  `_construction_sites` scans `PACKAGE.rglob` only). A consumer can build a `Surface` with arbitrary
  `names` and empty `withheld`.
- **A duplicate id is reported as an unresolved reference** (`manifest.py:125-127`):
  `raise UnresolvedReference(dupes[0], dupes[0])` produces *"x references 'x', which is not
  admitted"* — a true failure with a false cause, in the step whose job is to stop bad data.
- **`source_path` is authored and checked against nothing** — see NV-6 / item 1.6.

Round 1's F10 (dead `asdict` import) is fixed. F1, F6, F8 and both named drop points are fixed.

### F6 · An explicitly configured but absent manifest reads as empty, silently
`manifest.py:52-54` (override returned without an existence check) and `:175-177`

```
LOREWEAVE_AGENT_RUNTIME_MANIFEST=/nowhere/configured-but-absent.json
load()  ->  {"manifest_version": 1, "contract_version": "1.0.0", "declarations": []}
```

Executed. *No manifest anywhere* and *the manifest I was explicitly told to read is not there* are the
same result. The first is legitimately empty; the second is a deployment fault. This is the exact
conflation `Surface.is_empty` was built to prevent, one layer below it, and it is the CP-4 failure
the Dockerfile change was made to avoid — the change ships the file, but nothing detects its absence.

---

## 5 · Vacuity (NV)

| # | check | armed? |
|---|---|---|
| NV-1 | membrane gate `--selftest` (`gate:269-307`) | **YES** — I ran it: fires on 7 bypass shapes including both new prefix cases, silent on a legal module. Default mode runs it before the lint, and CI invokes the script bare (`lint-foundation.yml:94`, `:118`) |
| NV-2 | manifest drift (`gate:156-202`) | **YES** — six inputs above, one green, five red |
| NV-3 | three-kind discovery test (`tests:197-199`) | **NO** — it asserts `discover(load(nonexistent), kind=k) == []`, i.e. `[] == []`, for any string `k`. The one test naming real legacy ids (`:218-222`) names three **tools** (`book_list`, `glossary_search`, `tool_list`); **no legacy skill id and no legacy workflow id appears anywhere in the suite**, so "each of the three kinds" is met by a parametrize label, not by a subject. The claim is nonetheless true by construction (M2 + an empty manifest), which is why 1.3 passes on mechanism |
| NV-4 | drop-site enumeration (`tests:394-430`) | **NO** — F1. Classifies zero functions; green with every record deleted |
| NV-5 | revalidation on load (`manifest.py:159-218`) | **YES** for contract conformance — executed at both ends. **NO** for provenance: no realistic input distinguishes a generated row from a hand-typed contract-valid one |
| NV-6 | `derive_owning_service` (`contract.py:76-89`) | **PARTLY** — it rejects a path with no `services/` segment (real, tested). It cannot reject a *wrong* one: `derive_owning_service("anything/services/glossary-service/x.go")` → `"glossary-service"`, and the path is never checked against the filesystem or a service list. On the read side, `validate_document` (`manifest.py:201-207`) synthesises `f"services/{stored_owner}/"` and re-derives from it — **a tautology that rejects only an empty owner** |
| NV-7 | P4 (item 1.4, second half) | **NO SUBJECT AT ALL** — F3 |

---

## 6 · The bypass table

| # | claim | the path that defeats it, or the search that found none |
|---|---|---|
| 1.1 | manifest generated, starts empty | **None found.** Empty: the committed file is `"declarations": []`, asserted on the artifact (`tests:66-70`) and pinned by `_manifest_drift`. Generated: the previous bypass — *edit the JSON* — now reds CI on both a malformed and a well-formed edit (executed, §3.1). Residual, not a bypass: "produced by a generator" remains unprovable because no generator invocation exists in the tree |
| 1.2 | no legacy in the transitive imports | **Searched, found none.** Method: full read of all six modules; ran the gate over the real package (exit 0); repo-wide `grep -rn agentruntime` for a bridge module or an importer (none in either direction). The round-1 prefix hole is closed with a separator anchor (`gate:91-94`) and both shapes are in the selftest. Residual, acknowledged in the gate's own docstring and correct to acknowledge: the gate lints files **inside** the package, so legacy *data* handed to `SurfaceAssembler(dict)` / `discover(dict)` by an outside caller is a data path no import gate can see. **No such caller exists today** |
| 1.3 | discovery returns zero rows for a legacy declaration of each kind | **No code path.** `discover` (`surface.py:140-178`) reads one parameter and has no other catalog name in scope. **One silent-drop path found within it:** a malformed document yields `[]` with no record and no error (F2). Its tests prove nothing (NV-3) |
| 1.4 | producing an `Admitted` without the check is impossible | **Four working forgeries** (`_TOKEN` import; `object.__new__` + 2× `object.__setattr__`; `object.__setattr__` on a live instance; subclass) — all executed, all succeed, all now correctly disclosed rather than denied. **None of them reaches a manifest row with an unchecked declaration**, because `_row` (`manifest.py:88-109`) `isinstance`-checks and re-runs `check_contract`, and `load` re-runs it per row — executed. **P4: no INSERT exists to bind anything at, and the column it names is a literal at all three legacy INSERT sites** (F3) |
| 1.5 | an unresolvable reference fails generation | **Searched, found none.** `generate` (`manifest.py:141-150`) calls `build` before `write_text`, so a raise leaves no file (`tests:299-305` asserts `not p.exists()`). Round 1's read-path residual is now closed too: `validate_document:213-217` re-resolves members, and I executed a hand-broken member raising `UnresolvedReference` on `load` |
| 1.6 | owning service derived, never authored | **No direct path** — `Declaration` has no owner field (`contract.py:56-63`). **Indirect path, unchanged from round 1:** `source_path` is authored and validated against nothing, so any declaration can select any owner by writing a path that contains `services/<name>/`; executed with a path that does not exist on disk. **New this round:** the read-side check re-derives from the stored owner, so on `load` the owner is the authored value validated against itself (NV-6) |
| 1.7 | every narrowing registers | **The intended path is airtight** — `stage` and `reason` are required fields of `NarrowingRule`, `__post_init__` rejects empties, and `_narrow` records in the same loop iteration that drops. Round 1's two named drop points are closed (`discover(kind=)` now requires a log — executed; the assembler now refuses a malformed doc). **But the gate that was added to catch the next one cannot fire** (F1), one silent drop remains in `discover` (F2), and `Surface` is still constructible outside the package where the gate cannot count it |

---

## 7 · The `Admitted[D]` boundary — what is actually prevented, and by what

Every row executed against the real class at this commit.

| bypass | prevented? | by what |
|---|---|---|
| `Admitted(d, v)` — direct call | **yes** | the custom `__init__` raises when `_token is not _TOKEN` (`admission.py:79-84`) |
| `dataclasses.replace(a, …)` | **yes** | routes through `__init__`, no token → `TypeError` |
| `copy.copy` / `copy.deepcopy` | **yes** | `__copy__` / `__deepcopy__` raise (`:93-97`) |
| `pickle.dumps(a)` | **yes** | `__reduce__` raises (`:90-91`) |
| `a.declaration = x` | **yes** | `frozen=True`'s `__setattr__` |
| `object.__new__(Admitted)` then read | **yes, in the weak sense** | slots unset → `AttributeError` on first read. This is *loudness*, not prevention |
| `from …admission import _TOKEN` → `Admitted(d, v, _TOKEN)` | **no** | a single underscore is a convention; `import` does not honour it |
| `object.__new__` + 2× `object.__setattr__` | **no** | the slots can simply be filled |
| `object.__setattr__(a, "declaration", other)` on a live instance | **no** | `frozen` blocks `a.x = …`, not the two-argument form the class's own `__init__` uses |
| subclass with its own `__init__` | **no** | not final, no `__init_subclass__`, slots inherited; `isinstance` is true |

**The honest statement of what CP-1 guarantees, which is not what the item claims:**

> The **type** is an accident boundary only, and four deliberate forgeries of it work. What is
> actually enforced is narrower and stronger than the type: **no declaration enters or leaves the
> manifest without passing `check_contract` at that moment** — `_row` re-runs it on every write,
> `validate_document` on every read, and a forged `Admitted` wrapping an invalid declaration is
> rejected at the write (executed). The type therefore carries **no provenance**: a forged `Admitted`
> wrapping a *contract-valid* declaration writes a row indistinguishable from an admitted one, and so
> does a row typed into the JSON by hand. Conformance is enforced mechanically; admission-as-history
> is not enforced at all, and for the committed manifest only, the drift gate substitutes for it.

Both of `ARCHITECTURE.md` §6.1's amended layer-1 and layer-3 rows are true of the code at this commit.
Layer 2 is not: the gate it names performs no scan for either form it names (F4).
