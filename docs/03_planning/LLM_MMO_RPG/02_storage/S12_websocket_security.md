<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S12_websocket_security.md
byte_range: 339398-360894
sha256: 1f30eaac59bc208e129362b6bdd7430c4367925ca49d9ddde2324fd37f973df6
generated_by: scripts/chunk_doc.py
-->

## 12AB. WebSocket Token Security — S12 Resolution (2026-04-24)

**Origin:** Security Review S12 — WebSocket surface has distinct threat model from REST + S11 service-to-service auth. Long-lived connections, browser WS API constraints (no custom headers), per-message re-auth absent, state-change propagation to live connections not designed. Without this layer, WS is the easiest way to regress S2 capability + S3 privacy + S8 erasure + S10 state semantics.

### 12AB.1 Threat model

1. **Token in URL** — `wss://host/?token=...` leaks into access logs, proxy caches, Referer headers → violates §12X.8 logging rules
2. **Stale auth on long-lived connections** — JWT expires / revoked but WS stays open with trusted identity
3. **No per-message re-auth** — post-connect messages implicitly trusted; JWT revocation (logout, password reset, user-erasure) doesn't force disconnect
4. **S2 regression via WS subscription** — user removed from `session_participants` but WS still delivering events
5. **Cross-site WS hijacking** — HTTP-layer CSRF defenses don't apply at WS upgrade
6. **Subprotocol auth ambiguity** — browser WS API has no custom headers; token placement is awkward
7. **No per-connection rate limit** — 100 WS open, spam server; different surface from S6/S7
8. **Topic subscribe leak** — wildcard subscribe pulls sessions user isn't in
9. **Admin WS indistinguishable** — S5 tier distinctions lost on WS surface
10. **Replay attacks** — captured WS messages replayable indefinitely
11. **State-change propagation gap** — user erased, reality archived, admin kick, queue ban all need live-connection close, not next-refresh
12. **Mobile network handoff** — legitimate IP changes cause false kicks

### 12AB.2 Layer 1 — Ticket-Based Handshake

Auth flow — NO token in URL:

```
Step 1: Client (has user JWT)
   POST /v1/ws/ticket
   Authorization: Bearer <user_jwt>
   Body: {desired_realities: [...], desired_scopes: [...]}

Step 2: Auth-service validates JWT → issues ticket
   {
     "ticket_id": "wst_01h...",
     "user_ref_id": "...",
     "allowed_realities": ["R1", "R2"],
     "allowed_scopes": ["chat", "presence", "events"],
     "origin_hash": "sha256(app.loreweave.dev)",
     "client_fingerprint_hash": "sha256(ua + ip/24 + tls_sid_prefix)",
     "exp": "now + 60s"
   }
   Stored in Redis: key=ticket:<ticket_id>, TTL=60s, one-shot

Step 3: Client opens WS
   wss://gateway/ws
   Sec-WebSocket-Protocol: lw.v1, ticket.<ticket_id>

Step 4: Gateway redeems ticket atomically (DEL on redemption)
   - Validate origin_hash matches Origin header
   - Validate fingerprint hash (L6)
   - Open WSSession (L2)
   - Strip ticket.<id> from logs; only lw.v1 protocol logged

Step 5: Connection established; ticket discarded
```

**Ticket never in URL.** Gateway log scrubber strips `ticket.*` subprotocol entries before emission (§12X.8 structured logging integration).

**L2 is the long-lived credential; ticket is strictly one-shot for handshake.**

### 12AB.3 Layer 2 — Per-Connection WS Session

```go
type WSSession struct {
    ConnectionID         uuid.UUID
    UserRefID            uuid.UUID
    AllowedRealities     []uuid.UUID
    AllowedScopes        []string
    OriginHash           [32]byte
    ClientFingerprint    [32]byte
    SubscribedTopics     []TopicRef
    ExpiresAt            time.Time         // 15 min from open
    LastRefreshAt        time.Time
    SeqCounter           map[string]uint64 // per message-type
    SeenNonces           *TTLSet           // 60s nonce dedup
}
```

**TTL: 15 minutes** (independent of user JWT expiry).

Refresh protocol:
- Client sends `{"type":"ws.refresh","ticket":"<new_ticket_id>"}` before expiry
- Gateway validates new ticket (same fingerprint binding), extends session
- On refresh failure (ticket invalid / user revoked / erased) → close with code 4001 `token_expired`
- Client UX: automatic background refresh ~2 min before expiry; user-visible only on failure

Server-push invalidation (see L9): when user state changes server-side, control channel forces immediate close without waiting for next refresh.

### 12AB.4 Layer 3 — Per-Message S2/S3 Authorization

On every inbound message AND every outbound event push, server validates:

1. **Reality access** — reality state (`active`) + `user_consent_ledger` grants access
2. **Session membership** — S2 `session_participants` contains this user_ref_id for target session
3. **Scope match** — WS session's `AllowedScopes` includes the operation's scope
4. **Privacy delivery (outbound only)** — event's `privacy_level` permits delivery to this actor per S3 rules

Implementation:
```go
func (gw *WSGateway) authorizeMessage(s *WSSession, msg *InboundMessage) error {
    key := fmt.Sprintf("%s:%s:%s", s.UserRefID, msg.RealityID, msg.SessionID)
    cached, ok := gw.authzCache.Get(key)       // 30s TTL
    if !ok {
        cached = gw.computeAuthz(s, msg)
        gw.authzCache.Set(key, cached, 30*time.Second)
    }
    return cached.Check(msg.Operation, msg.PrivacyLevel)
}
```

Cache invalidation: control channel (L9) publishes authz-invalidation events on S2 participant change, S3 privacy change, reality state change → ws-gateway evicts affected cache entries + re-authorizes in-flight subscriptions.

Perf: ~1-2ms uncached, sub-ms cached; acceptable at WS volume.

**This is where the S2-regression-via-WS vector closes.** Without L3, §12S.2 capability filter applies only at event-write; WS push could still leak if subscribed before participant change.

### 12AB.5 Layer 4 — Origin Allowlist + CSRF Defense

At HTTP 101 upgrade handshake:

1. Read `Origin` header
2. Validate against allowlist:
   ```yaml
   # config/ws.yaml
   ws.origin.allowlist:
     prod:
       - https://app.loreweave.dev
       - https://loreweave.dev
     staging:
       - https://staging.loreweave.dev
     dev:
       - http://localhost:5173
       - http://localhost:3001
   ```
3. Unknown / missing origin → reject with HTTP 403 `origin_not_allowed` (no WS upgrade)
4. Cross-check ticket's `origin_hash` against hash of connection's `Origin` — mismatch = reject even if origin on allowlist (stolen-ticket defense: attacker on `evil.example.com` with valid ticket can't open WS because Origin doesn't match ticket binding)

Dev mode: config swaps allowlist; same code path.

### 12AB.6 Layer 5 — Per-Connection + Per-User Rate Limits

**Per connection** (enforced in WS handler):
| Limit | Value | Enforcement |
|---|---|---|
| Messages / minute | 100 (paid) · 200 (premium) | Token bucket in Redis per connection_id |
| Message size | 10 KB max | WS frame-size check at ingress |
| Subscriptions | 5 topics max | Subscribe op validates current count |

**Per user** (aggregate across connections):
| Limit | Value | Enforcement |
|---|---|---|
| Concurrent WS | 5 | LRU eviction: new connection beyond 5 closes oldest with code 4008 |

Tier multipliers applied on top of base:
- Free/BYOK: baseline
- Paid: 2× on message rate
- Premium: 3× on message rate

Shared infrastructure with S6 (§12V) + S7 (§12W) token buckets — same Redis keyspace pattern, different prefix (`lw:rl:ws:*`).

Violations:
- Soft (one-time burst): 429-like frame `{"type":"ws.rate_limit","retry_after_ms":1000}` + drop message
- Persistent (sustained > 10s): close with code 4006 `rate_limit_exceeded`

### 12AB.7 Layer 6 — Client Binding + Replay Defense

Ticket includes:
```
client_fingerprint_hash = SHA256(user_agent || ip_prefix_/24 || tls_session_id_first_16b)
```

At WS upgrade:
- Server recomputes fingerprint, compares with ticket
- **Full match** → accept
- **IP-prefix mismatch, UA match** → accept with `soft_reauth_required=true` marker (mobile handoff is legit); next message must include extra ticket OR close after 2 min
- **Full mismatch** → reject 403 `fingerprint_mismatch`

Per-message replay defense:
```json
{
  "type": "chat.message",
  "seq": 42,
  "nonce": "01h7x...",
  "session_id": "...",
  "content": "..."
}
```
- `seq` monotonic per connection per message-type; server rejects duplicates or out-of-order (within tolerance of 5)
- `nonce` unique UUID; server tracks in TTL set, 60s window; duplicate = reject
- Replay beyond 60s → rejected as stale (client must obtain new ticket and reconnect)

Per-message HMAC = **V2+** (significant overhead; defer until threat model requires it).

### 12AB.8 Layer 7 — Versioned WS Message Schema

Contracts at `contracts/ws/v1.yaml` — schema-as-code, mirrors §12C (R3) event-schema pattern:

```yaml
# contracts/ws/v1.yaml
version: 1
messages:
  chat.message:
    direction: client_to_server
    fields:
      seq:        {type: int, required: true, monotonic: true}
      nonce:      {type: string, required: true, format: uuid}
      session_id: {type: uuid, required: true}
      content:    {type: string, max_length: 10000}
    authz:
      requires_subscription: "session.{session_id}.chat"
      principal_mode: requires_user
    effects:
      - event_type: chat.message_authored
      - prompt_intent_possible: session_turn          # §12Y integration

  session.kick:
    direction: client_to_server
    fields:
      session_id:           {type: uuid, required: true}
      target_user_ref_id:   {type: uuid, required: true}
      reason:               {type: string, min_length: 50, max_length: 500}
    authz:
      requires_admin_tier: tier_2                     # S5 Griefing
      requires_admin_session_claim: true              # S11-D5
    effects:
      - control_channel_event: session.user_kicked
      - target_connection_close_code: 4005

  ws.refresh:
    direction: client_to_server
    fields:
      ticket: {type: string, required: true, format: ticket_id}
    authz:
      principal_mode: requires_user

  # Server-push message types
  event.delivery:
    direction: server_to_client
    fields:
      event_id:       {type: uuid}
      event_type:     {type: string}
      privacy_level:  {type: enum, values: [normal, sensitive, confidential]}
      payload:        {type: object}

  ws.close:
    direction: server_to_client
    fields:
      code:   {type: int}
      reason: {type: string}
      retry_guidance: {type: object, optional: true}
```

Enumerated message types V1:
- Chat: `chat.message`, `chat.typing`, `chat.edit`, `chat.delete`
- Session: `session.state`, `session.join`, `session.leave`, `session.kick` (admin)
- Presence: `presence.update`
- Protocol: `ws.ping`, `ws.pong`, `ws.refresh`, `ws.close`
- Server-push: `event.delivery`, `session.membership_changed`, `reality.state_changed`

Server validates shape + `authz` block on every message; malformed or unauthorized → error response + `lw_ws_messages_rejected_total{reason=...}` metric.

**Chat content → §12Y prompt-assembly integration**: messages marked with `prompt_intent_possible` get routed to prompt layer for LLM turns. WS doesn't bypass §12Y sandboxing — transport delivery is separate from content processing.

### 12AB.9 Layer 8 — Connection Lifecycle Audit + Enumerated Close Codes

Close codes:
| Code | Meaning |
|---|---|
| `1000` | Normal closure (client-initiated) |
| `4001` | `token_expired` — refresh failed |
| `4002` | `token_revoked` — user logout / JWT revoked |
| `4003` | `user_erased` — S8 crypto-shred fired |
| `4004` | `reality_archived` — S10 state transition to archived/dropped |
| `4005` | `admin_kick` — S5 Tier 2 Griefing action |
| `4006` | `rate_limit_exceeded` — persistent L5 violation |
| `4007` | `origin_mismatch` — L4 violation mid-connection |
| `4008` | `connection_limit_exceeded` — L5 per-user LRU eviction |
| `4009` | `fingerprint_mismatch` — L6 binding broken |
| `4010` | `schema_invalid` — persistent malformed messages |

Close codes are contract; §12Y fixtures + client error-handling hardcode this enum.

Audit events (to structured logs per §12X.8):
```json
{"ts":"...","event":"ws_connection.opened",
 "user_ref_id":"...","connection_id":"...",
 "origin":"...","fingerprint_hash":"..."}

{"ts":"...","event":"ws_connection.subscribed",
 "connection_id":"...","topic":"session.X.chat",
 "authorized_by":"session_participants"}

{"ts":"...","event":"ws_connection.closed",
 "connection_id":"...","code":4003,"duration_seconds":127,
 "message_count":45}
```

Retention: 90d (app_logs per §12X.4). Per-message sending NOT audited at INFO level (volume).

Admin WS actions (kick, bulk-disconnect):
- Write to `admin_action_audit` (§12U)
- Write to `service_to_service_audit` (§12AA.L9) — ws-gateway logs admin-originated close events with `admin_session_id`

### 12AB.10 Layer 9 — Forced Disconnect via Control Channel

Shared Redis stream `lw:ws:control` — published by state-change authorities, consumed by ws-gateway:

```
Publishers + event types:
┌─────────────────────┬─────────────────────────────────┐
│ auth-service        │ user.token_revoked              │
│                     │ user.throttled (S7 queue ban)   │
├─────────────────────┼─────────────────────────────────┤
│ meta-worker         │ user.erased (S8)                │
│                     │ user.consent_revoked (S8-D8)    │
├─────────────────────┼─────────────────────────────────┤
│ world-service       │ reality.state_changed           │
│                     │ reality.ancestry_severed (§12M) │
├─────────────────────┼─────────────────────────────────┤
│ admin-cli           │ session.user_kicked (S5)        │
│                     │ session.frozen (admin)          │
├─────────────────────┼─────────────────────────────────┤
│ roleplay-service    │ session_participants.changed    │
└─────────────────────┴─────────────────────────────────┘
```

All control events signed per §12AA.L7 (Ed25519; ws-gateway verifies before acting).

ws-gateway maintains in-memory indexes:
```go
connectionsByUser     map[user_ref_id][]connection_id
connectionsByReality  map[reality_id][]connection_id
connectionsBySession  map[session_id][]connection_id
```

Control event → index lookup → targeted action:
- `user.erased` → close all connections with code 4003
- `user.token_revoked` → close all connections with code 4002
- `reality.state_changed(archived|dropped)` → close all connections subscribed to reality with code 4004
- `session.user_kicked` → close specific user's connection to that session with code 4005
- `session_participants.changed` → invalidate L3 authz cache for affected users (no disconnect; next message re-authorizes)

**SLA: propagation from source event to connection close < 1 second.** Measured via `lw_ws_state_change_propagation_ms` histogram; alert if P99 > 5s (PAGE SRE).

### 12AB.11 Layer 10 — Observability + Dashboards

Metrics:
```
lw_ws_connections_active{env, region}                    gauge
lw_ws_connections_opened_total                            counter
lw_ws_connections_closed_total{close_code}                counter
lw_ws_messages_received_total{type}                       counter
lw_ws_messages_rejected_total{reason}                     counter
lw_ws_subscription_denied_total{reason}                   counter
lw_ws_connection_duration_seconds                         histogram
lw_ws_refresh_failures_total{reason}                      counter
lw_ws_state_change_propagation_ms                         histogram
lw_ws_rate_limit_violations_total                         counter
lw_ws_authz_cache_hit_ratio                               gauge
```

Alerts:
| Alert | Threshold | Severity |
|---|---|---|
| WS refresh failure rate | > 5% over 5 min | WARN (token flow broken?) |
| Connections closed code=4001 | > 10% of closes | WARN (re-auth UX broken?) |
| Subscription denied rate | > 20% | WARN (probing or bug) |
| State-change propagation P99 | > 5s | **PAGE** (security-critical SLA) |
| Connection count 3σ spike | baseline-dependent | INVESTIGATE (bot / incident) |
| Origin mismatch rejections | > 0.1% of upgrades | INVESTIGATE (attack probing) |

Dashboards:
- **DF9 per-reality ops**: WS connections per reality, close-code distribution, authz cache hit ratio
- **DF11 fleet management**: platform-wide WS health, propagation SLA, tier breakdown
- **Security dashboard**: L9 propagation latency, revoke events, origin-mismatch log

### 12AB.12 Interactions + service split + what this resolves

**Interactions**:

| With | Interaction |
|---|---|
| §12F (R6) publisher | ws-gateway consumes Redis streams from publisher; WS push path is §12F.L4 realized |
| §12S.2 (S2) | L3 per-message `session_participants` check closes WS-surface regression |
| §12S.3 (S3) | L3 privacy_level filter on outbound push; sensitive/confidential events gated |
| §12U (S5) | L7 admin messages require S11-D5 admin JWT + `admin_session_id`; L9 admin-kick propagation |
| §12V (S6) | L5 shares rate-limit infrastructure; LLM-triggering WS messages count toward S6 turn rate |
| §12W (S7) | L9 queue-ban → WS disconnect; prevents queue-abuse-via-WS |
| §12X (S8) | L9 `user.erased` → immediate disconnect code 4003; audit logs follow §12X.8 rules |
| §12Y (S9) | WS chat content → prompt-assembly; WS doesn't bypass §12Y sandboxing |
| §12Z (S10) | L9 reality state-change → WS close with code 4004; close codes map to GoneState |
| §12AA (S11) | ws-gateway is a service with SVID; control events signed per §12AA.L7; `x-principal-mode: requires_user` for chat RPCs |
| CLAUDE.md gateway invariant | WS terminates at api-gateway-bff V1; optional split to `ws-gateway` service V1+30d under same trust boundary |

**Service split**:

| Phase | Arrangement |
|---|---|
| **V1** | WS terminates at `api-gateway-bff` (merged with REST). Simpler deploy, shared auth, shared SVID. |
| **V1+30d trigger** | If per-instance WS active count > 10K OR CPU/memory profile diverges significantly from REST load → split into dedicated `ws-gateway` service. Same SVID trust model (§12AA), separate deployment. |

**Accepted trade-offs**:

| Cost | Justification |
|---|---|
| Ticket handshake = extra round-trip | 60s TTL and one-shot use make ticket cheap; eliminates URL-token leak vector |
| 15-min session + refresh complexity | Short blast-radius window if credentials compromised; client refresh is silent background task |
| Per-message authz adds 1-2ms | Closes S2 regression vector; 30s cache reduces cost dramatically |
| Control channel + in-memory indexes in ws-gateway | Required for <1s propagation SLA; memory cost bounded by concurrent connection count |
| Fingerprint binding rejects legit mobile handoff | L6 soft-reauth UX absorbs false positives; alternative (no binding) enables ticket theft |
| Enumerated close codes | Contract rigidity, but enables client error-handling determinism + fixture testing |

**What this resolves**:

- ✅ **Token in URL** — L1 subprotocol-only ticket
- ✅ **Stale auth** — L2 15-min refresh + L9 force-disconnect
- ✅ **S2 regression via WS** — L3 per-message authz with cache invalidation
- ✅ **Cross-site WS hijacking** — L4 origin allowlist + ticket origin binding
- ✅ **No per-connection rate limit** — L5 tiered limits
- ✅ **Replay attacks** — L6 seq + nonce + 60s window
- ✅ **Schema drift / admin indistinguishability** — L7 versioned schema + admin_tier authz
- ✅ **State-change propagation gap** — L9 <1s SLA via control channel
- ✅ **Audit gap** — L8 lifecycle events + close code enum
- ✅ **Cross-reality scope confusion** — ticket's `allowed_realities` binds session
- ✅ **Mobile handoff false kicks** — L6 soft-reauth UX

**V1 / V1+30d / V2+ split**:
- **V1**: L1 ticket handshake, L2 refresh, L3 per-message authz, L4 origin check, L5 rate limits, L7 schema v1, L8 basic audit + close codes, L9 core state-change propagation (revoke + erase), L10 metrics
- **V1+30d**: L6 fingerprint + replay defense, L8 full audit table integration, L9 full state-change propagation (reality, admin-kick, queue-ban), L10 advanced dashboards, service split to `ws-gateway` if load dictates
- **V2+**: L6 per-message HMAC, adaptive rate limits tied to S7 reputation, admin impersonation on WS

**Residuals (accepted)**:
- Per-message HMAC deferred V2+ (overhead vs threat-model tradeoff)
- Adaptive rate limits deferred V2+ (requires S7 reputation system as prerequisite)
- External WebSocket integrations part of DF15 (distinct trust model)

