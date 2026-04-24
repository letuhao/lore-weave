<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S08_audit_pii_retention.md
byte_range: 262900-281465
sha256: 4c156a113fcc0637d7b87a0012228c2ac4b00bdfe561cbf7d84b16737ed60679
generated_by: scripts/chunk_doc.py
-->

## 12X. Audit Log PII + Retention — S8 Resolution (2026-04-24)

**Origin:** Security Review S8 — design has 8+ data stores holding user data with inconsistent retention and no unified erasure strategy. GDPR/CCPA right-to-erasure has no mechanism against immutable event SSOT. Free-text admin `reason` fields can leak PII. Application logs undefined. No consent ledger for legal basis.

### 12X.1 Threat model + compliance drivers

Concerns:
1. **Event immutability vs right-to-erasure** — SSOT events hold user content forever (bound to reality lifecycle R9 = up to 120d+ after close). Direct deletion breaks event sourcing guarantees.
2. **Free-text PII leakage** — admin `reason` (S5), exported chat logs, debug log lines can accidentally contain emails/phones/IPs.
3. **Application log pipeline undefined** — gateway, chat-service, knowledge-service stdout may emit prompt/response bodies to aggregation tools.
4. **New tables added blind** — no contract forces PII classification on migration authoring.
5. **Audit tables themselves are mutation targets** — §12T.4 REVOKE is strong, but append-only doesn't mean immutable; a compromised DB-superuser role could replay inserts. No tamper evidence.
6. **Retention matrix fragmented** — 2y, 5y, 30d, indefinite scattered across §12L, §12T, §12S, §12V; conflicts with GDPR minimization.
7. **Legal basis untracked** — BYOK telemetry, D2/D3 derivative analytics, E3 IP reuse all need consent recording; no store exists.
8. **Backup PII retention unbounded** — R4 tiered backups carry everything; encryption-at-rest alone doesn't satisfy erasure.

Compliance anchors (not certification — design intent):
- GDPR Art. 17 (erasure)
- GDPR Art. 30 (processing records = PII classification matrix)
- GDPR Art. 6 (lawful basis = consent ledger + per-store `legal_basis` tag)
- CCPA deletion rights (aligned with erasure runbook)
- Billing/tax retention (typically 7y — overrides erasure for financial records)

### 12X.2 Layer 1 — PII Registry + Crypto-Shred (canonical erasure mechanism)

**Pattern:** PII never lives inline. It lives in a per-user encrypted blob in the meta DB. Every store that would otherwise hold PII holds an opaque `user_ref_id` instead. Erasure = destroy the per-user KEK.

```sql
-- Meta DB (single registry across all realities)
CREATE TABLE pii_registry (
  user_ref_id      UUID PRIMARY KEY,                -- opaque, referenced everywhere
  kek_id           UUID NOT NULL,                   -- KMS key envelope
  encrypted_blob   BYTEA NOT NULL,                  -- AES-256-GCM(KEK, pii_blob_json)
  blob_schema_ver  INT NOT NULL DEFAULT 1,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_rotated_at  TIMESTAMPTZ,
  erased_at        TIMESTAMPTZ,                     -- set when KEK destroyed
  erased_by_ticket TEXT
);

-- pii_blob_json shape: {email, display_name, legal_name?, timezone?, verified_phone?}

CREATE TABLE pii_kek (
  kek_id       UUID PRIMARY KEY,
  user_ref_id  UUID NOT NULL REFERENCES pii_registry(user_ref_id),
  key_material BYTEA NOT NULL,                      -- ciphertext; plaintext only in KMS/HSM
  destroyed_at TIMESTAMPTZ                          -- crypto-shred marker
);
CREATE INDEX ON pii_kek (user_ref_id) WHERE destroyed_at IS NULL;
```

Per-reality `pc_identity_ref` maps PC records to `user_ref_id`. PC public name stays (canon integrity: other players' events reference that name). PII behind registry: email, legal name, IP, etc.

**Crypto-shred semantics:**
- `DELETE` is not used; `destroyed_at` is set on `pii_kek` row + KMS-side `ScheduleKeyDeletion` (30d)
- After destruction: `encrypted_blob` remains but is unreadable — satisfies erasure at the information-theoretic level, preserves structural integrity of events
- Backups still contain the blob but also can't read it (same KEK lost)

**Why not hard-delete events:** event sourcing requires events to reconstruct projections. Rewriting history breaks provenance guarantees + cross-session causality (§12G). Crypto-shred sidesteps this: structure stays, meaning is removed.

### 12X.3 Layer 2 — PII Classification Contract

Every new/altered table MUST declare classification in its migration metadata:

```sql
-- Example migration header (enforced by CI lint)
-- @pii_sensitivity: high
-- @retention_class: events_lifecycle
-- @erasure_method: crypto_shred
-- @legal_basis: contract
-- @notes: Stores user-authored chat content; opaque via user_ref_id.
CREATE TABLE ...
```

Valid values:
- `pii_sensitivity`: `none | low | medium | high`
- `retention_class`: enumerated in §12X.4 matrix
- `erasure_method`: `crypto_shred | tombstone | hard_delete | retain_pseudonymized | retain_legal`
- `legal_basis`: `contract | consent | legitimate_interest | legal_obligation | vital_interest`

CI lint tool: `./scripts/pii-classify-lint.sh` runs on every migration PR; missing tags fail the build. Governance amendment to ADMIN_ACTION_POLICY will note this as a code-review reject condition.

Central registry file: `contracts/pii/tables_classification.yaml` — generated from migration headers; serves as living Art. 30 processing record.

### 12X.4 Layer 3 — Unified Retention Tier Matrix

Supersedes scattered retention rules. Authoritative single source of truth:

| retention_class | Store examples | Hot retention | Cold/archive | Erasure method | Legal basis |
|---|---|---|---|---|---|
| `events_lifecycle` | `events` (privacy=normal) | reality lifecycle (R9) | archived sever point | crypto-shred | Contract |
| `events_sensitive` | `events` (privacy=sensitive) | 30d hot | severed to archive | crypto-shred | Contract + minimization |
| `events_confidential` | `events` (privacy=confidential) | 7d hot | purged at lifecycle | crypto-shred | Contract + minimization |
| `admin_audit` | `admin_action_audit` | 2y (7y regulated) | — | crypto-shred actor + reason scrub | Legitimate interest |
| `meta_write_audit` | `meta_write_audit` | 5y | — | crypto-shred actor | Legitimate interest |
| `meta_read_audit` | `meta_read_audit` | 2y | — | crypto-shred actor | Legitimate interest |
| `billing_ledger` | `user_cost_ledger` | **7y** (revised from 2y) | — | pseudonymize at 2y | Legal obligation |
| `ops_metrics` | `user_queue_metrics` | 90d rolling | — | hard-delete | Legitimate interest |
| `memory_projection` | `npc_session_memory` | reality lifecycle | — | crypto-shred | Contract |
| `app_logs` | stdout → aggregator | **30d** | — | ingest-scrub + hard-delete | Legitimate interest |
| `backups` | R4 tiered | 7/14/30d (per R4) | — | natural expiry | Legitimate interest |
| `consent_ledger` | `user_consent_ledger` | retain while account active + 2y | — | retain_legal | Legal obligation |

**Note on S6 conflict resolution:** §12V.L6 originally stated `user_cost_ledger` retention 2y. S8 raises to 7y because tax/billing record keeping is a legal obligation that overrides the 2y default. Post-2y rows pseudonymize: `user_ref_id` replaced with a one-way hash that preserves aggregation for business analytics but cannot be joined back to identity. Update §12V.L6 accordingly.

**Note on S3 alignment:** §12S.3 already specifies 30d/7d hot for sensitive/confidential privacy. S8 restates these in the unified matrix and adds the crypto-shred mechanism that was implicit.

### 12X.5 Layer 4 — Free-text PII Scrubber

All free-text sink fields pass through a scrubber at write time:

```go
// contracts/pii/scrubber.go
type ScrubResult struct {
    Cleaned       string
    FoundPII      []PIIKind   // email, phone, ip_v4, ip_v6, cc, ssn, generic_id
    ScrubVersion  string       // semver; enables re-scrub when patterns improve
    ScrubbedAt    time.Time
}

func Scrub(raw string) ScrubResult { ... }
```

Fields protected:
- `admin_action_audit.reason`
- `admin_action_audit.error_detail`
- `meta_write_audit.notes` (when present)
- `user_consent_ledger.consent_context`
- Any exported chat transcripts (outside hot events path)
- Any new free-text field on classified tables

Storage pattern:
```sql
ALTER TABLE admin_action_audit
  ADD COLUMN reason_raw_hash BYTEA,              -- for potential legal audit recovery
  ADD COLUMN reason_scrubbed TEXT NOT NULL,
  ADD COLUMN scrub_version TEXT NOT NULL,
  ADD COLUMN scrubbed_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Drop raw column after migration verification
```

**Re-scrub:** when patterns improve (v1.1, v1.2, ...), a backfill job can re-scrub existing rows using `reason_raw_hash` for integrity check (never to recover raw text — hash is one-way).

Scrubber is regex-based V1 (email/phone/IP/CC patterns); ML-based detection is V2+. Baseline regex set sufficient for most accidental PII leakage.

### 12X.6 Layer 5 — Right-to-Erasure Runbook (`admin/user-erasure`)

New admin command, S5 **Tier 1 destructive** (dual-actor + 100+ char reason + 24h cooldown):

```
admin user-erasure \
  --user-ref-id=<uuid> \
  --ticket=<support_ticket_id> \
  --reason="<100+ char justification, scrubbed>" \
  --dry-run  # mandatory preview first
```

Execution steps (all through MetaWrite per §12T.2):
1. **Validate legal basis** — user self-request OR court order OR DPA-approved deletion
2. **Pre-checks** — balance must be zero on open billing (legal_obligation overrides; user notified)
3. **Crypto-shred KEK** — `pii_kek.destroyed_at = now()` + KMS `ScheduleKeyDeletion(30d)`
4. **Tombstone PC records** per-reality — display name → `[erased]`, preserve structural ID for canon
5. **Emit `user.erased` compensating event** — cross-reality fan-out via meta-worker; downstream services freeze any processing gated on consent
6. **Mark `user_cost_ledger` pseudonymize flag** — triggered later by retention cron at 2y mark (billing_ledger tier)
7. **Mark `user_consent_ledger` revoked_at** — for all active scopes
8. **Log full runbook execution** in `admin_action_audit` (reason auto-scrubbed per L4)
9. **Send confirmation** to user's last known email within 72h
10. **Full-erasure certificate** issued at 30d (after backup expiry + KMS key destruction)

**SLA:**
- Immediate effect: within 1h, reads returning PII surface redacted display; consent revocation propagated
- Full erasure: 30 days (bounded by R4 longest backup retention + KMS destruction window)

**Non-erasable residuals (documented to user):**
- `user_ref_id` persists as opaque key — required to prevent double-enrollment fraud
- Billing ledger retained 7y, pseudonymized at 2y
- Event structural records retained (canon integrity); content unreadable post-crypto-shred

**What happens if user returns:** fresh signup with new `user_ref_id`. Old `user_ref_id` stays erased. Platform can correlate only via new fraud-prevention signals (device, payment), not PII.

### 12X.7 Layer 6 — Audit Tamper Evidence (V1+30d)

Hash chain layered on §12T.4 REVOKE-based append-only. For each audit table (`admin_action_audit`, `meta_write_audit`, `meta_read_audit`, `user_consent_ledger`):

```sql
ALTER TABLE admin_action_audit
  ADD COLUMN prev_row_hash BYTEA,                    -- hash of previous row (by write order)
  ADD COLUMN this_row_hash BYTEA NOT NULL;           -- hash of this row's canonicalized content + prev_row_hash
```

- Writes (via MetaWrite helper) compute `this_row_hash = SHA256(canonical(row) || prev_row_hash)`
- Trigger `BEFORE INSERT` enforces the chain — out-of-order writes or retroactive insertion break the chain
- Daily Merkle root published to append-only object store: `s3://loreweave-audit-roots/<yyyy-mm-dd>/merkle-root.txt` + SNS notification
- SRE job compares: latest chain tip vs published root; mismatch → PAGE + forensics

**Why V1+30d, not V1:** adds operational complexity (trigger overhead ~5%, Merkle cron, object-store pipeline). §12T.4 REVOKE is adequate for V1 launch; hash chain is defense-in-depth layer. Flip to V1 if early threat modeling reveals higher adversary tier.

### 12X.8 Layer 7 — Structured Logging + Ingest Scrubber (V1)

New shared library `pkg/logging/` (Go) + equivalent in Python (`src/loreweave/logging/`):

```go
log.Info("session.turn.submitted",
    log.String("session_id", sid),
    log.PII("user_email", email),              // auto-masked in prod; hashed in dev
    log.Sensitive("prompt_body", body),        // dropped entirely at INFO level
)
```

Field tags:
- `log.PII(...)` — emitted as `***@***.***` pattern or opaque hash in prod
- `log.Sensitive(...)` — dropped at INFO; visible at DEBUG only in dev builds (forbidden in prod image)
- `log.Normal(...)` — no redaction

Prod logging rules:
- No stdout emission of chat content / prompt / response bodies — ever
- Request/response middleware logs request ID + user_ref_id + endpoint + duration + status — nothing more at INFO
- DEBUG logs disabled in prod builds (compile-time guard)

Ingest layer (for belt-and-suspenders against misbehaving third-party libs):
- Log aggregator pipeline (Vector/Fluent Bit) runs regex scrubber on every line before indexing
- Scrubber uses same L4 patterns; drops lines exceeding configured PII density

Retention: **30 days** in hot log store; no archive. Logs are debugging evidence, not compliance evidence. Compliance evidence lives in audit tables.

### 12X.9 Layer 8 — Consent Ledger

```sql
CREATE TABLE user_consent_ledger (
  user_ref_id          UUID NOT NULL,
  consent_scope        TEXT NOT NULL,           -- see scope enum below
  scope_version        TEXT NOT NULL,           -- e.g., privacy_policy_v3.2
  granted_at           TIMESTAMPTZ NOT NULL,
  revoked_at           TIMESTAMPTZ,
  grant_context        TEXT,                    -- scrubbed; signup flow, settings UI, etc.
  PRIMARY KEY (user_ref_id, consent_scope, scope_version)
);
CREATE INDEX ON user_consent_ledger (user_ref_id) WHERE revoked_at IS NULL;
```

Scope enum (V1):
- `core_service` — required; account operation. Revocation = account closure.
- `byok_telemetry` — opt-in; BYOK call metadata for cost modeling.
- `derivative_analytics` — opt-in; anonymized aggregates for D2/D3 tier refinement.
- `ip_derivative_use` — opt-in; E3-related. Default OFF until DF3 ships.
- `cross_reality_aggregation` — V2+; opt-in.
- `marketing_comms` — opt-in; unrelated to platform but tracked here for consistency.

Grant/revoke flow:
- Grant: UI event → MetaWrite → insert row
- Revoke: UI or API → MetaWrite → set `revoked_at` + emit `user.consent_revoked` event (meta-worker fans to services)
- Downstream services MUST check `user_consent_ledger` (cached 5 min) before processing consent-gated data; miss = deny

ToS / Privacy Policy version bump requires re-consent for non-core scopes (session interrupt: banner + modal). Re-consent = insert new row with new `scope_version`; old row stays for audit.

### 12X.10 Interactions with existing mechanisms

| With | Interaction |
|---|---|
| §12S.3 privacy tiers (S3) | Privacy levels already set 30d/7d retention for sensitive/confidential; S8 unifies with matrix + adds crypto-shred erasure mechanism |
| §12T MetaWrite (S4) | `pii_registry`, `user_consent_ledger`, `pii_kek` writes go through MetaWrite; hash chain (L6) augments §12T.4 REVOKE |
| §12U admin tiers (S5) | `admin/user-erasure` is Tier 1 destructive; reason scrubber (L4) applies to all admin reason fields |
| §12V cost controls (S6) | `user_cost_ledger` retention conflict resolved → 7y with 2y pseudonymize; this doc is authoritative |
| §12I reality closure (R9) | Reality closure ≠ user erasure; closure is reality-scoped, erasure is user-scoped across realities. User can request erasure mid-reality-life; other players' events reference `[erased]` PC |
| §12D backup (R4) | Backup retention already 7/14/30d; crypto-shred inherently handles backup erasure (KEK lost = backup unreadable) |
| Canon model (03 §3) | PC display name `[erased]` preserves canon narratively (in-universe: "the person who cannot be remembered"); DF14 mystery hooks can leverage this |

### 12X.11 Config consolidated

```
# §12X.2 PII Registry
pii.kek.rotation_interval_days = 365
pii.kek.destruction_grace_period_days = 30

# §12X.4 Retention (unified)
retention.billing_ledger_years = 7
retention.billing_ledger_pseudonymize_at_years = 2
retention.app_logs_days = 30
retention.consent_ledger_post_account_years = 2

# §12X.5 Scrubber
scrubber.patterns_version = "v1.0"
scrubber.regex_set = ["email", "phone", "ipv4", "ipv6", "cc_pan", "ssn_us", "api_key_like"]

# §12X.6 Erasure
erasure.confirmation_email_hours = 72
erasure.full_cert_issue_days = 30
erasure.billing_zero_balance_required = true

# §12X.7 Audit hash chain
audit_chain.enabled = false                              # V1
audit_chain.merkle_publish_target = "s3://loreweave-audit-roots"
audit_chain.publish_cron = "0 4 * * *"                   # daily 04:00 UTC

# §12X.8 Logging
log.prod.debug_enabled = false
log.ingest.scrubber_enabled = true
log.retention_days = 30

# §12X.9 Consent
consent.reverify_on_policy_version_bump = true
consent.cache_ttl_minutes = 5
```

### 12X.12 What this resolves

- ✅ **Right-to-erasure mechanism** — crypto-shred pattern works against immutable events
- ✅ **Retention matrix unified** — single source of truth, replaces scattered rules
- ✅ **Free-text PII accidents** — scrubber + re-scrub capability
- ✅ **Log pipeline PII** — structured library + ingest scrubber
- ✅ **Legal basis tracking** — consent ledger + `legal_basis` tag per store
- ✅ **Backup erasure** — crypto-shred makes backup encryption erasure meaningful
- ✅ **Audit tamper evidence** — hash chain V1+30d defense-in-depth
- ✅ **New-table PII blind spot** — classification contract + CI lint

**Deferred (V2+):**
- ML-based PII detection beyond regex
- Differential privacy for D2/D3 aggregated analytics
- Per-region data residency (EU+US hybrid hosting)
- Zero-knowledge audit proofs (replace hash chain)
- Formal SOC2/ISO-27001 control mapping (governance track)

**Residuals (accepted):**
- Crypto-shred leaves ciphertext in place forever; satisfies erasure informationally but isn't "zero on disk"
- `user_ref_id` persists post-erasure (opaque); required for fraud prevention
- Billing retention overrides erasure for 7y (legal obligation)

