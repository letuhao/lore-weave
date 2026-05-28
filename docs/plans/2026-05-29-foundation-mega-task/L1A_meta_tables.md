# L1.A — Meta Registry Tables (deep enumeration)

> **Parent:** [L1_db_physical_meta.md](L1_db_physical_meta.md)
> **Depth target:** B (artifact-level) — purpose + key columns + retention + write/read services + events + risks + kernel chunk reference
> **Reading instruction for RAID agents:** This file enumerates WHAT tables exist.
> For full DDL/CHECK constraints/indexes/grants, read the linked kernel chunk per row.
>
> **3 LOCKED decisions 2026-05-29** (see §7):
> - Q-L1A-1: `session_cost_tracking` = **per-reality DB** (live writes) + `session_cost_summary` in meta (60s rollup)
> - Q-L1A-2: `canon_entries`, `canonization_audit`, `book_authorship`, `canon_change_log` = **glossary-service's `glossary` DB** (NOT meta). Service map line 71 amendment required.
> - Q-L1A-3: `service_to_service_audit` = **full audit from V1**, no sampling.

---

## §0. Authoritative retention matrix (S08 §12X.4)

| Retention class | Hot | Cold/Archive | Erasure method | Legal basis |
|---|---|---|---|---|
| `events_lifecycle` | reality lifecycle (R9) | severed → archive | crypto-shred | Contract |
| `events_sensitive` | 30d hot | severed → archive | crypto-shred | Contract + minimization |
| `events_confidential` | 7d hot | purged at lifecycle | crypto-shred | Contract + minimization |
| `admin_audit` | 2y (7y regulated) | — | crypto-shred actor + reason scrub | Legitimate interest |
| `meta_write_audit` | 5y | — | crypto-shred actor | Legitimate interest |
| `meta_read_audit` | 2y | — | crypto-shred actor | Legitimate interest |
| `billing_ledger` | **7y** | — | pseudonymize at 2y | Legal obligation |
| `ops_metrics` | 90d rolling | — | hard-delete | Legitimate interest |
| `memory_projection` | reality lifecycle | — | crypto-shred | Contract |
| `app_logs` | **30d** | — | ingest-scrub + hard-delete | Legitimate interest |
| `backups` | 7/14/30d (per R4) | — | natural expiry | Legitimate interest |
| `consent_ledger` | retain while active + 2y | — | retain_legal | Legal obligation |

---

## §1. Reality routing + lifecycle group

### 1.1 `reality_registry` — primary routing table

- **Purpose:** maps `reality_id` → physical Postgres DB, status, owner, deploy cohort, session caps, locale
- **Owning chunks:** R04 §12D + S04 §12T.3 (CHECK constraints) + R09 §12I.2 (close-state columns) + SR05 §12AH.4 (`deploy_cohort`)
- **Key columns:**
  - `reality_id UUID PK`
  - `db_host TEXT` (CHECK: `^pg-shard-[0-9]+\.(internal|prod|staging)$`)
  - `db_name TEXT`
  - `status TEXT` (CHECK: enum of 10 values `provisioning|seeding|active|pending_close|frozen|migrating|archived|archived_verified|soft_deleted|dropped`)
  - `locale TEXT` (CHECK: `^[a-z]{2}(-[A-Z]{2})?$`)
  - `session_max_pcs INT` (CHECK: 1..50), `session_max_npcs INT` (CHECK: 0..50), `session_max_total INT` (CHECK: 2..100)
  - `status_transition_at TIMESTAMPTZ`
  - `close_initiated_by UUID`, `close_initiated_at TIMESTAMPTZ`, `close_reason TEXT`
  - `archive_verified_at TIMESTAMPTZ`, `archive_verification_id UUID`
  - `soft_delete_name TEXT`, `drop_scheduled_at TIMESTAMPTZ`, `drop_approved_by UUID`, `drop_approved_at TIMESTAMPTZ`
  - `deploy_cohort INT` (hash(reality_id) % 100; stable for canary rollout, SR05)
  - `last_stats_updated_at TIMESTAMPTZ`
- **Indexes:** PK; index on `db_host`, `status`, `deploy_cohort`; partial index on `WHERE status='active'`
- **Retention:** until row reaches `dropped` final state (~120d minimum, R9 §12I.1 6-state machine)
- **Written by:** `world-service` (lifecycle transitions, all via `AttemptStateTransition()`), `migration-orchestrator` (migration fields via `MetaWrite()`)
- **Read by:** ALL services (routing hot path; cached 30s in Redis per C03 §12O.6)
- **Events:** `reality.created`, `reality.status.<state>` (one per transition)
- **Risk:** **routing redirect attack** (flip `db_host` → all traffic to attacker shard) — S4 §12T.7 alert `lw_meta_routing_db_host_changes_total` PAGE if change without matching `migrating` state

### 1.2 `instance_schema_migrations` — per-DB migration tracker

- **Purpose:** which schema migration set has been applied to each per-reality DB
- **Owning chunk:** R04-L2 §12D.2
- **Key columns:** `reality_id UUID`, `migration_id TEXT`, `applied_at TIMESTAMPTZ`, `applied_by TEXT`, `failure_reason TEXT NULL`
- **PK:** `(reality_id, migration_id)`
- **Retention:** Operational (no expiry — historical record)
- **Written by:** `migration-orchestrator`
- **Read by:** `migration-orchestrator` (planning), `world-service` (verification on reality boot)
- **Events:** none (orchestrator owns its state internally)
- **Risk:** missing rows → wrong-version schema; orphan scanner (R04 §12D.7) reconciles

### 1.3 `publisher_heartbeats` — outbox publisher liveness

- **Purpose:** tracks active publisher replicas + their partition assignments; missing heartbeat = dead publisher
- **Owning chunk:** R06 §12F.3
- **Key columns:** `publisher_id TEXT PK`, `shard_host TEXT`, `assigned_ranges JSONB`, `last_heartbeat_at TIMESTAMPTZ`, `status TEXT` (`active|draining|dead`)
- **Indexes:** `(shard_host, last_heartbeat_at)`
- **Retention:** Ephemeral (24h rolling; old `dead` rows cleaned)
- **Written by:** `publisher` (own heartbeat), `meta-worker` (mark `dead` on no-heartbeat detection)
- **Read by:** `meta-worker` (leader election), SRE dashboard
- **Events:** none (heartbeat = direct table write)
- **Risk:** missed heartbeat detection → leader election delay; alert `lw_publisher_lag_seconds`

### 1.4 `lifecycle_transition_audit` — every reality status transition

- **Purpose:** audit every attempted state transition on `reality_registry.status` (success + concurrency conflict + invalid attempt)
- **Owning chunk:** C05 §12Q.4
- **Key columns:** `audit_id UUID PK`, `reality_id UUID`, `from_status TEXT`, `to_status TEXT`, `actor_id UUID`, `actor_type TEXT` (`owner|admin|system|cron`), `succeeded BOOLEAN`, `failure_reason TEXT` (`concurrent_modification|invalid_transition|...`), `payload JSONB`, `attempted_at TIMESTAMPTZ`
- **Indexes:** `(reality_id, attempted_at DESC)`, partial `(succeeded, attempted_at) WHERE succeeded=FALSE`
- **Retention:** `meta_write_audit` tier (5y) — see S04 §12T cross-ref
- **Written by:** `MetaWrite()` internal (via `AttemptStateTransition()` wrapper)
- **Read by:** SRE dashboard, conflict-heatmap dashboard (DF11)
- **Events:** none (audit-only)
- **Risk:** repeated `concurrent_modification` on same reality → hot race condition; metric `lw_lifecycle_transition_conflict_count`

### 1.5 `reality_close_audit` — close-lifecycle compliance trail

- **Purpose:** detailed audit of every R9 close transition (close_initiated, cancel, archive_completed, verified, soft_deleted, dropped) with full context
- **Owning chunk:** R09 §12I (full file, schema in §12I.x details)
- **Retention:** 7y compliance (`admin_audit` tier extended)
- **Written by:** `world-service` via `MetaWrite()` + `AttemptStateTransition()`
- **Events:** `reality.close.initiated`, `reality.close.cancelled`, `reality.archived`, `reality.verified`, `reality.soft_deleted`, `reality.dropped`
- **Risk:** missing rows = compliance gap; cross-check vs `lifecycle_transition_audit`
- **Open:** schema details — read R09 fully when building L1.A cycle

### 1.6 `archive_verification_log` — archive 5-step verification record

- **Purpose:** records each archive verification attempt (R9 hard gate before `archived → archived_verified`)
- **Owning chunk:** R09 §12I.3
- **Key columns:** `verification_id UUID PK`, `reality_id UUID`, `verifier_id TEXT`, `checks_passed JSONB`, `status TEXT` (`passed|failed|inconclusive`), `failure_reason TEXT`, `sample_size INT`, `temp_db_host TEXT`, `verified_at TIMESTAMPTZ`
- **Retention:** 7y compliance
- **Written by:** `world-service` (close flow)
- **Read by:** `world-service` (`AttemptStateTransition('archived' → 'archived_verified')` checks for `status='passed'` row)
- **Events:** `archive.verified`
- **Risk:** false-positive verification = data loss at drop; periodic restore-drill catches drift

### 1.7 `reality_migration_audit` — per-reality migration runs

- **Purpose:** detailed audit of each migration run per reality (start, attempts, success, failure_detail)
- **Owning chunks:** R04 §12D.2, SR05 §12AH (deploy classification)
- **Retention:** 1y
- **Written by:** `migration-orchestrator`
- **Read by:** SRE dashboard (migration progress board), DF11
- **Events:** `migration.applied`, `migration.failed`
- **Open:** schema details — read SR05 §12AH cycle

---

## §2. PII + identity group

### 2.1 `pii_registry` — encrypted user-PII envelope

- **Purpose:** canonical store for every user's PII (email, display_name, legal_name, timezone, verified_phone); referenced by opaque `user_ref_id` everywhere else
- **Owning chunk:** S08 §12X.2
- **Key columns:** `user_ref_id UUID PK`, `kek_id UUID`, `encrypted_blob BYTEA` (AES-256-GCM), `blob_schema_ver INT`, `created_at`, `last_rotated_at`, `erased_at TIMESTAMPTZ NULL`, `erased_by_ticket TEXT`
- **Retention:** forever (erasure via crypto-shred — KEK destroyed, blob remains unreadable)
- **Written by:** `auth-service` via `MetaWrite()`
- **Read by:** services with PII access need (rare — most code uses `user_ref_id` opaque)
- **Events:** `user.created`, `user.erased`
- **Risk:** PK rotation must keep `encrypted_blob` readable; KEK rotation atomically via §12X.11 config `pii.kek.rotation_interval_days = 365`

### 2.2 `pii_kek` — per-user Key Encryption Key envelope

- **Purpose:** holds the ciphertext KEK that encrypts the `pii_registry.encrypted_blob`; destroyed (crypto-shred) on user erasure
- **Owning chunk:** S08 §12X.2
- **Key columns:** `kek_id UUID PK`, `user_ref_id UUID FK`, `key_material BYTEA` (KMS ciphertext, plaintext only in KMS/HSM), `destroyed_at TIMESTAMPTZ NULL` (crypto-shred marker)
- **Indexes:** `(user_ref_id) WHERE destroyed_at IS NULL`
- **Retention:** forever (destroyed_at marker = erasure satisfied; row stays for audit)
- **Written by:** `auth-service` (creation), `admin-cli` (`admin/user-erasure` Tier 1 destructive)
- **Read by:** KMS adapter (decrypt path)
- **Events:** `user.erased` (when `destroyed_at` set)
- **Risk:** PII Sensitive — this is THE erasure mechanism; must integrate KMS `ScheduleKeyDeletion(30d)`

### 2.3 `user_consent_ledger` — GDPR Art. 6 legal-basis tracking

- **Purpose:** records grant + revoke of every consent scope per user (versioned by policy)
- **Owning chunk:** S08 §12X.9
- **Key columns:** `user_ref_id UUID`, `consent_scope TEXT`, `scope_version TEXT` (e.g., `privacy_policy_v3.2`), `granted_at TIMESTAMPTZ`, `revoked_at TIMESTAMPTZ NULL`, `grant_context TEXT` (scrubbed)
- **PK:** `(user_ref_id, consent_scope, scope_version)`
- **Indexes:** `(user_ref_id) WHERE revoked_at IS NULL`
- **Scope enum (V1):** `core_service|byok_telemetry|derivative_analytics|ip_derivative_use|cross_reality_aggregation|marketing_comms`
- **Retention:** `consent_ledger` tier — retain while account active + 2y
- **Written by:** `auth-service`, `world-service` (book authorship requires consent), `admin-cli` via `MetaWrite()`
- **Read by:** every service before processing consent-gated data (cached 5min per §12X.11)
- **Events:** `user.consent.granted`, `user.consent.revoked` (meta-worker fans to services)
- **Risk:** stale cache → process revoked-consent data; 5min TTL is acceptable bound

### 2.4 `player_character_index` — cross-reality PC lookup

- **Purpose:** user-facing PC index — which user owns which PCs across realities (for dashboard, fraud-prevention, cross-reality nav)
- **Owning chunks:** 04_player_character §A (PC-A1..A3) + S04 §12T.3 CHECK
- **Key columns (sketch):** `pc_index_id UUID PK`, `user_ref_id UUID`, `reality_id UUID`, `pc_id UUID` (per-reality), `pc_name TEXT`, `status TEXT` (CHECK: `active|offline|hidden|npc_converted|deceased|deleted`), `created_at`, `last_seen_at`
- **Retention:** Operational (until deleted)
- **Written by:** `world-service` via `MetaWrite()`
- **Read by:** `world-service` (PC lookup), gateway-BFF (dashboard), other PCs' prompt assembly
- **Events:** `pc.index.created`, `pc.index.status.*`
- **Risk:** **identity manipulation attack** (alter rows → impersonation, cross-user data leak) — S4 §12T.6 sensitive-read audit on non-owner queries
- **Open:** schema details — read 04_player_character/A_identity.md cycle

---

## §3. Audit group

### 3.1 `meta_write_audit` — universal meta-write audit (S04 L4)

- **Purpose:** records EVERY meta-table write via `MetaWrite()` helper — table, op, before+after row contents, actor, reason, request context
- **Owning chunk:** S04 §12T.5
- **Key columns:** `audit_id UUID PK`, `table_name TEXT`, `operation TEXT` (`INSERT|UPDATE|DELETE`), `row_pk JSONB`, `before_values JSONB`, `after_values JSONB`, `actor_type TEXT` (`admin|system|service|retention_cron`), `actor_id TEXT`, `reason TEXT`, `request_context JSONB`, `created_at`
- **Indexes:** `(table_name, created_at DESC)`, `(actor_id, created_at DESC)`, partial `(created_at) WHERE actor_type='admin'`
- **Retention:** **5y** (`meta_write_audit` tier in S08 matrix)
- **Append-only enforcement:** REVOKE UPDATE/DELETE from `app_service_role`, `app_admin_role` (S04 §12T.4)
- **Written by:** `MetaWrite()` internal (every call writes 1 row in same TX as the data write)
- **Read by:** SRE/forensics only (V1+30d adds anomaly detection — bulk reads, audit divergence)
- **Events:** none
- **Risk:** tamper resistance — V1 REVOKE-based; V2+ adds hash chain (S08 §12X.7) for tamper evidence

### 3.2 `meta_read_audit` — enumerated sensitive-path read audit (S04 L5)

- **Purpose:** records reads on enumerated sensitive paths only (NOT every read — performance-conscious)
- **Owning chunk:** S04 §12T.6
- **Key columns:** `audit_id UUID PK`, `query_type TEXT` (enum: `player_index_cross_user|audit_query|admin_bulk_export|...`), `parameters JSONB`, `actor_id TEXT`, `result_count INT`, `created_at`
- **Indexes:** `(actor_id, created_at DESC)`, `(query_type, created_at DESC)`
- **Sensitive-read enumeration (V1):** non-owner `player_character_index` lookup; queries on audit tables; bulk queries (LIMIT > 1000 or no WHERE filter); admin export commands
- **Retention:** 2y (`meta_read_audit` tier)
- **Written by:** instrumentation library wrapping enumerated query paths
- **Read by:** SRE/forensics, anomaly detector (bulk-read spike alert)
- **Risk:** enumeration list maintenance — quarterly security-team review

### 3.3 `admin_action_audit` — command-level admin audit (R13 L3)

- **Purpose:** every admin command run logged with parameters + result; complements meta_write_audit (which logs data-level writes)
- **Owning chunk:** R13 §12L.3
- **Key columns:** `audit_id UUID PK`, `command_name TEXT`, `command_version TEXT`, `actor_id UUID`, `reality_id UUID NULL`, `parameters JSONB`, `result JSONB` (`success|dry_run|error`), `error_detail TEXT`, `created_at`
- **Indexes:** `(actor_id, created_at)`, `(reality_id, created_at)`
- **Free-text fields:** `error_detail` MUST pass through S08 §12X.5 scrubber → split into `error_detail_raw_hash` + `error_detail_scrubbed` + `scrub_version` + `scrubbed_at`
- **Retention:** **2y** (R13 default), 7y if classed as regulated activity (configurable per command)
- **Written by:** `admin-cli` via `MetaWrite()`
- **Read by:** SRE/forensics, audit dashboard (DF11)
- **Events:** `admin.command.executed`
- **Risk:** missing rows from leaked admin token; correlate with meta_write_audit (S4 §12T.7 alert "admin_action_audit row without meta_write_audit companion → PAGE")

### 3.4 `service_to_service_audit` — inter-service RPC audit (S11)

- **Purpose:** every cross-service RPC logged for forensics + ACL compliance
- **Owning chunk:** S11 §12AA
- **Key columns (sketch):** `audit_id UUID PK`, `caller_service TEXT`, `callee_service TEXT`, `rpc_name TEXT`, `principal_mode TEXT` (`requires_user|system_only|either`), `user_ref_id UUID NULL`, `result TEXT`, `latency_ms INT`, `created_at`
- **Retention:** 5y
- **Written by:** entry middleware on every service (records inbound RPC)
- **Read by:** SRE/forensics
- **Risk:** cardinality — high volume. **LOCKED Q-L1A-3 2026-05-29:** full audit from V1 (no sampling). Capacity budget must be sized accordingly (I17). Estimate: at V3 (1K active realities × 100 RPC/turn × 100K turns/hour) → ~10M rows/day → ~2 TB/year. Partition by month + 5y retention = ~10 TB total. **Justifies dedicated audit DB cluster at V2+ per C03 §12O.10.**
- **Open:** schema details — read S11 §12AA cycle

### 3.5 `prompt_audit` — LLM prompt assembly audit

- **Purpose:** every `AssemblePrompt()` call records its context hash, template id/version, estimated cost, audit_id, rejected_refs — body NEVER stored (PII risk)
- **Owning chunk:** S09 §12Y
- **Key columns (sketch):** `audit_id UUID PK`, `prompt_context_hash BYTEA`, `template_id TEXT`, `template_version INT`, `intent TEXT`, `actor_user_ref_id UUID`, `reality_id UUID`, `session_id UUID NULL`, `estimated_cost_usd NUMERIC`, `rejected_refs JSONB`, `created_at`
- **Retention:** **90d hot / 2y cold** (S08 matrix)
- **Written by:** `contracts/prompt/` internal (every `AssemblePrompt()` call)
- **Read by:** incident replay tooling (reconstruct prompt from context hash + template version + audit_id)
- **Events:** none
- **Risk:** body must NEVER leak — strict separation enforced at lib level; `log.Sensitive()` enforced

---

## §4. Billing + cost + quota group

### 4.1 `user_cost_ledger` — per-user LLM cost tracking (7y legal)

- **Purpose:** every LLM call's cost recorded against user for billing + budget enforcement
- **Owning chunk:** S06 §12V (main S06 ledger spec)
- **Key columns (sketch):** `ledger_id UUID PK`, `user_ref_id UUID`, `reality_id UUID NULL`, `session_id UUID NULL`, `provider_id TEXT`, `model_id TEXT`, `prompt_tokens INT`, `completion_tokens INT`, `cost_usd NUMERIC`, `tier TEXT`, `created_at`
- **Retention:** **7y** (`billing_ledger` tier, S08-D3 override — legal/tax obligation); pseudonymize `user_ref_id` at 2y mark
- **Written by:** `usage-billing-service` (consumes `provider.call.completed` events)
- **Read by:** `usage-billing-service` (budget/cap), SRE dashboard
- **Events:** `billing.charge.*`, `billing.budget.alerted`
- **Risk:** pseudonymization correctness — one-way hash preserves aggregation, can't reverse-join to identity; CI lint validates
- **Open:** schema details — read S06 §12V.6 (ledger) cycle

### 4.2 `session_cost_tracking` — per-session budget enforcement (PER-REALITY DB — NOT META)

- **Purpose:** tracks cumulative cost per session against per-session cap (warn at 80%, hard-cap at 100%)
- **Owning chunk:** S06 §12V.3
- **Key columns:** `session_id UUID PK`, `reality_id UUID`, `user_id UUID`, `cap_usd NUMERIC(10,6)`, `spent_usd NUMERIC(10,6)`, `warned_at TIMESTAMPTZ NULL`, `capped_at TIMESTAMPTZ NULL`, `started_at`
- **Indexes:** `(user_id, started_at DESC)`
- **Retention:** until session end + 30d (analytics)
- **Written by:** `roleplay-service` (cost accumulator), `admin-cli` (S5 Griefing-tier admin override)
- **Read by:** `roleplay-service` (pre-turn budget check)
- **Events:** `billing.session.warned`, `billing.session.capped`
- **LOCKED Q-L1A-1 2026-05-29:** lives in **per-reality DB** (not meta). Session is scoped to one reality → natural fit. Reduces meta cardinality.
- **Rollup:** see §4.2b `session_cost_summary` (meta-side 60s rollup)

### 4.2b `session_cost_summary` — meta-side rollup (NEW — Q-L1A-1 resolution)

- **Purpose:** meta-side rollup of session cost for cross-reality user-level daily budget enforcement + admin overview
- **Owning chunk:** S06 §12V.3 + Q-L1A-1 resolution (this CLARIFY)
- **Key columns:** `session_id UUID PK`, `reality_id UUID`, `user_id UUID`, `spent_usd_rollup NUMERIC(10,6)`, `cap_usd NUMERIC(10,6)`, `status TEXT` (`active|warned|capped|ended`), `last_rollup_at TIMESTAMPTZ`
- **Indexes:** `(user_id, last_rollup_at DESC)`, `(status) WHERE status='active'`
- **Retention:** 30d post-session-end (matches per-reality)
- **Written by:** new `session-cost-rollup-worker` (drains per-reality `session_cost_tracking` every 60s via Redis Streams or direct DB poll) via `MetaWrite()`
- **Read by:** `roleplay-service` (cross-session daily check, via `user_daily_cost`), `admin-cli` (overview)
- **Events:** `billing.session.summary.updated`
- **Implementation note:** the rollup worker is a NEW service. Adds to service map. **Foundation must include it.**
- **Risk:** rollup lag → user briefly exceeds daily budget across realities; 60s is acceptable bound

### 4.3 `user_daily_cost` — per-user daily aggregate cap (V1+30d)

- **Purpose:** cross-session daily cost aggregate per user; cap enforcement aligned with D2-D3 margin
- **Owning chunk:** S06 §12V.4
- **Key columns:** `user_id UUID`, `date DATE`, `spent_usd NUMERIC(10,6)`, `cap_usd NUMERIC(10,6)`, `capped_at TIMESTAMPTZ NULL`
- **PK:** `(user_id, date)`
- **Retention:** `billing_ledger` tier (7y)
- **Written by:** `usage-billing-service` (rollup job)
- **Read by:** `roleplay-service` (pre-turn check), `admin-cli` (override)
- **Events:** `billing.daily.capped`
- **Implementation phase:** **V1+30d** (not V1 launch)

### 4.4 `user_queue_metrics` — NPC queue abuse metrics (S07)

- **Purpose:** tracks each user's queue-acceptance behavior (queues_joined, accepted, abandoned, declined); detects abuse patterns
- **Owning chunk:** S07 §12W.4
- **Key columns:** `user_id UUID PK`, `total_queues_joined INT`, `total_accepted INT`, `total_abandoned INT`, `total_declined INT`, `last_abandoned_at TIMESTAMPTZ`, `updated_at`
- **Retention:** `ops_metrics` tier (90d rolling)
- **Written by:** `world-service` (queue state machine)
- **Read by:** `world-service` (queue admission check), priority-decay calculator (V1+30d S07 L4)
- **Events:** none (counter only)
- **Risk:** abuse signal interpretation — `declined ≠ abandoned`; metric `acceptance_rate = accepted / (accepted + abandoned)`

---

## §5. Canon group — MOVED OUT OF META (Q-L1A-2 LOCKED 2026-05-29)

**LOCKED Q-L1A-2 2026-05-29:** `book_authorship`, `canon_entries`, `canonization_audit`, `canon_change_log` ALL live in **`glossary-service`'s `glossary` DB**, NOT `loreweave_meta`.

**Rationale:** S13-D4 strict (per-service DB owns its domain data). Service map line 71 is incorrect — must be amended in the foundation I3 invariant amendment PR.

**Service map amendments required (foundation deliverable):**
- Line 19 (`glossary-service`): change `glossary DB (glossary, lore, wiki_articles, wiki_revisions, wiki_suggestions)` → `glossary DB (glossary, lore, wiki_articles, wiki_revisions, wiki_suggestions, canon_entries, canonization_audit, book_authorship, canon_change_log)`
- Line 71 (loreweave_meta DB contains): remove `canon_entries + canonization_audit (S13)` row

**Implication for L5 inbound canon:** L5 push flow (meta-worker xreality.canon.*) now consumes events from glossary-service (via its outbox + publisher), not from a meta table. L5 push is RPC + event-driven, not table-poll.

**Implication for L4 SDK:** `AssemblePrompt()` `[WORLD_CANON]` reads from glossary-service via RPC (not direct meta read). Added latency mitigated by per-reality canon cache (written by meta-worker xreality consumer into per-reality DB canon projection).

**Tables that USED to be in this section (now in glossary DB, OUT of L1.A scope):**
- ~~`book_authorship`~~ → glossary DB. Spec lives in S13 §12AC.2; foundation cycle for glossary-service migration owns it.
- ~~`canon_entries`~~ → glossary DB. Spec in S13 §12AC.5.
- ~~`canonization_audit`~~ → glossary DB. Spec in S13 §12AC.4.
- ~~`canon_change_log`~~ → glossary DB. Spec in M4 (multiverse §9.8).

**Foundation responsibility for canon:** L5 inbound canon ingestion contracts (push/pull/seed) — see [L5_inbound_canon.md] when written. Glossary-service must add outbox emission of `canon.change.*` events; meta-worker consumes `xreality.canon.*`. No new meta tables required.

---

## §6. SRE group

### 6.1 `incidents` — incident lifecycle tracker (SR2)

- **Purpose:** authoritative record of every incident with severity, IC, timeline, postmortem reference
- **Owning chunk:** SR02 §12AE
- **Key columns (sketch):** `incident_id UUID PK`, `severity TEXT` (`SEV0|SEV1|SEV2|SEV3`), `severity_history JSONB` (auto-escalation trail), `declared_at TIMESTAMPTZ`, `triaged_at TIMESTAMPTZ NULL`, `mitigated_at TIMESTAMPTZ NULL`, `resolved_at TIMESTAMPTZ NULL`, `postmortem_due_at TIMESTAMPTZ NULL`, `incident_commander TEXT`, `affected_services TEXT[]`, `status TEXT` (`declared|triaged|mitigated|resolved|postmortem|closed`)
- **Lifecycle states (SR2):** `declared → triaged → mitigated → resolved → postmortem → closed` (via `AttemptStateTransition()`)
- **Retention:** **7y** (compliance)
- **Written by:** SRE on-call via `admin-cli`, alert engine (auto-declare on SEV0 conditions per SR2 §12AE.2)
- **Read by:** SRE dashboard, postmortem tooling, GDPR Art. 33 breach-notification flow
- **Events:** `incident.declared`, `incident.severity.changed`, `incident.<state>` per transition
- **Risk:** missing postmortem on SEV0/SEV1 = governance gap; alert if SEV0 closes without postmortem ref

### 6.2 `feature_flags` — runtime toggle store (SR5 L4)

- **Purpose:** central runtime toggles with scope targeting (global, reality, user, cohort, tier)
- **Owning chunk:** SR05 §12AH.4
- **Key columns:** `flag_name TEXT PK`, `description TEXT`, `default_enabled BOOLEAN`, `target_scope TEXT`, `enabled_realities UUID[]`, `enabled_users UUID[]`, `enabled_cohorts INT[]`, `enabled_tiers TEXT[]`, `owner UUID`, plus expiry/audit fields (TBD per SR05 deeper)
- **Retention:** Operational
- **Written by:** `admin-cli` via `MetaWrite()`
- **Read by:** all services (cached locally with TTL)
- **Events:** `feature_flag.created`, `feature_flag.toggled`
- **Risk:** flag-explosion drift; SR05 ages stale flags

### 6.3 `deploy_audit` — every deploy logged (SR5)

- **Purpose:** records every deploy with class, services, migration ids, canary stage progress, rollback events
- **Owning chunk:** SR05 §12AH
- **Key columns (sketch):** `deploy_id UUID PK`, `class TEXT` (`patch|minor|major|emergency`), `services_touched TEXT[]`, `migration_ids TEXT[]`, `canary_stage INT`, `canary_history JSONB`, `rolled_back BOOLEAN`, `rollback_reason TEXT`, `triggered_by UUID`, `created_at`
- **Retention:** 1y
- **Written by:** deploy pipeline + canary controller via `MetaWrite()`
- **Read by:** SRE dashboard ("which deploy caused this?" SR5 problem 8)
- **Events:** `deploy.started`, `deploy.canary.advanced`, `deploy.completed`, `deploy.rolled_back`
- **Open:** schema details — read SR05 §12AH.6 cycle

### 6.4 `shard_utilization` — Postgres shard live metrics (SR8)

- **Purpose:** per-shard utilization snapshots (current_db_count, total_storage_bytes, cpu_load_pct, connection_count)
- **Owning chunk:** SR08 §12AK
- **Retention:** Operational (90d rolling)
- **Written by:** shard health agent (per-shard sidecar)
- **Read by:** capacity planner (allocation decisions), SRE dashboard
- **Events:** `shard.scaling.warning`, `shard.scaling.full`
- **Open:** schema details — read SR08 §12AK.2 cycle

### 6.5 `scaling_events` — capacity-action audit (SR8)

- **Purpose:** every scaling decision (allocation, rebalance, freeze) audited
- **Owning chunk:** SR08 §12AK
- **Retention:** 1y
- **Written by:** capacity planner via `MetaWrite()`, `admin-cli` (`admin/capacity-override`)
- **Risk:** capacity-override Tier 2 — 24h auto-expire (S5)

### 6.6 `dependency_events` — circuit breaker + retry audit (SR6 I8)

- **Purpose:** audit of breaker transitions, retry exhaustion, bulkhead rejections per (service, dep)
- **Owning chunk:** SR06 §12AI.3
- **Key columns (sketch):** `event_id UUID PK`, `service TEXT`, `dep_name TEXT`, `event_type TEXT` (`breaker.open|breaker.close|retry.exhausted|bulkhead.full`), `latency_p99_ms INT`, `error_rate_pct NUMERIC`, `created_at`
- **Retention:** 1y
- **Written by:** all services via `contracts/resilience/` lib
- **Read by:** SRE dashboard, alert engine
- **Events:** `dependency.breaker.<state>`
- **Open:** schema details — read SR06 §12AI cycle

### 6.7 `chaos_drills` — chaos engineering runs (SR7)

- **Purpose:** records every chaos drill (planned, executed, outcomes) — meta-evidence that runbooks work
- **Owning chunk:** SR07 §12AJ
- **Retention:** 1y
- **Written by:** chaos-engine via `MetaWrite()`
- **Events:** `chaos.drill.started`, `chaos.drill.completed`
- **Open:** schema details — read SR07 §12AJ cycle

### 6.8 `supply_chain_events` — CI supply-chain events (SR10)

- **Purpose:** records SBOM scans, hash-pin violations, dep upgrades, CI gate fails
- **Owning chunk:** SR10 §12AM
- **Retention:** 1y
- **Written by:** CI pipeline via `MetaWrite()`
- **Open:** schema details — read SR10 §12AM cycle

### 6.9 `alert_outcomes` — alert closure audit (SR9)

- **Purpose:** records resolution + actionability of every alert (true positive / false positive / noise)
- **Owning chunk:** SR09 §12AL
- **Retention:** 1y
- **Written by:** alert engine + on-call ack tooling via `MetaWrite()`

### 6.10 `alert_silences` — temporary alert silencing audit (SR9)

- **Purpose:** records every alert silence (silence_id, alert_pattern, scope, ttl, requested_by, reason)
- **Owning chunk:** SR09 §12AL
- **Retention:** Operational (silences expire)
- **Written by:** SRE via `admin-cli`

### 6.11 `turn_outcomes` — per-turn UX reliability tracking (SR11)

- **Purpose:** every player turn's outcome (success, timeout, error, retried) with latency breakdown
- **Owning chunk:** SR11 §12AN
- **Retention:** 30d hot / 1y cold
- **Written by:** `roleplay-service` (turn finalization)
- **Read by:** SRE dashboard (TurnState taxonomy), SLO calculator (SR1 SLI input)

### 6.12 `observability_budget_breaches` — cardinality/cost budget breaches (SR12 I19)

- **Purpose:** records metric cardinality budget breaches + audit growth drift detected by `pkg/metrics/` admission control
- **Owning chunk:** SR12 §12AO
- **Retention:** 1y
- **Written by:** metric library (`pkg/metrics/`) when admission control rejects a label
- **Read by:** SRE dashboard, `contracts/observability/inventory.yaml` reconciler
- **Events:** `obs.budget.breach`

---

## §7. Open questions — resolutions

| # | Question | Resolution | Status |
|---|---|---|---|
| Q-L1A-1 | `session_cost_tracking` placement: meta vs per-reality DB? | **Hybrid:** per-reality DB owns live writes; meta DB has `session_cost_summary` (60s rollup by new `session-cost-rollup-worker` service). | **LOCKED 2026-05-29** |
| Q-L1A-2 | `canon_entries` location — service map line 71 says meta; S13-D4 says glossary-service | **Glossary DB.** All 4 canon tables move OUT of meta. Service map must be amended (line 19 add canon tables, line 71 remove). L5 inbound canon = event-driven via glossary-service outbox. | **LOCKED 2026-05-29** |
| Q-L1A-3 | `service_to_service_audit` cardinality strategy | **Full audit from V1**, no sampling. Capacity budget (I17) sized accordingly. Estimate ~10 TB over 5y → dedicated audit DB cluster at V2+ (C03 §12O.10 trigger). | **LOCKED 2026-05-29** |
| Q-L1A-4 | `prompt_audit` body never stored — how does replay work? | Replay uses `prompt_context_hash` to re-derive prompt deterministically (S09 §12Y "L8 replay anchor") | Confirmed by S09 |
| Q-L1A-5 | Hash chain (S08 §12X.7) for tamper evidence — V1 or V1+30d? | V1+30d (S08 says trigger overhead ~5%, defer) | Confirmed by S08 |
| Q-L1A-6 | Total table count may grow during L4 (SDK) deep-dive when contracts/* surface their own audit tables | Accept; revisit L1.A at L4-close to add discovered tables | Process note |

**New deliverables from these locks:**
1. `session-cost-rollup-worker` Go service (Q-L1A-1) — adds to service map; goes in L1.D-adjacent or L2 outbox-aware variant
2. Service map amendment (Q-L1A-2) — line 19 + line 71 — part of I3 invariant amendment PR
3. Capacity budget entry for `service_to_service_audit` storage (Q-L1A-3) — sizes 5y retention bucket; admin DB split criteria at V2+

---

## §8. Per-table count by category (post-Q-L1A-2 lock)

| Category | Count | Notes |
|---|---|---|
| Reality routing + lifecycle | 7 | Unchanged |
| PII + identity | 4 | Unchanged |
| Audit | 5 | Unchanged |
| Billing + cost + quota | 5 | **+1** `session_cost_summary` (Q-L1A-1 new rollup table) |
| Canon | **0 (moved to glossary DB)** | **−4** (Q-L1A-2 lock) |
| SRE | 12 | Unchanged |
| **Total in meta** | **33** | (was 36; Canon −4, Billing +1, net −3) |

(L4 deep-dive may add `instance_dependency_map`, `service_health_summary`, or similar — revisit at L4 close.)

---

## §9. Cycle-decomposition hint (do not lock yet)

For RAID cycle planning (after all layers done), L1.A alone is likely **3-4 cycles**:

| Mini-cycle | Tables | Why grouped |
|---|---|---|
| L1.A-1: Routing + lifecycle | reality_registry, instance_schema_migrations, publisher_heartbeats, lifecycle_transition_audit, reality_close_audit, archive_verification_log, reality_migration_audit | Together form the reality state machine |
| L1.A-2: PII + identity + consent | pii_registry, pii_kek, user_consent_ledger, player_character_index | Shared crypto-shred lifecycle |
| L1.A-3: Audit infrastructure | meta_write_audit, meta_read_audit, admin_action_audit, service_to_service_audit, prompt_audit | Audit tier — append-only enforcement + retention together |
| L1.A-4: Billing + SRE | user_cost_ledger, session_cost_summary, user_daily_cost, user_queue_metrics, incidents, feature_flags, deploy_audit, shard_utilization, scaling_events, dependency_events, chaos_drills, supply_chain_events, alert_outcomes, alert_silences, turn_outcomes, observability_budget_breaches | "Everything else"; large but mostly independent table-by-table |

**Note:** Canon tables (now glossary DB) are NOT a L1.A cycle. They become a `glossary-service` migration cycle in a subsequent program (out of foundation scope). Foundation owns only the **inbound canon contract** (L5).

---

## §10. Status

```
[x] L1.A — enumeration complete (36 tables at B-level depth)
[ ] L1.A — open questions resolved (6 items)
[ ] L1.B — Meta Access Library deep-dive
[ ] L1.C — Per-reality DB Provisioner deep-dive
[ ] L1.D — Migration Orchestrator Service deep-dive
[ ] L1.E — Meta HA Infrastructure deep-dive
[ ] L1.F — Meta Cache Layer deep-dive
[ ] L1.G — Pgbouncer deep-dive
[ ] L1.H — Tiered Backup deep-dive
[ ] L1.I — Per-DB Metrics deep-dive
[ ] L1.J — Degraded Mode deep-dive
[ ] L1.K — CI Lints deep-dive
[ ] L1.L — V1→V3 Capacity Gates deep-dive
```
