# RUN-STATE — the reality layer: give reality creation a home process

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3**, Foundation Invariants **I1–I19**, User Boundaries & Tenancy, Locked Decisions ledger, Data Plane channels **DP-Ch1–Ch37**

*(That line is required by `scripts/phase0-reconcile-gate.py`, which refused the first commit of this
file — the gate I widened to cover `docs/plans/` two days ago, doing its job on its author. Prior art
opened before writing: `06_data_plane/05_control_plane_spec.md`, `migrations/meta/001_reality_registry`,
`world-service/src/{provisioner,provisioner_live,capacity_glue,capacity_planner}.rs`.)*

**Opened 2026-08-08 at `9bb0f149b`.** Supersedes
[`2026-08-06-game-tier-build-RUN-STATE.md`](2026-08-06-game-tier-build-RUN-STATE.md) as the ACTIVE
file. That one is retained as the RECORD (2438 lines: the actor hub, the command substrate,
`crates/dp` slices 0–1b, and `BDR-1`..`BDR-48`) — **read it when you need a decision's history, not
to find out what to do next.**

---

## 0 · HOW TO WORK — read this before touching anything

These are not aspirations. Each one is a measured failure from the run that ended at `9bb0f149b`,
and following them would have saved most of a session.

### 0.1 · Investigate before you assume. The document AND the source.

The single largest cost last run was designing and verifying against a mental model instead of the
tree. **Before any design, build, or claim:**

```
grep/read the LOCKED docs that already model it      ← docs/standards/README.md is the index
grep/read the SOURCE that already implements it      ← the code is the fact; the doc is the claim
run the query that says whether it EXISTS            ← one command beats an hour of reasoning
```

`scripts/phase0-reconcile-gate.py` enforces the first for new specs. Nothing enforces the second —
that one is on you.

### 0.2 · Cheapest question first, and it is almost always "does this exist?"

The decisive query last run was `SELECT count(*) FROM pg_database WHERE datname LIKE 'reality%'` →
**0**. It was one command away for an entire session and was run last, after two pushes from the PO.
Four refutation rounds hardened a migration for a database type that had never been instantiated.

**Order: does it EXIST → does anything RUN it → who OWNS it → is it CORRECT.** Verifying correctness
of a component no path exercises is slow, finds problems one at a time, and cannot tell you which
parts are worth verifying at all. (`BDR-47`)

### 0.3 · "Blocked" means EXTERNAL. Everything else is unbuilt work.

`CLAUDE.md`, LOCKED: *"'Missing infrastructure' is NOT 'blocked' — it is unbuilt work to implement…
Saying 'blocked' when you mean 'I'd have to build it' is the lazy tell this rule exists to kill."*

Last run five items were called blockers and permission was requested for all five. Every one was
writable in this repo; three were built within one turn of the PO saying *"we don't have blocker"*,
and the first reality in the project's history existed. **The label was the only thing blocking.**
(`BDR-48`)

⇒ Before writing "blocked", answer: *can I write this in this repo?* If yes, it is a task.

### 0.4 · Do not hunt for data belonging to an unbuilt feature.

Three tool calls last run went to querying live databases for rows of `npc_session_memory_embedding`
— a projection for **NPC session memory**, part of the unbuilt MMO track. Of course it had no data.
**The question was never "does it have rows", it was "does this feature exist".**

### 0.5 · A drill proves a mechanism. It is not the product.

`provision-drill` hardcoded credentials for a different test rig and builds its **own** capacity
snapshot instead of reading `shard_utilization`, so it never exercises `capacity_glue`. It proved
provisioning works; it is not how a reality gets created.

### 0.6 · Escapes that cost real time last run

- **Heredocs eat backslashes.** `\b`, `\n`, `\u{74}` and `\\n` were all corrupted, once producing a
  **vacuous gate rule** that could never fire. Use the Edit/Write tools, or a scratchpad file, for
  anything containing a backslash. `cat -A` reveals it.
- **A fix without a leg is a fix the next edit removes.** Five mutations of a "fixed" migration
  stayed green; three silently reverted the fixes. *"I verified it live"* ≠ *"the suite would
  notice."* (`BDR-44`)
- **Do not run two suites against one throwaway DB name.** Contamination presents as a schema defect.
  Per-pid suffixes everywhere.

---

## 1 · MEASURED STATE — 2026-08-08, each with the command that produced it

Re-measure rather than trust this table if more than a session has passed.

| fact | value | command |
|---|---|---|
| realities in existence | **2** (was 1; `W3`'s worker made the second) | `psql -d loreweave_meta -tAc "SELECT count(*) FROM reality_registry"` |
| a reality's database | `lw_reality_cd0747d24b94`, **12 tables** — ~~13~~, a miscount in the first draft of this table, corrected 2026-08-08 when the second reality's schema was diffed against it and matched exactly | `SELECT count(*) FROM pg_tables WHERE schemaname='public'` |
| its migration ledger | **15 applied** | `SELECT count(*) FROM schema_migrations` |
| `channels` in a real reality | **exists, holds a root row, `REC-106` refuses a self-parent** | `SELECT to_regclass('public.channels')` |
| meta database | **exists**, 28 tables, 35 migrations | `psql -d loreweave_meta` |
| registered shards | **1** — `pg-shard-0.internal`, cap 50 | `SELECT * FROM shard_utilization` |
| meta bridge | **up, healthy, :8090** | `docker compose ps meta-bridge` |
| `world-service` server binary | **none serving** — `src/main.rs` exists but is a 22-line `println!` scaffold; the 7 real bins are workers/drills | `ls services/world-service/src/bin/`; `cat src/main.rs` |
| admin command surface | **33 commands, live and dispatched**, 10 domain registries | `go run ./cmd/admin --list` |
| a command that CREATES a reality | **`reality provision`**, shipped by `W3` (was: none — all 8 `reality` commands required one to exist) | `--list` |
| admin issuance on the dev stack | **was disabled** (`POST /internal/admin/token` → 404, no signing key). `W3` enabled it; the key lives in the operator's env, **not** the repo — regenerate + `export ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM=<base64 PKCS#8>` then `docker compose up -d auth-service` | `curl -o /dev/null -w '%{http_code}' -XPOST …/internal/admin/token` |
| game-tier services in compose | `game-server` only; `world-service`, `commit-service` absent | `grep -c "^  <svc>:" infra/docker-compose.yml` |
| Postgres login roles | **1**, `loreweave`, `rolsuper` + `rolbypassrls` | `SELECT rolname, rolsuper FROM pg_roles WHERE rolcanlogin` |

---

## 2 · DEFINITION OF DONE — unchanged, and it is the reason the above is trustworthy

A row closes only when **all three** hold, with the evidence pasted into the transcript.

| axis | question | what does NOT count |
|---|---|---|
| **CODE** | Does it hold without running? | inspection alone; "it compiles" |
| **RUN** | Did the real path execute? | mocks, fixtures, a drill standing in for a service, `#[cfg(test)]` consumers |
| **DATA** | Did it produce the contract-defined result? | "no error", logs, exit codes, code shape |

Every measurement states **what result would falsify PASS**.

**`V.1` — an independent cold-start refuter**, worktree-isolated against a COMMIT (`BDR-35`), briefed
to assume the work is wrong. Four rounds ran last phase; **all four returned BLOCK and all four were
right**, the fourth finding that two of the third's fixes were regressions. Budget for this.

**`V.2` — a mechanical oracle by a DIFFERENT method** than the thing it checks.

---

## 3 · THE BOARD

| # | row | state |
|---|---|---|
| `W1` | shard registration as cold config (`pg-shard-0.internal`, cap 50) | ✅ `31a57842b` |
| `W2` | meta database + `meta-bridge` in compose (the `I8` write path) | ✅ `9dcb2dea9`, `31a57842b` |
| `W4` | first reality provisioned end to end | ✅ `dd1d98b4e` |
| **`W3`** | **`reality provision` — an admin COMMAND, and a real provision worker behind it** | ✅ see evidence below |
| `W5` | `orphan_scanner` owns the abandoned half-provision | ⬜ |
| `W6` | `owner_user_id` on `reality_registry` — ownership exists before users can request | ⬜ decision + migration |
| `W7` | a `CREATEDB`-only system role; stop provisioning as superuser | ⬜ |
| `W8` | capacity: make the real path read `shard_utilization` (the drill fakes its snapshot) | ⬜ **subsumed by `W3`** |

### `W3` — RESHAPED 2026-08-08 by Phase 0, and this is why the phase exists

**This row said "`world-service` gains a server binary + an admin-routed provision endpoint."
That was written from a mental model — *services expose HTTP* — and the tree says otherwise.**
What an audit of the actual admin surface found, before a line was written:

| measured | command |
|---|---|
| `services/admin-cli` exists, **33 commands live and dispatched** | `go run ./cmd/admin --list` |
| a per-domain command registry, **10 domains** | `ls contracts/admin/registry/` |
| the framework enforces **admin-JWT + scope-per-tier, impact class, dry-run gate, dual-actor (second actor's OWN token), typed confirmation, reason, audit Before/After/Failure** | `internal/framework/dispatcher.go` |
| an un-wired destructive command **refuses to report success** | `NotWiredHandler`, PRR-05 |
| `admin_action_audit` exists in the live meta DB | `\dt` in `loreweave_meta` |
| admin→Rust seam is **subprocess, not HTTP** — `SubprocessRebuildInvoker` execs the `rebuilder` binary | `rebuild_projection_pg.go:115` |
| **HTTP calls in admin-cli: zero** | `grep -rn "http.NewRequest\|http.Post" services/admin-cli` |
| the `reality` domain has **8 commands, every one of which needs a reality that already exists** | `--list` |

⇒ **The gap is not a missing server. It is a missing command.** Nothing in this platform can
*create* a reality; the eight that exist can only freeze, thaw, close, rebuild and report one.

⇒ Had I built the endpoint, I would have re-implemented audit, dry-run, dual approval and typed
confirmation — badly. My first instinct was `require_internal` (a shared service token), which
carries **no actor identity at all**, against a framework that already binds every action to a
signed admin principal. `SUBJECT BEFORE APPARATUS` cuts both ways: build the subject the existing
apparatus is shaped for.

**IS:** `reality provision` in `contracts/admin/registry/reality.yaml`, dispatched by the existing
framework, whose handler execs a **real** `provision` worker binary in `world-service`.

**Impact class — `tier-2-griefing` (`admin:write`), `dry_run_required: true`.** It destroys nothing
(so not tier-1), but it consumes a finite shard slot every other reality shares — which is what
tier-2 names, and it is the class `reality capacity-override` already carries for the same reason.
Dry-run is a per-COMMAND field in the dispatcher (`c.DryRunRequired`), not a per-tier one, so a
tier-2 command can require it; provisioning is exactly where a "which shard, how full, then commit"
preview earns its keep (R13 §12L.5).

**`W8` is subsumed.** The drill hardcodes `used_realities: 0, total_realities: 100`. A real worker
has no business faking a capacity snapshot when `capacity_glue::live_snapshot` + `place_reality`
(advisory-locked, recount-under-lock) already exist and nothing calls them on the real path. Doing
`W3` correctly closes `W8` by construction rather than leaving a second row to fake it later.

### `W3` — evidence (three axes, 2026-08-08)

**CODE.** 20 new Go tests green; full admin-cli suite green; `world-service` **139 passed, 0
failed**; `admin-command-registry-lint` **PASS, 34 handlers**; `migration-manifest-gate`,
`db-safety-gate`, `ai-provider-gate` all OK.
**10/10 bites RED** via `scripts/provision-command-bite-harness.py` — every guard proved
load-bearing (blank `db_name`, no-capacity dry run, nil invoker, `reality_id` mismatch, exit-2
mapping, inherited child env, unforwarded `--dry-run`, env-validated-before-exec, cohort range,
nil UUID). Two vacuity defects were found and fixed *by* biting, not by review:
- `TestProvisionInvoker_DryRunFlagReachesWorker` **could not fail** — the fake worker chose its
  branch from the mode channel, so it never observed `--dry-run` at all. It now asserts on ARGV.
- the child-env bite first went red through a **build failure**, which proves the compiler works
  and nothing else. Rewritten as a compilable mutation; the harness now *reports* a build-failure
  red as `[WEAK]` instead of counting it.

**LIVE RUN.** The real `admin` binary, a real RS256 admin JWT minted by the running auth-service
for an active `admin_principals` row, no dev tokens, audit sink on the real meta DB:
```
reality c9143a8b-a19e-4a5c-8fca-f669e09f6998 provisioned on shard pg-shard-0.internal
as database lw_reality_c9143a8ba19e (11 steps, locale=en, cohort=0).
```
Enabling this required turning on admin issuance (`ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM`, base64
single-line — the signer accepts that form for exactly this reason); it was **404/disabled** on the
dev stack, i.e. no admin command had ever run audited here.

**DATA**, each read back independently:

| checked | result |
|---|---|
| `admin_action_audit` | 4 rows — `started`+`dry_run`, `started`+`success` — `actor_id` = the real principal `019d5e3c…`, `tier-2-griefing` |
| `reality_registry` | `active | pg-shard-0.internal | lw_reality_c9143a8ba19e` |
| `meta_write_audit` (I8) | **3** rows for this reality (register + 2 transitions) |
| per-reality DB | **12 tables, 15 migrations**, schema identical to the `W4` reality |
| `I4` isolation | `datacl = {=T/loreweave,…}` — PUBLIC holds `T` only, **not** `c` |
| `REC-106` | a self-parent insert is refused: `Key (reality_id, parent, parent_depth)=(…,42,0) is not present` |
| capacity | `used` moved 1 → 2 → 3 across the run; the dry run reported `2/50` and an independent SQL oracle agreed exactly |
| dry-run is inert | 0 registry rows, 0 databases created for the dry-run uuid |

**A defect the DATA axis caught that a green exit code hid:** the first admin-path dry run printed
`on shard ` — empty. The Rust key had been renamed `chosen_shard`→`shard` and the binary never
rebuilt, so Go parsed a field that was not there. Exit code 0 throughout. **Reading the output is
the check; the exit code is not.**

**IS NOT:** the user-facing request pipeline. A user *requests*; that request runs manifest ingest
and more, and it binds `book → lore bible → pre-manifest stub → manifest → reality`. Two of those
stages are undesigned and one is not a named artifact. **Engine first** — you cannot offer a manifest
builder without knowing what the engine supports. See
[`2026-08-08-book-to-reality-pipeline-index.md`](../specs/2026-08-08-book-to-reality-pipeline-index.md).

**The seam:** `W3`'s endpoint is where the request pipeline will later attach. Record the seam; do
not implement toward it.

---

## 4 · OPEN, each with a trigger

| id | what | trigger |
|---|---|---|
| `FLOW-19` | `channel_writer_state` has no FK to `channels` | `flow19_trigger()` in `dp-channels-schema-gate` reds when `channels` gains a non-test writer. `W3` did NOT create one — it creates the *table*, per migration; the first row-writer is still ahead |
| `W3-DEVKEY` | the dev stack's admin signing key is operator-env only, so `reality provision` reverts to unaudited-refused after a fresh clone | a second person needing to run an admin command here, or CI wanting one. Do **not** commit a key; a bootstrap script that generates one is the fix |
| `W3-LOCKSPAN` | the advisory lock is held across the WHOLE 11-step provision (incl. migrations), not just through `register_pending` at step 3 | provisioning becoming frequent enough that per-shard serialisation hurts. Deliberate: correctness over throughput on an admin-gated action |
| `1b7db-03` | `loreweave` is the sole Postgres login and is superuser | `W7`. Not a tenancy mechanism — DB roles are system roles, users never hold one |
| `1b14-07` | `metadata` JSONB / `display_name` / `dissolved_at` unconstrained | the first writer of `channels` |
| `1b7db-08` | `CREATE TABLE … INHERITS (channels)` bypasses constraints | conscious won't-fix; a non-SDK writer appearing |
| `1b7db-11` | `channels_id_positive` constrains an unwritten `reality_root` derivation | its first implementation |
| `G-S3`/`G-S4` | lore bible has no schema; "pre-manifest stub" is not a named artifact | the BOOK_TO_GAME track |
| slice 1 | `G3`/`G4`/`G6`–`G13` open; several need `dp-clippy` | `2026-08-06` run-state §6i |
| slice 2 | Phase 0 done (`2F-1`..`2F-4`); board not written. `DP-R3` names a clippy lint with **no dylint/`clippy_utils`/`rustc_private` anywhere** | a DESIGN decision before BUILD |

## 5 · REGISTERS

Decisions, parked, debt and **`BDR-1`..`BDR-48`** live in
[`2026-08-06-game-tier-build-RUN-STATE.md` §7](2026-08-06-game-tier-build-RUN-STATE.md). Append new
drift there or here; **a run that ends with an empty drift log is not clean, it is dishonest.**

The five that governed last run, so they are not re-learned:
`BDR-44` a fix without a leg · `BDR-45` a fix's blast radius ≠ its subject · `BDR-46` knowing a rule
does not transfer across a language boundary · `BDR-47` execute the path before verifying its parts ·
`BDR-48` "blocked" is a label, and it was the only blocker.

**`BDR-49` (2026-08-08) — I wrote a board row from a mental model, and the row survived a
compaction, a goal, and a hand-off before anything checked it.** `W3` said *"world-service gains a
server binary + an admin-routed provision endpoint"* — reasonable-sounding, and wrong: this repo
drives admin operations through `admin-cli` + a subprocess seam, with a governance layer (scope,
dry-run, dual-actor, typed confirm, audit) I would otherwise have rebuilt by hand, starting from a
shared token with no actor identity. **The cost of the error was zero only because Phase 0 ran
before the first line of code.** Note what did *not* catch it: not the goal, not the run-state,
not the QC pillars — all three would have happily verified a well-built endpoint nobody should
have built. **Three-axis DoD proves a thing works; only Phase 0 asks whether it should exist.**
Same shape as `BDR-47` (execute before verifying) one level up: **audit before building.**
