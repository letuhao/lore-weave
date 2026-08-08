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

### 0.6b · DO NOT ASK FOR PERMISSION TO CONTINUE (standing, PO 2026-08-09)

**The PO has delegated continuation. A question whose only possible answer is
*"keep going"* is a wasted turn — it costs a round trip and returns no
information.** The instruction, verbatim: *"the plan should be fully defined in
the runstate … stop asking something that I only answer as keep going/continue,
it useless ask and answer."*

So:

- **Never end a turn on a status report that waits.** Finish the row, then start
  the next row in the same turn.
- **Never ask which of two options to take when this file can decide it.** If a
  fork appears and is not sealed below, *seal it here* — write the call, the
  reason, and the trigger that would reverse it — and then act on it. A decision
  recorded in this file is worth more than a decision confirmed in chat, because
  the next session can read it.
- **Never ask for a size/scope blessing.** §0.3 already says missing
  infrastructure is unbuilt work, not a blocker.

**The three things that still stop the run**, unchanged and exhaustive:

1. an action that is **destructive or irreversible** outside the repo (dropping a
   real database, force-pushing, sending something outward);
2. a **sealed decision turning out to be wrong** — re-read it before saying so;
3. the PO's own **POST-REVIEW checkpoint** at a shippable risk boundary, which is
   a presentation, not a question.

**Anything else: park it in the register and keep moving.** A row that cannot be
finished becomes a `⬜ parked` line with what would unblock it, and the run
continues at the next row. *Blocked ≠ stopped* (§0.3).

### 0.6c · The forks that are SEALED, so nobody re-asks them

Each of these came up, was decided on evidence, and is closed. Re-opening one
needs a new fact, not a new opinion.

| fork | sealed call | reversal trigger |
|---|---|---|
| **`3E` adoption of `RealityId` across 880 sites** | **A RATCHET, never a big bang.** A baseline file records the count of bare `reality_id` sites per crate; a gate fails on an increase, and on a decrease that the baseline did not record — the exact shape `contracts/dp/dp-clippy-baseline.json` already proves in this repo. An 880-site single commit is unreviewable and unbisectable. | the count falls below ~50, at which point one commit is reviewable |
| **`DpError` variant set** | **Doc-driven, oracle-enforced.** `DP-K3` is the SSOT; `spec_oracle.rs` compares. Never hand-curate the list. | `DP-K3` itself is amended |
| **`3D`'s control-plane verification** | **A TRAIT in `crates/dp`, implemented in slice 5.** `crates/dp` declares no I/O, so it declares the seam and slice 5's `DpControlPlane` satisfies it. The trait ships **with its first implementor**, not before — a trait whose only impl is its own test double is the orphan shape. | — |
| **new types with crate-private constructors** | **Land WITH their producer, never before.** Proven by `3C`: `RealityId` was written, tested, and reverted because `new_verified` had no in-crate caller. `#[allow(dead_code)]` is not an option — it is the pragma-as-exemption shape. | — |
| **a `DP-R3` finding in a crate that is not game-layer** | **Not debt — out of scope.** `01_scope_and_boundary.md` §4 scopes by the DATABASE. Mark `plane = "platform"` with a reason; the gate refuses the claim from any crate addressing a per-reality DB. | §4 is amended |
| **anything the spec names that has no producer** | **Do not ship it.** Record it in a deferred register that a gate reads. | its producer arrives |

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
| realities in existence | **7** (was 0 at session start) | `psql -d loreweave_meta -tAc "SELECT count(*) FROM reality_registry"` |
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
| Postgres login roles | **3** — `loreweave` (`rolsuper`+`rolbypassrls`), **`loreweave_provisioner`** (`CREATEDB` only, `W7`), `w1p_foreign` (a drill fixture) | `SELECT rolname, rolsuper, rolcreatedb FROM pg_roles WHERE rolcanlogin` |

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
| `W5` | `orphan_scanner` owns the abandoned half-provision | ✅ **detection**; remediation needs a bridge endpoint (below) |
| `W6` | `owner_user_id` on `reality_registry` — ownership exists before users can request | ✅ column **and its producer**, live both tiers |
| `W7` | a `CREATEDB`-only system role; stop provisioning as superuser | ✅ `loreweave_provisioner`, live |
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

**Correction (2026-08-08, `V.1` finding H2): `dry_run_required` does not require a dry run.**
`dry_run.EnforceGate` is `if !dryRun && !confirm { refuse }` — an OR — and nothing records that a
dry run ever happened, so the ordering the registry schema described is unenforceable. `--confirm`
alone proceeds straight to execution; **verified live**, not just read. The field means "no flagless
invocation", nothing more. I took the field name at face value and repeated its own documentation's
claim; the schema comment is now corrected at source. Tracked as `W3-DRYRUN-MISNOMER` — it affects
all twelve commands carrying the flag, not just this one.

**`W8` is subsumed.** The drill hardcodes `used_realities: 0, total_realities: 100`. A real worker
has no business faking a capacity snapshot when `capacity_glue::live_snapshot` + `place_reality`
(advisory-locked, recount-under-lock) already exist and nothing calls them on the real path. Doing
`W3` correctly closes `W8` by construction rather than leaving a second row to fake it later.

### `W3` — evidence (three axes, 2026-08-08)

> ### ⚠ `V.1` returned **BLOCK** on `925b0e300` — 3 HIGH, 7 MEDIUM, 7 LOW
>
> The fifth cold-start round on this project, and the fifth to be right. It found **one real bug**
> and, more usefully, **three defects in the verification apparatus below** — including in the
> paragraph that claimed ten guards were load-bearing. Fixes and their evidence: [§3 · `W3` — the
> refutation](#w3--the-refutation-and-what-it-cost) below. **The evidence in this section is the
> PRE-refutation record; read the refutation before trusting any of it.**

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

### `W3` — the refutation, and what it cost

`V.1` ran cold-start against `925b0e300` in an isolated worktree, briefed to assume the work wrong.
**BLOCK.** Every HIGH is fixed and re-verified below.

**`H1` — a retry could put the database on a different shard than the registry names.** The bug is
real and it is mine. `bridge.go:47` documents its own idempotency: a retried `register-reality`
carrying a *different* `db_host` still returns 200 and **is not diffed** — justified by *"the single
V1 caller (the provisioner) always retries the same intent, so this is safe."* That held for
`provision-drill`, which hardcoded its shard. `W3` invalidated it by choosing a shard from **live
capacity on every invocation**: a run that dies after step 3 leaves `provisioning` on shard A, and
the retry sees A one-fuller, picks **B**, gets `already_registered` (which `provisioner.rs:252`
records as `skipped` and continues past), then creates the database and 15 migrations on B. Registry
says A, database lives on B, command prints success. Every consumer resolves its DSN from `db_host`.

*Fix:* the worker now **reads `reality_registry` before placing**. A row exists ⇒ its shard is
authoritative, placement is skipped entirely (the slot was claimed by the first attempt; re-claiming
it would double-count capacity), and a settled status is a no-op rather than a re-provision.
*Reproduced and verified:* registered a second, **emptier** shard (`pg-shard-1.internal`, 0/50 vs
shard-0 at 4/50) so a re-pick would certainly move — then ran the worker against a half-provisioned
row. It resumed on **shard-0**, the database landed on **shard-0**, and `pg-shard-1.internal` ended
with **0 rows**. Without the fix the planner picks least-full, which was shard-1.

**`H3` — the flagship bite was red for the wrong reason, and two of its three assertions could not
fail.** `TestProvisionInvoker_ChildEnvIsNotInherited` asserted on an error string the invoker
**truncates to 256 bytes**. `V.1` measured the child's env dump at 4242 bytes intact and 12907
broken; the two assertions naming the property read a window those strings could never reach, so
they passed identically either way, and the bite went red only because appending pushed an unrelated
substring past byte 256. **A red produced by a truncation artifact is not evidence** — and the
harness's `[WEAK]` detector only recognised build failures, so it certified this as `[RED]` and this
document reported *"10/10 — every guard proved load-bearing."* That claim was false for this guard.
*Fix:* the fake worker now computes the verdict itself and answers in one short field, so the
assertion is on parsed output and length-independent. Note what the bite must catch is **not** a
changed `PROVISION_*` value — `append(os.Environ(), env...)` puts the explicit vars last and last
wins — but the **presence** of variables the invoker never passed.

**`H2` — `dry_run_required` does not require a dry run.** See the corrected impact-class note above.

**The MEDIUMs, all fixed:** `M1` no timeout anywhere — a hung worker or one waiting on the
per-shard advisory lock blocked the admin command forever; now a 30-minute bound (matching
`catastrophic-rebuild`) plus `statement_timeout` on the **meta pool only**, which is what converts
an unbounded `pg_advisory_lock` wait into a legible error (the shard and migration pools must not
carry it — a long migration is legitimate). `M2` **no blank-`Shard` guard** — the commit narrates
finding exactly that defect live and fixed the *cause* (a renamed key) without adding the *guard*;
now guarded in both modes, with "no capacity" diagnosed first because that outcome legitimately
names no shard. `M3` a comment cited `tests/provision_worker.rs::dry_run_db_name_matches_provisioner`
— **a test that does not exist, in a file that does not exist** — to vouch that a hand-copied
`db_name` rule matched the provisioner's; fixed by deleting the copy and making `db_name_for`
public, so there is one implementation and nothing to drift. `M4` the Rust half had **zero tests**;
now 11. `M5` the bite harness **was wired into nothing** — it proved its guards once, on my machine;
now a CI job. `M6` the "BCP-47" check was `len > 35` reporting *"is not a BCP-47 tag"*; now an actual
subtag check with tests.

**What this round says about the method.** The three-axis DoD passed `W3` cleanly — CODE, LIVE RUN
and DATA were all genuinely green — and the work still carried a split-brain bug and three broken
checks. `V.1` is not a formality on top of the axes; **it is the only thing that read the apparatus
itself.** `BDR-50`.

### `W7` — provisioning no longer runs as superuser

`loreweave` is `rolsuper` **and** `rolbypassrls`, and every reality was created with it: the most
privileged credential in the platform, used for its most routine automated write. Superuser is
exactly what RLS, table ownership and per-database GRANTs cannot restrain, so a bug in the
provisioner had the whole cluster in reach — including every other tenant's database.

Provisioning actually needs **one attribute: `CREATEDB`.** The role that creates a database owns it,
so it can `REVOKE CONNECT` (I4) and create tables (the migrations) with no further grant.

**The one thing that genuinely required superuser was `CREATE EXTENSION vector`** in migration
`0008` — pgvector's control file does **not** declare `trusted` (verified by reading it), so
installing it is superuser-only, and that single line would have kept provisioning privileged.
Fixed by installing `vector` into **`template1`**: every `CREATE DATABASE` copies it, so
`CREATE EXTENSION IF NOT EXISTS` becomes a no-op any role can run. Preferred over marking the
extension trusted — this changes one cluster's template, not an extension's privilege rules.

**Not a per-user role.** Postgres roles are SYSTEM roles; users never hold one (`1b7db-03`, and the
PO's correction). This is one service credential, identical for every tenant. User-level tenancy is
`reality_registry.owner_*` (`W6`), enforced in the application.

**Live:** provisioned as `loreweave_provisioner` — 12 tables, 15 migrations, `vector 0.8.1`
inherited, database `datdba = loreweave_provisioner`, `datacl = {=T/…}` so I4 still holds — then
again through the **full audited admin path** with an owner.

**Bitten — it genuinely lacks what it gave up:**

| attempt | result |
|---|---|
| `UPDATE reality_registry` directly | **permission denied** — I8 is now enforced by privilege, not convention: the bridge is the only door |
| `SELECT FROM users` in `loreweave_auth` | **permission denied** |
| `CREATE ROLE … SUPERUSER` | **permission denied**, no `CREATEROLE` — no escalation path |
| `SELECT FROM shard_utilization` (granted) | succeeds — the grant is real, so the refusals above are not a broken connection |

The attributes are **re-asserted on every start** (`ALTER ROLE … NOSUPERUSER …`), so a role
hand-edited to superuser loses the drift rather than keeping the name and losing the point.

**And then the role was apparatus without a subject, so the worker now REFUSES superuser.** Grepping
my own work found `loreweave_provisioner` named in exactly two places: the script that creates it
and this document. **Nothing pointed the worker at it** — only a shell env I had set by hand. The
committed configuration still let an operator provision as `loreweave`, and the natural credential
to reach for is the one every other service uses. A role that exists but is never *required* changes
nothing.

So `connect_shard_admin` reads `rolsuper` for `current_user` and refuses:
```
provision: NOTRUN(setup): refusing to provision as superuser loreweave: creating databases
with a role that holds rolsuper puts every other tenant's database in reach of a bug here.
```
Verified both directions live — superuser **exit 2**, `loreweave_provisioner` proceeds. The escape
hatch is `PROVISION_ALLOW_SUPERUSER_REASON` and takes a **reason, not a boolean**: a blank value is
refused, because a `=1` flag records that someone bypassed the check and never why, and outlives the
incident that justified it. The decision is a pure function with 4 unit tests, so the rule is
exercisable without a database — a rule reachable only through a live connection is one the suite
cannot check. *(`--dry-run` does not check: it never connects to the shard, so there is no shard
role to inspect.)*

### `W6` — a reality now belongs to someone

`reality_registry` had `close_initiated_by` and `drop_approved_by` — the ADMINS who acted on a
reality — and **nothing saying whose reality it is**. `owner_user_id` appeared in zero meta
migrations and no design doc specified reality ownership. The PO's decision was already on record:
*"user own their book, their reality"*, no role hierarchy.

**Two columns, not a nullable uuid.** A bare nullable owner makes `NULL` mean both *"the platform
owns this"* and *"nobody recorded an owner"* — states needing opposite responses. So the tier is
declared: `owner_kind ∈ {system, user}`, with `system ⟺ owner_user_id IS NULL`. Matches the
System/Per-user table in CLAUDE.md. **No FK** — `reality_registry` is in `loreweave_meta` and users
in `loreweave_auth`; Postgres cannot key across databases, which is why the existing actor columns
carry none either.

**Biting the constraints found a defect in my own first draft.** I wrote the rule as one
disjunction, which is correct — and which made the enum CHECK **unreachable**, because
`owner_kind='wizard'` fails both branches and the consistency constraint always fired first. That is
`NV-1`'s hardest shape: an adjacent decision defeating a check while both look individually right.
Rewritten as two **implications**, so an unknown kind satisfies both (false antecedents) and reaches
the enum. Each constraint now has a distinct, reachable job — **proven**, three violations naming
three different constraints:

```
owner_kind='wizard'      → reality_registry_owner_kind_enum
owner_kind='user'        → reality_registry_owner_user_set
owner_user_id=<a user>   → reality_registry_owner_system_null   (on a system row)
```

**The tier is derived at the bridge, from ONE field.** The client sends `owner_user_id` or omits it;
the server decides `owner_kind`. A client able to send both could send `('system', <a user>)` and
have the table's CHECK discover it at the *end* of provisioning rather than at its edge.

**LIVE, both tiers, through the audited admin command:**

| | `owner_kind` | `owner_user_id` |
|---|---|---|
| `--owner_user_id 019d5e3c…` | `user` | `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c` |
| omitted | `system` | `(null)` |

The **I8 audit records the ownership decision itself** — `after_values` carries `user /
019d5e3c…` and `system / (null)` respectively — so who a reality was provisioned for is
reconstructible, not just its current state. The tenancy query returns exactly that user's reality.
*(`EXPLAIN` shows a seq scan: the table has five rows, so Postgres correctly ignores the partial
index. That is a statement about the row count, not about the index.)*

### `W5` — the scanner can now see, and what it is NOT

`orphan_scanner` shipped in cycle 5 as a scaffold whose dry run classified `let scanned = 0u32` — an
empty set, forever — and whose real mode exited 2 with *"cycle 6 dependency"*. The dependency it
named (the MetaWrite RPC stack) has been up since `W2`, and `W3` finally gave the platform a
**producer**: a crash between `CREATE DATABASE` and the registry transition now leaves exactly the
states it was specified to find.

Classification is a **pure function** (`orphan_scan::classify`, 13 unit tests) so the rules are
provable without a database. Four classes; the third is the one nothing else can see:

| class | why |
|---|---|
| `StalledProvision` | stuck in `provisioning`/`seeding` past 24h — records **whether the database was created**, since the two halves need different remediation |
| `MissingDatabase` | the registry row claims a database that is not there |
| **`UntrackedDatabase`** | **a `lw_reality_*` database no row claims. `capacity_glue` counts REGISTRY ROWS, so this is invisible to the one component whose job is knowing how full a shard is** |
| `DropEligible` | `soft_deleted` past the 7-day grace — reported, not acted on |

**Live, and the untracked class demonstrated rather than asserted.** Clean shard → `findings:0`,
exit 0. Created a real orphan (`CREATE DATABASE lw_reality_w5probe0001`, no registry row) → the
scanner found it, exit 1. **With that database present, the provisioner's own capacity read still
reported `used: 3` while `SELECT count(*) … LIKE 'lw_reality_%'` returned `4`** — the blindness,
measured. Dropped the probe → back to `findings:0`, exit 0. Exit codes verified directly (`0`/`1`/
`2`), not through a pipe: **`1` = the shard is dirty and `2` = I never looked must never be one
signal.**

**IS NOT: remediation.** The scanner is READ-ONLY — it writes nothing and drops nothing. Marking an
orphan needs a `reality_close_audit` write through the bridge, and the bridge exposes only
`register-reality` and `transition`. `--remediate` therefore **REFUSES (exit 2)** rather than
silently no-op'ing, which is the `NotWiredHandler` posture applied to a binary.

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
| ~~`W5-REMEDIATE`~~ | **CLOSED.** `orphan_scanner --record` writes findings through a new bridge endpoint. **`reality_close_audit` turned out to be the WRONG sink** and R13 §12L has been wrong about it since migration 005: its `event_type` is a closed enum of six close-lifecycle values (no orphan class) and its `reality_id` is `NOT NULL`, which the untracked-database class by definition has none of. New table `orphan_scan_finding` (038), keyed by the database — the one field every class names | done |
| ~~`W5-CRON`~~ | **CLOSED.** An `orphan-scanner` compose service runs it hourly and records through the bridge. Deliberately NOT another cron-manifest YAML: `scripts/archive-worker-cron.yaml` says of itself that its scheduler binding is deferred, so it is a schedule nothing reads — the same apparatus-without-a-subject shape this row exists to kill | done |
| `W6-OWNER-UNVALIDATED` | **conscious decision, recorded because `V.1` found it undocumented.** Nothing checks that `owner_user_id` names a real user: there is no FK (cross-database), and neither the bridge nor the admin handler looks the user up. An admin CAN provision a reality owned by a UUID belonging to nobody. Acceptable for an admin-only tier-2 command where the operator supplies the id deliberately — **not** acceptable once users request their own | the user-facing request pipeline. It must resolve the owner from the authenticated caller, not from a typed parameter |
| `D-META-ERASURE-COVERAGE` | **4 open, down from a reported 8** — the first count asked *"does PgMetaScrubber handle it"* rather than *"does ANY mechanism"*, and three (`pii_kek`, `pii_registry`, `user_consent_ledger`) turned out fully handled by admin-cli's crypto-shred / revoke path; `user_queue_metrics` is now implemented. Open: `user_cost_ledger` + `user_daily_cost` declare `pseudonymize_user_ref_at_2y`, a TIME-based retention job that is unbuilt; **`session_cost_summary` and `service_to_service_audit` declare NO method at all — a PO call, not an engineering one** | `TestMetaMigrationsDeclareAnImplementedErasure` — three registers (`implemented` / `handledElsewhere` / `knownUnhandled`), each must shrink, and a NEW user-referencing meta table cannot be added without a row in one of them |
| `W7-SHELL-UNCOVERED` | four round-3-era fixes ship with **no test and no bite**: `infra/db-ensure.sh` (the injection fix itself), the 036/037 down-migration guards, the column-level GRANT, and the `main.go` nil-owner guard. The bite harness's `TARGETS` are Go/Rust files only | a shell-level bite harness, or the next change to `db-ensure.sh`. Recorded because the injection fix is the highest-severity change in this run and is verified only by hand |
| `META-DOWN-UNCOVERED` | `scripts/migration-idempotency-validator.sh` walks **only** `contracts/migrations/per_reality` — the same `NV-3` shape this run diagnosed twice. The 036/037 down migrations are exercised by nothing automated | pointing the validator at both trees; it is the meta-tree twin of the erasure-gate fix |
| `W6-ERASURE-EVENT` | `reality_registry` + `OpUpdate` maps to `reality.status.changed` in the allowlist, so the erasure reassign would emit a status-changed event carrying no status change. **Latent only** — `main.go` builds the MetaWrite config with no `Outbox`, so nothing fires today | wiring an Outbox into the meta-worker erasure path |
| `W7-TEMPLATE1` | the provisioner relies on `CREATE DATABASE`'s **implicit** `TEMPLATE template1` to inherit `vector`; a future `TEMPLATE template0` (the standard move for encoding control) silently returns provisioning to needing superuser. Also cluster-wide: every new database on this box now carries pgvector, and `infra/foundation-dev/` is a **second** cluster that never runs `db-ensure.sh` | anyone adding a TEMPLATE clause, or standing up the foundation-dev cluster for provisioning |
| `1b7db-03` | ~~`loreweave` is the sole Postgres login and is superuser~~ **CLEARED by `W7`** — provisioning runs as `loreweave_provisioner` (`CREATEDB` only). Other services still connect as `loreweave`; narrowing those is a separate, larger sweep | the next service touched |
| `1b14-07` | `metadata` JSONB / `display_name` / `dissolved_at` unconstrained | the first writer of `channels` |
| `1b7db-08` | `CREATE TABLE … INHERITS (channels)` bypasses constraints | conscious won't-fix; a non-SDK writer appearing |
| `1b7db-11` | `channels_id_positive` constrains an unwritten `reality_root` derivation | its first implementation |
| `G-S3`/`G-S4` | lore bible has no schema; "pre-manifest stub" is not a named artifact | the BOOK_TO_GAME track |
| slice 1 | `G3`/`G4`/`G6`–`G13` open; several need `dp-clippy` | `2026-08-06` run-state §6i |
| slice 2 | Phase 0 done (`2F-1`..`2F-4`); board not written. `DP-R3` names a clippy lint with **no dylint/`clippy_utils`/`rustc_private` anywhere** | a DESIGN decision before BUILD |

## 4b · SLICE 2 — `DP-R3`'s lint. Board written at the slice's start (`BDR-26`).

**The reality-layer board above is CLOSED.** This file now also carries the `crates/dp` slice work,
which is what that detour existed to unblock: `channels` and the migration chain were applied by
nothing because no reality had ever been instantiated, and seven now exist.

**Why slice 2 and not slice 3/4.** The PO chose to BUILD `dp-clippy` rather than retire it, and to
build the SDK first so the lints have a subject. Phase 0 then corrected the premise: **one of the
four lints already has a large subject.** `crate-purity-gate` covers only the four PURE crates
(`actor-hub`, `game-rules`, `ruleset-core`, `sim-core`) — which is why it is green — while `DP-R3`'s
scope is every crate WITHOUT a `dp-crate` marker, and there:

```
world-service 15 · roleplay-service 7 · commit-service 6
dp-kernel 4 · service-http 3 · meta-rs 2 · world-gen 1     = 47 files
```

`2F-1` recorded this and I under-read it: *"a mechanism whose subject exists before the mechanism
does"* — the opposite of the `pc_*`/`npc_*` orphan. So slice 2 ships **one** lint against a real
subject, and stands up the toolchain the other three will need.

### The board

| # | row | state |
|---|---|---|
| `2A` | **the dylint toolchain** — `dp-clippy` crate, pinned nightly, one CI leg | ✅ `8c4c13360` + the `dp-clippy` job below |
| `2B` | **`forbid_raw_kernel_client`** shipped **RED** against the 47 files | ✅ `8c4c13360` — **9 findings / 4 crates**, measured; see the count correction below |
| `2C` | **the `dp-crate = true` marker**, re-added WITH its reader (`V1-F12`: it was removed because a declared input with no consumer is the orphan shape) | ✅ and the reader is the LINT, not a companion gate — see below |
| `2D` | **`DP-R3`'s exemption amended** — `2F-2`: it locks *"any crate other than `dp` itself"*, which fires on `crates/dp-kernel`, **where the database code is supposed to live** (`event_store_pg.rs`, `outbox.rs`). The exemption must be the MARKER, not a name | ✅ marker-keyed; and `crates/dp` deliberately does NOT carry it |
| `2E` | **`roleplay-service`'s status** — `2F-4` | ✅ **ANSWERED BY MEASUREMENT, and it was never a PO call** — see below |
| `2F` | **the CI leg** — `scripts/dp-clippy-gate.py` + the `dp-clippy` job in `gates.yml` | ✅ ratchet with 5 bites, all fire |
| `2G` | **`service-http` migrates FIRST** — a red low-level crate makes its dependents UNLINTABLE | ✅ **but NOT by migrating it.** Phase 0 found it is out of `DP-R3`'s scope entirely |

#### `2E` and `2G` — Phase 0 dissolved both rows instead of doing them

The plan was *"migrate `service-http` off its 2 raw clients, then ask the PO about
`roleplay-service`"*. Neither turned out to be the work.

**`01_scope_and_boundary.md` §4 is LOCKED and scopes `DP-R3` by the DATABASE**, not by the
language or the directory: *"if a service reads or writes any aggregate in a per-reality database
(`reality_<id>_db`), it is a game-layer service and uses the DP SDK."* Measured against that:

| crate | what its Postgres actually is | verdict |
|---|---|---|
| `service-http` | `db::init` — its own module doc says *"the per-service-DB pattern … a normal **platform-plane** DB like `loreweave_chat`, **NOT** the kernel services' per-reality sidecar model"*; plus a `SELECT 1` liveness probe | **out of scope** |
| `roleplay-service` | `services/roleplay-service/src/main.rs:17` — `service_http::db::init(&config.database_url, sqlx::migrate!("./migrations"))`, its own migrations; `reality_id` is a column in a SELECT list and an `Option<Uuid>` on a model. Its package description already said *"single platform pool"* | **out of scope** |
| `meta-rs` | the META database — it records *where* realities live and never opens one | **out of scope** |
| `world-gen` | `shape_dispatch_cache`, a cache of LLM dispatch decisions | **out of scope** |
| `world-service`, `commit-service` | per-reality `events` / reality DBs | **IN scope — real debt** |

So **`2E` was answerable by looking**, and I had parked it as *"needs a PO decision"*. The row
itself said *"nobody has looked"*. That is the anti-laziness rule in `CLAUDE.md` — *"saying
'blocked' when you mean 'I'd have to build it'"* — in its other form: saying *"needs a decision"*
when you mean *"I'd have to read four files."*

**The exemption needed a second key, not a broader first one.** Marking those four
`dp-crate = true` would have put a FALSE claim in four manifests — they are not the data plane,
they are simply not on the game plane. So `[package.metadata.dp] plane = "platform"` exists
alongside it, and the gate refuses to take either on trust:

- a **written `reason`** ≥40 chars, in the exempted crate's own diff;
- a `platform` claim is **REFUSED from any crate that addresses a per-reality database**
  (`db_name`, `reality_db`), with `meta-rs` — which owns the registry column — named as the one
  exception. Measured non-comment hits: `world-service` 123 · `commit-service` 7 · `meta-rs` 3 ·
  `service-http`/`world-gen`/`roleplay-service` **0**. **The two crates that most need `DP-R3` are
  exactly the two the exemption will not let out.**

**Result: `0` unchecked.** `commit-service` became lintable and turned out to carry **3 findings
nothing had ever seen**. The red set is now `world-service` 5 + `commit-service` 3 — *precisely*
the two services `DPA-SCOPE` derived from the locked rule. The lint and the LOCKED document agree
without being made to.

#### The two guards that were dead when written, and what caught them

1. **The false-claim check had no subject.** Its first version matched routing *symbols*
   (`RealityRouting`, `reality_routing`) on my claim that *"exactly `world-service` consumes
   routing — that is what gives this check teeth"*. I had read a grep result without opening the
   file: `world-service`'s only mention is a **module doc comment** at
   `services/world-service/src/lib.rs:19`, which the
   check's own comment-stripper correctly removes. `world-service` claiming `plane = "platform"`
   walked straight past it. The gate still failed — on `BASELINE STALE`, an unrelated rule — which
   is exactly why the bite mattered: **a guard can be dead while the suite around it stays green.**
2. **`[package.metadata]` is invisible to cargo's fingerprint.** Cargo carries it for external
   tools and excludes it from a unit's fingerprint, so adding or removing an exemption marker does
   **not** dirty the crate: cargo replays the cached success, rustc never runs, the lint never
   fires, and a stale verdict is reported as a fresh one. Measured: `world-service` reported CLEAN
   in a workspace pass while a direct run on the same tree produced 5 findings. The same hole
   swallows the lint itself — rebuilding `dp_clippy` with different rules dirties nothing.
   **This was about to matter in CI**, where `Swatinem/rust-cache` persists the target directory
   across runs: a marker deleted in a PR could be judged against a cache built while it was still
   there. The gate now hashes what cargo ignores — every `[package.metadata.dp]` block plus the
   lint library's bytes — and wipes the dylint target tree when that digest moves.

#### `2C` — the marker's reader is the LINT, and the companion gate was a phantom

The lint shipped in `8c4c13360` with `const DP_CRATES: &[&str]` — four crate names — and a comment
saying `scripts/dp-crate-marker-gate.py` kept that list in agreement with the manifests. **That
script did not exist.** It is the same defect `V.1` round 1 caught as `M3` (a test cited in evidence
that was never written), committed by the author who had just fixed that one.

The fix was not to write the gate. A lint runs inside rustc and *appears* unable to read
`Cargo.toml` — but cargo puts `CARGO_MANIFEST_DIR` in the rustc process's environment, which is why
`env!("CARGO_MANIFEST_DIR")` works in ordinary code. Measured under `cargo dylint`: present, and
naming the crate being compiled. So the lint reads the real manifest, the name list is deleted, and
the two-lists-must-agree problem it needed a gate for **stops existing**.

`crates/dp-kernel` carries the marker. **`crates/dp` deliberately does not** — its `[dependencies]`
is empty and `S2.3`'s *"declares no I/O"* rests on that, so the one crate `DP-R3`'s prose exempts by
name is precisely the one that should stay covered. That is a narrowing of the rule, recorded in
the manifest itself.

**The self-test leg was passing for the wrong reason.** `fixtures/dp_kernel` carried the marker AND
was named `dp_kernel`, and the lint keyed on the name — so the manifest key was decoration and
deleting it would have reddened nothing. `fixtures/unmarked` is now its twin: same package name,
byte-identical source, no marker. Legs 3+4 are a differential, so the marker is the subject.

#### `2F` — three vacuity traps, each MEASURED on this repo

1. **`cargo dylint --all` exits 0 when it loads no lint.** Measured: hide the library and it prints
   `Warning: No libraries were found.` and returns **0**. Every way of getting the name, path,
   toolchain or build wrong therefore produces a *green* run that linted nothing. `run-lint.sh` now
   calls `cargo dylint list` and refuses (exit 2) unless `dp_clippy` is loaded.
2. **The runner hardcoded a Windows target triple.** `TOOLCHAIN="…-x86_64-pc-windows-msvc"` — the
   host of the machine it was written on. On the Linux CI runner this leg was about to be added to,
   the library would have been named for a toolchain that was not running. Combined with (1) that is
   a permanently green CI leg enforcing nothing. Now derived from `rustup show active-toolchain`.
3. **A single `--workspace` pass silently omits crates.** Measured: it reported 3 red crates;
   linting `services/world-service` alone produced **5 more findings**, in a workspace member that
   was in the selection. The gate now requires every member to be positively accounted for — a
   finding or a compiler artifact — and re-lints any that are not. `world-service: 5` is in the
   baseline *only* because of that check.

**And the finding that reorders the work (`2G`).** Two members are `UNCHECKED` and cannot be fixed
by trying harder: `roleplay-service` and `commit-service` depend on `service-http`, which **fails to
compile because the lint reds it**. A crate that does not compile cannot have its dependents linted,
so a red low-level crate hides every finding above it. Both hold raw clients
(`roleplay-service/src/state.rs:11`), so the true count is **≥9 and unknowable** until `service-http`
is migrated. The baseline records them in a `blocked` register that names the blocker, and the gate
fails when that blocker goes clean — an excuse with an expiry date rather than a quiet exemption.

### What "shipped RED" means, and why it is the point

The lint lands **failing** against real code, and CI carries it as a ratcheted baseline rather than
green-by-emptiness. A lint that is green on the day it ships is a lint whose subject you have not
found yet — and this repo has four instances this session of exactly that. The red is the evidence
the rule bites; migrating those crates off raw clients is the work it then drives.

**Correcting the figure this section used to quote.** "47 files" was a *grep* count of files
mentioning `sqlx::`/`redis::` anywhere, across `crates/` **and** `services/`. It is not what the
lint reports and was never a violation count. What the lint actually measures, per crate, on the
workspace:

| | |
|---|---|
| **9 findings across 4 crates** | `world-service` 5 · `service-http` 2 · `meta-rs` 1 · `world-gen` 1 |
| **2 crates unlintable** | `roleplay-service`, `commit-service` — blocked by `service-http` (`2G`) |
| **1 crate exempt** | `dp-kernel`, by marker |

The gap between 47 and 9 is mostly `use` sites the rule does not name (`PgPoolOptions`, `Row`,
`redis::AsyncCommands`) and files inside crates counted once by the lint. Quoting the grep number
as if it were the violation count is the kind of figure that reads as rigour and measures nothing —
the ratchet in `contracts/dp/dp-clippy-baseline.json` is the number that moves.

---

## 4b · SLICE 3 — board, written at the slice's start (`BDR-26`)

Sealed scope: **`RealityId` + `SessionContext`**. Phase 0 changed how it is
approached, twice, before a line shipped.

| # | row | state |
|---|---|---|
| `3A` | **`DpError` (`DP-K3`)** — the settled enum slice 1 named as its own missing prerequisite | ✅ 17 variants + a doc-parsing oracle, 3 bites |
| `3B` | **`DP-R6`'s backpressure partition, in code** — `is_backpressure()` | ✅ and the non-backpressure arm is enumerated, so a new variant cannot be silently unclassified |
| `3C` | **the id newtypes** (`RealityId`/`SessionId`/`ChannelId`/`NodeId`) | ⬜ **blocked on a PRODUCER, not on effort** — see below |
| `3D` | **`CapabilityToken` + `SessionContext`** | ⬜ needs `3C` and a control-plane seam (slice 5) |
| `3E` | **adoption** — the bare `reality_id` sites | ⬜ **880 across 99 files**, measured; the plan's "457" is stale |

### `3C` — an unforgeable mint is dead code until something can mint

`RealityId` was written, tested and reverted inside an hour, and the revert is
the finding. `DP-K1` specifies *"module-private constructor — cannot be forged
by feature code"*, and that property works: `tests/ui/forged_reality_id.rs`
attempted **both** escapes and rustc refused each for its own reason —
`E0603` on the tuple-struct constructor, `E0624` on `new_verified` — with the
bite (field → `pub`) breaking the test.

Then `cargo clippy -p dp --all-targets -- -D warnings` said `new_verified` is
never used, and it was right. A crate-private constructor with no in-crate
caller **is** dead code, and its caller is session bind → `CapabilityToken` →
the control plane, i.e. slice 5. Silencing it with `#[allow(dead_code)]` is the
pragma-as-exemption shape `CLAUDE.md` names by example. So the types land with
`3D`, together, and `DpError` went first because **a `pub` enum's variants are
their own constructors** — it is complete the moment it is declared.

### What `3A` had to reconcile, and what caught it

- **`DP-K3`'s field type `Tier` does not exist here.** In `crates/dp`, `Tier` is
  the sealed marker TRAIT; the runtime enum the spec means is `TierLevel`,
  renamed by slice 1 under the rule `aggregate.rs` states for exactly this case
  (*"when a name is taken, take a different one and say so"*, `FLOW-24` — which
  lists `CircuitOpen`/`RateLimited` as two more of the same class). Caught by
  **rustc** (`E0782: expected a type, found a trait`), not by review.
- **Five variants carry types this workspace has not built** (`NodeId`,
  `Timestamp`, `ActorId`, `CausalityToken`). They are in `DEFERRED_VARIANTS`
  with the type each waits on, and the oracle **requires that list to account
  for every doc variant the code omits** — so a variant cannot be dropped
  silently, invented silently, or left deferred after it ships.
- **No new dependency.** `Display` is hand-written rather than taking
  `thiserror`, so the crate's empty `[dependencies]` — the evidence `S2.3`'s
  *"declares no I/O"* rests on — survives untouched.

**The oracle is the `REC-65` mechanism.** `REC-65` was *"`DP-K3` is LOCKED at 21
variants; 5+ docs mint satellites"*, adjudicated by `REC-102b` and required by
the sealed order *before* slice 4. `spec_oracle.rs` now parses `DP-K3`'s fenced
block out of the locked markdown and compares sets three ways. Bitten: a dropped
variant, an invented one, and a deferred row that outlived its deferral each red
with their own message.

### The rest of slice 3, specified now rather than discovered later

**`3C` + `3D` land as ONE commit.** They are one unit because §0.6c seals it: a
crate-private constructor ships with its producer.

| step | what | done = |
|---|---|---|
| `3D.1` | `CapabilityToken` — opaque, crate-private constructor, an expiry, and `is_live(now)`. NO signature verification here (that is the control plane's). | unit tests incl. an expired token; `Debug` must NOT print the secret — assert that |
| `3D.2` | `trait ControlPlane` in `crates/dp` — the seam. One method: resolve a bind request into a verified `(RealityId, SessionId, CapabilityToken)`, or a `DpError`. | it compiles and `SessionContext::bind` is generic over it |
| `3D.3` | `SessionContext` per `DP-K2` — `reality_id`/`session_id`/`node_id`/`capability`/`bound_at`, `check_live() -> Result<(), DpError>` returning `CapabilityExpired`. Channel fields (`current_channel_id`, `ancestor_channels`) ship **only if** `ChannelId` has a producer by then; otherwise they are a `DEFERRED` row like `DpError`'s. | `check_live` red-tested against an expired capability |
| `3C.1` | re-add `ids.rs` (`RealityId`/`SessionId`/`ChannelId`/`NodeId`) — the file is in `ff118081b`'s history, reverted deliberately | `cargo clippy -p dp --all-targets -D warnings` exit 0, i.e. no dead code, which is the whole test of whether the producer is real |
| `3C.2` | re-add `tests/ui/forged_reality_id.rs` + `.stderr` — both escapes, `E0603` + `E0624` | the pins READ, not blessed; bite = field → `pub` breaks it |
| `3D.4` | a test double implementing `ControlPlane` **in `#[cfg(test)]`**, so the trait has an impl and `bind` is exercised end to end | a bound `SessionContext` whose `reality_id()` is the one the double verified |

**`3E` — 🅿 PARKED, ordered after slice 5.** Unblocks when a PRODUCTION
`ControlPlane` implementor exists.

**Why it cannot start now, and this is a fact about the type rather than about
effort:** a crate adopts `RealityId` by *receiving* one, and the only source is
`SessionContext::bind`, which needs a `ControlPlane`. The only implementor today
is a `#[cfg(test)]` double. So a production crate could adopt the type only by
forging a value — which is precisely what the `pub(crate)` constructor exists to
prevent. Building the ratchet first would also be a gate that punishes correct
work: it would refuse a new `reality_id: Uuid` while offering nothing to use
instead.

**The figure was wrong three times, and the corrections are the useful part:**

| claim | what it counted | measured |
|---|---|---|
| the plan's *"457 bare `reality_id` sites"* | — | stale |
| this file's *"880 across 99 files"* | **every mention** — SQL strings, column names, comments | 884, and not the subject |
| the actual subject | `reality_id: Uuid` / `&Uuid` / `Option<Uuid>` — what `RealityId` replaces | **178** |

By crate: `world-service` 81 · `dp-kernel` 73 · `rebuilder` 10 · `meta-rs` 7 ·
`commit-service` 3 · one each in `roleplay-service`, `projections`,
`dp-kernel-macros`, `contracts-prompt`.

**And `dp-kernel`'s 73 are NOT in scope** — it carries `dp-crate = true`, it *is*
the data plane, and `RealityId::new_verified` is `pub(crate)` to `dp`, so the
kernel structurally cannot hold one. The real adoption surface is the game-layer
services `DPA-SCOPE` names: **`world-service` 81 + `commit-service` 3 = 84**, of
which `commit-service`'s 3 are reachable first.

| step | what | done = |
|---|---|---|
| `3E.1` | *(after slice 5)* `scripts/reality-id-adoption-gate.py` + `contracts/dp/reality-id-baseline.json` — count the 84 in-scope sites, fail on increase and on an unrecorded decrease | self-test + 2 bites (a new bare site; a baseline row that improved) |
| `3E.2` | migrate `commit-service` (3) then `world-service` (81) | the baseline shrinks; gate green |

### Slice 4 — the tier-typed write surface (gated on `3D`)

Sealed prerequisite met: `REC-65` is mechanised (`ff118081b`). Do **not** start
before `3D`, because every signature takes `&SessionContext`.

| step | what | done = |
|---|---|---|
| `4A` | `cache_key!` (`DP-R4`) | ✅ reality-scoped form; tier checked by construction (`E0271`), `KeyId` refuses `:` and empty; channel form deferred |
| `4B` | `t0_write`..`t3_write` typed by the tier marker traits | 🅿 **PARKED** — three prerequisites, below |
| `4C` | `read_projection_*` per `04b` | 🅿 **PARKED** behind `4B` (same three) |
| `4D` | `dp-clippy` `R-6` (`forbid_swallowed_backpressure`) | 🅿 **PARKED** — no subject until `4B` |

#### Why `4B`/`4C`/`4D` park, and exactly what unblocks each

Not effort, and not an external dependency — three concrete missing pieces, each
buildable but none of them a row on this board:

1. **`DpAggregate` has no `Delta`.** `DP-K5`'s signatures are
   `t2_write<A: T2Aggregate>(ctx, id: A::Id, delta: A::Delta)`. Today the trait
   carries `Tier`, `Scope`, `Id`, `TYPE_NAME` and no `Delta`. Adding one is a
   change to the aggregate CONTRACT — governed by `dp-aggregate-gate`, pinned by
   five trybuild `.stderr` files, and implemented by four real impls. It needs
   its own slice with its own refutation round, not a line in `4B`.
2. **There is no backend seam.** `crates/dp` declares no I/O, so a write surface
   here can only be a trait, exactly as `ControlPlane` is. Its implementor is
   `dp-kernel` (event store, outbox, projections) — i.e. slice 5's wiring.
   §0.6c: *a trait ships WITH its first implementor.*
3. **`DP-K5` is async.** Every primitive but `t0_write` is `async fn`, which
   pulls a runtime contract into the crate whose defining property is that it
   has none. That is a decision to take deliberately, with the `S2.3` no-I/O
   claim re-read, not incidentally while adding a write method.

**`4D` has no SUBJECT, which is the sharper reason.** `R-6` flags `.ok()` /
`unwrap_or_default()` over a `Result<_, DpError>`. Measured: the only functions
returning `Result<_, DpError>` today are `SessionContext::bind` and
`check_live`, both inside `crates/dp` itself, and nothing calls them outside
tests. A lint shipped now would be green by emptiness — the shape this run
removed five times. `DpError::is_backpressure` already exists and is the set the
lint must key on, so the lint is a small job **the day a write surface gives it
call sites**.

**Unblocks when:** `A::Delta` lands (its own slice) **and** `dp-kernel` is wired
behind the seam. `4D` unblocks the moment `4B` has feature-code callers.

---

## 5 · REGISTERS

Decisions, parked, debt and **`BDR-1`..`BDR-48`** live in
[`2026-08-06-game-tier-build-RUN-STATE.md` §7](2026-08-06-game-tier-build-RUN-STATE.md). Append new
drift there or here; **a run that ends with an empty drift log is not clean, it is dishonest.**

The five that governed last run, so they are not re-learned:
`BDR-44` a fix without a leg · `BDR-45` a fix's blast radius ≠ its subject · `BDR-46` knowing a rule
does not transfer across a language boundary · `BDR-47` execute the path before verifying its parts ·
`BDR-48` "blocked" is a label, and it was the only blocker.

**`BDR-51` (2026-08-08) — I fixed a bug in the lookup and left the identical bug in the writer, one
function later, in the same commit.** `V.1` round 2 found that `RealitiesForUser` ignored owned
realities; I fixed it, and shipped `reassignOwnedRealities` as the tail of the binding deleter —
*after* its `if len(found) == 0 { return nil }`. So the erasure never ran for a user who owns a
reality but drives no actor: **the exact class I had just fixed**. Round 3 proved it against live
data — both user-owned realities belonged to a user with zero bindings, so erasing them was a no-op.

Three lessons, in increasing order of how much they cost:
1. **A fix teaches you the shape of a bug. Search for that shape everywhere before closing.** I had
   the concept in hand and applied it to one of the two places that needed it.
2. **Every assertion about that path was a `strings.Contains` over the source.** The reviewer
   changed the query to `WHERE owner_user_id = $1 AND false` and the whole suite stayed green. A
   grep-vs-grep bite proves `strings.Contains` works; it cannot see behaviour. Three of my six META
   bites were that.
3. **A gate can be blind to its own subject.** My meta walk required the column at line start;
   migration 036 adds it via `ADD COLUMN`, so it matched **zero** files — the gate written to catch
   a default-uncovered column could not see that column. `NV-4`, inside the fix for `NV-3`.

**`BDR-50` (2026-08-08) — the three-axis DoD passed work that carried a split-brain bug and three
checks that could not fail.** `W3` was green on CODE, LIVE RUN and DATA, honestly. `V.1` still
returned BLOCK with 3 HIGH. The reason is structural, not effort: **the axes test the SUBJECT; only
an independent reader tests the APPARATUS.** My bite harness certified a guard whose assertions read
a 256-byte window the evidence could never reach, and reported it as proof. A cold reader measured
the actual byte lengths — 4242 vs 12907 — and the claim collapsed. Two corollaries worth keeping:
a green bite is not a proven guard unless you know *why* it went red; and `[WEAK]` detection must
cover more than build failures, because "red for an unrelated reason" is the failure mode that looks
most like success. **Budget `V.1` on anything load-bearing, and budget it against the VERIFICATION,
not only the code.**

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
