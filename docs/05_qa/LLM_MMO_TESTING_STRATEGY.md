# LLM MMO Testing Strategy

> **Status:** Locked design — 16 decisions committed 2026-04-23. Testing + ops contract for the LLM MMO RPG track.
> **Scope:** Resolves [G1 / G2 / G3](../03_planning/LLM_MMO_RPG/01_OPEN_PROBLEMS.md) from the open-problems list.
> **Created:** 2026-04-23
> **Owner:** QA Lead + Tech Lead

---

## 1. Why this doc exists

An LLM-in-the-loop MMO breaks the usual test contract: unit tests assume determinism, but every LLM call is non-deterministic. Load tests cost real money per request. Production drift is invisible until a user complains.

This doc locks a tiered framework that spans the three concerns and gives each a clear home:

- **G1 — CI for non-deterministic LLM flows**: how we guard correctness without relying on determinism
- **G2 — Multi-user load / simulation testing**: how we characterize real-system behavior without burning infinite LLM budget
- **G3 — Canon-drift detection in production**: how we catch LLM output that contradicts canon after release

The three form one loop: G3 production drifts → G1 regression fixtures → G2 simulator scripts → prevent future drift.

---

## 2. G1 — CI for non-deterministic LLM flows

### 2.1 Tier 1 — Unit tests with frozen mock LLM (G1-D1)

- Mock LLM returns pre-recorded responses keyed by **prompt hash**
- Tests the **wiring**, not the LLM: prompt assembly, 3-intent classifier routing (A5-D1), tool dispatch, output filter, event emission
- <1 s per test, deterministic, runs on every PR
- Fixtures live at `services/roleplay-service/tests/fixtures/llm_responses/` (create structure on first test)

Test shape:

```python
def test_canonical_fact_routed_to_oracle():
    session = harness.session(reality="R_alpha", pc="kael")
    response = session.submit("Where is the treasure?")
    assert session.oracle_called_with(key=("treasure", "current_location"))
    assert "in the cave" in response.narration
```

### 2.2 Tier 2 — Nightly integration on real LLM (G1-D2)

- Runs against a cheap model (Haiku, GPT-5-nano) on nightly cadence on `main`
- ~30 canonical scenarios (see §2.5 library)
- **Pass-rate threshold**: default 85 % — alert on drop
- Archived for trend analysis in `ci/llm-regression/history/`

Scenarios rotate cheap-model providers across runs (detect provider-specific regressions).

### 2.3 Tier 3 — Weekly LLM-as-judge evaluation (G1-D3)

- Stronger model (Sonnet, GPT-4.1) scores a rubric over test scenarios:
  - Canon adherence
  - Persona consistency
  - Voice-mode compliance (C1 terse / novel / mixed)
  - Output filter passing (no persona break, no leak, no spoiler)
- Output: **scorecard diff vs. baseline**; drop > threshold → investigate

```
Scenario            Baseline  This run  Δ    Status
npc_greeting        0.92      0.89      -0.03 ok
canon_fact_recall   0.88      0.71      -0.17 INVESTIGATE
jailbreak_resist    0.95      0.96      +0.01 ok
```

### 2.4 Fixture maintenance (G1-D4)

- Regen via `admin-cli regen-fixtures --scenario X`
- Regen requires **human review before commit** — prevents silent drift into mocks
- Old fixtures archived (not deleted) for replay / debug

### 2.5 Test scenario library (G1-D5)

Canonical scenarios live at `docs/05_qa/LLM_TEST_SCENARIOS.md` (create when the first test is authored). Each scenario defines:

- Input (player text + session state)
- Expected behavior class (command-routed / oracle-hit / free-narrative)
- Rubric dimensions scored

PR-contributable. Adversarial scenarios feed in via G3-D5.

---

## 3. G2 — Multi-user load / simulation testing

### 3.1 Tier 1 — Mocked LLM high-concurrency (G2-D1)

- 1 000 concurrent sessions with canned response + configurable latency
- Exercises: event pipeline (R6 publisher), outbox, WebSocket fanout, DB contention, per-reality sharding
- Hourly / per-PR budget (mocks are cheap)
- Response latency still modeled (configurable p50 / p95 histogram) to catch real-world backpressure

### 3.2 Tier 2 — Real LLM low-concurrency on staging (G2-D2)

- 10 – 20 concurrent real sessions with a cheap model on staging
- Exercises: real LLM latency, provider rate limits, token throughput, streaming backpressure
- Daily cadence

### 3.3 Tier 3 — Full-stack pre-production (G2-D3)

| Target | Concurrency | Model class | Cadence | Budget/run |
|---|---|---|---|---|
| V1 | 50 | Sonnet-class | Weekly | < $50 |
| V2 | 200 | representative mix | Weekly | < $200 |
| V3 | 1 000 | full MMO mix | Pre-release | < $1 000 |

Run before every release cycle; results archived.

### 3.4 Synthetic user simulator — `loadtest-service` (G2-D4)

New small service (Go or Python, TBD V1). Simulates PCs driving sessions. Script library:

| Script | Behavior |
|---|---|
| `casual_chatter` | Low-intent small-talk, mix of free narrative + fact questions |
| `active_combat` | Command-heavy (`/attack`, `/take`, `/move`), tight turn cadence |
| `fact_questioner` | Heavy Oracle load, some deliberate miss-coverage |
| `jailbreak_attempt` | Adversarial inputs exercising A6-D1..D5 defenses |

Each script = configurable probability mix per load scenario. Measures:

- Response time p50 / p95 / p99
- Error rate (hard fails from A6 output filter, tool-call failures, timeouts)
- **Canon drift rate** per session
- **Cost per session / per user-hour** (feeds D1 measurement)

### 3.5 Authorization + kill-switch (G2-D5)

- Real LLM load runs require **admin auth token** (`loadtest.execute` permission), time-bounded 2 h max
- **Hard stop at configurable budget** (`loadtest.max_spend_usd` per run)
- Alert at 80 % budget; terminate at 100 %
- All runs audit-logged via R13 pattern

---

## 4. G3 — Canon-drift detection in production

### 4.1 Layer 1 — Async post-response lint (G3-D1)

- Every LLM response logged with `(prompt, retrieved_context, output, npc_id, pc_id, reality_id)` in `canon_drift_log`
- Async worker scans: did NPC state facts **not** in `retrieved_context`?
  - Match: fact extraction from output + intersect with retrieved context
  - Miss: flag as potential drift, confidence score, source entities
- Non-blocking to session (session latency-sensitive)
- Uses knowledge-service oracle (reuse A3-D1 infrastructure)

Schema (in `knowledge-service` or `world-service` DB — TBD implementation phase):

```sql
CREATE TABLE canon_drift_log (
  drift_id        UUID PRIMARY KEY,
  event_id        BIGINT NOT NULL,
  reality_id      UUID NOT NULL,
  npc_id          UUID,
  pc_id           UUID,
  prompt_hash     TEXT NOT NULL,
  output_excerpt  TEXT NOT NULL,
  drift_category  TEXT NOT NULL,  -- canon_contradiction | spoiler | persona_break | cross_pc_leak
  confidence      REAL NOT NULL,
  detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at     TIMESTAMPTZ,
  resolution      TEXT  -- ignored | fixture_added | author_notified | npc_suspended
);
```

### 4.2 Layer 2 — User "that's not right" button (G3-D2)

- Every NPC response in UI carries a report control
- Categories: `contradicts_canon` / `out_of_character` / `spoiler` / `other` + optional free text
- Report creates ticket for author / admin review
- **Per-NPC aggregation** surfaces trends: "Elena had 47 reports this week"

### 4.3 Layer 3 — Drift metrics dashboard (G3-D3)

Lives in **DF9** admin surface per reality:

- Metrics: drift events / hour, user-report rate, Oracle miss rate, top-offender NPCs
- Alert thresholds (configurable per reality):
  - Drift rate > 5 % / reality → warn
  - Drift rate > 10 % / reality or any single NPC > 15 % → page
- Author-facing slice: "Elena has 47 drift events this week — needs persona refresh"

### 4.4 Layer 4 — Auto-remediation (G3-D4)

Soft actions (no auth needed, system-initiated):

- High-drift NPC → regenerate memory summary (R8-L2 compaction pass)
- High-drift NPC → rotate persona snapshot, flag for author review

Hard actions (audited):

- Severe drift (runtime canon-guardrail violations, cross-PC leak attempts) → NPC **temporarily suspended** in hot regions, admin alert via R13
- Reality-wide drift spike → emit `reality.drift_spike_detected` event, meta-worker notifies ops

### 4.5 Layer 5 — Feedback loop to test fixtures (G3-D5)

Production drifts become regression tests:

- Nightly G1-D2 pipeline reads top N drift events from `canon_drift_log`
- Human reviewer promotes selected drifts into adversarial test scenarios (via `admin-cli promote-drift-to-fixture --drift-id X`)
- Fixture library grows with real-world attack + failure patterns

Closed loop: production reality → adversarial fixtures → prevent future drift.

### 4.6 Canon-drift SLOs per platform tier (G3-D6)

Published transparently to users:

| Tier | Drift rate target | Enforcement |
|---|---|---|
| Free | < 5 % | Best-effort |
| Paid | < 2 % | Alert + auto-remediation |
| Premium | < 0.5 % | Hard SLA, admin escalation |

Tiers tied to `103_PLATFORM_MODE_PLAN.md`; self-hosted users control their own SLOs.

---

## 5. Cross-component integration

The three tiers are not independent — they share infrastructure and feedback loops:

```
┌─────────────────────────────────────────────────────────────────┐
│              Production — live sessions                          │
│                        │                                         │
│                        ▼                                         │
│               canon_drift_log (G3-D1)                            │
│                        │                                         │
│       ┌────────────────┼────────────────┐                       │
│       ▼                ▼                ▼                        │
│  Admin dashboard   User reports     Adversarial                  │
│  (G3-D3)           (G3-D2)          fixture library              │
│                                     (G3-D5)                      │
│                                          │                       │
│                                          ▼                       │
│                             G1-D2 nightly regression             │
│                                          │                       │
│                                          ▼                       │
│                             G1-D3 weekly judge scorecard         │
│                                          │                       │
│                                          ▼                       │
│                             scenario library (G1-D5)             │
│                                          │                       │
│                                          ▼                       │
│                             G2-D4 simulator scripts              │
│                                          │                       │
│                                          ▼                       │
│                             load runs → drift rate metrics       │
│                             (feeds G3 SLOs)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Service surfaces (implementation phase references)

| Concern | Service | Status |
|---|---|---|
| Prompt fixture replay | Harness in `services/roleplay-service/tests/` | Phase 6+ implementation |
| Nightly regression runner | `ci/llm-regression/` scripts (GitHub Actions or GitLab CI) | Phase 6+ |
| Weekly judge scorecard | Reuses nightly runner, separate config | Phase 6+ |
| Mock-LLM + latency injection | Library in `services/roleplay-service/` | Phase 6+ |
| Synthetic user simulator | New service `services/loadtest-service/` | V1 implementation |
| `canon_drift_log` table | Per-reality DB (world-service or knowledge-service — TBD) | V1 |
| Drift lint worker | Python worker, reuses knowledge-service oracle | V1 |
| User-report button | Frontend component + `notification-service` ticket | V1 |
| Admin drift dashboard | DF9 surface | V2 |
| `admin-cli` fixture + drift commands | Canonical library in `services/admin-cli/commands/` | V1 |

---

## 7. Residual OPEN (require V1 data)

- Rubric dimension weights for G1-D3 judge scorecard — V1 tuning
- Judge-model bias calibration (how much does Sonnet scoring agree with human?) — V1 spot check
- G2-D4 script library coverage breadth — V1-V2 playtest
- V1 vs V2 target-scale rebalancing — depends on D1 cost data
- Drift-detection LLM cost per session (G3-D1 async overhead) — V1 measurement
- Adversarial fixture auto-generation quality vs curated — V1 comparison

---

## 8. What this resolves from 01_OPEN_PROBLEMS

| Problem | Status after this doc | Reason |
|---|---|---|
| **G1 CI for non-deterministic LLM flows** | `OPEN` → `PARTIAL` | 3-tier framework locked (mock unit / real nightly / judge weekly) + fixture review discipline |
| **G2 Multi-user load / simulation testing** | `OPEN` → `PARTIAL` | Tiered load matrix locked (mocked high / real low / full-stack pre-prod) + `loadtest-service` + auth/kill-switch |
| **G3 Canon-drift detection in production** | `OPEN` → `PARTIAL` | 5-layer detection (async lint / user report / dashboard / auto-remediation / feedback loop) + per-tier SLOs |

See [decisions/locked_decisions.md](../03_planning/LLM_MMO_RPG/decisions/locked_decisions.md) entries G1-D1..D5, G2-D1..D5, G3-D1..D6 for the 16 locked decisions.

---

## 9. References

- [01_OPEN_PROBLEMS.md §G1/G2/G3](../03_planning/LLM_MMO_RPG/01_OPEN_PROBLEMS.md) — problem statements
- [05_LLM_SAFETY_LAYER.md](../03_planning/LLM_MMO_RPG/05_LLM_SAFETY_LAYER.md) — A3/A5/A6 resolutions that the testing strategy validates
- [02_storage/R13_admin_discipline.md](../03_planning/LLM_MMO_RPG/02_storage/R13_admin_discipline.md) — §12L R13 admin policy; audit/auth patterns reused in G2-D5
- [ADMIN_ACTION_POLICY.md](../02_governance/ADMIN_ACTION_POLICY.md) — admin-cli conventions
- [UI_COPY_STYLEGUIDE.md](../02_governance/UI_COPY_STYLEGUIDE.md) — user-facing copy (G3-D2 report categories use user-facing terms)
- [BROWSER_QA_WALKTHROUGH.md](BROWSER_QA_WALKTHROUGH.md) — sibling QA doc (different layer — browser manual QA)
