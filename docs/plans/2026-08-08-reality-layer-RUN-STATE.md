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
| **the capability MODEL (`5B`)** — and this one is a **deliberate deviation from a LOCKED spec**, sealed 2026-08-09 by the PO on the record below | **Opaque BEARER capability + a meta-table store; the control plane validates by LOOKUP.** `05_control_plane_spec.md` specifies signed JWTs (RS256/Ed25519, `capability_signing_keys` rotated quarterly, `tier_capability` keyed by service × aggregate × tier). We are not building that yet, because **nothing validates a capability offline today** — every holder can reach the CP, so a signature buys nothing and costs a key-rotation subsystem with zero readers, which is the orphan shape `Phase 0` exists to catch. `DP-C3` carries the amendment; this is not a silent divergence. **Its cost, stated up front:** validation is a round trip to the CP, per validation. Signing is the only thing that removes that round trip. | **a capability holder and its validator become different processes AND the round trip is measured to hurt.** `5C` makes the first half true within this same goal — so the trigger is deliberately conjunctive: remoteness alone does not fire it, *measured* pain does |
| **`bind` authenticates nothing** | **Fix it in `5B`, not later.** `BindRequest { reality, node }` carries no caller identity, so `MetaControlPlane` verifies the reality exists and accepts commands but never that *this caller may reach it*, while `DP-A12`'s "session-context-gated access" implies it did. `BindRequest` gains the calling service identity. Mandatory under either capability model — the spec keys capabilities BY service, so without it there is no subject to key on. | — |
| **`5C`, the gRPC control-plane surface** | **IN SCOPE — build it.** Sealed 2026-08-09 against my own recommendation to park; the PO's call. Phase 0 must settle one thing before code: whether an internal, cluster-only control-plane gRPC is a *public entry point* under gateway invariant `I1` at all. `I1` governs **external** traffic; if the surface is not externally reachable it does not amend `I1`, and that finding must be **recorded with the evidence**, not assumed in either direction. | — |

### 0.6 · Escapes that cost real time last run

- **Heredocs eat backslashes.** `\b`, `\n`, `\u{74}` and `\\n` were all corrupted, once producing a
  **vacuous gate rule** that could never fire. Use the Edit/Write tools, or a scratchpad file, for
  anything containing a backslash. `cat -A` reveals it.
- **A fix without a leg is a fix the next edit removes.** Five mutations of a "fixed" migration
  stayed green; three silently reverted the fixes. *"I verified it live"* ≠ *"the suite would
  notice."* (`BDR-44`)
- **Do not run two suites against one throwaway DB name.** Contamination presents as a schema defect.
  Per-pid suffixes everywhere.
- **Do not run two GATE SWEEPS at once — and now you cannot.** Measured 2026-08-09.
  `gate-wiring-gate`'s `MUTATING` tuple serialises the bite harnesses *within one
  sweep process*; two sweep processes defeat it entirely, and the damage is worse
  than a false red:

      harness A reads its baseline   <- already mutated by B
      harness A mutates, then restores TO A'S BASELINE
      = B's mutation is now PERMANENT, and A's digest check PASSES

  The restore-by-digest guard (`V1-F8`) cannot see it: it proves the file came
  back to what the harness read, and what it read was already wrong. Three files
  were left mutated in `crates/dp` — including `tier.rs`'s `as_key` returning
  `TIER_ZERO` — and all four bite gates reported red for a reason unrelated to
  any guard. **Fixed with a lock** (`target/.bite-harness.lock`, `O_EXCL`) that
  all four harnesses take; a second one refuses with exit 2 and says how to clear
  a stale lock. Not a dirty-tree check: restoring to a dirty working tree is
  correct, and refusing on ordinary uncommitted work would be refusing the wrong
  thing.

---

### 0.6d · THE EXECUTION CONTRACT — what "execute the run-state" actually obliges

This section exists so a goal prompt can be three lines. Everything a long prompt
used to carry lives here instead, where it is re-read at the start of every
session and survives a compaction. **A rule that lives only in a prompt is a rule
that evaporates.**

#### The execution invariant

At every moment there is exactly **one** authoritative next action: the next
applicable row of this file.

If the next action is defined here, **execute it.** Do not ask what to do next.
Do not ask whether to continue. Do not ask for confirmation. Do not say *"ready
for next"*, *"I can continue"*, or *"should I proceed"*. Do not return control
while executable work remains, and do not substitute a plan, a summary, a
recommendation or an explanation for the execution itself.

After a row is completed **and verified**, advance to the next applicable row and
execute it. Continue across turns. **A turn boundary is not permission to stop.**

#### The source-of-truth rule

Do not redesign, reorder, reinterpret, reopen or re-plan this file. Do not invent
replacement work because a different approach looks preferable. If this file
already says what to do, do not deliberate about what to do.

Sealed forks (§0.6c) reopen only on **new factual evidence** — never on
preference, doubt, or a wish to re-litigate.

#### The row-completion contract

A row is **not** done because code changed, because tests ran, or because it
looks right. A row is done when every piece of acceptance evidence that row
requires **is present in the transcript as pasted real command output.**

For every new guard, validator or oracle check, all six steps, in order:

1. run it normally, capture **GREEN**;
2. mutate exactly **one side** of the guarded subject or pair;
3. run it, capture genuine **RED** that names the violated relationship — and
   both sides, where the check is about a relationship;
4. restore the mutation;
5. run it again, capture **GREEN**;
6. only then mark the row done.

Never substitute *"passed"*, *"verified"* or *"looks correct"* for output. And
note what step 3 is really asking: a red for an unrelated reason — a build
failure, a renamed test that no longer runs — is the failure mode that looks most
like success (`BDR-50`, `BDR-56`).

#### Non-negotiable hazards

* **Never run two `gate-wiring-gate --run-all` sweeps concurrently**, and never
  run one while a bite harness is running. `BDR-53`: the second harness's restore
  makes the first one's mutation permanent, and the restore-by-digest guard
  cannot see it. The `O_EXCL` lock now refuses this — and **a refusal is exit 2,
  which is failure evidence, not a passing verification.**
* **Run `--run-all` DETACHED.** It takes ~25 minutes; a foreground call with a
  shorter timeout gets SIGTERM, and the harness that was mid-bite never restores
  — `BDR-89` left a deleted assertion in `spec_oracle.rs` and a stale
  `target/.bite-harness.lock`. The lock cannot cover this: it is released by the
  process, and the signal kills the process. **After any interrupted sweep, run
  `git status` before anything else** — the exit code was `143` and said nothing
  about the mutated file.
* **Heredocs eat backslashes** (§0.6). Use the Edit/Write tools for anything
  containing one.
* **Never run two suites against one throwaway database name** (§0.6).

#### Blockers

Park **only** on a blocker genuinely external to this repository (§0.3).

*"I would have to build it"*, *"this is large"*, *"this may take many turns"*,
uncertainty about implementation, and needing to read more code are **not**
blockers. When genuinely blocked: name the exact external dependency, record it
in the register, and **immediately continue with the next executable row.** One
blocked row never stops the run while another executable row exists.

#### The continuation check, before every turn boundary

1. Which row is current?
2. Is it complete against its acceptance criteria?
3. If yes — which row is next?
4. Is that action executable?
5. If executable — **execute it now.**

Never return a "next steps" list while executable work remains.

#### The drift log is not optional

Append to §5 as you go: real drift, newly discovered failure modes, assumptions
that turned out wrong, lessons about execution. **An empty drift log is not
evidence of a clean run** — it is evidence that nobody wrote down the near
misses.

#### Stop conditions — the complete list

**A.** every applicable row is complete and carries its pasted evidence; or
**B.** a destructive or irreversible action genuinely requires the PO's decision; or
**C.** a sealed decision is proven wrong by new factual evidence and this file
requires a decision to proceed; or
**D.** execution is genuinely blocked externally (§0.3) **and** no other
executable row exists.

Otherwise: **continue executing.**

#### What is NOT a stop condition — added 2026-08-10 after all four were used as one

The list above is exhaustive, and it was still talked past. Each of these was
either used to end a turn in this session or is one rephrasing away from it:

* **The POST-REVIEW checkpoint.** §0.6b classes it as *"a presentation, not a
  question"*. Present it and keep going. `BDR-64`: I quoted that sentence as the
  justification for stopping on it.
* **A green sweep, a passing suite, a completed row, a commit.** These are
  reasons to advance to the next row, which is the opposite of a reason to stop.
  A commit is a checkpoint, not a boundary.
* **A turn boundary**, an arriving notification, or a long-running command
  finishing. Read the result and continue in the same turn.
* **"The work has reached a natural pause."** There is no such row. If the
  continuation check in §0.6d has an executable answer, execute it.
* **Uncommitted work piling up.** Commit it and continue; committing is
  reversible and is phase 11, not an exit.
* **Wanting a decision that this file can make.** §0.6b: seal the fork here,
  with its reversal trigger, and act on it.

**The tell, in one line:** if you are reaching for a section of this file to
explain why stopping is allowed, you are already past the point where the
continuation check answered *"execute it now."*

#### Waiting is not stopping

A long verification (`--run-all` is ~25 minutes) is *work in progress*, not a
turn boundary. Launch it in the background, and while it runs do only what
cannot collide with it — `BDR-53` — which in practice means documents no bite
harness mutates. Do not idle, and do not end the run on "waiting for the
sweep".

### 0.6e · NEXT SESSION — the three targets, in this order

Mandatory, and they do **not** replace the remaining rows of §4; execute them at
the point this file's ordering dictates.

**The 2026-08-10 set is CLOSED** — `G3-ORACLE-COVERAGE`, `META-DOWN-UNCOVERED` and
`3E-NAMING-INCONSISTENCY`, plus the two §4 rows they uncovered (`3E-EPOCH-COMMIT-ADOPTION`,
`W7-SHELL-UNCOVERED`) and `slice 1`'s `G4`/`G6`–`G13`. Each carries its evidence in §4 and its
lessons in §5 (`BDR-57`..`BDR-70`). Shipped in `b4d495f4e` + the teeth-gate widening.

<details>
<summary>The three <code>done =</code> cells they were graded against, kept verbatim</summary>

A closed row's acceptance criterion is what a later reader audits the closure *against*; deleting
it leaves "done" as an assertion. Verbatim, as written when they were opened:

1. `G3-ORACLE-COVERAGE` — *"the ratchet exists and reds on a decrease; each new oracle rule is
   **bitten** per the six steps above — mutate one side of the doc/code pair, RED naming BOTH
   sides, restore, GREEN"*
2. `META-DOWN-UNCOVERED` — *"the validator walks both trees; the `036`/`037` down-migrations
   actually run, with pasted output"*
3. `3E-NAMING-INCONSISTENCY` — *"resolved by teaching the gate the input-boundary category, or by
   an explicit reasoned exemption. **NOT by renaming** — `BDR-55`: renaming moves the number, not
   the property"*

</details>

**The next three, in this order.** Every one is a worklist a mechanism can already count, which is
deliberate: after this session the open items are all *numbers that can only fall*, not prose.

| # | row | done = |
|---|---|---|
| 1 | ~~**`GATE-TEETH-55`**, the four bite harnesses~~ **✅ DONE 2026-08-10, 55 → 51.** All four now carry a `--self-test`; both arm families bitten (break `classify`'s `missing` branch → red; rot a leg anchor → red). `5d` still bites 8/8 end to end, so the proof did not cost the harness. **Continues as `GATE-TEETH-47`** in §4. **2026-08-10, 51 → 48:** `db-safety-gate`, `doc-language-gate`, `language-bias-gate` — the three that read a corpus and could silently read nothing. Each gained a **reach** family (every search dir must exist; the walk must clear a floor) beside its detectors, because a walk that reaches nothing is byte-identical to a clean tree. Found: 7 stale `language-bias` baseline rows and a gate RED on `main` for 9 days. **And a fourth thing that was not on the list** — `--verify-proofs` now RUNS the 42 advertised self-tests instead of matching their text, which caught `dp-oracle-bite-gate.py` certified on a string literal it uses to read *another* gate's output. See `BDR-74`, `BDR-75` | each gate gains a `--self-test` whose arms are proven on synthetic input, `NO_PROOF_BASELINE` lowered by the same number with the reason recorded, and the lowering **bitten** — remove one arm, watch the self-test red, restore |
| 2 | **`G3` continued — 13 → 14 of 26, and THIS ROW WAS WRONG.** It named four candidates; **three have no producer**, measured before writing anything: `DurableEventStream` 0 files · `advance_turn` 0 · `TurnBoundary` 0 · `wait_for_token` 0 · `route_to_writer` 0 · `CausalityToken` twice, both DEFERRED-register rows recording it as unbuilt. Oracles for those would be the orphan shape §0.6c forbids — the row told me to avoid exactly the trap it was walking me into. Only `11_access_pattern_rules` had both sides, and it is now covered by `spec_oracle_rules.rs`, which **found `DP-R7` enforced by nothing** | coverage rises, the baseline records it, and each new oracle rule is bitten per the six steps — mutate one side, RED naming BOTH, restore, GREEN. **Do not add a rule whose subject has no producer** (§0.6c). Of the twelve still unread, `16_bubble_up_aggregator`, `19_privacy_redaction_policies`, `20_operational_residuals` and `21_llm_turn_slot` need the same producer check FIRST — `00_preamble`, `22_feature_design_quickstart`, `99_open_questions` and `_index` are prose with no code side and should be excluded from the denominator rather than faked into it |
| 2b | ~~**`G3`'s PRODUCER AUDIT**~~ **✅ DONE 2026-08-10 — 14/26 → 14/15, and the worklist is now ONE document.** The denominator is split: `NOT_A_SPEC` (4, checked against *"declares zero `## DP-` headings"*) and `NO_PRODUCER` (7, each naming its marker symbols, checked against a comment-stripped walk of `crates` + `services`). Both bitten on the real tree: `pub struct RedactionFilter;` in `read.rs` reds naming the doc, the marker and the file; a `## DP-Ch99` appended to `99_open_questions.md` reds *"it became a specification"*; both restored byte-identically. Four arms added to `--selftest` (15 cases). **One of them was vacuous and biting caught it** — see `BDR-79`. Remaining: `01_scope_and_boundary.md`, whose boundary rule drives `reality-id-adoption-gate`'s `IN_SCOPE` with nothing comparing them | done |
| 2c | ~~**`G3`'s LAST DOCUMENT**~~ **✅ DONE 2026-08-11 — 14/15 → 15/15, the worklist is EMPTY.** The document has two code sides and they are in different languages, which is the whole reason this row was left last. **§2.4/§3b (Rust ↔ Rust)** get `crates/dp/tests/spec_oracle_scope.rs`: the primitives the doc names must be exported by `crates/dp/src/lib.rs` or carry a `SPECIFIED_NOT_BUILT` row, every exported `tN_*` door must sit in a tier family §2.4 still declares, and the `(~20 methods)` ceiling is **parsed out of the document** so raising it is an edit to a LOCKED doc rather than a constant bump in a test. **New finding: two of the three primitives §3b advertises as shipping do not exist** — `query_scoped_reality` and `t3_write_multi` — now registered with a shrink arm instead of living in prose. **§4's boundary rule (doc ↔ Python) is checked where its consumer is**, beside `IN_SCOPE` in `reality-id-adoption-gate.py`, because a Rust test reading a Python tuple is `BDR-79` exactly. That check runs §4 in **both** directions: every `dp`-dependent service must be in `IN_SCOPE` (and vice versa, with a phantom arm), and — the antecedent spelled forward — a service naming a `reality_<id>_db` **without** the SDK is the second door Option (c) exists to forbid. It closes the silent narrowing this gate's own preamble named as the cheapest way to fake a clean run. **Bitten: 5 arms on the Rust side** (register both ways, tier family, ceiling, and the ratchet itself reds `COVERAGE LOST`), **6/6 on the Python side** against synthetic trees, all restores byte-exact. Three defects found by biting, none visible on green: `BDR-82`, `BDR-83`, `BDR-84`; plus `BDR-85` | done |
| 2b-orig | **`G3`'s PRODUCER AUDIT — the measurement, kept because it is what the split rests on.** All twelve unread documents classified, measured the shrink arm's way (comment lines stripped, the recording file excluded — see `BDR-76`). **Eleven cannot honestly be covered.** *No producer, 7:* `14_durable_subscribe` · `15_turn_boundary` · `16_bubble_up_aggregator` · `18_causality_and_routing` · `19_privacy_redaction_policies` · `20_operational_residuals` · `21_llm_turn_slot` — every marker symbol 0 files; `BubbleUpAggregator`'s single hit is a `DEFERRED_RPCS` row recording it unbuilt, and the only `redact` code in the tree is log-field PII masking, a different subject. *Prose, no code side, 4:* `00_preamble` · `22_feature_design_quickstart` · `99_open_questions` · `_index`. **Coverable and uncovered: exactly one** — `01_scope_and_boundary`, whose boundary rule is what `reality-id-adoption-gate.py`'s `IN_SCOPE` is derived from, with nothing comparing them | **the denominator, not the numerator, is the remaining work.** Split it into `NOT_A_SPEC` and `NO_PRODUCER`, every row reasoned AND checked, each with a **shrink arm** returning a doc to the denominator the moment a marker symbol appears in non-comment source — the arm already built and bitten for `DP-R7`. Coverage then reads **14/15** with a one-item worklist instead of 14/26 with a number that cannot move. **Do not raise the numerator by writing an oracle over a producerless doc** (§0.6c) |
| 3 | ~~**`3E-EPOCH-COMMIT-ADOPTION`'s last site**~~ **✅ DONE 2026-08-10, 1 → 0 adoptable.** A **checked** exemption, not prose: the reason is that the harness *mints* its reality and registers it nowhere, so `bind` would refuse it — and that claim is now mechanised (`SELF_MINTED` + `check_self_minted`, four arms, void the moment a `--reality`/`REALITY_ID`/`parse_str` appears). The gate refused the 1→0 / 0→1 reclassification until the baseline recorded it; total unchanged at 57. See the §4 row and `BDR-73` | either it adopts a verified id, or it earns a **reasoned** exemption naming why a benchmark harness cannot bind. **Not a third category invented to make the number zero** — `BDR-55` |

**Deliberately NOT in this list**, unchanged: `D-META-ERASURE-COVERAGE`'s two undecided tables
(`session_cost_summary`, `service_to_service_audit` declare no erasure method at all). A GDPR
product decision, for the PO, not an autonomous run.

**Deliberately NOT in this list:** `D-META-ERASURE-COVERAGE`'s two undecided
tables (`session_cost_summary`, `service_to_service_audit` declare no erasure
method at all). That is a GDPR product decision, not engineering — it goes to the
PO, not into an autonomous run.

## 1 · MEASURED STATE — **re-measured 2026-08-10**, each with the command that produced it

Re-measure rather than trust this table if more than a session has passed. Two rows moved since
2026-08-08 and both are recorded rather than overwritten: the meta database gained migrations
`036`–`039` and the `session_registry` table with them.

| fact | value | command |
|---|---|---|
| realities in existence | **10** (was 7 on 2026-08-10, 0 at session start) — three added 2026-08-11 by the world-service live smoke, one of them recovered from a half-provisioned state through the resume path | `psql -d loreweave_meta -tAc "SELECT count(*) FROM reality_registry"` |
| a reality's database | `lw_reality_cd0747d24b94`, **12 tables** — ~~13~~, a miscount in the first draft of this table, corrected 2026-08-08 when the second reality's schema was diffed against it and matched exactly | `SELECT count(*) FROM pg_tables WHERE schemaname='public'` |
| its migration ledger | **15 applied** | `SELECT count(*) FROM schema_migrations` |
| `channels` in a real reality | **exists, holds a root row, `REC-106` refuses a self-parent** `[NC:behaviour]` | `SELECT to_regclass('public.channels')` |
| meta database | **exists**, **29 tables, 40 migrations** (was 28/35 on 2026-08-08 — `036`/`037` ownership, `038` orphan_scan_finding, `039` session_registry, `040` tier_policy) | `psql -d loreweave_meta -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'"`; `ls migrations/meta/*.up.sql \| wc -l` |
| registered shards | **1** — `pg-shard-0.internal`, cap 50 `[NC:row-contents]` | `SELECT * FROM shard_utilization` |
| meta bridge | **up, healthy, :8090** | `docker compose ps meta-bridge` |
| `world-service` server binary | **SERVING, since 2026-08-11** `[NC:live-process]` — `POST /internal/v1/realities` + `/livez` `/readyz` `/metrics` on `crates/service-http`; a reality was created over a socket and confirmed in `pg_database`. Was *"none serving — a 22-line `println!` scaffold; the 7 real bins are workers/drills"*, which is now wrong on all three counts (it serves, it is not a scaffold `[NC:no-predicate]`, and there are **8** other bins). **Corrected by the audit that falsified it, not by the track that did** — see `BDR-91` | `ls services/world-service/src/bin/`; `cat src/main.rs` |
| admin command surface | **33 commands, live and dispatched** `[NC:toolchain]`, 10 domain registries | `go run ./cmd/admin --list` |
| a command that CREATES a reality | **`reality provision`**, shipped by `W3` (was: none — all 8 `reality` commands required one to exist) | `--list` |
| admin issuance on the dev stack | **was disabled** `[NC:history]` (`POST /internal/admin/token` → 404, no signing key). `W3` enabled it; the key lives in the operator's env, **not** the repo — regenerate + `export ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM=<base64 PKCS#8>` then `docker compose up -d auth-service` | `curl -o /dev/null -w '%{http_code}' -XPOST …/internal/admin/token` |
| game-tier services in compose | `game-server` only; `world-service`, `commit-service` absent — **still true**, and now a gap rather than a non-event: world-service has a server binary with no compose entry and no general `Dockerfile` (`WS-COMPOSE`) | `grep -cE '^  (world-service|commit-service|game-server):' infra/docker-compose.yml` → **1** of 3 |
| Postgres login roles | **3** — `loreweave` (`rolsuper`+`rolbypassrls`), **`loreweave_provisioner`** (`CREATEDB` only, `W7`), `w1p_foreign` (a drill fixture) | `SELECT rolname, rolsuper, rolcreatedb FROM pg_roles WHERE rolcanlogin` |

**Every figure above is measured by `scripts/actor-hub-figures-gate.py`, which `--check`s it against
the artifacts on every commit** — ten of them: the reality count, the exemplar's tables and migration
ledger, the meta database's tables and migrations, the shard count, world-service's other binaries,
the admin domain registries, the game-tier services in compose, and the Postgres login roles.

**`[NC:…]` marks a sub-claim that is NOT checked, and why.** A table where checked figures sit beside
unchecked prose, indistinguishable, is the same defect one level down — so the unchecked half says so
in the cell rather than borrowing the credibility of the row it lives in.

| tag | why no command yields it |
|---|---|
| `[NC:behaviour]` | needs an attempted WRITE, not a read — `REC-106`'s refusal is a rejection, and a gate that provokes one on every commit is a gate that writes to a live database |
| `[NC:live-process]` | needs a RUNNING process. False on any box with nothing up, so the honest answer is *skip and say so*, never *the document is wrong* |
| `[NC:no-predicate]` | **nobody has said what would falsify it.** This is the honest core of the whole thread: *"not a scaffold"* is unfalsifiable as written, and marking it is the only available remedy |
| `[NC:toolchain]` | needs `go run ./cmd/admin --list`. A naive file count answers 34 against a claimed 33, which is precisely why a wrong measurement is worse than an admitted gap |
| `[NC:history]` | a claim about a PAST state. No present measurement confirms one |
| `[NC:row-contents]` | a row's contents rather than a count — the gate governs figures (`CR-F3`), and `cap 50` is a column value |

<!-- actor-hub-figures:end reality-measured-state -->

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

<details>
<summary>W3 / W7 / W6 / W5 evidence — all four rows are CLOSED; this is how each was proven.</summary>

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


</details>

## 4 · OPEN, each with a trigger

| id | what | trigger |
|---|---|---|
| `FLOW-19` | `channel_writer_state` has no FK to `channels` | `flow19_trigger()` in `dp-channels-schema-gate` reds when `channels` gains a non-test writer. `W3` did NOT create one — it creates the *table*, per migration; the first row-writer is still ahead |
| `W3-DEVKEY` | the dev stack's admin signing key is operator-env only, so `reality provision` reverts to unaudited-refused after a fresh clone | a second person needing to run an admin command here, or CI wanting one. Do **not** commit a key; a bootstrap script that generates one is the fix |
| `W3-LOCKSPAN` | the advisory lock is held across the WHOLE 11-step provision (incl. migrations), not just through `register_pending` at step 3 | provisioning becoming frequent enough that per-shard serialisation hurts. Deliberate: correctness over throughput on an admin-gated action |
| `W6-OWNER-UNVALIDATED` | **conscious decision, recorded because `V.1` found it undocumented.** Nothing checks that `owner_user_id` names a real user: there is no FK (cross-database), and neither the bridge nor the admin handler looks the user up. An admin CAN provision a reality owned by a UUID belonging to nobody. Acceptable for an admin-only tier-2 command where the operator supplies the id deliberately — **not** acceptable once users request their own | the user-facing request pipeline. It must resolve the owner from the authenticated caller, not from a typed parameter |
| `D-META-ERASURE-COVERAGE` | **4 open, down from a reported 8** — the first count asked *"does PgMetaScrubber handle it"* rather than *"does ANY mechanism"*, and three (`pii_kek`, `pii_registry`, `user_consent_ledger`) turned out fully handled by admin-cli's crypto-shred / revoke path; `user_queue_metrics` is now implemented. Open: `user_cost_ledger` + `user_daily_cost` declare `pseudonymize_user_ref_at_2y`, a TIME-based retention job that is unbuilt; **`session_cost_summary` and `service_to_service_audit` declare NO method at all — a PO call, not an engineering one** | `TestMetaMigrationsDeclareAnImplementedErasure` — three registers (`implemented` / `handledElsewhere` / `knownUnhandled`), each must shrink, and a NEW user-referencing meta table cannot be added without a row in one of them |
| `W6-ERASURE-EVENT` | `reality_registry` + `OpUpdate` maps to `reality.status.changed` in the allowlist, so the erasure reassign would emit a status-changed event carrying no status change. **Latent only** — `main.go` builds the MetaWrite config with no `Outbox`, so nothing fires today | wiring an Outbox into the meta-worker erasure path |
| `W7-TEMPLATE1` | the provisioner relies on `CREATE DATABASE`'s **implicit** `TEMPLATE template1` to inherit `vector`; a future `TEMPLATE template0` (the standard move for encoding control) silently returns provisioning to needing superuser. Also cluster-wide: every new database on this box now carries pgvector, and `infra/foundation-dev/` is a **second** cluster that never runs `db-ensure.sh` | anyone adding a TEMPLATE clause, or standing up the foundation-dev cluster for provisioning |
| `1b7db-03` | ~~`loreweave` is the sole Postgres login and is superuser~~ **CLEARED by `W7`** — provisioning runs as `loreweave_provisioner` (`CREATEDB` only). Other services still connect as `loreweave`; narrowing those is a separate, larger sweep | the next service touched |
| `1b14-07` | `metadata` JSONB / `display_name` / `dissolved_at` unconstrained | the first writer of `channels` |
| `1b7db-08` | `CREATE TABLE … INHERITS (channels)` bypasses constraints | conscious won't-fix; a non-SDK writer appearing |
| `1b7db-11` | `channels_id_positive` constrains an unwritten `reality_root` derivation | its first implementation |
| `G-S3`/`G-S4` | lore bible has no schema; "pre-manifest stub" is not a named artifact | the BOOK_TO_GAME track |
| `D-DP-ORPHANED-CAPABILITY-ON-REJECTED-BIND` | **promoted here 2026-08-10 from the post-slice-5 review**, which is now collapsed — an open row inside a closed section is a row nobody re-reads. `MetaControlPlane::verify_bind` records the capability before returning; `SessionContext::bind` can still reject afterwards on `now_ms >= expires_at_ms`, so a caller more than one TTL ahead of the CP's clock leaves a live row whose secret was dropped. Not a security hole — an unpresentable row — but the shape (a store write whose caller can still fail) is worth a name | `session_registry` carries `@retention_hot: 90d`, so these are already inside a retention regime. Wakes on the first retention sweep reporting a non-trivial count of never-validated rows — which needs a `last_validated_at` column, and that column arrives with the fix |
| `SWEEP-RED-UNEXPLAINED` | **`dp-oracle-bite-gate` reported RED once inside `--run-all` and has not reproduced** — green on three runs since, one of them a second full sweep from a clean tree (85 green, rc=0). Nothing was changed between, so there is no fix to claim. Leading hypothesis (`BDR-90`): an orphaned `cargo` child of the sweep I had killed with SIGTERM a minute earlier, holding `target/`'s lock — consistent with the evidence, not established by it | **wakes on the next RED from this harness.** It is uninvestigable as things stand: `gate-wiring-gate` prints one summary line per gate and discards the captured output, so the failing leg cannot be recovered from the log. The fix that would make a recurrence diagnosable is to RETAIN the failing gate's output — do that when it next fires, or sooner if another one-off appears |
| `GATE-TEETH-43` | **43 of 98 CI-invoked gates carry no red-ability proof** (97 until 2026-08-11; `authorable-surface-gate` made it 98 and ships with a `--self-test`, so the numerator held) — no `--self-test`, no `test_<name>.py`. The HARD tier is green (every one *can* return non-zero); what is missing is the demonstration that it *does*. Opened at **55** on 2026-08-10 when `BDR-70` widened the teeth gate's scope from 58 to 97; **55 -> 51 the same day**, taking the four `dp-slice{1,5b,5c,5d}-bite-gate` harnesses first because a bite harness with broken machinery prints `bitten: N/N` and is believed. Each now proves the MACHINERY — the four-way verdict on synthetic transcripts, byte-exact CRLF round-trip, the restore check firing on a corrupted file, and every leg anchor still present — not the guards it bites | ratcheted at 51 and cannot grow; `NO_PROOF_BASELINE` records every move with its reason. **51 -> 48 (2026-08-10):** `db-safety-gate`, `doc-language-gate`, `language-bias-gate` — the three that read a corpus and could silently read nothing; each gained a REACH family, and the run found 7 stale baseline rows plus a gate red on `main` for 9 days. **48 -> 47:** not progress — `deferral-gate.py` already had a proof and was being FALSELY ACCUSED, its `def self_test` deleted by a docstring stripper that pairs any two triple-quotes (`BDR-80`). Python is parsed now. **Next: `--verify-proofs` RUNS 43 of them in CI, so the remaining 47 are gates whose red-ability nothing demonstrates AT ALL** **47 -> 43 (2026-08-11): the security-adjacent batch is DONE** — `injection-coverage-lint`, `meta-sensitive-read-bypass-lint`, `pii-classify-lint`, `test-dsn-coverage-gate`, each with a REACH family beside its detectors because all four are corpus walkers and each had a different silent-nothing path: `pii-classify` grandfathers everything below 018 (a renumbering leaves it inspecting zero and printing PASS), `test-dsn` derives its unarmed set FROM its gating set (an empty walk prints *"every gating variable is armed"*, the exact false clean it exists to prevent one level up), `injection-coverage` skips a missing `SCAN_DIRS` entry with a bare `continue` (renaming a service directory retires it over that whole service), and `meta-sensitive-read` guarded its zero-tables case but not its grep ROOTS. **15/15 arms bitten, all four files restored byte-exact; the lowering itself bitten** — removing one proof reds `grew to 44 (baseline 43)`. `--verify-proofs` now RUNS 47 (was 43). Two real defects found, neither visible on green: `os.environ["X_TEST_Y"]` was NEVER matched by the gate whose subject is invisible suites (`BDR-87`), and a 16-row list of tracked injection holes had no shrink arm (`BDR-88`). Plus `BDR-86`. **Next batch by blast radius: the destructive/tenancy set** — `meta-write-discipline-lint`, `tenancy-scope-lint`, `secret-scan`-adjacent gates; pick them the same way, worst-consequence-first |


**Recently cleared (2026-08-12)** — `CLAIM-ROT`, **the row this whole thread was named for.** Opened 2026-08-11 by the audit in `BDR-91`; its action cell said *"spec first, then CLARIFY with the PO"*. Both happened: the spec was written, audited, and then **overturned by its own experiment** (`docs/specs/2026-08-15-claim-rot.md` §4c), which found the unit was the FIGURE and not the row — so the proposed claim registry was NOT built. What shipped instead is `actor-hub-figures-gate` widened to this file's own MEASURED STATE table: ten figures measured on every commit, six unmeasurable sub-claims tagged `[NC:…]` in the cell, bitten five ways, `e66eb7d9d`. Board: [`2026-08-16-claim-rot-RUN-STATE.md`](2026-08-16-claim-rot-RUN-STATE.md). **Still uncovered and honestly so:** prose claims — the two instances that survived longest were a README and a Dockerfile comment, and *"not a scaffold"* has no predicate at all (`CR-PROSE-CLAIMS`).

**Recently cleared (2026-08-10)** — moved out of the table because a closed row re-read at every PLAN is the register rot this file keeps finding in other people's lists. Evidence for each is in §5 and in the collapsed slice sections below: `G3-ORACLE-COVERAGE` · `3E-NAMING-INCONSISTENCY` · `3E-EPOCH-COMMIT-ADOPTION` · `W5-REMEDIATE` · `W5-CRON` · `W7-SHELL-UNCOVERED` · `META-DOWN-UNCOVERED` · `slice 1` · `slice 2`.

<details>
<summary>Recently cleared — the closed rows in full, with the evidence each carried</summary>

| id | what | trigger |
|---|---|---|
| ~~`G3-ORACLE-COVERAGE`~~ | **CLOSED 2026-08-10. 9 → 13 of 26**, ratchet built and bitten. `scripts/dp-oracle-coverage-gate.py` + `contracts/dp/oracle-coverage-baseline.json`: a document counts only when its name is a string literal in code (not a comment), in a function **reachable from a `#[test]`**, with an assertion **somewhere in that chain** — a grep would have scored 14/26 on day one and been wrong about five, because `spec_oracle`'s own docstring names documents it does not read. Four new oracle files: `dp-control-plane/tests/spec_oracle_cp.rs` (`DP-C2` tables · `DP-C3` RPC set · `DP-C8` TTL), `dp/tests/spec_oracle_sdk.rs` (`DP-K9` refresh lead · `DP-K11` lint set), `dp/tests/spec_oracle_channels.rs` (`DP-Ch11` columns + uniqueness triple · `DP-Ch31` states, incl. a doc↔doc arm). **`scripts/dp-oracle-bite-gate.py`: 19/19 legs, each mutating ONE side and requiring the red to NAME BOTH.** Three prose-only gaps became registers with a shrink arm: `CP_TABLES_WITHOUT_A_MIGRATION` (5), `DEFERRED_LINTS` (2), `DEFERRED_EVENT_COLUMNS` (1). **New finding: `DP-Ch11` declares `events.turn_number` and NO migration creates it** — registered, blocker named. See `BDR-57`..`BDR-60` | done |
| ~~`3E-NAMING-INCONSISTENCY`~~ | **CLOSED 2026-08-10, and it was NOT latent.** The gate learned the property, nothing was renamed. **`commit-service` reported `0 adoptable, 0 exempt` — completely adopted — while carrying five real sites, four of them on the spine's LIVE WRITE PATH (`epoch_commit.rs`).** A whole in-scope service was invisible because its field is spelled `reality`. A second defect fell out in the opposite direction: the regex tail accepted `reality_id: Uuid::from_u128(0x42)`, a struct *literal*, so **eleven non-sites** were inflating `exempt` (63 → 52). Now three categories — `adoptable` (must reach zero) · `exempt` (the reality cannot be accepting commands) · **`boundary`** (the raw value a bind consumes) — each ratcheted against growth, with an `AMBIGUOUS` arm refusing a prefix in both tables. **The boundary category is detected by PROPERTY**, not a list: a `reality: Uuid` parameter of a function whose body reaches `SessionContext::bind`/`MetaControlPlane` is a bind input, and stops being one if the body stops binding — self-tested in both directions on a pair of sources differing by one line. Only `spine_args` (a struct field with no enclosing function to read) is curated, which is the *"or an explicit reasoned exemption"* half of the trigger. **Honest outcome per `BDR-55`: the number went UP, 0 → 5 adoptable.** New debt row below | done |
| ~~`3E-EPOCH-COMMIT-ADOPTION`~~ | **PAID 2026-08-10, 5 → 1.** All four `epoch_commit` signatures (`drain_and_reconcile` / `reconcile_and_commit` / `activation_payload` / `envelope`) now take `&dp::RealityId`; `spine.rs` passes `session.reality_id()` — **taken from the `SessionContext` the loop already holds, never from a helper returning an id alone**, which is `BDR-54`'s shape and would have dropped the `plane` that keeps the capability refreshable. The two test callers bind through the existing `tests/support::verified_reality` double rather than a new one. Evidence: `cargo check` enumerated every call site; suite green (`epoch_event_contract` 4 passed, `epoch_activation_live` 4 passed — both *ran*, checked, because a test that quietly stops running is the red-for-the-wrong-reason mode); ratchet bitten 1 → 2 → 1 by reverting one signature. **Remaining: 1** — `bin/ceilings.rs`'s benchmark envelope builder, left ADOPTABLE rather than exempted on purpose: under-exempting leaves something to read, and it was outside this row's stated cell. **CLOSED 2026-08-10, 1 → 0** — see the row below | done |
| ~~`3E-CEILINGS-LAST-SITE`~~ | **CLOSED 2026-08-10, 1 → 0 adoptable, and it is an EXEMPTION whose reason is CHECKED.** The trigger allowed *"a reasoned exemption naming why a benchmark harness cannot bind"* and forbade *"a third category invented to make the number zero"* — so the reason had to be falsifiable, not well-written. **The real reason is not "it is a benchmark"**, which would be the invented category: it is that `ceilings.rs` **mints** its reality with `Uuid::new_v4()` three lines before use, deliberately (its own §Safety: *"every run uses a freshly minted random `reality_id`, so it cannot touch another run's rows"*). No `reality_registry` row exists for it, so `SessionContext::bind` would **refuse** it — the same shape as `provisioner`'s *"there is no bind that could precede the thing being created"*. Adopting would mean forging the assertion `dp::RealityId` exists to make, or provisioning a world, which makes an append-throughput measurement depend on the meta stack. **The mechanism:** a new `SELF_MINTED` table + `check_self_minted()` with four arms — the file must still contain `Uuid::new_v4()`; it must contain **no external reality source** (`--reality`, `REALITY_ID`, `Uuid::parse_str`); the prefix must name a real exemption; the prefix must match a file. Comments are stripped first, so a mention of the flag in prose is not an input. **Bitten live:** added `flag("--reality")` to `main`, gate reds `SELF-MINTED CLAIM VOID … it now reads one from outside: ['--reality']`, restored, green, harness diff empty. **The reclassification could not be silent** — the gate refused adoptable 1 → 0 *and* exempt 0 → 1 until the baseline recorded both, and the total stayed 57. `--self-test` now also prints the retirement notice it was written with: adoptable is zero everywhere, so **the exemptions are the whole story**, which is precisely why this one is checked | done |
| ~~`W5-REMEDIATE`~~ | **CLOSED.** `orphan_scanner --record` writes findings through a new bridge endpoint. **`reality_close_audit` turned out to be the WRONG sink** and R13 §12L has been wrong about it since migration 005: its `event_type` is a closed enum of six close-lifecycle values (no orphan class) and its `reality_id` is `NOT NULL`, which the untracked-database class by definition has none of. New table `orphan_scan_finding` (038), keyed by the database — the one field every class names | done |
| ~~`W5-CRON`~~ | **CLOSED.** An `orphan-scanner` compose service runs it hourly and records through the bridge. Deliberately NOT another cron-manifest YAML: `scripts/archive-worker-cron.yaml` says of itself that its scheduler binding is deferred, so it is a schedule nothing reads — the same apparatus-without-a-subject shape this row exists to kill | done |
| ~~`W7-SHELL-UNCOVERED`~~ | **CLOSED 2026-08-10 — the shell-level bite harness exists: `scripts/db-ensure-bite-gate.py`, 4/4 bitten.** ~~036/037 down-migration guards~~ discharged by `META-DOWN-UNCOVERED` (both downs run and re-run; `036`'s data-loss guard bitten with a real user-owned reality). ~~The injection fix~~ — **the live leg is the strongest evidence in this run: with `:'pw'` in place the payload `x'; ALTER ROLE … SUPERUSER; --` is refused (`rolsuper = false`); with the binding removed THE SAME PAYLOAD GRANTED SUPERUSER.** The fix is proven load-bearing by making the vulnerability come back. It runs the pipeline **extracted from `db-ensure.sh` itself**, not a retyped copy, against a throwaway role — the real `loreweave_provisioner` owns the reality databases, so Postgres would refuse to drop it and the script's `if ! role exists` branch can never be reached on a booted cluster. ~~The column-level GRANT~~ and ~~the over-privilege assert~~ carry static paired-anchor legs, each bitten. ~~the `main.go` nil-owner guard~~ **also closed**, and it was the only one of the four with no witness at all: `TestProvisionRequest_RejectsNilUUID` covers the *reality* id, not the *owner*. `cmd/admin/provisionowner_test.go` adds the pair — the nil owner is refused, **and a real owner gets past the guard** (`NV-2`: a single-sided test proves the handler errors, not that the GUARD errored). Bitten by replacing `if owner == uuid.Nil` with `if false`: the nil owner then flowed past and died in the subprocess invoker instead, which the test caught and named. **The silent failure it prevents is a tenancy downgrade reported as success** — the invoker drops the flag when the value is nil, so the operator would get a platform-owned reality and a cheerful message | **all four covered.** The next shell/Go guard added to this path earns a leg in the same two harnesses |
| ~~`META-DOWN-UNCOVERED`~~ | **CLOSED 2026-08-10.** The validator now walks **both** trees — `PASS — 116 file(s) across 2 tree(s)` (38 + 78) — and its logic moved to `migration-idempotency-validator.py` behind the existing `.sh`, which stays the entry point because two CI legs name it. **Pointing it at the meta tree was not enough**: every check was a `grep` anchored to one LINE, and 8 of 13 `ALTER TABLE … COLUMN` statements across both trees are multi-line, four in the tree it already walked. Statement-aware now, plus a per-tree file **floor** (a walk that finds nothing exits **2**, not 0) and a new check for the `DROP CONSTRAINT IF EXISTS` idiom that 7 of 9 sibling migrations already used. **8 real violations found and fixed, all in `036`/`037`.** Down migrations run and RE-run clean against a throwaway meta DB (39 ups applied, both downs ×2, exit 0, columns gone), the ups are retry-safe, and `036`'s data-loss guard still refuses when a user-owned reality exists — verified by inserting one. See `BDR-61`/`BDR-62` | done |
| ~~slice 1~~ | **RE-MEASURED 2026-08-10 and the row was stale in almost every clause.** Each `G` claim checked against the tree rather than trusted: **`G4`** — `D-DP-CLIPPY-NOT-BUILT` was discharged by slice 2 (`dp-clippy`, two lints, ratcheted CI gate), and the aggregate contract is enforced by `tests/aggregate_contract.rs` over a real `syn` AST, which is stronger than the lint the row asked for. **`G7`** *"clippy has no CI home at all"* — false: `foundation-ci.yml` has a `dp-contract` job running `cargo clippy -p dp --all-targets -- -D warnings`. **`G8`** *"`cargo test -p dp` runs only on a PR to `main`"* — false: `dp-contract` is **unconditional**, and its own name says *"all branches"*. **`G9`** *"five `.stderr` pins float on `@stable` with no toolchain file"* — false: `rust-toolchain.toml` exists AND the job pins `toolchain: "1.89.0"` with a comment giving this exact reason. **`G10`–`G13`** — `DP-F7`'s second copy of `DP-S5`'s numbers is compared by `dp_f7_rate_limits_match_dp_s5_ceilings`; the `fifth_tier.stderr` misstatement and the `tier.rs`/`DP-A5` misattribution are both corrected in place. **`G6`** was the only live one, and its stated fix was wrong — see `BDR-70`. **`G3` is CLOSED** (row above): re-measured 2026-08-10 by `dp-oracle-coverage-gate`, **13 of 26 read, 13 unopened** — `05_control_plane_spec.md` among the read ones, which was the point. The thirteen still unread are `00_preamble`, `01_scope_and_boundary`, `11_access_pattern_rules`, `14_durable_subscribe`, `15_turn_boundary`, `16_bubble_up_aggregator`, `18_causality_and_routing`, `19_privacy_redaction_policies`, `20_operational_residuals`, `21_llm_turn_slot`, `22_feature_design_quickstart`, `99_open_questions`, `_index` — **and the ratchet is what keeps that number honest now, so it is a worklist rather than an unknown.** `G4`'s stated blocker — *no dylint anywhere* — was discharged by slice 2; the specific aggregate-contract lint is still unwritten | `2026-08-06` run-state §6i |
| ~~slice 2~~ | **CLOSED 2026-08-09 (row was stale).** It said *"board not written"* and *"no dylint anywhere"*; the board IS written below and `2A`–`2G` are all ✅ — `lints/dp-clippy` ships two lints (`forbid_raw_kernel_client`, `forbid_swallowed_backpressure`) on a pinned nightly with a ratcheted CI gate. **The row outlived its subject by four slices**, which is the register rot this file keeps finding elsewhere | done |

</details>

<details>
<summary>CLOSED SLICES 2-5 + the post-slice-5 review — the boards, the evidence and the refutations, kept whole. Read for a decision's history, not to find the next action.</summary>

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
| `3E.2` | migrate `commit-service` (3) then `world-service` (73) | ✅ **world-service: 0 adoptable** (52 structurally exempt + 2 input-boundary), classified below and re-measured 2026-08-10. ⚠ **`commit-service` is NOT 0 — it is 5**, and the "3 → 0" recorded here was measured by a gate that could not see the crate: it matched `reality_id:` and the field is spelled `reality`. Four of the five are `epoch_commit.rs` on the live write path. Tracked as `3E-EPOCH-COMMIT-ADOPTION` in §4; see `BDR-63`. **The row is left visible rather than rewritten, because "3 → 0" was the reading that made this file believe the crate was finished** |

> ### ⚠ `world-service`'s 73 sites are NOT mechanically adoptable, measured 2026-08-09
>
> The plan treated the remainder as a bulk rename. It is not, and the reason is
> structural rather than effortful.
>
> **A `dp::RealityId` asserts a specific fact: the control plane confirmed this
> reality EXISTS and ACCEPTS COMMANDS.** `MetaControlPlane` refuses
> `Provisioning`, `Frozen`, `Archived`, `SoftDeleted` and `Dropped`. Now look at
> where the sites actually are:
>
> | file | sites | what it does |
> |---|---|---|
> | `provisioner.rs` | 10 | CREATES the reality. `ProvisionRequest.reality_id` is documented *"caller-generated"*, and `register_pending` INSERTs it with `status=provisioning` |
> | `reality_seeder/*` | 22 | seeds a reality that is not yet open |
> | `deprovisioner.rs` | 7 | DROPS the database of a reality being torn down |
>
> **Roughly half the sites are lifecycle code whose entire job is realities that
> do not accept commands.** Binding one is not merely unimplemented — it is a
> contradiction, and forcing it would mean either weakening
> `accepts_commands()` (breaking the guarantee for everyone) or minting an
> unverified `RealityId` (breaking the one property `forged_reality_id.rs`
> pins).
>
> **ALL 73 CLASSIFIED (2026-08-09), because a sample is not a measurement:**
>
> | class | ≈sites | why it cannot hold a verified `RealityId` |
> |---|---|---|
> | **lifecycle** — `provisioner*`, `reality_seeder/*`, `deprovisioner`, `bin/provision` | ~50 | the reality is `provisioning`, being seeded, or being dropped. `provisioner.rs` *"INSERT into reality_registry with status=provisioning"* — a status the control plane refuses |
> | **ops / maintenance** — `rebuild/*`, `orphan_scan`, `bin/replay-aggregate` | ~13 | runs against realities in ANY state, deliberately. `rebuild/mod.rs`: *"the reality MUST stay frozen and an operator inspects the dead letter."* `orphan_scan` lists `"frozen"` among what it handles |
> | **embedding queue** — `embedding_queue/*` | ~10 | the only plausible live-serve candidate |
>
> **So roughly ten of seventy-three could hold one.** The other ~63 are code
> whose subject is precisely a reality that is NOT accepting commands — which is
> the exact fact a `RealityId` asserts. This is not effort and it is not
> "unbuilt infrastructure" (§0.3's gate #4, which this project treats as the lazy
> tell): it is a type asserting something false about its subject.
>
> **The real finding is about `world-service` itself.** `DPA-SCOPE` names it
> game-layer because it touches per-reality databases. But what it DOES —
> provision, seed, rebuild, scan, deprovision — is lifecycle and operations, not
> gameplay. `01_scope_and_boundary.md` §4 scopes DP-R3 by the DATABASE, and that
> is right for DP-R3; the `RealityId` adoption question is a different one and
> the database test does not answer it.
>
> **RESOLVED 2026-08-09 — the gate was measuring the wrong thing, and that was
> the defect to fix.** It reported 73 in a way that reads as debt, when ~62 of
> those could never be paid. A ratchet whose target is unreachable is a CEILING
> wearing a ratchet's name.
>
> * **The count is split**: `adoptable` (ratcheted toward zero) and
>   `structurally exempt` (each entry carrying a REASON, length-checked, the
>   same shape `dp-clippy-gate` uses for `plane = "platform"`). Exempt is **not
>   a hole**: those files are still counted, still baselined, and still FAIL on
>   growth. A phantom exemption — one matching no file — is itself a failure.
> * **`world-service`: 11 adoptable → 0.** The embedding-queue runtime path now
>   takes `dp::RealityId` end to end, and `bin/embedding_worker` BINDS through
>   the real `MetaControlPlane` before draining, using the meta pool it already
>   opened for its audit trail. A worker pointed at a frozen or archived world
>   now refuses at startup.
> * **`IN_SCOPE` was NOT narrowed.** That was the alternative on the table and
>   it would have made 62 sites vanish with nothing left to read. The
>   classification is visible, reasoned and reviewable instead.
>
> **The rejected alternative, recorded:** giving lifecycle code its own newtype
> (`RealityRef`). A newtype over `Uuid` that verifies nothing is naming, not
> safety — 62 sites of churn to document what the plain type already says. Its
> trigger should be a real confusion bug, not tidiness.
>
> **Not decided here, and deliberately not:** narrowing a gate's scope is
> exactly the move that needs a reason on the record rather than a quiet edit,
> and §0.6c's `3E` seal says the reversal trigger is *"the count falls below
> ~50, at which point one commit is reviewable"*. The count is 73. The ratchet
> holds it there and fails on any increase.

### Slice 4 — the tier-typed write surface (gated on `3D`)

Sealed prerequisite met: `REC-65` is mechanised (`ff118081b`). Do **not** start
before `3D`, because every signature takes `&SessionContext`.

| step | what | done = |
|---|---|---|
| `4A` | `cache_key!` (`DP-R4`) | ✅ reality-scoped form; tier checked by construction (`E0271`), `KeyId` refuses `:` and empty; channel form deferred |
| `4B` | `t0_write`..`t3_write` typed by the tier marker traits | ✅ `DP-R5` held by rustc (`E0271`), bitten |
| `4C` | `read_projection_*` per `04b` | ✅ scope held by rustc (`E0271`), bitten; `Decode` split from `DpAggregate` |
| `4D` | `dp-clippy` `R-6` (`forbid_swallowed_backpressure`) | ✅ **BUILT** — fires on exactly 3 of 5 fixture cases; armed, zero workspace subjects yet |

#### `4D` — BUILT, and the "no subject" reasoning was wrong

**The PO overruled the park, and was right.** `4D` was parked twice on the
grounds that `R-6` would be "green by emptiness". §0.3 is what settles it: a
blocker is something EXTERNAL you cannot write. *"It would flag nothing today"*
is not that. The rule the lint enforces is not made truer or falser by how many
violations currently exist — and a rule armed **before** the first adopter is
strictly better than one armed after, because the first adopter is exactly who
would otherwise establish the pattern.

**What it does.** Flags `.ok()`, `.unwrap_or_default()` and
`.unwrap_or_else()` on any `Result<_, DpError>`. Deliberately the whole error
type rather than only the two backpressure variants: a `Result` is not a
variant, and nothing at this level can know which variant a call may return.
Flagging the DISCARD is the decidable question, and `DpError::is_backpressure`
remains the single home of the `{RateLimited, CircuitOpen}` set so the lint
never mints a second copy.

**Non-vacuity is a COUNT, not a boolean.** `fixtures/swallower` holds five
functions: three discards, one discard of a `Result` whose error is *not* a
`DpError`, and one that propagates. The self-test asserts **exactly 3** —
"it fired" would also be true of a lint that flagged all five. Bitten: removing
the receiver-type check yields *"R-6 MISCOUNTED: 4 finding(s), expected 3"*.

**Zero workspace subjects, measured and stated.** `dp-clippy-gate` over all 29
members reports the same 8 `DP-R3` findings and no `R-6` findings, because no
crate outside `crates/dp` yet holds a `Result<_, DpError>` to discard. The lint
is armed for the first one — which is `3E`'s adoption.

**A structural change came with it.** Two lints cannot each emit their own
`register_lints`: `dylint_linting::declare_late_lint!` bundles the library entry
point with the lint, so the second invocation re-defines it (`E0259`/`E0428`).
The entry point is now written out, and the self-test gained a leg asserting the
library still loads — because a silently-dropped `register_late_pass` would
leave one rule inert while every other leg kept passing.

#### The superseded reasoning, kept because it was wrong in an instructive way

`R-6` flags `.ok()` / `unwrap_or_default()` applied to a `Result<_, DpError>`.
After `4B`/`4C` that type finally exists on a real surface, so the lint has
something to *match*. What it does not have is a **call site**: every caller of
`t2_write` / `read_projection_reality` today is a `#[cfg(test)]` fixture inside
`crates/dp`, because no crate depends on `dp` yet.

**This is NOT the `4B` mistake repeating.** The difference is what the missing
piece is. `4B` was missing *code I could write*, and calling that a blocker was
the lazy tell. `4D` is missing *other people's call sites*, which arrive when a
service adopts the SDK — and that is `3E`, which is itself ordered after slice 5.
Writing the lint now would produce a rule that is green on the whole tree, and
this run has already removed five mechanisms with exactly that shape.

**The cheap half is already done, and deliberately:**
`DpError::is_backpressure` exists and is the set `R-6` must key on, so the lint
cannot mint a second copy of `{RateLimited, CircuitOpen}` that drifts.
`crates/dp/src/write.rs`'s own test asserts backpressure is returned rather than
swallowed — the property `R-6` will police, proven at the one place that can
prove it today.

**Trigger:** the first crate outside `crates/dp` that calls a `dp` primitive.

#### ⚠ `4B` WAS PARKED FOR AN HOUR, AND THE PARK WAS WRONG

The park cited three prerequisites. **All three were things I could write**, which
§0.3 names exactly: *"saying 'blocked' when you mean 'I'd have to build it' is the
lazy tell this rule exists to kill."* Recorded rather than quietly deleted,
because the failure was using the goal's own escape hatch on work that was in
reach — satisfying the letter while lowering the bar.

| the claim | what was true |
|---|---|
| *"`DpAggregate` has no `Delta` — a contract change, four real impls, five trybuild pins, its own slice"* | Measured after the PO pushed back: **all impls are test fixtures inside `crates/dp`**, ten of them, and `DP-K1`'s `Aggregate` **has specified `Delta` and `Projection` from the start**. Adding them closed a gap this crate opened, and took one edit plus a `.stderr` regeneration |
| *"there is no backend seam"* | I had written `ControlPlane` — the same kind of seam — ninety minutes earlier. `WriteBackend` is that move again |
| *"`DP-K5` is async"* | A fork §0.6c says to SEAL and act on. Sealed: **async belongs to the backend impl, not to this contract crate.** The seam is sync; a consumer wanting async implements it on an async client |

**What `4B` actually proves today.** `DP-R5` — *no cross-tier mixing in a single
write* — held by the type checker: `t2_write` is bounded `A: DpAggregate<Tier =
T2>`, so a `T3` aggregate down the `T2` path is `E0271` at the call site. That
matters because it does **not** fail loudly — it succeeds with a weaker
durability promise than the aggregate was designed for, and the loss surfaces
later as a read that should have been impossible. Also proven: the session is
checked **before** the backend is touched (a write rejected after it is applied
is not a rejection), and backpressure is returned rather than swallowed.

**What it does not prove, stated plainly:** nothing in production writes through
this surface. The only `WriteBackend` implementor is a `#[cfg(test)]` spy, the
same standing `ControlPlane` has.

**`dp-aggregate-gate` refused the first version**, and correctly by its own
lights: the four primitives were generated by a `macro_rules!`, and `R10` rejects
any macro body mentioning `DpAggregate` because `syn` cannot see whether it emits
an impl. Over-broad here — it emitted functions — and still the right default.
Written out longhand instead; **weakening a guard four refutation rounds hardened
to buy back a macro is the trade this repo exists not to make.**

**`4D`'s subject note stands.** `R-6` flags `.ok()` over a `Result<_, DpError>`,
and the write surface now returns exactly that — so the lint has a subject the
moment feature code calls it. Ordered after `4C` rather than parked.

### Slice 5 — `DpControlPlane`. Board written at the slice's start (`BDR-26`).

**Phase 0 measured two things that decide the shape:**

- `DP-C3` specifies a **gRPC service with 13 RPCs** (session/capability lifecycle,
  tier policy, reality registry, channel tree, writer leases — half of them
  streaming).
- **This repo has no gRPC anywhere.** `grep tonic|grpc` over every `Cargo.toml`
  in `crates/` and `services/`: zero hits. There is also no capability store in
  `migrations/meta`.

That is gate #2 — *large/structural, write a plan* — **not** blocked. §0.3 also
requires the decomposition, and it is the useful part here: **`3E` does not need
the service. It needs ONE production `ControlPlane` implementor**, so that a
crate can obtain a `RealityId` without forging one. The reality registry already
exists and holds 7 rows.

| # | row | done = |
|---|---|---|
| `5A` | **a real `ControlPlane`** over `reality_registry` | ✅ `d82cf4671` — LIVE bind against the real registry; the run caught an `INT2`/`INT4` decode bug no mock could reach |
| `5-WIRE` | **`dp-kernel` behind `WriteBackend` + `ReadBackend`** | ✅ `7f88dcd59` — end-to-end `t2_write` → `EventStore`, event read back and asserted |
| `5B` | the capability STORE — `RefreshCapability` needs one; today a capability is minted and never recorded. **Bearer + lookup, sealed above**, and it carries a second obligation: **`BindRequest` gains the calling service identity**, because today `bind` authenticates nothing | ✅ migration `039_session_registry` (5 annotations) · `session_store.rs` + `PgCapabilityStore` writing through `meta_write` (audit row same-TX, asserted live) · `ServiceIdentity` · the `DP-C8` amendment written · `dp-slice5b-bite-gate` **7/7** + **2 live SQL bites** · LIVE: bind → validate → revoke → re-validation refused, against real Postgres |
| `5C` | the gRPC surface (`DP-C3`) — `tonic`, protos, the non-channel RPC groups. **In scope**, sealed above | ✅ `contracts/proto/dp_control_plane.proto` (the contract; server AND client generated from it) · `crates/dp-control-plane` · 9 tests over a **real TCP socket** · `dp-slice5c-bite-gate` **7/7** · `I11` ACL rows for the 6 served RPCs · `UNIMPLEMENTED_METHODS` asserted against the running server |

**`I1` — settled with evidence, and the answer is that it does not apply.** `I1`
governs *"all **external** traffic… no service accepts direct **public** traffic"*,
enforced by *"AWS security groups expose ONLY `api-gateway-bff` and `game-server`
to the public subnet"*. `DP-C3` specifies *"gRPC over mTLS **between CP and game
services**"* — service-to-service, inside the cluster, no third public listener.
So `5C` neither amends nor violates it, and **`I11` is the invariant that does
apply**: every inter-service RPC needs an ACL row naming allowed callers and
principal mode. Those rows are in `contracts/service_acl/matrix.yaml` as
`control-plane-rpcs`.

**The count in this row was wrong and is corrected.** `DP-C3` lists **26** RPCs in
**10** groups, not 13; the non-channel surface is **six** groups and **14** RPCs,
not four. The proto covers all fourteen. `crates/meta-rs/src/control_plane.rs`
carried the same wrong figure and is fixed.

**Six of the fourteen are served; eight return `UNIMPLEMENTED` naming the missing
table** — `tier_policy`, `tier_capability`, `npc_binding` and `schema_version` are
absent from every migration, measured. A contract may declare more than today's
server can serve; a MODEL may not, which is why they are RPCs and not tables.
`UNIMPLEMENTED_METHODS` is compared to what the running server actually refuses,
so the list cannot rot in either direction.

**What `5C` is NOT:** a deployable `services/control-plane-service` binary. That
needs a capacity budget (`I17`), an SLO row, timeouts (`I16`), an observability
inventory (`I19`) and a security-group manifest — a deployment story, not a
transport. Its trigger is the first out-of-process caller.
| `5D` | channel tree + writer leases (`DP-A16`, `DP-Ch9`) — **this is what produces `ChannelId`**, and therefore what retires four DEFERRED registers at once | ✅ `dp::ChannelId` (i64, ADOPTED from `dp-kernel`, which now re-exports it) · `ChannelTree` + `SessionContext::move_to_channel` (the producer) · `channel_key` · `read_projection_channel` · `DEFERRED_IDS`/`_SESSION_FIELDS`/`_CACHE_FORMS` **deleted**, `_READ_FORMS` 3→2 · `dp-slice5d-bite-gate` **8/8** including a bite proving the shrink rule itself still fires · `channel-id-adoption-gate` ratchets the 22 remaining `unverified` sites |

> ### ⚠ `5D`'s PREMISE IS WRONG, found by Phase 0 on 2026-08-09 — read this before starting it
>
> This board says `5D` *"is what produces `ChannelId`"*, and `crates/dp`'s
> `DEFERRED_IDS` says the same: *"nothing mints a `ChannelId`"*. **Something
> does.** `crates/dp-kernel/src/channel.rs` (425 lines) has shipped a
> `ChannelId`, a `WriterLease`, a `ChannelWriter` and a `HeldLease`, with two
> integration tests (`integration_channel_writer.rs`,
> `integration_writer_lease.rs`), migration `0014_channel_ordering`, and a
> `channels` table in `0019_channels`.
>
> **And the two `ChannelId`s disagree about their representation.**
> `dp-kernel`'s is `ChannelId(pub(crate) i64)`; `DP-Ch1` specifies a `Uuid`.
> That file already argues the case and calls it settled — *"the spec says
> `Uuid`; the build, the wire contract (`Uint64String`) and `DP-Ch11`'s
> allocator all say 64-bit, and two of three win — `i64` is adopted into the
> spec"* — so `5D` must NOT mint a second, `Uuid`-shaped `ChannelId` in
> `crates/dp`. Two types with one name, differing in representation, is the
> `pc_*`/`npc_*` shape with a compiler behind it.
>
> `dp-kernel` also carries `ChannelId::unverified(raw: i64)`, documented as a
> **PRE-SDK SEAM** whose own doc comment says: *"when `crates/dp` lands this
> function is deleted and the compiler enumerates the migration.
> `rg 'ChannelId::unverified'` is the worklist."* `crates/dp` has landed. That
> sentence is `5D`'s actual first task, and it is a worklist somebody already
> wrote.
>
> **So `5D` is not "build a channel tree". It is: adopt the EXISTING one into
> `crates/dp`, delete the unverified seam, and reconcile `DEFERRED_IDS` with the
> `i64` decision.** Scoping it as new construction would rebuild what exists —
> the exact failure `Phase 0` question 1 was added to catch, after the actor-hub
> round designed feature #1 without auditing what already modelled an actor.
>
> **DONE 2026-08-09, with two deviations from the plan above, both stated:**
>
> 1. **`ChannelId::unverified` is RATCHETED, not deleted.** 22 call sites remain.
>    Deleting it in one commit means routing every one through a real tree, and
>    for the unit tests among them that means inventing a fake tree — trading an
>    honest escape hatch for a dishonest verification. §0.6c already sealed the
>    shape for `3E`: *a ratchet, never a big bang.*
>    `scripts/channel-id-adoption-gate.py` + `contracts/dp/channel-id-baseline.json`
>    fail on an increase and on an unrecorded decrease. The doc comment that had
>    promised deletion "when `crates/dp` lands" had been wrong since slice 1 with
>    nothing to say so — a worklist in a comment is a worklist nobody runs, which
>    is why this is a gate.
> 2. **`session_registry.current_channel_id` is still absent, and stays absent.**
>    `move_to_channel` is an SDK-side operation; nothing writes a session's
>    channel back to the control plane, because `DP-Ch9`'s CP-side RPC lives in
>    the four CHANNEL groups that `5C` deliberately left out of the proto. Adding
>    the column now would be a column NULL in every row — the orphan shape with a
>    schema. Its trigger is the channel RPC group.

---

## POST-SLICE-5 DATA-PLANE REVIEW — 2026-08-09

Adversarial pass over everything slices 3–5 built. Three findings; one fixed
here, two tracked with mechanisms. **Each mechanism is a thing that changes
colour by itself** — the deferral rule this repo learned the hard way is that a
row and a promise are not a mechanism.

### ✅ `D-DP-CAPABILITY-NOT-VALIDATED-ON-DATA-PATH` — CLOSED 2026-08-09, and the review had the remedy wrong

**The finding was right; the proposed fix was not.** The text below says it needs
a change to the `WriteBackend`/`ReadBackend` seam. It does not, and `DP-C3` says
why in one line: the control plane is *"low-QPS (≤100/s global)"*. Validating
every write would exceed its own budget by orders of magnitude, so per-write
validation was never the design. `DP-C8` states what is: *"Short expiry (5 min)
bounds blast radius — no explicit revocation list needed in the normal case."*

So the revocation window is closed by **TTL + refresh**, not by a seam change:

* **`DEFAULT_CAPABILITY_TTL_MS` 15 min → 5 min.** It had shipped at three times
  the spec, which states 5 in three independent places. That constant IS the
  revocation window — the upper bound on how long a revoked session keeps
  writing — so the drift was the finding's actual magnitude.
* **`dp::CapabilityRefresh` + `SessionContext::refresh_if_due`**, with
  `REFRESH_LEAD_MS = 60_000` (`DP-K10` step 4: *"refresh 60s before exp"*).
  Implemented by `MetaControlPlane` and `GrpcControlPlane`.
* **`spine` calls it every drain iteration and FAILS CLOSED** — the `?` is the
  mechanism. An operator who revokes a session gets a writer that stops.
* A `const` assertion in `meta-rs` ties the two numbers together, because
  `crates/dp` sets the lead and never sees a TTL: a lead at or above the TTL
  makes every capability due the instant it is issued.

*Evidence:* 4 new bites (11/11 on the capability gate) · live Postgres —
*"session … refreshed while live, refused after revocation"* · and the
`#[expect(dead_code)]` that carried this id **fired**, exactly as designed:
`refresh_if_due` presents the secret, the build reported the expectation
unfulfilled, and the pragma came out. A mechanism that removed itself when the
debt was paid.

*What remains genuinely out of scope, and is not a deferral:* per-write
validation. It is not unbuilt — it is ruled out by `DP-C3`'s own scale contract.

<details><summary>the original finding, kept for the record</summary>

#### `D-DP-CAPABILITY-NOT-VALIDATED-ON-DATA-PATH` — as first written

`5B` built capability validation and `5C` exposed bind/refresh. **Nothing calls
`validate_capability` outside tests**, and the data path cannot: neither
`WriteRequest` nor `ReadRequest` carries a capability, so no backend has one to
present.

What `dp::SessionContext::check_live` actually does is the CLIENT checking **its
own copy** of an expiry it was handed. That catches an honest expiry. It cannot
catch a revocation — so `revoke_session`, which `5B` made immediate and
single-session at the control plane, **has no effect on the data plane at all**.
A revoked session keeps writing until its local expiry (default 15 minutes).

*Why it is not fixed here:* the fix changes the `WriteBackend`/`ReadBackend`
seam — the contract `4B`/`4C` sealed and `5-WIRE` implemented — and adds a
control-plane round trip to every write. That is a design decision about the
data path's hot loop, not a patch, and it interacts directly with the sealed
bearer-capability deviation's cost.

*Mechanism:* the `#[expect(dead_code)]` on `CapabilityToken::secret` and
`SessionContext::capability` now names **this id** as its reason. Those items
are dead precisely because no backend takes a capability; the day one does, the
expectation goes unfulfilled and the build fails, carrying this id in the
message. Verified by bite — adding a caller produced
`this lint expectation is unfulfilled … D-DP-CAPABILITY-NOT-VALIDATED-ON-DATA-PATH`.

</details>

### 🟠 `D-DP-ORPHANED-CAPABILITY-ON-REJECTED-BIND`

`MetaControlPlane::verify_bind` records the capability **before** returning —
correctly, since handing out an unrecorded one is worse. But
`SessionContext::bind` can still reject afterwards, on `now_ms >= expires_at_ms`.
Since the control plane mints `now + ttl` on **its** clock and the caller checks
against **its own**, a caller more than one TTL ahead rejects a capability that
is already in the store. The row is live, its secret was dropped on the floor,
and nothing will ever present it.

Not a security hole — an unpresentable row — but rows accumulate, and the shape
(a store write whose caller can still fail) is worth a name.

*Mechanism:* `session_registry` carries `@retention_hot: 90d`, so these rows are
already inside a retention regime rather than growing forever. The waking
trigger is the first retention sweep that reports a non-trivial count of rows
never validated — which needs a `last_validated_at` column, and that column
arrives with the fix above.

### ✅ FIXED IN THIS PASS — a pragma whose reason had already expired

Both `#[expect(dead_code)]` attributes read *"slice 4's write surface presents
it; unfulfilled the day it does."* Slice 4 shipped, slice 5 shipped, and both
items are still dead. The **mechanism** was sound; the **reason** named an event
that had already passed without producing the effect — the *escape hatch cannot
reach its reason* shape from `non-vacuity.md`. Re-pointed at the real trigger,
which is how they became the mechanism for the finding above rather than a note
beside it.

### What the review checked and found sound

* `RealityId` / `SessionId` / `NodeId` / `ChannelId` — no forging path; the two
  compile-fail fixtures still pin `E0603` + `E0624`.
* Scope bounds pinned in BOTH directions after `5D`'s mirror.
* The digest, not the secret, is what `session_registry` stores; the `Debug` impl
  redacts; the gRPC layer collapses "never issued" and "revoked" into one status
  so the endpoint is not an oracle.
* `refresh` is CAS'd against the read expiry AND `revoked_at IS NULL`, proven
  live.
* Every `UNIMPLEMENTED` RPC is compared against the running server.

---

**Two findings `5B`'s Phase 0 handed to `5D`, recorded rather than silently fixed:**

1. **`DP-Ch32`'s auto-dormant scan spans two databases.** Its SQL joins `channels`
   (PER-REALITY) against `session_registry` (META) in one statement:
   `AND id NOT IN (SELECT current_channel_id FROM session_registry WHERE active = true)`.
   That cannot run once the two live in different databases, which `039` has now
   made concrete rather than hypothetical. `5D` owns the resolution — most likely
   the CP reads the live session set and passes it in, rather than the query
   reaching across.
2. **`session_registry.current_channel_id` is deliberately absent**, because
   nothing produces a `ChannelId` (§0.6c). `5D` is its producer and therefore
   owns adding the column. The migration header names it, and
   `DEFERRED_SESSION_FIELDS` in `crates/dp/src/session.rs` already reds when the
   producer lands.

**And one `5B` handed to `DP-C4`:** `tier_capability` — the table that decides
whether a service may touch an aggregate — has **no producer** in this repo. Its
rows come from *"a deploy manifest calling CP's admin API"* (`DP-C4`), which does
not exist. Until it does, `bind_session` records **who asked** and does not decide
**whether they may**, and the `DP-C8` amendment says so in the spec. Its trigger
is the admin API arriving; building the table before that is the orphan shape.

**`5A` is the whole unblock.** It closes `3E` (adoption becomes possible), which
closes `4D` (the lint gains call sites). `5B`–`5D` are the rest of `DP-C3` and do
not gate either.

**Where `5A` lives — decided, not left open.** Not `crates/dp` (declares no I/O).
`crates/meta-rs` is the natural home: it is the Meta Access Library, it already
reads the registry and resolves routing, and it is the crate whose job is
answering *"where does this reality live and may you reach it"*. It would take a
new `dp` dependency — acceptable, since `dp` is a contract crate with no I/O of
its own, so the platform-plane crate stays platform-plane.

---


</details>

## 5 · REGISTERS

Decisions, parked, debt and **`BDR-1`..`BDR-48`** live in
[`2026-08-06-game-tier-build-RUN-STATE.md` §7](2026-08-06-game-tier-build-RUN-STATE.md). Append new
drift there or here; **a run that ends with an empty drift log is not clean, it is dishonest.**

The five that governed last run, so they are not re-learned:
`BDR-44` a fix without a leg · `BDR-45` a fix's blast radius ≠ its subject · `BDR-46` knowing a rule
does not transfer across a language boundary · `BDR-47` execute the path before verifying its parts ·
`BDR-48` "blocked" is a label, and it was the only blocker.

---

**`BDR-67` (2026-08-10) — the test that already existed was for the wrong nil.**
`W7-SHELL-UNCOVERED` listed the `main.go` nil-owner guard as untested, and a grep for `uuid.Nil` in
`admin-cli` finds `TestProvisionRequest_RejectsNilUUID` — which looks exactly like the coverage in
question and is about the **reality id**, not the **owner**. Two guards, two nil UUIDs, one search
term. The row was right and the grep would have talked anyone out of it. **When a row says
something is uncovered and a search says otherwise, check WHICH subject the hit covers** — this is
`NV-1`'s "the subject cannot vary" wearing a plausible test name. The guard it protects fails
*upward*: the invoker drops the flag when the owner is nil, so accepting it yields a platform-owned
reality and a success message — a tenancy downgrade that reports as a win.

**`BDR-66` (2026-08-10) — the strongest security evidence available is making the vulnerability come
back.** `W7`'s injection fix had been *"verified only by hand"* for two days. The static check —
*does `db-ensure.sh` contain `:'pw'`* — is worth little: it says the fix is spelled, not that it
works. `db-ensure-bite-gate`'s live leg runs the pipeline **extracted from the script** with
`LOREWEAVE_PROVISIONER_PASSWORD` set to the payload from the script's own comment, twice: bound
(`rolsuper = false`) and then with the binding removed (**SUPERUSER granted**). Only the second run
makes the first one mean anything — without it, "the payload did not escalate" is equally consistent
with the payload never reaching the statement. Two things had to be reasoned about first, and both
would have been incidents: the real `loreweave_provisioner` **owns the reality databases**, so
`DROP ROLE` fails and the script's `if ! role exists` branch is unreachable on any booted cluster;
and the injection must be attempted against a **throwaway** role, dropped in a `finally`.

**`BDR-65` (2026-08-10) — two defects in one harness, and the harness caught both.**
`db-ensure-bite-gate`'s first run scored its own first leg `THE CHECK IS NOT LOAD-BEARING` and its
live leg `NOBUILD`. Neither verdict was about `db-ensure.sh`:

* the mutation anchored on `:'pw'`, whose **first occurrence is in the comment explaining the fix**,
  twenty lines above the statement — so a first-occurrence replace edited prose and the code never
  changed. `BDR-56`, arriving in the file written to apply `BDR-56`. Re-anchored on
  `PASSWORD :'pw' CREATEDB`, which exists only in the DDL.
* `subprocess.run(..., text=True, input=…)` on Windows writes stdin through a `newline=None`
  wrapper, so every `\n` became `\r\n` and bash read `PROVISIONER_ROLE=lw_bite_provisioner\r`. Same
  family as §0.6's *"heredocs eat backslashes"*, one layer down. Fixed by passing **bytes**.

Worth keeping for the shape rather than the details: **both presented as "the guard is broken" when
the harness was broken**, and the four-way verdict is the only reason they were distinguishable —
`nobuild` named the second one outright, and the first was found by asking *why* it went green.

**`BDR-64` (2026-08-10) — I presented a POST-REVIEW and then STOPPED, and §0.6b calls it "a
presentation, not a question".** Three rows were complete, the sweep was green, and the honest next
action was `3E-EPOCH-COMMIT-ADOPTION` — a row I had just written, with a trigger I had just
established as fired (§0.6c reverses at ~50 sites; this was 5). Instead the turn ended on *"I'm
presenting here first rather than starting it."* The rationalisation was reasonable-sounding and
wrong in a specific way: **it treated a checkpoint the file defines as a REPORT as though it were a
GATE.** The stop-condition list in §0.6d has four entries and none of them is "the work reached a
natural-looking pause." Worth recording because the failure was not forgetting the rule — the rule
was quoted, in the same message, as the justification for breaking it. **A checkpoint that produces
a presentation does not also produce a halt**, and the tell is reaching for §0.6b while the
continuation check in §0.6d has an executable answer.

The work itself then took one turn: `cargo check` enumerated every call site, and the four
signatures, one call site and two test callers were done in minutes. **The stop cost more than the
row did.**

**`BDR-91` (2026-08-11) — THE MEASURED-STATE TABLE WENT FALSE AND THE RUN THAT FALSIFIED IT
QUOTED IT APPROVINGLY ON THE WAY PAST.** Found by an audit the human asked for, three tracks and
two commits later, not by anything mechanical.

§1's row read *"`world-service` server binary: **none serving** — a 22-line `println!` scaffold; the
7 real bins are workers/drills."* **That row is what motivated the world-service track**, and by the
end of it every clause was wrong: it serves, it is not a scaffold, and there are eight other bins.
`realities in existence: 7` became 10 in the same session. Neither was updated.

Worse than forgetting. The world-service board **cites this row as evidence it was right and I was
wrong** — *"this matches the reality-layer board's own measured row, which had it right while I had
it wrong"* — written in the same hour the track made it false. Reading a fact, using it, and
invalidating it are three separate acts, and only the first two happened deliberately.

**The shape is the one this run kept diagnosing in other people's documents.**
`AS-PIPELINE-INDEX-ROT` (four of five gate rows claiming blocked what was built), `WSD-3` (a compose
file and a running container disagreeing for three days), the `world-service` README (*"Cycle 0
scaffold — no behavior"* for a crate with nine binaries), the pgvector Dockerfile comment (stale
from the hour it was committed). **Four findings of the disease and four fresh instances of it, in
one run.** The table even carries its own warning — *"Re-measure rather than trust this table if
more than a session has passed"* — which is an instruction to the reader, and an instruction to the
reader is not a mechanism.

`actor-hub-figures-gate` is the existing proof this is mechanisable: it caught five stale citations
in the very commit that added this run's last gate, because it MEASURES what a document CITES.
Generalising it from figures to claims is the open work, and it is the same row as
`AS-PIPELINE-INDEX-ROT`.

**`BDR-90` (2026-08-11) — a ONE-OFF red in the sweep, not reproduced, and recorded as unexplained
rather than closed.** The first completed `--run-all` reported
`dp-oracle-bite-gate.py RED (194.9s)` and exited 1. It is green on three subsequent runs: twice
standalone (`19/19`, rc=0, ~196s) — the second one invoked exactly as the sweep does, relative
path, `cwd=REPO`, `stdin=DEVNULL`, captured output — and once inside a second full sweep from a
clean tree (`GREEN (192.6s)`, 85 green, rc=0).

**What I did not do is call it fixed.** Nothing was changed between the red and the greens, so
there is no fix to claim; the only honest statement is that it did not reproduce.

The leading hypothesis, unproven: that sweep started ~1 minute after I killed the previous one
with SIGTERM (`BDR-89`), and **killing the Python parent does not kill its `cargo` child.** An
orphan holding `target/`'s lock would make a leg's cargo call fail, and `gate-wiring-gate`'s own
MUTATING comment says a raced harness *"reports 'did not bite'"* — a bias toward FALSE RED, which
is the direction observed. Consistent with the evidence and not established by it: I checked for
orphaned `cargo`/`rustc` processes only *before the second* sweep (none), which is the wrong side
of the event to learn anything.

**What would settle it:** if it recurs, capture the harness's own output — `gate-wiring-gate`
prints only a summary line per gate, so the leg that failed is not recoverable from the log
afterwards. That is the actionable gap this leaves: **a sweep that reports RED should retain the
failing gate's captured output**, or a one-off like this is uninvestigable by construction.

**`BDR-89` (2026-08-11) — a TIMEOUT reaches `BDR-53`'s hazard by a route the lock cannot cover,
and it leaves the mutation in the tree.** `gate-wiring-gate --run-all` takes ~25 minutes; run in
the foreground it was killed at a 10-minute tool ceiling (exit 143, SIGTERM). It left
`crates/dp/tests/spec_oracle.rs` **modified** — a bite harness had deleted
`check_deferred_write_forms();` as its one-line mutation and died before restoring — plus a stale
`target/.bite-harness.lock`.

**The `O_EXCL` lock cannot help here.** It exists to stop a *second* harness making a *first*
one's mutation permanent, and it does that well. But it is released by the process, and SIGTERM
kills the process: the lock outlives the run while the restore does not. So the tree is left
mutated **and** further harnesses are refused — the failure is loud in the second respect and
completely silent in the first.

What makes it dangerous is the timing: had I committed without re-reading `git status`, a deleted
assertion would have gone in as part of a commit about gate rigour. The mutation is a *deletion of
a check* — precisely the change a bite is designed to make, and precisely the change nobody wants
to keep.

**Two rules.** Run `--run-all` **detached**, never in a foreground call with a timeout shorter
than the sweep. And after any interrupted sweep, `git status` **before** anything else — the tree
is the evidence, not the exit code, which in this case was `143` and said nothing about the file.

**`BDR-88` (2026-08-11) — a list of tracked SECURITY holes had no shrink arm.**
`injection-coverage-lint`'s `BASELINE` is sixteen modules that assemble an LLM prompt from
retrieved text without sanitising it. Every row is an exemption from a security check, and
nothing checked the rows: a module that adopted the sanitizer kept its row, and a row whose file
was deleted kept excusing whatever next took that path. Both directions red now. Measured before
adding, so the arms are separable from today: all 16 files exist and all 16 are still flagged, so
neither arm fires on this tree — which is exactly the state in which an arm can be deleted and
nobody notices.

Recorded alongside it, a decision NOT taken: `RETRIEVED_TEXT`'s markers are `\b`-anchored and `_`
is a word character, so `retrieved_docs` and `retrieved_chunks` do not match. The tempting fix is
to widen the markers. **On this gate a false positive becomes a BASELINE row — an exemption** — so
widening trades a missed module for a standing excuse, and the evidence to justify it would be a
real unsanitised module of that shape. The limit is now a pinned self-test case rather than a
surprise, per `BDR-55`: state the property, do not move the number.

**`BDR-87` (2026-08-11) — the gate that exists to find invisible test suites could not see a
whole read form.** `test-dsn-coverage-gate`'s docstring lists five env-read spellings. Its `READ`
regex put `os\.environ\[` in the list of function NAMES and then required `\s*[(\[]` after it —
so it demanded `os.environ[[`, and **`os.environ["X_TEST_Y"]` had never matched, in every run
since the gate was written.** A suite gated by a subscript read was invisible to the gate whose
entire subject is invisible suites.

**The method that found it is the transferable part:** the self-test cases were written from what
the docstring CLAIMS the gate covers, one case per claimed form, before looking at whether the
regex implements them. Writing cases from the *code* would have reproduced the bug — I would have
written the four forms it does match. A gate's own documentation is an independent oracle, and it
is free.

**`BDR-86` (2026-08-11) — a Python rewrite silently turned a shell gate into CRLF, and a manual
green did not catch it.** Quieting `pii-classify-lint.sh`'s self-test output, I round-tripped the
file through `pathlib.Path.write_text`, which on Windows translates `\n` to `\r\n`. `bash` then
read `set -euo pipefail\r` and answered `set: pipefail\r: invalid option name`, exit 2.

The measured part worth keeping: **running `bash scripts/pii-classify-lint.sh --selftest` by hand
reported PASS; the same file, same flag, invoked as `subprocess.run(["bash", rel, flag],
cwd=ROOT)` reported exit 2.** So the corruption was invisible to the check I would naturally have
called sufficient, and it was caught by `--verify-proofs` — the mode added the day before on the
argument that a string-match proof is not a proof. It paid for itself in one day, on a defect it
was not designed for. **Use byte-level I/O (`read_bytes`/`write_bytes`) for anything a shell will
execute, and never treat a hand-run green as the environment CI will use.**

**And it happened a second time in the same hour, on a document rather than a script** — the same
`write_text` round-trip rewrote every line of `docs/sessions/SESSION_HANDOFF.md`
(`10986` added / `10969` removed for a twenty-line edit), because that file is LF in the working
copy. The consequence was not cosmetic: `citation-gate --staged` checks **added lines**, so a
whole-file rewrite handed it ten thousand lines of historical archive and it correctly refused the
commit over `file:line` citations written months ago. **A line-ending change is a semantic change
to every added-lines gate in the repo** — it does not merely produce noise, it re-opens the entire
history of a document to a check scoped to new work.

**`BDR-85` (2026-08-11) — a module-level `const` holding the document's path made a real oracle
score ZERO, and the ratchet was right.** `spec_oracle_scope.rs` opened `01_scope_and_boundary.md`
through `const SCOPE_DOC: &str = "…"`, and `dp-oracle-coverage-gate` went on reporting the document
unread. My first instinct was that the gate had a gap. It does not: the rule is *"the name appears
in a function reachable from a `#[test]` whose chain asserts"*, and a module const is a string
nothing necessarily reads — the exact difference between an oracle and a file that merely mentions
a document. The idiom every earlier oracle uses (`rules_doc()`, a reader function holding the
literal) is load-bearing, not stylistic. **Recorded because the tempting move was to widen the gate
to accept consts, which would have admitted every file that names a doc in a comment-adjacent
position** — `BDR-55`'s shape, moving the number instead of the property.

**`BDR-84` (2026-08-11) — my bite harness reported 5 of 6 working arms as SURVIVED, and it read as
a discovery.** `BDR-56` says a red for an unrelated reason is the failure mode that looks most like
success. This is its mirror at the harness level: I compared each mutated run's output against the
**gate's** problem strings (`"NOT IN SCOPE"`), while the thing actually printing was the
**self-test's own** wording (*"absent from IN_SCOPE did NOT red"*). Every arm had fired correctly.
For a few seconds the honest reading of the output was *"five of these arms are redundant"* — which
would have led to deleting five working checks.

Worse, the one arm scored **BITTEN** was scored on a **traceback**: removing the `doc.is_file()`
guard makes the next line raise, and Python prints the offending source line, which contains
`BOUNDARY RULE UNREADABLE`. A crash matched the string search. So the single "pass" was as wrong as
the five "failures". The harness now requires a line starting `FAIL: ` **and** rejects any output
containing a traceback. **Lesson: a bite harness asserts on the SELF-TEST's vocabulary, never the
gate's, and a non-zero exit is not a verdict — it is a prompt to ask which failure it was.**

**`BDR-83` (2026-08-11) — `pub use X as Y` was invisible, and the shrink arm stayed green while the
crate exported the symbol it calls unbuilt.** `crate_root_exports` split the brace list on commas
and kept a token only if every character was alphanumeric. `t3_write as t3_write_multi` contains
spaces, so it was **dropped entirely** rather than read as an export named `t3_write_multi`. The
bite is what found it: adding that alias — the precise event the register's shrink arm exists to
catch — left the oracle perfectly green. **An adjacent-decision defeat in miniature**: the filter
was individually correct (it rejects malformed tokens) and it defeated the arm that depended on it.

**`BDR-82` (2026-08-11) — the non-vacuity floor made the arm it sits above UNREACHABLE.** The doc
names exactly three primitives, so I wrote `assert!(named.len() >= 3)` as the "am I reading
anything" guard. That guard and the register's *"the doc no longer names it"* arm have the same
trigger: **drop any one primitive and the floor fires first**, so the arm could never run. It was
vacuous from the moment it was written, and the GREEN run agreed with it completely — only the bite
separated them.

**The general rule, now that this has cost time twice** (`BDR-79` was the same family): a
non-vacuity floor and the arms above it are only separable while **floor < the number of subjects**.
Setting the floor *at* the subject count converts every arm above it into a floor test. The floor's
job is *"the parse reached the table"*; the arm's job is *"an item vanished"* — and if one deletion
cannot tell them apart, one of them is decoration. The floor is now 2 with a comment saying why it
must not be "tightened" back to 3.

**`BDR-81` (2026-08-10) — a hand-rolled bite printed "mutated" and had changed nothing.** Proving
the two arms of the new AST proof-detector are independent, I mutated one with a `str.replace` in
a throwaway script. It printed `mutated: the def-name arm only`, the tests stayed green, and for a
moment that read as *"the arm is redundant"*. **The replace had silently no-opped** — an escaping
mismatch — and my script asserted nothing before printing success.

The real harnesses have had this covered for weeks: `bite()` refuses with **`MISUSE — anchor not
found`** and again with **`MISUSE — mutation produced identical text`**. My ad-hoc version had
neither, so it produced the one output a bite must never produce — *a passing result from a
mutation that never happened*, which is `bitten: N/N` reduced to a single line. Redone with the
Edit tool, which fails loudly on a missing anchor; both arms then reded independently.

Third time today that the ad-hoc method was the thing at fault while the mechanism beside it was
correct (`BDR-76`). **Use the harness, or borrow its checks — do not hand-roll the one step whose
entire job is to be untrusted.**

**`BDR-80` (2026-08-10) — the teeth ratchet was FALSELY ACCUSING a gate, and its own docstring
predicted the cost.** `deferral-gate.py` ships a `--self-test` with eleven bite cases and was
reported as carrying no red-ability proof. Cause: `_PY_DOCSTRING` strips docstrings by matching
non-greedily between *any* two triple-quote marks, with no notion of which ones open a docstring.
It pairs them across the whole file, so text between two unrelated marks disappears — **87% of
that file (40246 → 5421 chars), `def self_test` included.**

Measured across all 97 gates: one gate's proof deleted, and 40–60% loss on several others that
happened not to matter. Python is now PARSED — the AST knows what a docstring is. One gate gained
certification, **none lost**, and `NO_PROOF_BASELINE` 48 → 47 for a reason that is not progress:
the worklist had a finished gate on it. The `_SELFTEST` comment already said what this costs —
*"a detector that misses an existing proof is a false accusation, and the pressure it creates is
to bolt on a second, redundant proof to satisfy a regex."*

**Two things fell out, and both are the adjacent-decision shape:**

* **`--verify-proofs` caught the second one immediately**, which is the mode earning its keep on
  the day it shipped: the proof moved to the AST while `_selftest_flag` still went through the
  corrupted stripper, so `deferral-gate` was *certified as proven* and *reported as exposing no
  flag to run*. Each half correct alone. The proof and the runner now read the same thing.
* **Writing the docstring that explains this defect reproduced it.** My explanation quoted the
  offending regex literally, the embedded triple-quote closed the docstring early, and the file
  stopped parsing. Fixed by naming `_PY_DOCSTRING` instead of quoting it.

**`BDR-79` (2026-08-10) — I wrote a self-witness arm that could not fail, in the same hour I wrote
the drift entry about self-witnessing.** The `G3` denominator split excludes 7 documents whose
subject is unbuilt, so `producers_for` is the load-bearing piece: if it finds nothing, every
exclusion stands forever and looks exactly like a tier nobody has built. I gave it a self-test arm
asserting `producers_for(("NO_PRODUCER",)) == []` — the gate must not read its OWN table as an
implementation.

**The arm passes whatever the code does.** `PRODUCER_ROOTS` is `crates` + `services`; this gate
lives in `scripts/`. It was never in the walk, so the `if f.resolve() == me` skip it was "proving"
is dead code — measured by deleting the skip and watching the self-test stay green. `NV-1`, the
subject cannot vary, and **nothing but biting the arm would ever have shown it**: it read as a
thoughtful guard against the exact mistake I had made twice that day.

Replaced with the property that is actually load-bearing — *this file is outside the producer
walk* — which reds the moment `scripts` joins `PRODUCER_ROOTS`, at which point the skip stops
being decoration and starts being the defence. Bitten in both directions. The skip stays as
defence in depth, with a docstring saying plainly that it is not the thing doing the work today;
a comment claiming a guard that the code does not need is how the next reader learns the wrong
lesson.

**`BDR-78` (2026-08-10) — the pre-commit hook found what the self-test, the 25-minute sweep and
`/review-impl` all missed, and it found it in the arm written to catch that exact thing.**
`doc-language-gate` refused the commit: *"line 316: exemption with no reason"*. Line 316 was my
own test fixture — the literal `<!-- doc-language-gate: ok -->` feeding the arm that proves a
reasonless pragma IS a finding. To a scanner reading this file's own diff, test INPUT and a real
reasonless exemption are the same bytes.

**Why three layers were blind to it, and the hook was not:** the self-test feeds `parse_diff`
synthetic diffs, so it never scans the file it lives in; the sweep runs the gate in `--all` mode,
which reports the legacy baseline and never blocks; `/review-impl` read the diff as a human would.
Only the real `--staged` path scans *this file as content*, and only at commit time. **The layer
that caught it is the one closest to the actual event** — which is the entire argument for having
more than one, and the reason CLAUDE.md ranks the hook above the goal condition.

Fixed by composing the markers from a `_MARK` constant, so the fixture the test runs is
byte-identical while the source text is not a pragma. Same rule as `gate-teeth-gate` refusing to
certify itself, extended one step: **a gate must never be its own witness, and that includes its
test data.** Third instance of the self-witness shape today — `dp-oracle-bite-gate` certified on a
literal it uses to read another gate, my `spec_oracle_rules.rs` docstring inventing five
producers, and now this.

**`BDR-77` (2026-08-10) — I built a guard against "the scope never reaches it" and shipped it with
that exact hole.** `/review-impl` on the day's diff: `verify_proofs({})` prints **"0 advertised
self-test(s) RAN and passed"** and exits 0. Everything in it is a loop over a list, and nothing
required the list to be non-empty — `NV-3`, in the mode written *that hour* to fix `NV-3` in three
other gates, whose whole added value was a reach floor. I added floors to `db-safety-gate` (500
test files), `doc-language-gate` (500 tracked) and `language-bias-gate` (500 scanned), and none to
the thing running them.

It is worse than a self-contained hole, and that is the part worth keeping: **`language-bias-gate`'s
baseline-staleness arm lives in its `--self-test`, so this step is the only thing that runs it in
CI.** A vacuous pass here silently retires an arm belonging to a different gate. A guard that other
guards depend on has to be the *most* non-vacuous thing in the tree, not the least.

Two more from the same review, both the same family — **an adjacent decision defeats it**:

* The `ceilings` exemption was keyed on a path **prefix**, and the rows above it are directory
  families where that is right. This one reasons about ONE FILE's behaviour — measured,
  `ceilings_v2.rs` and `ceilings_live_writer.rs` both matched it. `check_self_minted` would still
  have demanded a sibling mint its own reality, but **an exemption must not widen by default and
  lean on a second check to narrow it back.** Keyed on `.rs` now.
* In `name_grounding.py` the near-miss length gate read the RAW name while the edit distance read
  the FOLDED one. Interchangeable under `.lower()`, which preserves length; not under the spine —
  `Straße` (6) folds to `strasse` (7). Both halves individually correct, the pair wrong. A no-op
  for ASCII, which is every name in the tree today, and exactly the kind of thing that stops being
  a no-op the first time the feature is used for what it was built for.

**`BDR-76` (2026-08-10) — three times in one session I "found" a defect that was an artefact of
my own probe, and every time the correct method already existed in the repo.**

1. **Six broken gates that were fine.** I ran `--self-test` against everything; four answered
   `exit 127` and two `exit 2`. All six spell it `--selftest`.
2. **Four more, one layer down.** With the spelling fixed, the shell gates still failed 127 —
   `bash` on Windows turns an absolute `D:\Works\…` into `D:Workssource…`. The fix is a
   POSIX-relative path against `cwd=ROOT`, which is what every other runner here already does.
3. **A producer that appeared out of nowhere.** Re-verifying `BDR-72` before repeating it in a
   handoff, `DurableEventStream` · `advance_turn` · `TurnBoundary` · `wait_for_token` ·
   `route_to_writer` each came back **1 file** where `BDR-72` recorded 0. The one hit, in every
   case, was **my own docstring in `spec_oracle_rules.rs` recording that they are 0 files.**
   Writing down that a symbol has no producer creates an occurrence of that symbol.

The third is the one worth keeping, because the mechanism I had already written handles it and
the ad-hoc grep did not: the `DP-R7` shrink arm strips comment lines *and* skips the file doing
the recording, for exactly this reason — *a gate must never be its own witness*. Re-measured its
way, the numbers match `BDR-72` to the digit (`CausalityToken` 2, `BubbleUpAggregator` 1, the
rest 0).

**The pattern across all three: a measurement whose METHOD differs from the mechanism's method
gives a different answer, and the ad-hoc one is the wrong one.** `BDR-56` warns about a red for
an unrelated reason looking like success; this is its mirror — a red for an unrelated reason
looking like a *discovery*, which is more tempting because it feels like diligence. And the
day's most-repeated version of the same thing was smaller and dumber: a trailing `echo`/`tail`
masked a real exit status **four** times, once inside a task notification that reported `0` for
a sweep that had exited `1`.

**`BDR-75` (2026-08-10) — the teeth ratchet counted 42 self-tests that nothing ran, and one of
them did not exist.** `--verify-proofs` was built because `teeth_proof` certifies a gate by
MATCHING TEXT: `def self_test`, a `--self-test` flag, or the bare word `SELFTEST`. Rename the
function and leave the flag and the count stays at **49 proven** while `--self-test` raises
`NameError` — measured, both modes run against the same tree, disagreeing. So the number this
repo publishes about its own gates rested on claims, one level out from the thing the file is
about.

**On its first run it found a false certification, and the cost was not cosmetic.**
`dp-oracle-bite-gate.py` was certified *built-in selftest* on the string `"SELFTEST FAIL"` — a
literal it uses to read the **coverage gate's output**. It had no self-test at all. That matters
because it is a **bite harness**: broken machinery there prints `bitten: 19/19` and is believed,
which is why its four `dp-slice*` siblings were given self-tests in the previous move. **The
false certification is exactly what kept it off that worklist.** A mention counted as a proof —
fourth occurrence of that shape here, and the `_SELFTEST` comment already warned about it for
the two spellings it *had* narrowed, leaving the third open. All three alternatives are now
shapes, not words; narrowing cost exactly one certification, the phantom one. It now carries a
real self-test (seven verdict arms including `running 0 tests` → `missing`, the both-sides rule
both ways, and all 19 leg anchors), so the count held at 49.

Two smaller things, both worth the ink:

* **I reported six broken gates that were fine.** A probe that ran `--self-test` against
  everything got four `exit 127` and two `exit 2`; all six spell it `--selftest`. Every one of
  those reds looked precisely like a finding. `BDR-56` says a red for an unrelated reason is the
  failure mode most like success — this is its mirror, a red for an unrelated reason that looks
  like a *discovery*. The runner now reads the spelling out of the file instead of guessing.
* **And then the same class again, one layer down:** `bash` on Windows receives an absolute
  `D:\Works\…` as escape soup (`D:Workssource…`) and answers *No such file or directory* — exit
  127, indistinguishable from a broken self-test. Four gates were reported failing before the
  path was found to be at fault. The runner passes a POSIX-relative path against `cwd=ROOT`.

**`BDR-74` (2026-08-10) — three gates that read a corpus, and the thing none of them could see
was itself.** `db-safety-gate`, `doc-language-gate` and `language-bias-gate` were taken together
because they share one failure mode that is invisible by construction: **a walk that reaches
nothing and a clean tree produce byte-identical output, exit 0 included.** Demonstrated rather
than argued — rename `services/` in `SEARCH_DIRS` and `db-safety-gate` still exits 0 with **1558
test files unguarded**; add `/docs/` to `doc-language-gate`'s subject-matter allowlist and it
reports a *better* number (505/8678 against a true 995/10821) with the rule's entire subject out
of scope. So each self-test has a **reach** family: every search directory must exist, and the
walk must clear a floor.

Every detector arm has a false-positive twin, and that is not symmetry for its own sake — a
language gate that cries wolf is switched off within a day, so `Soufflé`/`naïve`/`Gödel`, CJK
domain terms, `self.name.lower()` behind the ML-2 lookbehind and a `WHERE`-scoped `DELETE` must
all come back clean **from the same code path that reds without them**.

**What the `language-bias-gate` arm found is the reason to prefer a checked baseline to a
counted one.** 7 of its 44 rows named code that no longer existed — four ML-2 offenders fixed
(one now imports the shared `normalize_entity_name` spine), two ML-5 rows given
`ensure_ascii=False`, one line deleted. **A fingerprint whose subject is gone is a standing
exemption for a line nobody has written yet:** write that exact statement at that exact path and
the gate waves it through. A baseline's whole value is that it shrinks, and nothing was watching
whether this one did. Pruned 44 → 37; `D-LANGBIAS-COMPACTION-LOWER` and
`D-LANGBIAS-CANONCHECK-LOWER` are discharged by the same finding.

The same run surfaced that the gate **had been RED on `main` since 2026-08-01** — nine days —
over two live ML-2 violations in `composition-service/name_grounding.py`. Fixed at the source,
not baselined, and the fix is load-bearing rather than lint-shaped: the fold is a *symmetric*
match key, so `Ｅｌａｒａ` and `Straße` were being reported to the author as **unanchored names**
— false accusations — while the spine keeps `ma`/`má` distinct as it documents. Both sides of the
comparison had to move in one edit; folding one side differently from the other silently stops
every match, which is the adjacent-decision shape. 53 + 138 tests green.

**`BDR-73` (2026-08-10) — an exemption is a claim, and a claim that cannot be wrong is the shape
`BDR-55` names.** The last adoptable site was `ceilings.rs`, and the row offered an exemption if it
were *reasoned*. The tempting reason is **"it is a benchmark harness"** — and that is precisely the
invented category, because nothing about being a benchmark stops a process from binding. A
benchmark with a meta URL and a provisioned world binds like anything else; *"I would have to build
it"* is §0.3's non-blocker, not a structural fact.

The real reason is one clause narrower and it is a property of the code: **the harness MINTS its
reality and registers it nowhere.** `dp::RealityId` asserts *the control plane confirmed this
reality exists and accepts commands*; this uuid is invented three lines before use, deliberately, so
the run cannot touch a real world's rows. There is no registry row, so `bind` would refuse it.
Adoption would mean forging the assertion the type exists to make.

**The difference between those two reasons is that the second can go wrong and say so.** So it is
mechanised rather than written: `check_self_minted` reds if the mint disappears, if an external
reality source appears (`--reality` / `REALITY_ID` / `Uuid::parse_str`), if the claim guards an
exemption that is not there, or if it matches no file. Comments are stripped first — a mention of
the flag in prose is not an input, the distinction `deferral-gate` had to learn.

Two things the run got for free, both worth keeping:

* **The reclassification could not be silent.** Moving one site from `adoptable` to `exempt` made
  the gate fail *twice* — `BASELINE STALE (ADOPTABLE) 1 → 0` and `REGRESSION (EXEMPT) 0 → 1` — and
  refuse to pass until both were recorded. The total stayed **57**. That is the three-category split
  doing the job it was built for: an exemption cannot make a number disappear, only move it in
  daylight. It was written for growth; this is the first time it caught a *reclassification*.
* **The gate announced its own retirement, and the notice is the argument for this work.** With
  adoptable at zero everywhere, `--self-test` now prints *"the exemptions have become the whole
  story."* A ratchet at zero is only as honest as its exemption reasons — which is exactly when a
  prose reason stops being sufficient.

**`BDR-72` (2026-08-10) — a LOCKED access-pattern rule is enforced by nothing, and the board row
that sent me looking was itself the trap it warned about.** `§0.6e` row 2 named four documents to
cover next and told me, in its own `done =` cell, *"do not add a rule whose subject has no
producer"*. **Three of the four have no producer** — `DurableEventStream`, `advance_turn`,
`TurnBoundary`, `wait_for_token`, `route_to_writer` are 0 files each, and `CausalityToken`'s two
hits are both DEFERRED rows recording it as unbuilt. Writing those oracles would have produced
three files of ceremony that cannot fail, over Phase-4 designs nothing implements. **I wrote that
row yesterday.** A board row is not evidence, including one you wrote while holding the rule it
violates.

The one document with both sides paid for the trip. `11_access_pattern_rules` states `DP-R1`..`R8`,
and **`DP-R7` — "no direct LLM-output-to-kernel-write" — is named by nothing in the tree.** Its own
enforcement clause specifies *review* plus a *"compile (partial)"* `Validated<T>` wrapper; measured,
`Validated<T>` has **0** definitions. Its stated violation mode is *"prompt-injection exploit writes
directly to kernel. Catastrophic in a multi-user game economy."*

**But the honest finding is narrower than "a security rule is unenforced", and the difference is
the interesting part.** There is also **no subject**: `LlmResponse` / `llm_output` appear in **0**
Rust files, so nothing today *can* take the shortcut. Unenforced-and-unviolatable is a different
state from unenforced, and collapsing them would have overstated a security finding — the failure
mode opposite to the one I keep hitting. So it is a register row with a **mechanical** wake-up: the
oracle walks every `.rs` under `crates/` and `services/` (comment lines stripped — prose about LLM
output is not LLM output) and reds the moment one appears, naming the file. Bitten by adding a
`struct LlmResponse` to `read.rs`.

**`BDR-71` (2026-08-10) — an unproven BITE HARNESS is worse than an unproven gate, and §0.6's
oldest warning caught me again.** The four `dp-slice*-bite-gate` harnesses certify every
`crates/dp` guarantee, and none of them proved its own machinery. The asymmetry is what makes them
the right four to take first: an ordinary gate with broken logic goes quiet, while **a bite harness
with broken logic prints `bitten: N/N`** — it does not merely fail to warn, it manufactures
evidence for every guard it names. `classify` was split out of `test_outcome` so the four-way
verdict could be checked on synthetic transcripts in milliseconds instead of a 30-second cargo run;
the arm that matters most is that a `running 0 tests` transcript must NOT read as a pass, because
a renamed witness would otherwise score as a successful bite.

Two things worth keeping from doing it:

* **§0.6's *"heredocs eat backslashes"* is still undefeated.** Writing the CRLF fixture through a
  bash heredoc turned `"a\r\nb"` into a literal newline and a `SyntaxError`. The rule says use the
  Edit/Write tools for anything containing a backslash; I used a heredoc, in a self-test whose
  entire subject is CRLF handling. Repaired by building the string from `chr()` — the fix worked,
  but the rule would have been cheaper.
* **A display path stopped a safety check from being testable.** `restored_byte_identical` called
  `path.relative_to(REPO)` in its failure branch, which raises for a temp file — so the corrupted-
  restore arm could not be exercised against the REAL function, only a copy. Testing a copy of a
  safety check proves nothing about the one that runs. Fixed in both harnesses.

**`BDR-70` (2026-08-10) — the gate that exists to prove gates can fail could not see 40% of them.**
`slice 1`'s `G6` said *"the gate is absent from `gate-bite-harness.MUTATIONS`"*. Checking it
found something larger and different. `gate-teeth-gate` discovers its subjects by regexing
`.github/workflows/` for a literal `scripts/<name>` path — complete only while every gate was
named in a workflow. `gate-wiring-gate --run-all` ended that, and its own docstring says why the
runner exists: *"a gate written tomorrow runs in CI the day it lands, with nobody remembering to
add a line."* **Measured: 58 seen, 97 executed.** The ~40 gates riding the runner were not
exempt and not failing — they were **invisible**, so the ratchet reported a subset as the whole,
and the three gates added earlier the same day were outside its scope on arrival.

**One mechanism's coverage upgrade silently narrowed another's.** Neither gate is wrong on its
own; `NV-3`'s *"an adjacent decision defeats it"* is named as the hardest of the four shapes for
exactly this reason, and here the adjacent decision was **the fix to the sibling gate**. Discovery
is now delegated to `gate-wiring-gate`'s own list rather than re-implementing the predicate — two
definitions of "what is a gate" is the drift this repo has a standard about.

`NO_PROOF_BASELINE` 45 → **55**, the one direction a ratchet normally forbids. It is a scope
correction, not new debt, and the constant carries the reason. Two things kept it from being
worse and neither is bookkeeping: the three new gates all shipped a `--self-test`, and
`migration-idempotency-validator.sh`'s proof turned out to be real but **delegated** to its `.py`
by my own wrapper refactor — recorded as `DELEGATES_PROOF` with the target named, rather than
adding a no-op line so the wrapper's text contains `--self-test`, which is the *"bolt on a proof
to satisfy a regex"* pressure the file's own comment warns about. Bitten: disabling runner
discovery drops the count to 44 and the ratchet reds.

**`BDR-69` (2026-08-10) — I counted diacritics and called it a violation count, then deferred the
work on the inflated figure.** `SESSION_HANDOFF.md` was reported as *"162 lines across ~120
regions"* of English-only-rule breach and parked as gate #2 (large/structural). Both numbers were
`grep -c` over a diacritic class. The LOCKED rule permits non-English **where the text IS the
subject matter**, and almost all of it was: novel character names and cultivation terminology,
scene titles, shipped i18n strings, CJK/full-width normalisation fixtures, and the Vietnamese
pronoun data that is the literal subject of the linguistic-QA sections. **The real defect was ~19
blocks of pasted author speech**, fixed in one pass. Stripping the other ~120 would have destroyed
meaning while reporting compliance.

This is the same defect as `BDR-63`, committed within the hour of fixing it: **a pattern match
standing in for the property**, where the property is *"is this prose the author wrote, or is it
the subject under test?"* — and a regex cannot tell those apart. Worse, the deferral row I wrote
proposed building *"a diacritic ratchet over `docs/**`"* as the obvious mechanism.
`scripts/doc-language-gate.py` **is** that gate, already wired pre-commit, deliberately judging
added lines only against a 995-file baseline. I proposed building a mechanism that already existed
**while the standards index was open in the same turn** — §0.1's *"grep/read the SOURCE that already
implements it"*, skipped.

**`/review-impl`, 2026-08-10 — four findings on this session's own work, three of them MED.**
Run after every row was closed and the sweep was green, which is the point: the three-axis DoD and a
green sweep passed all four (`BDR-50` — *"the axes test the SUBJECT; only an independent reader
tests the APPARATUS"*).

1. **`[User Boundaries & Tenancy]` `036` up dropped a tenancy CHECK non-atomically.** Three separate
   `ALTER TABLE … DROP CONSTRAINT IF EXISTS x;` / `ADD CONSTRAINT x` pairs, in a file with no
   `BEGIN;` — so each ran in its own transaction and there was a window in which
   `reality_registry_owner_user_set` did not exist, i.e. a window accepting a `user`-kind row with a
   NULL owner. **`037`, the same change made in the same hour, already used the atomic
   comma-separated form.** The review found it by comparing the two halves of one edit against each
   other; nothing else would have. Fixed, re-verified live: 39 ups applied, `036`/`037` up re-applied
   exit 0, all five owner constraints present, and the data-loss guard still refuses with a real
   user-owned row inserted (`INSERT 0 1` → `ERROR: refusing to roll back 036`).
2. **`is_bind_input` leaked its exemption past the function's closing brace.** It walked back to the
   nearest `fn` and never checked the site was *inside* it, so a `pub reality: Uuid` struct field
   following a binding function inherited `boundary` and vanished from the adoptable count — in the
   gate written because a *different* measurement defect hid four live sites. Not live in the tree
   (counts unchanged at 1/52/4 after the fix, which is how we know), and it would have bitten the
   first file to put a struct under a bind. Fixed with a containment check, and **bitten**: removing
   it turns the new self-test red naming the leak.
3. **The bite harness wrote to a file the live cluster executes every five seconds.**
   `infra/db-ensure.sh` is bind-mounted into the postgres container and run as its healthcheck
   (`infra/docker-compose.yml:62,66`, `interval: 5s`). `write_text` truncates before writing, so a
   healthcheck landing mid-write reads a syntax error and postgres goes UNHEALTHY — cascading to
   every `depends_on: service_healthy`; and a harness killed before its `finally` leaves the
   **interpolated, vulnerable** form on disk to run every five seconds. The write bought nothing:
   `extract_create_role_pipeline` takes a string. Removed; still 4/4, still proves the escalation.
4. **The self-test that should have caught #2 could not.** Its struct fixture had no preceding
   function, so `rfind("fn ")` returned `-1` and the dangerous branch was never reached — `NV-1`,
   the subject could not vary. A struct-after-a-binding-fn case is now leg 2 of that arm.

**And one during the verification itself:** the re-check of finding 1's guard inserted a row that
the `reality_registry_db_host_format` CHECK rejected, so the "guard refuses" leg ran against a table
with no user-owned rows and would have passed for the wrong reason. Caught by reading the output
rather than the exit code. Redone with a valid host. `BDR-56` does not stop applying to the
verification of a fix for `BDR-56`.

**`BDR-68` (2026-08-10) — I piped the sweep through `tail` and read `tail`'s exit code as the
sweep's.** The second full sweep was reported as **"exit code 0"** and it had **failed**:
`gate-wiring-gate --run-all | tail -45` returns the status of the LAST command in the pipeline, so
a genuine red — `file-ceiling-gate`, a file I had grown past its recorded size — was masked. It was
caught only because the text was grepped for `FAILED` afterwards, which was luck dressed as
process. **This is `BDR-50`'s lesson inverted: not a red for the wrong reason, but a GREEN that was
never the gate's own verdict.** The habit that produced it is ordinary and will recur — piping a
long-running command to `tail` to keep the output readable. The fix is mechanical: redirect to a
file and echo `$?`, never pipe the thing whose exit code is the evidence.

The masked finding deserves its own line, because the tempting fix was the wrong one. `spine.rs`
was allowlisted at 375 lines and a five-line comment took it to 377 — so update the allowlist to
377? `file-ceiling-gate` answers that in its own words: *"an allowlist entry buys amnesty for the
debt that exists, never for more of it."* **The comment was shortened instead.** A ceiling that
moves whenever something touches it is not a ceiling.

**VERIFICATION, 2026-08-10 — three full sweeps, each run alone.** Final:
`gate-wiring-gate.py --run-all`, **RC=0 captured directly** (not through a pipe): **84 GREEN**, zero
untracked failures, zero stale `KNOWN_RED` rows, one tracked red (`language-bias-gate`,
`D-GATE-ROT-LANGUAGE-BIAS`, pre-existing and unrelated). All **six** bite harnesses green, including
the two added here (`dp-oracle-bite-gate` 64.1s, `db-ensure-bite-gate` 2.9s), both run serially per
their `MUTATING` rows. Afterwards, byte-identical: `06_data_plane/`, `contracts/migrations/`,
`infra/db-ensure.sh`, `crates/dp/src`, `crates/meta-rs/src`, `admin-cli/cmd/admin/main.go` —
`BDR-53`'s damage mode is precisely a mutation that survives the sweep it was made in. The cluster
too: **0** stray `lw_bite%` roles, **0** leftover throwaway databases, `loreweave_meta` still
holding its 7 realities.

**`BDR-63` (2026-08-10) — the gate said a service was FULLY ADOPTED, and the reason was a field
name.** `3E-NAMING-INCONSISTENCY` was filed as *"latent — both are honest raw inputs today"*, about
one CLI argument. It was not latent. `reality-id-adoption-gate` matched `reality_id:` and
`commit-service` spells the field `reality`, so the crate reported **`0 adoptable, 0 exempt`** —
indistinguishable from a crate that had finished the migration — while carrying five bare sites,
**four of them on the spine's live write path**. The row that predicted this is in the gate's own
source: *"the alternative was renaming the field to `reality` so the regex stopped matching, which
would have moved the number without moving the property."* It had already happened, one service
over, and the note did not go looking.

Two lessons, and the second is the one worth carrying:

1. **A clean number from a name-matching check is the least trustworthy number there is.** `0 of 0`
   should have prompted *"does this gate can see this crate at all?"*, and `--list` answers that in
   one command. It was never run against the crate reporting zero.
2. **When you write down a failure mode you are avoiding, go and look for it.** The gate documented
   the exact defect, in the exact words, as a hypothetical — and a sibling instance was live in the
   tree at the time of writing. Writing the trap down is not the same as searching for it.

The fix widened the regex to the property, which surfaced a mirror defect in the other direction:
the tail accepted `reality_id: Uuid::from_u128(0x42)`, a struct **literal**, so eleven non-sites had
been inflating `exempt`. **A count that includes things that are not its subject is not a
measurement** — and it had been baselined, so the ratchet was holding a number partly made of noise.

**`BDR-62` (2026-08-10) — a WALK is not a CHECK, and a file count reads exactly like coverage.**
`migration-idempotency-validator` was widened from one migration tree to two, which is what
`META-DOWN-UNCOVERED` asked for. It would have been close to worthless. Every one of its six checks
was a `grep -E` anchored to a single LINE, and the meta tree writes multi-clause DDL across several
lines — measured, **8 of 13 `ALTER TABLE … COLUMN` statements are multi-line, four of them in the
tree it had walked all along.** So the widened validator would have printed *"78 file(s)"* and
*"PASS"*, and a reader would have had a number, a green, and almost no checking. Two things fell out
of fixing it properly: a per-tree file **floor**, because the old code printed *"no migrations
found"* and **exited 0** — the wrong-path failure is silent in the direction of success; and a rule
for the `DROP CONSTRAINT IF EXISTS` idiom, because **7 of 9** constraint-adding migrations already
followed it and 2 did not, and a convention with a 78% adoption rate is a coin flip wearing a
convention's name.

**`BDR-61` (2026-08-10) — the lint went GREEN on the file whose retry still failed, and it was RIGHT
to.** After all 8 text violations in `036`/`037` were fixed, `migration-idempotency-validator`
passed. Re-running `036_reality_ownership.down.sql` against a throwaway meta database still died:
`ERROR: column "owner_kind" does not exist`. The statement that broke it is inside a `DO $guard$ …
$guard$` block — a PL/pgSQL data-loss guard that counts user-owned realities before dropping the
column — and the validator **deliberately blanks dollar-quoted bodies**, because a function body is
not DDL and reading it would be guessing. So the one statement that mattered lives in the one region
the check cannot see, by a correct design decision. **Every `IF EXISTS` added in that pass was real
and none of them helped: the file failed before reaching any of them.** The lesson is the one this
validator's own docstring already stated and I still had to re-learn by running it — *it reads TEXT;
the property is BEHAVIOUR* — and the corollary is sharper: **a proxy that is honest about its blind
spot will still be mistaken for the property unless something exercises the property.** The fix was
an early `RETURN` when the guarded column is already gone, and the guard was then re-bitten in the
direction that matters: with a user-owned reality inserted, it still refuses.

**`BDR-60` (2026-08-10) — deleting ONE call site killed an entire register check and the suite
reported 15 passed.** The bite for the coverage ratchet removed
`check_deferred_write_forms();` — the sole call site of the helper that checks
`DEFERRED_READ_FORMS` and `DEFERRED_WRITE_FORMS` against `DP-K4`/`DP-K5`. The crate still compiles
(an uncalled private fn is a warning), and `cargo test -p dp --test spec_oracle` printed **`test
result: ok. 15 passed; 0 failed`** with the check dead. **Nothing in the unit suite can see a
defeated helper, because the suite's unit of observation is the test that still runs.** The
coverage ratchet saw it, and this is the concrete answer to *"why a gate and not just tests"* — the
question a reader will reasonably ask of every ratchet in this repo.

**`BDR-59` (2026-08-10) — the reachability walk was written BACKWARDS, and the self-test caught it
on the first run.** The gate asks *"is this function called from a live one"*; the first draft asked
*"does this function call a live one"*. Same words, opposite edge direction, and it scored
`check_deferred_write_forms` — a real helper reached from a real test — as dead code. Worth keeping
for what caught it: not review and not the tree, but a five-line synthetic fixture written **before**
the walk, whose only job was to be the ordinary shape. A gate's self-test earns its cost on the day
the gate is written, not later.

**`BDR-58` (2026-08-10) — a fence parser defeated by a document that TALKS about fences.**
`DP-Ch11`'s SQL block contains an amendment comment reading *"the previous scan read only ```sql
blocks containing `REFERENCES channels`"* — a triple backtick, mid-line, inside the block. A closing
delimiter matched as a plain substring ended the block after **341 characters**, `ADD COLUMN` matched
**zero** times, and both new `DP-Ch11` rules failed. **They failed for the right reason and said so**,
because each carries a `parsed only N — the block's shape moved` guard. That is the cheap version of
this bug; the expensive version is a truncation that still finds *something*, agrees with the code,
and reports green. **The non-vacuity guard was worth more than the parser it protected** — and note
the recursion: the corpus documents its own tooling, so a parser over these documents must survive
prose about parsers. Fixed by reading the format (a fence is a LINE-INITIAL delimiter), not by
special-casing the file.

**`BDR-57` (2026-08-10) — the coverage gate measured a NAMING CONVENTION and called it a property.**
It counted a document as read when a string literal equalled its filename. `spec_oracle.rs` writes
`dp_doc("08_scale_and_slos.md")`, so it worked; `spec_oracle_cp.rs`, written the same hour, writes
`.join("../../docs/…/06_data_plane/05_control_plane_spec.md")` — and the gate reported that file as
reading **nothing at all**, while the test beside it was comparing three sections of that document
to code. **`NV-3`, inside the gate written to close an `NV-3`**: the scope never reached a reader
that spelled the path differently, and it was default-uncovered rather than refused. The tell was
available immediately and nearly missed — the gate printed `05_control_plane_spec.md` in its
*still unread* list one command after a test that reads it had gone green. **When a fresh measurement
contradicts something you just did, the measurement is the thing to doubt first.** Fixed by matching
the literal's BASENAME, which is the property; a fixture for the path form is now leg 11 of the
self-test.

**`BDR-56` (2026-08-09) — a bite mutation that changes nothing prints exactly what a vacuous guard
prints.** Three legs of `dp-slice5d-bite-gate` scored `THE GUARD IS NOT LOAD-BEARING` and all three
were wrong about the guard: one mutation added a no-op statement, one used a `{channel:.0}`
precision spec that std's integer `Display` ignores, and one named a type that does not exist so the
build failed. **The four-way verdict (`pass`/`fail`/`nobuild`/`missing`) caught the third; nothing
but re-reading caught the first two.** `mutated != original` is necessary and not sufficient —
`BDR-30` said so about a trimmed table cell, and it is just as true of a mutation that compiles,
runs, and means nothing. A fourth leg turned out to have **no removable guard at all**: `&self ->
Self` is enforced by rustc, so `DP-K2`'s "a move returns a NEW context" cannot be un-guarded. Stated
in the harness and not counted, per `V1-F3`.

**`BDR-55` (2026-08-09) — a ratchet whose target is unreachable is a CEILING wearing a ratchet's
name.** `reality-id-adoption-gate` reported 73 sites as debt. Classified, **~62 of them could never
be paid**: `dp::RealityId` asserts *"exists AND accepts commands"*, and provisioning, seeding,
rebuilding, orphan-scanning and deprovisioning are precisely the code whose subject is a reality in
none of those states. The number could not reach zero, so nobody could ever act on it — which
`gate-wiring-gate`'s own preamble names as worse than no gate. **The defect was in the MEASUREMENT,
not the code.** Two things worth keeping: the fix must not be narrowing `IN_SCOPE` (62 sites would
vanish with nothing left to read — a gate quietly deciding it is done); and the honest last mile is
a *third* category — the env input a bind CONSUMES cannot already be its output. Renaming that field
so the regex stopped matching would have moved the number without moving the property.

**`BDR-54` (2026-08-09) — a constructor that returns half of what the caller needs reads as
complete.** `bind_reality` returned the `SessionContext` and **dropped the control plane**, leaving
the process holding a capability it had no way to renew. Nothing was missing at the call site,
nothing failed a test, and the shape of the bug is *the same defect as never refreshing at all,
arrived at by accident*. Found only when the refresh work needed the plane an hour later. **When a
function hands back a live thing, ask what keeps it alive.**

**`BDR-53` (2026-08-09) — two mutating harnesses corrupt the tree PAST the guard built to prove they
do not.** `gate-wiring-gate` serialises them inside one sweep; two sweeps defeat it. The damage is
not a flaky verdict:

    harness A reads its baseline   <- already mutated by B
    harness A mutates, then restores TO A'S BASELINE
    = B's mutation is now PERMANENT, and A's digest check PASSES

`V1-F8`'s restore-by-digest proves the file came back to what the harness **read**, and what it read
was already wrong. Three files were left mutated in `crates/dp` — including `tier.rs::as_key`
returning `TIER_ZERO` — and all four bite gates reported red for a reason unrelated to any guard.
**A safety mechanism scoped to one process is default-uncovered for two.** Fixed with an `O_EXCL`
lock; deliberately not a dirty-tree check, which would refuse ordinary uncommitted work and refuse
something that is actually safe.

**`BDR-52` (2026-08-09) — a finding and its REMEDY are two separate claims, and only one of mine was
checked.** The post-slice-5 review correctly found that nothing validated a capability on the data
path, so revocation never reached a running writer. It then prescribed a `WriteBackend`/`ReadBackend`
seam change — **which `DP-C3` rules out in one line**: the control plane is *"low-QPS (≤100/s
global)"*, so per-write validation exceeds its own scale contract by orders of magnitude. `DP-C8`
states the real design (*"Short expiry (5 min) bounds blast radius"*), and the actual fix was a
constant and a refresh call. **The finding got evidence; the remedy got only plausibility.** The
same read that produced the remedy would have produced the correct one — the spec was open on the
screen. Corollary, and it is the reason this cost two hours rather than ten minutes: **our TTL was
15 minutes against a spec that says 5 in three independent places, and that constant IS the
revocation window.** Nothing compared a `const` to the document that governs it, and
`05_control_plane_spec.md` is not one of the nine documents `spec_oracle` opens (`G3`).

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
