<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S06_llm_cost_controls.md
byte_range: 247185-255983
sha256: 69c4673f7ec05f7f95b4efed62fdce11b96122f3200e7e25b5e4d0e91ee55ac8
generated_by: scripts/chunk_doc.py
-->

## 12V. LLM Cost Controls — S6 Resolution (2026-04-24)

**Origin:** Security Review S6 — no production per-user rate limit on LLM turns. Compromised paid-tier account could drain platform LLM budget. Closes economic DOS vector left by D2-D1 tier model.

### 12V.1 Threat model

Attack scenarios:
1. Compromised paid account scripts automated turns → drains budget
2. Legitimate heavy user accidentally exceeds economic viability
3. Prompt injection triggers expensive retry loops
4. User targets premium-model path (5-20× standard cost)
5. Spam patterns (whisper spam, continuous NPC questions) burn budget

**Economic model at risk:** D2-D3 unit economics = `tier_price ≥ 1.5 × (cost_per_hour × avg_hours/month)`. Uncapped cost breaks ratio.

### 12V.2 Layer 1 — Per-user turn rate limit

Token bucket per user in Redis (cheap, fast). Tier-aware:

| Tier | Limit | Rationale |
|---|---|---|
| Free (BYOK) | Unlimited platform-side | User pays own LLM; platform indifferent |
| Paid | 120 turns/hour | Realistic play: 1 turn/20-30s = 120-180/h; 120 catches automation |
| Premium | 300 turns/hour | Heavy RP ceiling |

Burst capacity: 20% over limit briefly (handles short high-engagement moments).

Exceeded → 429 Too Many Requests with `Retry-After`.

Config:
```
rate_limit.turns_per_hour.free = null           # BYOK, unlimited
rate_limit.turns_per_hour.paid = 120
rate_limit.turns_per_hour.premium = 300
rate_limit.burst_capacity_multiplier = 1.2
```

Implementation: per-user Redis bucket, atomic decrement on turn submit, refill at `3600/limit` second interval.

### 12V.3 Layer 2 — Per-session cost cap

Each session has budget. Warn at 80%, hard-cap at 100%:

```sql
CREATE TABLE session_cost_tracking (
  session_id      UUID PRIMARY KEY,
  reality_id      UUID NOT NULL,
  user_id         UUID NOT NULL,
  cap_usd         NUMERIC(10,6) NOT NULL,
  spent_usd       NUMERIC(10,6) NOT NULL DEFAULT 0,
  warned_at       TIMESTAMPTZ,
  capped_at       TIMESTAMPTZ,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON session_cost_tracking (user_id, started_at DESC);
```

Cap hit → "This session has reached its budget. Start a new session to continue."

Admin override via S5 Griefing-tier action (mandatory reason + user notification).

Config:
```
session_cost_cap_usd.paid = 5.00
session_cost_cap_usd.premium = 20.00
session_cost_cap_warn_pct = 80
```

Prevents single user draining budget via marathon session.

### 12V.4 Layer 3 — Per-user daily cost budget (V1+30d)

Aggregate across all sessions per user:

```sql
CREATE TABLE user_daily_cost (
  user_id       UUID NOT NULL,
  date          DATE NOT NULL,
  spent_usd     NUMERIC(10,6) NOT NULL DEFAULT 0,
  cap_usd       NUMERIC(10,6) NOT NULL,
  capped_at     TIMESTAMPTZ,
  PRIMARY KEY (user_id, date)
);
```

Aligned with D2-D3 margin. Exceeded → user choices:
- Wait until next day
- Upgrade tier
- Admin override (S5 Griefing)

Config:
```
daily_cost_cap_usd.paid = 1.50               # initial; refined by D1 data
daily_cost_cap_usd.premium = 5.00
```

### 12V.5 Layer 4 — Real-time cost observability

Metrics per user + platform:

```
lw_user_llm_turns_per_hour{user_id, tier}                  gauge
lw_user_llm_cost_per_session{user_id, session_id}          gauge
lw_user_llm_cost_per_day{user_id, date}                     gauge
lw_user_llm_cost_per_hour_current{user_id}                 gauge

lw_platform_llm_cost_per_hour_total                        gauge
lw_platform_llm_daily_budget_remaining_pct                 gauge
```

**Alert thresholds:**
- User turn rate > 2× realistic baseline → investigate
- User daily cost > 1.5× expected → investigate
- Platform daily budget < 20% remaining → **PAGE SRE**
- Platform daily budget < 10% → engage L5 circuit breaker

### 12V.6 Layer 5 — Circuit breaker (V1+30d)

Two-level defense:

**User-level:**
```
If user's cost/hour > 3× their 7-day baseline:
  - Throttle to 50% of tier limit for 24h
  - In-app notification: "Activity higher than usual. Rate limited 24h."
  - Auto-release after 24h of normal activity
```

**Platform-level:**
```
If platform daily budget < 10% remaining:
  - Proportional throttle all paid users to 50%
  - SRE PAGE
  - Optional emergency kill-switch (G2-D5 pattern, production-scoped)
  - Free/BYOK users unaffected
```

### 12V.7 Layer 6 — Cost ledger

Every LLM call logged:

```sql
CREATE TABLE user_cost_ledger (
  entry_id         BIGSERIAL PRIMARY KEY,
  user_id          UUID NOT NULL,
  session_id       UUID,
  reality_id       UUID,
  event_id         BIGINT,                       -- which event triggered
  llm_provider     TEXT NOT NULL,                -- 'anthropic' | 'openai' | 'local'
  model_name       TEXT NOT NULL,
  input_tokens     INT NOT NULL,
  output_tokens    INT NOT NULL,
  cost_usd         NUMERIC(10,6) NOT NULL,
  is_platform_paid BOOLEAN NOT NULL,             -- true if platform paid, false if BYOK
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON user_cost_ledger (user_id, created_at DESC);
CREATE INDEX ON user_cost_ledger (session_id) WHERE is_platform_paid = true;
CREATE INDEX ON user_cost_ledger (created_at) WHERE is_platform_paid = true;
```

Powers L2/L3 aggregation + observability + billing reconciliation + D1 feedback loop.

**Retention:** **7 years** (revised by S8 / §12X.4 — billing/tax legal obligation); rows pseudonymize at 2y mark (replace `user_id` with one-way hash, retain aggregates). Original 2y minimum superseded.

### 12V.8 Layer 7 — Model selection governance

Premium models (Claude Opus, GPT-4) cost 5-20× standard. Tier-gated:

| Tier | Allowed models |
|---|---|
| Free (BYOK) | Any — user's own keys, user's own risk |
| Paid | Standard only (Sonnet, GPT-4o-mini, equivalents) |
| Premium | Standard + premium, per-turn cost shown in UI |
| Admin override | Any, via S5 Griefing-tier action for specific ops |

Enforcement: LLM call API validates `model_name` against user's tier allowlist. Reject unauthorized with 403.

### 12V.9 Interactions

| Locked item | Interaction |
|---|---|
| **D1 cost measurement** | L6 ledger data feeds D1; L2/L3 exact values tuned by D1 output |
| **D2 tier viability** | L1-L3 enforce D2-D3 margin ratio in real-time |
| **D2-D4 tier features** | L7 model gating maps to tier feature differentiation |
| **G2-D5 loadtest kill-switch** | L5 platform circuit breaker reuses same pattern, production-scoped |
| **S1 reality creation rate limit** | Shares Redis rate-limit infrastructure |
| **S4 meta_write_audit** | Cost override admin actions captured via MetaWrite |
| **S5 admin commands** | "cost_override" = Griefing tier; user notified per S5-D4 |
| **R13 admin audit** | Cost cap overrides audited at Griefing tier level |

### 12V.10 V1 / V2+ split

- **V1 launch (mandatory):**
  - L1 turn rate limit (Redis token bucket)
  - L2 session cost cap
  - L4 basic observability (metrics + alerts)
  - L6 cost ledger
  - L7 model selection gating
- **V1 + 30 days:**
  - L3 daily cost budget
  - L5 circuit breaker (user + platform)
  - Baselines refined from V1 data
- **V2+:**
  - ML-based anomaly detection (replaces threshold baselines)
  - Predictive cost modeling (forecast per-user cost)
  - Dynamic tier suggestions ("you play a lot; upgrade?")

### 12V.11 Accepted trade-offs

| Cost | Justification |
|---|---|
| Rate limit may frustrate power users | 120/h = 2× realistic play; rare to hit legitimately; premium exists |
| Session cap breaks immersion | $5 = ~2-3 hours play; new session continues story; caps are upper bounds |
| Daily budget friction for heavy users | Tier upgrade provides headroom; aligns with economic reality |
| Token-bucket Redis roundtrip | ~1ms per turn; negligible vs LLM 3-8s |
| Ledger write per LLM call | ~15 writes/sec platform-wide; Postgres handles easily |
| Model gating restricts premium experimentation | Premium tier + admin override for legit cases |

### 12V.12 What this resolves

- ✅ **Economic DOS vector**: L1/L2/L3 bound per-user cost; L5 platform-wide breaker
- ✅ **D2-D3 margin enforcement**: rate limits + budgets enforce margin in real-time
- ✅ **Anomaly detection**: L4 + L5 catch abuse patterns
- ✅ **Cost attribution**: L6 ledger enables billing + D1 feedback
- ✅ **Premium-model abuse**: L7 tier gating prevents 5-20× cost path abuse

**Residuals (V2+):**
- ML anomaly detection (V1 uses thresholds; sufficient for catching gross abuse)
- Predictive cost modeling (V1 reactive caps)
- Dynamic tier suggestions (V1 manual upgrade)

