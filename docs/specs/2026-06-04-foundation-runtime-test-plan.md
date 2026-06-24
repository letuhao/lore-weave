# Foundation Runtime Test Plan — spine-first, phased to whole-foundation

> **What this is.** A concrete, phased test plan that validates the foundation as a *runtime benchmark of the
> architecture*, modeled on how OS-scale / large distributed systems test themselves (LTP/xfstests conformance,
> FoundationDB/TigerBeetle DST, CockroachDB Jepsen+roachtest, statistical perf-gating). This is the PLANNING
> artifact; implementation is incremental (§10 roadmap).
>
> **Honest scope (v2 correction).** The foundation's *correctness spine* is the event-sourced pipeline
> **L2 (event-store/outbox/publisher/archive) → L3 (projections/replay/rebuild/integrity)**. That spine is where
> this plan is deep and immediately buildable. The domain layers **L4–L7**, the SRE/ops service fleet, and the
> novel-platform domain services are covered **structurally + on a phased schedule** (§6.4, §10) — they are NOT
> fully specified here because most are unbuilt. **This plan is spine-first; "whole-foundation" is the trajectory,
> not the v1 surface area.** Do not read the per-layer matrix as claiming uniform coverage.
>
> **Grounded in research:** [2026-06-04-foundation-runtime-test-plan-research.md](2026-06-04-foundation-runtime-test-plan-research.md)
> (two adversarially-verified deep-research passes).
>
> **Benchmarked:** v1 was coverage-audited by 4 independent cold-start reviewers; v2 folds in every
> high-confidence finding. See §13 changelog for the v1→v2 diff.
>
> **The single load-bearing correctness invariant:** **`projection == replay(events)`** — its runtime oracle
> exists (the L3.E/F integrity-checker, `services/integrity-checker/` + `replay-aggregate` Rust bin). This plan
> makes that oracle the spine and **hardens it against its own known blind spots** (§2).
>
> **Status:** DRAFT v2 (DESIGN). Author: foundation runtime-test-plan task, 2026-06-04.

---

## 0. Framing — the layered oracle stack (and why no single oracle suffices)

Research-verified: large event-sourced/distributed systems converge on a **layered stack of complementary
oracles**, because *no single method is sufficient* — TigerBeetle had a query bug evade all 4 fuzzers; CockroachDB
had a consistency bug survive ~2 years of nightly Jepsen; VLDB 2024 proves a differential oracle (our
`projection==replay`) is **blind to common-mode bugs**. We adopt the same layered stack, ordered by ROI/effort.

| # | Technique | OS-scale precedent | What it proves | What it CANNOT prove | Our status |
|---|---|---|---|---|---|
| A | **Conformance battery** (1 behavior=1 test, golden-diff, runner+results) | LTP, xfstests, KUnit/kselftest | Each invariant I1–I19 + each event/projection-schema rule holds | Behaviors not enumerated; emergent/timing bugs | NEW — extend the 9 live-smokes |
| B | **Differential oracle** (`projection==replay`) — **SAMPLED** | xfstests golden `$seq.out` | Go-projection and Rust-replay *agree* on sampled rows | (i) common-mode bugs; (ii) event-store integrity (both read same events); (iii) unsampled rows | **EXISTS** — harden + standing-gate + acknowledge sampling |
| C | **Structural property oracle** (proptest/Hypothesis) | proptest discipline | Generic invariants for ALL streams: version-monotonic, idempotent, no-orphan, deterministic-replay | *Value-level* correctness (a structurally-valid wrong value passes) | NEW |
| **C2** | **From-spec reference oracle** (independent 3rd projector / golden expected-value fixtures) | SQLancer/PQS construct-known-answer | The projected *value* matches the spec, independent of both impls | Only as good as the reference/fixtures' coverage | **NEW — closes the value-level common-mode gap** |
| **C3** | **Event-store integrity ledger** (independent event-count / global-sequence / causal-completeness check) | TigerBeetle log/storage checks | The *event log itself* is complete & uncorrupted (no silent loss/gap/rot) | Bugs inside the log writer shared by all readers | **NEW — closes the deepest blind spot** |
| D | **Jepsen-style fault + history checker** | CockroachDB nightly Jepsen (Elle/Knossos) | System stays consistent *during* faults AND converges after | Faults not in the matrix | NEW — inject **and** analyze history (not just post-quiesce drift) |
| E | **Model checking** (Stateright/TLA+) | FoundationDB, AWS | Protocol/state-machine invariants at design time | Implementation drift from model | NEW — Rust kernel protocols |
| F | **Perf / saturation / soak** (USL, wrk2, statistical CI gate) | lmbench/fio + Bencher/benchstat | p50/p99/p999, Nmax knee, leak/backlog growth | Correctness | NEW — `lw_projection_lag_seconds` seeds the soak signal |
| G | **Recovery / DR drills** | xfstests crash tests | kill→restart, rebuild, restore round-trip, replay determinism | (uses B/C as oracle → inherits their limits) | Components EXIST |
| H | **DST** (deterministic clock/net/disk + interleavings) | FoundationDB Flow, TigerBeetle VOPR | Deep concurrency/timing bugs, seed-reproducible | Bugs outside the simulated surface | TIERED (§9): **H0 now · H1-loom EARLY · H1-madsim/H2 later** |

**The corrected correctness spine is `B(sampled) ∧ C(structural) ∧ C2(from-spec) ∧ C3(log-integrity)`** — NOT `B`
alone, and NOT even `B∧C`. v1 implied `B∧C ⇒ correct`; that is false (C is structural-only). The from-spec oracle
(C2) and the log-integrity ledger (C3) are the two new pillars v2 adds to make the spine sound.

**Two altitudes** (kernel KUnit vs kselftest): in-process unit · whole-flow live-stack (`infra/foundation-dev/`).
**Two axes** (xfstests): `generic/` (cross-reality-shard) · per-service.

---

## 1. The conformance battery — invariants → assertions (Technique A)

**Model:** xfstests/LTP — *one behavior = one test*, pass decided by **golden-output diff + exit status** (the
4 xfstests conditions: no crash · not-`notrun` · exit 0 · output == golden). But a conformance suite is a *runner +
a results contract*, not just a catalog (§1.3).

### 1.1 Invariant assertion matrix (I1–I19) — honest about net-new vs reused

Legend: **REUSE** = an existing `scripts/*-lint.sh` folded into the catalog (net-new coverage ≈ 0, just
registered) · **NEW-LINT** = a lint that does NOT exist yet and must be built · **NEW-RT** = a net-new *runtime*
assertion needing a live DB · **NAMED-ONLY** = enforcement target unbuilt, assertion deferred with the layer.

| Inv | Conformance assertion | Kind | Notes / hazards |
|---|---|---|---|
| **I1** Gateway | only `api-gateway-bff` + `game-server` public; 3rd listener = FAIL | NEW-RT | AWS-SG not on dev stack → this is a **prod-only / IaC-manifest** assertion; on dev stack `notrun`. **+ D-GAME-WS-EDGE-CONTROLS**: assert WS handshake validates JWT/ticket, per-conn + per-user caps, join/leave audited (3 provisional controls — v1 dropped these). |
| **I2** Provider-gateway | `import anthropic/openai` outside sanctioned dirs = FAIL | REUSE | `lint-no-direct-llm-imports.sh` |
| **I3** Language rule | mismapped/absent service = FAIL | REUSE | `language-rule-lint.sh` |
| **I4** DB-per-service | service role cannot auth to another service's DB | NEW-RT | **HAZARD: untestable on the current stack** — dev/CI use a single `foundation` superuser. Requires a per-service-role provisioning fixture, OR mark `notrun` on dev + run only on a role-segmented stage. v1 silently asserted this as live-testable. |
| **I5** DB-per-reality | each reality has distinct `db_name`; no shared-DB row | NEW-RT | gated on provisioner (L1.C, unbuilt) → `notrun` until L1 lands |
| **I6** Session boundary | concurrent commands serialize FIFO; LLM-call outside tx | NAMED-ONLY | roleplay-service `missing` in language-rule.yaml → defer with L4 |
| **I7** No cross-reality query | no service holds cross-reality role except meta-worker; query-shape lint | NEW-LINT + NEW-RT | the "query-shape lint" does NOT exist — net-new |
| **I8** `MetaWrite()` funnel | direct meta INSERT/UPDATE outside `MetaWrite()` = FAIL; `meta_write_audit` REVOKE holds | REUSE + NEW-RT | `scripts/meta-write-discipline-lint.sh` **exists** (fold in); the runtime REVOKE-verification on a live DB is net-new |
| **I9** `AttemptStateTransition()` | invalid transitions rejected; CAS blocks concurrent double-transition | NEW-RT + E | runtime target `reality_registry.status` gated on L1 |
| **I10** Prompt assembly | built via `AssemblePrompt`; user content only in `[INPUT]`, XML-escaped | NAMED-ONLY | L4+ consumers unbuilt |
| **I11** SVID s2s auth | RPC without ACL entry = FAIL; `x-principal-mode` declared | REUSE + NEW-RT | `scripts/service-acl-matrix-lint.sh` **exists** (fold in); the runtime SVID-presence + `x-principal-mode` check is net-new |
| **I12** No secrets/models | secrets via gitleaks (REUSE) **+ model-name resolution from provider_registry, no compile-time pin** = NEW-LINT | REUSE + NEW-LINT | v1 dropped the **model-name half** — restored |
| **I13** Outbox | state+event same tx; `redis.XAdd` outside publisher = FAIL | REUSE-lint + NEW-RT + E | property + model-check |
| **I14** Additive schema | new field nullable/additive; breaking → new `event_type` + upcaster + **≥30d cooldown date-boundary** + replay-forever | REUSE + NEW-RT | add the `retire_after` date-boundary assertion (npc.said v1 `retire_after: 2026-12-31`): after the date, loader refuses registration but **archived events still replay** |
| **I15** Stable IDs | retired IDs strikethrough, no renumber | NEW-LINT | **HAZARD: no lint exists; invariant doc says "code review"** — v1 claimed a "static" check that cannot exist as described. Either build an ID-catalog lint or mark this code-review-only (not a conformance test). |
| **I16** Timeout discipline | no `context.Background()` on registered-dep paths (REUSE); **call-chain timeout-sum ≤ SLO** = NEW-LINT | REUSE + NEW-LINT | the chain-budget assertion needs a call-graph + dep-matrix sum — net-new, non-trivial |
| **I17** Capacity budget | service absent from `budgets.yaml` = deploy-block; class↔deploy-kind valid | REUSE | `capacity-budget-lint.sh` |
| **I18** Dep hash pinning | unhashed dep / floating tag / undigested image = FAIL | REUSE | `dep-pinning-lint.sh` |
| **I19** Observability inventory | every `lw_*` + `*_audit`/`*_events` declared (REUSE) **+ runtime: metric lib rejects unauthorized labels at emission (V1 warn-drop)** = NEW-RT | REUSE + NEW-RT | v1 dropped the **emission-time** half; **note:** inventory-completeness ≠ runtime cardinality-explosion safety — a label like unbounded `reality_id` is a separate runtime check |

> **v2 discipline:** the catalog tags each test REUSE / NEW-LINT / NEW-RT / NAMED-ONLY so net-new work is visible
> and `notrun` cases are explicit (no silent "covered"). Of 19 invariants: 6 REUSE-only, ~9 need net-new
> lints/runtime harnesses, ~4 are NAMED-ONLY (deferred with their layer). **Genuinely-executable-now ≈ 6 full +
> partial runtime ≈ 37% of I-surface** — stated plainly, not hidden.

### 1.2 Event/projection schema conformance — per-type semantic invariants

v1 swept all 14 event types under "generate valid streams" and specified only `npc.said` v1→v2. v2 adds the
**type-specific semantic invariants** — exactly the common-mode-bug surface — as named conformance tests:

| Event / type | Semantic invariant to assert | Why it matters |
|---|---|---|
| `canon.change.recorded` | **APPEND-ONLY — never edited/deleted (enforced 3 layers)**: assert UPDATE/DELETE rejected | hard, cheap, 0 coverage in v1 |
| `admin.canon.override.vetoed` | **veto ⇒ reality SKIPPED, NO compensating event emitted** (negative path: assert no emit) | skip-and-do-NOT-emit = common-mode magnet |
| `admin.canon.override.compensating` | **audit-distinguishable from `canon.entry.updated`** (L5.J classifies as force_propagate) | misclassification corrupts change-history |
| `npc_projection.core_beliefs` | **author-locked, immutable — LLM cannot mutate**; assert mutation rejected | security/integrity invariant |
| `world.tick` | simulation heartbeat drives scheduled NPC/weather/faction behavior; assert tick advances state deterministically | **0 coverage in v1** |
| `npc.said` v1→v2 | upcaster round-trip + replay-identical | (kept from v1) |
| all 14 | **codegen parity** (Go↔Rust↔TS↔Python regenerate → golden-diff, extend `eventgen-validate.sh`) | drift across 4 langs |

**Projection-table conformance (all 10 + embedding):**
- **VerificationMeta presence** — blanket schema test: all 10 tables carry the 5 Q-L3-4 columns (kept; this is the
  one v1 dimension at ~100%).
- **Per-table CHECK-constraint conformance** (v1 missing): `npc_pc_relationship_projection.trust_level` ∈ [-100,100];
  `region_projection` exits/floor_items JSONB-array shape; `session_participants.left_at` window; `world_kv` (only
  PK-on-text table) shape.
- **`npc_session_memory_embedding` pgvector/BYTEA DUAL-MODE** (v1's biggest spine-adjacent blind spot): the 0006
  `DO $vector_create$` block makes this `VECTOR(1536)` (prod) **or** `BYTEA` stub (no-pgvector env). The
  differential oracle (B) byte-compares `to_jsonb(t)` — **a `VECTOR` column's jsonb float serialization is
  environment-dependent and non-canonical**, and BYTEA-vs-VECTOR mode differs dev↔prod. Assert: (i) comparator
  excludes or canonicalizes the embedding column (don't byte-compare raw floats); (ii) the cycle-14 ALTER swap
  preserves data; (iii) the `octet_length(embedding) = 1536*4` (**6144-byte**) CHECK holds (0006:296). **Note:** a
  source comment in 0006 (line ~285) previously misstated this as an "8192-byte" vector — that comment was
  itself wrong (1536 fp32 × 4 = 6144) and has been corrected (0006:285, plus the propagated references in
  0008_pgvector_setup.up/down.sql). **This can make B silently pass or flap — must be designed
  before B is trusted on the embedding table.**
- **Projection-coverage** — every table has a registered Rust trait impl (REUSE `projection-coverage-lint.sh`).

### 1.3 The conformance RUNNER + results contract (v1 omitted — real suites need this)

A real LTP/xfstests suite ships machinery the catalog alone isn't:
- **Verdict schema** — uniform `{pass | fail | notrun | skip}` across heterogeneous tools (lints exit-code, Go
  `-tags=integration` tests, Rust tests, live probes) wrapped to one contract. **This wrapping IS the S1 build.**
- **`notrun`/skip semantics** — define *when* a runtime assertion legitimately skips (e.g. I4 on single-superuser
  dev stack, I5 before provisioner) vs fails-closed. Without this the live-stack half flaps and gets muted.
- **Expunge / known-failures list** (xfstests `-E`, LTP skiplist) — "known-broken, tracked, doesn't block the
  gate." Wire it to the repo's **Deferred-Items** discipline: catastrophic-rebuild (DEFERRED 149), monthly L3.F
  get expunge entries, not silent gaps.
- **Results store / history** — machine-readable results per run (parallels the perf time-series §8 needs for
  change-point detection). Lets us distinguish "newly failing" from "chronically skipped."
- **Where it lives** — new `tests/conformance/` tree (`generic/` + per-service) + a `conformance-ci.yml` (or extend
  `foundation-ci.yml`). Decided at S1.

---

## 2. Oracle strategy — sampled differential + structural + from-spec + log-integrity (B · C · C2 · C3)

### 2.1 Harden the existing differential (B) — and acknowledge it is SAMPLED
The integrity-checker (`services/integrity-checker/pkg/comparator`) does `SELECT to_jsonb(t) - <5 meta keys>` from
the live row vs a `replay-aggregate`-built temp row, canonicalize, byte-compare. **`live.go::CheckTable` checks
only `SampleRows(..., SampleSize)` — B is a *probabilistic* oracle, not exhaustive.** Plan:
- **Acknowledge sampling** in all coverage claims (v1 over-framed B as an xfstests *exhaustive* golden oracle).
- **Standing nightly gate** + **N seeded shards in parallel** (CockroachDB 50× lesson — raises rare-drift
  frequency, the correct mitigation for a sampled oracle that could otherwise hide a bug for months).
- Extend verdict coverage already started (orphan-drift, skip, `ErrOwnerPruned`).
- **B re-derives from the SAME `events` rows the projection consumed** → B verifies *projection-logic agreement*,
  NOT event-store integrity. That gap is closed by C3, not B.

### 2.2 Structural property oracle (C) — what it does and does NOT close
Generate random *valid* event streams (S3 generator) and assert, for ALL of them, properties that hold regardless
of impl — all checkable against real schema columns (`aggregate_version`, `event_id` exist on every projection
table):
- **monotonic `aggregate_version`** per aggregate (no decrease, no intra-aggregate gap).
- **no orphan rows** — every projection row's `event_id` references a real event.
- **idempotent apply** — re-applying the same event yields identical state.
- **deterministic replay** — same stream + same seed ⇒ byte-identical projection **cross-run** (this is C's
  strongest, genuinely-independent win: catches nondeterminism — clock/map-order/RNG/float — that the cross-impl
  differential cannot).

> **Honest limit (v2):** C is **structural, not from-spec**. `idempotent-apply` and `deterministic-replay` run
> events through the *same* Rust `all_projections()` code B uses → they are NOT independent of that impl for
> value-correctness; they catch nondeterminism, not common-mode spec-misreadings. A common-mode bug that computes a
> *wrong-but-monotonic, idempotent, non-orphan* value passes both B and C. `commutativity "where declared"` is
> dropped — nothing in the registry/traits declares it. **C closes nondeterminism + structural common-mode; it
> does NOT close value-level common-mode.**

### 2.3 From-spec reference oracle (C2) — closes the value-level common-mode gap **[new in v2, highest-value]**
Per SQLancer/PQS "construct the known answer." For the **highest-risk event→projection rules**, define an oracle
that does NOT depend on Go-projection or Rust-replay agreeing:
- **Option A — golden expected-value fixtures per event type:** a hand-authored table `{event payload → expected
  projection delta}` for each of the ~6 projecting event types and the canon semantic rules (§1.2). Replay applies
  the event; assert the projection delta equals the fixture. Cheap, high-signal, version-pinned.
- **Option B — tiny independent reference projector:** a deliberately-simple 3rd implementation (Python, ~hundreds
  of LOC) of the projection logic, used as a 3-way differential (Go vs Rust vs reference). Catches common-mode
  between Go+Rust if the reference reads the spec independently.
- **Start with A** (fixtures) — lower effort, covers the named semantic invariants directly; graduate to B if
  fixture maintenance becomes the bottleneck.

### 2.4 Event-store integrity ledger (C3) — closes the deepest blind spot **[new in v2]**
B and C both read the same `events` rows; a lost/duplicated/reordered/byte-rotted event is invisible to both. Add
an **independent log-integrity check**, not derived from the projection:
- **global-sequence completeness** — no gaps in the per-reality event sequence (every `aggregate_version` present
  from 1..N per aggregate; no missing global ordinal).
- **event-count ledger** — an independent count of emitted vs stored vs published events reconciles (catches silent
  loss that leaves a self-consistent partial projection).
- **stored-event integrity** — optional checksum/hash on the event payload at write, verified on read (catches
  byte-rot; the TigerBeetle storage-corruption lesson).
- This is the convergence oracle for the "lost events" and "archive corruption" fault scenarios (§3) that B/C miss.

> **Metamorphic relations** remain *supplementary only* (research REFUTED "solves the oracle problem"): permuted-
> causally-equivalent stream ⇒ same final state; truncate-then-extend consistent with full replay.

---

## 3. Fault matrix — Jepsen-style injection **+ history checker** (Technique D)

**Model:** Jepsen's value is *separating fault-injection from history-analysis*. v1 kept the nemesis but replaced
the analyzer with "integrity-checker reports zero drift after quiesce" — which only catches damage that *survives
to a quiescent state*, missing transient linearizability/ordering violations *during* the fault window. **v2
restores the history checker.**

### 3.1 Fault catalog (the nemesis) — needs a real injection harness (greenfield)

| Fault | Injection mechanism | Convergence + during-fault assertion |
|---|---|---|
| Postgres down | stop `postgres` container | outbox drains on restart; **C3 log-complete**; B/C post-quiesce |
| Postgres slow | **toxiproxy / `tc`** latency | I16 timeouts fire; no pool-exhaustion cascade; eventual convergence |
| Redis Streams partition | drop/partition `redis` | publisher resumes from last XID; **no event loss (C3)**; no dup-apply |
| MinIO unavailable | stop `minio` mid-archive | archive retries; **no partial-Parquet (C3 checksum)**; restore round-trips |
| Worker killed mid-batch | `docker kill` publisher/meta/archive | at-least-once + idempotent ⇒ no double-projection; outbox cursor correct |
| Duplicate/out-of-order events | seeded generator injection | idempotent apply; monotonic-version guard ignores stale |
| Partition rollover | force per-reality partition boundary | replay spans partitions; no boundary drift |
| Clock skew (multi-node) | skew container clocks | ordering by version not wall-clock; **per-message skew × outbox-cursor / Redis-XID interaction** (v1 had only coarse single-skew) |
| RabbitMQ down | stop `rabbitmq` | meta fan-out paths degrade + recover |
| Meta-HA split-brain | partition Patroni nodes | **history checker (below), not just "registry consistent"** |

> **Greenfield prereq (v2 acknowledges):** toxiproxy / `tc` / chaos tooling, and a Compose service to host them,
> **do not exist in repo** — S6 must build the injection harness + a quiesce detector. "NOW" means feasible on the
> live stack, not zero-setup.

### 3.2 The checker — history analysis, not just post-quiesce drift
1. **During-fault history analysis** — record the operation history and analyze with a linearizability/transactional
   checker. Reachable polyglot via **Maelstrom** (JSON-over-stdio, Jepsen's Knossos/Elle checkers) for
   protocol-level; for the meta-HA/registry path this is the **split-brain oracle** v1 lacked.
2. **integrity-checker zero drift** (B, sampled) post-quiesce.
3. **C3 log-complete** — no lost/dup/reordered events (the loss case B/C miss).
4. **replay reproduces** (B) + **structural properties** (C) + **from-spec fixtures** (C2) re-run post-fault.
5. **outbox drains to empty**; **archive round-trips** (C3 checksum verify, not symmetric-path equality only).

---

## 4. Model checking — Stateright / TLA+ (Technique E)
Design-time verification of Rust kernel protocols. Targets (priority order):
1. **`AttemptStateTransition()` graph** (I9) — no reachable state violates CAS; liveness: every transition completes
   or rolls back *(liveness in Stateright is experimental — may need TLA+ if cyclic paths defeat it)*.
2. **Outbox → publisher → consumer** (I13) — at-least-once + idempotent; no loss, no permanent dup under crash.
3. **Cross-reality fan-out** (I7) — `xreality.*` dispatch reaches exactly the intended per-reality streams, no leak.

Cost = model authoring (extract the state machines into Stateright actors); the `transitions-validation-lint.sh`
graph is the source for #1. Design-altitude — does not check the implementation's locking (that's H1-loom, §9).

---

## 5. Workload generator (S3) — **the critical-path build, re-sized to L–XL**

v1 rated this "M"; it is **L–XL and the dependency root of C, C2, C3, B-shards, D, F, H0.** A single seeded
generator feeds them all. "Valid event stream across 14 types" is non-trivial:
- **Per-event-type payload schemas** — only ~6 of 14 types project (canon.*, admin.canon.*, xreality.* don't feed
  the 10 L3.A tables); the generator must know each type's shape.
- **Monotonic per-aggregate version assignment** across 5 aggregates.
- **Valid cross-references** — a move event needs a real `to_region_id`; relationships need real entity ids.
- **Causal ordering** — events that depend on prior state ordered correctly.
- **Profiles:** `micro` (1 aggregate/1 table — for C unit tests) · `single-reality` · `multi-reality` (cross-shard,
  exercises I5/I7) · `multi-user-session` (exercises I6).
- **Output via the real outbox write path** so the whole base→derived pipeline runs.

For the **gateway/WS surface** (TS + Colyseus): open-loop HTTP/WS load via **wrk2/k6** (coordinated-omission-correct).
Optional schemathesis/RESTler API fuzzing (§11 open decision).

---

## 6. Per-layer scenario matrix (base → derived)

⊕ = an existing live-smoke already seeds it. Read with the §scope caveat: L2/L3 are deep; L1 + L4–L7 are
phased/structural.

### 6.1 L1 — Provisioning / Sharding / Capacity
Invariants I4, I5, I17. Components: reality_registry, provisioner (L1.C, *unbuilt*), meta HA (L1.E), budgets.
Scenarios: provision N realities → distinct DBs (I5); **service-role isolation (I4) — `notrun` on single-superuser
dev stack, needs role-segmented stage**; budget deploy-block (I17); scale-beyond-max → `admin/capacity-override`
24h-bounded; **meta-HA failover → split-brain history checker (§3.2), not just "consistent"**.

### 6.2 L2 — Event-store / Outbox / Publisher / Retention / Archive  **(deep)**
Invariants I13, I14. Components: `events` (0002 ⊕), outbox (0005), publisher ⊕, meta-worker ⊕, archive ⊕,
retention ⊕. Scenarios: outbox atomicity (I13); publisher drain + crash-resume; cross-reality fan-out ⊕;
archive PG→Parquet→MinIO→restore round-trip ⊕ **+ C3 checksum**; retention prune bounded ⊕; ship v2 event → v1 still
replays (I14) + `retire_after` date-boundary; **C3 log-integrity ledger over the event store**.

### 6.3 L3 — Projections / Replay / Rebuild / Integrity  **(the spine, deepest)**
Invariant: `projection==replay` + Q-L3-4. Components: 0006 ⊕, traits (`crates/projections/*`), replay-aggregate ⊕,
rebuilder ⊕, integrity-checker ⊕ (daily L3.E), monthly L3.F (deferred → expunge), metrics L3.J. Scenarios: clean-row
differential (B, sampled) ⊕; injected drift detected ⊕; cross-aggregate replay ⊕; rebuild round-trip ⊕;
catastrophic-rebuild (DEFERRED 149 → expunge); pgsource keyset scan ⊕; **C structural suite**; **C2 from-spec
fixtures**; **pgvector/BYTEA embedding comparator design (§1.2)**; lag/drift/duration/runs metrics bounded.
**Cover all 3 Rust kernel-derived aggregate services — `world-service` ⊕ AND `travel-service` + `tilemap-service`**
(v1 exercised only world-service though all are `#[derive(Aggregate)]` consumers the spine exists to protect).

### 6.4 L4–L7 — Domain (derived) **— phased, structural only**
Invariants I6, I10, canon Q-L5-*. Components: roleplay (L4, unbuilt), canon (`canon.*`, `admin.canon.override.*`
— owned by glossary-service), knowledge, quest/faction (future). Scenarios authored **as each layer lands**:
session FIFO + LLM-outside-tx (I6); prompt injection defense (I10); **canon semantic invariants from §1.2**
(append-only, veto-skip-no-emit, compensating-classification); cross-reality canon promotion fan-out.

### 6.5 Service-fleet coverage — explicit phasing (v1 left ~31 services at 0% silently)
- **Spine services (now):** world/travel/tilemap, publisher, meta-worker, archive, retention, integrity-checker.
- **Edge (now-ish):** api-gateway-bff + game-server (perf/WS load §8; I1 edge controls §1.1).
- **Domain novel-platform** (auth, book, sharing, catalog, provider-registry, billing, translation, glossary,
  notification, statistics): **phased** — note auth owns `xreality.user.erased`, glossary owns all canon.* events;
  their *event-contract* conformance (§1.2) is testable now even if the service flow is later.
- **AI/Python** (chat, knowledge, video-gen, worker-ai): phased with L4+.
- **SRE/ops fleet** (~12 bots: alert-recorder, backup-scheduler, canary-controller, incident-bot, oncall-bot,
  postmortem-bot, statuspage-updater, slo-budget-calculator, breach-notifier, chaos-engine, meta-outbox-relay,
  migration-orchestrator, admin-cli): **explicitly out of v2 spine scope; tracked, not forgotten** — these are
  operational, validated by their own integration tests + the §3 fault drills they participate in.

---

## 7. Recovery / DR drills (Technique G)
On the live stack (components exist): (1) kill+restart mid-workload → convergence (§3.2); (2) rebuild-from-events
→ `projection==replay` (B) + C + C2, seeded by `rebuilder_live.rs` ⊕; (3) restore-from-archive → replay reproduces
+ C3 checksum (needs a window-drop+restore orchestration not yet shown to exist); (4) replay determinism across two
rebuilds (= C deterministic-replay; do not double-count with H0); (5) catastrophic-rebuild (DEFERRED 149 → expunge).

---

## 8. Benchmark & perf-regression (Technique F)
Research-backed: **statistical gating, baseline-first, no fixed-%.**
- **Generators (open-loop, coordinated-omission-correct):** wrk2/k6/fortio → HdrHistogram → p50/p99/p999/p99.9.
- **Saturation/knee:** fit **USL** `X(N)=γN/(1+α(N−1)+βN(N−1))` across rates → `Nmax=sqrt((1−α)/β)`. **β (coherency)
  hypothesized to map to projection/replay cost + Redis backlog — this must be *measured*, not asserted** (v1 stated
  it as fact). Needs a multi-rate rig + a curve-fitter (greenfield).
- **Per-layer micro:** event-write throughput (L2), projection-apply latency (L3.B), replay/rebuild time per N
  events (L3.G), integrity-check duration (`lw_projection_check_duration_seconds` ⊕), WS fan-out (L4+).
- **Soak/endurance:** primary signal `lw_projection_lag_seconds` ⊕ (trends up under steady load ⇒ pipeline behind);
  secondary: outbox depth, Redis stream length, RSS.
- **CI gate (statistical):** benchstat (Mann-Whitney @α=0.05, Go) · hyperfine (binary wall-clock, any-lang) ·
  **Bencher** as cross-lang gate — `percentage`/`t_test` + `--error-on-alert` first, **graduate to change-point once
  a per-commit time-series exists** (fixed-% is a documented anti-pattern). **Confirm Bencher self-host** (§11) —
  it is the named gate but its self-host path for AWS/Compose is unvalidated.
- **No pass/fail numbers asserted until baselined** — F ships a *method*, baselines are S7's first output.

---

## 9. DST feasibility — tiered, with **loom/shuttle pulled EARLY** (Technique H)
Determinism checklist: single-threaded · seeded RNG · virtual clock · no external IO. Whole-stack DST is a larger
build — but **kernel-local interleaving DST is cheap here because the Rust replay path is ALREADY deterministic**
(VOPR/Flow's hardest cost is already paid). v2 splits the tier:

| Tier | Scope | Path | Effort | When |
|---|---|---|---|---|
| **H0 — seeded determinism** | replay-determinism + C reproducibility | seed the S3 generator | low | with C (note: = G.4, don't double-count) |
| **H1-loom — kernel-local interleavings** | **outbox→publisher→apply concurrency, loom/shuttle** | free; determinism precondition already met | **S/M — moved EARLY (~S6)** | targets the deep-race class C/structural is blind to |
| **H1-madsim — Rust kernel sim** | world/travel/tilemap under sim clock/net/disk | madsim/turmoil (instrument code) | medium-large/service | after spine |
| **H2 — whole-stack DST** | entire Compose stack, hypervisor faults | **Antithesis** (paid, wraps compose) | external $ | strategic, near-prod |

**Sequencing verdict (from benchmark):** "conformance+property first, whole-stack-DST last" is **defensible** —
DST needs the invariants-as-assertions to check against, and whole-stack determinism is genuinely a large build.
**But v1 wrongly bundled cheap kernel-local loom/shuttle into the far tier** — its precondition is met and it
catches the race class the structural oracle misses, so it moves up beside the fault matrix. **Do NOT defer all DST
to near-prod** (that is exactly how CockroachDB's bug stayed latent 2 years).

---

## 10. Incremental roadmap — re-ordered (S3 before S2)

| Slice | Deliverable | Tech | Feasible | Effort (v2) | Depends on |
|---|---|---|---|---|---|
| **S1** | **Conformance runner + catalog** — verdict schema, notrun/skip, expunge-list, results store; fold REUSE lints + 9 live-smokes | A | NOW | **M–L** (the wrapping IS the build) | — |
| **S3** | **Seeded workload generator** — valid streams across 14 types, version-monotonic, valid refs, causal order, 4 profiles | (feeds C/C2/C3/D/F/H0) | NOW | **L–XL** (critical path) | — |
| **S2** | **Property oracle (C)** + **from-spec fixtures (C2)** — structural props + golden expected-value per event type | C, C2, H0 | after S3 | **L** | S3 |
| **S2b** | **Event-store integrity ledger (C3)** — global-sequence/count/checksum | C3 | NOW–after S3 | M | (S3 for stress) |
| **S4** | **Runtime invariant assertions** — I4/I5/I8/I9 live probes (+ notrun rules); schema/VerificationMeta/upcaster/CHECK conformance; pgvector comparator design | A | NOW | M–L | S1 |
| **S5** | **Standing integrity gate + parallel shards** — nightly B, N seeded shards | B | after S3 | S–M | S3 |
| **S6** | **Fault matrix v1 + history checker + loom/shuttle** — injection harness (toxiproxy/`tc`), quiesce detector, Maelstrom/Elle history analysis, loom on outbox→apply | D, H1-loom | NOW (build infra) | **L–XL** | S3, S2b |
| **S7** | **Perf harness** — wrk2/k6 + USL rig + curve-fit + Bencher/benchstat/hyperfine gate; baseline KPIs; confirm Bencher self-host | F | NOW | L | S3 |
| **S8** | **Recovery/DR drills** — kill/restart, rebuild, restore round-trip+checksum, replay determinism | G | NOW | M | S2, C3 |
| **S9** | **Model checking** — Stateright: AttemptStateTransition + outbox + fan-out | E | NOW | M–L | — |
| **S10** | **Rust kernel sim DST (H1-madsim)** | H | LARGER | L–XL | spine |
| **S11** | **Whole-stack DST (H2 / Antithesis eval)** | H | STRATEGIC | external | — |

**Build order (corrected):** **S1 → S3 → {S2, S2b, S4, S9} → S5 → S6 → S7 → S8 → S10 → S11.** S3 is the gate;
nothing in the correctness spine builds before the generator exists.

---

## 11. Open decisions (carry into implementation, do not block the plan)
1. **Fuzzing direction** (research unverified): syzkaller-style event-write interface fuzzing vs schemathesis/RESTler
   gateway OpenAPI fuzzing — can either reuse `projection==replay` / C2 as the violation signal? Add an S-slice at
   S6/S7 rather than leaving it roadmap-less.
2. **Internal-harness template** (unverified): FoundationDB Flow vs Kafka Trogdor+ducktape vs CockroachDB
   roachtest+sqlsmith — decide at S6/S10.
3. **Bencher threshold-test** (t_test vs percentage vs change-point) for dev-noise vs prod; gate in dev CI vs
   dedicated stable runner. **Confirm Bencher self-host** before committing it as the gate.
4. **C2 form** — golden fixtures (start) vs independent reference projector (graduate).
5. **DST H1-madsim vs H2 sequencing** — open-source first or evaluate Antithesis earlier.
6. **I15 / I4** — build the missing lints (ID-catalog, per-service-role stage) or formally mark code-review-only /
   notrun-on-dev.

---

## 12. Acceptance criteria for THIS plan (the doc)
- [x] Honest scope stated: spine-first, phased to whole-foundation (no whole-foundation overclaim).
- [x] Correctness spine corrected to `B(sampled) ∧ C(structural) ∧ C2(from-spec) ∧ C3(log-integrity)`.
- [x] Layer → invariant → component → scenario matrix (§6) base→derived, with phasing made explicit.
- [x] Per-event-type semantic invariants named (§1.2); pgvector dual-mode hazard named.
- [x] Conformance runner machinery specified (§1.3): verdict schema, notrun/skip, expunge, results store.
- [x] Fault matrix + **history checker** (not post-quiesce drift only) (§3).
- [x] Workload generator re-sized to L–XL and placed before its dependents (§5, §10).
- [x] DST tiered; loom/shuttle pulled early; whole-stack DST defer justified (§9).
- [x] Perf approach statistical + baseline-first; β-mapping flagged as to-measure (§8).
- [x] Service-fleet coverage phased explicitly, not silently dropped (§6.5).
- [x] Every choice traces to a verified research finding + the benchmark; net-new vs reused tagged (§1.1).
- [x] Open decisions tracked (§11).

---

## 13. Changelog — v1 → v2 (from the 4-reviewer coverage benchmark)
1. **Scope honesty** — retitled "whole-foundation" → "spine-first, phased"; added explicit caveat that L2/L3 are
   deep and L1/L4–L7/fleet are structural/phased. (breadth + reference reviewers)
2. **Spine correctness** — `B∧C` → `B∧C∧C2∧C3`; added **C2 from-spec oracle** (value-level common-mode) and **C3
   event-store integrity ledger** (deepest blind spot); acknowledged **B is sampled**; demoted C to structural-only.
   (failure-mode + reference reviewers, convergent)
3. **Fault history checker** — §3 restored Jepsen's history-analysis half (Maelstrom/Elle); split-brain gets a real
   checker; added per-message clock-skew × cursor interaction. (failure-mode + methodology + reference, all 3)
4. **S3 re-sized** M→L–XL and **reordered before S2**; build order corrected to S1→S3→…. (methodology)
5. **Greenfield acknowledged** — toxiproxy/`tc`/k6/Bencher/proptest/stateright/`tests/conformance/` all absent;
   "NOW" = feasible-with-build, not zero-setup. (methodology + reference)
6. **Conformance runner machinery** added (§1.3): verdict schema, notrun/skip, expunge-list, results store.
   (reference)
7. **loom/shuttle pulled early** to ~S6 (cheap because replay is already deterministic); whole-stack DST defer kept.
   (reference)
8. **Per-event-type semantic invariants** (§1.2): canon.change append-only, override.vetoed skip-no-emit,
   compensating-classification, core_beliefs immutability, world.tick. **pgvector/BYTEA dual-mode comparator hazard.**
   (breadth)
9. **Restored dropped invariant-halves**: I12 model-names, I19 emission-time + cardinality note, I1 WS edge controls,
   I14 retire_after date-boundary. (breadth)
10. **Net-new vs reused tagging** (§1.1) so the ~37%-executable reality is visible, not hidden; I15/I4 hazards flagged
    (no existing lint / single-superuser stack). (breadth + methodology)
11. **All 3 Rust kernel services** (world/travel/tilemap), not just world-service. (breadth)
12. **Service-fleet phasing** explicit (§6.5) — ~31 previously-0% services tracked, not silently dropped. (breadth)
