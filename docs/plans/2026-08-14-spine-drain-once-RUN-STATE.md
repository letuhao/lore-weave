# `DFO-7` — `spine --drain-once` DOES NOT DRAIN ONCE — RUN-STATE

**Opened 2026-08-14** · branch `feat/game-logic` · opened at HEAD `c28d1ae67` · size **M**
(files 4 · logic 3 · side-effects 0)

**Adopts** [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md) §0.6d as
its execution contract, and §0.6's hazards (detached sweeps, real exit codes, no heredoc for a patch
carrying backslashes, byte-level I/O, asserted anchors on every board edit).

**Reconciles:** Non-Vacuity — the fix ships with a check that can fail, and the bite is pasted ·
Debugging Protocol — no fix without root cause, and the cause was proven at the protocol level
before a line changed · Performance Standard — *"timeouts all-languages"* is exactly the rule this
violated, and **its gate does not reach the violation**: `timeout-discipline-lint.sh` scans Rust for
`reqwest` without a timeout and knows nothing about an unbounded Redis read (`NV-3`, the scope never
reaches it). Recorded rather than glossed; not built here, because the boundary below excludes it
and `read_options()` now makes the mistake unavailable at the one place the value becomes a command.
Its trigger is a SECOND bus implementation appearing.

The look also asked whether the same defect exists in the siblings — this repo's recurring shape —
and for once it does not: `game-server/src/rooms/ChannelRoom.ts:117` already omits `BLOCK` via a
ternary on `blockMs`, and the Go rail defaults `CONSUMER_BLOCK` to `2s`
(`meta-worker/cmd/meta-worker/main.go:418`). The Rust rail was the outlier.

---

## §0.2 BOUNDARY — what this run may touch

**IN:** the semantics of `BusConfig::block_ms` and the one call site that passes `0`; a regression
check for it; a live drive of the `spine` BINARY with `--drain-once`.

**OUT:** the proposal bus's 250/2000 ms values (they are correct and unrelated) · `DFO-6`'s
per-suite database runner · `DP-X2`'s two unbuilt Redis roles · anything on the BOOK_TO_GAME
authoring track (`G-S3`/`G-S4` remain parked by the PO) · combat and progression, which have no
complete design.

---

## §1 ROOT CAUSE — found before any fix, and proven at the protocol level

`epoch_signal::connect_signal_bus` builds the binding-signal rail with `block_ms: 0`, under a doc
comment that states the intent in as many words:

> `block_ms: 0` NEVER blocks. The proposal fetch already owns the loop's latency; blocking here
> would add this timeout to every idle iteration for a stream that is empty almost always.

`BusConfig`'s own field doc agrees: `/// XREADGROUP BLOCK milliseconds (0 = don't block).`

**Both are false.** `services/commit-service/src/bus.rs` passed the value straight to
`StreamReadOptions::block`, and redis-rs 0.27.6 stores it as `Option<usize>` and writes `BLOCK
<ms>` whenever that option is `Some` (its `ToRedisArgs for StreamReadOptions` impl, in the vendored
crate rather than this tree — read at
`~/.cargo/registry/src/index.crates.io-*/redis-0.27.6/src/streams.rs`). So `0` becomes a literal
`BLOCK 0`. In the Redis stream protocol `BLOCK 0` means **wait indefinitely**; the way to not block
is to omit the argument entirely, which is what `None` does.

Measured against the live `infra-redis-1`, on an empty group, with nothing else changed:

```text
--- BLOCK 0 on an empty stream, 5s patience ---
BLOCK0_RC=124
--- no BLOCK arg at all ---

NOBLOCK_RC=0
```

`124` is `timeout`'s kill. The two commands differ in the presence of the argument and in nothing
else.

**Why that stops the whole binary.** `drain_and_reconcile` is the FIRST statement in the spine's
loop body — deliberately, so an epoch switch is reconciled before the batch it would re-validate —
and its first statement is `signals.fetch()`. The stream it reads is `lw.meta.events`, which the
module's own doc describes as *"empty almost always"*. So on a normal start the spine blocks
forever on iteration one, **before it ever reads a proposal**, and `--drain-once` can never reach
its `break`.

This is why the hang was measured identically at `HEAD` with the entire data-foundation change
stashed (`HEAD_RC=124`): it predates that work and has nothing to do with it.

### The shape

A comment asserting a behaviour that the code does the opposite of, in a codebase where the value
is passed through one function that documents the same falsehood. Neither doc was checked against
the protocol. It is `NV`'s *escape-hatch-cannot-reach-its-reason* cousin: the intent was written
down, was correct, and was never once executed.

---

## §2 THE FIX, and why this one and not the other one

Two repairs were available:

1. **Give the signal bus a small non-zero timeout.** Rejected: it makes the comment's stated cost
   real — every idle iteration of the spine would pay that timeout for a stream that is almost
   always empty, which is exactly what the author wrote `0` to avoid.
2. **Make `block_ms == 0` mean what both docs already say it means** — omit the argument. Chosen.
   It repairs the code to match the intent rather than rewriting the intent to match the bug, and
   `0` is the only value in the tree that changes behaviour (`grep`: one call site).

---

## §3 BOARD

| slice | state | evidence |
|---|---|---|
| `S1` root cause proven at the protocol level | `[x]` | `BLOCK0_RC=124` / `NOBLOCK_RC=0`, §1 |
| `S2` a check that reds on the bug, with no stack at all | `[x]` | RED on the literal wire args — see below |
| `S3` the fix | `[x]` | 3/3 green; `block_ms 0` emits no `BLOCK` |
| `S4` the BINARY drains once and EXITS | `[x]` | `DRAIN_RC=0` → `MUTANT_RC=124` → `RESTORED_RC=0` |
| `S5` suite green; the smoke is repeatable, not a transcript | `[x]` | `SUITE_RC=0`, 583/0 across 47 suites |
| `S6` the sweep is green, and the two it turned RED were both mine | `[x]` | `SD-5` + `SD-6`, each fixed at root and bitten |

### `S2` — the RED, and what makes it non-vacuous

`BusConfig::read_options()` is EXTRACTED so the check reads the same construction
`ProposalBus::fetch` issues, rather than rebuilding the options itself. A test that rebuilt them
would be a second copy of the decision — and watching the copy with no defect is exactly how
`DFO-8` stayed green through the previous run.

Against the unfixed code the failure prints the bytes that were going on the wire:

```text
running 3 tests
test bus::read_options_tests::the_group_and_count_survive_both_ways ... ok
test bus::read_options_tests::a_real_timeout_is_still_sent ... ok
test bus::read_options_tests::block_ms_zero_does_not_put_block_on_the_wire ... FAILED

block_ms 0 must emit no BLOCK argument at all — `BLOCK 0` blocks FOREVER, which is
the DFO-7 hang. Got: ["GROUP", "g", "c", "BLOCK", "0", "COUNT", "8"]

test result: FAILED. 2 passed; 1 failed
RED_RC=101
```

and after the fix, `test result: ok. 3 passed; 0 failed` (`GREEN_RC=0`). The second arm —
`a_real_timeout_is_still_sent` — is why this is non-vacuous in BOTH directions: a "fix" that simply
stopped emitting `BLOCK` would satisfy the first arm and turn the 250 ms proposal rail into a hot
spin at 100% CPU.

### `S4` — the six-step bite, on the BINARY

Two throwaway databases, migrated; a reality and a channel seeded; two entries waiting on the
proposals stream. Every run below is the assembled `spine.exe`, not a component.

```text
=== messages ARE waiting — the exact DFO-7 condition ===
epoch signals: lw.meta.events as epoch-signal:7e57ab1e-…:ch1
REJECT-COMMIT [schema] 1786673024696-0 → channel_event_id 1 (turn stays 0) — missing field `producer_service`
REJECT-COMMIT [decision-vocabulary] 1786673025069-0 → channel_event_id 2 (turn stays 0) — tool '' is not in the closed vocabulary

== spine report ==
consumed  : 2
rejected  : 2 (schema/dedup/vocabulary — acked, recorded)
pel depth : 0
DRAIN_RC=0
```

Then the bug goes back in — ONE side, `read_options` returning to an unconditional `.block()`:

```text
MUTANT: .block(block_ms) is unconditional again; sha256=7a8d57784b0724c9
=== MUTANT, message waiting, 60s patience ===
epoch signals: lw.meta.events as epoch-signal:7e57ab1e-…:ch1
MUTANT_RC=124
```

**`124`, and the last line it printed is the last line `DFO-7` recorded** — *"epoch signals:
lw.meta.events …"*, verbatim. The reproduction matches the report exactly.

Restored byte-exact, with a FRESH mtime (`shutil.copy2` would preserve the old one and cargo would
re-run the MUTANT binary while sha256 reported byte-exact — that is `DFD-2`, measured last run):

```text
RESTORED byte-exact; sha256=37624693494487fa; mtime stamped fresh
REJECT-COMMIT [schema] 1786673123180-0 → channel_event_id 3 — missing field `producer_service`
consumed  : 1
RESTORED_RC=0
```

The entry the mutant consumed but never acked was **redelivered from the PEL** to the restored run.
That was not designed for and is worth recording: a killed writer's at-least-once discipline held
across the bite.

### `S5` — the smoke is a mechanism, and it was bitten too

`scripts/smoke/spine-drain-once.sh` provisions both databases, applies both migration sets, checks
the four tables the binary needs, and runs
`services/commit-service/tests/spine_drain_once_live.rs`, which spawns `spine` and requires it to
terminate. Bitten as a unit:

```text
GREEN    test the_spine_binary_drains_once_and_exits ... ok        finished in 0.76s
MUTANT   `spine --drain-once` did not exit within 90s — this is DFO-7
         test result: FAILED. 0 passed; 1 failed                   finished in 90.45s
RESTORED test the_spine_binary_drains_once_and_exits ... ok        finished in 0.76s
```

**It is not measuring nothing at 0.76s**: the driven binary left `1` reality row in the meta DB and
**`proposal.rejected | 2`** in the channel DB. And with no stack it does not pass quietly —

```text
SKIP the_spine_binary_drains_once_and_exits — set SPINE_SMOKE_META_TEST_DATABASE_URL,
SPINE_SMOKE_CHANNEL_TEST_DATABASE_URL and SPINE_SMOKE_REDIS_URL, or run scripts/smoke/spine-drain-once.sh
```

**Stated limit.** The smoke drives the REJECTION path only; the resolution path has its own live
coverage and this test is about the loop terminating. Two per-reality migrations do not apply on a
stock postgres image (`0006_projections`, `0008_pgvector_setup` — the pgvector library is absent,
`DFO-6`'s cause (a)); the script REPORTS them rather than swallowing them, and the spine path
touches nothing they create.

## §4 OPEN

| row | what |
|---|---|
| — | none. `DFO-7` is closed; `DFO-6` and the two unbuilt `DP-X2` Redis roles remain in the data-foundation run-state, untouched by this run |

## §5 DRIFT — append as it happens; an empty log is dishonest, not clean

| id | what |
|---|---|
| `SD-5` | **The repo's most-cited standard had no row in its own index.** `phase0-reconcile-gate` refused this run-state for citing `Non-Vacuity` — correctly: of 128 index rows, none had it as a first cell. It appears in the quick-nav table keyed by *concern* (*"a gate, lint, test, `const` assertion…"*) and in a callout, but it was **not registered**, so the gate that exists to catch a citation pointing at nothing was pointing every author away from `NV`. LOCKED in CLAUDE.md, second in Key Rules, 46 gates enforcing it, no row. Added (now 129), and the row says when and why. |
| `SD-6` | **`meta-write-discipline-lint` knew Go's test convention and not Rust's.** Its exclusion list carried `_test\.(go|rs|ts)` — which is how GO spells a test. Rust integration tests are `<crate>/tests/*.rs`, a directory cargo compiles as test targets and nothing else, so the new smoke's fixture was judged as production code writing a meta table unaudited. **Latent, not benign**: it stayed quiet only because no Rust integration test had ever seeded a meta table before. `NV-3`, the scope never reaches it — and the arms that existed tested the MATCHER, so nothing covered the filter chain at all. Fixed by FACTORING the chain into `exclude_nonsubject()` (the self-test now exercises the same function the walk uses, not a retyped copy — `DFO-8`'s lesson) and adding three arms: a `src/` write is still reported · a `tests/*.rs` one is not · a `src/tests_helper.rs` is still reported. Bitten by widening the pattern to any path containing `tests`: `selftest: a src/ file merely NAMED tests_* was excluded` → `SELFTEST FAIL`, `BITE_RC=2`; restored byte-exact, `RESTORE_RC=0`. |
| `SD-7` | **Hazard #5, hit again, in the file where I had written it down.** A heredoc carrying a Python string that ended in a backslash was a `SyntaxError`, and because the shell chained on, the NEXT command still printed `SELFTEST PASS` and `BITE_RC=0` — a bite that never ran, reporting exactly what a passing bite reports. Caught only because the mutation message was missing from the output. **Every patch since has gone through the Write tool.** |
| `SD-8` | Incidental, unfixed, and named rather than left as a surprise: `.claude/worktrees/` holds **6.3 GB** of stale agent worktrees, untracked, with only three specific names in `.gitignore` and not the `agent-*` pattern. They also pollute repo-wide greps — one search in this run returned five hits from them before any real file. Flagged for the human rather than deleted: it is their disk, and the ignore rule is their call. |
| `SD-1` | **I nearly shipped the unit test alone.** It guards the root cause and runs with no stack, which is genuinely the stronger guard — and it would have left `DFO-7`'s actual complaint unanswered, because the row is not *"the argument is wrong"*, it is *"nothing exercises the binary"*. A check that reds on today's cause is not the same as a check that reds on tomorrow's block. Both shipped. |
| `SD-2` | **Four setup failures were each read as the next symptom, and none of them was.** Wrong password, a missing `session_registry`, a missing `channels` table, a missing channel ROW — four errors in a row from the binary, each of which could have been mistaken for *"the fix did not work"*. What kept it honest was that the messages were specific. `DFO-8`'s lesson last run was the same one from the other side: the reason was in memory and the program printed only a count. |
| `SD-3` | **`0.76s` looked like a skip and I nearly recorded it as a pass.** A live test that skips returns `ok` exactly like one that runs. Verified by reading the rows the driven binary wrote (`proposal.rejected | 2`) rather than trusting the word `ok` — and the skip path was then run deliberately to confirm it announces itself. |
| `SD-4` | Two migrations do not apply on this box and I recorded them rather than let the loop swallow them. The first draft of the script used `&&` chaining that would have hidden a NEW failure among the two expected ones. |
