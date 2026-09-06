# CP-1 · V-CODE — verdict, round 5 (the round-4 delta only)

**Artifact:** `77575da39d43ddf53f71a6791e149eada61343f0`. `git rev-parse HEAD` verified before the audit
and again immediately before this verdict — **HEAD did not move**. `git status --porcelain` over
`app/agentruntime/`, `tests/test_cp1_membrane.py` and `scripts/agentruntime-membrane-gate.py` is
**empty**. **No tracked file was edited.**

**Scope.** Exactly `git diff c57626938..HEAD -- services/chat-service/`: `surface.py` (+30/−12, the
post-condition rewritten and two docstrings), `narrowing.py` (+13/−4, module docstring),
`test_cp1_membrane.py` (+52, three new tests). Round 4's PASS on 1.7 rested on code this delta
changed, so it is re-earned here rather than carried. 1.1/1.2/1.3/1.5/1.6 are not re-graded; **1.4's
P4 half is out of scope** (escalated to the PO).

**Method.** Execution, not reading. Sandbox at
`scratchpad/sb/` — the package, the gate, the manifest and the test file copied out of the tree into
a mirror of the repo shape so `_REPO` resolves. Sandbox baseline is **2 failures / 64 passed** (both
path-dependent: `test_the_gate_actually_RUNS_in_ci`, `test_REAL_legacy_declarations_…`); every
mutation below is reported as *new* failures against that baseline. Caller-side probes ran against
the **real, unmodified** package on `sys.path`. The real suite at HEAD: **66 passed**. The gate:
exit 0. `--selftest`: exit 0. Thirteen source mutations, four gate-spelling probes, six caller
probes.

---

## 1 · Verdict

| question | verdict |
|---|---|
| **1 · does 1.7 still hold at HEAD?** | **PASS** — re-earned on the rewritten code, not carried |
| **2 · is F3 actually fixed?** | **YES**, all three compositions; and the inverse hole does **not** exist |
| **3 · are the two new tests red-able?** | **YES, both.** Plus a third that guards the F3 fix and is a behaviour gate, not a shape gate |
| **4 · does `Surface.withheld` still mean what consumers need?** | **Nothing breaks today** (no consumer exists) — but the contract **narrowed silently**, and two docstrings now describe a `withheld` the code no longer produces. **New finding.** |
| **5 · prose** | **PARTIAL.** Both changed files are now accurate about themselves — and the **third copy of the retracted claim is still standing**, and the correcting paragraph **introduces a new over-claim of the same shape** |

**Overall for the delta: it does what it claims.** F3 and F4 from round 4 are genuinely closed, at the
mechanism, with committed proof. The delta's cost is a quiet change to what `Surface.withheld`
contains, and one more round of an erratum applied in two files out of three.

---

## 2 · The falsifier — what would have made me say FAIL

Each was tested by execution:

1. **A silent narrowing on a shipped path at HEAD.** I enumerated every removal shape in the package
   (`grep -nE "\.pop\(|\bcontinue\b|filter\(|\[[0-9]*:|for .* in .* if |\.remove\(|del " *.py`) and
   got four hits: `manifest.py:125` (a duplicate *detector*, removes nothing), `narrowing.py:77`
   (`for_pass`, filters *records*), `surface.py:140` (`mine`, filters *records*). The only two sites
   that remove a **declaration** are `_narrow` (`surface.py:182-190`) and `discover`
   (`surface.py:222-231`), and both write the record inside the same loop. **None found.**
2. **The rewritten post-condition failing to fire.** It fires — see §3.1, five mutations.
3. **The F3 fix trading a false positive for a false negative** — i.e. "count only my own
   contribution" letting a real drop through on a shared log. It does not: §3.2, executed.
4. **A new gate that is green when its mechanism is removed** (round 4's F4). Both new gates red:
   §3.3.

What I did not find, and would have needed to: a declaration removed by the code as committed with no
`{tool, stage, reason, pass}` record.

---

## 3 · Question by question

### 3.1 · Does 1.7 still hold at HEAD? — **Yes**

The post-condition was rewritten (`surface.py:136-167`): `withheld` is now
`self._log.entries[_log_mark:]` filtered to this pass, not `self._log.for_pass(pass_number)`. Five
mutations against the sandbox, plus one executed at runtime:

| # | mutation | suite | runtime |
|---|---|---|---|
| **M4** | round-3's killer — `if not rules: kept = kept[:1]` | **RED** (2 tests: `test_assembling_with_NO_RULES_offers_everything_admitted`, `test_a_log_SHARED_WITHIN_ONE_PASS_…`) | raises |
| **M5** | **a branch no test drives** — `if len(rules) >= 2: kept = kept[:1]` | **green — invisible to CI** | **`AssertionError: narrowing lost 2 declaration(s) with no {tool, stage, reason, pass} record: 3 admitted, 1 offered, 0 registered at pass 1`** |
| **M7** | `_narrow` drops without recording | **RED** (6 tests) | raises |
| **M1** | `if False and len(kept)+len(withheld) != …` | **RED** | — |
| **M2** | law body deleted (`if False:`) | **RED** | — |

**M5 is the answer to the question as asked.** A drop on a branch the suite never executes is
invisible to CI and a **loud crash the first time the branch runs**. That is the same structural
property round 4 granted the PASS for, and the rewrite preserves it.

The three residuals the new comment (`surface.py:153-160`) *admits* are all real — I executed both:

- **baseline is `self._rows`**: `a = SurfaceAssembler(doc); a._rows.pop(); a.assemble(pass_number=1)`
  → `names=('book_get','book_list')`, `withheld=()`, **no error**. Confirmed.
- **cardinality, not identity**: a `_narrow` that drops 2 rows and writes 2 `__ghost__` records →
  law silent, surface `withheld` names declarations that were never admitted. Confirmed.

Those disclaimers are accurate, which is a change from every prior round. They are residuals, not
defeats: neither is what the committed code does.

### 3.2 · Is F3 actually fixed? — **Yes, and the inverse failure does not exist**

All three compositions round 4 crashed, executed against the **real** package
(`scratchpad/probe_f3.py`):

| composition | round 4 | HEAD |
|---|---|---|
| `discover(doc, kind="skill", log=log, pass_number=1)` then `SurfaceAssembler(doc, log=log).assemble(pass_number=1)` | `AssertionError: narrowing lost -3` | **OK** — `names=('book_get','book_list','world_setup')`, `withheld=()`, `len(log)==2` |
| two assemblers sharing one log **within pass 1** | `AssertionError: narrowing lost -2` | **OK** — `s1` 2 names/1 record, `s2` 2 names/0 records, `len(log)==1` |
| the same pass assembled twice on one assembler (a retry) | `AssertionError: narrowing lost -1` | **OK** — both surfaces identical, `len(log)==2` |

**The opposite failure — does counting "only my own contribution" let a genuine silent drop
through?** No. Executed: pre-populate a shared log with 2 discovery records at pass 1, then drive a
silent drop through the real `assemble` on that same log and pass →

```
AssertionError: narrowing lost 1 declaration(s) with no {tool, stage, reason, pass} record:
3 admitted, 2 offered, 0 registered at pass 1.
```

The arithmetic reason it cannot regress: `mine ⊆ for_pass(pass_number)`, so
`len(kept) + len(mine) ≤ len(kept) + len(for_pass(...))`. Reducing the `registered` term can only
turn an equality into an inequality — the law becomes **more** likely to fire on a shortfall, never
less. The only way to balance a real drop is to fabricate same-pass records *inside this assembly*,
which is E3 above and is unchanged by the delta.

One new fragility, latent and loud: `_log_mark` makes the law **reentrancy-sensitive**. A nested
`assemble` on the same assembler (e.g. from inside a rule predicate) would land its records after the
outer mark and inflate the outer `mine`, raising a negative-loss error again. No shipped code does
this; I record it because it is the same shape F3 had.

### 3.3 · Are the two new tests red-able? — **Both, and the third is stronger than it looks**

| gate | mutation | result |
|---|---|---|
| `test_the_POST_CONDITION_itself_fires` (`tests:461-481`) | **M1** disable the law · **M2** delete the law | **RED both times**, and it is the *only* new failure — so it is the gate, not a side effect |
| `test_the_EXPORTED_row_reader_refuses_a_malformed_document` (`tests:118-128`) | **M3** revert `declarations()` to `.get("declarations", [])` | **RED**, sole new failure |
| `test_a_log_SHARED_WITHIN_ONE_PASS_does_not_break_the_law` (`tests:483-499`) | **M6** revert `mine` to `for_pass(pass_number)` · **M8** freeze `_log_mark = 0` · **M13** revert **and** weaken the law to one-directional | **RED all three** |

Both gates named in the task fire. `test_the_POST_CONDITION_itself_fires` executes the real
`assemble()` and the real law (it monkeypatches `_narrow` to drop-without-recording, restoring in
`finally`) — a behaviour gate, not a substring assertion.

**M13 is the interesting one.** The obvious wrong fix for a future false positive is to make the law
one-directional; combined with reverting `mine`, that would restore the F3 bug while still never
raising on the honest caller. It **reds anyway**, because the test asserts `s.withheld == ()` — the
*contents* — not merely the absence of an exception. That is the difference between this round's
tests and the four rounds of gates that preceded them.

**Two residual holes in the gates**, both executed:

- **M9** — the law weakened to `< len(self._rows)` (dropping the over-registration direction, which
  is *exactly* the direction F3 lived in): **whole suite green**. Nothing guards the `>` half.
- **M10** — the `if e.pass_number == pass_number` filter inside `mine` deleted: **whole suite green**.
  It is a **no-op today**: `_narrow` always stamps the `pass_number` it was handed, so no entry
  appended after `_log_mark` can carry a different one. **NV: the subject never occurs — unarmed.**

### 3.4 · Does `Surface.withheld` still mean what its consumers need?

**Who reads it.** Repo-wide, `*.py`/`*.go`/`*.ts`/`*.sh`/`*.yml`/`*.sql`, excluding `node_modules` and
`__pycache__`: **nothing outside `app/agentruntime/` constructs a `SurfaceAssembler` or reads
`Surface.withheld`.** The `.withheld` hits in `services/chat-service/app/services/stream_service.py`
(`:6902`, `:7058`, `:7350`, `:7518`, `:7559`) are CP-0's `_advertised.withheld_json()` — a different
object on the legacy surface. The only readers are four assertions in `test_cp1_membrane.py`
(`:438`, `:498`, `:513`, `:602`). **So the change breaks nothing today. It is latent, and CP-2 is
where it lands.**

**But the contract changed, and no docstring says so.** Executed on the delta's own blessed
composition:

```
log.records()    -> [{"tool":"book_get","stage":"discovery_kind_filter",...,"pass":1},
                     {"tool":"book_list","stage":"discovery_kind_filter",...,"pass":1}]
surface.names    -> ('book_get', 'book_list', 'world_setup')
surface.withheld -> ()
```

Two consequences, both from execution:

1. **A consumer that persists `surface.withheld` loses 2 of 2 narrowings.** `Surface`'s class
   docstring — **not touched by this delta** — still says (`surface.py:75-77`): *"Carries the withheld
   set **alongside** the offered one, not in a log: a narrowing recorded somewhere the caller must go
   and find is a narrowing that gets dropped at the first persistence boundary, which is how the
   legacy column came to be empty for the one stage it was built for."* After the change, a narrowing
   performed by `discover` at that pass is **precisely** "recorded somewhere the caller must go and
   find". The sentence describes the guarantee the delta removed, and it is the sentence a CP-2 author
   will read.
2. **The blessed state is a `{withheld at pass 1} ∩ {advertised at pass 1}` contradiction.**
   `book_get` and `book_list` are recorded withheld at pass 1 *and* advertised at pass 1.
   `narrowing.py:38-42` says `pass_number` exists because *"a verifier found 19 of 303 withheld
   declarations **simultaneously advertised on every pass** and could not tell a contradiction from a
   sequence"*. The new regression test (`tests:496-499`) asserts that exact state is correct. The
   composition may well be legitimate — but nothing in the module reconciles the two records, and the
   field added to make this detectable is now stepped over by the test that blesses it.

**Docstring accuracy for `withheld` specifically: NO.** The new meaning ("only what this assembly
registered") appears **only** in an implementation comment about the conservation law
(`surface.py:128-135`). `Surface.withheld` has no field documentation; `Surface`'s class docstring
now over-claims; `assemble`'s rewritten docstring does not mention it.

**Also:** `NarrowingLog.for_pass` (`narrowing.py:76-77`) is now **dead production code** — repo-wide,
its only remaining reference is the comment at `surface.py:130` describing the bug it caused.

### 3.5 · Prose

**What the delta got right.** Every over-claim round 4 named *inside `surface.py`* is retracted, and
the replacements are true (verified by execution, §3.1):

| round-4 F7 item | HEAD |
|---|---|
| `surface.py:116` *"The only place a declaration can be removed"* | **corrected** — *"the only place THIS CLASS removes a declaration… It is not the only removal site in the module — `discover(kind=…)` is another"* |
| `surface.py:120` *"there is no second place that drops at all"* | **removed** |
| `surface.py:140-142` *"whatever future code removes a row… arrives here with the arithmetic broken"* | **removed**, replaced by three residuals I executed and confirmed accurate |
| `narrowing.py:14` *"no second path, and `Surface` cannot be built from a name list"* | **corrected**, with the erratum kept visible |

**The uncorrected copy the task asked about — found.**
`scripts/agentruntime-membrane-gate.py:136`:

```
#   Surface  - CP-1.7 / P1. `assemble()` is the only place a declaration can be
#     dropped, and it writes the record in the same statement.
```

This is the **third copy**, named as such in round 4's F7, and it is untouched (`git log -1` on that
file: `4642b609b`, prior to the delta). Both changed files now explicitly retract this sentence;
the file that *enforces* the property still asserts it. `narrowing.py:20-22` names this exact failure
mode — *"this copy was left standing through four verification rounds, which is the same
erratum-not-applied-everywhere failure that this run has now made in three separate documents"* —
in a paragraph that then leaves the third instance standing.

**A new over-claim, of the same shape, introduced by the correcting paragraph.**
`narrowing.py:23`: *"the gate keeps `Surface` single-sited so a second construction reds CI."* Stated
without qualification, as the corrected truth. `surface.py:72-73` makes the same claim. Executed
against the real gate, four spellings of a second construction site:

| second `Surface(...)` construction | gate |
|---|---|
| plain `Surface(...)` inside the package | **exit 1 — violation** ✅ |
| attribute call `_m.Surface(...)` inside the package | **exit 0 — passes** ❌ |
| alias `_S = Surface; _S(...)` inside the package | **exit 0 — passes** ❌ |
| `Surface(...)` in a module **outside** `app/agentruntime/` | **exit 0 — never scanned** ❌ |

Cause unchanged from round 4's F5: `_construction_sites` (`gate:143-150`) matches
`getattr(node.func, "id", None)` over `PACKAGE.rglob("*.py")` only. Three of the four constructions
the new sentence says "reds CI" do not.

The pattern the last four rounds recorded holds for a fifth: **the mechanism moved one layer
stronger, and the sentence above it is still one layer wider than the mechanism** — this time in the
paragraph written to fix that exact habit.

---

## 4 · Findings

### R5-F1 · `Surface.withheld` narrowed its contract; the docstring that defines its purpose was not updated
`services/chat-service/app/agentruntime/surface.py:140` (the change), `:75-77` (the stale claim)

`withheld` now reports only what this assembly registered. A narrowing performed by `discover` at the
same pass lives only in the log, which is the exact failure mode `Surface`'s docstring says the field
exists to prevent. Executed: 2 narrowings in the log, `surface.withheld == ()`. **No consumer today**
(grep: nothing outside the package reads it), so this is latent — and CP-2, where one turn discovers
by kind and then assembles, is where it lands. In the safe direction for P1 (the record is not lost,
only relocated), wrong for the field's documented purpose.

### R5-F2 · The blessed regression test asserts a withheld/advertised contradiction at one pass
`services/chat-service/tests/test_cp1_membrane.py:496-499`; field rationale at `narrowing.py:38-42`

`book_get` and `book_list` are recorded withheld at pass 1 and appear in `surface.names` at pass 1.
`pass_number` was introduced because a verifier could not tell that contradiction from a sequence.
Nothing in the module reconciles the two records, and the test states the state is correct.

### R5-F3 · The third copy of the retracted "only place a declaration can be dropped" is still standing
`scripts/agentruntime-membrane-gate.py:136`

Named in round 4's F7. Untouched by the delta. Now contradicted by both files it was copied from.

### R5-F4 · The paragraph correcting an over-claim states a new unqualified one
`services/chat-service/app/agentruntime/narrowing.py:23`, repeated at `surface.py:72-73`

*"the gate keeps `Surface` single-sited so a second construction reds CI."* Executed: an attribute
call, an alias, and any site outside `app/agentruntime/` all pass the gate. Root cause
`scripts/agentruntime-membrane-gate.py:143-150` (round 4's F5, unchanged).

### R5-F5 · The conservation law's over-registration half is unguarded
`services/chat-service/app/agentruntime/surface.py:161`

**M9**: weakening `!=` to `<` leaves the whole suite green. That is the direction F3 lived in, and it
is also the direction that bounds the fabricated-record evasion (drop 2, fabricate 3 → `!=` fires,
`<` does not).

### R5-F6 · The `pass_number` filter inside `mine` has no subject — NV, unarmed
`services/chat-service/app/agentruntime/surface.py:140`

**M10**: deleting the filter is invisible to the suite, because `_narrow` always stamps the
`pass_number` it was handed, so no entry appended after `_log_mark` can carry a different one. Correct
and defensive; currently a no-op with no realistic input that makes it matter.

### R5-F7 · `NarrowingLog.for_pass` is now dead production code
`services/chat-service/app/agentruntime/narrowing.py:76-77`

Repo-wide, its only surviving reference is the comment at `surface.py:130` that describes the bug it
caused.

### Carried forward, unchanged by this delta (out of scope, re-confirmed by execution)
- **round-4 F1** — the law's baseline is `self._rows`; `a._rows.pop()` narrows silently. Confirmed.
- **round-4 F2** — cardinality not identity; two `__ghost__` records balance a 2-row drop. Confirmed.
- **round-4 F5** — the single-site gate's blind spots. Confirmed, four spellings.
- **round-4 F6** — **M12**: `rows = [r for r in rows_of(manifest_doc) if "kind" in r]` inside
  `discover` is **invisible to the whole suite** (every fixture row carries a `kind`). Still open.
  Note **M11** (deleting `discover`'s `log.record`) *does* red 3 tests, so the recording is guarded —
  it is the *pre-filter* that is not.

---

## 5 · Vacuity (NV) — this delta

| # | check | armed? |
|---|---|---|
| NV-1 | the rewritten post-condition (`surface.py:161`) | **YES.** Fired under M4, M5, M7 and on the probe of §3.2. Subject occurs at n≥2 with any unrecorded drop after `self._rows` |
| NV-2 | `test_the_POST_CONDITION_itself_fires` (`tests:461`) | **YES.** Reds under M1 and M2, and is the sole new failure in both. Round 4's F4 is closed |
| NV-3 | `test_the_EXPORTED_row_reader_refuses_a_malformed_document` (`tests:118`) | **YES.** Reds under M3, sole new failure |
| NV-4 | `test_a_log_SHARED_WITHIN_ONE_PASS_does_not_break_the_law` (`tests:483`) | **YES, and strongly.** Reds under M6, M8 *and* M13 (the plausible wrong fix), because it asserts `withheld`'s contents |
| NV-5 | the `pass_number` filter in `mine` (`surface.py:140`) | **NO — no subject.** M10 invisible; `_narrow` cannot produce a differing pass. Unarmed by construction |
| NV-6 | the law's `>` direction (`surface.py:161`) | **UNGUARDED.** M9 invisible to the suite. Armed in the code, unwitnessed in the tree |
| NV-7 | `Surface` single-site gate (`gate:140`) | **PARTIAL, unchanged.** Fires on the plain in-package spelling; blind to attribute, alias, and everything outside `PACKAGE` |

---

## 6 · The bypass table — the delta

| the path | status |
|---|---|
| a silent narrowing **in the code as committed** | **none found.** Method: enumerated every removal shape in all six modules by regex, read both declaration-removal sites, executed every public entry point, ran 13 source mutations and 6 caller probes |
| a drop on any branch of `assemble`, covered or not | **closed in production.** M5 proves an uncovered branch is invisible to CI and raises at runtime |
| F3 — a log shared within one pass | **closed.** Three compositions execute clean; guarded by a test that reds under three separate reverts |
| "count only my own contribution" hiding a real drop on a shared log | **not reachable.** `mine ⊆ for_pass`, so the sum can only shrink; executed, still raises |
| narrowing at construction / by mutating `_rows` | **open** — round-4 F1, re-executed. Now *disclosed* in the code comment |
| a drop with fabricated balancing records | **open** — round-4 F2, re-executed. Now *disclosed* |
| narrowing outside `assemble` (`discover`, a new method, a bare `Surface(...)`) | **open** — the gate is the only backstop and misses 3 of 4 spellings (R5-F4) |
| `discover` dropping on a field every fixture carries | **open** — round-4 F6, M12, suite green |
| a narrowing that reaches the log but not the surface | **NEW, R5-F1** — `discover`'s narrowings at the assembled pass no longer appear in `Surface.withheld` |

---

## 7 · Summary for the record

**1.7 holds at HEAD, on the rewritten code.** The post-condition was changed in the one place the
earlier PASS depended on, and it still fires — including on a branch no test drives, where it
converts a CI blind spot into a runtime crash rather than a smaller surface. F3 is fixed for all
three compositions round 4 named, and the fix does not open the inverse hole: a genuine silent drop on
a shared log still raises, and the arithmetic makes that structural rather than lucky. Both gates
round 4 asked for exist, and both go red when their mechanism is removed — the first round in five in
which every fix ships with committed proof it can fail.

Three things should not be lost in that. The fix quietly changed **what `Surface.withheld` contains**,
and the docstring that defines the field's purpose still describes the guarantee that was removed —
harmless today because nothing reads it, and pointed straight at CP-2. The **third copy** of the
sentence both changed files now retract is still in the gate that enforces the property. And the
paragraph written to correct an over-claim **states a new one**: three of four ways to build a second
`Surface` do not red CI, and the sentence says they do.
