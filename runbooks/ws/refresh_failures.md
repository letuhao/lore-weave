# Runbook — WS Token Refresh Failures

> **Owning alerts:** `LWWsHandshakeFailureSpike` (reason=ticket_expired), `LWWsAuthzRejectionSpike`
> **Severity:** warn (page only if user-facing impact)
> **Owning service:** `api-gateway-bff` (WS server) + `auth-service` (JWT issuer)
> **LOCKED references:** Q-L6-1, Q-L6-2, Q-L6-3 (foundation server-only)

---

## What triggered

- `LWWsHandshakeFailureSpike{reason="ticket_expired"}` — clients present tickets that have already passed the 60 s TTL when the WS upgrade is attempted.
- `LWWsAuthzRejectionSpike` — per-message authz drops (cycle 29 L6.C) trend up because client tokens went stale mid-session.

---

## Causes (ranked by frequency)

| # | Cause | Signal |
|---|---|---|
| 1 | **Clock skew on a gateway replica** — replica wall clock drifted such that ticket is considered expired before client thinks so | `ticket_expired` localized to one pod; `node_time_offset_seconds` > 5 |
| 2 | **Slow client upgrade** — mobile network jitter delays the `Sec-WebSocket-Protocol` request past 60 s | distributed across pods; correlates with mobile carriers in user-agent |
| 3 | **Stuck refresh loop** — frontend-game's refresh logic mis-handles 401 from `/v1/ws/ticket` and never re-fetches | sustained spike from a small set of users |
| 4 | **auth-service JWT expiry** — root JWT itself expired, so ticket-issue rejects with 401 | `lw_auth_jwt_expired_total` correlates with the WS spike |

---

## Triage flow

### Step 1 — is it clock skew?

```bash
# Check pod-level clock offset on every gateway replica
kubectl exec -n loreweave-prod deploy/api-gateway-bff -- date -u
# Compare to chrony / NTP source — > 5 s drift is the threshold

# Or with metrics
promql 'max(abs(node_time_offset_seconds{job="api-gateway-bff"})) by (instance) > 5'
```

If yes → restart the affected pod (force NTP sync on startup) and add to incident notes.

### Step 2 — is it a frontend-game regression?

```bash
# Are tickets being fetched repeatedly without successful redeem?
promql 'rate(lw_ws_ticket_redeemed_total{outcome="expired"}[5m]) / rate(lw_ws_handshake_failures_total[5m])'
# Ratio close to 1.0 = clients fetch ticket but fail to redeem in time
```

If yes → page frontend-game on-call. They may need to ship a hotfix that increases the
`ticket → upgrade` budget or pre-fetches a ticket BEFORE the WS connection.

### Step 3 — is it the JWT itself?

```bash
# JWT-side metrics (auth-service)
promql 'rate(lw_auth_jwt_expired_total[5m])'
```

If high → auth-service is rejecting `/v1/ws/ticket` calls before they even get to ticket-issue. Check `auth-service` logs for users whose refresh-token expired.

---

## Containment

| Cause | Mitigation |
|---|---|
| Clock skew | `kubectl rollout restart deploy/api-gateway-bff` — pods re-sync NTP at startup |
| Slow client | TEMPORARILY bump `WS_HANDSHAKE_TIMEOUT_MS` via env override on the deployment; ticket TTL itself is LOCKED at 60 s (Q-L6 family — do not change) |
| Frontend regression | Roll back frontend-game; coordinate with their on-call |
| auth-service JWT issue | Roll back auth-service or extend JWT TTL via the auth admin API |

---

## Verification

1. `rate(lw_ws_handshake_failures_total{reason="ticket_expired"}[2m])` returns to baseline (< 0.05/sec).
2. `rate(lw_ws_ticket_redeemed_total{outcome="success"}[1m])` returns to expected (typically 5–50/sec V1).
3. No user-facing reports of "stuck loading chat".

---

## Post-incident

- If clock skew was the cause, file a P3 ticket for SRE infra to investigate NTP drift root cause.
- If a frontend regression caused it, ensure their CI now includes a test that the ticket→upgrade time is < 5 s.
- If the JWT itself was the issue, add a pre-flight check at `/v1/ws/ticket` that 401s with a `RETRY_AFTER_LOGIN` close code (4002) so the client can route the user back to login instead of looping.

---

## Related runbooks

- `runbooks/ws/ticket_replay_attack.md` — sibling alert for malicious failures
- `runbooks/ws/forced_disconnect.md` (cycle 29) — when control-channel disconnects misbehave
