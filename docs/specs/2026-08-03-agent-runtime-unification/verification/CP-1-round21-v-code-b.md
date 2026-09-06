# CP-1 · round 21 · V-CODE **B — the membrane**

**Artifact:** `9818c7bc57c8381a4dddbbfcc88cbaadc5e89f06` at start **and** at finish — it did not move.
Graded delta `3caac262d` + `ad4e69030`, diffed against `b73e086ca`.
Working tree verified `git status --porcelain` **empty** at start and at finish. **No `git checkout`
was used at any point**; every injection was patched and restored as BYTES from my own snapshot in
the scratchpad, and every restore was asserted equal.

---

# ▶ THE CENSUS VERDICT — **it works, and it does not mean what it says**

`scripts/agentruntime-census.py` is the first artifact of this run whose purpose is to make *"a
finding is closed"* mechanical. It is graded first, and it is graded as a gate.

**It runs, it reproduces, and it fails safe on the axis it was built for.** I ran it verbatim from
the repo root: `agentruntime-census selftest OK - 68 raise sites, fires on a guarded one` →
`agentruntime-census: 68 sites, 13 silent, 55 red`, **exit 0**. I then compared all eight package
files byte-for-byte against a pre-run snapshot: **8/8 identical**. I re-derived the enumeration with
my own independent AST walker: **68 sites, member for member, ordinal for ordinal**. The measurement
converges for the fourth independent time.

**And then it is wrong in the way that matters.** Its output is not a measurement of guarding. It is
a measurement of *whether one particular suite's assertions can distinguish this raise from the next
one*. Those are different sentences, and the allowlist header states the first one:

> `# Refusal sites the suite does NOT notice being removed.`
> `# … Every line is a claim that nothing checks; adding one is a decision, and removing one is a closed finding.`

**Five of the thirteen lines are not that claim.** One is checked by an existing test that passes
anyway. Two are covered by a same-class sibling three lines away. **Two are unreachable dead code.**
Executed, one site at a time, over the whole enumerated allowlist — not a sample.

## ▶ Q2 — is the allowlist honest? **NO. 5 of 13 rows mean something else.**

Method: for each of the 13, neuter *exactly that site* (the census's own `_neutered`, its own
`_sites`), then run a probe that exercises **the condition the site guards** and record what the
system actually does. The census asks *"does the suite go red"*; I asked *"does the semantic still
refuse, and from where"*. Control + neutered, 13/13, restored and asserted after each.

| # | site (allowlist row) | neutered ⇒ what actually happens | what the row means |
|---|---|---|---|
| 1 | `canon.py::_norm::NotCanonicalisable::1` (float) | `NotCanonicalisable: $.a: float has no canonical form` — the **fallback at `canon.py:84`** catches it | 🔴 **GUARDED, MIS-RECORDED.** `test_cp1_membrane.py:1584` is `pytest.raises(canon.NotCanonicalisable, match="float")`. The sibling's message interpolates `type(value).__name__` — which *is* `"float"` — so **the test that exists for this exact clause still passes**. The row says "nothing checks"; something does |
| 2 | `canon.py::_norm::NotCanonicalisable::2` (non-`str` key) | `TypeError: normalize() argument 2 must be str, not int` | 🟡 refuses **worse** (bare `TypeError`; `NotCanonicalisable` *is* a `TypeError`, so a caller catching the parent sees no change). No test — row is honest, verdict "unguarded" is not |
| 3 | `canon.py::_norm::NotCanonicalisable::4` (fallback) | **ACCEPTED** — `digest(date(2020,1,1))` returns `fe95e167…` | ✅ **genuinely unguarded** |
| 4 | `contract.py::check_contract::ContractViolation::7` | **ACCEPTED** — `admit(Declaration(members=("Bad Id!",)))` returns an `Admitted` | ✅ genuinely unguarded **at `admit()`**; masked by M5 on the document path |
| 5 | `contract.py::check_row_shape::ContractViolation::2` | `ContractViolation: t0.w.1: is a field the contract does not define…` — **sibling `::3`, same class** | 🔴 **MASKED, MIS-RECORDED.** A non-string key is refused either way |
| 6 | `contract.py::check_row_shape::ContractViolation::7` | `ContractViolation: s0.w.members[0]: not a declaration id: ''` — **`check_contract::7`, same class** | 🔴 **MASKED, MIS-RECORDED** at the door callers use (`check_row`) |
| 7 | `manifest.py::build::UntrustedRow::4` (`:244-246`) | **byte-identical to control**, both raise `ContractViolation` | 🔴 **UNREACHABLE.** AST-enumerated inside the probe: `check_row`/`check_row_shape`/`check_contract` raise **`['ContractViolation']` only**, and `ContractViolation` subclasses `UntrustedRow`, so the preceding `except ContractViolation` takes every path. The `except UntrustedRow` clause is **dead** |
| 8 | `manifest.py::generate::UntrustedRow::1` | `AttributeError: 'NoneType' object has no attribute 'exists'` | 🟡 refuses **worse**; genuinely untested |
| 9 | `manifest.py::generate::UntrustedRow::2` (the TOCTOU re-check) | **ACCEPTED** — the manifest is written with every origin reset | ✅ **genuinely unguarded**, and it is the one the flag exists for |
| 10 | `manifest.py::validate_document::UntrustedRow::5` | `TypeError: 'NoneType' object is not iterable` | 🟡 refuses **worse** — and `TypeError` is **not** a `ValueError`, so `except UntrustedRow` callers stop catching it |
| 11 | `manifest.py::validate_document::UntrustedRow::6` (`:427-428`) | **byte-identical to control** | 🔴 **UNREACHABLE**, same mechanism as #7 |
| 12 | `surface.py::OrderBy.__post_init__::ValueError::3` | list-pair `["cost2","asc"]` → **ACCEPTED**, sorts, `effective_keys()` returns it. 3-tuple/1-tuple → `ValueError` *from Python's own unpacking*. scalar → `TypeError` | ✅ unguarded **for the list vehicle**; the other three are masked by the unpack, which is why the clause reads silent |
| 13 | `surface.py::TakeWhileBudget.__post_init__::ValueError::1` | **ACCEPTED** — `TakeWhileBudget(budget=-1)` constructs | ✅ **genuinely unguarded** — the `k=0` failure of the class next door, in the sibling the `TopK` comment was written about |

**Score: 5 rows of 13 (38%) do not mean what the file says.** Two of those five (#7, #11) are dead
code, and an allowlist has **no vocabulary for "unreachable"** — its remediation text is *"guard it
or record it deliberately"*, which sends the next builder to write a test for a handler that can
never execute. **The correct action on #7 and #11 is `delete`, and the instrument cannot say so.**

The systematic cause is one sentence: **the suite mostly asserts an exception CLASS, and this package
is built out of layered checks of one class.** So the census can only resolve a site whose removal
changes the observation the suite happens to make. Where guarding is layered — which is everywhere
the design is good — it under-reports, and #1 shows it under-reports even against a `match=`.

## ▶ Q1 — can it be defeated? **Yes, by four shapes, three of which are ordinary refactors.**

| # | shape | executed? | result |
|---|---|---|---|
| D1 | **a weakened CONDITION, raise untouched** | ✅ | `type(key) is not str` → `not isinstance(key, str)`: **`134 passed`**. `type(m) is not str` → `isinstance`: **`134 passed`**. Both at once: **`134 passed`**. The census output is *unchanged* — the raise is still there and still silent. **A closure certified by this gate can be undone without one census row moving.** (This is B18-8, and the new gate is blind to it by construction) |
| D2 | **extract the raises into a helper** | ✅ (AST) | `check_contract`'s seven `raise ContractViolation(` → `_reject(…)`: `contract.py` goes **18 → 12** sites; **7 ids vanish, 1 appears**. The census's headline promise — *"the sibling has its own id and its own row"* — does not survive an ordinary refactor. In compare mode the gate prints **`NOW GUARDED contract.py::check_contract::ContractViolation::7`**, which is **false** |
| D3 | **`assert` instead of `raise`** | ✅ | one clause rewritten as `assert d.kind in KINDS`: **18 → 17** sites, the clause still refusing at runtime, **no row**. And under `python -O` the clause itself disappears |
| D4 | **`__init__.py`, excluded BY NAME (`census.py:112`), and a non-recursive glob** | ✅ | a raise added to `__init__.py` enumerates as 1 site and the census **skips the file**. Today `__init__.py` holds 0 raises, so this is latent — but `__init__.py` is exactly where an import-time guard belongs |
| D5 | `sys.exit` / `os._exit` / `return None` where a raise belonged / a raising call inside a comprehension | ⚠️ argued | `_sites` matches `ast.Raise` only. The package has **0 `assert` and 0 `exit` calls today** (measured), so D3–D5 are latent, not live |

**What it cannot be defeated by:** a one-liner `if x: raise` or a multi-statement raise line — I
enumerated every site for that hazard and found **zero**, so `_neutered`'s line-replacement is
faithful on today's tree. The 68 also survived my independent re-derivation exactly.

## ▶ Q3 — does it fail closed? **Two of three. The third leaves the tree broken.**

| case | executed | result |
|---|---|---|
| normal completion | ✅ | 68/13/55, **exit 0**, **8/8 files byte-identical to a pre-run snapshot** |
| **a syntactically broken module** | ✅ | appended `def broken(:` to `ambient.py` → **exit 1**, `SyntaxError: invalid syntax`, uncaught, **before any file was written**. It **stops**, it does not skip. ✅ fail-closed — though as a raw traceback, not one of its own `SELFTEST FAIL:` lines |
| **killed mid-run** | ✅ | `Popen`, 45 s, `kill()` → `M services/chat-service/app/agentruntime/admission.py`, and the suite goes **`1 failed, 133 passed`**, the failure named `TestAdmittedCannotBeProducedWithoutTheCheck::test_round_trip_forgery_is_refused[deepcopy]`. 🔴 **A production module is left neutered in the live tree and the suite blames a test.** This is verbatim the carried finding *"the probe modules are written into the live `app/` tree, so an interrupted run leaves the suite red blaming the wrong file"* — **reproduced in the new instrument, one round after being recorded**, which is the second time this script has reproduced a defect a verifier had already written down (the first was `write_text` and CRLF, which the docstring admits) |
| the restore guarantee itself | ✅ | `assert path.read_bytes() == raw` at `census.py:123` and `:160` is an **`assert`**. Executed: `python -O -c "assert False"` does not fire. **`python -O scripts/agentruntime-census.py` silently removes the one guarantee the docstring is built around** |

## ▶ Q4 — is the id stable? **No. It is a positional ordinal, and an insertion re-points every later row.**

`module::qualname::ExcClass::ordinal` survives a *move*, which is what the docstring claims and it is
true. It does **not** survive an *insertion*, and the failure is silent in the place it matters.

Executed: one new `raise UntrustedRow("a NEW refusal…")` inserted **above** the others in
`validate_document`, then a scoped census over that function (8 sites, suite run per site):

```
SILENT  …validate_document::UntrustedRow::1      <- the genuinely new refusal
RED     …::2  …::3  …::4
RED     …validate_document::UntrustedRow::5      <- IN THE ALLOWLIST
SILENT  …validate_document::UntrustedRow::6      <- IN THE ALLOWLIST
SILENT  …validate_document::UntrustedRow::7
gate prints -> NEWLY SILENT: [::1, ::7]   NOW GUARDED: [::5]
```

The gate **does** fire (exit 1). Its three lines are:

* `NEWLY SILENT ::1` — **true**;
* `NEWLY SILENT ::7` — **misattributed**: `::7` is the old `::6`, renumbered, not a new hole;
* `NOW GUARDED ::5` — **FALSE.** Nothing became guarded. `::5` now names a different raise. And its
  remediation text is *"good news: drop it from the allowlist in the same change"* — **following the
  gate's own instruction deletes the record of a real unguarded site.**

Worse, the row that moved silently produces **no diff at all**: the allowlist's `::6` entry now
certifies a site it was never generated against. **An allowlist that goes stale silently is worse
than none** — the docstring's own sentence, and the id it chose does not meet it.

## ▶ And the instrument that decides every future closure has **no test**

`grep -rl "agentruntime-census"` over `services/`, `scripts/`, `tests/`: **one hit, the script
itself**. `grep -c census` in `test_cp1_membrane.py`: **0**. The membrane gate next door *is*
referenced from the suite; this is not. Its only self-check is `--selftest`, which nothing runs but
itself, and which is a **fixed single probe** in `check_row_shape` — it proves the harness can fire
once, not that the enumeration is complete or that the ids are stable.

**Census verdict: the measurement is real and reproducible; the record it produces is 62% accurate
and its remediation instructions are wrong on 5 of 13 rows and on 2 of the 3 lines it printed in the
one drift scenario I drove. It is not yet safe to make "a finding is closed" mean "this row moved."**
Three changes would make it so, and all three are small:

1. **A third state.** `SILENT` must split into `UNGUARDED` and `COVERED-BY-SIBLING`, decided by
   re-running the site's *semantic* probe, not the suite. Without it, #1/#5/#6 send fixes at
   already-guarded code — the run's most-repeated failure, now automated.
2. **A `DEAD` state**, or a rule that a site whose neutering is behaviourally identical is reported
   for deletion. #7 and #11 are unreachable and the allowlist makes them permanent.
3. **A content-addressed id**, not an ordinal — `module::qualname::ExcClass::sha1(source_segment)`.
   It survives insertion, which the ordinal does not.

---

# OVERALL: **FAIL**

Not on the census's arithmetic — that converges. On three things: the allowlist is 38% mis-recorded
against its own stated meaning (**B21-1, B21-2**); the gate is blind to the exact defect class
(**B18-8**) that is open in the code it is measuring (**B21-3**); and an interrupted run leaves a
production module neutered in the live tree (**B21-6**) — the carried finding, reproduced in the
instrument built this round. Plus **six carried findings re-measured open**, and a register that
still drops rows.

## Per-claim verdicts, each with its falsifier

| # | claim under test | falsifier I ran | verdict |
|---|---|---|---|
| 1 | the census enumerates every refusal in the membrane | my own independent AST walker; a hazard scan for one-liner raises; a hunt for `assert`/`exit` forms | ✅ **PASS on today's tree** — 68/68 member-for-member, 0 hazards, 0 asserts. ❌ but D1–D4 defeat it on any tomorrow |
| 2 | the 13 allowlist rows are refusals nothing checks | neuter each, run a probe for the guarded condition | 🔴 **FAIL — 5 of 13** |
| 3 | it fails closed | broken module; `kill` at 45 s; byte-compare 8 files | 🟡 **PARTIAL** — clean and broken-module cases pass; **interruption fails** |
| 4 | the id survives an edit that moves it | insert one same-class raise above an allowlisted one, re-census the function | 🔴 **FAIL** — 1 true / 1 misattributed / 1 false, and one row re-points with no diff |
| 5 | `dict(r)` is shallow at all four doors | `row["members"] is source["members"]`, then mutate | 🔴 **CONFIRMED OPEN** (B20-1) |
| 6 | B18-8 open | downgrade both pins, run the suite | 🔴 **OPEN, 4th round** |
| 7 | B18-11 open | AST over the package for `canon.<attr>` | 🔴 **OPEN, 4th round** |
| 8 | B18-10 open | add a fifth exported door, run suite **and** gate | 🔴 **OPEN, 7th round** |
| 9 | `surface.py:305` open | 5 key-pair vehicles, control + neutered | 🔴 **OPEN, 3rd round** |
| 10 | `_ID` has no length bound | a 300-char id through `admit → build → validate_document` | 🔴 **OPEN, 3rd round** |
| 11 | the `Open, carried` register is trustworthy | diff it against every R19/R20 verdict summary | 🔴 **FAIL — B20-4 confirmed and understated** |

---

## 2 · `dict(r)` IS SHALLOW — confirmed at all four doors, and the fix is neither a deep copy nor a freeze alone

Executed:

```
rows_of            members IS the source list: True
declarations       members IS the source list: True
discover           members IS the source list: True
validate_document  members IS the source list: True
```

And the consequence, executed:

```
rows = surface.rows_of(d)                       # validated; check_document_rows/M5 has run
d["declarations"][1]["members"].append("GHOST_NEVER_ADMITTED")
the ALREADY-RETURNED validated rows changed: True
they now carry: [['t0', 'GHOST_NEVER_ADMITTED']]
```

…and two doors on one document share the object outright:

```
rows_of(d) and discover(d) share one members list: True
mutating one changed the other: ['t0', 'GHOST2']   ...and the SOURCE document too
```

**This is the same sentence as `validate_document`'s own `{**doc}` fix, one level down.** That
comment says *"A validator returns what it validated, or it has validated nothing"* and *"nothing
this function returns was read after it was checked"* — and the `members` list it returns is the
caller's own object, so it **can be** written after it was checked. `members` is the field M5 exists
for and the field `['ghost']` reached four consumers through for three rounds.

**Is a deep copy the fix?** Partly, and I would not stop there.

* A deep copy closes the aliasing but leaves the returned row a **plain mutable `dict`**, so
  `rows[0]["members"].append("ghost")` still produces a row that passed no clause — just one that no
  longer corrupts the source. Executed: a returned row accepts `row["injected"] = 1` freely.
* **Freezing alone is not enough either**, because freezing the row without copying still hands back
  a frozen view *over the caller's list*.
* The shape that matches this package's own decisions elsewhere — `Declaration` is
  `@dataclass(frozen=True, slots=True)` with `members: tuple[str, ...]` — is to **rebuild the row
  from what was checked, with `members` as a `tuple`**. That is one line at each of the two producers
  (`surface.py:72`, `manifest.py:448`), it is a copy *and* a freeze, and it makes the aliasing
  inexpressible rather than merely absent. `ROW_FIELDS` would need `members` to accept `tuple`, which
  is the same one-line schema decision `ROW_REQUIRED`'s gate already exists to force.

⚠️ **A warning that belongs to this run's own record:** `surface.py:72` and `manifest.py:448` are
*siblings*. Seven times this run a fix landed on one of a pair. **Both, or neither.**

Reachability: **guard-only today** (zero importers outside the package) → **production-reachable the
moment CP-2.1 imports it**.

## 3 · B18-8, B18-11, B18-10 — all three re-measured, all three OPEN

### B18-8 — 4th round, and the new gate is structurally blind to it

| injection | suite |
|---|---|
| `type(key) is not str` → `not isinstance(key, str)` | `134 passed` |
| `type(m) is not str or not m` → `not isinstance(m, str) or not m` | `134 passed` |
| **both at once** | `134 passed` |
| *control:* `type(row) is not dict` → `isinstance(row, dict)` (both reads) | **`2 failed`, 132 passed** |

The control matters: **one of the three exact-type pins in `check_row_shape` is guarded and two are
not**, so this is a coverage gap in a family, not an absent convention — the sibling pattern again.
And note what the census says about all three: **nothing**. It measures raises; this is a condition.

### B18-11 — 4th round, sharper each time

```
contract.py      imports at [21]  canon.<attr> uses: []
manifest.py      imports at [27]  canon.<attr> uses: []
'canon' in __all__: False
nfc() docstring still names manifest.load as a door: True
```

Two dead imports, **zero** attribute uses anywhere in the package, not exported, and the refuted
docstring at `canon.py:42` — which claims `manifest.load` is *"one of the two doors §0.14.2 names"*
and that it *"did not normalise"* — is **verbatim**, a full round after being refuted in the code it
describes (`contract.py:285-293` records the refutation and removed the call; the docstring that
motivated the call was left standing).

### B18-10 — **7th round**

```
suite: (0, '134 passed')
gate : (0, 'agentruntime-membrane-gate OK - 8 module(s), 0 allowed external import(s), 2 single-sited type(s)')
door serves an unvalidated row: ['TYPED BY HAND!!:nope']
```

A fifth exported row-reading door, added to `surface.py` **and** `__init__.__all__`, passes the suite
**and** the membrane gate **and** serves a hand-typed row. The scoping argument (*"zero importers, so
it is honest"*) is still true and still means the same thing: **it becomes dishonest at the commit
that imports the package**, with no new defect and no round to catch it.

## 4 · THE RECORD — **B20-4 is confirmed, and it is understated. The register is NOT trustworthy.**

R20's corrected `Open, carried` (RUNSTATE `:1983-1987`) restored the `:531`/`:542` contradiction and
added `O_S`, `dict(r)`-shallow and B20-4 itself. It still does not carry the four B20-4 names:

| id | subject | in R20's list, by id **or** by paraphrase? | I re-measured |
|---|---|---|---|
| **B18-1** | the subset gate contributes 0 of 2 | ❌ absent | R20-B `:437-440`, executed |
| **B18-2** | the eleventh guard reds on CP-2's first operation | ❌ absent | R20-B `:442-444`, executed |
| **B18-9** | the document-stamp gap at the consumer doors | ❌ absent | ✅ **I re-measured it myself, below** |
| **B19-5** | one test, three clauses, one indistinguishable message | ❌ absent | R20-B `:519` |

The nearest text to B18-9 in the list — *"`dict(r)` is shallow (all four doors hand back the source
document's own `members` list)"* — is **B20-1**, a different finding. The shared phrase *"four
doors"* is a coincidence of wording, and reading it as coverage of B18-9 is exactly how a row gets
lost. I re-measured B18-9 rather than take it on the record:

```
no manifest_version      rows_of=ACCEPT  declarations=ACCEPT  discover=ACCEPT  validate_document=refuse
manifest_version=999     rows_of=ACCEPT  declarations=ACCEPT  discover=ACCEPT  validate_document=refuse
contract_version=banana  rows_of=ACCEPT  declarations=ACCEPT  discover=ACCEPT  validate_document=refuse
no contract_version      rows_of=ACCEPT  declarations=ACCEPT  discover=ACCEPT  validate_document=refuse
undefined top key        rows_of=ACCEPT  declarations=ACCEPT  discover=ACCEPT  validate_document=refuse
```

**5/5 malformed documents, accepted by three exported doors and refused by the fourth.** Open.

### 🔴 B21-9 — and **two more** were dropped in the same edit, which nobody has counted yet

Diffing R19's list (RUNSTATE `:1903-1907`) against R20's:

| dropped | closure recorded anywhere? |
|---|---|
| **W4 / W7** | ✅ legitimately — shipped this round |
| the `O_J` residual | ✅ legitimately — superseded by `O_S` |
| **T10** | ❌ **none.** R19's line reads *"T10/T11d"*; R20's carries **only T11d** |
| **route 25** | ❌ **none.** `grep "route 25"` over all four R19/R20 verdicts: **one hit**, and it is R19-B *quoting the register*. No verdict records a closure |

So the true count is **B20-4's four, plus T10, plus route 25 — six**. And beyond the register's own
line, eleven further findings that R19-A/R20-A/R20-B record open (A19-3, A19-7, A19-10, A19-11,
A19-12, A20-4, A20-5, B20-3, B20-5, B20-6, B20-7) have never been carried at all.

**Verdict on the record: NOT trustworthy — and the reason is now diagnosable rather than moral.** The
register is **hand-typed prose in a `·`-separated sentence**, and it has lost rows in **four
consecutive rounds** while being corrected twice. Correcting it a third time will not work; the
correction *is* the defect surface. The register must be **generated from the verdicts** — the same
sentence this run has already accepted about consolidations (*"a consolidation is a count, not a
sentence"*) applied to itself. That is a ten-line script over the `## 6a` tables that every verdict
already emits, and it is a smaller change than the census.

## 5 · `surface.py:305` and `_ID`'s missing length bound — both carried, both open

**`surface.py:305`, 3rd round.** Five vehicles, control vs neutered:

| vehicle | control | site neutered |
|---|---|---|
| `(["cost2", "asc"],)` | `ValueError: keys[0] is not a (field, direction) pair` | 🔴 **ACCEPTED** — `effective_keys()` returns `(['cost2','asc'], ('id','asc'))` and `sort()` ranks on it |
| `(("cost2","asc","x"),)` | refused | `ValueError: too many values to unpack` |
| `(("cost2",),)` | refused | `ValueError: not enough values to unpack` |
| `(7,)` | refused | `TypeError: cannot unpack non-iterable int` |
| `("ab",)` | refused | `ValueError: keys[0]: unknown direction 'b'` |

So the clause is load-bearing for **exactly one** vehicle and Python's unpacking masks the rest —
which is *why* the census reads it silent, and why a test written to close it must use the **list**
pair or it will pass with the clause deleted. A mutable list inside a `frozen=True, slots=True`
dataclass is also the ranking's identity gone: the stage is no longer hashable, and *"a closure is
not content-addressable, so a pipeline built from closures has no identity"* is this module's own
argument.

**`_ID`, 3rd round.** Executed: `len=300`, `_ID.match → True`, `admit` + `build` OK, **written id
length = 300**, and `validate_document` round-trips it at 300. An id decides membership in every
allow-list and deny-list it is compared against (§0.14.1), and it is unbounded.

---

## Bypass table

| guard | bypass | executed | reachable |
|---|---|---|---|
| the census's "closed = SILENT→RED" | weaken the **condition**, leave the raise | ✅ 3 patches, `134 passed` ×3 | any future fix |
| the census's per-site id | extract raises into a helper (18→12 sites) | ✅ AST | any refactor |
| the census's per-site id | insert one same-class raise above an allowlisted one | ✅ scoped census | any new clause |
| the census's enumeration | write the clause as `assert` (18→17) | ✅ AST | any future guard |
| the census's enumeration | put the guard in `__init__.py` | ✅ | latent (0 sites today) |
| the census's byte-restore assertion | `python -O` | ✅ | operator error |
| `check_row_shape`'s key pin | a `str` subclass (B18-8) | ✅ 3 patches | adversarial |
| `check_row_shape`'s member pin | a `str` subclass (B18-8) | ✅ | adversarial |
| four doors' "returns what it validated" | mutate the shared `members` list afterwards | ✅ | guard-only → CP-2 |
| `rows_of`/`declarations`/`discover` | a malformed document-level stamp (B18-9) | ✅ 5/5 | guard-only → CP-2 |
| `OrderBy`'s key-pair shape | a 2-element **list** | ✅ | guard-only → CP-2 |
| `TakeWhileBudget`'s budget floor | `budget=-1` | ✅ | guard-only → CP-2 |
| `_ID` | a 300-character id | ✅ end-to-end | adversarial |
| four exported doors | add a fifth (B18-10) | ✅ suite + gate green | structural |

## Red-ability table — **my denominator, derived from the delta itself**

The delta makes **8 checkable claims about the instrument**. That is my denominator, and it is
derived from the script's own docstring and CI comment, not from what happens to be tested.

| # | claim the delta makes | test that would go red | red-able? |
|---|---|---|---|
| 1 | the enumeration finds every refusal | `--selftest`'s `len(sites) < 50` | 🟡 **weak** — a floor of 50 over 68 tolerates losing 18 sites |
| 2 | neutering a guarded refusal reds the suite | `--selftest`'s fixed probe in `check_row_shape` | ✅ (one site) |
| 3 | the restore reproduces BYTES | `assert path.read_bytes() == raw` | 🟡 an `assert`; **gone under `-O`** |
| 4 | every allowlist line is a refusal nothing checks | — | ❌ **none** |
| 5 | the id survives an edit that moves it | — | ❌ **none** |
| 6 | it fails closed on a broken module | — | ❌ none (behaviour is correct, unguarded) |
| 7 | it fails closed on interruption | — | ❌ **none, and the behaviour is wrong** |
| 8 | CI runs it on every PR to `main` | — | ❌ none (trigger verified by reading: `pull_request` → `main`, no `paths:` filter, so it **does** run) |

**Red-able: 1 of 8 cleanly, 3 of 8 weakly. 5 of 8 have no test at all — and the script has zero test
references anywhere in the repository.** The artifact proposed as CP-1's closure criterion is the
least-guarded thing in the delta.

For the **findings** I raise, the denominator is 11 (below): **red-able today: 0/11** — every one is
demonstrated by an injection I wrote, and none has a committed test.

## Sibling table

| rule | applied to | missed | verdict |
|---|---|---|---|
| exact-type pin against a `str`/subclass | `row` ✅ (2 tests fire) | **`key`** ✗ · **`m`** ✗ | 1 of 3 | 🔴 B18-8 |
| a returned row is rebuilt from what was checked | the row `dict` ✅ · the two doc stamps ✅ | **`members`, the list itself** ✗, at both producers | 2 of 3 | 🔴 B20-1 |
| a narrowing parameter has a floor | `TopK.k >= 1` ✅ · `cost_field` non-empty ✅ | **`budget >= 0`** ✗ | 2 of 3 | 🔴 allowlist #13 |
| a stage parameter's shape is bounded | `keys` is a tuple ✅ · `field` ✅ · `direction` ✅ | **the pair itself, for a list** ✗ | 3 of 4 | 🔴 B19-4 |
| a refusal carries C-12 structure | `ContractViolation` ✅ everywhere | `generate::1` → `AttributeError` ✗ · `validate_document::5` → `TypeError` ✗ *(once the site is removed)* | — | context |
| the doc-level clauses run at every door | `validate_document` ✅ | `rows_of` ✗ `declarations` ✗ `discover` ✗ | 1 of 4 | 🔴 B18-9 |
| a harness must not leave the tree dirty | byte restore on the happy path ✅ | **on interruption** ✗ | 1 of 2 | 🔴 B21-6 |
| a deleted claim's docstring goes with it | the call-site comment ✅ | **`nfc()`'s docstring** ✗ | 1 of 2 | 🔴 B18-11 |

## Guard table

| behaviour | guarded by | strength |
|---|---|---|
| a float is not canonicalisable | `:1584` `match="float"` | 🔴 **passes with the clause deleted** — the fallback's message contains the type name |
| a set is not canonicalisable | `:1588` `match="no order"` | ✅ site `::3` reds |
| an unknown type is not canonicalisable | — | ❌ none |
| a non-`str` dict key is refused *as* `NotCanonicalisable` | — | ❌ none (degrades to bare `TypeError`) |
| `admit()` refuses a malformed member id | — | ❌ none at that door |
| a non-string row key is refused | sibling `::3` | 🟡 refused, but the named clause is untested |
| a malformed member is refused | sibling `check_contract::7` | 🟡 same |
| `generate()` without a location refuses | — | ❌ none |
| the `exists`/`load` TOCTOU re-check | — | ❌ none — **and it is the one `bootstrap=` exists for** |
| `declarations` must be a plain list | — | ❌ none (degrades to `TypeError`, which is not a `ValueError`) |
| an `OrderBy` key-pair is a 2-tuple | — | ❌ none for the list vehicle |
| `budget >= 0` | — | ❌ none |
| the census restores bytes | its own `assert` | 🟡 gone under `-O` |
| the census's ids are stable | — | ❌ none |

## Reachability verdict on **every** finding

| id | finding | class | production-reachable today? |
|---|---|---|---|
| **B21-1** | 5 of 13 allowlist rows are not "a refusal nothing checks" — 1 is tested, 2 are sibling-covered, 2 are dead | **instrument correctness** | **YES** — it is a repo artifact and the proposed closure criterion |
| **B21-2** | `manifest.py:244-246` and `:427-428` are unreachable `except UntrustedRow` handlers; `check_row` raises `ContractViolation` only | dead code | no (behaviour) / **YES** (the allowlist makes them permanent) |
| **B21-3** | the census is blind to a weakened condition; B18-8's pins downgrade with `134 passed` and no census row moves | **instrument completeness** | **YES** |
| **B21-4** | the ordinal id re-points on insertion; the drift report is 1 true / 1 misattributed / 1 false, and its remediation deletes a real record | **instrument correctness** | **YES** |
| **B21-5** | extracting raises into a helper collapses 7 rows into 1 | instrument | **YES** |
| **B21-6** | an interrupted census leaves a production module neutered and the suite red blaming a test | harness / tree | **YES** — I did it |
| **B21-7** | the byte-restore guarantee is an `assert`, removed by `-O` | harness | **YES** |
| **B21-8** | `generate()` — *the only writer* — emits **CRLF on Windows**. One call rewrote `contracts/agent-runtime-manifest.json` line-for-line with identical content (verified: `[]\r\n}\r\n` vs `[]\n}\n`); the M1 drift gate is a byte-equality check | **behaviour of the only writer** | **YES** — no adversary, no import needed; found by accident and restored from the committed blob |
| **B21-9** | **T10** and **route 25** were dropped from `Open, carried` with no closure in any R19/R20 verdict — B20-4's four is really six | process | **YES** |
| B20-1 | `dict(r)` shallow at 4/4 doors; the source's `members` list is returned and shared across doors | correctness | guard-only → **prod at CP-2** |
| B18-9 | 5/5 malformed documents accepted at three doors | structural | guard-only → **prod at CP-2** |
| B18-8 | two of three exact-type pins downgrade silently | adversarial | no |
| B18-10 | a fifth exported door, suite **and** gate green — **7th round** | structural | no |
| B18-11 | `canon` dead: 2 dead imports, 0 uses, refuted docstring verbatim — **4th round** | dead code / doc | no |
| B19-4 | `surface.py:305` — a 2-element **list** becomes an ordering key | guard-only | no |
| B19-12 | `_ID` unbounded; 300 chars written end-to-end | adversarial | no |
| B20-4 | the register drops open findings | process | **YES** |

**Introduced this round: 9** (B21-1 … B21-9). **Carried, re-measured open: 8.**

## ▶ The claim I am not allowed to settle

R20-A's finding — that if the design's premise *"each request runs in its own task and therefore its
own context copy"* holds, five rounds of ordering argument concerned **unreachable states**, and if it
fails the delta makes the system worse — **is not answerable from source, and I did not try.**

**What would answer it:** an execution, in a running `chat-service` process, that instruments
`contextvars.copy_context()` identity per in-flight request and records whether two concurrent
requests ever observe the same `Context` object — under the real ASGI server, with the real
concurrency settings, including the paths that do *not* originate from an HTTP handler (background
tasks, the outbox relay, any `asyncio.create_task` that inherits rather than copies). That is a
**V-LIVE** measurement, and this run's own record says both CP-1 V-LIVE rounds returned
`CANNOT DETERMINE` because `agentruntime` has **zero importers** — a fact I re-verified
(`grep -rn agentruntime --include=*.py` outside the package returns only a DB `CHECK` constraint, a
string constant in `instrument.py`, two test fixtures, and the two scripts).

**Who owns it:** the **PO**, and it is prior to the closure-criterion decision, not downstream of it.
Neither verifier can settle it and the builder must not, because the builder wrote the premise. If it
holds, the correct action on five rounds of ordering work is to **record them as concerning
unreachable states and stop**; if it fails, the delta needs re-grading against a hazard nobody has
measured. **Deciding the census question first spends the round on the instrument while the question
that determines whether the instrument has a subject stays open.**

## Executed vs argued

| | count |
|---|---|
| **executed** — code I ran and read the output of | **18** |
| **argued** — reasoned, not run | **3** |

Executed: the full census verbatim (68 sites, ~5 min) · an independent AST re-derivation of all 68
ids · a byte-comparison of 8 files against a pre-run snapshot · **13 semantic probes over the
enumerated allowlist, control + neutered** · 2 corrected probes · `dict(r)` aliasing at 4 doors +
cross-door sharing + post-validation mutation · `_ID` at 300 chars end-to-end · the `canon` AST
sweep · 4 B18-8 injections (3 + a control) · the fifth-door injection against suite **and** gate ·
the ordinal-insertion scoped census (8 sites) · the broken-module case · the kill-at-45s case · the
helper-extraction and `assert`-form AST measurements · `python -O` · B18-9 at 5 shapes × 4 doors ·
the membrane-gate selftest · the CRLF write by `generate()`.

Argued, and labelled as such: the deep-copy-vs-freeze recommendation (a design judgement); the CI
job's behaviour inside GitHub Actions (I read the trigger and confirmed no `paths:` filter, but ran
no workflow); D5's latent shapes (`sys.exit`, a raising helper in a comprehension), which the package
does not contain today.

**Not one of my findings rests on an argument.** And per the standing rule, every execution above is
over an **enumerated** space — all 13 allowlist rows, all 68 sites, all 5 key-pair vehicles, all 5
document shapes × all 4 doors, all 3 exact-type pins — not a chosen sample.

## Convergence

| | value |
|---|---|
| findings **introduced** by me, round 21 | **9** |
| B-scope `introduced` series, r10→r21 | `2, 1, 2, 1, 3, 2, 4, 3, 2, 2, 2, 5, 9` ⚠️ *(the series is **B-scope only** — B20-5's correction still stands, and RUNSTATE `:1919` still publishes it as the run's)* |
| carried findings re-measured **open** | 8 |
| carried findings **closed** by this delta | **0** |
| my denominator, instrument claims | 8 · red-able 1 cleanly, 3 weakly |
| my denominator, my findings | 11 · red-able **0** |

**The series went up again, and on the round whose delta was 213 lines of instrument.** I want to be
precise about what that does and does not mean, because a number that only rises invites being
explained away: **7 of my 9 are findings *about the census itself*.** A new artifact attracts
findings the way a new module does. The honest reading is not *"quality fell"* — it is that
**mechanising the criterion moved the argument into the mechanism, and the mechanism has the same
defect the code has: it is right about the case it was written for and silent about its siblings.**

## ▶ My new falsifiable prediction

> **If the census is adopted as CP-1's closure criterion unchanged, the first finding closed against
> it will be closed by a test that changes no runtime behaviour.** Concretely: the next delta will
> remove **`canon.py::_norm::NotCanonicalisable::1`** and/or **`contract.py::check_row_shape::ContractViolation::2`**
> from `contracts/agentruntime-census-silent.txt` by adding an assertion on the *message text* of a
> site whose semantic is already refused by its sibling — and the allowlist will shrink while nothing
> that was accepted before is refused after.

**Falsifier (both halves must hold to refute me):** the next delta's allowlist shrinks **only** at
rows I measured `ACCEPTED` — `canon::_norm::NotCanonicalisable::4`, `check_contract::CV::7`,
`generate::UntrustedRow::2`, `validate_document::UntrustedRow::5`,
`OrderBy.__post_init__::ValueError::3` (with a **list** pair, not a 3-tuple) and
`TakeWhileBudget.__post_init__::ValueError::1` — **and** the two dead handlers (`manifest.py:244-246`,
`:427-428`) are **deleted**, not tested.

Secondary prediction, offered because it is cheap to check: **if `dict(r)` is fixed, it will be fixed
at one of `surface.py:72` and `manifest.py:448` and not both.** That would be the eighth instance.

---

`git rev-parse HEAD` at finish: **`9818c7bc57c8381a4dddbbfcc88cbaadc5e89f06`** — unmoved.
`git status --porcelain`: **empty**, and all 8 package files byte-identical to my pre-run snapshot.
The only tracked file this verdict wrote is itself. Nothing was committed.
