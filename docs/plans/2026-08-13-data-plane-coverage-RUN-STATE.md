# DATA-PLANE COVERAGE — RUN-STATE

**Opened 2026-08-13** · branch `feat/game-logic` · opened at HEAD `eda010977`

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3** · Data Plane channels
**DP-Ch1–Ch37** · A gate, lint, test, `const` assertion, validator, or an axiom that constrains
code —
`phase0-reconcile-gate` refused the first commit of this file for having no such line, and it
was right to: this is a plan against a tier that already holds 25 LOCKED documents. What the
look found, all measured:

* **§C is the rule this run enforces, not a new one** — and it is deliberately absent from the
  field above, because §C is PROSE in the index, not a table row, and the gate resolves table
  rows. Naming it in the field would have been a reference pointing at nothing, which is the
  phantom shape the gate exists to refuse. *"Durable `INV-<id>` rules cited **at the
  enforcement site and in a proving test**."* The two tiers this run measures (`sited`, `proven`)
  are that sentence, counted. Nothing new is being invented — an existing convention is being
  given an instrument.
* **§F's channels row is STALE: it says `DP-Ch1–Ch37`; the docs declare `DP-Ch1..Ch53`** — 53
  ids, 16 of them outside the range the index advertises. The index is where an agent looks to
  find out what governs a change, so a short range reads as *"Ch38+ is not governed"*.
  Tracked as `DPD-6`; **not fixed here** — editing the index is a separate change with its own
  review, and a plan file is not the place to silently amend a standard.
* **§F's DP-A/R/T row claims `dp::forbid_*` clippy lints.** They exist — `forbid_raw_kernel_client`
  and `forbid_swallowed_backpressure` in `lints/dp-clippy/src/lib.rs`, citing `DP-R3` and `DP-R6`.
  **My first pass said they did not exist**, because I grepped `lints/dp-clippy/libs/`, which holds
  only a compiled `.dll`. Corrected before it was written down. The honest reading: two lints
  covering two ids, under a row that advertises enforcement for **31**.
* **No overlapping instrument exists.** No gate measures citation coverage for any invariant
  family — `dp-channels-schema-gate` compares spec SQL to migration SQL, `design-lint` checks
  doc-side prefixes against an id catalog, and `gate-teeth-gate` measures gates, not invariants.
  `DP-COV0` is new, and question 2 (does it have a producer?) is answered by its own CI wiring.

> This file is the commitment. `/goal` holds the session open; **this file holds the work.**
> After any compaction, re-read `§0` FIRST, then `git log`, then continue. Never re-litigate a
> sealed decision from memory — re-read it here.

---

## 0 · HOW TO WORK — BINDING

### 0.1 The execution contract

This run **adopts §0.6d of [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md)**
as its execution contract, unchanged. That file also still holds §0.6c (sealed forks) and §5
(`BDR-57`..`BDR-90`). Read it before the first batch.

### 0.2 The problem, measured 2026-08-13

> **These numbers were hand-measured and WRONG in three ways. `DP-COV0` replaced them.**
> The hand count said 86 declared / 34 uncited. Measured by the gate: **84 declared**
> (`DP-R9`/`DP-R10` were never declarations — see `DPD-1`), and the walk covers `services/` and
> four more languages than my grep did. **Never re-hand-count this; run the gate.**

`docs/03_planning/LLM_MMO_RPG/06_data_plane/` declares **84** invariants. Measured by
`scripts/dp-invariant-coverage-gate.py` on 2026-08-13, over **4397** files:

| family | declared | uncited | unproven |
|---|---|---|---|
| `DP-T` | 4 | 0 | 0 |
| `DP-R` | 8 | 1 | 0 |
| `DP-A` | 19 | **7** | 11 |
| **`DP-Ch`** | **53** | **25** | **36** |
| **total** | **84** | **33** | **47** |

**sited 51/84 · proven 37/84.**

Reproduce:

```bash
python scripts/dp-invariant-coverage-gate.py --list     # once DP-COV0 ships
```

The worklist is **`--list`**, not a list in this file — a list here is a second source of
truth that goes stale the first time an id is closed.

### 0.3 What "cited nowhere" does and does not mean

**It is not a synonym for "unenforced."** An invariant can hold by construction — a newtype that
makes the bad state unrepresentable needs no comment naming the rule. So the deliverable of this
run is **a decision per id, mechanised**, not a number driven down.

But an uncited id **is** untraceable, and this repo's convention exists precisely against that:
[`docs/standards/README.md`](../standards/README.md) §C — *"Durable `INV-<id>` rules cited **at the
enforcement site and in a proving test**. Grep an ID to find both its guard and its test."*
An id you cannot grep to a guard is where a dead rule hides, and this project has now found that
shape often enough to have a standard about it.

### 0.4 The three classifications — and the one that must be EARNED

Every one of the 34 lands in exactly one:

| # | verdict | what it costs |
|---|---|---|
| **(a)** | **enforced by construction** | Name the construct. Add a test that **cites the id** and reds when the construct is removed. A verdict nothing can check is not a verdict. |
| **(b)** | **enforced, but uncited** | Add the citation **at the enforcement site AND in its proving test** (§C). If no proving test exists, it is (c), not (b). |
| **(c)** | **genuinely absent** | Build it, or open a `§4` row that **carries a mechanism** — an asserted trigger that reds when its subject arrives, a ratchet, or a `KNOWN_RED`. Never prose. |

> **⚠ (a) IS THIS RUN'S `GT-F1`.** On the gate-teeth board, proof detection was *structural*, so 28
> stub self-tests would have taken the baseline to zero and proven nothing — strictly worse than 28,
> because a gap invites work and a false pass silences review. **"Enforced by construction" is the
> same trap in a new costume.** It is the cheapest verdict to type and the hardest to falsify.
> An id is not classified (a) until a test that names it goes RED when the construct is removed,
> and that output is pasted. Anything less is (c).

### 0.5 DP-COV0 comes FIRST, and is not optional

Before any classification: **build the coverage gate.** The 60% above is a number I measured once by
hand; a number nothing re-measures is `NV-1` and this run would be standing on it for 60 turns.

`scripts/dp-invariant-coverage-gate.py` must:

1. Parse the declared id set out of `06_data_plane/*.md` (do not enumerate it in the gate — a list
   is default-uncovered; a doc added tomorrow must be in scope).
2. Walk `crates/`, the migrations, and `scripts/`+`lints/` for citations, and report **TWO
   tiers**, because §C asks for two things: *"cited **at the enforcement site** and **in a proving
   test**"*.
   - **sited** — the id appears in a non-test code/SQL/gate file.
   - **proven** — the id appears in a **test**: a `#[test]`/`#[cfg(test)]` block, a file under
     `tests/`, or a gate's `--self-test`.
   An id that is *sited* but not *proven* is the `// TODO(DP-Ch7)` case: traceable to a file,
   guarded by nothing. **The ratchet targets `proven`**, because that is the tier that cannot be
   satisfied by a comment.

   > **CORRECTION, 2026-08-13 — §0.5 originally said to STRIP COMMENTS and count only code.** That
   > was wrong, and wrong in a way that would have inverted this whole run: the repo's convention
   > *is* a comment naming the id beside the guard (`INV-KAL`, `INV-T2`, every `DP-` citation in
   > `crates/`). A comment-stripped walk would have scored the convention itself as zero coverage
   > and sent me to "fix" 84 invariants that were already cited correctly. The rule I was importing
   > — *a comment is not a mechanism* — is about a comment **claimed as the enforcement**, which is
   > a different thing from a comment **pointing at** enforcement. Two tiers keep both truths.
   > See `DPD-2`.
3. Carry a **reach floor**: zero declared ids, or zero files walked, is **exit 2 misuse**, never a
   pass. A walk that reaches nothing is byte-identical to full coverage.
4. Ratchet the uncited count **in both directions**, per family.
5. Ship a `--self-test` whose every arm is bitten before the gate is used for anything.

**Bite it before trusting it.** The gate is the instrument; an uncalibrated instrument makes the
whole run unfalsifiable.

### 0.6 Per batch, in order

1. State the invariant in one sentence, **from the doc**, not from memory.
2. Grep for its subject — the type, the table, the column, the function.
3. Classify (a)/(b)/(c). **Measure before writing anything.**
4. Mechanise the classification.
5. **Bite it**: GREEN → mutate ONE side → genuine RED → restore **byte-exact** → GREEN. Paste it.
6. Lower the ratchet by the number closed, with the reason recorded here.

### 0.7 Hazards — these have all bitten this project

- Run any sweep **DETACHED** and read the process's **REAL** exit code, never a task notification's
  (the notification fires for the launcher).
- **Edit nothing while a sweep or bite harness runs.** If one is killed, verify by hand that no
  mutation was stranded before doing anything else.
- Run the bite harness with `--gate`/`--only`, never the whole table, while iterating.
- **Byte-level I/O** for anything a shell executes. `Path.write_text` rewrote a whole file to CRLF
  once and cost four bite arms their anchors.
- **Never restore a bite with `git checkout`.** Restore from the bytes you read.
- Bite `want` strings are **case-sensitive**.
- **Never hand bash an absolute Windows path** — backslashes are eaten, `rc=127`. Repo-relative.
- **Never use a heredoc for a patch containing backslashes.** It ate `\\n` and `\.` four times in one
  session. Write the patch script with the Write tool instead.
- A non-ASCII byte in a `b"..."` literal is a `SyntaxError`. Escape it.
- Use `-F <file>` for commit messages.
- `cargo test --workspace` needs **`-j 4`** on this machine; the default dies with
  `STATUS_COMMITMENT_LIMIT` — environmental, not a code defect.
- `set -euo pipefail` kills a script at a failing command substitution **before a guard below can
  speak**. This defeated a reach floor twice, including once in the case written for that floor.
- A board edit uses an **asserted anchor** (`assert count == 1`), never a bare `str.replace`.

### 0.8 Do not stop

A batch finishing, a commit, a green sweep, an empty turn, a `POST-REVIEW` — **none is a stop
condition**. If an invariant genuinely cannot be classified, record it in `§4` with what would
settle it, and move on. **Commit and push after each batch; report at most once per batch.**

### 0.9 DONE

All of the following, or 60 turns, whichever comes first:

- [ ] `DP-COV0`, `DP-A`, `DP-R`, `DP-Ch1`, `DP-Ch2` all closed, **with their bites pasted**
- [ ] `dp-invariant-coverage-gate` green at the new measured number, ratchet lowered with reasons
- [ ] `--list` shows no uncited invariant except rows tracked in `§4` **that carry a mechanism**
- [ ] `cargo test --workspace -j 4` — **real exit code pasted**
- [ ] a detached `python scripts/gate-wiring-gate.py --run-all` — **real exit code pasted**

> **Claiming a check passed without pasting its output does NOT satisfy this condition.** The `/goal`
> evaluator reads the transcript and cannot run commands; it enforces persistence, not honesty. The
> proof has to be *in* the transcript.

---

## 1 · THE BOARD

| batch | subject | ids | state |
|---|---|---|---|
| `DP-COV0` | the coverage gate itself, bitten | — | ✅ **CLOSED.** `scripts/dp-invariant-coverage-gate.py`: 84 declared parsed from headings, 4397 files walked, two tiers (`sited`/`proven`), phantom rule + 2 shrink arms, 2 reach floors, per-family ratchet in both directions. **20 self-test cases, 13 mutations, all red.** Wired via the `--run-all` runner; `gate-teeth-gate` now 100/100 |
| `DP-A` | access-pattern invariants | `A2` `A3` `A4` `A8` `A11` `A18` `A19` (7) | ⬜ |
| ~~`DP-R`~~ | rule invariants | ~~`R9` `R10`~~ | ✅ **CLOSED BEFORE IT STARTED — the batch was a mirage.** Both ids are non-declarations (`DPD-1`), and one names a rule the tier REJECTED. `DP-R` measures 8 declared / 1 uncited, and that one — `DP-R7` — is the INVERSE case: **proven but not sited**. It has a test (`crates/dp/tests/spec_oracle_rules.rs`) and no citation at its enforcement site, so you can find its proof and not its guard. Folded into `DP-A`'s batch |
| `DP-Ch1` | channel primitives, first half | `Ch3` `Ch6` `Ch7` `Ch8` `Ch10` `Ch14` `Ch15` `Ch19` `Ch20` `Ch23` `Ch25` `Ch27` `Ch29` (13) | ⬜ |
| `DP-Ch2` | channel primitives, second half | `Ch30` `Ch36` `Ch39` `Ch40` `Ch43` `Ch44` `Ch45` `Ch46` `Ch47` `Ch48` `Ch49` `Ch50` (12) | ⬜ |

`DP-Ch` is 25 of the 34 and is split for that reason. If the family turns out to be mostly (a) in
SQL, it closes fast; if not, it is the bulk of this run.

---

## 2 · CARRIED IN — known non-invariant gaps in this tier

Not this run's subject, recorded so they are not rediscovered as news:

| id | what | source |
|---|---|---|
| `FLOW-19` | `channel_writer_state` has no FK to `channels`; **the first row-writer is still ahead** — the tables are live, the write path is not exercised | reality-layer `§`register |
| `W6-OWNER-UNVALIDATED` | nothing checks `owner_user_id` names a real user. Conscious, admin-only; **explicitly not acceptable once users request their own realities** | reality-layer `§`register |
| `GUARDRAIL-UNWIRED` | `contracts/canon/guardrail_rules.yaml` has **zero production call sites**; blocked on the L3 event write path | standards index §B |

---

## 3 · CLOSED

*(nothing yet)*

---

## 4 · OPEN ROWS — each must carry a MECHANISM, not prose

| id | what | mechanism / what would settle it |
|---|---|---|

---

## 5 · DRIFT REGISTER

**A run that ends with an empty drift log is not clean — it is dishonest.** Record the near-misses:
the arm that came back green, the anchor that drifted, the classification taken back.

| id | what happened |
|---|---|
| `DPD-6` | **The standards index under-states the channel family by 16 ids.** §F says `DP-Ch1–Ch37`; `06_data_plane/` declares `DP-Ch1..Ch53`. The index is the file CLAUDE.md sends every agent to for *what governs this change*, so a short range reads as *"Ch38+ is ungoverned"* — and Ch38+ is where 12 of this run's 25 uncited channel ids live. Found by `phase0-reconcile-gate` refusing this file's first commit, which is the gate working exactly as designed. **Deliberately not fixed inside a plan file**; amending a standard is its own change. |
| `DPD-5b` | A near-miss inside the Phase 0 look itself: I grepped `lints/dp-clippy/libs/` for the `forbid_*` lints the index claims, found only a compiled `.dll`, and was one sentence from recording *"the index claims clippy enforcement that does not exist"*. They exist, in `src/lib.rs`. **The claim I nearly made about a stale index would itself have been the stale claim.** |
| `DPD-5` | **The gate's own DOCUMENTATION was coverage, and three layers hid it.** `DP-Ch7` appeared in the module docstring as an example of a weak citation — and it is a real declared id, so any file containing that string cites it. Self-exclusion hid it from the ORIGINAL, but `gate-bite-harness` runs a **copy under a different filename**, which does not match `SELF`. So the original measured `DP-Ch` uncited = 25 and every mutant measured 24; each mutant then emitted a spurious PROGRESS finding that reddened the self-test **regardless of the mutated rule**, and three ratchet arms survived on the difference. Fixed at the root — examples use a reserved `9000` range that cannot be declared — plus a case asserting **this file names no real invariant**. Self-exclusion stays; it must simply not be the only thing standing between the gate and its own prose. |
| `DPD-4` | **The gate certified three real invariants off its own test fixtures.** `--list` showed `DP-A1`/`A2`/`A3` as `sited|proven`, sourced to the gate, because its self-test writes `## DP-A1` into synthetic files and the walk covers `scripts/`. `gate-self-tests.discover()` carries the identical exclusion for the identical reason. Found by READING the inventory, not by the bite — 13 mutations were green over it. Corrected: sited 54→51, proven 41→37, and `DP-A` uncited 5→**7**, which is what my hand count said before the gate existed. |
| `DPD-3` | An arm survived because **one case reached only one of two branches**: the unproven ratchet's case set the baseline to `real + 1`, driving the PROGRESS branch, so disabling `if unp > base_unp` changed nothing. The uncited pair had both directions; its twin did not. Fixed the case, added the missing row. |
| `DPD-2b` | A heredoc ate a backslash **again** — the fifth time — mangling a multi-line string into a `SyntaxError`. It is on this file's own hazard list. Patch scripts get written with a file, not a heredoc, without exception. |
| `DPD-1` | **The first measurement corrected the premise.** My hand count said 86 declared / 34 uncited. Measured by heading, **84 are declared** — `DP-R9` and `DP-R10` are not invariants at all. They occur twice: as *placeholders in a numbering instruction* (`11_access_pattern_rules.md`: *"A new stable ID `DP-R9`, `DP-R10`, … is assigned"*), and in `99_open_questions.md`, which records that a proposed `DP-R9` was **REJECTED** (G4a). So one of the two ids I had queued as work is a rule the tier deliberately refused — citing it in code would be a defect, not coverage. **`DP-R` is 8/8 and its batch is empty.** This is why the gate is built before the classifications and not after: the number the whole run hangs on was wrong on turn one, by exactly the amount a human eye misses. |
| `DPD-2` | **§0.5 was wrong when written, and it is binding, so it is corrected in place rather than worked around.** It told the gate to strip comments and count only code — but this repo's citation convention *is* a comment beside the guard. A comment-stripped walk would have reported near-zero coverage and sent this run to "fix" invariants that were already cited to standard. The rule being misapplied (*a comment is not a mechanism*) is about a comment claimed **as** the enforcement, not a comment **pointing at** it. Replaced with two tiers, `sited` and `proven`, which is what §C actually asks for. |
