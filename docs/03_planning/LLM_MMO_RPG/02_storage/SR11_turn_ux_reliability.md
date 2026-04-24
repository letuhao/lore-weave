<!-- CHUNK-META
chunk: SR11_turn_ux_reliability.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR10.
-->

## 12AN. Turn-Based Game Reliability UX — SR11 Resolution (2026-04-24)

**Origin:** SRE Review SR11 — the first SR concern at the product+infra boundary. SR1-SR10 made the platform reliable; SR11 makes failures **coherent to the user**. A turn takes 60-120s (SR1-D2 LLM SLO); during that window, LLMs time out, WS connections drop, pods scale down (SR6-D10), chaos drills fire (SR7), degraded modes activate (SR6-D5). Without disciplined UX, users see spinners-forever, duplicate messages, mysterious disconnects, or worse — they re-send a turn that already charged against S6 budget. SR11 makes every infra failure state map to a specific user-visible state with a clear affordance.

### 12AN.1 Problems closed

1. Turn state invisible to user — "is the AI thinking or did my message not send?"
2. Retry ambiguity — user re-sends queued message and double-charges S6 budget
3. Presence lies — other players shown as "idle" when they've actually disconnected
4. Disconnect policy undefined — does their turn freeze, continue, or cancel?
5. Optimistic UX rollback undesigned — client shows X, server says Y, UI desyncs
6. Degraded-mode UX inconsistent — "limited" mode looks like a bug
7. Session fairness unspecified — premium can monopolize turn processor
8. Abandoned turns leak state — user never returns, session processor stuck
9. Error codes leak to users — "HTTP 504: upstream timeout" instead of actionable message
10. Chaos drill user-visibility — should users know? How?
11. Multi-player session UX — when one user's stuck, others wait or proceed?
12. Cross-device continuity — mobile + desktop same account both in session

### 12AN.2 Layer 1 — Turn State Machine (8 states)

Per-user-per-turn state machine at `contracts/turn/state_machine.go`:

```
               [user types]
                    ↓
   ┌───────── drafting ──────────┐
   │                              │
   │  [user submit]        [user cancel]
   │        ↓                     ↓
   │    submitted ──→ queued ──→ llm_processing ──→ streaming ──→ complete
   │        │           │              │                │
   │        │           │              │                └→ failed_retryable ─┐
   │        └──→ failed_retryable ←────┤                                     │
   │                   │               └→ failed_terminal                   │
   │                   ↓                                                     │
   │              [retry → submitted]                                        │
   │                                                                         │
   └───────────── (after timeout / user abandon) ────────────→ failed_terminal
```

**State semantics + user-visible labels (i18n-keyed):**

| State | Meaning | User-visible UX | Retry safety |
|---|---|---|---|
| `drafting` | User typing; not yet submitted | Input field; send button | N/A (no server state) |
| `submitted` | Client sent; awaiting server ack | Grayed input; "Sending..." | ⚠️ Retry creates duplicate; dedup by idempotency key |
| `queued` | Server accepted; not yet processing (R7 session queue) | "In line, 3 turns ahead" with position | ✅ Retry safe — idempotency key rejects dupe |
| `llm_processing` | Provider call in-flight | "AI is thinking..." + elapsed timer | ❌ **Retry NOT safe** — double-charges S6 budget; UX disables resend |
| `streaming` | Response streaming back via WS | Text streaming in real-time | ❌ Retry invalid; partial response already rendered |
| `complete` | Turn done; state updated | Normal rendered message | N/A |
| `failed_retryable` | Transient error (network blip, provider 503, circuit breaker open) | Error banner: "Couldn't send — try again" + retry button | ✅ User-initiated retry safe |
| `failed_terminal` | Budget exhausted / reality archived mid-turn / abandoned timeout | Error banner: specific reason + non-retry affordance | ❌ Retry blocked; different action available (e.g., "Top up budget") |

**Transition audit:** every state change emits `turn.state_transition{turn_id, from, to, reason}` via outbox (I13); populates `turn_outcomes` table (§12AN.9).

**Idempotency:** `submitted` → `queued` transition keyed on client-generated UUID; duplicate submission returns existing turn_id without creating new. Prevents S6 double-charge from resend-storms during network blips.

### 12AN.3 Layer 2 — Per-User Turn Indicator UX

WebSocket message type `turn.status.update` (per §12AB.L7 versioned schema):

```yaml
turn.status.update:
  fields:
    turn_id: uuid
    state: TurnState
    position_in_queue: int?          # queued only
    elapsed_ms: int                   # since transition to current state
    expected_ms_remaining: int?       # estimate based on SR1-D2 SLO
    retry_safe: bool                  # derived from state
    cancel_available: bool            # true in drafting / submitted / queued
  authz: session_participant
```

Client renders contextually:
- `drafting` → no indicator
- `submitted` → subtle spinner next to send button
- `queued` → "In line, position X of Y" with countdown
- `llm_processing` → "AI is thinking..." + elapsed (1s / 5s / 15s / 30s... bucketed so counter doesn't spasm) + abort button (user-initiated `failed_terminal`; refunds S6 budget if pre-provider-call, otherwise not)
- `streaming` → text streams in; abort stops stream but charges full cost (can't un-ring the LLM)

**Latency budget (per SR1-D2 tier):**
- Paid: 60s SLO; indicator transitions "AI is thinking..." → "Taking longer than usual..." at 45s → "Very slow response" at 55s → `failed_retryable` at 60s
- Premium: 120s SLO; same pattern scaled 1.5×

**Cancel affordance:** only `drafting`, `submitted`, `queued` allow cancel. `llm_processing` allows **abort** (different verb) — explicit "cost was incurred" framing.

### 12AN.4 Layer 3 — Session-Wide Presence

New enum at `contracts/lifecycle/presence.go`:

```go
type PresenceState string

const (
    PresenceActive            PresenceState = "active"             // WS connected; recent activity
    PresenceIdle              PresenceState = "idle"               // WS connected; no input 60s+
    PresenceTyping            PresenceState = "typing"             // WS connected; drafting state
    PresenceWaitingAI         PresenceState = "waiting_ai"         // one of their turns in llm_processing/streaming
    PresenceDisconnectedBrief PresenceState = "disconnected_brief" // WS dropped < 5 min (expected reconnect)
    PresenceDisconnectedGhost PresenceState = "disconnected_ghost" // WS dropped 5-30 min (awaiting cleanup)
)
```

**NOT** a replacement for `GoneState` (§12Z — `active` / `severed` / `archived` / `dropped` / `user_erased`). GoneState = entity existence; PresenceState = session-scoped liveness. A GoneState=`active` PC can have PresenceState=`disconnected_ghost`.

**Propagation:**
- `session.presence.changed` event via outbox → WS push to other participants
- Debounced: same user's rapid Active ↔ Typing ↔ Active collapsed to 2s minimum interval
- Per-session presence snapshot queryable via `GET /v1/sessions/<id>/presence` (for initial render on session-enter)

**Schema extension to `session_participants` (per S2):**
```sql
ALTER TABLE session_participants
  ADD COLUMN presence_state        TEXT NOT NULL DEFAULT 'disconnected_brief',
  ADD COLUMN presence_changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN ws_connection_id      TEXT,                  -- nullable; matches S12 WSSession
  ADD COLUMN last_activity_at      TIMESTAMPTZ NOT NULL;
```

Per-WS-disconnect (S12 close codes): auto-transition to `disconnected_brief`; 5-min timer → `disconnected_ghost`; 30-min timer → `presence_cleanup` admin event + participant removed from session (S2 capability invalidated).

### 12AN.5 Layer 4 — Disconnect Handling (3-policy matrix)

When a user disconnects mid-turn, what happens to their in-flight turn?

| User's turn state at disconnect | Policy | Outcome |
|---|---|---|
| `drafting` | No server state — nothing to preserve; client draft may be locally cached per browser | Reconnect finds empty compose box (default) or restored draft (V1+30d nice-to-have) |
| `submitted` | Server-side idempotency key persists 30s; if reconnect within 30s, treat as continuation | If reconnect > 30s: `failed_retryable` with "your last message may not have sent" |
| `queued` | Server continues processing; turn_id persists indefinitely until state machine terminal | Reconnect → user sees current state (likely `streaming` or `complete` by reconnect time); backfill via `turn.status.update` event replay from S2 |
| `llm_processing` | Server continues; user's LLM budget already committed (S6) | Reconnect → user sees response if complete, or progress if still processing; budget charged regardless |
| `streaming` | Server completes stream; output buffered 60s for reconnect replay | Reconnect → buffer replayed; after 60s the stream is lost (terminal in transcript but user missed live render) |
| `complete` | Turn in transcript per normal | Reconnect → full transcript available |
| `failed_retryable` | Error surfaced; turn in audit but not in transcript | Reconnect → error banner re-shown with retry affordance |
| `failed_terminal` | Turn in transcript marked failed; compensating event emitted | Reconnect → user sees failure reason; no retry affordance |

**Multi-user session disconnect policy** (declared per-reality in DF4 World Rules when DF4 designed; V1 default):
- **Default `proceed-if-turn-complete`**: other players' turns complete even if the disconnected player's turn was in-flight; next free turn-slot advances without waiting
- **Opt-in `suspend-all`**: specific session mode where a disconnect pauses all participants until reconnect or ghost-cleanup (cooperative genres; party coordination)
- **Opt-in `replace-with-npc`**: after `disconnected_ghost` transition, their PC auto-converts to NPC per DF1 (forward-ref) so session flow isn't blocked

Per-session policy stored in `session_metadata.disconnect_policy` (nullable; inherits reality default).

### 12AN.6 Layer 5 — Optimistic UX Rules

Some user actions render provisionally before server confirms. Rules for when this is safe:

| Action | Optimistic? | Rollback mechanism |
|---|---|---|
| Submit turn | Yes — message appears in transcript with "sending" indicator | State transitions `submitted` → `failed_retryable`; message visually marked error + retry button |
| Cancel drafting | Yes — instant | N/A |
| Cancel `queued` turn | Yes — position vanishes | Server confirms within 500ms; rollback if server already promoted to `llm_processing` ("too late to cancel — AI already started") |
| Edit PC sheet | No — wait for server (spans tabs; too risky) | N/A |
| Change reality settings (DF4) | No | N/A |
| Presence update (typing) | Yes — instantly shown to others via WS push | Server ignores if participant capability invalid; visually clears |
| Scroll / UI interactions | Yes (client-only) | N/A |

**Divergence protocol:** when optimistic render disagrees with server response:
1. **Conservative rollback**: client state reverts to server-truth; user sees brief flicker
2. **Notification**: non-modal toast "Your last action couldn't complete" (NOT modal — modals hijack; toast is ambient)
3. **Audit**: client logs divergence to structured log (pseudonymized per S8); surfaces in SR9 weekly alert review if divergence rate exceeds baseline

**Principle:** optimistic UX is for responsiveness; server is always the source of truth. Never use optimistic state for decisions that affect other users (whispers, PvP actions, canonization proposals).

### 12AN.7 Layer 6 — Degraded-Mode UX

For each SR6-D5 service mode, user sees a specific UX:

| Service Mode | User-visible affordance | Tone |
|---|---|---|
| `full` | Normal UX | None |
| `limited` | Yellow banner at top: "Running on backup systems — some features slower or unavailable" + link to status page (V2+) | Informational, not alarming |
| `essentials` | Orange banner: "Reduced functionality — reading and existing sessions only; new turns paused" | Cautious |
| `read_only` | Red banner (specific to affected reality): "This world is temporarily read-only" + admin contact | Urgent |
| `offline` | Full-screen modal: "Service temporarily unavailable" + ETA (if known) + status-page link | Blocking |

**Degraded-mode actions per state:**
- `full` / `limited`: turn submission enabled (may use fallback LLM in `limited`)
- `essentials`: new turns **rejected client-side** with clear error; reading/scrolling/presence continues
- `read_only`: all write actions disabled; state visible; admin commands still work for ops
- `offline`: client retries reconnect with exponential backoff + jitter (per SR6-D4); shows ETA if header provides

**Client degraded-mode signal:** `X-LW-Mode` response header (per SR6-D5) + WS control channel push when mode changes. Client subscribes on session-connect; mode change triggers UI update + toast.

**Reality-scoped vs platform-wide:** user in reality A may see `read_only` while reality B is `full`. UX differentiates — banner is reality-scoped when applicable, platform-wide otherwise.

### 12AN.8 Layer 7 — Turn Fairness

Session turn-processor (R7) is single-writer; turn queue determines order. Naive FIFO without tier consideration = premium users pay more for no benefit.

**Per-tier queue model:**

1. Each session has **one primary turn queue** (FIFO)
2. **Tier-bump slots** — premium users can "skip to front" with budget cost (S6 integration)
3. **Cooldown on tier-bump** — same user max 1 bump per 60 seconds (prevents monopolization)
4. **Hard cap** — any single user max 30% of session turns over a 10-minute rolling window
5. **Fairness metric** — exposed as `lw_turn_fairness_gini{session_id}` (low cardinality) — Gini coefficient of turn distribution; alert if >0.6

**Queue position UX:**
- `queued`: "In line, position X of Y"
- Tier-bumped: "Priority: position 1 of Y (cost +$0.X per tier-bump)" with S6-D2 budget check
- Hard-capped: "Please wait — others want a turn too" + cooldown countdown

**Rationale:** prevents premium-user monopolization while respecting the paid tier benefit. 60s cooldown + 30% cap are tunable per reality (DF4).

### 12AN.9 Layer 8 — Abandoned-Turn Cleanup + `turn_outcomes` Audit

**Absolute timeout:** any turn in `submitted` / `queued` / `llm_processing` / `streaming` for > 30 minutes auto-transitions to `failed_terminal` with reason `abandoned_timeout`.

Reasons for hitting timeout:
- User disconnected + never reconnected within ghost-cleanup window
- LLM provider genuinely stuck (shouldn't happen post-SR6-D2 timeout but possible if bug)
- Session-processor bug (recovery path)
- Chaos drill lingering effect (SR7)

**`turn_outcomes` audit:**

```sql
CREATE TABLE turn_outcomes (
  turn_id               UUID PRIMARY KEY,
  session_id            UUID NOT NULL,
  user_ref_id           UUID NOT NULL,                   -- S8-D1 opaque
  pc_id                 UUID,                             -- nullable for chat-service turns
  initial_state         TEXT NOT NULL,                    -- drafting (for client turns) or submitted (for server reconstruction)
  terminal_state        TEXT NOT NULL,                    -- complete / failed_retryable / failed_terminal
  started_at            TIMESTAMPTZ NOT NULL,
  terminated_at         TIMESTAMPTZ NOT NULL,
  latency_ms            BIGINT,
  queue_wait_ms         BIGINT,                           -- submitted → queued → llm_processing
  llm_processing_ms     BIGINT,                           -- llm_processing → streaming
  streaming_ms          BIGINT,                           -- streaming → complete
  provider_used         TEXT,                             -- from SR6-D6 failover
  failover_count        INT DEFAULT 0,                    -- 0 = primary; 1+ = fell back
  error_code            TEXT,                             -- registered code (§12AN.10)
  user_visible_reason   TEXT,                             -- templated per error_code
  retry_count           INT DEFAULT 0,                    -- user-initiated retries that led to this terminal state
  cost_usd              NUMERIC(10,6),                    -- from S6-D6 user_cost_ledger
  turn_text_hash        TEXT,                             -- SHA-256 of turn input (for dedup audit); content in event log
  state_transitions     JSONB                             -- full trace for reconstruction
);

CREATE INDEX ON turn_outcomes (session_id, started_at DESC);
CREATE INDEX ON turn_outcomes (user_ref_id, started_at DESC);
CREATE INDEX ON turn_outcomes (terminal_state, started_at DESC) WHERE terminal_state != 'complete';
CREATE INDEX ON turn_outcomes (error_code, started_at DESC) WHERE error_code IS NOT NULL;
```

**Retention:** **1 year** (aligns `scaling_events` + `dependency_events`; high-volume operational data).
**PII classification:** `low` (opaque user_ref_id per S8; turn text in separate events per per-event encryption V2+).
**Write path:** `MetaWrite()` (I8); append-only with narrow-column completion allowlist.

**Derived metrics:**
- `lw_turn_completion_rate{tier}` — completed / total per user tier (SR1-D2 SLI)
- `lw_turn_failover_rate{provider_pair}` — SR6-D6 failover effectiveness
- `lw_turn_abandon_rate{session_type}` — abandoned / total per session type

### 12AN.10 Layer 9 — Error Message Discipline

Every user-visible error MUST be a registered error code → user-template mapping. No raw technical messages.

**Registry:** `contracts/errors/user_errors.yaml`:

```yaml
- code: TURN_SUBMISSION_TIMEOUT
  user_template: "We couldn't reach our servers. Check your connection and try again."
  technical_context: "Client-side timeout at /v1/turns POST; typically transient network."
  retry_safe: true
  escalation_path: null

- code: LLM_BUDGET_EXHAUSTED
  user_template: "You've reached your usage limit for this session. <link>Learn about top-up</link> or start a new session."
  technical_context: "S6-D2 per-session cap hit; S6-D1 daily budget may also apply."
  retry_safe: false
  escalation_path: "top_up"

- code: REALITY_READ_ONLY
  user_template: "This world is temporarily read-only. We're working on it — usually back within 15 minutes."
  technical_context: "SR6-D5 read_only mode active for reality."
  retry_safe: false
  escalation_path: "status_page"

- code: TURN_ABANDONED
  user_template: "Your turn timed out. You can start a new turn when you're ready."
  technical_context: "30-min abandoned-turn cleanup; §12AN.9."
  retry_safe: true
  escalation_path: null

- code: LLM_PROVIDER_UNAVAILABLE
  user_template: "The AI is having trouble right now. Please try again in a moment."
  technical_context: "All LLM providers in failover chain returned error or circuit-open."
  retry_safe: true
  escalation_path: null

- code: CANON_INJECTION_DETECTED
  user_template: "Your message couldn't be processed due to a safety check. If you believe this is a mistake, <link>contact support</link>."
  technical_context: "S9-D5 injection scan flagged; S13 canon-write scan may also apply; review quarterly."
  retry_safe: false
  escalation_path: "contact"

- code: SESSION_CAPACITY_FULL
  user_template: "This session is full right now. Try again in a minute, or <link>explore other worlds</link>."
  technical_context: "SR8-D4 per-reality session-processor saturation ceiling hit."
  retry_safe: true
  escalation_path: "browse_realities"
```

**CI enforcement (`scripts/error-code-lint.sh`):**
- Every `user_visible_reason` in `turn_outcomes` MUST match a registered code
- Every new user-facing error path in code MUST reference a registered code
- Error templates scanned for PII (per §12X.4 scrubber) — catches accidental leakage of user data in errors

**Translation:** templates stored per-locale (`contracts/errors/user_errors.<locale>.yaml`); MV5-primitive P1 locale used to select. English default.

**Technical context NEVER shown to user** — only in admin/debug UI + logs. Clean separation prevents accidental leakage of service names, SQL queries, provider names, etc.

### 12AN.11 Layer 10 — V1 Minimal Bar (12-state matrix)

**V1 launch gate:** these 12 specific user-visible states must render correctly in production prior to V1 launch.

Matrix = [turn state × service mode × connection state]:

| # | Scenario | Expected UX |
|---|---|---|
| 1 | Normal turn (full mode, connected) | Standard turn flow: drafting → AI thinking → response |
| 2 | Slow turn (full mode, LLM taking 45s+) | "Taking longer than usual..." indicator at 45s |
| 3 | Turn during `limited` mode (fallback LLM active) | Banner shown; turn proceeds with fallback; breadcrumb in SESSION_STATE only |
| 4 | Turn during `essentials` mode | Turn submission rejected client-side with registered error code + user-friendly message |
| 5 | Reality enters `read_only` mid-turn | User's current turn completes; future turn-submit shows REALITY_READ_ONLY error |
| 6 | WS disconnect during `queued` | Reconnect within 30s: see current state. Over 30s: status replay via WS-catchup |
| 7 | WS disconnect during `llm_processing` | Reconnect within 60s: response appears. Over 60s: in transcript, missed live stream |
| 8 | Turn hits S6 budget limit | LLM_BUDGET_EXHAUSTED error with top-up CTA |
| 9 | Presence — other user disconnected ghost | Their PC shown as "disconnected" with reconnect-hope countdown |
| 10 | Turn auto-abandoned at 30 min | TURN_ABANDONED error; state terminal |
| 11 | Injection detection triggers | CANON_INJECTION_DETECTED error (non-scary; no "you are being scanned" language) |
| 12 | Session capacity full (SR8-D4) | SESSION_CAPACITY_FULL error with browse-alternatives affordance |

**Test procedure:** each of the 12 scenarios has a chaos-drill (SR7-D3) + an E2E test in `services/roleplay-service/e2e/turn_ux/`. V1 launch gate CI (`v1-turn-ux-check.sh`) queries `chaos_drills` + E2E results for each scenario passing.

**V1+30d evolution:**
- Extend matrix with tier-bump fairness scenarios (SR11-D7)
- Mobile-specific UX review (cross-device session continuity)
- Accessibility review per CC-6-D1 WCAG 2.2 AA against all 12 states

### 12AN.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| I6 (session concurrency) | Turn state machine is per-session FIFO; queue ordering from R7 |
| I10 (prompt assembly) | Turn content goes through AssemblePrompt; failure paths map to registered error codes |
| I13 (outbox) | Turn state transitions emit `turn.state_transition` events via outbox |
| SR1-D2 | Turn latency SLIs derived from `turn_outcomes` latency_ms |
| SR2-D7 | Turn-outcome analysis may trigger incident if failure pattern emerges |
| SR3 | Turn runbook library ensures on-call knows how to investigate stuck turns |
| SR5-D3 | Canary rollout checks `lw_turn_completion_rate` per cohort |
| SR6-D5 | Degraded-mode UX maps to each of the 5 modes (L6) |
| SR6-D6 | Failover UX surfaces as `limited` mode + breadcrumb (L6) |
| SR6-D10 | Drain during scale-down: in-flight turns complete before replica terminates; new turns go to other replicas |
| SR7-D3 | Each V1 scenario (L10) has a corresponding chaos drill |
| SR9-D1 | Turn abandon rate >baseline → SEV2 alert |
| SR10-D4 | CVE in LLM provider triggers failover if P1 tier; user sees `limited` mode |
| S2 (session participants) | PresenceState extends session_participants schema |
| S6-D2 | Per-session budget cap hit = LLM_BUDGET_EXHAUSTED error code |
| S9 (prompt) | Injection detection → CANON_INJECTION_DETECTED user error |
| S12-D1 | WS ticket refresh during disconnect-reconnect handles Layer 4 continuity |
| S13 | Canonization in progress may queue turns; user sees queued indicator |
| C5 (multi-stream UI) | Partial overlap — presence/connection UX adds one differentiation dimension; remains PARTIAL pending full UI design |
| DF1 (daily life) | Forward-ref: disconnect-replace-with-NPC policy (L4) integrates with DF1 conversion |
| DF4 (world rules) | Forward-ref: disconnect policy per-reality override comes from DF4 |
| DF5 (session/group chat) | Forward-ref: SR11 establishes the patterns DF5 implements in detail |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `admin/session-unfreeze` Tier 2 · `admin/turn-abandon` Tier 3 · `admin/presence-reset` Tier 3 |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| 8-state turn machine adds complexity | Each state is a distinct user experience; collapsing them = retry ambiguity or spinner-forever |
| Presence system adds ~2× WS traffic | Debounced + coarse-grained; worth it for multi-user session UX |
| Disconnect policy matrix has 8 rows × 3 policies = 24 cases | Unavoidable complexity for correctness; V1 defaults are safe |
| Optimistic UX can flicker on rollback | Small UX cost for large responsiveness gain; divergence rate monitored |
| Error code registry adds i18n workflow overhead | Translation is mandatory for platform; registry makes it tractable |
| 12-scenario V1 gate adds testing time | Each scenario catches a distinct failure class; skip any = user-facing bug class in prod |
| turn_outcomes 1y retention | Aligns other 1y audit tables; operational + SR1 SLI data |
| 30-min abandoned-turn window is long | Handles user-coming-back-from-lunch case; shorter = false abandonments during normal play |

**What this resolves:**

- ✅ Turn state invisible — L1 state machine + L2 user indicator
- ✅ Retry ambiguity — L1 retry_safe field per state; L2 disables resend in unsafe states
- ✅ Presence lies — L3 PresenceState with auto-transitions + debounced propagation
- ✅ Disconnect policy undefined — L4 3-policy matrix with default proceed-if-turn-complete
- ✅ Optimistic UX rollback undesigned — L5 conservative rollback + divergence toast
- ✅ Degraded-mode UX inconsistent — L6 per-mode UX mapping with tone discipline
- ✅ Session fairness — L7 FIFO + tier-bump + 30% hard cap + Gini monitoring
- ✅ Abandoned turns leak — L8 30-min auto-abandon + compensating event
- ✅ Error codes leak — L9 registered error codes + template library + CI lint
- ✅ Chaos drill user-visibility — L10 + SR7-D6 maintenance_safe tag controls
- ✅ Multi-player session UX — L3 + L4 + L7 cover the coordination surface
- ✅ Cross-device continuity — S12 ticket refresh + L4 reconnect policy (mobile + desktop both reconnect same PC via user_ref_id)

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 turn state machine in `contracts/turn/`
  - L2 per-user turn indicator via `turn.status.update` WS messages
  - L3 presence states + schema extension + debounced propagation
  - L4 3-policy disconnect matrix with `proceed-if-turn-complete` default
  - L5 optimistic UX rules with conservative rollback
  - L6 degraded-mode UX banners per SR6-D5 mode
  - L7 FIFO queue + tier-bump + 30% cap
  - L8 30-min abandoned-turn cleanup + `turn_outcomes` audit
  - L9 registered error codes + template library + CI lint + i18n
  - L10 12-scenario V1 launch gate with E2E + chaos-drill coverage
- **V1+30d:**
  - L5 divergence rate metric + SR9 alert
  - L4 draft auto-save (local browser storage + cross-device sync)
  - L7 Gini fairness metric + alerting
- **V2+:**
  - Live turn-state preview (other users see your progress)
  - ML-assisted queue estimation (SR1 SLO-aware ETA refinement)
  - Accessibility enhancements per CC-6-D2 streaming-text rules
  - Co-op turn-chaining (multiple users contribute to one turn)

**Residuals (deferred):**
- Cross-device session migration (seamless mobile↔desktop handoff) — V2+
- Rich presence (custom status text / emoji / mood) — V3+
- Spectator mode (observe without participating) — DF5 scope
- Asynchronous turn (submit, come back hours later) — DF1 scope

**Decisions locked (10):**
- **SR11-D1** 8-state turn machine at `contracts/turn/state_machine.go` with state-chart + transition audit via outbox; idempotency key on submitted→queued prevents S6 double-charge from resend storms
- **SR11-D2** `turn.status.update` WS messages + retry_safe field + contextual indicator per state (position in queue / AI thinking with elapsed / streaming text) + tier-matched latency-budget phrasing; cancel vs abort verbs separate pre-LLM vs post-LLM cost framing
- **SR11-D3** `PresenceState` 6-value enum (active / idle / typing / waiting_ai / disconnected_brief / disconnected_ghost) + `session_participants` schema extension + debounced WS propagation; distinct from GoneState (entity existence) vs PresenceState (session liveness)
- **SR11-D4** 3-policy disconnect matrix (suspend / timeout / abandon-other-users); V1 default `proceed-if-turn-complete`; per-session override `session_metadata.disconnect_policy`; DF4 extension point for per-reality defaults
- **SR11-D5** Optimistic UX rules with per-action table; conservative rollback + non-modal toast notification + divergence audit; principle "server is always source of truth"; optimistic never used for decisions affecting other users
- **SR11-D6** Degraded-mode UX mapping — each of SR6-D5's 5 modes has specific banner + tone + allowed-actions rules; reality-scoped vs platform-wide differentiation; client subscribes to `X-LW-Mode` + WS control channel
- **SR11-D7** Turn fairness — FIFO primary + tier-bump slots with S6 budget cost + 60s cooldown + 30% hard cap per 10-min rolling window; `lw_turn_fairness_gini` metric alerting at >0.6
- **SR11-D8** Abandoned-turn 30-min absolute timeout with auto-transition to `failed_terminal` reason `abandoned_timeout`; compensating event emitted; `turn_outcomes` audit table (1y retention; 4 indexes)
- **SR11-D9** Registered error code library at `contracts/errors/user_errors.yaml` with per-locale templates + CI lint + 7 initial codes (TURN_SUBMISSION_TIMEOUT / LLM_BUDGET_EXHAUSTED / REALITY_READ_ONLY / TURN_ABANDONED / LLM_PROVIDER_UNAVAILABLE / CANON_INJECTION_DETECTED / SESSION_CAPACITY_FULL); technical context never user-visible
- **SR11-D10** V1 minimal bar — 12-scenario matrix (turn state × service mode × connection state); each has E2E test + chaos drill; `v1-turn-ux-check.sh` CI gate blocks launch if any scenario not passing

**Features added (11):**
- **IF-44** Turn state machine library (`contracts/turn/state_machine.go`)
- **IF-44a** `turn.status.update` WS message type + per-state indicator UX
- **IF-44b** `PresenceState` enum + `session_participants` schema extension + propagation
- **IF-44c** Disconnect-handling 3-policy matrix + per-session/reality configuration
- **IF-44d** Optimistic UX framework + divergence rollback protocol
- **IF-44e** Degraded-mode UX banner system + tone discipline
- **IF-44f** FIFO + tier-bump queue + fairness Gini metric
- **IF-44g** `turn_outcomes` audit table (1y retention)
- **IF-44h** Registered error code library (`contracts/errors/user_errors.yaml`) with i18n + CI lint
- **IF-44i** V1 12-scenario launch gate (`v1-turn-ux-check.sh`)
- **IF-44j** `admin/session-unfreeze` + `admin/turn-abandon` + `admin/presence-reset` CLI commands

**Foundation vocabulary additions (to `05_vocabulary.md` — SR11 POST-REVIEW approval required):**
- `TurnState` enum (8 values per L1)
- `PresenceState` enum (6 values per L3; distinct from GoneState)

Per the SR6/SR8/SR10 process lesson, vocabulary additions surfaced in POST-REVIEW. Not self-authorized.

**No new invariant** — UX is product discipline, not architectural. I18 (SR10) remains the most recent invariant.

**Problem statuses — no direct moves.** SR11 introduces new UX territory not previously cataloged under A-G / M problems. Partial overlap with C5 (multi-stream UI) via presence/connection differentiation but C5's UI-layout concern remains unresolved. B4 (multi-user turn arbitration) is a distinct problem about NPC-responds-to-whom, not about PC turn-queue ordering — SR11 does not resolve B4. The new concerns SR11 addresses (turn-state visibility, disconnect handling, optimistic UX rollback, degraded-mode user tone, turn fairness, error-code discipline) are cataloged via SR11-D* decisions and IF-44 features rather than as problem-status moves.

**Remaining SRE concerns (SR12) queued:** observability cost + cardinality — retroactive discipline over all metrics/audits accumulated across SR1-SR11 (~45 alerts · 9 audit tables · dozens of gauges + counters). Caps + rollup + deletion policy. Final SR.
