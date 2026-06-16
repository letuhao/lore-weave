# Runbook — WS Ticket Replay Attack

> **Owning alerts:** `LWWsTicketReplayAttack`, `LWWsOriginMismatchSpike`, `LWWsFingerprintMismatchSpike`
> **Severity:** page (replay + origin mismatch); warn (fingerprint mismatch)
> **Owning service:** `api-gateway-bff` (NestJS, `/v1/ws/ticket` + `/ws/v1` per cycle 28 L6.A+L6.B)
> **LOCKED references:** Q-L6-1 (NestJS WS impl), Q-L6-2 (10K cap), Q-L6-3 (server-only)

---

## What triggered

- `LWWsTicketReplayAttack` — sustained `ticket_not_found` redemptions >0.5/sec for 5 m. Attackers replay captured ticket IDs OR a buggy client retries without re-fetching.
- `LWWsOriginMismatchSpike` — tickets issued for origin A presented for upgrade with origin B. Likely cross-site (CSWSH) attempt or misconfigured CDN.
- `LWWsFingerprintMismatchSpike` — ticket presented with UA/IP/24/TLS prefix not matching the issued bundle. Could be legitimate mobile handoff or ticket exfiltration.

---

## Why the alert exists (S12 §12AB.2)

Tickets are **one-shot**, **60 s TTL**, and **bound to origin + fingerprint**:

| Defense layer | Implementation file (cycle 28) |
|---|---|
| One-shot | `ticket-store.ts::InMemoryTicketStore.redeem` — Map.get+delete atomic |
| TTL | `TICKET_TTL_MS = 60_000` in `ticket-store.ts` |
| Origin bind | `hashOrigin(req.headers.origin)` compared via `constantTimeBufferEquals` |
| Fingerprint bind | `hashFingerprint(ua, ip/24, tls_session_prefix)` compared at upgrade |
| Entropy | `wst_<32-hex>` from `crypto.randomUUID` — 122 random bits |

Any replay attempt must therefore:
1. Capture the ticket BEFORE the legitimate redeem (one-shot kills serial replays).
2. Replay within 60 s (TTL kills slow replays).
3. From the SAME origin (CORS + origin hash kill cross-site attempts).
4. From a device matching the original UA/IP/24/TLS prefix.

---

## Triage steps

### 1. Identify scope

```bash
# Top user-refs by handshake failure in last 5 m
loki -q '{job="api-gateway-bff"} |= "WS /ws/v1 handshake rejected" | json | line_format "{{.user_ref_id}} {{.reason}}"' \
  --since=5m | sort | uniq -c | sort -rn | head

# Top source IPs (after /24 collapse) by failed redeem
grep ticket_not_found gateway.log | jq -r '.client_ip_24' | sort | uniq -c | sort -rn | head
```

### 2. Distinguish attack from regression

| Signal | Attack | Client bug |
|---|---|---|
| Many distinct user_ref_ids | yes — attacker exfiltrated multiple tickets | no — one buggy client retries |
| Single user_ref_id, many IPs | no — attacker rarely targets one user from many sources | yes — mobile roaming |
| Spike correlates with deploy | no | likely — client regression |
| Origin mismatch present | YES — attack | NO — bug |

If correlated with a deploy → roll back client (frontend-game) or rev the protocol header to force-fetch.

### 3. Containment

**Replay attack confirmed:**
```bash
# 1. Disable ticket issue for the affected user(s) (auth-service admin API)
kubectl exec deploy/auth-service -- admin user lock --user-ref $USER --reason ticket_replay_suspected

# 2. Force-disconnect their existing WS sessions (L6.D cycle 29 mechanism;
#    until that lands, restart the gateway pod the user is hashed to)
kubectl rollout restart deploy/api-gateway-bff -n loreweave-prod

# 3. Capture forensics — last 60 m of ticket issues + redeem outcomes
kubectl logs deploy/api-gateway-bff --since=60m | grep -E '(TICKET|WS /ws/v1)' > /tmp/ticket-forensics-$(date +%s).log
```

**Origin mismatch sustained:**
- Check CDN config — are we serving `/v1/ws/ticket` from a different host than `/ws/v1`? They MUST share origin.
- If WAF / Cloudflare is in front, ensure it preserves the `Origin` header through to NestJS.

**Fingerprint mismatch sustained (warn-level):**
- Check whether a mobile carrier rolled out new CGNAT egress IPs (legit).
- Check whether one user's UA changed mid-session (browser auto-update — legit).
- Both legit cases resolve themselves in <60 m; if persistent past that → escalate.

---

## Verification post-mitigation

1. `rate(lw_ws_ticket_redeemed_total{outcome="not_found"}[5m])` returns to baseline (< 0.05/sec).
2. `lw_ws_active_connections` not in free-fall (we haven't accidentally evicted real users).
3. Audit log shows the lock action against the suspected user (auth-service `user_locks` table).

---

## Post-incident

- Add the captured ticket IDs to the audit log with `disposition = replay_attempt`.
- If this was a real attack, write up the timeline in `docs/security/incidents/YYYY-MM-DD-ws-ticket-replay.md`.
- Consider whether the 60 s TTL is too generous for the threat model — but DO NOT change without LOCKED Q vote (Q-L6 family).

---

## Related runbooks

- `runbooks/ws/refresh_failures.md` — what to do when token refresh starts failing en masse
- `runbooks/ws/saturation.md` (cycle 29) — when the cap-saturation alert fires
- `runbooks/ws/forced_disconnect.md` (cycle 29) — when L6.D control-channel disconnects misbehave
