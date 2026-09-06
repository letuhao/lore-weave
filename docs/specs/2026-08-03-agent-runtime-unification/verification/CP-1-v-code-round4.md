# CP-1 · V-CODE — verdict, round 4 (item 1.7 only)

**Artifact:** `c5762693864245506ea894145f4731cd178a2638`. `git rev-parse HEAD` verified before the audit
and again immediately before this verdict was written — **HEAD did not move**. `git status --porcelain`
over `app/agentruntime/`, `scripts/agentruntime-membrane-gate.py`,
`contracts/agent-runtime-manifest.json` and `tests/test_cp1_membrane.py` is **empty** — the artifact
paths are clean. **No tracked file was edited.**

**Scope.** One item: **1.7 — "every narrowing registers `{tool, stage, reason, pass}`"**. 1.1/1.2/1.3/
1.5/1.6 are not re-graded; 1.4's P4 half is a PO question and is not graded. The delta under audit is
`git diff 2f24eea11..HEAD -- services/chat-service/`: `surface.py` (+25, the post-condition),
`manifest.py` (+14, `declarations()` delegating to `rows_of`), `__init__.py` (+2, `rows_of` exported),
`test_cp1_membrane.py` (+35).

**Method.** Source read plus **execution**. Mutations were applied to a *copy* of the package in a
scratchpad sandbox (`app/agentruntime/*.py` + `tests/test_cp1_membrane.py` copied out of the tree);
the sandbox has a 19-failure path-dependent baseline (tests that resolve `_REPO`), and every mutation
is reported as *new* failures against that baseline. Caller-side probes ran against the **real,
unmodified** package on `sys.path`. I ran the real suite unmodified (**63 passed**), the membrane gate
(exit 0) and its `--selftest` (exit 0). I read rounds 1–3 and treated every finding as a claim to
re-test.

---

## 1 · Verdict

**1.7 · PASS, with four residuals and one new latent defect.**

This is the first round in which I could not produce a **silent narrowing on any path the shipped code
actually takes**. Round 3's killer is closed, and closed at the mechanism rather than at the test:
injecting round 3's exact defect (`if not rules: kept = kept[:1]`) now raises from **production code**
at `surface.py:146`, not from an assertion in a test file.

| round-3 finding | round-4 status | how I determined it |
|---|---|---|
| **F1** — silent drop on the `rules == ()` branch, 62/62 green | **CLOSED** | injected `G`; `AssertionError` raised at `app/agentruntime/surface.py:146` — *"narrowing lost 2 declaration(s)… 3 admitted, 1 offered, 0 registered at pass 1"*. Caught **twice**: by the law in prod, and by the new n=3 no-rules test |
| **F2** — `declarations()` is a third silent `.get("declarations", [])` | **CLOSED** | executed: `declarations({})` → `ValueError`, `declarations({"declarations": None})` → `ValueError`. Repo-wide grep finds **no fourth copy** |
| **F3** — the conservation *test*'s enumeration is blind to four function shapes | **superseded, not fixed** | the test's enumeration is unchanged, but it is no longer the load-bearing check for the `assemble` path. It remains the only check for `discover` |

---

## 2 · The falsifier — what would have made me say FAIL

I would have written FAIL if any one of these had held. Each was tested by execution, not by reading:

1. **A shipped path that narrows without a record.** I enumerated every point in the package where a
   row can be removed (`surface.py:126` via `_narrow`, `surface.py:204-213` in `discover`, and the
   `kept`/`names` construction in `assemble`) and executed each. Both drop sites record; the third is
   backed by the post-condition. `manifest.py` has **no** skip path — `load`/`validate_document`/`build`
   raise on a bad row rather than dropping it (grep for `continue` / `.pop(` / slicing over the package
   returns nothing but membership tests in `contract.py` and `manifest.py`).
2. **Round 3's `G` surviving.** It does not: the AssertionError above.
3. **A drop that is invisible because the fixtures are too small** (round 3's actual killer). Not
   reproducible any more — see §3.2. The law is in production code, so fixture size bounds only what
   *CI* sees, not what *production* permits.
4. **A fourth copy of the row-reader.** `grep -rn "get(['\"]declarations\|\[['\"]declarations['\"]\]"`
   over the whole repo (`*.py`, `*.go`, `*.ts`, `*.sh`) returns exactly two production sites, and I
   executed both on three malformed documents.

What I did **not** find, and would have needed to find to fail the item: a narrowing performed by the
code as committed, with no record. There is none.

---

## 3 · Question by question

### 3.1 · Can the post-condition be evaded? — **Yes, four ways, none of them on a shipped path**

All executed against the real package (`scratchpad/r4_probe.py`, `r4_mut.py`).

| # | evasion | result | is it live? |
|---|---|---|---|
| **E1** | **narrowing at or before construction** — the law's baseline is `self._rows` (`surface.py:104,143`), which is *the assembler's input*, not the manifest. Injected `self._rows = rows_of(manifest_doc)[:-1]` | **law silent** | no code does this today |
| **E2** | **mutating `_rows` between construction and assembly** — `a = SurfaceAssembler(doc); a._rows.pop(); a.assemble(pass_number=1)` → `names=('tool_0','tool_1')`, **`withheld=()`** | **law silent** | reachable by any caller; `__slots__` permits assignment and the list is mutable |
| **E3** | **a drop that fabricates matching records** — the law compares **counts**, never ids. Two `__ghost__` records balanced a 2-row drop exactly | **law silent** | requires new code; the two existing drop sites record `row["id"]`, and two tests assert the exact record |
| **E4** | **narrowing that never reaches `assemble`** — `discover()` (no law), a new assembler method building `Surface` directly, `dataclasses.replace(surface, names=names[:1])` on the returned object, or `Surface(names=('tool_0',), pass_number=1, withheld=())` built from a bare name list | **law never runs** | the `Surface` single-site gate is the only backstop, and it has holes — below |

**On E4 and the gate.** `SINGLE_SITED = {"Admitted": 1, "Surface": 1}` at
`scripts/agentruntime-membrane-gate.py:140` does real work: I injected a second narrowing method that
calls `Surface(...)` inside the package and `_construction_sites("Surface")` returned **2 sites → gate
FAILS**. But `_construction_sites` (`:143-150`) matches only `getattr(node.func, "id", …)`, i.e. a
plain `Name` call, and scans `PACKAGE.rglob` only. Executed:

- `_m.Surface(...)` (an attribute call) inside the package → **1 site counted, gate passes**, and the
  method narrows silently.
- `Surface(...)` **outside** the package (any CP-2 consumer, any test) → not scanned at all.

So `surface.py:70-74`'s "*the gate counts construction sites instead, so a second one reds CI*" is true
for the plain spelling in the package and false for an attribute call, an alias, or anywhere else.

### 3.2 · Is it reachable? — **Yes, and more importantly its reachability no longer depends on the fixtures**

`test_assembling_with_NO_RULES_offers_everything_admitted` (`tests/test_cp1_membrane.py:449-461`) is
the fixture that reaches it: `_assembler(3).assemble(pass_number=1)`, n=3, `rules=()` — the exact call
shape round 3 proved unreachable. Under mutation `G` the failure comes from `surface.py:146`, so the
law is what fires, and the test's `s.count == 3` is a second, independent backstop for the same defect.

**The structural difference from round 3 is this, and it is the reason for the PASS.** I injected a
drop on a branch **no test drives** — `if len(rules) >= 2: kept = kept[:1]`:

- against the suite: **no new failures — invisible to CI**;
- at runtime with two rules: **`AssertionError: narrowing lost 2 declaration(s)…`**

Round 3's finding was *"a silent narrowing ships and the suite is green"*. That is no longer the
failure mode. A drop on an uncovered branch is now a **loud crash the first time the branch executes in
production**, not a silently smaller surface. No realistic drop *inside `assemble` and after
`self._rows`* remains arithmetically invisible: with `withheld` empty, any `len(kept) < len(self._rows)`
trips, including at n=2. The residual arithmetic blind spots are E1/E3 above — a baseline that was
already narrowed, and a fabricated record — not fixture size.

### 3.3 · `rows_of` consolidation — **exactly one row-reader; no fourth copy**

Repo-wide, `*.py`/`*.go`/`*.ts`/`*.sh`, excluding `node_modules` and `__pycache__`:

| site | reads the key | behaviour on `{}` | behaviour on `{"declarations": None}` |
|---|---|---|---|
| `app/agentruntime/surface.py:39` `rows_of` | yes — **the reader** | `ValueError` | `ValueError` |
| `app/agentruntime/manifest.py:190` `validate_document` | yes — a **validator** | `UntrustedRow` | `UntrustedRow` |
| `app/agentruntime/manifest.py:233-234` `declarations()` | **no — delegates to `rows_of`** | `ValueError` | `ValueError` |

All executed. Round 3's F2 is closed, and `rows_of` is now exported (`__init__.py:45,54`), so the
package's public row-reader and its strict one are the same function. The only remaining note is
cosmetic: the same malformed input raises `ValueError` through one door and `UntrustedRow` through the
other. Both refuse; neither is silent.

### 3.4 · Does the round-4 delta introduce a new hole? — **Yes, one, and it is latent**

**The post-condition counts *every* log entry at that pass, not the entries this assembly wrote.**
`withheld = self._log.for_pass(pass_number)` (`surface.py:127`) is a filter over a log the caller may
supply and share — which is the log's documented purpose (`narrowing.py:52-56`: *"Everything withheld
during one turn"*) and a blessed pattern
(`tests/test_cp1_membrane.py:628-635`, `test_a_shared_log_accumulates_across_assemblers`). Executed
against the real package:

```
discover(doc, kind="skill", log=log, pass_number=1) then SurfaceAssembler(doc, log=log).assemble(pass_number=1)
  -> AssertionError: narrowing lost -3 declaration(s) ... 3 admitted, 3 offered, 3 registered at pass 1

two assemblers sharing one log within pass 1 (docA then docB)
  -> AssertionError: narrowing lost -2 declaration(s) ... 3 admitted, 3 offered, 2 registered at pass 1

the same pass assembled twice on one assembler (a retry)
  -> AssertionError: narrowing lost -1 declaration(s) ... 3 admitted, 2 offered, 2 registered at pass 1
```

Three legitimate compositions, three crashes, each reporting a **negative** loss and naming a defect
that does not exist. The blessed test survives only because it shares its log across passes 1 and 2,
never within one. Nothing outside the package constructs a `SurfaceAssembler` today
(`grep -rn agentruntime` over `services/` and `scripts/` finds only the gate, a CHECK constraint and
`RUNTIME_AGENTRUNTIME`), so this is **latent** — and CP-2, where one turn assembles tools and skills
separately, is exactly where it lands. It fails loud and in the safe direction, so it does not
falsify 1.7; it is a defect introduced by the fix for 1.7.

**Second, smaller: neither round-4 change is guarded by a test.** Both proven by mutation:

| mutation | suite |
|---|---|
| disable the post-condition (`if False and …`) | **63/63 green — invisible** |
| revert `declarations()` to `.get("declarations", [])` | **63/63 green — invisible** |

The law is genuinely armed — I made it fire four times — but *nothing in the tree* proves it can, and
nothing reds if a future edit removes either fix. This is the third consecutive round in which a
correct fix ships with no committed proof that it can go red; the difference is that this time the
mechanism is in production code, so its removal is at least a visible diff in `surface.py` rather than
a quiet regression in a test.

### 3.5 · Does `surface.py`'s prose match its behaviour? — **No. Three sentences still over-claim, one of them verbatim from a claim already corrected next to it.**

| location | claim | what is true |
|---|---|---|
| `surface.py:116` | *"The single assembly point. **The only place a declaration can be removed.**"* | **False.** `discover()` at `surface.py:204-213` removes declarations — 80 lines below, in the same file, and **its own docstring says so**: *"P1 is a property of the module, not of one function in it"* (`:193`). The file contradicts itself |
| `surface.py:120` | *"There is no branch that drops without recording, because there is no second place that drops at all."* | Same. There is a second place; it records, which is what matters — but the sentence asserts the stronger thing |
| `surface.py:140-142` (new this round) | *"A post-condition evaluated on every real assembly has no enumeration to be incomplete: **whatever future code removes a row, by whatever shape, arrives here with the arithmetic broken.**"* | **False three ways, all executed:** a removal at construction changes the baseline (E1); a removal outside `assemble` never arrives (E4); the arithmetic is cardinality-only and balances against fabricated records (E3) |
| `narrowing.py:14` | *"There is no second path, and **`Surface` cannot be built from a name list.**"* | **False, executed:** `Surface(names=('tool_0',), pass_number=1, withheld=())` builds. `surface.py:70-74` **corrects exactly this sentence** for its own docstring — *"An earlier draft said 'constructible only by', which was false: this is an ordinary frozen dataclass and anyone can call it"* — and the sibling copy in `narrowing.py` was left standing. The repo's own lesson, from the round-3 ARCHITECTURE amendment, is that a correction applied only where a verifier quoted it leaves the document more misleading than before |
| `scripts/agentruntime-membrane-gate.py:136` | *"`assemble()` is the only place a declaration can be dropped"* | The same false sentence, third copy |
| `surface.py:29-37` `rows_of` — *"ONE PLACE"* | **now accurate** for the reader; `validate_document` reads the key to validate it and also refuses | 

The pattern across four rounds is unchanged and worth stating once: **the mechanism is now one layer
stronger than it was, and the sentence above it is still one layer wider than the mechanism.** What is
different this round is the direction of the gap — previously the prose covered a hole that shipped;
now it covers a hole that requires new code or a private attribute to reach.

---

## 4 · Findings

### F1 · The conservation law's baseline is the assembler's input, not the manifest
`services/chat-service/app/agentruntime/surface.py:104`, `:143`

`len(self._rows)` is the "admitted" term. A narrowing performed in `__init__`, or by mutating `_rows`
before `assemble`, redefines the very quantity the law conserves. Executed: `a._rows.pop()` yields a
surface of 2 names from a 3-row manifest with `withheld=()` and no error. The one place the law
structurally cannot look is the line above it.

### F2 · The law conserves cardinality, not identity
`services/chat-service/app/agentruntime/surface.py:143`

Two `__ghost__` records balanced a 2-row drop exactly; the law passed and the surface's `withheld`
named declarations that were never admitted. Mitigated today by
`test_a_dropped_declaration_produces_a_full_record` and `test_the_withheld_set_travels_WITH_the_surface`
asserting exact records at the two existing drop sites — i.e. by tests, at the two shapes their author
enumerated.

### F3 · A shared log within one pass turns a legitimate assembly into an AssertionError
`services/chat-service/app/agentruntime/surface.py:127`, `:143`; log contract at `narrowing.py:52-56`

Three compositions the module's own design invites — discover-then-assemble, two assemblers in one
pass, a retry of one pass — raise, reporting a **negative** number of lost declarations. Latent (no
callers yet). Introduced by this round's fix.

### F4 · Neither round-4 change has a test that goes red when it is removed
`services/chat-service/app/agentruntime/surface.py:143`, `manifest.py:233`

Disabling the post-condition, and reverting `declarations()` to the silent `.get`, each leave the suite
at **63/63 green**. Both fixes are correct and unguarded.

### F5 · `Surface`'s single-site gate misses an attribute call and everything outside the package
`scripts/agentruntime-membrane-gate.py:143-150`

`_construction_sites` matches `ast.Call` with `func.id == "Surface"` over `PACKAGE.rglob` only.
Executed: a plain second site is caught (2 sites → gate fails); `_m.Surface(...)` in the same file is
not (1 site → gate passes); a `Surface(...)` outside the package is never scanned. The gate is the only
backstop for the E4 class.

### F6 · Round 3's `F` (a `discover` drop keyed on a field the fixture always has) is still open
`services/chat-service/app/agentruntime/surface.py:195`, gate at `tests/test_cp1_membrane.py:463-532`

Injecting `rows = [r for r in rows_of(manifest_doc) if "kind" in r]` is **invisible to the whole
suite** — every fixture row carries a `kind`. `discover` is outside the post-condition entirely, so the
conservation *test*, with its `params[0] == "manifest_doc"` enumeration, is still the only thing
watching it, and it samples one fixture.

### F7 · Four prose claims assert more than the code delivers
`surface.py:116`, `:120`, `:140-142`; `narrowing.py:14`; repeated at `agentruntime-membrane-gate.py:136`.
Detail in §3.5. `narrowing.py:14` is the un-corrected copy of a sentence corrected 60 lines away.

---

## 5 · Vacuity (NV) — this delta

| # | check | armed? |
|---|---|---|
| NV-1 | the post-condition, `surface.py:143` | **YES.** Fired four times under mutation (`G`, `H`, a branch-conditioned drop, a `rows_of` drop) and three times on legitimate input (F3). Its subject occurs at n≥2 with any unrecorded drop after `self._rows` |
| NV-2 | the post-condition's **test coverage** | **NO.** Removing it changes nothing in the suite. Armed in fact, unwitnessed in the tree |
| NV-3 | `test_assembling_with_NO_RULES_offers_everything_admitted` (`tests:449`) | **YES.** n=3 is the smallest fixture that distinguishes a drop from a no-op on this branch; reds under `G` and under `D1`. This is the coverage round 3 named, and it was added |
| NV-4 | `declarations()` → `rows_of` (`manifest.py:233`) | **YES in behaviour** (executed on three malformed documents), **NO as a gate** — no test reds if it regresses |
| NV-5 | conservation *test* enumeration (`tests:501-521`) | **PARTIAL, unchanged from round 3.** Still `params[0] == "manifest_doc"` over `vars(surface)`; still one fixture; F6 shows it green over a real silent drop in `discover` |
| NV-6 | `Surface` single-site gate (`gate:140`) | **YES for the plain spelling in the package**; blind to attribute/alias calls and to everything outside `PACKAGE` (F5) |

---

## 6 · The bypass table — item 1.7

| the path | status |
|---|---|
| a drop on the `rules == ()` branch of `assemble` (round 3's killer) | **closed** — `AssertionError` from `surface.py:146`, plus an independent test assertion |
| a drop on any *other* branch of `assemble` | **closed in production** — invisible to CI, loud at runtime. Proven with `len(rules) >= 2` |
| `manifest.declarations()` serving `[]` for a malformed document (round 3's F2) | **closed** — raises `ValueError`; no fourth copy repo-wide |
| narrowing at construction, or by mutating `_rows` | **open** — law's baseline; executed, `withheld=()`, no error. Requires a private attribute or new code in `__init__` |
| a drop with fabricated records | **open** — the law is cardinality-only; executed |
| narrowing outside `assemble` (`discover`, a new method, `dataclasses.replace`, a bare `Surface(...)`) | **open** — only the single-site gate backstops it, and F5 gives two ways past it. `discover` itself records today |
| `discover` dropping on a field the fixtures always carry | **open** — F6, executed, whole suite green |
| a silent narrowing **in the code as committed** | **none found.** Method: enumerated every removal site by reading all six modules, grepped the package for `continue`/`.pop(`/slicing/`filter(`, executed every public entry point on well-formed and malformed documents, and ran seven source mutations against the suite |

---

## 7 · Summary for the record

1.7 holds for the artifact as it stands. The round-4 change is structurally different from its three
predecessors in the one way that matters: **it is a post-condition in production code, so a coverage
gap in the suite no longer converts into a silent narrowing in the product** — it converts into a
crash at the moment the gap is exercised. I could defeat it only by narrowing the assembler's own
input, by fabricating balancing records, or by not calling `assemble` at all; none of those is what
the committed code does.

What would have made me say otherwise: any shipped path that drops a declaration without a record. I
looked for one by enumeration and by execution, across every entry point in the package, and found
none. Had `declarations({})` still returned `[]`, or had round 3's `rules == ()` drop still survived
the suite, this would have been a fourth FAIL.

Two things should not be lost in the PASS. The fix **introduced** a latent crash on the log-sharing
pattern the module itself documents and tests (F3) — a real defect, in the safe direction. And for the
third round running, the sentence above the mechanism claims more than the mechanism does, including
one sentence (`narrowing.py:14`) that was already corrected 60 lines away and left standing here.
