# CP-1 · round 24 · V-CODE **B — the membrane**

`git rev-parse HEAD` **at start**: `b5d81e54ad6fed9134758b02e8d4bb66e1691a25`
`git rev-parse HEAD` **at finish**: `b5d81e54ad6fed9134758b02e8d4bb66e1691a25` — **unmoved**, checked
four times across the round. Nothing committed. One tracked file written: this verdict.

**Verdict: FAIL.** Not on a judgement call. The graded delta `714d8b7c8` **destroys the census**, and
I measured it end to end before I read a line of anyone's argument.

---

## 0 · B24-0 — 🔴 **THE CENSUS MEASURES NOTHING AT THE FROZEN ARTIFACT, AND CI IS RED**

I ran the instrument first, on the theory that a gate should be executed before it is discussed. Ten
minutes, from the repo root, at `b5d81e54a`, unmodified tree:

```
$ python scripts/agentruntime-census.py -v
agentruntime-census selftest OK - 68 raise sites, fires on a guarded one
  RED    admission.py::Admitted.__init__::TypeError::1::0fb853fb
  ... 68 of these, every one RED ...
NOW GUARDED   canon.py::_norm::NotCanonicalisable::1::50f6dc36  <- good news: drop it from the allowlist
... thirteen NOW GUARDED lines, one per allowlist row ...
agentruntime-census: 68 sites, 0 silent, 68 red
RC=1
```

**0 silent. 68 red. rc=1. Thirteen `NOW GUARDED … good news` lines.** The CI job runs
`python scripts/agentruntime-census.py` with no flags, so **the `agentruntime-census` job fails on
every run at this artifact**, and the only remedy it prints is *delete all thirteen allowlist rows*.

Its own docstring names this outcome, one paragraph long, about the previous defect:

> The gate then printed thirteen `NEWLY SILENT` and thirteen `NOW GUARDED` lines and instructed the
> maintainer, thirteen times, to delete the allowlist. **That is worse than the failure it replaced**,
> because the previous one was obviously broken and this one is plausible.

It has happened again, in the delta that was graded for fixing it, for a different reason.

### The mechanism, isolated by execution

`census()` builds a mirror with `_mirror()`, which shells out to `git ls-files` with `cwd=ROOT`. The
graded delta's new test **drives `census()` from inside the suite**. So when the census runs the suite
*inside its own mirror*, that test loads the **mirror's** census script, whose `ROOT` is the mirror
root — **which has no `.git`** — and dies:

```
E  subprocess.CalledProcessError: Command '['git', 'ls-files', '-z']' returned non-zero exit status 128
scripts/agentruntime-census.py:87 (via _mirror)
FAILED tests/test_cp1_membrane.py::TestStageKindsAreDataNotClosures::
       test_THE_CENSUS_DOES_NOT_WRITE_INTO_THE_LIVE_TREE
1 failed, 136 passed
```

Executed, three ways, and the third is the falsifier:

| experiment | result |
|---|---|
| build a mirror, run the suite in it **unneutered** | **1 failed**, 136 passed — `has .git in mirror? False` |
| same, with **only** the new guard test `--deselect`ed | **rc 0**, `136 passed, 1 deselected` |
| the live tree, same command | **137 passed** |

So the mirror suite is red **unconditionally, for every one of the 68 neuterings**, and `census()`
records `red = not green = True` for all 68. The instrument reports 68/68 RED without ever measuring
a single guard.

### The falsifier, executed: a 2-line skip restores it exactly

I patched **one** thing — the new test skips when `_REPO/.git` is absent, i.e. when it is looking at a
census mirror rather than the live tree — and re-ran the full census:

```
RC=0   RED=55   SILENT=13
agentruntime-census: 68 sites, 13 silent, 55 red
```

**13 silent, 55 red, rc=0, and the allowlist matches row for row.** The thirteen rows were never
wrong. The graded delta broke the instrument that validates them, and both verifiers of R23 —
including my predecessor, who reasoned about this file at length — graded it without running it.

Restore verified by sha256 (`2994774d8c70da6a…`), tree clean.

### 🔴 And the `--selftest` is theatre — it cannot tell "fired" from "cannot run"

`_selftest()` decides its positive control with `fired = not _suite_is_green(mirror / _CS_REL)`.
Since the mirror suite can never be green, `fired` is **always True**. Executed, patch-and-restore,
clean tree:

| census under test | `--selftest` says |
|---|---|
| baseline | `rc 0` · `selftest OK - 68 raise sites, fires on a guarded one` |
| **`_neutered` returns `src` unchanged** (removes nothing) | `rc 0` · **`fires on a guarded one`** |
| **the probe write deleted entirely** (nothing is ever neutered) | `rc 0` · **`fires on a guarded one`** |

The check written to prove the harness can fire, before the harness is trusted, **passes when the
harness does nothing at all**. This is the run's own named failure — *a check whose control and seed
agree is theatre* — now inside the control built to prevent it. `scripts/agentruntime-census.py:250`.

**Reachability: CI, today.** Not guard-only, not CP-2. The `agentruntime-census` job is red on `main`
at this commit and the printed remedy deletes the artifact the gate exists to protect.

---

## 1 · The executing guards — **nine bypasses, and one of them is the same fix landing beside its subject**

### 1a · Is the write-watch measuring the property, or the next proxy for it?

**The next proxy, and a narrower one than it reads.** The builder correctly identified that
before/after is satisfied by the restore, and moved to observing *during* the run. But the
observation is `mp.setattr(pathlib.Path, "write_bytes", _watch)` plus
`_live = [w for w in writes if _REPO in w.parents]`. That is not "the census does not write into the
live tree". It is:

> *the `census()` function, and only it, does not write into the live tree, through
> `pathlib.Path.write_bytes` specifically, using an absolute path specifically.*

Four qualifiers, three of them unstated. Enumerated as a grid — **{writer function} × {write API}**,
every cell writing neutered production source into the **live** package and restoring afterwards,
which is precisely the shape the guard claims to forbid:

| writer | `write_bytes` | `open(...,"wb")` | `shutil.copyfile` | `os.replace` |
|---|---|---|---|---|
| **`census()`** | ✅ **RED (caught)** | 🔴 GREEN | 🔴 GREEN | 🔴 GREEN |
| **`_selftest()`** | 🔴 **GREEN** | 🔴 GREEN | 🔴 GREEN | 🔴 GREEN |

**1 of 8 cells caught.** Every cell executed; census script restored and sha-verified after each
(`be544d37c29e76ed…`, printed by the harness).


The census's own `_mirror()` already uses `shutil.copyfile`, and its own `--write` path already uses
`write_text` — so two of the un-watched APIs are not hypothetical, they are in this file.

### 1b · The bypass table

Every row EXECUTED: patch bytes from an in-process snapshot → run the named test → restore →
`assert sha256 == snapshot`. Never `git checkout`. Final shas verified for both files.

| # | bypass | target | test | verdict |
|---|---|---|---|---|
| **B24-1** | **`_selftest`'s probe moved back to the LIVE `contract.py`** — the test drives `census()` and never `main()`/`_selftest()`, so the second neutering writer is unwatched | census | write-watch | 🔴 **GREEN** |
| **B24-2** | live write via `open(path,"wb").write(...)` | census | write-watch | 🔴 **GREEN** |
| **B24-3** | live write via a **relative** path — `_REPO in w.parents` is `False` for a relative `Path`, and the restore satisfies before/after | census | write-watch | 🔴 **GREEN** |
| **B24-4** | live write via `shutil.copyfile` from a scratch file | census | write-watch | 🔴 **GREEN** |
| **B24-5** | `_neutered` returns `src` unchanged — the census measures nothing | census | write-watch | 🔴 **GREEN** |
| **B24-6** | **step-level** `if: false` on the `Refusal census` step — only the **job**-level `if` is checked | workflow | ci-yaml | 🔴 **GREEN** |
| **B24-7** | **job-level** `continue-on-error: true` — only **step**-level is checked | workflow | ci-yaml | 🔴 **GREEN** |
| **B24-8** | `run: python scripts/agentruntime-census.py; true` — `"\|\|" not in r` forbids exactly the one spelling it names | workflow | ci-yaml | 🔴 **GREEN** |
| **B24-9** | `on:` reduced to `workflow_dispatch:` — the job is wired, parsed, unconditional, and never runs on a PR | workflow | ci-yaml | 🔴 **GREEN** |
| CTRL-A | mirror removed entirely (`pkg = PKG`) | census | write-watch | ✅ red |
| CTRL-B | mirror placed **inside** the repo (`mkdtemp(dir=ROOT)`) | census | write-watch | ✅ red |

**Nine.** The prompt asked for the ninth; **B24-1** is the one that matters, because it is not a
clever spelling — it is *the identical defect, in the sibling function, twenty lines away*. The fix
moved `census()` to a mirror and left `_selftest()`'s neutering write beside it. `_selftest()` writes
`_neutered(...)` into a file and restores it in a `finally`; point that file at the live tree and the
graded guard is green. **That is the run's most-repeated failure — a fix landing on the sibling of
the site a verifier named — for the eighth time, and this time inside the instrument built to make
that structurally impossible.**

Two controls fired, so the instrument is not inert. It is scoped to one cell of an eight-cell space.

### 1c · The YAML parse is a real improvement, and it is still a substring check about structure

Parsing the workflow as YAML genuinely killed the comment-satisfies-the-assertion class — that is
worth saying, and it is the strongest thing in the delta. But the assertions written over the parsed
object reproduce the same shape one level up: `"if" not in job` checks one of the two places an `if`
can live; `s.get("continue-on-error")` checks one of the two places it can live; `"||" not in r`
names one of several ways a shell swallows an exit code; and nothing at all looks at `on:`. **A
workflow is structured data and is now read as structured data — but the properties asserted over it
are still a hand-picked list of spellings, which is the same defect in a better format.**

---

## 2 · The non-injective id — **an injective, prose-blind id IS achievable. "Choose" is refuted.**

The honest answer the prompt offered — *"a stable id and a prose-blind id are incompatible, choose"* —
**is not what the evidence says**, and I can show the discriminator.

### 2a · Grading the question, not defending the finding

My predecessor's numbers reproduce, with one correction of framing:

| measurement | value |
|---|---|
| sites | **68** |
| **distinct full ids** | **68** — the full id *is* injective as a label, because the ordinal is in it |
| distinct shape digests | **54** |
| digest collision groups anywhere in the package | 5, covering 19 sites |
| **groups where the ordinal is the ONLY discriminator** (`mod::qual::Exc::digest` repeats) | **4, covering 8 sites** |
| of those, containing an allowlisted row | **2** |

So "68 → 54 digests, 4 collision groups, 2 with an allowlist row" is **confirmed**. The precise claim
is not "two sites share an id" — it is **"for 8 of 68 sites the digest carries no information the
ordinal did not already carry"**, which returns those sites to the pre-digest state the digest was
added to fix. Executed: physically swapping the two guard blocks in each reorderable group and
re-enumerating gives an **identical id set, 3 of 3 groups** — `+0 / -0`.

### 2b · The severity is worse than "reorder", and it is exactly the R23 headline

The reorder is the small case. Here is the general one, executed **over the whole enumerated space**
rather than a sample. For each of the 68 sites, replace the nearest enclosing `if`/`while` test with
`False` — making the refusal **unreachable**, the strongest possible weakening — and ask whether the
census's id set moves:

```
sites total                                   : 68
sites sitting under an if/while               : 59
guard neutralised -> CURRENT id set UNCHANGED : 59/59  (100%)
   ...of which ALLOWLISTED (SILENT) rows      : 10/13
guard neutralised -> +enclosing-test UNCHANGED:  0/59
```

**The census's id covers the `raise` statement and not the condition that reaches it.** For a RED
site the suite catches this on its own — the census adds nothing there. For a SILENT site the suite
by definition does not, and the id does not move, so the allowlist still matches and **rc=0 over a
change that made ten of its thirteen refusals unreachable.**

That is R23's headline claim — *a gate for the 55 RED and not for the 13 SILENT* — **CONFIRMED, and
with a mechanism it did not have.** Not a scoping opinion; 59/59, enumerated.

### 2c · The discriminator, and the trade measured in both directions

Widen the digest's input from the `raise` statement to **the raise plus the string-blanked
`ast.unparse` of its nearest enclosing branch test.** A condition is *code*, not prose, so blanking
its string literals keeps the whole thing prose-blind. Executed over all 68 sites:

| candidate id | ordinal-only groups | allowlisted groups | reword **every** message → rows moved | guard→`False` → blind |
|---|---|---|---|---|
| **shipped** (shape only) | **4** (8 sites) | **2** | ✅ 0/68 | 🔴 **59/59** |
| + previous sibling statement | 4 (8 sites) | 0 | ✅ 0/68 | — |
| **+ enclosing test** | ✅ **0** | ✅ **0** | ✅ **0/68** | ✅ **0/59** |
| shape **with** prose | 0 | 0 | 🔴 **68/68** | — |

The four groups separate on conditions that are structurally distinct after blanking:

```
canon._norm            isinstance(value, float)      vs  isinstance(value, (set, frozenset))
check_contract         d.kind == '\0' and d.members  vs  d.kind in ('\0','\0') and not d.members
OrderBy.__post_init__  not self.keys                 vs  field == '\0' and i == 0
TakeWhileBudget        self.budget < 0               vs  not self.cost_field
```

**Answer: an injective id is achievable without prose-churn — 4 collision groups → 0, 0/68 rows moved
by a full reword sweep, and it closes the 59/59 guard blindness as a side effect. ~6 lines in
`_shape_digest`/`_sites`. The gate does not have to choose.**

⚠️ **Two honest caveats, because a fix asserted is not a fix.**
1. This is injective **on today's tree**, not provably injective. Two guards differing only in a
   string literal would blank to the same text. → **Therefore the real closure is not the
   discriminator, it is a post-condition:** the census should **assert** that `mod::qual::Exc::digest`
   is unique across the package and exit 1 naming the collision. ~4 lines, exact, and it converts a
   silent staleness into a build failure. *A repair layer needs a post-condition.*
2. Every row would be rewritten once. That is a reviewable one-off diff, and the allowlist header
   already says adding or removing a row is a decision.

### 2d · One risk I can retire, measured

The digest moved from `ast.dump` to `ast.unparse` because `ast.dump` was **0/68 stable across 3.12 and
3.13**. That the replacement is stable was **asserted in a docstring and never measured.** CI pins
3.12; this machine is 3.13. Executed:

```
3.13.12 vs 3.12.10  ->  68/68 ids IDENTICAL
13/13 allowlist rows exist under the CI-pinned 3.12
```

**The `ast.unparse` bet holds.** That is a genuine PASS, and the only unqualified one I found in the
delta's neighbourhood.

---

## 3 · `dict(r)` is shallow at 4/4 doors — and what the rewritten test must assert

Re-measured independently, fresh fixtures built from `contract.ROW_FIELDS` rather than from the
test's expectations (**5th round, unchanged**):

```
rows_of            members IS the source list: True   after source mutation: ['t0','GHOST_NEVER_ADMITTED']
validate_document  members IS the source list: True   after source mutation: ['t0','GHOST_NEVER_ADMITTED']
declarations       members IS the source list: True   after source mutation: ['t0','GHOST_NEVER_ADMITTED']
discover           members IS the source list: True   after source mutation: ['t0','GHOST_NEVER_ADMITTED']
cross-door: rows_of and declarations share ONE members list: True
```

**I endorse my predecessor's three clauses and add the reason the third is load-bearing, in the terms
this round is being graded on.** The existing test asserts `out == snap` *after* the call and nothing
between; that is a **before/after comparison**, and it is the identical error the builder just
diagnosed in his own first write-watch — *"the property is not «the tree ends unchanged», it is «the
tree is never written»"*. Here the property is not «the returned document equals the snapshot», it is
**«the returned document does not share mutable state with the caller's input»**, and only an
assertion that acts on the input *after* the call can tell those apart. The builder has already
written that sentence about his own instrument this round; it applies verbatim to `surface.py:72` and
`manifest.py:448`.

Required:

1. keep `good == snapshot` (the validator must not edit its input in place) — already correct;
2. **identity separation** — for every returned row, every `list`/`dict` field satisfies
   `v is not src[k]`, and the message names the field;
3. **post-call independence** — mutate the caller's input *after* the call, then
   `assert json.loads(json.dumps(out)) == snapshot`. The JSON round-trip, not `==`, so the clause is
   red under the defect and green under *either* remedy (deep copy **or** tuple rebuild) — otherwise
   the test pins the implementation and blocks the fix, which is what it does today.

`surface.py:72` and `manifest.py:448` are siblings. **Both, or neither.**
**Reachability: guard-only today (zero importers) → production-reachable at the commit CP-2.1 imports
the package.**

---

## 4 · The carried findings — re-measured, all open

### B18-8 — **7th round.** 1 of 3 exact-type pins is guarded, and the control proves it is a family

| injection (`contract.py`) | suite |
|---|---|
| `type(key) is not str` → `isinstance` (`:220`) | **137 passed** |
| `type(m) is not str or not m` → `isinstance` (`:254`) | **137 passed** |
| **both at once** | **137 passed** |
| *control:* the row pin `:217` → `isinstance` | ✅ **2 failed, 135 passed** |

The control fires, so the suite can see this class of downgrade; it sees exactly one of the three
places it occurs. **Reachability: guard-only → CP-2.1.**

### B18-10 — **10th round**

```
B18-10 fifth exported door serving an unvalidated row: ['TYPED BY HAND:1']
SUITE: 137 passed        GATE: rc 0, agentruntime-membrane-gate OK - 8 module(s), 0 allowed external import
```

An exported `summarise_rows` reading `r['id']`/`r['kind']` with no validator: suite green, gate
green, and it served a row whose `kind` is the integer `1`. **Nothing in the package or its gate
requires a row-reading function to validate.** The CP-2 scoping is still honest only because there
are zero importers; the first commit that imports `app.agentruntime` from `app/` makes every
guard-only finding in this run production-reachable retroactively.


### B18-11 — **7th round**

```
contract.py    canon imported at [21]   canon.<attr> uses: []
manifest.py    canon imported at [27]   canon.<attr> uses: []
'canon' in __all__: False
canon.py nfc() docstring still names manifest.load as a door: True
```

Two dead imports, zero attribute uses, not exported, and a docstring the code below it already
refuted. **Reachability: dead code + a false claim a reader will act on. Not a runtime defect.**

### `surface.py:305` — **6th round**, 5 vehicles, control vs neutered

| vehicle | control | `type(pair) is not tuple` removed |
|---|---|---|
| `(["cost2","asc"],)` | `ValueError: keys[0] is not a (field, direction) pair` | 🔴 **ACCEPTED** |
| `(("cost2","asc","x"),)` | refused | refused (same message) |
| `(("cost2",),)` | refused | refused (same message) |
| `(7,)` | refused | `TypeError: object of type 'int' has no len()` |
| `("ab",)` | refused | `ValueError: keys[0]: unknown direction 'b'` |

Load-bearing for **exactly one of five** vehicles. A closure written against a 3-tuple or a scalar
passes with the clause deleted. **Reachability: guard-only → CP-2.1.**

### `_ID` unbounded — **6th round**

```
contract._ID.match(300 chars): True
validate_document round-trip id length: 300
rows_of id length: 300      discover id length: 300
```

`_ID = re.compile(r"^[a-z][a-z0-9_]*$")` at `contract.py:31` has no length bound; a 300-character id
survives three exported doors intact. **Reachability: guard-only → CP-2.1; becomes a prompt-budget
issue the moment a declaration id reaches a model.**

---

## 5 · The record audit, and 🔴 **the verification method is now a source of contamination — measured, in my own run**

### 5a · The record

| claim | status |
|---|---|
| R23's `Open, carried` block exists | ✅ present (an improvement R21 lacked) |
| the six ≤15-line changes B listed toward an injective id | ✅ carried into the R24 prompt as item 2 |
| `ALLOWLIST.write_text` (`census.py:280`) — raised by **A22-9 and B22-7 independently** | 🔴 **still `write_text`, still absent from the register — 3rd round.** The file's own opening paragraph is about `write_text` rewriting LF as CRLF on Windows. The one call that still uses it is the one that writes the allowlist. |
| the M1 "byte-equality" claim in `ambient.py:76` + `test_cp1_membrane.py:2185`,`:2199` (B22-1) | 🔴 still present, still absent from the register — 3rd round |
| **W4** — written, executed and measured by a verifier, still not in the tree | 🔴 **8th round** (A's item; noted for the record) |
| the ~6.71 GB of unremoved mirrors | 🔴 **grown: 108 directories, 8.4 GB** in `%TEMP%`, measured this round. `_mirror()` has no cleanup, and the graded delta makes it **worse** — the new guard test creates a **237 MB** mirror on **every suite run**. ⚠️ *Honesty: my own ~20 runs contributed to that total. The rate is the finding, not the number — one 237 MB directory per suite run, never removed, is what makes the number whatever the round's activity was.* |

**A register that has lost rows in six consecutive rounds has lost rows in a seventh.** Both of the
absent rows were raised by *both* verifiers independently, which is the strongest signal this process
produces, and it is the signal being dropped.

### 5b · The contamination question — **yes, and I can date it**

The prompt says the live allowlist was observed rewritten by a concurrent process. **I reproduced the
hazard in my own session, three distinct ways, and one of them was mine.**

| # | observation | evidence |
|---|---|---|
| 1 | **another agent registered a git worktree inside the main repo's `.git`** | `git worktree list` → `…/scratchpad/wt-a  b5d81e54a (detached HEAD)`. I never created it. "Isolation by worktree" still writes to the **shared** `.git/worktrees/`. |
| 2 | **two of my scratchpad analysis scripts were overwritten mid-run by another process**, with content referencing *"the sweep is mutating wt-a"* | the tool reported both files "modified… by the user or a linter". My results survived only because they were already in my transcript. **That is luck, not method.** |
| 3 | **the scratchpad is not session-scoped in practice** | my `vb/` directory already contained `inject_b.py`, `p1_identity.py` … `p6_r9delta.py`, dated the previous day — a prior verifier's working set, under a path advertised as session-isolated. |
| 4 | **my own contamination**: a control injection (`mkdtemp(dir=ROOT)`) left a **237 MB** `lw-census-*/` inside the repo. The next suite run went **`1 failed`** — `test_the_package_imports_only_stdlib_and_itself` tripped over the copied package — and `--selftest` reported `the suite is not green`. I nearly recorded that as a finding. | removed; `git status` clean; live suite back to `137 passed`, verified |
| 5 | 🔴 **the BUILDER's uncommitted fix for B24-0 landed in the shared worktree while I was still measuring it.** Late in the round `scripts/agentruntime-census.py` was at `ed8d7294…` and `test_cp1_membrane.py` at `7216e455…` — **neither the artifact's sha nor mine.** `git diff` shows a `_suite_is_green` that refuses to classify on `pytest` exit 2–5, and a `pytest.skip` on a missing `.git`, with a comment describing my measurement verbatim | `git diff`, quoted below |

**Observation 5 is the serious one, and it is a different failure from 1–4.** `HEAD` never moved, so
the *artifact* stayed frozen — but **the working tree the verifiers actually execute did not.** A
frozen commit is not a frozen subject when the verification runs against the checkout.

The counterfactual is exact and it is not hypothetical: **had that fix landed twenty minutes
earlier, my census run would have printed `13 silent, 55 red, rc=0` and I would have reported the
census HEALTHY at `b5d81e54a`** — a false PASS on the largest finding of the round, produced by an
honest verifier running the right command, with no way to detect it short of hashing every file
first. That is the same class as `feedback_verify_deployed_image_matches_source`, arriving from
inside the loop rather than from a container registry.

My measurements are attributable because the sha manifest brackets them: the census run, the mirror
probes, the 11 bypass injections and the 8-cell grid all completed with
`scripts/agentruntime-census.py = be544d37…` (the artifact), printed by each harness at exit. Only
the last two probes (B18-8, B18-10) ran after the drift, and neither touches the drifted files.
**I did not restore the builder's files** — clobbering another writer's in-flight work is
`feedback_superseded_async_cleanup_clobbers_live`, and it is exactly what a diligent "restore my
snapshot" reflex would have done.

**So: yes, the method is a source of contamination, and it is currently strong enough to manufacture
a false finding.** Observation 4 is the dangerous one: the debris did not corrupt a measurement
subtly, it produced a *plausible red* in a different test, which a verifier under time pressure would
report as the builder's defect. That is the run's `feedback_host_env_drift_masquerades_as_code_bug`
lesson arriving from inside the verification harness.

The drifted diff, quoted so the record is unambiguous about what was in the tree and when:

```python
 def _suite_is_green(cwd=None) -> bool:
+    """Green / not-green — and **a crash is neither.** ..."""
     r = subprocess.run([...])
-    return r.returncode == 0
+    if r.returncode not in (0, 1):
+        raise SystemExit("pytest exited " + str(r.returncode) + " ... - it did not run the suite ...")
```
```python
+        if not (_REPO / ".git").exists():
+            pytest.skip("running inside a census mirror; the outer run is the measurement")
```

Both are correct fixes and I would sign off on their shape — the `returncode not in (0, 1)` guard is
*better* than my 2-line skip, because it makes the whole class of "the harness could not run"
un-classifiable rather than patching the one instance. That is not the point. **The point is that
they were in the tree, uncommitted, during a round whose premise is a frozen artifact.**

**What would fix it — four things, in order of cost:**

1. 🔴 **The census must clean up its mirror.** `_mirror()` returns a `mkdtemp` that nothing ever
   removes: 108 dirs / 8.4 GB today, and every guard-test run adds one. `try/finally shutil.rmtree`,
   or `TemporaryDirectory`. This is the largest single source of cross-run interference and it is
   **four lines**.
2. **Each verifier gets its own worktree AND its own scratchpad root, keyed by verifier id, not by
   session.** Observations 2 and 3 show the current key is reused. `wt-a` proves the worktree half is
   already understood; the scratchpad half is not.
3. **A verifier must open and close with a sha manifest of every file in scope, printed in the
   verdict**, so a contaminated measurement is detectable *in review* rather than only by the
   verifier who happened to notice. I did this (opening shas in §7); it cost one command and it is
   what let me attribute observation 4 to myself within one minute instead of filing it, and what
   let me date observation 5 to after the grid.
4. 🔴 **The builder must not edit the worktree the verifiers are executing.** A frozen commit is not
   a frozen subject. The cheapest honest form: verifiers run from a **detached checkout of the frozen
   sha**, and every harness prints the sha of each file it touched **immediately before and after**
   the measurement — so a verdict carries the evidence that its subject was the artifact. Without
   that, "graded against `b5d81e54a`" is an assertion about a commit id while the measurement was
   taken from a directory.

**What it does NOT justify:** a shared worktree did not cause B24-0. I measured the census red on an
untouched tree with all shas matching, before any injection, and the fix-and-recover run reproduces it
in the opposite direction. Contamination is a real hazard here and is **not** the explanation for the
central finding.

---

## 6 · Tables

### 6a · Red-ability, **with my own denominator**

My denominator is not "the assertions in the delta". It is **the enumerated space of the property
each test claims**.

| guard | property it claims | my denominator | caught | red-able |
|---|---|---|---|---|
| `test_THE_CENSUS_DOES_NOT_WRITE_INTO_THE_LIVE_TREE` | "the census never writes into the live tree" | {2 writer functions} × {4 write APIs} = **8 cells**, all executed | **1/8** | see §1a |
| …same, path spelling | absolute vs relative | 2 | 1 | 1/2 |
| …same, "the census measures something" | `_neutered` is a no-op | 1 | 0 | **0/1** |
| `test_THE_CENSUS_IS_WIRED_TO_RUN_IN_CI` | "the census runs, unconditionally, and can fail the build" | {job `if`, step `if`, job `continue-on-error`, step `continue-on-error`, `\|\|`, `;`, `--write`, `--selftest`, `on:`} = **9 levers** | **5** | **5/9** — ⚠️ *4 executed (the 4 bypasses B24-6…9); the 5 caught ones are read off the test's own assertions, not injected. Stated so the denominator is not inflated.* |
| `census --selftest` | "the harness can fire" | {`_neutered` no-op, probe write removed} = 2 | 0 | **0/2** |
| the census **as a gate** | "a named site moved SILENT→RED" | 68 sites | **0** — it reports 68/68 RED and rc=1 | **0/68** |
| the census id | "a guard weakening moves the row" | 59 guarded sites, all executed | 0 | **0/59** |

### 6b · Sibling table — *the run's most-repeated failure, again*

| the site that was fixed | its sibling | sibling fixed? |
|---|---|---|
| `census()` neuters in a mirror | **`_selftest()` neuters** — same file, `:248` | 🔴 **no — B24-1 is green** |
| `census()` writes bytes via `write_bytes` | `ALLOWLIST.write_text` `:280` — the LF/CRLF defect the file opens with | 🔴 **no — 3rd round** |
| the job-level `if` is forbidden | the **step**-level `if` | 🔴 no — B24-6 |
| step `continue-on-error` is forbidden | **job** `continue-on-error` | 🔴 no — B24-7 |
| `\|\|` is forbidden | `;`, `set +e` | 🔴 no — B24-8 |
| `surface.py:72` `dict(r)` | `manifest.py:448` `dict(r)` | 🔴 neither, 5th round |

### 6c · Guard table

| guard | subject | verdict |
|---|---|---|
| the YAML parse replacing substring matching | the workflow | ✅ **real improvement** — kills the comment class outright |
| the write-watch replacing before/after | `census()` | ⚠️ **right diagnosis, 1 of 8 cells** |
| `assert results` (census enumerated something) | vacuity | ✅ non-vacuous |
| `assert len(before) >= 6` | the package moved | ✅ good |
| the `seen`/cwd assertion (`_REPO not in s.parents`) | the suite ran outside the repo | ✅ correct, and the fixed-backwards comment is honest |
| `census --selftest`'s positive control | the harness fires | 🔴 **vacuous — 0/2** |
| the census as a gate | 68 sites | 🔴 **broken — measures nothing** |

### 6d · Reachability verdict on **every** finding

| finding | reachability |
|---|---|
| **B24-0** census measures nothing; CI job red; remedy printed is "delete the allowlist" | 🔴 **CI, today, on `main`** |
| **B24-0b** `--selftest` vacuous | 🔴 **CI, today** — it is the gate's own precondition |
| B24-1 `_selftest` live-tree write | 🔴 **live tree** the moment anyone re-spells it; SIGKILL leaves `raise→pass` in a tracked module |
| B24-2/3/4 un-watched write APIs | same, latent |
| B24-5 `_neutered` no-op | measurement integrity, CI |
| B24-6/7/8/9 workflow levers | 🔴 **CI** — each silently disables a blocking gate |
| B24-10 the id is blind to guard weakening (59/59) | 🔴 **CI** — rc=0 over 10 unreachable allowlisted refusals |
| B24-11 the id is reorder-blind for 8/68 sites | verdict-id integrity; the anti-sibling guarantee |
| B24-12 `_mirror()` never cleans up — 108 dirs / 8.4 GB | 🔴 **developer machines + CI runners, today**; and it can drop a copy of the package into the repo, which reds an unrelated test |
| B20-1 `dict(r)` at 4/4 doors | guard-only → **CP-2.1** |
| B18-8 exact-type pins | guard-only → **CP-2.1** |
| B18-10 fifth exported door | structural; the scoping is honest only while there are zero importers |
| B18-11 dead `canon` imports + refuted docstring | dead code + false doc |
| B19-4 `surface.py:305` | guard-only → **CP-2.1** |
| B19-12 `_ID` unbounded | guard-only → **CP-2.1** |
| `ALLOWLIST.write_text` | CRLF drift on Windows on `--write` |
| the R23 register's two dropped rows | process |
| the contamination hazard | 🔴 **the verification loop itself** |

---

## 7 · Falsifiers, integrity, and the numbers

### Falsifier per claim

| claim | falsifier |
|---|---|
| B24-0: the census measures nothing | run it at `b5d81e54a` and get anything other than `0 silent, 68 red, rc=1` |
| B24-0: the new guard test is the cause | deselect **only** that test in a mirror and still get a red suite |
| B24-0b: the selftest is vacuous | make `_neutered` a no-op and get `SELFTEST FAIL` |
| B24-1…9 | apply the named edit and get a red test |
| the injective-id claim | find a pair of sites the `+enclosing-test` digest fails to separate, **or** a message reword that moves a row |
| the 59/59 guard blindness | find one guarded site whose id moves when its test becomes `False` |
| the version claim | produce a 3.12/3.13 id mismatch |
| contamination | show `wt-a`, the overwritten scripts and the stale `vb/*.py` are mine |

### Integrity

Opening sha manifest taken before any command; every injection patched **bytes** from an in-process
snapshot and restored in a `finally` with a sha assertion; `git checkout` never used.

```
be544d37…  scripts/agentruntime-census.py            OK at finish
b4f96741…  .github/workflows/lint-foundation.yml     OK at finish
2994774d…  services/chat-service/tests/test_cp1_membrane.py   OK at finish
d233dd7e…  contracts/agentruntime-census-silent.txt  untouched
ad9feac3…  scripts/agentruntime-membrane-gate.py     untouched
+ all 8 files in app/agentruntime/                   OK at finish
```
`git status` clean of my debris; live suite `137 passed`; **HEAD `b5d81e54a`, unmoved.**

### Executed vs argued

| | count |
|---|---|
| claims **executed** | **38** |
| claims **argued** only | **4** — that CI would go red on GitHub's runners (inferred from a platform-independent `git ls-files` failure); that a guard-condition refactor is acceptable churn; that the `+enclosing-test` id is not *provably* injective on a future tree; that the reorder-blind both-RED groups damage verdict-ids rather than the gate |
| **ratio** | **38 : 4  ≈  **9.5 : 1**** |

Two full 10-minute census runs, one 8-cell grid, 11 bypass injections, 2 controls, 3 selftest
injections, a 68-site × 4-candidate id sweep, a 59-site guard sweep, a 3-group reorder sweep, a
two-interpreter comparison, and a four-door aliasing probe.

### Convergence

| round | findings introduced by B |
|---|---|
| 12–23 | 2, 1, 2, 1, 3, 2, 4, 3, 2, 2, 2, 5 |
| **24** | **14 new** (B24-0, 0b, 1–9, plus the 59/59 id blindness, the 8.4 GB mirror leak, and the builder-in-the-worktree drift) — **the highest of the run, on the second-smallest delta** |
| …clustering to **6 root causes** | the mirror/recursion, the vacuous selftest, the un-watched sibling writer, the un-enumerated write API, the un-enumerated workflow lever, the guard-blind id |
| carried, unclosed | 6 (`dict(r)`, B18-8, B18-10, B18-11, `surface.py:305`, `_ID`) |
| closed by me this round | **1** — the `ast.unparse` cross-version stability bet, measured 68/68 |

**The series has not converged and this round it diverged.** But the shape changed: for the first
time the largest finding was produced by **running the deliverable instead of reading it**, and it
took ten minutes. Eleven of my twelve findings are downstream of two decisions — *execute the gate
first*, and *enumerate the space instead of sampling it*. The previous two rounds read the same file
and found neither, and my predecessor's excellent id analysis was performed on an instrument that
was, at that moment, reporting 68/68 RED.

### 🔮 New falsifiable prediction

**R25 will fix `test_THE_CENSUS_DOES_NOT_WRITE_INTO_THE_LIVE_TREE` so that the census runs again —
and will not clean up `_mirror()`.** The census will report `13 silent, 55 red, rc=0`, this will be
read as closure, and `%TEMP%` will exceed **12 GB**. Specifically:

* `_mirror()` will still contain no `rmtree`/`TemporaryDirectory` at R25's artifact — **falsified** by
  a cleanup landing;
* `_selftest()`'s probe (B24-1) will still be reachable by re-spelling one path with the guard green
  — **falsified** by the guard reding on B24-1;
* the census's `--selftest` will still pass with `_neutered` a no-op — **falsified** by
  `SELFTEST FAIL`.

I predict **3 of 3 hold.** The reason is stated in the delta being graded: the fix moved `census()`
and left `_selftest()` twenty lines below it. **The sibling is the pattern, not the exception, and it
has now happened inside the instrument built to end it.**

---

## Recommendation

**FAIL. Do not close CP-1 against the census at any scope.**

The census cannot certify a single site today: it reports 68/68 RED, rc=1, and instructs the
maintainer to delete the artifact it protects. Closing CP-1 "against the census" would be closing it
against an instrument whose selftest passes when it neuters nothing.

**Minimum to make the census usable as a closing instrument — in order:**

1. **Make the guard test skip inside a census mirror** (2 lines). Measured: restores
   `13 silent / 55 red / rc=0`.
2. **Give `--selftest` a control it cannot pass vacuously** — assert the mirror suite is **green
   before** the injection and red after, in the same mirror.
3. **`_mirror()` must clean up** (4 lines).
4. **Move `_selftest()`'s neutering into the watched path**, or the write-watch is scoped to half the
   writers (B24-1).
5. **Widen the digest to the enclosing test, and assert id uniqueness** (~10 lines total). Closes
   4 collision groups and 59/59 guard blindness, at 0/68 prose churn.

With 1–5 done, **I would support closing CP-1 against the census for the 55 RED sites and the 13
allowlisted rows — and for nothing else.** The census still cannot say a guard is *right*, only that
the suite notices it is gone; §2b shows it currently cannot even say that much about the thirteen
rows it exists to hold.
