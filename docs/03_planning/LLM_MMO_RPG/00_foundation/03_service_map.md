# Service Map

> **19 services** across the LoreWeave monorepo. Split into "existing" (12, from CLAUDE.md §Architecture) and "LLM MMO RPG V1 new" (7, per SESSION_HANDOFF §2 "Services identified for V1"). Each row names the service's responsibility boundary + the data it owns + its event surface.

---

## Existing services (pre-MMO-RPG)

| Service | Lang | Owns (data) | Emits events | Consumes events | Responsibility |
|---|---|---|---|---|---|
| `api-gateway-bff` | TS / NestJS | (none — stateless) | `gateway.request.*` (audit only) | n/a | Sole external-traffic entry (I1). Auth termination, rate-limit, per-user context. |
| `auth-service` | Go / Chi | `auth` DB (users, sessions, JWTs, devices) | `auth.user.*`, `auth.session.*`, `auth.token.revoked` | n/a | Identity, JWT issuance, device registry, break-glass admin JWT. |
| `book-service` | Go / Chi | `books` DB (books, chapters, chunks) | `book.*`, `chapter.*`, `chunk.*` | `auth.user.deleted` | Book ingestion, chapterization, chunking for knowledge pipeline. |
| `sharing-service` | Go / Chi | `sharing` DB (visibility, ACLs) | `share.*`, `visibility.*` | `book.created`, `auth.user.deleted` | Book visibility rules (private/unlisted/public), per-user share grants. |
| `catalog-service` | Go / Chi | `catalog` DB (curated index) | `catalog.entry.*` | `book.published`, `share.made-public` | Public catalog for discoverable books. |
| `provider-registry-service` | Go / Chi | `provider_registry` DB (BYOK creds, model configs) | `provider.config.*` | `auth.user.deleted` | BYOK provider credentials, model name resolution (I12). S9 data-retention tier + trains-on-inputs flags live here. |
| `usage-billing-service` | Go / Chi | `billing` DB (usage meters, cost ledger) | `billing.charge.*`, `billing.budget.alerted` | `provider.call.completed` (every LLM call per S6), all `*.completed` usage signals | Metering + billing. Owns `user_cost_ledger` (S6-D6, 2y retention, pseudonymized at 2y per S8). |
| `translation-service` | Go / Chi | `translation` DB (jobs, cached translations) | `translation.*` | `chunk.created` | Translation pipeline orchestration. |
| `glossary-service` | Go / Chi | `glossary` DB (glossary, lore, wiki_articles, wiki_revisions, wiki_suggestions) | `glossary.*`, `wiki.*`, `canon.*` | `chunk.analyzed`, `canonization.proposed` (S13) | Glossary + wiki + **canon entries** (`canon_entries` + `canonization_audit` tables live here — S13-D4). Two-layer SSOT with knowledge-service (glossary = authored, knowledge = extracted). |
| `chat-service` | Python / FastAPI | `chat` DB (conversation histories) | `chat.message.*` | `provider.config.changed` | Cursor-style AI chat (non-MMO). Uses LiteLLM via I2 gateway. |
| `knowledge-service` | Python / FastAPI | `knowledge` DB (Postgres SSOT + Neo4j derived) | `knowledge.entity.*`, `knowledge.relation.*` | `chunk.analyzed`, `glossary.entity.*` | Knowledge graph + memory (planned). Fuzzy/semantic entity layer anchored to glossary via `glossary_entity_id` FK. |
| `video-gen-service` | Python / FastAPI | `video_gen` DB | `video.*` | `book.published` (trigger) | Video generation (skeleton). |

---

## LLM MMO RPG V1 new services

| Service | Size | Lang | Owns (data) | Emits events | Consumes events | Responsibility |
|---|---|---|---|---|---|---|
| `world-service` | Large | Go | `reality_registry` (shared meta) + per-reality DBs (reality lifecycle) | `reality.*`, `session.*` (session membership only), `canon.propagate.*` | `canon.promoted` (S13), `migration.*` | Reality lifecycle state machine (R9, 7 states); reality provisioning; session host; cross-reality canon propagation (M4). |
| `roleplay-service` | Large | Go | Per-reality event streams (session events, turn events) | `turn.*`, `npc.*`, `pc.*`, `session_participants.*` | `provider.config.changed`, `session.created`, `canon.propagated` | LLM orchestration per session; one command-processor per session (I6). Turn processing, intent classification (A5), dispatch (A5), injection defense (A6). |
| `publisher` | Small | Go | `events_outbox` (per-reality DB) | forwards to Redis Streams | `events_outbox` rows (drained) | Outbox-to-Redis publisher (I13). Claims `publisher_claims` rows; idempotent. |
| `meta-worker` | Small | Go | writes to `reality_registry` + fan-out tables | n/a (writes to meta, no events) | Redis Streams `xreality.*` (cross-reality propagation topics) | Sole cross-reality writer (I7). Aggregates xreality signals into meta-registry updates. |
| `event-handler` | Small | Go | (cross-session event routing state) | `session.inbound.*` (routes events into destination session) | Redis Streams `xsession.*` | Sole cross-session event writer (I6). Crosses the session concurrency boundary safely. |
| `migration-orchestrator` | Small | Go | `migration_runs` (meta), `reality_migration_audit` | `migration.*` | n/a (triggered by admin-cli) | Per-reality schema migrations (R4-L2, concurrency 10). 6-phase migration protocol (SR5). |
| `admin-cli` | Small | Go | (stateless; reads via meta + per-reality) | `admin.*` + writes to `admin_action_audit` | n/a | Canonical admin command library (R13-L1). Every command is named, versioned, dry-run-first, S5-impact-classified. |

---

## Service composition conventions

### External traffic
```
public client → api-gateway-bff → <domain service>
```
Nothing else accepts inbound public traffic (I1). WebSocket upgrade and ticket handshake also through `api-gateway-bff` (S12).

### Internal RPC
Every RPC is in `contracts/service_acl/matrix.yaml` (I11). Example entry:
```yaml
- caller: roleplay-service
  callee: provider-registry-service
  rpc: GetProviderConfig
  principal_mode: requires_user
  tls: mTLS  # V1+30d; V1 uses JWT-SVID + LB-TLS
```

### Event topics
- Per-service emit: `<service-name>.<entity>.<verb>` (e.g., `reality.created`, `turn.completed`)
- Cross-reality: `xreality.<verb>` (e.g., `xreality.canon.promoted`) — only `meta-worker` consumes
- Cross-session: `xsession.<verb>` — only `event-handler` consumes
- All events go through outbox (I13), never direct `redis.XAdd`

### Shared meta DB
Single `loreweave_meta` DB contains:
- `reality_registry` (reality-to-shard allocation, status, deploy_cohort, queue_policy)
- `pii_registry` (S8 — user crypto-shred envelope)
- `user_consent_ledger` (S8)
- `book_authorship` (S13 — canon authority)
- `canon_entries` + `canonization_audit` (S13)
- `prompt_audit` (S9, retention 90d hot / 2y cold)
- `user_cost_ledger` (S6, retention 2y, pseudonymize at 2y per S8)
- `user_queue_metrics` (S7)
- `admin_action_audit` + `service_to_service_audit` (5y)
- `meta_write_audit` + `meta_read_audit`
- `incidents` + `feature_flags` + `deploy_audit`
- `pii_kek` (KEK envelope store; crypto-shred target for user erasure)

All meta writes via `MetaWrite()` (I8). No service reads meta DB directly except via `contracts/meta/` library.

---

## When you add a new service

1. Claim name in this file (append row).
2. Register SVID + add ACL matrix rows for every RPC.
3. Declare Postgres role + owned DB (I4).
4. Declare event topics emitted + consumed.
5. Add runbook in `docs/sre/runbooks/<domain>/<service>.md` (SR3 27-runbook-gate applies if V1-critical).
6. Add to `03_service_map.md` — this file.

All 6 in the same commit as the service scaffold. See `07_feature_workflow.md` §"New service" for the full checklist.
