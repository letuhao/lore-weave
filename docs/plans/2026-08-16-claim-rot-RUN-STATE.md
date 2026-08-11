# RUN-STATE — claim rot: the measured-state table checks itself

**Reconciles:** `scripts/design-lint.py` · `scripts/gate-wiring-gate.py` · `scripts/closed-set-gate.py` — Phase 0 is **already done and lives in [`docs/specs/2026-08-15-claim-rot.md`](../specs/2026-08-15-claim-rot.md)**: §2 audits the six existing claim-vs-reality mechanisms, §4b audits that audit, and §4c is the experiment that overturned both. This file is the board only; it does not re-derive the design.

---

## 0 · HOW TO WORK

**Binding execution contract: [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)**, adopted verbatim.

Hazards, each earned:

* **`--run-all` DETACHED, read the process's REAL exit code** (`BDR-89`/`BDR-90`), and **edit nothing while it runs** (`WSD-8` — I did it twice and burned two sweeps).
* **Byte-level I/O** for anything a shell executes or any document (`BDR-86`).
* **Never restore a bite with `git checkout`** (`TLD-10`).
* **A bite harness is an unverified check** (`TLD-11`), **its `want` strings are case-sensitive** (the `grep -F` miss), and **a gate's own documentation can trip it** (`WSD-4`).
* **Backticks in `git commit -m` trigger command substitution** — use `-F` with a message file.

**Not stop conditions:** a commit · a green sweep · a POST-REVIEW · uncommitted work · **wanting a decision this file can make**. That last one is why this board exists: the previous turn stopped to ask two questions that were mine to seal, which is the anti-pattern §0.6b names.

---

## 1 · SEALED FORKS

**`CR-F1` · Widen `actor-hub-figures-gate` IN PLACE. No rename, no clone, no extraction.**
Measured before sealing: `actor-hub-figures` has **279 textual references across 14 files**, including four scripts (`gate-bite-harness`, `gate-self-tests`, `gate-teeth-gate`), the standards index, and run-state history that is a record and must not be rewritten.

* **Rename — rejected.** 279 refs, and rewriting history to fix a filename is worse than the filename.
* **Clone — rejected.** ~200 lines of machinery carrying five recurrences of scar tissue (`D-343`…`D-359`), duplicated to serve a second consumer.
* **Extract to a shared module — rejected FOR NOW.** Two consumers is not rule-of-three, and it refactors a load-bearing gate in order to add a feature to it.
* **Chosen:** the file keeps its name; its **docstring becomes the contract** and states that it governs figures in *track run-states* — actor-hub first, reality-layer second. `gate-wiring-gate` keys on the `-gate.py` suffix, which is untouched.

**Reversal trigger: a THIRD consumer.** That is rule-of-three, and then extract.

**`CR-F2` · The unmeasurable sub-claims get MARKED in the table, not left to look verified.**
§4c found six: a behaviour (`REC-106` refuses a self-parent), one needing a live process (*"SERVING"*), one needing a toolchain (*"33 commands"*), a historical claim (*"was disabled"*), a row's contents (*"cap 50"*), and — the honest core of this whole thread — **one with no predicate at all**: *"not a scaffold"*. Nobody has ever said what would falsify it. A table where checked figures sit beside unchecked prose, indistinguishable, is this defect one level down. **Reversal trigger:** none.

**`CR-F3` · Figures only. Behaviours, live-process state and history are OUT, by name.**
The unit is the FIGURE inside a marker-delimited window — the precedent's unit, which §3 of the spec had drifted off. A gate promising to check *"SERVING"* would be wrong on any box with nothing running. **Reversal trigger:** none within this track.

---

## 2 · THE BOARD

| # | row | done = | state |
|---|---|---|---|
| `CR0` | this file | `phase0-reconcile-gate.py` passes, output pasted | ✅ `REAL_RC=0`; SELFTEST 11 cases + 13 specs vs 128 index rows |
| `CR1` | the measurements | a `measure()` entry per governed figure, each **runnable** and each degrading to `Unmeasurable` rather than crashing when its dependency is absent (no Postgres, no Docker) | ✅ 10 entries, all 10 agree with the doc; `PATH` stripped of `psql` → 6 degrade with a named reason, **4 still measure**, rc 0 |
| `CR2` | the claims + scope | a `CLAIMS` pattern per figure and a `SCOPES` window over the reality-layer MEASURED STATE table; the gate's docstring restated per `CR-F1` | ✅ 10 `CLAIMS` rows, one `SCOPES` window + `must_claim` naming all 10 keys; docstring restated |
| `CR3` | `CR-F2`'s marking | every sub-claim §4c found unmeasurable is visibly marked in the table as not checked, with which of the ~~four~~ **six** reasons (`CRD-3`) | ✅ 6 `[NC:…]` tags + a 6-row legend, both inside the governed window |
| `CR4` | bitten | change a figure in the doc → red naming both sides; change the measurement → red; break the scope window → **reach** red rather than a silent pass over zero subjects; an absent dependency → `Unmeasurable`, exit 0, said out loud. All restored byte-exact | ✅ 5 arms, ALL PASS, every restore sha-verified byte-exact |
| `CR5` | verify | `cargo test --workspace` + a **detached** `--run-all`, REAL exit codes pasted; `NO_PROOF_BASELINE` unchanged (the gate already carries a `--self-test`) | ✅ `cargo test --workspace` **`REAL_RC=0`**, 184 green binaries · sweep **`SWEEP_REAL_RC=0`**, **86 GREEN / 0 RED** (1 documented SKIP: bencher needs a live stack) · gate `--self-test` **156 cases / 0 failures** · `gate-bite-harness` **84/84** · `NO_PROOF_BASELINE` **43, unchanged** (`gate-teeth-gate.py` untouched) |

### `CR4` — the five arms, and what each one is for

| arm | mutation | the RED it must produce |
|---|---|---|
| `A` | a governed figure moves in the DOCUMENT | `claims 11 for realities in the registry, measured 10` — **both sides named** |
| `B` | the MEASUREMENT moves, the document does not | `claims 39 for the meta database's migration count, measured 78`. Without this arm the gate is half a check: it could tell you the doc changed but never that the WORLD did |
| `C1` | the end sentinel DELETED | `the markers … do not both resolve, so this document was NOT checked` — **reach**, plus all 10 keys reported orphaned and 10 `NV-3` no-subject findings |
| `C2` | the sentinel **MOVED UP** two rows | the window still RESOLVES, so `C1`'s rule is silent — only `must_claim` fires, naming exactly the 5 keys below the new position. This is the arm that proves `C1` is not doing both jobs |
| `D` | the dependency is absent | rc **0**, `NOT CHECKED here (psql is not on PATH)` per figure — an unmeasurable claim is a SKIP that says so, never a refusal |

**`CR4b` — the bites made permanent, because a transcript is not a mechanism.**
**Eight** new rows in `scripts/gate-bite-harness.py` — the table goes **76 → 84**
— behind **15** new `--self-test` cases (141 → 156), plus one existing anchor
widened. A case asserts the rule works today; a mutation asserts the case would
notice if it stopped. The eight: the reality scope row · the psql-absent guard ·
the psql error branch · the non-count scalar guard · the empty-glob **reach**
guard · the dev DSN pinned instead of read from compose · the exemplar database
pinned instead of read · and the psql memo row that `CRD-6` split off from
cargo's. Running the full table also found `CRD-8`, a pre-existing survivor that
a sentence had been certifying for weeks.

**Final:** `all 84 mutations reddened their self-test`, `REAL_RC=0`.

**Honest limits of the harness.** It injects `cargo` away, so the actor-hub Rust
figures were NOTES during the bites — that does not touch the reality-layer arms,
and it is why the run takes seconds instead of the >10 minutes the first attempt
burned before it was killed. Arm `D` patches `_psql` in-process; the genuine
`PATH`-stripped subprocess run is `CR1`'s evidence, so both forms are on record.
And the harness's own first version **hung for eleven minutes** walking up from
`__file__` for a `.git` that is not above the scratchpad — `Path.parent` at a
drive root returns itself. `TLD-11` again: a bite harness is an unverified check.

---

**Shipped: `e66eb7d9d`** — 5 files, +580/−17.

---

## 3 · OPEN ROWS

| id | what | why not here | mechanism |
|---|---|---|---|
| `CR-PROSE-CLAIMS` | the two instances that survived longest are prose — the `world-service` README (*"Cycle 0 scaffold"*, months) and the measured-state row's own narrative half | `CR-F3` — a gate that promised these would be wrong on any dev box, and *"not a scaffold"* has no predicate | **none, and it is honest that there is none.** §5 of the spec: this catches the next reader, not the author who falsifies. The README rotted because nobody read it, and a gate does not fix not reading |
| `CR-OTHER-TABLES` | other tracks' run-states have measured-state blocks under no gate | `CR-F1`'s reversal trigger — the third consumer is when to extract | adding one is a `SCOPES` entry; the cost is the measurements, not the machinery |

---

## 4 · DRIFT REGISTER

**An empty drift log is not evidence of a clean run.**

| id | what happened |
|---|---|
| `CRD-1` | **I stopped to ask two questions that were mine to answer, having quoted the rule against it all session.** After the experiment settled Q4 I presented a three-option menu — including one option I had already picked in the same sentence (*"I lean widen + rename"*). §0.6d lists *"wanting a decision this file can make"* as **not** a stop condition. Root cause: when the world-service goal auto-cleared I reverted to interrupt-driven work instead of continuing under one. |
| `CRD-3` | **`CR3`'s own `done=` cell was a stale figure, in the board written to kill stale figures.** It said *"which of the four reasons"* while `CR-F2` one screen above enumerates **six** — behaviour, live-process, toolchain, history, row-contents, no-predicate, one per sub-claim. Written the same hour, by me, in the same file. Nothing would have caught it: a board's `done=` cell is prose, and `CR-PROSE-CLAIMS` is open precisely because this track builds no mechanism for that. **The disease demonstrating itself on the doctor** — and the honest reading is that it is evidence FOR `CR-PROSE-CLAIMS` being a real gap rather than a formality. |
| `CRD-8` | **`SESSION_HANDOFF`'s governed block claimed something false, and it says to check.** *"Every mutation in the committed mutation harness reds its gate's self-test (…run it rather than trust this sentence)"* — I ran it: **82 of 83**. `the cargo-absent guard removed` makes the child invoke a real unfiltered `cargo test`, and a WARM one here is **>400s** against the harness's 300s child bound, so it scored a survivor on any machine where the workspace takes over five minutes. **Pre-existing, not this round's** — the change added no Rust — and the gate this round widened *cannot* catch it, because it is prose. Direct evidence that `CR-PROSE-CLAIMS` is a real gap and not a formality. Fixed at the root: the case now injects a runner it proves UNREACHABLE, so the guard's removal is detectable in 30s with no toolchain — which is what this gate's own docstring already demanded (*"a rule whose coverage depends on the developer's machine is not covered"*). |
| `CRD-7` | **I diagnosed the timeout confidently and wrongly, then tested it.** First read: my concurrent `cargo test --workspace` held the target-directory lock and starved the child. Plausible, mechanical, and **false** — re-running the mutation alone timed out identically. The concurrency call was still a mistake worth naming (I argued *"cargo touches none of the Python the harness is rewriting"*, not noticing the mutated gate INVOKES cargo), but it was not the cause. One command separated the two, and I nearly wrote the first one into the register as fact. |
| `CRD-9` | **The pre-commit hook refused this commit, and it was right.** `_psql` spawned through a module-level `_psql_runner`, so the `subprocess.run` sat in a function carrying no `except subprocess.TimeoutExpired` of its own — the bound existed and its expiry was an **uncaught traceback out of a hook that fires repo-wide**, which `gate-bite-harness`'s `unbounded_children` rule exists to catch. `_cargo_passed`, twenty lines above the code I was writing, already spawns through an inline lambda for precisely that reason. **I invented a second shape instead of reading the first**, in a file whose docstring records that exact class four times. Fixed by moving the spawn inside `_psql`'s own `try`. Worth naming because it is the run's clearest case of a MECHANISM catching what reading did not. |
| `CRD-6` | **`_psql` copied `_cargo_passed`'s cache bypass verbatim, and broke an existing bite.** The line `cacheable = run is None and which is None` then matched twice, so the harness reported **table drift** rather than mutating the wrong function — it caught me. The deeper point is the one this file keeps relearning: **a rule written twice is a rule with half a test.** The copy now carries its own mutation row, and both anchors carry their `key =` line. |
| `CRD-5` | **The bite harness hung for eleven minutes and produced nothing, twice over.** First version shelled the gate ~15 times, each paying a cold `cargo test` — killed at 10 minutes. Second version walked up from `__file__` for a `.git` that is not above the scratchpad, and `Path.parent` at a drive root returns ITSELF, so it spun. Output was buffered, so both looked identical from outside: silence. `TLD-11` — **a bite harness is an unverified check** — and the tell I nearly missed is that ZERO bytes after eleven minutes is not *slow*, it is *stuck*, because Python flushes at 8 KB. Cost: ~20 minutes and one `TaskStop` against a tree I had to verify by hand was not left mid-mutation. |
| `CRD-4` | **The coverage arm fired on me, mid-row.** The legend I wrote for `CR3` used a bolded **34** to argue why a naive admin-command count is untrustworthy — and the gate refused the commit, because a bolded figure inside a governed block read by no rule is exactly what it hunts. Fifteen minutes after the block was placed under it. Recorded not as an embarrassment but as the strongest available evidence that the reach is live: I did not construct this case, I walked into it. |
| `CRD-2` | **The lean I was about to ask permission for was wrong, and one command would have shown it.** *"Widen + rename"* — `actor-hub-figures` has **279 references across 14 files**, including four scripts and immutable run-state history. Had the question been asked and answered yes, the answer would have been acted on without the measurement, because I presented a preference rather than a cost. Sealing a fork forces the measurement; asking does not. |
