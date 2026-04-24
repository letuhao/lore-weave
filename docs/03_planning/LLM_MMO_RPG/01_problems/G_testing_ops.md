<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: G_testing_ops.md
byte_range: 28604-31700
sha256: 88031460fd7d39f809d80833dd8293f8fda44f4f2a5bd34fe493bddaf17af16e
generated_by: scripts/chunk_doc.py
-->

## G. Testing & operations

### G1. CI for non-deterministic LLM flows — **PARTIAL**

**Problem:** Unit tests assume determinism. LLM output varies. Regression test suites become flaky or meaningless.

**Resolved by:** 3-tier testing framework in [`05_qa/LLM_MMO_TESTING_STRATEGY.md §2`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#2-g1--ci-for-non-deterministic-llm-flows):

- Tier 1 (G1-D1) — unit tests with frozen mock LLM (prompt-hash keyed fixtures; <1s; per-PR)
- Tier 2 (G1-D2) — nightly integration on cheap real LLM (~30 scenarios, 85% pass-rate threshold)
- Tier 3 (G1-D3) — weekly LLM-as-judge scorecard (Sonnet/GPT-4.1 grading rubric dimensions vs baseline)
- Fixture maintenance via `admin-cli regen-fixtures` with mandatory human review (G1-D4)
- Canonical scenario library at `docs/05_qa/LLM_TEST_SCENARIOS.md` (G1-D5)

Decisions G1-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:** rubric dimension weights, judge-model bias calibration — V1 tuning.

### G2. Multi-user load/simulation testing — **PARTIAL**

**Problem:** How to load-test an MMO with LLM in the loop? Real LLM costs real money; mocked LLM doesn't exercise real latency/failure modes.

**Resolved by:** Tiered load matrix in [`05_qa/LLM_MMO_TESTING_STRATEGY.md §3`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#3-g2--multi-user-load--simulation-testing):

- Tier 1 (G2-D1) — mocked LLM at 1000 concurrency for pipeline stress, hourly
- Tier 2 (G2-D2) — real LLM at 10-20 concurrency for latency/throughput, daily on staging
- Tier 3 (G2-D3) — full-stack pre-production (V1 50/$50, V2 200/$200, V3 1000/$1000), weekly
- New service `loadtest-service` with script library (casual / combat / fact / jailbreak) (G2-D4)
- Admin auth + hard budget kill-switch for real LLM runs (G2-D5)

Decisions G2-D1..D5 locked 2026-04-23.

**Residual `OPEN`:** script library coverage breadth, target-scale rebalancing — V1 playtest.

### G3. Canon-drift detection in production — **PARTIAL**

**Problem:** In live play, NPC may say things that contradict canon. How to detect and alert?

**Resolved by:** 5-layer detection + feedback loop in [`05_qa/LLM_MMO_TESTING_STRATEGY.md §4`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#4-g3--canon-drift-detection-in-production):

- Layer 1 (G3-D1) — async post-response lint against knowledge-service oracle, logs to `canon_drift_log`
- Layer 2 (G3-D2) — user "that's not right" button with categorized reports + per-NPC aggregation
- Layer 3 (G3-D3) — per-reality drift dashboard in DF9 with alert thresholds
- Layer 4 (G3-D4) — auto-remediation (memory regen, persona rotation, temporary NPC suspension on severe drift)
- Layer 5 (G3-D5) — feedback loop: production drifts → G1 adversarial fixtures (human-curated promotion)
- Per-tier SLOs (G3-D6): free <5%, paid <2%, premium <0.5%

Decisions G3-D1..D6 locked 2026-04-23.

**Residual `OPEN`:** drift-detection LLM overhead cost per session, adversarial fixture auto-generation quality — V1 measurement.

---

---

