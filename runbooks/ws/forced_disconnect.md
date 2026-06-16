# SRE Runbook — WS Forced Disconnect

> Source: L6.D (RAID cycle 29). Spec: S12 §12AB.9 (close codes), §12AB.10 (forced disconnect SLA).
> Pairs with the [ticket replay runbook](./ticket_replay_attack.md) + the
> [refresh failures runbook](./refresh_failures.md).

## What this covers

The gateway forcibly closes a user's WebSocket connections in response to
a control message on the shared Redis pubsub topic
`lw:dependency:control`. This runbook covers:

- How forced disconnect happens (control flow)
- The 11 close codes + when each fires
- SRE actions for the 5 alerts that involve forced disconnect
- How to manually force-disconnect a user (incident response)

## Control flow (success path)

```
+-----------------+   PUBLISH      +------------------+   FANOUT      +------------------+
| auth-service    |--------------->| Redis pubsub     |-------------->| api-gateway-bff  |
| admin-cli       | ws_disconnect_ | lw:dependency:   | each replica  | WsControlChannel |
| roleplay-svc    | user kind      | control          | subscribes    | Consumer         |
+-----------------+                +------------------+               +------------------+
                                                                              |
                                                                              v
                                                                   +------------------+
                                                                   | Disconnector     |
                                                                   | -> WsV1Gateway   |
                                                                   |    .disconnect   |
                                                                   |    User(...)     |
                                                                   +------------------+
                                                                              |
                                                                              v
                                                                   close(code, reason)
                                                                   on each live socket
```

End-to-end SLA: **< 1 second** propagation (publish → close-frame on browser).
P99 > 5s triggers the `LWWsForcedDisconnectLatency` alert (page).

## The 11 close codes

Canonical Rust enum: `crates/contracts-ws/src/close_codes.rs::CloseCode`.
Canonical Go enum: `contracts/ws/envelope.go::CloseCode`.

| Code | Short name | Trigger | Producer |
|------|-----------|---------|----------|
| 1000 | normal_closure | client initiated, clean shutdown | client |
| 4001 | token_expired | session token expired mid-connection | gateway |
| 4002 | token_revoked | JWT revoked / user logout | auth-service |
| 4003 | user_erased | S8 crypto-shred fired | erasure-service |
| 4004 | reality_archived | S10 reality dropped | reality-service |
| 4005 | admin_kick | admin force-kick via CLI | admin-cli |
| 4006 | rate_limit_exceeded | persistent rate-limit violation | gateway |
| 4007 | origin_mismatch | mid-connection origin policy change | gateway |
| 4008 | connection_limit_exceeded | per-replica cap reached (Q-L6-2) | gateway |
| 4009 | fingerprint_mismatch | compromise detected (client binding broken) | compromise-detection |
| 4010 | schema_invalid | persistent malformed messages | gateway |

## Manual force-disconnect (incident response)

For an immediate revocation NOT going through the auth-service /
admin-CLI flow (e.g., the auth-service is hard-down and you need to
kick a user out):

```bash
NONCE=$(uuidgen)
redis-cli -h <redis-host> PUBLISH lw:dependency:control "$(jq -cn \
  --arg user "$USER_REF_ID" \
  --arg nonce "$NONCE" \
  --arg reason "manual_kick: $INCIDENT_TICKET" \
  --arg svc "sre-runbook" \
  --arg inst "$(hostname)" \
  --argjson code 4005 \
  --argjson ts "$(date +%s%N)" \
  '{
     version: 1,
     kind: "ws_disconnect_user",
     service: $svc,
     instance: $inst,
     reason: $reason,
     ts_nanos: $ts,
     user_ref_id: $user,
     close_code: $code,
     nonce_id: $nonce
   }')"
```

Verify in 1-3s: gateway logs `WS /ws/v1 force-disconnect close ...` for
each pod that had this user connected.

## Triage table — alerts that involve forced disconnect

| Alert | Probable cause | First action |
|-------|---------------|--------------|
| `LWWsForcedDisconnectLatency` (page) | Redis pubsub lag or gateway pod stuck | Check Redis `latency` cmd; restart Redis-pubsub-stuck pod (close socket `<host>:6379`) |
| `LWWsForcedDisconnectSpike` (warn) | Auth incident (mass logout?) or admin runbook misuse | Look at `reason` label distribution; cross-reference with auth-service incidents |
| `LWWsConsumerDropSpike` (warn) | Bad publisher emitting malformed payloads | Tail `gateway` logs grep `ws-control:`; identify producer via `service` field |
| `LWWsConsumerVersionMismatch` (info) | Mixed rollout — new publisher, old consumer | Wait for consumer rollout to complete; harmless |
| `LWWsDuplicateNonces` (info) | Producer retry loop without idempotency | Identify the retrying publisher; rate-limit emit |

## Idempotency

Each control message MUST carry a unique `nonce_id` (UUID v4 recommended).
Subscribers de-dupe on a 1024-entry LRU per pod. Two emissions of the
same `nonce_id` collapse to a single close action.

## Adversary considerations

- **DoS via mass disconnect**: a compromised publisher could disconnect
  ALL users by spamming the topic. Defense: Redis ACL restricts PUBLISH
  to the named producer services (`auth-service`, `admin-cli`,
  `roleplay-service`, `erasure-service`, `reality-service`,
  `compromise-detection`). SRE manual kick requires CLI auth.
- **Malformed payload**: dropped + counted (`lw_ws_authz_rejections_total`
  with `reason=schema_invalid`); never crashes the consumer.
- **Replay across pods**: same nonce → same close, fanout is idempotent.
- **Stale close-code values**: any code outside the 11 enumerated values
  is rejected at the Disconnector before reaching the socket.

## Verification queries

After a kick:

```promql
# Count of forced disconnects in the last 5 min
increase(lw_ws_connection_evictions_total{reason="forced_disconnect"}[5m])

# Drop rate on the control channel (should be ~0)
rate(lw_ws_authz_rejections_total{reason="schema_invalid"}[5m])
```

## Cross-links

- Spec: [`docs/03_planning/LLM_MMO_RPG/02_storage/S12_websocket_security.md`](../../docs/03_planning/LLM_MMO_RPG/02_storage/S12_websocket_security.md) §12AB.9 + §12AB.10
- Code: [`services/api-gateway-bff/src/ws/control-channel-consumer.ts`](../../services/api-gateway-bff/src/ws/control-channel-consumer.ts)
- Code: [`services/api-gateway-bff/src/ws/disconnector.ts`](../../services/api-gateway-bff/src/ws/disconnector.ts)
- Code: [`crates/contracts-ws/src/close_codes.rs`](../../crates/contracts-ws/src/close_codes.rs)
- Code: [`contracts/lifecycle/mode_propagation.go`](../../contracts/lifecycle/mode_propagation.go) (shared channel)
