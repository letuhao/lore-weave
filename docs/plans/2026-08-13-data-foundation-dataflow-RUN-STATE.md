# RUN-STATE — the data foundation: make one real thing flow through it

**Opened 2026-08-13** · branch `feat/game-logic` · opened at HEAD `718c29fc9`

**Reconciles:** SDK-First · Per-service DB ownership / no cross-DB FK · Performance Standard ·
User Boundaries & Tenancy ·
A gate, lint, test, `const` assertion, validator, or an axiom that constrains code — and the audit that opened this file found the thing all
five govern is **built as a contract and has no data in it**, measured at HEAD:

* `crates/dp` is 3,655 lines with one runtime dependency (`uuid`) and **declares no I/O by design**.
  It exposes **6** of the ~20 primitives `06_data_plane/01 §2.4` names.
* **Production call sites of any tier primitive, outside `crates/dp`: ZERO.** The only `t2_write`
  in the tree is inside `dp-kernel/src/dp_backend.rs`'s own `#[cfg(test)]`.
* The one production backend pair — `KernelWriteBackend` / `KernelReadBackend` — has **zero
  consumers outside the file that defines it**.
* The two services that depend on `dp` (`commit-service`, `world-service`) use it **only** for
  `RealityId` / `SessionContext::bind`. Neither touches the data path.
* `§2.4` says *"Direct Redis access for T0–T2 reads and cache."* **`redis` appears in exactly one
  Cargo.toml in the Rust tree — `services/commit-service`** — for the proposal bus and a ceilings
  bin. **Zero DP crates.** The only `impl Cache` anywhere is `InMemoryCache` in `meta-rs`.
* `dp:events:*` (`DP-Ch17`) still has **0 producers**; `spec_oracle_channels.rs` holds the asserted
  trigger that reds the day it arrives.
* The control plane declares **14 RPCs and 8 return `UNIMPLEMENTED`** — six of them because
  `tier_policy`, `npc_binding` and `schema_version` **have no migration in this repo**.

**This is the actor hub's own failure shape one layer down** — 91 tests, zero consumers — with the
tests to match. `scripts/orphan-model-gate.py` exists because of it. A coverage gate reporting
**84/84 sited** over a surface with zero production callers is the most expensive way this repo has
found to feel finished.

> This file is the commitment. `/goal` holds the session open; **this file holds the work.**
> After any compaction, re-read `§0` FIRST, then `git log`, then continue.

---

## 0 · HOW TO WORK — BINDING

### 0.1 The execution contract

Adopts **§0.6d of [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md)**
unchanged — the execution invariant, the source-of-truth rule, the six-step row-completion contract,
and the non-negotiable hazards. That file also holds §0.6c (sealed forks) and §5
(`BDR-57`..`BDR-90`). Read it before the first batch.

### 0.2 🔴 THE BOUNDARY — this section is the point of this file

The last four days drifted, measured: two tracks measured the tree (`gate-teeth`, `dp-coverage`) and
two left the tier entirely (`authorable-surface`, `lore-bible`). **The PO stated the objective on
2026-08-13:**

> *"the main purpose is build data plane, foundation and wire actor hub, control feature and build
> player feature to consume it, a full dataflow, but seem like we cross the line, there are no
> combat, progression feature yet because they are not complete design yet"*

**IN SCOPE — and nothing else is:** the data-plane foundation, the control plane it needs, the actor
hub wired to it, and one player-facing feature consuming the result end to end.

**OUT OF SCOPE. Each of these is a drift row if it is started, not a judgement call:**

| ⛔ | why |
|---|---|
| **combat** — any rule, tuning surface, or table whose subject is combat | **not completely designed** (PO, 2026-08-13) |
| **progression** — `progression_kinds`, XP, tiers, advancement | **not completely designed** (PO, 2026-08-13) |
| **the lore bible / `G-S3` / `G-S4` / BOOK_TO_GAME** | different track — the authoring pipeline, upstream of the manifest. Parked: [`2026-08-14-lore-bible-RUN-STATE.md`](2026-08-14-lore-bible-RUN-STATE.md) |
| **a new gate whose subject is another gate** | `gate-teeth` closed at baseline ZERO. Measuring the tree is not building the spine |
| **a new coverage/measurement instrument** | unless a board row below needs it as *its own* acceptance evidence, and the row says so |
| **a document as a deliverable** | a schema something validates against and a byte that reaches a store are deliverables. Prose is not |

**The test before starting anything:** *does a byte move through the SDK because of this?* If no,
it is not this run's work — record it in `§4` and move to the next row.

### 0.3 The ordering, and why it is forced

`DF1` first, and it is the smallest row on the board on purpose. Every other row is an
*improvement to a path nothing walks*. A Redis cache for T0–T2 that no caller reads is the same
finding as the one that opened this file, arriving faster. **One real caller first — it is the
measurement that stops this happening again, and it will reveal what is actually missing.**

### 0.4 Per batch, in order

1. State what is being built in one sentence, **from the document**, not from memory.
2. Measure the subject before writing anything.
3. Build the smallest thing that is real.
4. **Bite it**: GREEN → mutate ONE side → genuine RED → restore **byte-exact** → GREEN. Paste it.
5. Update this board with the evidence string.

### 0.5 A STRING THAT LOOKS LIKE A SUBJECT IS NOT THE SUBJECT

The lesson of the three runs before this one, five separate instances: a word in an unrelated
README · a symbol inside the oracle that counts it at zero · a `DetRng` from another crate · a doc
comment saying *"unbuilt"* · a document's own filename. Each read as evidence something exists.

- Measure **existence** in code with comments **stripped**.
- Measure **citation** with comments **counted**.
- Never conflate them, and say which one a check is doing.

**Any new gate ships a `--self-test` AND mutation rows in `gate-bite-harness` in the same commit.**

### 0.6 Hazards — every one of these has bitten

- Run any sweep **DETACHED**; read the process's **REAL** exit code, never a task notification's.
- **Never run two `gate-wiring-gate --run-all` sweeps concurrently** (`BDR-53`). A refusal is exit 2
  — that is failure evidence, not a pass.
- **Edit nothing while a sweep runs.**
- **Byte-level I/O**, and read CRLF **from the bytes** rather than assuming it.
- **NEVER use a heredoc for a patch containing backslashes** — it ate them **seven times** in one
  session. Write the patch to a file with the Write tool.
- **Never hand bash an absolute Windows path.** Repo-relative.
- `-F <file>` for commit messages. `cargo test --workspace` needs **`-j 4`**.
- Every board edit uses an **asserted anchor** (`assert count == 1`), never a bare `str.replace`.

### 0.7 Do not stop

A batch finishing, a commit, a green sweep and an empty turn are **not** stop conditions. If
something genuinely cannot be built, record it in `§4` with what would settle it and move on.
**Commit and push after each batch; report at most once per batch.**

### 0.8 DONE

All of the following, or 45 turns, whichever comes first:

- [ ] `DF1` closed — a **production** call site of a DP tier primitive exists, ran live, and the
      resulting row is **pasted from Postgres** (not from a test double)
- [ ] `DF2` closed — `tier_policy` / `schema_version` / `npc_binding` migrated; the RPCs that
      cited them **answer for real**, and `UNIMPLEMENTED_METHODS` shrinks with the test still green
- [ ] `DF3` closed — a Redis-backed cache the SDK reads through for T0–T2, with a **measured**
      read latency pasted against the `03_tier_taxonomy` budget
- [ ] `DF4` closed — every module touching kernel state carries a `DP-R2` tier table, and something
      **machine-checks** that it does
- [ ] `DF5` closed — the end-to-end dataflow: one player-facing action → actor hub → DP write →
      projection → wire, **with the ids and payload pasted at each hop**
- [ ] `cargo test --workspace -j 4` — **real exit code pasted**
- [ ] detached `gate-wiring-gate --run-all` — **real exit code pasted**

> **Claiming a check passed without pasting its output does NOT satisfy this condition.** The
> `/goal` evaluator reads the transcript and cannot run commands; it enforces persistence, not
> honesty.

---

## 1 · THE BOARD

| batch | subject | state |
|---|---|---|
| `DF1` | **one real caller.** `commit-service` writes one aggregate through `dp::t2_write` → `KernelWriteBackend` → event store, on a live stack. The SDK becomes a door instead of a diagram | ⬜ |
| `DF2` | **the control plane's three missing tables** — `tier_policy` (`DP-C4`), `schema_version` + `npc_binding` (`DP-C2`). Unblocks 6 of the 8 dead RPCs | ⬜ |
| `DF3` | **the T0–T2 cache.** `§2.4`'s "direct Redis access" — zero DP crates have it today, so every tier collapses to the durable path and the taxonomy is a comment | ⬜ |
| `DF4` | **`DP-R2` tier tables per module** — the PO's *"data instance for each module"*, owed by every feature doc and paid by none | ⬜ |
| `DF5` | **the full dataflow** — actor hub + a control feature + a player feature consuming it, end to end | ⬜ |

`DF1` is deliberately the smallest. See `§0.3` for why the order is forced rather than chosen.

---

## 2 · CARRIED IN

| id | what | source |
|---|---|---|
| `DPD-6` | the standards index says `DP-Ch1–Ch37`; the docs declare `Ch1..Ch53`. **16 ids read as ungoverned** in the file CLAUDE.md sends every agent to. Amending a standard is its own change | data-plane coverage run-state §5 |
| `M2` residue | `VerbTable`/`VerbDecl` shipped in `ruleset-core`, and `engine_default.toml` declares **zero verbs** (87 lines, `verb` occurs 0×). The substrate has no rows | this audit |
| `LB0` finding | `lore-enrichment-service` (252 files) already ships the corpus sweep `G-S3` was going to rebuild. Worth keeping when that track reopens | parked lore-bible run-state |

---

## 3 · CLOSED

*(nothing yet)*

---

## 4 · OPEN ROWS — each must carry a MECHANISM, not prose

| id | what | mechanism / what would settle it |
|---|---|---|

---

## 5 · DRIFT REGISTER

**A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| `DFD-1` | **The four days before this file drifted, and no mechanism noticed.** `gate-teeth` and `dp-coverage` were meta-work on the verification layer; `authorable-surface` was the manifest tier; `lore-bible` left the tier entirely and started mapping output onto `progression_kinds` and combat — **features the PO had not finished designing**. Each track individually justified itself, each updated its own board, and nothing held the objective. The `Reconciles:` gate checks that a spec *looked* at the standards index; **no gate asks whether the work is the work that was asked for.** §0.2 is a file, not a gate, and that is a known weaker mechanism — recorded here rather than claimed as solved. |
