<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S11_service_to_service_auth.md
byte_range: 319439-339398
sha256: 998eb91c5b7784b2c518ad44a9624eb4991587443be49148e63a24e64ef9fa5d
generated_by: scripts/chunk_doc.py
-->

## 12AA. Service-to-Service Authentication — S11 Resolution (2026-04-24)

**Origin:** Security Review S11 — current design covers external-traffic auth (gateway JWT) + per-service DB roles (§12T.8), but service-to-service RPC has no cryptographic identity. With 19+ services at MMO-RPG scope (adding world-service, roleplay-service, publisher, meta-worker, event-handler, migration-orchestrator, admin-cli, audit_retention_cron), flat-trust VPC = blast radius = whole platform.

### 12AA.1 Threat model

1. **Flat-trust network** — one compromised service = full compromise; meta-worker and admin-cli are particularly juicy targets
2. **Admin-cli impersonation** — no cryptographic distinction between real admin-cli and malicious actor on same network; app layer trust bypasses §12T.8 DB roles
3. **Event-handler forgery** — Redis ACL misconfiguration lets attacker inject forged events; consumers treat them as authentic
4. **No RPC audit** — "what did meta-worker do at 03:15?" currently unanswerable
5. **Shared env-var secrets** — single DB password or API key leak → all services compromised; no rotation path
6. **Provider-registry credential leakage** — BYOK keys fetchable by any service on the network
7. **S8 cross-reality fan-out** (`meta-worker` → all realities) needs downstream verification of origin
8. **Confused deputy** — JWT forwarding without explicit contract = services escalating user privilege accidentally
9. **Admin-vs-user indistinguishable** at service boundary (same JWT schema currently)
10. **Dev/prod parity drift** — "no auth locally" causes production-only bugs
11. **No break-glass** — incident response has no audited time-bounded access path; ad-hoc root access permanent

### 12AA.2 Layer 1 — Per-Service Cryptographic Identity (SPIFFE-like)

Every service has workload identity:
```
spiffe://loreweave.dev/service/<service-name>/<env>
```
Examples:
- `spiffe://loreweave.dev/service/roleplay-service/prod`
- `spiffe://loreweave.dev/service/meta-worker/prod`
- `spiffe://loreweave.dev/service/admin-cli/prod`

Identity form:
- **V1**: JWT-SVID in HTTP header (`Authorization: SVID <jwt-svid>`)
- **V1+30d**: X.509 SVID cert via mTLS (L2)

TTL policy:
| Service class | TTL | Rationale |
|---|---|---|
| General services | 24h | Balance rotation overhead vs blast radius |
| High-sensitivity (meta-worker, admin-cli, migration-orchestrator, audit_retention_cron) | 1h | Tighter blast radius for privileged operations |

**Secret-free attestation**: SVIDs issued by PKI after runtime-metadata attestation — no pre-shared password:
- ECS: task ARN + IAM role
- K8s: pod spec + namespace + service account
- EC2: instance ID + IAM role

Platform PKI options:
- **V1 default**: AWS Private CA + cert-manager (managed, fits existing ECS/RDS)
- **V2+ if self-host needed**: SPIRE self-hosted (`services/spire-server/`)

Service bootstrap env vars:
```
SERVICE_NAME=roleplay-service
ENV=prod
SVID_SOCKET=/var/run/spire/agent.sock
VAULT_URL=https://vault.internal:8200
# ... NOTHING secret
```

### 12AA.3 Layer 2 — mTLS for Service-to-Service Traffic

**V1**: JWT-SVID in `Authorization` header; TLS terminated at load balancer (ALB). Service entry-middleware validates JWT-SVID against platform CA.

**V1+30d**: End-to-end mTLS via sidecar (Envoy):
- Client presents X.509 SVID cert; server validates:
  - CA trust chain to platform PKI
  - SVID identity matches ACL expectation (L3)
  - Cert not expired / not revoked
- App code unchanged; sidecar handles TLS termination + initiation
- Configuration via workload selector: `selector: service:roleplay-service, env:prod`

**External-traffic invariant preserved**: api-gateway-bff remains sole external termination point (per CLAUDE.md). Internal mTLS is layered on top.

**Parity**: dev/staging/prod all use mTLS (V1+30d onward); dev gets short-lived dev-CA with auto-rotation. "Disable auth locally" is forbidden.

### 12AA.4 Layer 3 — Service ACL Matrix

Declarative allowed call pairs at `contracts/service_acl/matrix.yaml`:

```yaml
# Caller → allowed callees + specific RPCs
roleplay-service:
  requires_mtls: true
  can_call:
    knowledge-service:
      - /v1/memory/search
      - /v1/memory/write
    glossary-service:
      - /v1/glossary/lookup
    provider-registry-service:
      - /v1/providers/resolve
    # prompt-assembly is in-process; not a network call

meta-worker:
  requires_mtls: true
  can_call:
    world-service:
      - /internal/events/fanout
      - /internal/reality/ancestry-update
    roleplay-service:
      - /internal/session/invalidate
      - /internal/session/consent-revoked
    knowledge-service:
      - /internal/entity/erase
    # ... per cross-reality broadcast surface

admin-cli:
  requires_mtls: true
  can_call: "*"                                 # all services
  additional_requirements:
    - admin_jwt_with_impact_tier
    - tier_1_requires_dual_actor                # S5 integration
    - break_glass_requires_tier_1_dual_actor
```

Enforcement:
- Each service has entry middleware that reads caller SVID (JWT-SVID or cert)
- Middleware resolves caller's service name, looks up ACL row
- If `(caller, callee, rpc)` not in matrix → `403 Forbidden` + audit log entry
- Denied-call metric `lw_service_acl_denied_total{caller, callee, rpc}` — SRE alert on spikes

Governance:
- Changes to `matrix.yaml` require PR review from security team (GitHub CODEOWNERS)
- CI lint: PR that adds `http.Post("http://other-service/...")` without corresponding ACL entry → fail
- Changelog of ACL changes reviewed quarterly alongside admin audit (§7 of ADMIN_ACTION_POLICY)

### 12AA.5 Layer 4 — User Context Propagation (explicit principal split)

Each RPC declares principal requirement in its OpenAPI/gRPC spec:

```yaml
# contracts/api/knowledge-service/v1.yaml
/v1/memory/search:
  post:
    x-principal-mode: requires_user              # forwards user JWT
    x-admin-tier-required: false
    # ...

/internal/entity/erase:
  post:
    x-principal-mode: system_only                # no user JWT; caller SVID authoritative
    x-admin-tier-required: false
    x-callers-allowed: [meta-worker]
```

Three modes:
| Mode | User JWT required | Example |
|---|---|---|
| `requires_user` | Yes, forwarded from upstream | Session turn submission |
| `system_only` | No; caller SVID authoritative | meta-worker fanout |
| `either` | Either works; downstream branches | Health checks, maintenance |

Middleware populates context:
```go
type Principal interface {
    IsUser() bool
    IsService() bool
    IsAdmin() bool
    UserRefID() *uuid.UUID
    ServiceSVID() string
    AdminSessionID() *uuid.UUID
    AdminImpactTier() *ImpactClass
}

ctx.PrincipalUser()     // *UserPrincipal or nil
ctx.PrincipalService()  // *ServicePrincipal (always present when authenticated)
ctx.IsOnBehalfOf()      // true if user JWT forwarded
```

**Confused-deputy defense**: service cannot act "on behalf of user" without forwarded JWT. RPC declared `requires_user` rejects requests missing user JWT even if caller SVID is valid.

Audit log records both principals: `{caller_svid, user_ref_id?}` so "which service did what on behalf of whom" is always traceable.

### 12AA.6 Layer 5 — Admin Context Distinction

Admin JWT claim schema (distinct from user JWT):

```json
{
  "sub": "admin_user_id_123",
  "iss": "auth-service",
  "aud": "loreweave-internal",
  "role": "admin",
  "admin_session_id": "01h...",
  "admin_impact_tier": "tier_1",
  "admin_second_approver": "admin_user_id_456",
  "admin_approval_timestamp": "2026-04-24T14:00:00Z",
  "exp": "15-min TTL",
  "jti": "unique per issuance"
}
```

Issuance flow (via auth-service):
- **Tier 3 Informational**: standard admin login; single-actor; 15-min TTL
- **Tier 2 Griefing**: 50+ char reason logged + user notification scheduled (S5-D5); single-actor; 15-min TTL
- **Tier 1 Destructive**: dual-actor approval flow completed + 24h cooldown (S5-D1); JWT binds `admin_second_approver`; 15-min TTL
- **Break-glass**: L10 flow; 24h TTL (exception); all actions double-audited

Short TTL (15 min) = reduced blast radius if token leaks. Admin consoles refresh silently. Operational overhead bounded because admin sessions are typically short anyway.

Downstream service validation:
- `role == "admin"` required for admin endpoints
- `admin_impact_tier` must meet endpoint's minimum (e.g., `admin/user-erasure` requires `tier_1`)
- `admin_session_id` cryptographically links admin session → `admin_action_audit` rows (S5)
- `admin_second_approver` present AND non-empty for Tier 1 — else reject

Admin JWT never used for `requires_user` RPCs unless admin is impersonating a specific user (separate flow, explicit `impersonation_of` claim — V2+).

### 12AA.7 Layer 6 — Vault-Based Secret Management

All secrets (DB passwords, API keys, LLM provider credentials, KEKs, signing keys) live in vault:
- **V1 default**: AWS Secrets Manager + KMS (fits existing stack)
- **V2+ alternative**: Vault self-hosted if control requirements grow

Services authenticate to vault via SVID:
```go
secret, err := vault.GetSecret(ctx, "db/roleplay-service/prod",
    WithSVID(svidClient))
```
- Vault policy binds SVID → allowed secret paths (not service-name strings — prevents spoofing)
- Tokens issued to services are short-lived (15-min); services re-fetch on expiry or 401 from downstream

Env vars contain only bootstrap config (see L2). NO:
- DB passwords
- API keys
- Encryption keys
- JWT signing keys

Rotation:
- Vault auto-rotates DB passwords per schedule (monthly general; weekly for meta-worker role)
- LLM provider keys rotated when `provider_registry` detects compromise signals
- KEKs rotated yearly (§12X.11 config)

Dev mode:
- Local vault via Docker compose with dev-only fixtures
- Same code path as prod (no `if env == "dev": use env vars` branches)

### 12AA.8 Layer 7 — Event Authenticity (async flows)

Outbox schema extension (§12F):

```sql
ALTER TABLE outbox
  ADD COLUMN signed_by_svid_fingerprint BYTEA NOT NULL,
  ADD COLUMN signature                  BYTEA NOT NULL,
  ADD COLUMN signed_at                  TIMESTAMPTZ NOT NULL;
```

Signing (publisher side, §12F):
```
payload = SHA256(event_body || signed_by_svid_fingerprint || signed_at)
signature = Ed25519_sign(service_private_key, payload)
```
- Service private key fetched from vault per SVID rotation
- Every outbox row signed at insert time (inside outbox-writer transaction)
- Publisher verifies own signatures on read (detects in-flight tampering in DB)

Verification (event-handler / consumers):
- On consume from Redis stream, consumer fetches signer's public key from platform PKI (cached per SVID)
- Recomputes hash; verifies signature
- Mismatch → route to DLQ (§12F.2) + SRE alert (not silent drop)

Covers:
- Forged events if Redis ACL misconfigured
- Cross-service replay attacks (signed_at + freshness check)
- Event tampering in transit or at rest

### 12AA.9 Layer 8 — Network Egress Allowlist

Architecture:
- All services in private subnet
- No default internet egress
- NAT gateway per-service egress allowlist (enforced via security groups + route tables)

Per-service egress:
| Service | Allowed destinations |
|---|---|
| `api-gateway-bff` | internal services only |
| `roleplay-service` | LLM providers (per `provider_registry`), internal services |
| `knowledge-service` | embedding provider APIs (per config), internal services |
| `chat-service` | LLM providers (legacy), internal services |
| `book-service` | MinIO (S3 endpoint), internal services |
| `meta-worker` | internal services only (no internet) |
| `publisher` | internal services only |
| `auth-service` | internal services + optional SSO provider |
| `admin-cli` | internal services only |
| `migration-orchestrator` | internal services only |
| `audit_retention_cron` | internal services + MinIO (archive) |

Enforcement + monitoring:
- VPC flow logs capture all egress
- Destination outside per-service allowlist → `lw_egress_denied_total` metric + SRE PAGE
- DNS firewall blocks unknown domain lookups from services
- Review quarterly: allowlist changes + unexpected destination attempts

Only inbound entry: api-gateway-bff via CDN/ALB. All other services have no public IP.

### 12AA.10 Layer 9 — Service-to-Service Audit

Two tiers:

**General services** — structured logs + distributed tracing:
```json
{
  "ts": "2026-04-24T14:22:10.123Z",
  "caller_svid": "spiffe://loreweave.dev/service/book-service/prod",
  "callee_service": "glossary-service",
  "rpc": "/v1/glossary/lookup",
  "user_ref_id": "...",
  "trace_id": "otel-trace-abc123",
  "status": 200,
  "duration_ms": 45,
  "bytes_in": 312,
  "bytes_out": 1804
}
```
OpenTelemetry propagation: gateway injects `trace_id`; every service forwards. Gives end-to-end traces.

Retention: 90d (per §12X.8 app_logs).

**High-sensitivity services** (meta-worker, admin-cli, migration-orchestrator, audit_retention_cron):

```sql
CREATE TABLE service_to_service_audit (
  audit_id          UUID PRIMARY KEY,
  caller_svid       TEXT NOT NULL,
  callee_service    TEXT NOT NULL,
  rpc               TEXT NOT NULL,
  user_ref_id       UUID,
  admin_session_id  UUID,
  admin_impact_tier TEXT,
  trace_id          TEXT NOT NULL,
  status            INT NOT NULL,
  duration_ms       INT NOT NULL,
  break_glass       BOOLEAN NOT NULL DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON service_to_service_audit (caller_svid, created_at DESC);
CREATE INDEX ON service_to_service_audit (user_ref_id, created_at DESC) WHERE user_ref_id IS NOT NULL;
CREATE INDEX ON service_to_service_audit (admin_session_id) WHERE admin_session_id IS NOT NULL;
CREATE INDEX ON service_to_service_audit (created_at DESC) WHERE break_glass = true;
```

Retention: **5 years** (aligns with §12T.5 meta_write_audit). Table lives in meta DB. No raw payload (event body audit lives elsewhere).

PII classification: `low` — contains user_ref_id but no content; aligns with §12X.3 contract.

Anomaly detection:
- Unexpected `(caller, callee, rpc)` combination → SRE alert
- Sudden volume spike from single caller → investigate
- Break-glass session activity logged in dedicated view for on-call review

### 12AA.11 Layer 10 — Dev/Staging/Prod Parity + Break-Glass

**Parity**:

All three environments use:
- SPIFFE-like SVIDs (dev uses dev-CA)
- Vault (dev uses local Docker compose vault with fixture secrets)
- ACL matrix (same file, same enforcement)
- mTLS V1+30d (dev certs short-lived too)

"No auth locally" = forbidden. Parity bug hunts are hours; this rule buys years of debugging time back.

Dev differences (parity preserved, knobs relaxed):
- SVID TTL 24h (vs 1h for high-sensitivity prod)
- Vault secrets are fixtures, not real
- PKI is dev-CA, rotated daily
- NAT egress allowlist may be wider (includes dev proxy)
- Audit retention shorter (30d)

**Break-glass emergency access**:

Endpoint: `POST /admin/break-glass` on auth-service
- Requires: Tier 1 dual-actor (S5) + 100+ char incident reason + incident ticket ID
- Issues: 24h TTL admin JWT with `break_glass=true` claim
- Every RPC while `break_glass=true`:
  - Logged to `admin_action_audit` (standard)
  - Logged to `service_to_service_audit` with `break_glass=true` flag (dedicated column for filter)
  - Emits SLACK + PAGE notification to on-call security (visibility)
- Post-use mandate:
  - Rotate any credentials touched during break-glass (tracked via session_id → touched_paths query)
  - Incident postmortem within 7 days (governance; tracked in R13 §7 quarterly review)

No permanent backdoor accounts. Break-glass always time-bounded. Missing postmortem → audit-review flag.

### 12AA.12 Interactions + V1 split + what this resolves

**Interactions**:

| With | Interaction |
|---|---|
| §12T.8 (S4) | App-layer SVID + DB role must match; vault binds SVID → DB credential (service X can't fetch service Y's DB creds) |
| §12U (S5) | Admin JWT carries `admin_impact_tier` + `admin_second_approver`; auth-service enforces Tier 1 flow before JWT issuance |
| §12X (S8) | meta-worker `user.erased` fan-out events signed (L7); consumers verify; audit ties admin_session_id → erasure action |
| §12F (R6) | Outbox schema extended with `signed_by_svid_fingerprint` + `signature`; publisher is signer; event-handler verifies |
| §12Y (S9) | `prompt_audit.caller_svid` made explicit (was implicit); trace_id propagation gives end-to-end visibility |
| §12Z (S10) | `admin/entity-provenance` timeline merges `service_to_service_audit` rows; break-glass highlighted in view |
| CLAUDE.md | Adds "Internal-mTLS invariant" (after V1+30d rollout) and "Service ACL invariant" alongside existing "Provider gateway invariant" |
| ADMIN_ACTION_POLICY | §R4 dangerous list: `admin/break-glass` added; §4 reject list: bypass ACL matrix + hardcoded service secrets |
| DF11 (Fleet + Lifecycle) | Service health dashboard includes SVID expiry monitoring + ACL denial rates |
| DF9 (per-reality ops) | Admin actions carry `admin_impact_tier` + `admin_session_id` in RPC headers |

**Accepted trade-offs**:

| Cost | Justification |
|---|---|
| SPIFFE/SVID infrastructure upfront | Without it, service-level trust is flat; blast radius unbounded |
| Vault dependency from V1 | Secret-management is not optional at 19+ services; worth the operational cost |
| mTLS sidecar complexity (V1+30d) | V1 JWT-SVID + LB-TLS is intermediate stage that gives 80% of value |
| 15-min admin JWT TTL | Short blast-radius window; operational overhead absorbed by silent refresh |
| Break-glass mandate is strict | Compensates for bypass power; missing postmortem flagged automatically |
| Parity rule "no auth locally" | Saves hours of debugging later |

**What this resolves**:

- ✅ **Flat-trust network** — SVIDs + ACL matrix make service identity cryptographic
- ✅ **Admin-cli impersonation** — only service with matching SVID + valid admin JWT can invoke admin endpoints
- ✅ **Event forgery** — L7 signing + verification; DLQ on mismatch
- ✅ **No RPC audit** — L9 logs + high-sensitivity audit table
- ✅ **Env-var secret leakage** — L6 vault eliminates shared secrets
- ✅ **Provider-registry credential leakage** — vault gates access; SVID-bound secret paths
- ✅ **Cross-reality fan-out authenticity** — L7 event signing
- ✅ **Confused deputy** — L4 explicit principal mode per RPC
- ✅ **Admin-vs-user indistinguishable** — L5 distinct JWT schema + claims
- ✅ **Dev/prod parity** — L10 parity rule + same code paths
- ✅ **Missing break-glass** — L10 defined + audited + time-bounded

**V1 / V1+30d / V2+ split**:
- **V1**: L1 JWT-SVID + attestation, L3 ACL matrix + CI lint, L4 explicit principal modes, L5 admin JWT claims, L6 vault (required), L8 private subnet + egress allowlist, L9 structured logs + `service_to_service_audit` (5y for high-sensitivity), L10 parity + break-glass
- **V1+30d**: L2 full mTLS (sidecar rollout), L7 event signing (after outbox stabilizes)
- **V2+**: ML anomaly on RPC patterns, automated incident runbook, service-level intention-vs-capability auditing, SPIRE self-host migration if needed

**Residuals (deferred)**:
- External integration auth (MCP servers, external webhooks) — separate design, likely **DF15**
- Multi-region cross-region service auth (V3+)
- Confidential computing (TEE) for meta-worker — research frontier
- User impersonation flow for admin (explicit `impersonation_of` claim) — V2+

