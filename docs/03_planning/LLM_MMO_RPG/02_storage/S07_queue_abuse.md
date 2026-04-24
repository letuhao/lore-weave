<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S07_queue_abuse.md
byte_range: 255983-262900
sha256: e70b48edb6bfcd6c86af4c6b6c6e1601413575644c5e463ff3a9378ed8c14abe
generated_by: scripts/chunk_doc.py
-->

## 12W. Queue Abuse Prevention — S7 Resolution (2026-04-24)

**Origin:** Security Review S7. §12R.1.2 H3 queue UX (introduced for popular NPC) had per-NPC depth cap but no per-user controls. Closes queue flood DOS vector + griefing slot-blocking patterns.

### 12W.1 Framing

H3 queue existed because R7-L6 locks NPC to 1 session at a time + H3 session caps at 6 PCs. Popular NPC → queue forms. Queue design at §12R.1.2 included 20-depth-per-NPC + 24h expiry but not:
- Per-user queue depth cap
- Abandonment tracking
- Graduated anti-abuse

**Attack surface:**
- Bot joins 100 NPC queues, abandons all → blocks legitimate users
- Griefer takes slot just to deny others
- Resource exhaustion via mass queue creation

**Legitimate behavior to preserve:**
- Player queues 3-5 NPCs, accepts first to open
- Player AFK misses notification
- Player IRL-busy, doesn't return

### 12W.2 Layer 1 — Per-user queue depth cap

```
queue.user.max_simultaneous = 5
```

Exceeded → reject with explanatory message. Realistic play: 3-5 concurrent queues typical; cap generous.

### 12W.3 Layer 2 — Two-stage expiration

Existing 24h max retained, plus notification response window:

1. Slot opens → user notified via standard platform channel
2. **10-minute response window** to accept or decline
3. No response → entry auto-expires (counts as abandoned per L3), slot goes to next
4. 24h absolute max regardless

```
queue.notification_response_window_minutes = 10
queue.entry_max_age_hours = 24
```

### 12W.4 Layer 3 — Acceptance rate tracking

```sql
CREATE TABLE user_queue_metrics (
  user_id              UUID PRIMARY KEY,
  total_queues_joined  INT NOT NULL DEFAULT 0,
  total_accepted       INT NOT NULL DEFAULT 0,
  total_abandoned      INT NOT NULL DEFAULT 0,      -- expired after notification
  total_declined       INT NOT NULL DEFAULT 0,      -- explicit opt-out (OK, not abuse)
  last_abandoned_at    TIMESTAMPTZ,
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Declined ≠ abandoned.** Explicit opt-out is acceptable behavior. Only silent expiration counts.

Computed metric: `acceptance_rate = accepted / (accepted + abandoned)` over rolling window.

Queue table extensions capture state transitions:

```sql
ALTER TABLE npc_session_queue
  ADD COLUMN notified_at   TIMESTAMPTZ,
  ADD COLUMN accepted_at   TIMESTAMPTZ,
  ADD COLUMN declined_at   TIMESTAMPTZ,
  ADD COLUMN abandoned_at  TIMESTAMPTZ;     -- computed: expired after notified_at without response
```

### 12W.5 Layer 4 — Priority decay (V1+30d)

Based on L3 data. User with acceptance rate < 30% over last 30 attempts gets gentle position penalty:

```
effective_queue_order = natural_fifo_order + penalty_factor
  where penalty_factor > 0 if acceptance_rate < threshold
```

Legitimate users with higher acceptance rates effectively jump ahead. Abuser still enters queue but ranks lower.

**Reversible:** improve acceptance rate → decay reverses. Not a ban.

Config:
```
queue.priority_decay.enabled = true                    # V1+30d
queue.priority_decay.threshold_acceptance_rate = 0.3
queue.priority_decay.evaluation_window = 30            # last N attempts
queue.priority_decay.penalty_factor = 5                # added to queue_order
```

### 12W.6 Layer 5 — Abandonment cool-down

Severe pattern → hard block (short cooldown):

```
If user abandons ≥ 10 queues in rolling 24h window:
  - Queue-join rejected for 1 hour
  - Notification: "Too many abandoned queues. Try again in 1 hour."
  - Counter resets after cool-down
```

10 abandoned/24h is well beyond any legitimate pattern. Cool-down is short to avoid over-punishing borderline cases.

Config:
```
queue.abandonment.threshold_per_24h = 10
queue.abandonment.cooldown_minutes = 60
```

### 12W.7 Layer 6 — Reality-level queue override (schema V1, DF4 activates)

Some realities may prefer no queue at all ("intimate RP realities where NPCs are always available to current party") or custom depth:

```sql
ALTER TABLE reality_registry
  ADD COLUMN queue_policy TEXT NOT NULL DEFAULT 'default',
    -- 'default' | 'disabled' | 'custom'
  ADD COLUMN queue_custom_config JSONB;
```

V1: schema reserved, all realities use `default`. DF4 World Rules activates custom policies when DF4 lands.

### 12W.8 V1 / V2+ split

- **V1 launch:**
  - L1 per-user queue depth cap (5)
  - L2 enhanced response window (10 min)
  - L3 metrics tracking
  - L5 abandonment cool-down (10/24h → 1h ban)
- **V1 + 30 days:**
  - L4 priority decay (requires L3 data)
- **V2+:**
  - Reputation/trust system
  - ML-based abuse pattern detection
  - L6 DF4 activation

### 12W.9 Interactions

| Locked item | Interaction |
|---|---|
| §12R.1.2 queue base design | S7 extends — per-user cap + metrics + graduated abuse response |
| H3 session caps (6 PCs/4 NPCs) | Queue exists BECAUSE of session caps; abuse undermines caps |
| S6 rate limit | Joining queue doesn't trigger LLM call — separate vector but similar pattern |
| S1 reality creation rate limit | Shared Redis rate-limit infrastructure |
| S5 admin commands | Admin manual queue-clear = Griefing tier; user notified per S5 |
| DF4 World Rules | L6 activation when DF4 lands |

### 12W.10 Config consolidated

```
queue.user.max_simultaneous = 5
queue.notification_response_window_minutes = 10
queue.entry_max_age_hours = 24                          # existing from §12R.1

queue.priority_decay.enabled = true                      # V1+30d
queue.priority_decay.threshold_acceptance_rate = 0.3
queue.priority_decay.evaluation_window = 30
queue.priority_decay.penalty_factor = 5

queue.abandonment.threshold_per_24h = 10
queue.abandonment.cooldown_minutes = 60
```

### 12W.11 Accepted trade-offs

| Cost | Justification |
|---|---|
| Max 5 queues may frustrate super-power-users | 5 generous; 99% of legitimate play fits |
| 10-min response window may miss AFK users | 24h absolute max still applies; can rejoin |
| Priority decay could penalize busy legitimate users | Reversible, gentle; hard block only at severe L5 threshold |
| Extra schema columns on queue table | Small — state transitions useful for debug anyway |
| Reality queue policy schema V1 | Zero cost; avoids later migration for DF4 |

### 12W.12 What this resolves

- ✅ **Queue flood attack** — L1 per-user cap + L5 severe-pattern block
- ✅ **Slot-blocking griefers** — L2 10-min window + L4 priority decay
- ✅ **Legitimate play preserved** — all measures soft/graduated; hard block rare
- ✅ **Acceptance tracking** — L3 data enables refinement
- ✅ **DF4 readiness** — L6 schema future-proofed

**Residuals (V2+):**
- Reputation/trust system (L4 is baseline)
- ML abuse pattern detection
- Cross-reality queue priority

