# RUN-STATE — gate teeth: 41 gates that assert coverage nobody has proven

**Reconciles:** A gate, lint, test, `const` assertion, validator, or an axiom that constrains code ·
MCP Tool I/O Standard · Settings & Configuration Boundary — the first is the governing row; the
others because the recurring defect below is theirs in a different costume (a closed set that is not
enum-locked, a value stored and never consumed). Phase 0 is §1 and was measured, not assumed.

---

## 0 · HOW TO WORK

**Binding execution contract: [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)**, adopted verbatim.

Hazards, each earned in this repo:

* **`--run-all` DETACHED, read the process's REAL exit code** (`BDR-89`/`BDR-90`) — a task
  notification said *"exit code 0"* over a run whose process returned **1**, on 2026-08-11.
* **Edit nothing while a sweep or bite harness runs** (`WSD-8`).
* **Byte-level I/O** for anything a shell executes or any document (`BDR-86`).
* **Never restore a bite with `git checkout`** (`TLD-10`) — it restores from the index and deletes
  unstaged work.
* **A bite harness is an unverified check** (`TLD-11`); its `want` strings are **case-sensitive**.
* **Never hand bash an absolute Windows path** — backslashes are eaten as escapes and every arm
  reports `rc=127`. Use a relative path under `cwd`.
* **Backticks in `git commit -m` trigger command substitution** — use `-F`.

**Not stop conditions:** a commit · a green sweep · a batch finishing · a POST-REVIEW · wanting a
decision this file can make.

---

## 1 · PHASE 0 — measured 2026-08-12

| fact | value | command |
|---|---|---|
| CI-invoked gates | **98** | `gate-teeth-gate.py --list` |
| carrying a red-ability proof | **57** | same |
| carrying none | **41** | same |
| …of those, shell | **26** | `--list \| grep 'no red-ability'` |
| …of those, Python | **15** | same |
| size range | **38 – 386 lines** | `wc -l` |

**Every one of the 98 is already proven able to return non-zero.** What the 41 lack is a proof that
they return non-zero *for their own reason* — that the rule bites rather than the script merely
being capable of exiting 1.

### 1.1 · ⚠️ THE TRAP — why this number sat still

**Proof detection is STRUCTURAL.** `gate-teeth-gate` searches executable text for
`def self_test` / `selftest() {`, or a `test_<name>.py`. **It cannot distinguish a real self-test
from an empty one.** So 41 stub functions would take this baseline to **zero** and prove nothing.

That outcome is **strictly worse than 41**: a gap invites work, a false pass silences review. It is
also exactly `NV-1` — a check that cannot fail is a claim in the costume of evidence — committed
inside the mechanism built to count `NV-1` violations.

**Therefore the unit of progress on this board is not "a `selftest()` exists". It is "a mutation of
the rule makes the self-test red, and the output is pasted."**

### 1.2 · The house pattern, already in the tree

`scripts/emit-migration-0013-lint.sh` is the precedent and is copied rather than reinvented:

1. extract the rule into a **predicate function** a case can drive;
2. `selftest()` asserts **both directions** — the bad sample is flagged, the good sample is not;
3. `case "${1:-}"` runs **`selftest; run_lint`** on a bare invocation, so the proof executes on
   every CI run rather than on request;
4. selftest failure exits **2**, distinct from a lint violation's 1.

### 1.3 · What the first batch found, which generalises

Both gates in batch 1 **counted nothing**. A walk that reached zero services printed `PASS` —
byte-identical to compliance (`BDR-82`). **Assume every one of the 41 has this defect until its
counter is read**; a reach floor is part of the work, not an extra.

---

## 2 · SEALED FORKS

**`GT-F1` · A `selftest()` is not counted until it is BITTEN.** Six steps, output pasted, restore
byte-exact. **Reversal trigger: none.** This is the board's reason to exist (§1.1).

**`GT-F2` · Batch by SHAPE, not by size.** Gates sharing a predicate shape (*"X must appear in
registry Y"*) share their case design, so the second costs a fraction of the first. Ordering by line
count would scatter the shapes and pay the design cost every time.

**`GT-F3` · Every gate gains a REACH FLOOR in the same edit.** `0 < floor < measured`, printed. A
gate that cannot say what it scanned cannot be believed when it says it found nothing (`BDR-82`,
and §1.3 measured it twice out of two).

**`GT-F5` · Every EXEMPTION LIST gains a SHRINK ARM in the same edit** (sealed 2026-08-12, from
evidence rather than principle). Three allowlists in a row needed one and none had it:
`projection-coverage`'s 12 rows, `runbook-drift-check`'s 23 (**91% dead**), and by extension any
list to come. A row dies two ways — its **subject disappears**, or its **reason expires** — and both
must red. An exemption with no expiry is permanent by default, and the `runbook-drift` case shows
that is not merely untidy: each of its 21 dead names would have silently satisfied a stale runbook
reference, i.e. the allowlist could hide the very drift the gate detects. **Reversal trigger:** none.
The repo already had the pattern twice (`deferral-gate`'s `PROSE_ONLY`, `dp-oracle-coverage`'s
`NO_PRODUCER`); this fork stops it being rediscovered a fourth time.

**`GT-F4` · The baseline moves only DOWN, and only after the bite.** The ratchet already refuses to
pass until the number follows a drop; it must never be raised to accommodate a gate that lost its
proof. **Reversal trigger:** a scope widening that legitimately adds unproven gates — the 2026-08-10
`45 → 55` precedent, which is recorded as the one honest exception.

---

## 3 · THE BOARD

`done =` for every batch row: **each gate carries a predicate-driven `selftest()` asserting both
directions, a reach floor, and a pasted six-step bite; `gate-teeth-gate` green at the lowered
baseline; the batch committed.**

| # | batch | gates | state |
|---|---|---|---|
| `GT1` | registry membership — the smallest two | `capacity-budget-lint.sh` · `service-acl-matrix-lint.sh` | ✅ **43 → 41**, `baed59cad`. 5 bite arms, all byte-exact |
| `GT2e` | ecosystem pinning | `dep-pinning-lint.sh` | ✅ **38 → 37.** 5 bite arms. Two findings that dwarf the proof — `GTD-8` (89% foreign trees, and `-not -path` does not prune) and `GT-DOCKER-WARN-100PCT` |
| `GT2d` | handler-registry membership | `admin-command-registry-lint.sh` | ✅ **39 → 38.** 5 bite arms (marker parser · receiver narrowing · the case fold · membership · the exempt pragma). **Its scans have ZERO subjects** — see `GT-ADMIN-NO-SUBJECT` |
| `GT2c` | config-vs-tree conformance — moved here from `GT2` | `language-rule-lint.sh` (the LOCKED I3 amendment) | ✅ **40 → 39.** `run_lint` parameterised on config + services root, so 5 bite arms drive the WHOLE gate end-to-end: the outer `Cargo.toml` marker, the parse block-end rule, the I3 comparison, PRR-21 completeness, and the reach floor. Two self-inflicted findings — `GTD-6`, `GTD-7` |
| `GT2b` | forbidden-shape scanners — moved here from `GT2` | `dependency-registry-lint.sh` | ✅ **41 → 40.** 4 bite arms (one Go shape · one Rust shape · the exemption widened · the walk pointed at nothing), all byte-exact. Two defects fixed in passing — see `GTD-4`, `GTD-5` |
| `GT3c` | runbook ↔ service drift | `runbook-drift-check.sh` | ✅ **34 → 33.** 4 bite arms. Its allowlist was **91% dead** — see `GTD-12`. `GT3` is now CLOSED |
| `GT3b` | registry coverage + exemption hygiene | `projection-coverage-lint.sh` | ✅ **35 → 34.** 3 bite arms. Its allowlist had **no shrink arm** — see `GTD-11` |
| `GT3a` | drift / mirror checks — done | `read-audit-query-type-drift-lint.sh` · `transitions-validation-lint.sh` | ✅ **37 → 35.** 6 bite arms. Each shipped a DIFFERENT way of passing over nothing — `GTD-9`, `GTD-10` |
| `GT4a` | handler instrumentation | `tracing-completeness-lint.sh` | ✅ **33 → 32.** 5 bite arms incl. BOTH ratchet directions. Second DISARMED gate — see `GTD-13` |
| `GT4b` | metric inventory conformance | `observability-inventory-lint.sh` | ✅ **32 → 31.** 4 bite arms. Same missing-file hole as `transitions-validation` — see `GTD-14` |
| `GT4` | observability inventory | · `dashboard-validator.sh` · `alert-rule-validator.sh` · `slo-latency-lint.py` | ⬜ |
| `GT5` | discipline lints (forbidden-shape scanners) | `timeout-discipline-lint.sh` · `blocking-in-async-lint.py` · `prompt-assembly-discipline-lint.sh` · `raw-sql-lint.py` · `pagination-cap-lint.py` · `logging-discipline-lint.sh` | ⬜ |
| `GT6` | context-budget family | `context-budget-l3-lint.py` · `context-budget-defaults-lint.py` · `context-inspector-checklist-gate.py` · `context-inspector-trace-gate.py` | ⬜ |
| `GT7` | deploy / freeze | `deploy-class-check.sh` · `deploy-freeze-check.sh` · `feature-freeze-enforcer.sh` · `raid/prod-isolation-lint.sh` | ⬜ |
| `GT8` | the remainder, one at a time | `knowledge-access-gate.py` · `knowledge-http-surface-gate.py` · `boundaries-lock-gate.py` · `ingress-admission-gate.py` · `i18n-completeness-gate.py` · `design-draft-token-lint.py` · `game-wire-lint.py` · `sdk-duplication-gate.py` · `phantom-route-scan.py` · `outbox-event-emit-lint.sh` · `role-grant-validator.sh` · `template-fixture-validator.sh` · `runbook-verification-lint.sh` · `perf/bench-gate.sh` | ⬜ |

**The batch list is a WORKLIST, not the scope.** The scope is the predicate *"CI-invoked and no
red-ability proof"*, which `gate-teeth-gate --list` recomputes. A gate added tomorrow joins it
without anyone editing this table — and if this table and the gate ever disagree, **the gate is
right**.

---

## 4 · OPEN ROWS

| id | what | why not here |
|---|---|---|
| `GT-STRUCTURAL-DETECTION` | the ratchet counts a `selftest()` it cannot evaluate (§1.1) | fixing it means executing every gate's self-test and judging it, which is `gate-bite-harness`'s job — the two mechanisms already exist and the gap is that nothing joins them. A real row, deliberately not solved by this board |
| `GT-OBS-UNEMITTED` | **54 of the 100 metrics declared in `contracts/observability/inventory.yaml` are emitted nowhere in code** | planned-but-unbuilt and rot look identical from here, and this gate cannot tell them apart — declaring a metric ahead of its emitter is legitimate. Reported as a number on every run rather than enforced, so the ratio is visible to whoever can judge it. A shrink arm would need a producer/planned distinction the inventory does not carry |
| `GT-TRACING-WARN-OVERDUE` | `tracing-completeness-lint` runs in warn mode with **49** untraced handlers; the error-mode flip its header promises for *"cycle 33+"* is in no deferral row and no handoff line | the flip is a MIGRATION (49 call sites), not a lint change, so it is not this board's to make. The gate is now armed by a ratchet that reds on any NEW untraced handler, which is the part that can regress today. Whoever owns the tracing migration owns the flip |
| `GT-DOCKER-WARN-100PCT` | `dep-pinning`'s Docker arm warns on **36 of 36** Dockerfiles; **zero** digest-pinned `FROM`s exist anywhere in the tree | a warn that fires on 100% of its subjects has no discriminating power — it was 36 identical lines every CI run, which is how a gate teaches people to skip its output. Collapsed to a ratio, which still moves the day someone digest-pins one. Whether to adopt digest pinning at all is a platform decision, not a teeth one |
| `GT-ADMIN-NO-SUBJECT` | `admin-command-registry-lint` walks `services/` and matches **nothing**: `// ADMIN-SQL:` and `// ADMIN-RPC:` occur **0** times, `func (… *AdminHandler)` **0** times. Its rule is now proven to bite, but it has nothing to bite in this tree, and its old message read as verified admin coverage | **not resolved by making it red** — zero markers is the TRUE state and failing on the truth is cry-wolf. The gate now prints its subject count and says nothing was compared. The real question is whether the marker convention should be adopted (the live admin surface is the 10 registry YAMLs + the Go dispatcher) or the gate retired; that is a design call, not a teeth call |
| `GT-PERF-BENCH` | `perf/bench-gate.sh` SKIPs in `--run-all` (*"needs a live stack"*) | a gate that cannot run here cannot be bitten here; it needs the stack, and a self-test for it would be testing the skip |

---

## 5 · DRIFT REGISTER

**An empty drift log is not evidence of a clean run.**

| id | what happened |
|---|---|
| `GTD-1` | **The first bite arm certified nothing and looked like a pass.** Blanking the whole meta-write alternation red the self-test — but on its FIRST case, so it proved `contracts/meta` was live and said nothing about the other two. A bite that reds for the wrong reason is a bite that certifies coverage it never exercised. Split into one arm per alternative. |
| `GTD-15` | **The first gate that was already right, and it is worth recording as loudly as the broken ones.** `slo-latency-lint.py` exits 2 on a missing config, exits 2 on an empty `endpoints:` list, and prints its count — reach sound before I touched it, unlike the twelve before it. It needed only cases and a `GT-F5` shrink arm. **The case worth keeping:** `p95_ms: true`. `True` IS an `int` in Python, so without the explicit `isinstance(p95, bool)` guard a boolean passes as the number 1 — a positive number, and a green SLO. The guard was already there; nothing proved it load-bearing until a bite arm removed it and watched the case go red. A correct guard with no case is one refactor from silently disappearing. |
| `GTD-14` | **The same missing-file hole, in a gate that had already survived two `NV-4` findings.** `observability-inventory-lint` opened with `if [[ ! -f "$inventory" ]]; then echo "skipping"; exit 0; fi` — one `git mv` from permanently green, and the SECOND gate on this board with that exact line. Its header is unusually careful (it documents two hard-won false-positive fixes), which is the point: a gate can be well-maintained on the axis someone was looking at and still pass over nothing on the axis nobody was. Its EMITTED side had no floor either — the declared side fails loudly when it empties, so the asymmetry hid it. |
| `GTD-13` | **A second disarmed gate, and its re-arming promise was tracked nowhere.** `tracing-completeness-lint` defaults to `warn`: it printed **49** violations and exited 0, so *"it passed"* and *"49 handlers have no tracing"* were the same observable. Its header promised the error-mode flip *"in cycle 33+"* — measured 2026-08-12, that appears in no deferral row and no handoff line. Prose, several cycles overdue, nothing to wake it. **Armed with a RATCHET instead of a flip**: flipping reds the build on 49 pre-existing violations (a migration), while a falling baseline reds a NEW untraced handler today. Both directions bitten — a ratchet that only reds upward never falls. Tracked as `GT-TRACING-WARN-OVERDUE`. |
| `GTD-12` | **A second allowlist, 91% dead, and this one could hide the drift it guards against.** `runbook-drift-check`'s `KNOWN_LOGICAL` held 23 names described as *"canonical platform names that aren't yet `services/` dirs"* — **19 of them ARE `services/` dirs** (they shipped) and 2 more are cited by no runbook. **Two** were load-bearing. Worse than dead weight: each of the 21 would have silently satisfied a stale runbook reference, which is exactly the drift this gate detects. Trimmed to two with both shrink arms. Third allowlist in this repo to need them — `GT-F2` should probably become *"every exemption list gets a shrink arm in the same edit"*. |
| `GTD-11` | **A 12-row allowlist with no shrink arm — an exemption permanent by default.** `projection-coverage-lint` reds when a registered event has no projection, but nothing red when an allowlisted event was **deregistered** (the row outlives its subject) or when one **gained a projection** (the reason expired). The `npc.said` row literally documents its own retirement trigger in prose — *"when the actor/NPC track ships an emitter, this row must be replaced"* — and no mechanism could notice. This repo already solved it twice (`deferral-gate`'s `PROSE_ONLY` shrink, `dp-oracle-coverage`'s `NO_PRODUCER`); this gate just never got the arm. Measured clean on landing: 0 stale, 0 expired. **Its docstring was also stale** — *"5/14 registered events are projected"* against a measured **4/16**, i.e. claim rot in the header of a gate. |
| `GTD-10` | **`transitions-validation-lint` was one `git mv` from permanently green.** Its first statement was `if [[ ! -f "$target" ]]; then echo "nothing to lint"; exit 0; fi`. Rename or move `contracts/meta/transitions.yaml` and the gate reports success forever, with a cheerful message explaining why. The file existing today is the only reason it never bit. An EMPTY file was the same story by a second road — all three heuristics are trivially satisfied by no content. Both are now exit 2. |
| `GTD-9` | **`read-audit-query-type-drift-lint` called two empty sets agreement.** The entire gate is one string comparison between two grep outputs; if either pattern stops matching, both sides become `""`, the equality holds, and it prints *"PASS — CHECK == YAML SSOT (**0 ids**)"*. A drift detector that reports agreement because it parsed nothing is the defect it exists to catch, wearing its own success message — and the `(0 ids)` was printed on every run for anyone who looked. Floor added BEFORE the comparison, because after it the answer is already wrong. |
| `GTD-8` | **`-not -path` does not prune, and I had assumed it did.** `dep-pinning-lint` excluded `node_modules`/`.venv` by RESULT filter, so `find` still descended into every `.claude/worktrees/*/target/` — two complete Rust build trees, four times per run. 51–76s for a gate whose real subject is 131 files; `-prune` took it to **13s**. The scope error underneath it was worse than the latency: **89% of what it scanned was foreign** — agent worktree copies, `site-packages`, `vendor` — so it was judging third-party packages by this repo's pinning convention, one bare `requests` away from a false finding nobody could act on. |
| `GTD-7` | **I wrote a second reach floor that could never fire.** `language-rule-lint` got floors on both *directories walked* and *comparisons made* — but a comparison requires the directory to EXIST under the root, so `scanned == 0` implies `compared == 0` and the walk floor was strictly shadowed by its sibling. A rule that cannot produce a finding another does not is **deletable with the suite green**, which is the precise defect this whole board exists to remove. Deleted rather than kept as decoration; its count folded into the surviving message. Ten minutes between writing it and its own gate's discipline catching it.
| `GTD-6` | **A floor placed above the violation report turned a real finding into a misuse code.** The PRR-16 case (a service declared `missing` but present on disk) returned **2** instead of **1**, because the zero-comparisons floor fired before violations were counted. Floors exist for the SILENT case; if the gate found something it demonstrably had a subject. Ordering fixed — and the end-to-end self-test is what caught it, which a unit test of `detect_lang` never could have.
| `GTD-5` | **The reach floor I added to satisfy `GT-F3` could not reach its own reason.** Under `set -euo pipefail` a `find` on a missing directory fails, the command substitution fails with it, and the script dies at that line with rc=1 — *before* the floor can report anything. So the guard against "the walk reached nothing" was inert in exactly the case it was written for. **Found by the bite, not by review**, and it is the fourth non-vacuity shape by name: an adjacent decision (a shell option set at the top of the file) defeating a guard added at the bottom. Fixed with `|| true` inside the braces. |
| `GTD-4` | **`dependency-registry-lint` reported `2` violations against a real `49`, for months.** The counter incremented once per GREP BLOCK, not per hit, so two categories read as two call-sites. Anyone tracking the ClientFactory migration off that line — and `DEFERRED 082` is exactly that — would think it was nearly done. Nobody noticed because the gate runs in WARN mode and exits 0 either way: **"it passed" and "it found 49 problems" were the same observable.** |
| `GTD-3` | **`GT2`'s batch was grouped by a shape I had not read.** I filed `dependency-registry-lint.sh` under *registry membership* on the strength of its NAME; it is a forbidden-shape scanner and shares nothing with `capacity-budget`. `GT-F2` says batch by shape precisely so the design cost is paid once — and I grouped by filename, which is the same error one level up. Split into `GT2b`; the remaining `GT2` entries are still unread and may move too. |
| `GTD-2` | **Handed bash an absolute Windows path and all four arms died at `rc=127`.** `D:\Works\…` arrives as `D:Works…` — backslashes eaten as escapes. Cost one full harness run to diagnose something the tree had already taught me twice this session. |
