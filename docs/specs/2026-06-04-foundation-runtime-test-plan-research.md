# Research — How OS-scale / large distributed & event-sourced systems validate themselves (2026)

> **Purpose.** Groundwork for the upcoming *foundation runtime test plan* task. This file captures the
> deep-research output (adversarially verified, cited) on how large systems test their own correctness
> and performance as of 2026, then maps each technique onto OUR foundation with feasibility + ROI.
>
> **Status:** Research pass 1 complete (24/25 claims confirmed, 1 refuted). Pass 2 pending — fills the
> coverage gaps listed at the bottom (perf-regression, conformance suites, syscall/API fuzzing, FDB/PG/Kafka harnesses).
>
> **Method:** `deep-research` workflow — 5 search angles, 22 sources fetched, 102 claims extracted,
> 25 verified by 3-vote adversarial verification (need 2/3 refutes to kill).
>
> **Our context.** Event-sourced, per-reality-sharded, multi-language (Rust = kernel-derived world/travel/tilemap,
> Go = domain/meta, Python = AI/LLM, TS = gateway/BFF + Colyseus realtime). Postgres per-service + Redis Streams
> (jobs) + MinIO (objects). Docker Compose for dev, AWS for prod. The single load-bearing correctness invariant
> is **`projection == replay(events)`**, whose runtime oracle already exists: the L3.E/F integrity-checker
> (Go-written projection vs Rust event-replay, byte-compare differential).

---

## TL;DR

As of 2026 the dominant correctness methodology for distributed/event-sourced systems is **Deterministic
Simulation Testing (DST)** — run the system in a simulated environment controlling clock + thread-interleaving
+ randomness, so concurrency/timing/state bugs reproduce 100% from a **seed** and can be rolled back to inspect
(FoundationDB Flow, TigerBeetle VOPR, S2 "mad-turmoil", WarpStream-via-Antithesis). It is complemented by
**Jepsen-style fault-injection + checker** as a standing nightly oracle (CockroachDB) and **model/property-based
checking** (Stateright in Rust).

**Hard-won lesson, repeated across every system: no single oracle is sufficient.** DST and Jepsen both let real
bugs survive for *years*. Most directly relevant to us: a **differential oracle like `projection == replay` is
blind to common-mode bugs** — if the Go projection and the Rust replay share the same wrong reading of the spec,
they emit byte-identical wrong output and the integrity-checker silently passes.

---

## (1) Methodology — verified (high confidence)

| Technique | Proves | Limit |
|---|---|---|
| **DST** (FDB Flow, TB VOPR, S2 mad-turmoil, WarpStream/Antithesis) | Presence of deep concurrency/timing bugs + perfect reproduction from a seed. WarpStream: 6 wall-clock h ≈ 280 simulated h (skips `time.Sleep`). | Only controls non-determinism sources **inside** the harness. |
| **Jepsen** (nemesis + checker; Knossos linearizability, Elle transactional cycles) | Whether recorded operation histories are consistent under a chosen model during partitions/faults. Cleanly separates fault-injection from correctness analysis. | Sampling-based → can miss rare bugs. |
| **Property / model-based** (Stateright, TLA+/P) | Invariants hold for ALL generated inputs/states. Stateright models can also run on a real network without reimplementation. | Must author the model; Stateright liveness checking is experimental (acyclic paths only). |
| **Differential** (= OUR `projection==replay`) | Two independent implementations agree. | **Blind to common-mode bugs** (VLDB 2024 "Gamera"): identical wrong logic → identical wrong output → no discrepancy. Directly limits our integrity-checker. |

> ⚠️ The claim that **metamorphic testing "solves the oracle problem"** was **REFUTED** (vote 1-2). Treat
> metamorphic relations as a *supplementary* independent oracle, not a proven solution. The differential-oracle
> common-mode limitation, by contrast, is firmly established.

**Determinism checklist for DST** (the line between "feasible now on live stack" vs "larger build"), per S2 /
Phil Eaton / corroborated independently: **single-threaded execution · seeded RNGs · no physical clocks (virtual
clock) · no IO to anything outside the simulation.** Our live stack is multi-process with real PG/Redis/MinIO and
real clocks → true DST needs a deterministic clock/network/disk shim (or the Antithesis hypervisor wrapping the
whole stack).

---

## (2) Tooling current to 2026 — alive & usable for our stack

- **Rust DST, open-source (no license cost):** `madsim` (deterministic tokio-compatible runtime; used in
  production by RisingWave; idea borrowed from FoundationDB + sled) + `turmoil` (simulated networking) +
  `loom`/`shuttle` (concurrency-interleaving model checkers). S2 combined Tokio single-thread paused-clock +
  Turmoil + MadSim libc overrides (`clock_gettime`/`getrandom`) into a custom "mad-turmoil" crate. → **the free
  DST path for our Rust world/travel/tilemap services.** Effort: medium-to-large per service (code must be
  instrumented for in-process determinism).
- **Antithesis** (commercial, hosted hypervisor; license/cost applies): deterministically simulates an **entire
  set of Docker containers** and injects faults — WarpStream proved it runs against a real SaaS stack expressed
  as **standard `docker-compose` files + Docker images, no service rewrite**. Caught a metrics-library data race
  in **233 seconds** that 10,000+ hours of CI with Go's race detector never found. → strongest evidence our
  Docker-Compose dev stack is a viable DST target via the paid path.
- **Jepsen + Maelstrom:** Maelstrom is a Jepsen-based workbench where nodes are written in **any language** over
  JSON-on-STDIN/STDOUT/STDERR, with built-in fault injection (latency, loss, partitions) and Jepsen checkers up to
  strict serializability. → exercise Rust/Go/Py/TS node logic against Jepsen checkers **without Clojure**. Caveat:
  Maelstrom suits protocol/algorithm validation; for full-system runs use native Jepsen against the real services.
- **Stateright** (Rust): embedded model checker + behavior-exploration UI + lightweight actor runtime; verifies
  `always` (safety), `sometimes` (nontriviality), `eventually` (liveness — experimental). Unlike TLA+, models can
  run on a real network. → model-check the Rust kernel-derived protocols at design time. Effort: medium (model authoring).

---

## (3) Real-system case studies — verified

- **TigerBeetle.** Primary correctness method is **DST via a single test (VOPR)**: runs an entire cluster on one
  thread, simulating clock/disk/network — clock skew, read/write corruption, message loss & reordering — and is
  deterministic from a **seed + git commit**, so any bug reproduces perfectly. *But:* a missing-query-results bug
  (#2544) **evaded all four fuzzers** (two did no joins; two generated consecutively-indexed objects so the
  zig-zag merge-join path never ran). External Jepsen still found two genuine safety issues; only by 0.16.30 did
  TB appear to meet Strong Serializability. → VOPR is the reference architecture for a future full-DST build of
  our Rust kernel services; it is the "larger build" tier, not feasible on a vanilla live stack.
- **CockroachDB.** Ran **Jepsen nightly since before 1.0**, yet a pipelined-writes consistency bug **stayed
  latent ~2 years** (since v2.0) and reproduced only ~once/month. Fix-ROI: built a harness running **50 parallel
  copies** to raise reproduction frequency enough to gather diagnostics. → **parallelism-for-frequency** is the
  lesson; applies equally to seeded DST runs and to our integrity-checker as a nightly gate.

---

## Recommendations — mapped to our foundation (by ROI / effort)

**Feasible NOW on the live Docker-Compose stack (low→medium effort):**

1. **Pair an independent 2nd oracle** with `projection==replay` to kill common-mode bugs — property-based
   invariants over event streams (proptest/Hypothesis: monotonic version, idempotent apply, no-orphan rows)
   and/or metamorphic relations. **This is the single most important gap** — the current oracle is structurally
   blind, and our own live-smoke history (a heavily unit-tested keystone that was 100% broken at runtime) shows
   the failure mode is real here.
2. **Make the integrity-checker a STANDING nightly gate** (not ad-hoc) and run **many seeded shards in parallel**
   (CockroachDB 50× lesson) to surface rare drift.
3. **Jepsen / Maelstrom** against the Rust kernel-derived services via a JSON-stdio shim.
4. **Stateright** to model-check the world/travel/tilemap state machines at design time.

**Larger build, but strongest demonstrated bug-finding ROI (proven):**

5. **Full DST** for the Rust kernel services — free `madsim/turmoil/loom/shuttle` path (instrument code for
   in-process determinism), or commercial **Antithesis** wrapping the whole Docker-Compose stack (paid, minimal
   code change). This is our "VOPR" tier.

---

## Coverage gaps — (RESOLVED by research pass 2, see below)

> **Update:** pass 2 (bottom of this doc) filled these. Perf-regression + conformance are now VERIFIED
> high-confidence; fuzzing + internal-harness case studies are primary-sourced but not yet 3-vote verified.

Pass 1 is strong on DST + Jepsen + Stateright + the differential-oracle limit, but produced **zero verified
primary-source evidence** on the following — these were the targets for pass 2 and must NOT be stated at the
confidence of the verified findings above:

- **All of area (4) — Benchmark / perf-regression at scale:** k6 / vegeta / fortio / oha workload generators,
  p50/p99/p999 + saturation-point discovery, soak/endurance (leak + backlog) detection, CI perf-regression gating
  + threshold-setting.
- **Conformance suites:** POSIX PTS, Linux LTP, xfstests, kernel selftests — harness architecture & ROI.
- **Syscall / interface fuzzing:** syzkaller-style.
- **API fuzzing:** schemathesis, RESTler — for the gateway/BFF + service-boundary surface.
- **Fault-injection infra tooling:** toxiproxy, chaos-mesh, pumba.
- **Specific internal harnesses** of FoundationDB (Flow simulation), PostgreSQL (regression / isolation / TAP),
  Apache Kafka (Trogdor / ducktape); concrete TLA+ / P usage.

---

## Sources (verified findings)

- Antithesis — DST docs: <https://antithesis.com/docs/resources/deterministic_simulation_testing/> (primary)
- WarpStream — DST for our entire SaaS: <https://www.warpstream.com/blog/deterministic-simulation-testing-for-our-entire-saas> (primary)
- Antithesis — WarpStream case study: <https://antithesis.com/case_studies/warpstream/>
- S2 — DST blog ("mad-turmoil"): <https://s2.dev/blog/dst> (primary)
- Jepsen — TigerBeetle 0.16.11 analysis: <https://jepsen.io/analyses/tigerbeetle-0.16.11> (primary)
- TigerBeetle — VOPR internals: <https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md> (primary)
- CockroachDB — Jepsen lessons: <https://www.cockroachlabs.com/blog/jepsen-tests-lessons/> (primary)
- CockroachDB — demonic nondeterminism: <https://www.cockroachlabs.com/blog/demonic-nondeterminism/> (primary)
- madsim: <https://github.com/madsim-rs/madsim> (primary) · turmoil: <https://github.com/tokio-rs/turmoil>
- Jepsen: <https://github.com/jepsen-io/jepsen> · Maelstrom: <https://github.com/jepsen-io/maelstrom> (primary)
- Stateright: <https://github.com/stateright/stateright> · <https://docs.rs/stateright> (primary)
- VLDB 2024 "Gamera" — differential-oracle common-mode limit: <https://www.vldb.org/pvldb/vol17/p836-zhuang.pdf> (primary)
- DST determinism checklist (Phil Eaton): <https://notes.eatonphil.com/2024-08-20-deterministic-simulation-testing.html> (blog)
- Linux kernel testing overview: <https://docs.kernel.org/dev-tools/testing-overview.html> (primary)
- awesome-DST list: <https://github.com/ivanyu/awesome-deterministic-simulation-testing>

### Refuted
- "Metamorphic testing solves the test-oracle problem" — vote 1-2, source VLDB 2024 p836. Treat metamorphic
  relations as a supplementary oracle only.

### Source-quality caveats
- DST ROI figures (WarpStream 233 s, 280/160 simulated-h, S2 "17 notable bugs") are first-party self-reported
  anecdotes from vendors / Antithesis customers — illustrative, not controlled benchmarks.
- Antithesis is commercial/paid; the open-source madsim/turmoil/loom/shuttle path requires instrumenting your own
  code and does not wrap an arbitrary multi-process Docker-Compose stack the way Antithesis does.

---
---

# Research pass 2 — Perf-regression · Conformance · Fuzzing · Internal harnesses

> Fills the pass-1 gaps. **Areas (1) perf-regression and (2) conformance are verified high-confidence (3-0
> unanimous, primary sources).** Areas (3) fuzzing and (4) internal-harness case studies produced **no surviving
> 3-vote-verified claims** this pass (claims were extracted but dropped from the verified top-25 by token budget) —
> their primary sources WERE fetched and are cited below as **primary-sourced but not yet adversarially verified**.
> Method: 6 angles, 29 sources fetched, 136 claims extracted, 25 verified (24 confirmed, 1 refuted).

## (4) Benchmark & perf-regression at scale — VERIFIED (high confidence)

**The industry has moved from fixed-% thresholds to STATISTICAL gating.** Polyglot tool stack that fits Rust/Go/Py/TS:

| Tool | Role | Notes (all open-source/free unless noted) |
|---|---|---|
| **benchstat** (`golang.org/x/perf`) | Go micro-benchmark A/B gate | Non-parametric by default — **Mann-Whitney U at α=0.05**, median summaries. Gates on statistical significance, not %-change. |
| **hyperfine** | CLI/binary-level wall-clock, **language-agnostic** | ≥10 runs / ≥3 s default, mean/stddev/min/max + built-in outlier detection (interference + caching). Wraps any command → Rust kernel bins, Python AI, TS gateway. (Outlier detection *warns*, doesn't gate.) |
| **Bencher** | Cross-language **CI gate** | 7 selectable threshold tests via `--threshold-test`: `static, percentage, z_score, t_test, log_normal, iqr, delta_iqr`. Breached Boundary Limit → Alert; `--error-on-alert` fails the CI step. **Open-source self-hostable + paid hosted tier** — confirm self-host for our AWS/Compose model. |
| **wrk2** | Open-loop load + tail latency | Constant offered rate via `-R/--rate` (vs wrk's closed-loop). **Corrects Coordinated Omission** (naive generators stop sending during latency spikes → understate tails). Records to **HdrHistogram** → lossless p99.9999. Same open-loop model: k6, fortio, vegeta. |

- **Fixed-% thresholds are a documented anti-pattern** for noisy suites (MongoDB retrospective + ICPE 2020 Daly
  et al. + DataStax "Hunter" ICPE 2023): they answer "did perf change >X%" but the real question is "WHICH commit
  changed it" — the two only coincide for large changes in low-noise envs. Old fixed-threshold systems "missed
  small regressions, flagged a lot of false positives on noisier tests, and sometimes flagged real things at the
  wrong time." **Upgrade = change-point detection** (E-Divisive means over the full commit time-series) — robust to
  run-to-run variation that noise reduction alone can never eliminate. **But it requires accumulated history** →
  start with Bencher percentage/t-test gating, graduate to change-point once a time-series exists.
- **Saturation / knee-point discovery = Universal Scalability Law.** `X(N) = γN / (1 + α(N−1) + βN(N−1))`
  (γ=concurrency, α=contention, β=coherency). Knee load computed directly: **`Nmax = sqrt((1−α)/β)`**. For us, **β
  (coherency) maps to projection/replay consistency cost + Redis-Streams backlog** — a natural fit. Method: measure
  p50/p99/p999 at fixed offered rates with wrk2/k6/fortio, fit USL across rates → find Nmax.

**MAP TO US (feasible NOW, low effort):** hyperfine + Bencher for polyglot perf-gating; wrk2/k6 open-loop for the
event-write path + gateway/WS surface; the existing `lw_projection_lag_seconds` gauge is a candidate
soak/endurance signal for backlog/drift growth. Change-point detection = longer-term upgrade.

## (2) Conformance / selftest suites — VERIFIED (high confidence)

**Uniform pattern across OS-scale projects: one behavior = one test entry; pass decided by golden-output
differential + exit status.**

- **xfstests/fstests** decides pass by **4 conditions**: no core file · no `$seq.notrun` (skip) · exit status 0 ·
  actual output == pre-recorded golden `$seq.out`. Structure: cross-implementation **`generic/`** battery + per-target
  dirs (`xfs/`, `ext4/`) → one assertion runs against many implementations.
- **LTP** = reliability/robustness/stability battery as automation; each test a standalone shell/C binary, config
  via env/CLI, reports via exit value; catalog enforces **one `runtest` entry per test** ("wrapper-of-many strongly
  discouraged"). *(Nit: "one entry per test" is catalog-level, not literal per-assertion.)*
- **Kernel splits by granularity:** **KUnit** (in-kernel isolated unit tests, Arrange-Act-Assert, one behavior per
  test, run at boot/module-load, no reboot) + **kselftest** (whole-feature, userspace-facing).
  *(REFUTED 0-3: the claim that the kernel mandates kselftests for all new syscalls — it does NOT gate that way.)*

**MAP TO US (highest near-term ROI):** our integrity-checker (Go projection vs Rust replay byte-differential) **is
already an xfstests-style golden oracle** for `projection==replay`. Build an **LTP-style battery where each of I1–I7
and each event/projection schema rule = one standalone test binary with a golden expectation**, organized
`generic/` (cross-reality-shard) + per-service, gating releases on exit status — **KUnit-altitude** assertions
inside each Rust/Go service, **kselftest-altitude** whole-flow checks across the live Docker-Compose stack.

## (3) Fuzzing — primary-sourced, NOT yet 3-vote verified

Sources fetched (claims didn't survive budget into the verified top-25 — treat as leads, verify before committing):
- **syzkaller** — coverage-guided syscall fuzzer, syscall-description grammar, corpus, crash repro: <https://github.com/google/syzkaller>
- **RESTler** (Microsoft) — stateful REST-API fuzzing from OpenAPI: <https://www.microsoft.com/en-us/research/publication/restler-stateful-rest-api-fuzzing/>
- **OSS-Fuzz CI model** (continuous fuzzing integration): <https://google.github.io/oss-fuzz/getting-started/continuous-integration/>
- Coverage-guided fuzzing surveys: ACM <https://dl.acm.org/doi/10.1145/3597205> · arXiv <https://arxiv.org/pdf/2112.10328>
- **Open question (unresolved):** for our event-write path, does syzkaller-style interface fuzzing (event types as a
  "syscall" grammar) beat schemathesis/RESTler OpenAPI fuzzing of the gateway — and can either reuse
  `projection==replay` as the crash/violation signal?

## (4-bis) Internal-harness case studies — primary-sourced, NOT yet 3-vote verified

Sources fetched (verify before adopting a template):
- **FoundationDB** — Flow deterministic simulation + **Buggify** fault injection: <https://apple.github.io/foundationdb/testing.html> · <https://github.com/apple/foundationdb/blob/main/flow/include/flow/Buggify.h>
- **Apache Kafka** — **Trogdor** fault-injection + ducktape: <https://github.com/apache/kafka/blob/trunk/trogdor/README.md>
- **CockroachDB** — **roachtest**: <https://github.com/cockroachdb/cockroach/blob/master/pkg/cmd/roachtest/README.md> · **metamorphic** testing: <https://www.cockroachlabs.com/blog/metamorphic-testing-the-database/> · **sqlsmith** randomized SQL: <https://www.cockroachlabs.com/blog/sqlsmith-randomized-sql-testing/>
- **SQLancer / PQS** (Rigger, OSDI 2020) — randomized oracle for DB correctness: <https://www.usenix.org/system/files/osdi20-rigger.pdf>
- **Csmith** — randomized differential test-case generation: <https://github.com/csmith-project/csmith>
- **Open question (unresolved):** best template for our live-stack harness — FDB Flow (closest to our deterministic
  Rust replay kernel + buggify), Kafka Trogdor+ducktape (closest to our Redis-Streams job/fault model), or
  CockroachDB roachtest+sqlsmith/metamorphic (closest to randomized cross-service)? Needs a dedicated case-study pass.

## Pass-2 license/cost note
hyperfine · benchstat · wrk2 · LTP · xfstests · KUnit · syzkaller · RESTler · roachtest = open-source/free.
**Bencher** = open-source self-hostable + paid hosted tier (confirm self-host path).

## Still-open after pass 2
- Fuzzing direction (syscall-grammar vs OpenAPI) — fetched, not verified.
- Internal-harness template choice (FDB / Kafka / Cockroach) — fetched, not verified.
- Can `lw_projection_lag_seconds` double as the soak/endurance backlog+drift signal; what `Nmax` our
  per-reality-shard pipeline exhibits under open-loop load.
- Bencher threshold-test choice (t_test vs percentage vs change-point) for Docker-Compose-dev noise vs AWS-prod;
  gate in dev CI vs only on a dedicated stable runner.
